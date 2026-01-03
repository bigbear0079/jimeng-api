"""
获取 Dreamina 历史任务
"""

import requests
import json
import sys

# Dreamina US API
BASE_URL = "https://dreamina-api.us.capcut.com"
AID = 513641

def get_history(sessionid: str, page: int = 1, page_size: int = 20):
    """获取历史生成任务"""
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Cookie": f"sessionid={sessionid}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Origin": "https://dreamina.capcut.com",
        "Referer": "https://dreamina.capcut.com/",
    }
    
    params = {
        "aid": AID,
        "device_platform": "web",
        "region": "US",
        "web_version": "7.5.0",
    }
    
    # 获取草稿列表 - 使用正确的 API 路径
    data = {
        "scene": "image",
        "page": page,
        "page_size": page_size,
        "order_by": "update_time",
        "http_common_info": {"aid": AID}
    }
    
    try:
        resp = requests.post(
            f"{BASE_URL}/mweb/v1/get_aigc_history",
            headers=headers,
            params=params,
            json=data,
            timeout=30,
            proxies={"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}
        )
        
        if resp.status_code == 200:
            result = resp.json()
            return result
        else:
            print(f"请求失败: {resp.status_code}")
            print(resp.text)
            return None
    except Exception as e:
        print(f"请求出错: {e}")
        return None


def print_tasks(data: dict):
    """打印任务列表"""
    if not data:
        print("没有数据")
        return
    
    drafts = data.get("data", {}).get("drafts", [])
    
    if not drafts:
        print("没有找到任务")
        return
    
    print(f"\n{'='*60}")
    print(f"找到 {len(drafts)} 个任务")
    print(f"{'='*60}\n")
    
    for i, draft in enumerate(drafts):
        draft_id = draft.get("draft_id", "")
        title = draft.get("title", "无标题")
        status = draft.get("status", "")
        cover_url = draft.get("cover_url", "")
        create_time = draft.get("create_time", 0)
        update_time = draft.get("update_time", 0)
        
        # 状态映射
        status_map = {
            "0": "排队中",
            "1": "生成中", 
            "2": "已完成",
            "3": "失败",
        }
        status_text = status_map.get(str(status), f"未知({status})")
        
        print(f"[{i+1}] {title}")
        print(f"    ID: {draft_id}")
        print(f"    状态: {status_text}")
        if cover_url:
            print(f"    封面: {cover_url[:80]}...")
        print()


if __name__ == "__main__":
    # 从 .env 读取 token
    import os
    
    env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
    sessionid = None
    
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if line.startswith("JIMENG_TOKEN_3="):
                    token = line.split("=", 1)[1].strip()
                    # 去掉 us- 前缀
                    if token.startswith("us-"):
                        sessionid = token[3:]
                    else:
                        sessionid = token
                    break
    
    if not sessionid:
        print("未找到 sessionid，请检查 .env 文件")
        sys.exit(1)
    
    print(f"使用 sessionid: {sessionid[:20]}...")
    
    result = get_history(sessionid)
    
    if result:
        print_tasks(result)
        
        # 保存原始数据
        with open("history_result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("原始数据已保存到 history_result.json")
