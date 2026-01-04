"""
Dreamina 纯 API 注册功能
不需要打开浏览器，直接通过 API 注册账号
"""

import requests
import random
import string
import time
import re
from typing import Optional, Dict

# Tempmail API 配置
TEMPMAIL_API_KEY = "tempmail.20251223.7eftc4cqujo8m0bifqr1sdq4fkmm3agqkp3i31gz1xq382yx"

# 默认代理（设为 None 表示直连）
DEFAULT_PROXY = None

# 导入代理配置（自动判断本机或局域网）
from proxy_config import get_proxy_list

# 代理列表（用于轮询）
PROXY_LIST = get_proxy_list()  # 自动判断使用本机或局域网代理

# 代理索引
_proxy_index = 0


def get_next_proxy() -> str:
    """获取下一个代理（轮询）"""
    global _proxy_index
    if not PROXY_LIST:
        return DEFAULT_PROXY
    proxy = PROXY_LIST[_proxy_index % len(PROXY_LIST)]
    _proxy_index += 1
    return proxy


def random_delay(min_sec: float = 1.0, max_sec: float = 3.0):
    """随机延迟，模拟人类操作"""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


def encode_mix_mode(text: str) -> str:
    """使用 mix_mode=1 编码（XOR 5 然后转 hex）"""
    result = []
    for char in text:
        encoded_byte = ord(char) ^ 5
        result.append(f'{encoded_byte:02x}')
    return ''.join(result)


def generate_password(length: int = 12) -> str:
    """生成随机密码"""
    chars = string.ascii_letters + string.digits
    password = ''.join(random.choices(chars, k=length))
    # 确保包含大小写和数字
    password = password + random.choice(string.ascii_uppercase)
    password = password + random.choice(string.ascii_lowercase)
    password = password + random.choice(string.digits)
    return password


def generate_birthday() -> str:
    """生成随机生日 (1980-2000)"""
    year = random.randint(1980, 2000)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year}-{month:02d}-{day:02d}"


def generate_device_id() -> str:
    """生成设备 ID"""
    return str(random.randint(7500000000000000000, 7600000000000000000))


def generate_verify_fp() -> str:
    """生成 verifyFp"""
    chars = string.ascii_letters + string.digits
    random_part = ''.join(random.choices(chars, k=32))
    return f"verify_{random_part[:8]}_{random_part[8:16]}_{random_part[16:20]}_{random_part[20:24]}_{random_part[24:32]}"


class TempMailClient:
    """临时邮箱客户端"""
    
    def __init__(self, api_key: str, proxy: str = None):
        self.api_key = api_key
        self.base_url = "https://api.tempmail.lol"
        self.headers = {"Authorization": api_key}
        self.proxies = None
        if proxy:
            self.proxies = {
                "http": f"http://{proxy}",
                "https": f"http://{proxy}"
            }
    
    def create_inbox(self) -> dict:
        """创建临时邮箱"""
        try:
            resp = requests.post(
                f"{self.base_url}/v2/inbox/create",
                headers=self.headers,
                proxies=self.proxies,
                timeout=15
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}
    
    def get_emails(self, token: str) -> list:
        """获取邮件列表"""
        try:
            resp = requests.get(
                f"{self.base_url}/v2/inbox",
                headers=self.headers,
                params={"token": token},
                proxies=self.proxies,
                timeout=15
            )
            if resp.status_code == 200:
                return resp.json().get("emails", [])
        except:
            pass
        return []
    
    def wait_for_code(self, token: str, timeout: int = 90) -> Optional[str]:
        """等待验证码"""
        print(f"等待验证码邮件（{timeout}秒超时）...")
        start = time.time()
        
        while time.time() - start < timeout:
            emails = self.get_emails(token)
            for email in emails:
                subject = email.get("subject", "")
                body = email.get("body", "") or email.get("html", "")
                
                if "code" in subject.lower() or "verify" in subject.lower():
                    # 提取 6 位字母数字验证码
                    codes = re.findall(r'\b([A-Z0-9]{6})\b', body)
                    if codes:
                        print(f"✓ 找到验证码: {codes[0]}")
                        return codes[0]
            
            time.sleep(3)
        
        print("✗ 等待验证码超时")
        return None


