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
            
            # 提取图片URL 和 history_id
            image_urls = []
            history_id = None
            if "data" in result and isinstance(result["data"], list):
                for item in result["data"]:
                    if "url" in item:
                        image_urls.append(item["url"])
                    # 尝试提取 history_id
                    if "history_id" in item:
                        history_id = item["history_id"]
            
            # 如果没有从 data 中获取到 history_id，尝试从其他位置获取
            if not history_id and "history_id" in result:
                history_id = result["history_id"]
            
            # 使用 history_id 作为 task_id，如果没有则用本地生成的
            task_id = history_id or f"img_{datetime.now().strftime('%Y%m%d%H%M%S')}_{account_id}"
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


# ============ 历史任务查询 API ============

@app.get("/api/history", tags=["历史任务"])
async def get_dreamina_history(
    account_id: int = 1,
    page: int = 1,
    page_size: int = 20,
    scene: str = "image",
    history_id: str = None,
):
    """查询 Dreamina 历史生成任务（输入任务ID直接查询）"""
    import httpx
    
    # 获取账户 token - 从 .env 获取
    env_accounts = get_env_accounts()
    if account_id not in env_accounts:
        raise HTTPException(status_code=404, detail=f"账户 {account_id} 不存在")
    
    token = env_accounts[account_id]["token"]
    if not token:
        raise HTTPException(status_code=400, detail="账户 token 为空")
    
    # 解析 sessionid
    if token.startswith("us-"):
        sessionid = token[3:]
        region = "US"
        base_url = "https://dreamina-api.us.capcut.com"
    elif token.startswith("cn-"):
        sessionid = token[3:]
        region = "CN"
        base_url = "https://jimeng-api.jianying.com"
    else:
        sessionid = token
        region = "US"
        base_url = "https://dreamina-api.us.capcut.com"
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Cookie": f"sessionid={sessionid}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Origin": "https://dreamina.capcut.com",
        "Referer": "https://dreamina.capcut.com/",
    }
    
    params = {
        "aid": 513641,
        "device_platform": "web",
        "region": region,
        "web_version": "7.5.0",
    }
    
    # 如果没有提供 history_id，从本地数据库获取
    history_ids = []
    if history_id:
        history_ids = [history_id]
    else:
        # 从本地数据库获取任务ID列表
        conn = get_db()
        cursor = conn.cursor()
        task_type = "image" if scene == "image" else "video"
        offset = (page - 1) * page_size
        
        cursor.execute("""
            SELECT task_id FROM tasks 
            WHERE account_id = ? AND task_type = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (account_id, task_type, page_size, offset))
        rows = cursor.fetchall()
        conn.close()
        
        # 提取数字ID
        for row in rows:
            task_id = row[0]
            if task_id and task_id.isdigit():
                history_ids.append(task_id)
    
    if not history_ids:
        return {
            "success": True,
            "account_id": account_id,
            "tasks": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "message": "没有找到任务记录",
        }
    
    # 用 get_history_by_ids 批量查询
    data = {
        "history_ids": history_ids,
        "image_info": {
            "width": 2048,
            "height": 2048,
            "format": "webp",
            "image_scene_list": [
                {"scene": "normal", "width": 720, "height": 720, "uniq_key": "720", "format": "webp"},
            ]
        }
    }
    
    try:
        async with httpx.AsyncClient(
            timeout=30, proxy=f"http://{PROXY}" if PROXY else None
        ) as client:
            resp = await client.post(
                f"{base_url}/mweb/v1/get_history_by_ids",
                headers=headers,
                params=params,
                json=data,
            )

            if resp.status_code == 200:
                result = resp.json()
                result_data = result.get("data", {})

                # 格式化任务列表
                tasks = []
                for hid in history_ids:
                    history_info = result_data.get(hid, {})
                    if history_info:
                        task_info = history_info.get("task", {})
                        item_list = history_info.get("item_list", [])
                        cover_url = ""
                        title = "无标题"
                        if item_list:
                            cover_url = item_list[0].get("common_attr", {}).get("cover_url", "")
                            title = item_list[0].get("common_attr", {}).get("description", "无标题")

                        status = task_info.get("status", 0)
                        status_map = {10: "已完成", 20: "处理中", 30: "失败", 42: "后处理", 45: "最终处理", 50: "已完成"}

                        tasks.append({
                            "id": hid,
                            "title": title,
                            "status": status,
                            "status_text": status_map.get(status, f"未知({status})"),
                            "cover_url": cover_url,
                            "create_time": history_info.get("created_time", 0),
                            "update_time": task_info.get("finish_time", 0),
                            "image_count": len(item_list),
                        })
                
                return {
                    "success": True,
                    "account_id": account_id,
                    "tasks": tasks,
                    "total": len(tasks),
                    "page": page,
                    "page_size": page_size,
                }
            else:
                raise HTTPException(status_code=resp.status_code, detail=f"API 请求失败: {resp.text}")
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="请求超时")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history/{history_id}", tags=["历史任务"])
async def get_history_detail(
    history_id: str,
    account_id: int = 1,
):
    """查询单个历史任务详情"""
    import httpx
    
    # 获取账户 token - 从 .env 获取
    env_accounts = get_env_accounts()
    if account_id not in env_accounts:
        raise HTTPException(status_code=404, detail=f"账户 {account_id} 不存在")
    
    token = env_accounts[account_id]["token"]
    if token.startswith("us-"):
        sessionid = token[3:]
        base_url = "https://dreamina-api.us.capcut.com"
    else:
        sessionid = token
        base_url = "https://dreamina-api.us.capcut.com"
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Cookie": f"sessionid={sessionid}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Origin": "https://dreamina.capcut.com",
        "Referer": "https://dreamina.capcut.com/",
    }
    
    params = {
        "aid": 513641,
        "device_platform": "web",
        "region": "US",
        "web_version": "7.5.0",
    }
    
    data = {
        "history_ids": [history_id],
        "image_info": {
            "width": 2048,
            "height": 2048,
            "format": "webp",
            "image_scene_list": [
                {"scene": "normal", "width": 1080, "height": 1080, "uniq_key": "1080", "format": "webp"},
            ]
        }
    }
    
    try:
        async with httpx.AsyncClient(
            timeout=30, proxy=f"http://{PROXY}" if PROXY else None
        ) as client:
            resp = await client.post(
                f"{base_url}/mweb/v1/get_history_by_ids",
                headers=headers,
                params=params,
                json=data,
            )
            
            if resp.status_code == 200:
                result = resp.json()
                history_data = result.get("data", {}).get(history_id, {})
                
                # 提取图片列表
                images = []
                item_list = history_data.get("item_list", [])
                for item in item_list:
                    common_attr = item.get("common_attr", {})
                    image_info = item.get("image_info", {})
                    images.append({
                        "id": common_attr.get("id", ""),
                        "description": common_attr.get("description", ""),
                        "cover_url": common_attr.get("cover_url", ""),
                        "url": image_info.get("large_images", [{}])[0].get("image_url", "") if image_info.get("large_images") else "",
                    })
                
                task_info = history_data.get("task", {})
                
                return {
                    "success": True,
                    "history_id": history_id,
                    "status": task_info.get("status", 0),
                    "finish_time": task_info.get("finish_time", 0),
                    "images": images,
                    "raw_data": history_data,
                }
            else:
                raise HTTPException(status_code=resp.status_code, detail=f"API 请求失败: {resp.text}")
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="请求超时")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
