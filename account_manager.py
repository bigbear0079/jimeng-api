"""
Dreamina 账户管理器
管理多账户积分、自动选择可用账户
"""

import json
import os
import threading
import requests
from datetime import datetime, date, timezone, timedelta
from typing import Optional, Dict, List

# UTC+8 时区（北京时间）
UTC_PLUS_8 = timezone(timedelta(hours=8))

ACCOUNTS_FILE = "accounts.json"
MIN_CREDITS = 4  # 最低积分要求（1K图片需要4积分）

# 文件锁，防止并发写入冲突
_accounts_file_lock = threading.Lock()

# Dreamina API 配置
DREAMINA_API = {
    "us": {
        "base_url": "https://dreamina-api.us.capcut.com",
        "commerce_url": "https://commerce.us.capcut.com",
        "aid": 513641,
    },
    "hk": {
        "base_url": "https://mweb-api-sg.capcut.com",
        "commerce_url": "https://commerce-api-sg.capcut.com",
        "aid": 513641,
    },
}

# 导入代理配置（自动判断本机或局域网）
from proxy_config import PROXY_HOST

# 代理配置
PROXY = f"{PROXY_HOST}:7897"


def get_proxy_dict():
    """获取代理字典"""
    if PROXY:
        return {
            "http": f"http://{PROXY}",
            "https": f"http://{PROXY}",
        }
    return None


def load_accounts() -> dict:
    """加载账户数据（线程安全）"""
    with _accounts_file_lock:
        if not os.path.exists(ACCOUNTS_FILE):
            return {"accounts": {}, "last_reset_date": ""}
        
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_accounts(data: dict):
    """保存账户数据（线程安全）"""
    with _accounts_file_lock:
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def check_and_reset_daily(data: dict) -> dict:
    """检查是否需要每日重置（基于 UTC+8 时区）"""
    today = datetime.now(UTC_PLUS_8).date().isoformat()
    
    if data.get("last_reset_date") != today:
        print(f"[账户管理] 新的一天 ({today})，标记需要刷新积分")
        data["last_reset_date"] = today
        save_accounts(data)
    
    return data


def parse_token(token: str) -> tuple:
    """解析 token，返回 (region, sessionid)"""
    token = token.strip()
    for prefix in ["us-", "hk-", "jp-", "sg-"]:
        if token.lower().startswith(prefix):
            return prefix[:-1], token[3:]
    return "cn", token


def get_credits_from_api(token: str) -> dict:
    """从 jimeng-api 获取账户积分"""
    try:
        resp = requests.post(
            "http://127.0.0.1:5100/token/points",
            headers={"Authorization": f"Bearer {token}"},
            json={},
            timeout=30,
        )
        
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                points = data[0].get("points", {})
                return {
                    "gift_credit": points.get("giftCredit", 0),
                    "purchase_credit": points.get("purchaseCredit", 0),
                    "vip_credit": points.get("vipCredit", 0),
                    "total": points.get("totalCredit", 0),
                    "valid": True,
                }
    except Exception as e:
        print(f"[API] 获取积分失败: {e}")
    
    return {"total": 0, "valid": False}


def receive_credits_from_api(token: str) -> dict:
    """从 jimeng-api 领取每日积分"""
    try:
        resp = requests.post(
            "http://127.0.0.1:5100/token/receive",
            headers={"Authorization": f"Bearer {token}"},
            json={},
            timeout=60,
        )
        
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                credits = data[0].get("credits", {})
                return {
                    "gift_credit": credits.get("giftCredit", 0),
                    "purchase_credit": credits.get("purchaseCredit", 0),
                    "vip_credit": credits.get("vipCredit", 0),
                    "total": credits.get("totalCredit", 0),
                    "valid": True,
                }
    except Exception as e:
        print(f"[API] 领取积分失败: {e}")
    
    return {"total": 0, "valid": False}


def update_account_credits(account_id: int, token: str, email: str = None) -> int:
    """
    更新账户积分
    
    Returns:
        积分数量，如果 token 无效返回 -1
    """
    data = load_accounts()
    data = check_and_reset_daily(data)
    
    credits_info = get_credits_from_api(token)
    
    if not credits_info.get("valid"):
        print(f"[账户 {account_id}] Token 无效或查询失败")
        return -1
    
    # 如果积分为 0，尝试领取每日积分
    if credits_info.get("total", 0) == 0:
        print(f"[账户 {account_id}] 积分为 0，尝试领取每日积分...")
        receive_result = receive_credits_from_api(token)
        if receive_result.get("valid") and receive_result.get("total", 0) > 0:
            credits_info = receive_result
            print(f"[账户 {account_id}] 领取成功！")
        else:
            print(f"[账户 {account_id}] 领取失败或无可领取积分")
    
    credits = credits_info.get("total", 0)
    region, _ = parse_token(token)
    
    # 更新账户信息
    data["accounts"][str(account_id)] = {
        "credits": credits,
        "gift_credit": credits_info.get("gift_credit", 0),
        "purchase_credit": credits_info.get("purchase_credit", 0),
        "vip_credit": credits_info.get("vip_credit", 0),
        "email": email,
        "region": region,
        "last_update": datetime.now().isoformat(),
        "token": token[:25] + "..."
    }
    save_accounts(data)
    print(f"[账户 {account_id}] 积分: {credits} (赠送:{credits_info.get('gift_credit', 0)}, 购买:{credits_info.get('purchase_credit', 0)}, VIP:{credits_info.get('vip_credit', 0)})")
    return credits