class DreaminaAPIRegister:
    """Dreamina API 注册"""
    
    BASE_URL = "https://login.us.capcut.com"
    AID = "513641"
    SDK_VERSION = "2.1.10-tiktok"
    
    def __init__(self, proxy: str = None):
        self.proxy = proxy
        self.proxies = None
        if proxy:
            self.proxies = {
                "http": f"http://{proxy}",
                "https": f"http://{proxy}"
            }
        
        self.device_id = generate_device_id()
        self.verify_fp = generate_verify_fp()
        self.csrf_token = None
        self.ms_token = None
        self.ttwid = None
        
        self.session = requests.Session()
        if self.proxies:
            self.session.proxies = self.proxies
    
    def _get_common_params(self) -> dict:
        return {
            "aid": self.AID,
            "account_sdk_source": "web",
            "sdk_version": self.SDK_VERSION,
            "language": "en",
            "verifyFp": self.verify_fp,
        }
    
    def _get_common_headers(self) -> dict:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "Origin": "https://dreamina.capcut.com",
            "Referer": "https://dreamina.capcut.com/",
            "appid": self.AID,
            "did": self.device_id,
        }
        if self.csrf_token:
            headers["x-tt-passport-csrf-token"] = self.csrf_token
        return headers
    
    def init_session(self) -> bool:
        """初始化会话，获取必要的 token"""
        try:
            # 先访问主页获取基础 cookies
            resp = self.session.get(
                "https://dreamina.capcut.com/ai-tool/home",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                },
                timeout=30
            )
            print(f"  访问主页状态: {resp.status_code}")
            
            # 从 cookies 中提取 token
            cookies = self.session.cookies.get_dict()
            self.csrf_token = cookies.get("passport_csrf_token") or cookies.get("passport_csrf_token_default")
            self.ms_token = cookies.get("msToken")
            self.ttwid = cookies.get("ttwid")
            
            # 如果没有必要的 token，尝试访问 passport 接口
            if not self.csrf_token or not self.ms_token:
                resp = self.session.get(
                    f"{self.BASE_URL}/passport/web/account/info/v2",
                    params={"aid": self.AID, "account_sdk_source": "web"},
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Origin": "https://dreamina.capcut.com",
                        "Referer": "https://dreamina.capcut.com/",
                    },
                    timeout=30
                )
                cookies = self.session.cookies.get_dict()
                self.csrf_token = self.csrf_token or cookies.get("passport_csrf_token") or cookies.get("passport_csrf_token_default")
                self.ms_token = self.ms_token or cookies.get("msToken")
            
            print(f"✓ 初始化会话成功")
            print(f"  CSRF Token: {self.csrf_token[:20] if self.csrf_token else 'None'}...")
            print(f"  msToken: {self.ms_token[:20] if self.ms_token else 'None'}...")
            print(f"  ttwid: {self.ttwid[:20] if self.ttwid else 'None'}...")
            print(f"  Cookies: {list(cookies.keys())}")
            return True
        except Exception as e:
            print(f"✗ 初始化会话失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def send_code(self, email: str, password: str) -> bool:
        """发送验证码到邮箱"""
        encoded_email = encode_mix_mode(email)
        encoded_password = encode_mix_mode(password)
        
        data = {
            "mix_mode": "1",
            "email": encoded_email,
            "password": encoded_password,
            "type": "34",
            "fixed_mix_mode": "1",
        }
        
        try:
            resp = self.session.post(
                f"{self.BASE_URL}/passport/web/email/send_code/",
                params=self._get_common_params(),
                headers=self._get_common_headers(),
                data=data,
                timeout=30
            )
            
            result = resp.json()
            print(f"  send_code 响应: {result}")
            
            if result.get("message") == "success" or result.get("data", {}).get("status") == 1:
                print(f"✓ 验证码已发送到 {email}")
                return True
            else:
                print(f"✗ 发送验证码失败: {result}")
                return False
        except Exception as e:
            print(f"✗ 发送验证码出错: {e}")
            return False
    
    def verify_code(self, email: str, code: str) -> Optional[str]:
        """验证验证码，返回 email_ticket"""
        encoded_email = encode_mix_mode(email)
        encoded_code = encode_mix_mode(code)
        
        data = {
            "mix_mode": "1",
            "email": encoded_email,
            "code": encoded_code,
            "type": "34",
            "fixed_mix_mode": "1",
        }
        
        try:
            resp = self.session.post(
                f"{self.BASE_URL}/passport/web/email/register/code_verify/",
                params=self._get_common_params(),
                headers=self._get_common_headers(),
                data=data,
                timeout=30
            )
            
            result = resp.json()
            if result.get("message") == "success":
                email_ticket = result.get("data", {}).get("email_ticket")
                if email_ticket:
                    print(f"✓ 验证码验证成功")
                    return email_ticket
            
            print(f"✗ 验证码验证失败: {result}")
            return None
        except Exception as e:
            print(f"✗ 验证码验证出错: {e}")
            return None
    
    def register(self, email: str, code: str, password: str, email_ticket: str, birthday: str) -> Optional[Dict]:
        """完成注册并登录"""
        encoded_email = encode_mix_mode(email)
        encoded_code = encode_mix_mode(code)
        encoded_password = encode_mix_mode(password)
        
        data = {
            "mix_mode": "1",
            "email": encoded_email,
            "code": encoded_code,
            "password": encoded_password,
            "type": "34",
            "email_ticket": email_ticket,
            "birthday": birthday,
            "force_user_region": "US",
            "biz_param": "{}",
            "fixed_mix_mode": "1",
        }
        
        try:
            resp = self.session.post(
                f"{self.BASE_URL}/passport/web/email/register_verify_login/",
                params=self._get_common_params(),
                headers=self._get_common_headers(),
                data=data,
                timeout=30
            )
            
            result = resp.json()
            if result.get("message") == "success":
                # 从 cookies 中获取 sessionid
                cookies = self.session.cookies.get_dict()
                sessionid = cookies.get("sessionid") or cookies.get("sid_tt")
                
                if sessionid:
                    print(f"✓ 注册成功！")
                    print(f"  SessionID: {sessionid[:30]}...")
                    return {
                        "sessionid": sessionid,
                        "email": email,
                        "password": password,
                        "region": "us",
                        "full_token": f"us-{sessionid}",
                    }
            
            print(f"✗ 注册失败: {result}")
            return None
        except Exception as e:
            print(f"✗ 注册出错: {e}")
            return None


def api_register(proxy: str = None, save: bool = True, use_proxy_rotation: bool = False) -> Optional[Dict]:
    """
    纯 API 注册 Dreamina 账号
    
    Args:
        proxy: 代理地址（如果指定则使用固定代理）
        save: 是否保存到 .env
        use_proxy_rotation: 是否使用代理轮询
    
    Returns:
        注册成功返回凭证，失败返回 None
    """
    # 选择代理
    if use_proxy_rotation:
        current_proxy = get_next_proxy()
    else:
        current_proxy = proxy or DEFAULT_PROXY
    
    # 1. 创建临时邮箱
    print("=" * 50)
    print("开始 API 注册 Dreamina 账号")
    print(f"使用代理: {current_proxy}")
    print("=" * 50)
    
    tempmail = TempMailClient(TEMPMAIL_API_KEY, proxy=current_proxy)
    inbox = tempmail.create_inbox()
    
    if "address" not in inbox:
        print(f"✗ 创建临时邮箱失败: {inbox.get('error')}")
        return None
    
    email = inbox["address"]
    inbox_token = inbox["token"]
    print(f"✓ 创建临时邮箱: {email}")
    
    # 随机延迟
    random_delay(1, 2)
    
    # 2. 初始化 API 客户端
    api = DreaminaAPIRegister(proxy=current_proxy)
    if not api.init_session():
        return None
    
    # 生成密码
    password = generate_password()
    print(f"✓ 生成密码: {password}")
    
    # 随机延迟
    random_delay(0.5, 1.5)
    
    # 3. 发送验证码
    if not api.send_code(email, password):
        return None
    
    # 4. 等待验证码
    code = tempmail.wait_for_code(inbox_token, timeout=90)
    if not code:
        return None
    
    # 随机延迟
    random_delay(1, 2)
    
    # 5. 验证验证码
    email_ticket = api.verify_code(email, code)
    if not email_ticket:
        return None
    
    # 随机延迟
    random_delay(0.5, 1)
    
    # 6. 完成注册
    birthday = generate_birthday()
    
    credentials = api.register(email, code, password, email_ticket, birthday)
    
    if credentials and save:
        from jimeng_login_helper import save_to_env
        save_to_env(credentials)
    
    return credentials


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Dreamina API 注册")
    parser.add_argument("-p", "--proxy", type=str, default=DEFAULT_PROXY, help="代理地址")
    parser.add_argument("-s", "--save", action="store_true", help="保存到 .env")
    parser.add_argument("-c", "--count", type=int, default=1, help="注册数量")
    parser.add_argument("-r", "--rotation", action="store_true", help="启用代理轮询")
    parser.add_argument("-d", "--delay", type=int, default=5, help="每次注册间隔（秒）")
    
    args = parser.parse_args()
    
    if args.rotation:
        print(f"✓ 启用代理轮询，代理池: {len(PROXY_LIST)} 个")
    
    success_count = 0
    fail_count = 0
    
    for i in range(args.count):
        if args.count > 1:
            print(f"\n[{i+1}/{args.count}] 开始注册...")
        
        result = api_register(
            proxy=args.proxy if not args.rotation else None,
            save=args.save,
            use_proxy_rotation=args.rotation
        )
        
        if result:
            success_count += 1
            print(f"\n注册成功！")
            print(f"Email: {result['email']}")
            print(f"Token: {result['full_token'][:40]}...")
        else:
            fail_count += 1
            print(f"\n注册失败")
        
        if i < args.count - 1:
            delay = args.delay + random.randint(0, 3)  # 随机化延迟
            print(f"\n等待 {delay} 秒...")
            time.sleep(delay)
    
    if args.count > 1:
        print(f"\n{'='*50}")
        print(f"批量注册完成！成功: {success_count}, 失败: {fail_count}")
        print(f"{'='*50}")
