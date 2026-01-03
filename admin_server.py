"""
Dreamina 管理后台 API 服务
启动: uvicorn admin_server:app --reload --port 8100
"""

import os
import json
import asyncio
import sqlite3
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
from dotenv import load_dotenv

from account_manager import (
    list_accounts,
    refresh_all_credits,
    update_account_credits,
    get_env_accounts,
    get_credits_from_api,
    parse_token,
    get_available_account,
)

load_dotenv()

app = FastAPI(
    title="Dreamina 管理后台",
    description="Dreamina 账户管理、积分查询、任务记录",
    version="1.0.0",
)

# 数据库文件
DB_FILE = "data.db"

# Dreamina API 配置
DREAMINA_API = {
    "us": {
        "base_url": "https://dreamina-api.us.capcut.com",
        "aid": 513641,
    },
}

PROXY = "127.0.0.1:7897"


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 任务记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE,
            account_id INTEGER,
            task_type TEXT,
            prompt TEXT,
            status TEXT DEFAULT 'pending',
            result_url TEXT,
            credits_used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 积分记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS credit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            change_amount INTEGER,
            change_type TEXT,
            balance_after INTEGER,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()


# 初始化数据库
init_db()


# ============ 请求模型 ============

class RefreshAccountRequest(BaseModel):
    account_id: Optional[int] = None


class TaskRecord(BaseModel):
    task_id: str
    account_id: int
    task_type: str
    prompt: str
    status: str = "pending"
    credits_used: int = 0


# ============ 账户管理 API ============

@app.get("/api/accounts", tags=["账户管理"])
async def get_accounts():
    """获取所有账户列表"""
    accounts = list_accounts()
    
    total_credits = sum(acc["credits"] for acc in accounts)
    available_count = sum(1 for acc in accounts if acc["credits"] >= 4)
    
    return {
        "accounts": accounts,
        "total_credits": total_credits,
        "available_count": available_count,
        "total_count": len(accounts),
    }


@app.post("/api/accounts/refresh", tags=["账户管理"])
async def refresh_accounts(req: RefreshAccountRequest = None):
    """刷新账户积分"""
    if req and req.account_id:
        # 刷新单个账户
        env_accounts = get_env_accounts()
        if req.account_id not in env_accounts:
            raise HTTPException(status_code=404, detail=f"账户 {req.account_id} 不存在")
        
        token = env_accounts[req.account_id]["token"]
        credits = update_account_credits(req.account_id, token)
        
        return {"success": True, "account_id": req.account_id, "credits": credits}
    else:
        # 刷新所有账户
        results = await asyncio.to_thread(refresh_all_credits)
        return {"success": True, "results": results}


@app.get("/api/accounts/{account_id}/credits", tags=["账户管理"])
async def get_account_credits(account_id: int):
    """获取账户实时积分"""
    env_accounts = get_env_accounts()
    if account_id not in env_accounts:
        raise HTTPException(status_code=404, detail=f"账户 {account_id} 不存在")
    
    token = env_accounts[account_id]["token"]
    credits_info = await asyncio.to_thread(get_credits_from_api, token)
    
    return {
        "account_id": account_id,
        "credits": credits_info,
    }


# ============ 任务管理 API ============