def get_available_account(exclude: set = None, min_credits: int = None) -> Optional[int]:
    """
    获取一个可用的账户
    
    Args:
        exclude: 要排除的账户ID集合
        min_credits: 最低积分要求，默认使用 MIN_CREDITS
    """
    data = load_accounts()
    data = check_and_reset_daily(data)
    exclude = exclude or set()
    min_credits = min_credits or MIN_CREDITS

    for account_id, info in data.get("accounts", {}).items():
        acc_id = int(account_id)
        if acc_id in exclude:
            continue
        credits = info.get("credits", 0)
        if credits >= min_credits:
            return acc_id

    return None


def deduct_credits(account_id: int, amount: int = 4):
    """扣除账户积分"""
    data = load_accounts()
    
    account_key = str(account_id)
    if account_key in data.get("accounts", {}):
        current = data["accounts"][account_key].get("credits", 0)
        data["accounts"][account_key]["credits"] = max(0, current - amount)
        data["accounts"][account_key]["last_update"] = datetime.now().isoformat()
        save_accounts(data)
        print(f"[账户 {account_id}] 扣除 {amount} 积分，剩余: {data['accounts'][account_key]['credits']}")


def set_account_credits(account_id: int, credits: int):
    """设置账户积分"""
    data = load_accounts()
    
    account_key = str(account_id)
    if account_key in data.get("accounts", {}):
        data["accounts"][account_key]["credits"] = credits
        data["accounts"][account_key]["last_update"] = datetime.now().isoformat()
        save_accounts(data)
        print(f"[账户 {account_id}] 积分设置为: {credits}")


def list_accounts() -> List[dict]:
    """列出所有账户状态"""
    data = load_accounts()
    data = check_and_reset_daily(data)
    
    accounts = []
    for account_id, info in data.get("accounts", {}).items():
        accounts.append({
            "id": int(account_id),
            "credits": info.get("credits", 0),
            "gift_credit": info.get("gift_credit", 0),
            "purchase_credit": info.get("purchase_credit", 0),
            "vip_credit": info.get("vip_credit", 0),
            "email": info.get("email", ""),
            "region": info.get("region", "us"),
            "last_update": info.get("last_update", ""),
            "status": "available" if info.get("credits", 0) >= MIN_CREDITS else "low_credits",
        })
    
    return sorted(accounts, key=lambda x: x["id"])


def get_env_accounts() -> Dict[int, dict]:
    """从 .env 获取所有账户配置"""
    from dotenv import load_dotenv
    load_dotenv(override=True)
    
    accounts = {}
    # 扫描 1-100 范围内的账户
    for i in range(1, 101):
        token = os.getenv(f"JIMENG_TOKEN_{i}")
        if token:
            region, _ = parse_token(token)
            accounts[i] = {"token": token, "region": region}
    
    return accounts


def refresh_all_credits():
    """刷新所有账户的积分"""
    env_accounts = get_env_accounts()
    
    results = []
    for account_id, config in env_accounts.items():
        print(f"刷新账户 {account_id}...")
        credits = update_account_credits(
            account_id=account_id,
            token=config["token"],
        )
        results.append({
            "id": account_id,
            "credits": credits,
            "valid": credits >= 0,
        })
    
    return results


def print_accounts():
    """打印所有账户信息"""
    accounts = list_accounts()
    
    print("\n" + "=" * 60)
    print(f"Dreamina 账户列表 ({len(accounts)} 个)")
    print("=" * 60)
    
    total_credits = 0
    available_count = 0
    
    for acc in accounts:
        credits = acc["credits"]
        total_credits += credits
        status = "✓ 可用" if credits >= MIN_CREDITS else "✗ 积分不足"
        if credits >= MIN_CREDITS:
            available_count += 1
        
        print(f"\n账户 {acc['id']} ({acc['region'].upper()}):")
        print(f"  积分: {credits} (赠送:{acc['gift_credit']}, 购买:{acc['purchase_credit']}, VIP:{acc['vip_credit']})")
        print(f"  状态: {status}")
        if acc["email"]:
            print(f"  邮箱: {acc['email']}")
        print(f"  更新: {acc['last_update'][:19] if acc['last_update'] else '未知'}")
    
    print("\n" + "-" * 60)
    print(f"总积分: {total_credits} | 可用账户: {available_count}/{len(accounts)}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Dreamina 账户管理器")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有账户")
    parser.add_argument("--refresh", "-r", action="store_true", help="刷新所有账户积分")
    args = parser.parse_args()
    
    if args.refresh:
        refresh_all_credits()
    
    print_accounts()
