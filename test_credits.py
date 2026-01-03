"""测试积分 API"""
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("JIMENG_TOKEN_3")
if token.startswith("us-"):
    sessionid = token[3:]
else:
    sessionid = token

print(f"Token: {token[:30]}...")
print(f"SessionID: {sessionid[:30]}...")

headers = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Cookie": f"sessionid={sessionid}",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Origin": "https://dreamina.capcut.com",
    "Referer": "https://dreamina.capcut.com/",
}

proxies = {
    "http": "http://127.0.0.1:7897",
    "https": "http://127.0.0.1:7897",
}

url = "https://commerce.us.capcut.com/commerce/v1/benefits/user_credit"

print(f"\n请求 URL: {url}")

resp = requests.post(url, headers=headers, json={}, timeout=30, proxies=proxies)

print(f"状态码: {resp.status_code}")
print(f"\n响应内容:")
print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