@app.post("/api/tasks", tags=["任务管理"])
async def create_task_record(task: TaskRecord):
    """创建任务记录"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO tasks (task_id, account_id, task_type, prompt, status, credits_used)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (task.task_id, task.account_id, task.task_type, task.prompt, task.status, task.credits_used))
        conn.commit()
        return {"success": True, "task_id": task.task_id}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="任务ID已存在")
    finally:
        conn.close()


@app.get("/api/tasks", tags=["任务管理"])
async def get_tasks(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    account_id: Optional[int] = None,
):
    """获取任务列表"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 构建查询
    where_clauses = []
    params = []
    
    if status:
        where_clauses.append("status = ?")
        params.append(status)
    if task_type:
        where_clauses.append("task_type = ?")
        params.append(task_type)
    if account_id:
        where_clauses.append("account_id = ?")
        params.append(account_id)
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    # 获取总数
    cursor.execute(f"SELECT COUNT(*) FROM tasks WHERE {where_sql}", params)
    total = cursor.fetchone()[0]
    
    # 获取分页数据
    offset = (page - 1) * page_size
    cursor.execute(f"""
        SELECT * FROM tasks 
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, params + [page_size, offset])
    
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {
        "tasks": tasks,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@app.put("/api/tasks/{task_id}", tags=["任务管理"])
async def update_task(task_id: str, status: str, result_url: Optional[str] = None):
    """更新任务状态"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE tasks 
        SET status = ?, result_url = ?, updated_at = CURRENT_TIMESTAMP
        WHERE task_id = ?
    """, (status, result_url, task_id))
    
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="任务不存在")
    
    conn.commit()
    conn.close()
    
    return {"success": True, "task_id": task_id, "status": status}


@app.get("/api/tasks/stats", tags=["任务管理"])
async def get_task_stats():
    """获取任务统计"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 总任务数
    cursor.execute("SELECT COUNT(*) FROM tasks")
    total = cursor.fetchone()[0]
    
    # 按状态统计
    cursor.execute("""
        SELECT status, COUNT(*) as count 
        FROM tasks 
        GROUP BY status
    """)
    status_stats = {row["status"]: row["count"] for row in cursor.fetchall()}
    
    # 按类型统计
    cursor.execute("""
        SELECT task_type, COUNT(*) as count 
        FROM tasks 
        GROUP BY task_type
    """)
    type_stats = {row["task_type"]: row["count"] for row in cursor.fetchall()}
    
    # 今日任务数
    cursor.execute("""
        SELECT COUNT(*) FROM tasks 
        WHERE date(created_at) = date('now')
    """)
    today_count = cursor.fetchone()[0]
    
    # 总消耗积分
    cursor.execute("SELECT SUM(credits_used) FROM tasks")
    total_credits = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return {
        "total": total,
        "today": today_count,
        "by_status": status_stats,
        "by_type": type_stats,
        "total_credits_used": total_credits,
    }


# ============ 图片生成 API (代理到 jimeng-api) ============

JIMENG_API_URL = "http://127.0.0.1:5100"


class ImageGenerateRequest(BaseModel):
    prompt: str
    model: str = "jimeng-4.5"
    ratio: str = "1:1"
    resolution: str = "2k"
    account_id: Optional[int] = None


class VideoGenerateRequest(BaseModel):
    prompt: str
    model: str = "jimeng-video-3.5-pro"
    ratio: str = "16:9"
    duration: int = 5
    account_id: Optional[int] = None


@app.post("/api/generate/image", tags=["生成任务"])
async def generate_image(req: ImageGenerateRequest):
    """生成图片（代理到 jimeng-api）"""
    import httpx
    
    # 选择账户
    if req.account_id:
        account_id = req.account_id
    else:
        account_id = get_available_account(min_credits=4)
        if not account_id:
            raise HTTPException(status_code=400, detail="没有可用账户（积分不足）")
    
    # 获取 token
    env_accounts = get_env_accounts()
    if account_id not in env_accounts:
        raise HTTPException(status_code=404, detail=f"账户 {account_id} 不存在")
    
    token = env_accounts[account_id]["token"]
    
    # 调用 jimeng-api
    async with httpx.AsyncClient(timeout=1200) as client:  # 20分钟超时
        try:
            resp = await client.post(
                f"{JIMENG_API_URL}/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": req.model,
                    "prompt": req.prompt,
                    "ratio": req.ratio,
                    "resolution": req.resolution,
                },
            )
            
            result = resp.json()
            
            # 提取图片URL
            image_urls = []
            if "data" in result and isinstance(result["data"], list):
                for item in result["data"]:
                    if "url" in item:
                        image_urls.append(item["url"])
            
            # 记录任务
            task_id = f"img_{datetime.now().strftime('%Y%m%d%H%M%S')}_{account_id}"
            result_url = image_urls[0] if image_urls else None
            status = "completed" if resp.status_code == 200 and image_urls else "failed"
            
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tasks (task_id, account_id, task_type, prompt, status, result_url, credits_used)
                VALUES (?, ?, 'image', ?, ?, ?, ?)
            """, (task_id, account_id, req.prompt, status, result_url, 4 if status == "completed" else 0))
            conn.commit()
            conn.close()
            
            # 刷新积分
            await asyncio.to_thread(update_account_credits, account_id, token)
            
            return {
                "success": resp.status_code == 200 and len(image_urls) > 0,
                "account_id": account_id,
                "data": result,
                "images": image_urls,
            }
            
        except httpx.TimeoutException:
            # 超时也记录任务
            conn = get_db()
            cursor = conn.cursor()
            task_id = f"img_{datetime.now().strftime('%Y%m%d%H%M%S')}_{account_id}"
            cursor.execute("""
                INSERT INTO tasks (task_id, account_id, task_type, prompt, status, credits_used)
                VALUES (?, ?, 'image', ?, 'timeout', 4)
            """, (task_id, account_id, req.prompt))
            conn.commit()
            conn.close()
            raise HTTPException(status_code=504, detail="生成超时，请稍后查询结果")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate/video", tags=["生成任务"])
async def generate_video(req: VideoGenerateRequest):
    """生成视频（代理到 jimeng-api）"""
    import httpx
    
    # 选择账户
    if req.account_id:
        account_id = req.account_id
    else:
        account_id = get_available_account(min_credits=20)
        if not account_id:
            raise HTTPException(status_code=400, detail="没有可用账户（积分不足）")
    
    # 获取 token
    env_accounts = get_env_accounts()
    if account_id not in env_accounts:
        raise HTTPException(status_code=404, detail=f"账户 {account_id} 不存在")
    
    token = env_accounts[account_id]["token"]
    
    # 调用 jimeng-api
    async with httpx.AsyncClient(timeout=1200) as client:
        try:
            resp = await client.post(
                f"{JIMENG_API_URL}/v1/videos/generations",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": req.model,
                    "prompt": req.prompt,
                    "ratio": req.ratio,
                    "duration": req.duration,
                },
            )
            
            result = resp.json()
            
            # 记录任务
            if resp.status_code == 200:
                conn = get_db()
                cursor = conn.cursor()
                task_id = f"vid_{datetime.now().strftime('%Y%m%d%H%M%S')}_{account_id}"
                cursor.execute("""
                    INSERT INTO tasks (task_id, account_id, task_type, prompt, status, credits_used)
                    VALUES (?, ?, 'video', ?, 'completed', 20)
                """, (task_id, account_id, req.prompt))
                conn.commit()
                conn.close()
                
                # 刷新积分
                await asyncio.to_thread(update_account_credits, account_id, token)
            
            return {
                "success": resp.status_code == 200,
                "account_id": account_id,
                "data": result,
            }
            
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="生成超时，请稍后查询结果")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


# ============ 积分记录 API ============

@app.get("/api/credit-logs", tags=["积分记录"])
async def get_credit_logs(
    page: int = 1,
    page_size: int = 50,
    account_id: Optional[int] = None,
):
    """获取积分变动记录"""
    conn = get_db()
    cursor = conn.cursor()
    
    where_sql = "account_id = ?" if account_id else "1=1"
    params = [account_id] if account_id else []
    
    # 获取总数
    cursor.execute(f"SELECT COUNT(*) FROM credit_logs WHERE {where_sql}", params)
    total = cursor.fetchone()[0]
    
    # 获取分页数据
    offset = (page - 1) * page_size
    cursor.execute(f"""
        SELECT * FROM credit_logs 
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, params + [page_size, offset])
    
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {
        "logs": logs,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.post("/api/credit-logs", tags=["积分记录"])
async def add_credit_log(
    account_id: int,
    change_amount: int,
    change_type: str,
    balance_after: int,
    description: str = "",
):
    """添加积分变动记录"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO credit_logs (account_id, change_amount, change_type, balance_after, description)
        VALUES (?, ?, ?, ?, ?)
    """, (account_id, change_amount, change_type, balance_after, description))
    
    conn.commit()
    conn.close()
    
    return {"success": True}


# ============ 静态文件 ============

# 挂载静态文件目录
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", tags=["页面"])
async def index():
    """管理后台首页"""
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Dreamina 管理后台 API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
