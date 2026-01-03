"""
即梦 (Jimeng) / Dreamina 登录助手
使用 undetected-chromedriver 自动获取 sessionid
支持国内站 (jimeng.jianying.com) 和国际站 (dreamina.capcut.com)

登录方式:
- 国内站: 手机号登录、抖音扫码登录、邮箱登录
- 国际站: Google 账号、TikTok 账号、Facebook、邮箱、CapCut Mobile

使用方法:
1. 安装依赖: pip install undetected-chromedriver requests
2. 运行: python jimeng_login_helper.py --region us --save
3. 在浏览器中完成登录
4. 程序自动获取 sessionid 并保存
"""

import undetected_chromedriver as uc
import time
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, List

# Tempmail API 配置 (从 tempmail.lol 获取 API Key)
TEMPMAIL_API_KEY = "tempmail.20251223.7eftc4cqujo8m0bifqr1sdq4fkmm3agqkp3i31gz1xq382yx"

# 代理列表（每个浏览器轮流使用）
# 格式: "ip:port" 或 "ip:port:username:password"
PROXY_LIST = [f"127.0.0.1:{port}" for port in range(7891, 7973)]  # 82个代理端口

# 文件写入锁
env_lock = threading.Lock()

# 浏览器创建锁
browser_lock = threading.Lock()

# 窗口位置管理（4个固定位置）
window_slots = [False, False, False, False]
window_slots_lock = threading.Lock()

# 代理索引锁
proxy_index = 0
proxy_lock = threading.Lock()

# Cookie 名称列表（用于查找 sessionid）
SESSION_COOKIE_NAMES = [
    "sessionid",
    "sessionid_ss", 
    "sid_tt",
    "sid_guard",
]


def get_next_proxy() -> str:
    """获取下一个代理（轮询）"""
    global proxy_index
    if not PROXY_LIST:
        return None
    with proxy_lock:
        proxy = PROXY_LIST[proxy_index % len(PROXY_LIST)]
        proxy_index += 1
        return proxy


def acquire_window_slot() -> int:
    """获取一个空闲的窗口位置（0-3），如果都被占用则等待"""
    while True:
        with window_slots_lock:
            for i in range(4):
                if not window_slots[i]:
                    window_slots[i] = True
                    return i
        time.sleep(1)


def release_window_slot(slot: int):
    """释放窗口位置"""
    with window_slots_lock:
        if 0 <= slot < 4:
            window_slots[slot] = False


class JimengLoginHelper:
    """即梦/Dreamina 登录助手"""
    
    # 国内站
    CN_URL = "https://jimeng.jianying.com"
    CN_LOGIN_URL = "https://jimeng.jianying.com/ai-tool/image/generate"
    
    # 国际站 (Dreamina)
    INTL_URL = "https://dreamina.capcut.com"
    INTL_LOGIN_URL = "https://dreamina.capcut.com/ai-tool/image/generate"
    
    # 地区前缀映射
    REGION_PREFIX_MAP = {
        "us": "us-",
        "hk": "hk-",
        "jp": "jp-",
        "sg": "sg-",
        "cn": "",
    }
    
    def __init__(self, region: str = "cn"):
        """
        初始化登录助手
        
        Args:
            region: 地区，可选值: cn(国内), us(美国), hk(香港), jp(日本), sg(新加坡)
        """
        self.region = region.lower()
        self.is_international = self.region in ["us", "hk", "jp", "sg"]
        
        if self.is_international:
            self.base_url = self.INTL_URL
            self.login_url = self.INTL_LOGIN_URL
        else:
            self.base_url = self.CN_URL
            self.login_url = self.CN_LOGIN_URL
    
    def get_session_id_prefix(self) -> str:
        """获取 sessionid 前缀"""
        return self.REGION_PREFIX_MAP.get(self.region, "")


class TempMailClient:
    """Tempmail.lol 客户端 - 用于自动获取临时邮箱和验证码"""
    
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
        import requests
        try:
            resp = requests.post(f"{self.base_url}/v2/inbox/create", headers=self.headers, proxies=self.proxies, timeout=15)
            data = resp.json()
            if "address" in data:
                return data
            return {"error": resp.text}
        except Exception as e:
            return {"error": str(e)}
    
    def get_emails(self, token: str) -> list:
        """获取邮件列表"""
        import requests
        try:
            resp = requests.get(f"{self.base_url}/v2/inbox", headers=self.headers, params={"token": token}, proxies=self.proxies, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("emails", [])
        except:
            pass
        return []
    
    def wait_for_code(self, token: str, timeout: int = 60) -> str:
        """等待验证码邮件并提取验证码"""
        import re
        print(f"等待验证码邮件（{timeout}秒超时）...")
        start = time.time()
        
        while time.time() - start < timeout:
            emails = self.get_emails(token)
            for email in emails:
                subject = email.get("subject", "")
                body = email.get("body", "") or email.get("html", "")
                
                # 打印完整邮件内容用于调试
                print(f"\n{'='*50}")
                print(f"收到邮件:")
                print(f"主题: {subject}")
                print(f"内容:\n{body}")
                print(f"{'='*50}\n")
                
                # 查找验证码（6 位字母数字混合）
                if "code" in subject.lower() or "verify" in subject.lower() or "验证" in subject:
                    # 提取 6 位字母数字混合验证码（如 CBV85U）
                    codes = re.findall(r'\b([A-Z0-9]{6})\b', body)
                    if codes:
                        print(f"✓ 找到验证码: {codes[0]}")
                        return codes[0]
            
            time.sleep(3)
        
        print("✗ 等待验证码超时")
        return None


def login_and_get_sessionid(
    region: str = "cn",
    timeout: int = 180,
    worker_id: int = None,
    proxy: str = None,
    headless: bool = False,
    auto_email: bool = False,
) -> Optional[Dict]:
    """
    打开浏览器登录即梦/Dreamina，获取 sessionid
    
    Args:
        region: 地区 (cn/us/hk/jp/sg)
        timeout: 等待登录超时时间（秒），默认 180 秒
        worker_id: 工作线程 ID（用于并发时区分浏览器实例）
        proxy: 代理地址，格式 "ip:port"
        headless: 是否无头模式（不显示浏览器窗口）
        auto_email: 是否自动使用临时邮箱注册（需要配置 TEMPMAIL_API_KEY）
    
    Returns:
        {"sessionid": "xxx", "region": "xxx", "full_token": "xxx", "all_cookies": {...}, "email": "xxx"}
    """
    helper = JimengLoginHelper(region)
    
    # 如果启用自动邮箱注册，先创建临时邮箱
    tempmail = None
    inbox_token = None
    email = None
    
    # 默认代理（用于 tempmail API，因为中国 IP 被限制）
    tempmail_proxy = proxy or "127.0.0.1:7897"
    
    if auto_email:
        if not TEMPMAIL_API_KEY:
            print("✗ 未配置 TEMPMAIL_API_KEY，无法使用自动邮箱注册")
            print("  请在 jimeng_login_helper.py 中设置 TEMPMAIL_API_KEY")
            auto_email = False
        else:
            tempmail = TempMailClient(TEMPMAIL_API_KEY, proxy=tempmail_proxy)
            inbox = tempmail.create_inbox()
            if "address" not in inbox:
                print(f"✗ 创建临时邮箱失败: {inbox.get('error', '未知错误')}")
                auto_email = False
            else:
                email = inbox.get("address")
                inbox_token = inbox.get("token")
                print(f"✓ 创建临时邮箱: {email}")
    
    options = uc.ChromeOptions()
    
    # 设置代理
    if proxy:
        proxy_parts = proxy.split(":")
        if len(proxy_parts) >= 2:
            options.add_argument(f"--proxy-server={proxy_parts[0]}:{proxy_parts[1]}")
            print(f"✓ 使用代理: {proxy_parts[0]}:{proxy_parts[1]}")
    
    # 无头模式（不推荐，因为需要手动登录）
    if headless:
        options.add_argument("--headless=new")
    
    # 窗口位置参数 (1920x1080 屏幕，4个窗口，一排4个)
    window_width = 480  # 1920 / 4 = 480
    window_height = 800  # 单行，高度可以更大
    x_offset = 0
    y_offset = 0
    window_slot = -1
    
    # 为并发模式设置独立的用户数据目录
    if worker_id is not None:
        import tempfile
        user_data_dir = os.path.join(
            tempfile.gettempdir(), f"jimeng_uc_profile_{worker_id}_{int(time.time())}"
        )
        options.add_argument(f"--user-data-dir={user_data_dir}")
        
        window_slot = acquire_window_slot()
        print(f"[线程 {worker_id}] 获得窗口位置 {window_slot + 1}")
        x_offset = window_slot * window_width
        y_offset = 0  # 固定在第一排
    
    # 使用锁串行化浏览器创建
    with browser_lock:
        driver = uc.Chrome(options=options)
    
    # 设置窗口大小和位置
    try:
        driver.set_window_size(window_width, window_height)
        driver.set_window_position(x_offset, y_offset)
    except:
        pass
    
    try:
        site_name = "Dreamina (国际站)" if helper.is_international else "即梦 (国内站)"
        print(f"\n{'='*60}")
        print(f"正在打开 {site_name} 登录页面...")
        print(f"URL: {helper.login_url}")
        print(f"{'='*60}")
        
        driver.get(helper.login_url)
        time.sleep(5)  # 等待页面加载完成
        
        # 尝试点击 Sign in 按钮（多次重试，使用 JavaScript 点击更可靠）
        sign_in_clicked = False
        for retry in range(5):
            try:
                # 使用 JavaScript 查找并点击 Sign in 按钮
                result = driver.execute_script("""
                    // 查找包含 "Sign in" 文字的元素
                    var elements = document.querySelectorAll('*');
                    for (var i = 0; i < elements.length; i++) {
                        var el = elements[i];
                        if (el.innerText && el.innerText.trim() === 'Sign in') {
                            // 确保是可点击的元素
                            if (el.tagName === 'BUTTON' || el.tagName === 'A' || 
                                el.tagName === 'SPAN' || el.tagName === 'DIV') {
                                el.click();
                                return 'clicked';
                            }
                        }
                    }
                    return 'not found';
                """)
                
                if result == 'clicked':
                    print("✓ 已点击登录按钮")
                    sign_in_clicked = True
                    time.sleep(2)
                    break
                else:
                    print(f"  登录按钮未找到 (尝试 {retry + 1}/5)")
                    
            except Exception as e:
                print(f"点击登录按钮失败 (尝试 {retry + 1}): {e}")
            
            time.sleep(2)
        
        if not sign_in_clicked:
            print("✗ 未能点击登录按钮，尝试直接打开登录页面...")
            # 备选方案：直接访问登录相关的 URL 或刷新页面
            driver.refresh()
            time.sleep(3)
        
        # 如果启用自动邮箱注册，尝试自动填写邮箱
        if auto_email and email:
            try:
                time.sleep(2)
                # 点击 "Continue with email" 按钮（多次重试）
                email_clicked = False
                for retry in range(3):
                    email_buttons = driver.find_elements("xpath", "//*[contains(text(), 'Continue with email') or contains(text(), '邮箱')]")
                    if not email_buttons:
                        email_buttons = driver.find_elements("css selector", "[class*='email']")
                    
                    for btn in email_buttons:
                        try:
                            if btn.is_displayed():
                                btn.click()
                                print("✓ 已点击邮箱登录按钮")
                                email_clicked = True
                                time.sleep(2)
                                break
                        except:
                            continue
                    
                    if email_clicked:
                        break
                    time.sleep(1)
                
                # 点击 "Sign up" 链接切换到注册页面
                time.sleep(1)
                signup_links = driver.find_elements("css selector", ".lv_new_sign_in_panel_wide-footer-switch-button")
                if not signup_links:
                    signup_links = driver.find_elements("xpath", "//*[contains(text(), 'Sign up')]")
                for link in signup_links:
                    try:
                        link.click()
                        print("✓ 已切换到注册页面")
                        time.sleep(2)
                        break
                    except:
                        continue
                
                # 查找邮箱输入框并填入（使用更精确的选择器）
                time.sleep(1)
                email_inputs = driver.find_elements("css selector", "input.lv_new_sign_in_panel_wide-input")
                if not email_inputs:
                    email_inputs = driver.find_elements("css selector", "input[placeholder*='email'], input[placeholder*='Enter email']")
                if not email_inputs:
                    email_inputs = driver.find_elements("css selector", "input[type='email'], input[type='text']")
                
                for inp in email_inputs:
                    try:
                        inp.clear()
                        inp.send_keys(email)
                        print(f"✓ 已填入邮箱: {email}")
                        break
                    except:
                        continue
                
                # 查找密码输入框并填入（生成随机密码）
                time.sleep(0.5)
                import random
                import string
                password = ''.join(random.choices(string.ascii_letters + string.digits, k=12)) + "Aa1!"
                
                password_inputs = driver.find_elements("css selector", "input[type='password']")
                for inp in password_inputs:
                    try:
                        inp.clear()
                        inp.send_keys(password)
                        print(f"✓ 已填入密码")
                        break
                    except:
                        continue
                
                # 点击继续按钮（多次重试，因为有时候需要点击多次）
                def click_continue_button():
                    btns = driver.find_elements("css selector", "button.lv_new_sign_in_panel_wide-sign-in-button")
                    if not btns:
                        btns = driver.find_elements("css selector", "button.lv_new_sign_in_panel_wide-primary-button")
                    if not btns:
                        btns = driver.find_elements("xpath", "//button[contains(text(), 'Continue') or contains(text(), '继续')]")
                    
                    for btn in btns:
                        try:
                            if btn.is_enabled() and btn.is_displayed():
                                btn.click()
                                return True
                        except:
                            continue
                    return False
                
                # 尝试多次点击继续按钮
                time.sleep(1)
                reached_code_page = False
                for attempt in range(3):
                    if click_continue_button():
                        print(f"✓ 已点击继续按钮 (第{attempt + 1}次)")
                        time.sleep(2)
                        # 检查是否到了验证码页面
                        if driver.find_elements("css selector", ".verification_code_input-wrapper, input[maxlength='1']"):
                            reached_code_page = True
                            break
                    else:
                        time.sleep(1)
                
                # 只有到了验证码页面才等待邮件
                if not reached_code_page:
                    # 再等一下，可能页面加载慢
                    time.sleep(3)
                    if driver.find_elements("css selector", ".verification_code_input-wrapper, input[maxlength='1']"):
                        reached_code_page = True
                
                # 等待并获取验证码
                if tempmail and inbox_token and reached_code_page:
                    time.sleep(3)  # 等待邮件发送
                    code = tempmail.wait_for_code(inbox_token, timeout=90)  # 增加到90秒
                    
                    if code:
                        # 查找验证码输入框
                        time.sleep(2)
                        
                        # 方案1: 查找隐藏的完整输入框 (maxlength=6)
                        hidden_code_input = driver.find_elements("css selector", ".verification_code_input-wrapper input[maxlength='6']")
                        if hidden_code_input:
                            try:
                                hidden_code_input[0].send_keys(code)
                                print(f"✓ 已自动填入验证码: {code}")
                            except Exception as e:
                                print(f"填入验证码失败: {e}")
                        else:
                            # 方案2: 查找多个单字符输入框
                            code_inputs = driver.find_elements("css selector", "input[type='text'], input[type='number'], input[data-testid*='input']")
                            single_char_inputs = [inp for inp in code_inputs if inp.get_attribute("maxlength") == "1"]
                            
                            if len(single_char_inputs) >= 6:
                                for i, char in enumerate(code[:len(single_char_inputs)]):
                                    try:
                                        single_char_inputs[i].send_keys(char)
                                        time.sleep(0.1)
                                    except:
                                        pass
                                print(f"✓ 已自动填入验证码: {code}")
                            else:
                                # 方案3: 尝试找到单个输入框
                                for inp in code_inputs:
                                    try:
                                        inp.clear()
                                        inp.send_keys(code)
                                        print(f"✓ 已自动填入验证码: {code}")
                                        break
                                    except:
                                        continue
                        
                        # 等待验证码验证，然后处理生日页面
                        time.sleep(3)
                        
                        # 填写生日信息
                        def fill_birthday():
                            """填写生日表单"""
                            import random
                            
                            try:
                                # 检查是否有生日页面
                                birthday_title = driver.find_elements("css selector", ".lv_new_sign_in_panel_wide-birthday-title")
                                if not birthday_title:
                                    return False
                                
                                print("检测到生日填写页面...")
                                
                                # 1. 填写年份
                                year = str(random.randint(1980, 2000))
                                year_input = driver.find_elements("css selector", "input.gate_birthday-picker-input[placeholder='Year']")
                                if year_input:
                                    year_input[0].clear()
                                    year_input[0].send_keys(year)
                                    print(f"✓ 已填入年份: {year}")
                                
                                time.sleep(0.5)
                                
                                # 2. 选择月份 - 点击 lv-select 下拉框
                                month_selectors = driver.find_elements("css selector", ".gate_birthday-picker-selector")
                                if len(month_selectors) >= 1:
                                    month_selectors[0].click()
                                    print("✓ 已点击月份下拉框")
                                    time.sleep(0.8)
                                    
                                    # 等待下拉选项出现并选择 - 尝试多种选择器
                                    month_options = driver.find_elements("css selector", "[role='option']")
                                    if not month_options:
                                        month_options = driver.find_elements("css selector", ".lv-select-option")
                                    if not month_options:
                                        month_options = driver.find_elements("css selector", "[class*='option']")
                                    if not month_options:
                                        # 尝试查找所有可见的列表项
                                        month_options = driver.find_elements("xpath", "//div[contains(@class, 'popup') or contains(@class, 'dropdown')]//div[string-length(text()) > 0]")
                                    
                                    # 过滤出可见的选项
                                    visible_options = [opt for opt in month_options if opt.is_displayed()]
                                    print(f"  找到 {len(visible_options)} 个可见月份选项")
                                    
                                    if visible_options:
                                        selected = random.choice(visible_options[:12])
                                        selected.click()
                                        print(f"✓ 已选择月份")
                                    else:
                                        print("✗ 未找到月份选项")
                                
                                time.sleep(0.5)
                                
                                # 3. 选择日期 - 点击第二个 lv-select 下拉框
                                day_selectors = driver.find_elements("css selector", ".gate_birthday-picker-selector")
                                if len(day_selectors) >= 2:
                                    day_selectors[1].click()
                                    print("✓ 已点击日期下拉框")
                                    time.sleep(0.8)
                                    
                                    # 等待下拉选项出现并选择 - 尝试多种选择器
                                    day_options = driver.find_elements("css selector", "[role='option']")
                                    if not day_options:
                                        day_options = driver.find_elements("css selector", ".lv-select-option")
                                    if not day_options:
                                        day_options = driver.find_elements("css selector", "[class*='option']")
                                    if not day_options:
                                        day_options = driver.find_elements("xpath", "//div[contains(@class, 'popup') or contains(@class, 'dropdown')]//div[string-length(text()) > 0]")
                                    
                                    # 过滤出可见的选项
                                    visible_options = [opt for opt in day_options if opt.is_displayed()]
                                    print(f"  找到 {len(visible_options)} 个可见日期选项")
                                    
                                    if visible_options:
                                        valid_options = visible_options[:min(28, len(visible_options))]
                                        selected = random.choice(valid_options)
                                        selected.click()
                                        print(f"✓ 已选择日期")
                                    else:
                                        print("✗ 未找到日期选项")
                                
                                time.sleep(0.5)
                                
                                # 4. 点击 Next 按钮
                                next_btn = driver.find_elements("css selector", ".lv_new_sign_in_panel_wide-birthday-next, button.lv_new_sign_in_panel_wide-primary-button")
                                if not next_btn:
                                    next_btn = driver.find_elements("xpath", "//button[contains(text(), 'Next')]")
                                
                                if next_btn:
                                    for _ in range(10):
                                        try:
                                            if next_btn[0].is_enabled():
                                                next_btn[0].click()
                                                print("✓ 已点击 Next 按钮")
                                                return True
                                        except:
                                            pass
                                        time.sleep(0.3)
                                
                                return True
                            except Exception as e:
                                print(f"填写生日失败: {e}")
                                import traceback
                                traceback.print_exc()
                                return False
                        
                        # 尝试填写生日（可能需要等待页面加载）
                        for _ in range(3):
                            if fill_birthday():
                                break
                            time.sleep(2)
                        
                    else:
                        print(f"请手动输入验证码（检查邮箱 {email}）")
                        
            except Exception as e:
                print(f"自动邮箱注册过程出错: {e}")
                print("请手动完成登录")
        
        print(f"\n{'='*60}")
        print(f"请在浏览器中完成登录操作")
        print(f"支持的登录方式:")
        if helper.is_international:
            print(f"  - Continue with Google")
            print(f"  - Continue with TikTok")
            print(f"  - Continue with Facebook")
            print(f"  - Continue with email")
            print(f"  - Continue with CapCut Mobile")
        else:
            print(f"  - 手机号登录")
            print(f"  - 抖音扫码登录")
            print(f"  - 邮箱登录")
        print(f"{'='*60}\n")
        
        print(f"等待登录完成（{timeout}秒超时）...")
        
        # 等待登录成功
        start_time = time.time()
        sessionid = None
        all_cookies = {}
        
        while time.time() - start_time < timeout:
            cookies = driver.get_cookies()
            
            # 收集所有 cookie
            for cookie in cookies:
                all_cookies[cookie["name"]] = cookie["value"]
            
            # 查找 sessionid
            for cookie in cookies:
                cookie_name = cookie["name"].lower()
                if cookie_name in SESSION_COOKIE_NAMES:
                    sessionid = cookie["value"]
                    # 检查是否是有效的 sessionid（不是空的或太短的）
                    if sessionid and len(sessionid) > 20:
                        print(f"\n✓ 获取到 sessionid！")
                        
                        # 添加地区前缀
                        prefix = helper.get_session_id_prefix()
                        full_token = f"{prefix}{sessionid}" if prefix else sessionid
                        
                        print(f"  Cookie 名称: {cookie['name']}")
                        print(f"  sessionid: {sessionid[:30]}...")
                        print(f"  地区: {region.upper()}")
                        print(f"  完整 token: {full_token[:35]}...")
                        
                        return {
                            "sessionid": sessionid,
                            "region": region,
                            "full_token": full_token,
                            "all_cookies": all_cookies,
                            "email": email,
                        }
            
            # 每 5 秒检查一次
            time.sleep(5)
            remaining = int(timeout - (time.time() - start_time))
            if remaining > 0 and remaining % 30 == 0:
                print(f"  还剩 {remaining} 秒...")
        
        print("✗ 登录超时")
        return None
        
    finally:
        driver.quit()
        if window_slot >= 0:
            release_window_slot(window_slot)
            print(f"[线程 {worker_id}] 释放窗口位置 {window_slot + 1}")


def get_next_account_id(env_file: str = ".env") -> int:
    """获取下一个可用的账户编号"""
    if not os.path.exists(env_file):
        return 1
    
    with open(env_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    existing_ids = set()
    for line in content.split("\n"):
        if line.startswith("JIMENG_TOKEN_"):
            try:
                parts = line.split("=")
                if len(parts) == 2 and parts[1].strip():
                    id_part = parts[0].replace("JIMENG_TOKEN_", "")
                    existing_ids.add(int(id_part))
            except:
                pass
    
    if not existing_ids:
        return 1
    return max(existing_ids) + 1


def save_to_env(credentials: dict, account_id: int = None, env_file: str = ".env") -> int:
    """将凭证保存到 .env 文件，返回账户编号（线程安全）"""
    if not credentials:
        print("没有凭证可保存")
        return None
    
    with env_lock:
        if account_id is None:
            account_id = get_next_account_id(env_file)
        
        content = ""
        if os.path.exists(env_file):
            with open(env_file, "r", encoding="utf-8") as f:
                content = f.read()
        
        token_key = f"JIMENG_TOKEN_{account_id}"
        region_key = f"JIMENG_REGION_{account_id}"
        
        lines = content.split("\n")
        new_lines = []
        token_found = False
        region_found = False
        
        for line in lines:
            if line.startswith(f"{token_key}="):
                new_lines.append(f"{token_key}={credentials['full_token']}")
                token_found = True
            elif line.startswith(f"{region_key}="):
                new_lines.append(f"{region_key}={credentials['region']}")
                region_found = True
            else:
                new_lines.append(line)
        
        if not token_found:
            new_lines.append(f"\n# 即梦账户{account_id}")
            new_lines.append(f"{token_key}={credentials['full_token']}")
        if not region_found:
            new_lines.append(f"{region_key}={credentials['region']}")
        
        with open(env_file, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines))
        
        print(f"✓ 已保存到 {env_file} (账户 {account_id})")
        return account_id


def remove_account_from_env(account_id: int, env_file: str = ".env"):
    """从 .env 文件中删除账户凭证"""
    if not os.path.exists(env_file):
        return
    
    with open(env_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    token_key = f"JIMENG_TOKEN_{account_id}"
    region_key = f"JIMENG_REGION_{account_id}"
    comment_key = f"# 即梦账户{account_id}"
    
    lines = content.split("\n")
    new_lines = []
    
    for line in lines:
        if line.startswith(token_key) or line.startswith(region_key) or line.strip() == comment_key:
            continue
        new_lines.append(line)
    
    while new_lines and new_lines[-1].strip() == "":
        new_lines.pop()
    
    with open(env_file, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))


def verify_token(token: str) -> bool:
    """验证 token 是否有效"""
    import requests
    
    # 解析地区
    region_prefix = ""
    actual_token = token
    
    for prefix in ["us-", "hk-", "jp-", "sg-"]:
        if token.lower().startswith(prefix):
            region_prefix = prefix
            actual_token = token[3:]
            break
    
    # 根据地区选择 API
    if region_prefix == "us-":
        base_url = "https://dreamina-api.us.capcut.com"
        aid = 513641
    elif region_prefix in ["hk-", "jp-", "sg-"]:
        base_url = "https://mweb-api-sg.capcut.com"
        aid = 513641
    else:
        base_url = "https://jimeng.jianying.com"
        aid = 513695
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Cookie": f"sessionid={actual_token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
        "Origin": base_url,
        "Referer": base_url,
    }
    
    params = {
        "aid": aid,
        "account_sdk_source": "web",
    }
    
    try:
        resp = requests.post(
            f"{base_url}/passport/account/info/v2",
            headers=headers,
            params=params,
            json={},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            # 检查返回数据中是否有 user_id
            if data.get("data", {}).get("user_id"):
                print(f"✓ Token 验证成功，用户ID: {data['data']['user_id']}")
                return True
            # 检查 ret 字段
            if data.get("ret") == "0":
                return True
    except Exception as e:
        print(f"验证 token 失败: {e}")
    
    return False


def get_credits(token: str) -> Optional[Dict]:
    """获取账户积分信息"""
    import requests
    
    # 解析地区
    region_prefix = ""
    actual_token = token
    
    for prefix in ["us-", "hk-", "jp-", "sg-"]:
        if token.lower().startswith(prefix):
            region_prefix = prefix
            actual_token = token[3:]
            break
    
    # 根据地区选择 API
    if region_prefix == "us-":
        base_url = "https://commerce.us.capcut.com"
    elif region_prefix in ["hk-", "jp-", "sg-"]:
        base_url = "https://commerce-api-sg.capcut.com"
    else:
        base_url = "https://jimeng.jianying.com"
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Cookie": f"sessionid={actual_token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    
    try:
        resp = requests.post(
            f"{base_url}/commerce/v1/benefits/user_credit",
            headers=headers,
            json={},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            credit_info = data.get("data", {}).get("credit", {})
            if credit_info:
                return {
                    "gift_credit": credit_info.get("gift_credit", 0),
                    "purchase_credit": credit_info.get("purchase_credit", 0),
                    "vip_credit": credit_info.get("vip_credit", 0),
                    "total": credit_info.get("gift_credit", 0) + credit_info.get("purchase_credit", 0) + credit_info.get("vip_credit", 0),
                }
    except Exception as e:
        print(f"获取积分失败: {e}")
    
    return None


def batch_login(
    count: int = 5,
    region: str = "us",
    save: bool = True,
    delay: int = 5,
    proxy: str = None,
    use_proxy_rotation: bool = True,
) -> List[Dict]:
    """
    批量获取多个账户的 sessionid（串行模式）
    
    Args:
        count: 要获取的账户数量
        region: 地区
        save: 是否自动保存到 .env
        delay: 每次登录之间的延迟（秒）
        proxy: 代理地址（如果指定则使用固定代理，否则使用 PROXY_LIST 轮询）
        use_proxy_rotation: 是否使用代理轮询（默认 True）
    
    Returns:
        成功获取的凭证列表
    """
    results = []
    success_count = 0
    fail_count = 0
    
    print(f"\n{'='*50}")
    print(f"开始批量获取 {count} 个即梦账户的 sessionid")
    print(f"地区: {region.upper()}")
    if proxy:
        print(f"固定代理: {proxy}")
    elif use_proxy_rotation and PROXY_LIST:
        print(f"代理轮询: {len(PROXY_LIST)} 个代理")
    print(f"{'='*50}\n")
    
    for i in range(count):
        print(f"\n[{i+1}/{count}] 正在获取第 {i+1} 个账户...")
        print("-" * 40)
        
        # 选择代理：优先使用指定代理，否则轮询 PROXY_LIST
        current_proxy = proxy
        if not current_proxy and use_proxy_rotation:
            current_proxy = get_next_proxy()
            if current_proxy:
                print(f"使用轮询代理: {current_proxy}")
        
        try:
            credentials = login_and_get_sessionid(
                region=region,
                timeout=120,
                auto_email=True,  # 批量模式默认启用自动邮箱
                proxy=current_proxy,
            )
            
            if credentials:
                # 验证 token（验证失败也保存，因为验证 API 可能有问题）
                is_valid = verify_token(credentials["full_token"])
                if save:
                    save_to_env(credentials)
                success_count += 1
                results.append(credentials)
                if is_valid:
                    print(f"✓ 第 {i+1} 个账户获取成功 (已验证)")
                else:
                    print(f"✓ 第 {i+1} 个账户获取成功 (验证API无响应，token已保存)")
            else:
                fail_count += 1
                print(f"✗ 第 {i+1} 个账户获取失败")
        
        except Exception as e:
            fail_count += 1
            print(f"✗ 第 {i+1} 个账户出错: {e}")
        
        if i < count - 1:
            print(f"\n等待 {delay} 秒后继续...")
            time.sleep(delay)
    
    print(f"\n{'='*50}")
    print(f"批量获取完成！")
    print(f"成功: {success_count} 个")
    print(f"失败: {fail_count} 个")
    print(f"{'='*50}")
    
    return results


def _worker_login(
    worker_id: int,
    region: str,
    save: bool = True,
    proxy: str = None,
    use_proxy_rotation: bool = True,
) -> Optional[Dict]:
    """单个工作线程的登录任务"""
    # 选择代理：优先使用指定代理，否则轮询 PROXY_LIST
    current_proxy = proxy
    if not current_proxy and use_proxy_rotation:
        current_proxy = get_next_proxy()
    
    if current_proxy:
        print(f"[线程 {worker_id}] 开始登录... (代理: {current_proxy})")
    else:
        print(f"[线程 {worker_id}] 开始登录...")
    
    try:
        credentials = login_and_get_sessionid(
            region=region,
            timeout=120,
            worker_id=worker_id,
            proxy=current_proxy,
            auto_email=True,  # 并发模式默认启用自动邮箱
        )
        
        if credentials:
            # 验证 token（验证失败也保存，因为验证 API 可能有问题）
            is_valid = verify_token(credentials["full_token"])
            if save:
                account_id = save_to_env(credentials)
                credentials["account_id"] = account_id
            if is_valid:
                print(f"[线程 {worker_id}] ✓ 登录成功 (已验证)")
            else:
                print(f"[线程 {worker_id}] ✓ 登录成功 (验证API无响应，token已保存)")
            return credentials
        else:
            print(f"[线程 {worker_id}] ✗ 登录失败")
            return None
    except Exception as e:
        print(f"[线程 {worker_id}] ✗ 出错: {e}")
        return None


def batch_login_parallel(
    count: int = 5,
    workers: int = 2,
    region: str = "us",
    save: bool = True,
    proxy_list: List[str] = None,
    use_proxy_rotation: bool = True,
) -> List[Dict]:
    """
    并发批量获取多个账户的 sessionid
    
    Args:
        count: 要获取的账户数量
        workers: 并发浏览器数量
        region: 地区
        save: 是否自动保存到 .env
        proxy_list: 代理列表（如果指定则使用此列表，否则使用全局 PROXY_LIST）
        use_proxy_rotation: 是否使用代理轮询（默认 True）
    
    Returns:
        成功获取的凭证列表
    """
    results = []
    
    # 使用指定的代理列表或全局 PROXY_LIST
    effective_proxy_list = proxy_list if proxy_list else (PROXY_LIST if use_proxy_rotation else None)
    
    print(f"\n{'='*50}")
    print(f"开始并发获取 {count} 个即梦账户 (并发数: {workers})")
    print(f"地区: {region.upper()}")
    if effective_proxy_list:
        print(f"代理池: {len(effective_proxy_list)} 个")
        for i, p in enumerate(effective_proxy_list):
            print(f"  [{i+1}] {p}")
    print(f"{'='*50}\n")
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _worker_login,
                i + 1,
                region,
                save,
                None,  # proxy 参数设为 None，让 _worker_login 自动轮询
                use_proxy_rotation,
            ): i
            for i in range(count)
        }
        
        for future in as_completed(futures):
            worker_id = futures[future] + 1
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                print(f"[线程 {worker_id}] 异常: {e}")
    
    success_count = len(results)
    fail_count = count - success_count
    
    print(f"\n{'='*50}")
    print(f"并发获取完成！")
    print(f"成功: {success_count} 个")
    print(f"失败: {fail_count} 个")
    print(f"{'='*50}")
    
    return results


def list_accounts(env_file: str = ".env") -> List[Dict]:
    """列出所有已保存的账户"""
    if not os.path.exists(env_file):
        print("没有找到 .env 文件")
        return []
    
    with open(env_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    accounts = []
    account_ids = set()
    
    for line in content.split("\n"):
        if line.startswith("JIMENG_TOKEN_"):
            try:
                parts = line.split("=")
                if len(parts) == 2 and parts[1].strip():
                    id_part = parts[0].replace("JIMENG_TOKEN_", "")
                    account_ids.add(int(id_part))
            except:
                pass
    
    for account_id in sorted(account_ids):
        token = None
        region = "cn"
        
        for line in content.split("\n"):
            if line.startswith(f"JIMENG_TOKEN_{account_id}="):
                token = line.split("=", 1)[1].strip()
            elif line.startswith(f"JIMENG_REGION_{account_id}="):
                region = line.split("=", 1)[1].strip()
        
        if token:
            # 验证 token
            is_valid = verify_token(token)
            accounts.append({
                "account_id": account_id,
                "token": token,
                "region": region,
                "valid": is_valid,
            })
    
    return accounts


def print_accounts(env_file: str = ".env"):
    """打印所有账户信息"""
    accounts = list_accounts(env_file)
    
    if not accounts:
        print("没有找到已保存的账户")
        return
    
    print(f"\n{'='*60}")
    print(f"已保存的即梦/Dreamina 账户 ({len(accounts)} 个)")
    print(f"{'='*60}")
    
    for acc in accounts:
        status = "✓ 有效" if acc["valid"] else "✗ 无效"
        print(f"\n账户 {acc['account_id']}:")
        print(f"  地区: {acc['region'].upper()}")
        print(f"  Token: {acc['token'][:30]}...")
        print(f"  状态: {status}")
        
        # 尝试获取积分
        if acc["valid"]:
            credits = get_credits(acc["token"])
            if credits:
                print(f"  积分: {credits['total']} (赠送: {credits['gift_credit']}, 购买: {credits['purchase_credit']}, VIP: {credits['vip_credit']})")
    
    print(f"\n{'='*60}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="即梦 (Jimeng) / Dreamina 登录助手 - 自动获取 sessionid",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 登录 Dreamina 美国站并保存
  python jimeng_login_helper.py --region us --save
  
  # 登录即梦国内站
  python jimeng_login_helper.py --region cn --save
  
  # 列出所有已保存的账户
  python jimeng_login_helper.py --list
  
  # 验证 token
  python jimeng_login_helper.py --verify "us-your_session_id"
  
  # 使用自动邮箱注册
  python jimeng_login_helper.py --region us --save --auto-email
  
  # 批量获取 3 个账户（自动使用临时邮箱）
  python jimeng_login_helper.py --batch 3 --region us --save
"""
    )
    parser.add_argument(
        "--region", "-r",
        type=str,
        default="us",
        choices=["cn", "us", "hk", "jp", "sg"],
        help="地区: cn(国内), us(美国), hk(香港), jp(日本), sg(新加坡)，默认 us"
    )
    parser.add_argument(
        "--batch", "-b",
        type=int,
        default=None,
        help="批量获取数量"
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=1,
        help="并发浏览器数量（默认1，即串行）"
    )
    parser.add_argument(
        "--delay", "-d",
        type=int,
        default=5,
        help="串行模式下每次登录的间隔秒数"
    )
    parser.add_argument(
        "--save", "-s",
        action="store_true",
        help="自动保存到 .env"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出所有已保存的账户"
    )
    parser.add_argument(
        "--verify", "-v",
        type=str,
        default=None,
        help="验证指定的 token"
    )
    parser.add_argument(
        "--auto-email", "-a",
        action="store_true",
        help="自动使用临时邮箱注册（需要配置 TEMPMAIL_API_KEY）"
    )
    parser.add_argument(
        "--proxy", "-p",
        type=str,
        nargs="?",
        const="auto",
        default=None,
        help="代理设置: 不带参数(-p)使用 PROXY_LIST 轮询，带参数(-p ip:port)使用指定代理"
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=180,
        help="登录超时时间（秒），默认 180"
    )
    
    args = parser.parse_args()
    
    # 处理代理参数
    use_proxy_rotation = False
    fixed_proxy = None
    
    if args.proxy == "auto":
        # -p 不带参数，使用 PROXY_LIST 轮询
        use_proxy_rotation = True
        print(f"✓ 启用代理轮询，代理池: {len(PROXY_LIST)} 个")
    elif args.proxy:
        # -p ip:port，使用指定代理
        fixed_proxy = args.proxy
        print(f"✓ 使用固定代理: {fixed_proxy}")

    # 列出账户
    if args.list:
        print_accounts()
    # 验证 token
    elif args.verify:
        is_valid = verify_token(args.verify)
        if is_valid:
            print(f"✓ Token 有效")
            credits = get_credits(args.verify)
            if credits:
                print(f"  积分: {credits['total']}")
        else:
            print(f"✗ Token 无效")
    # 批量模式
    elif args.batch:
        if args.workers > 1:
            results = batch_login_parallel(
                count=args.batch,
                workers=args.workers,
                region=args.region,
                save=args.save,
                proxy_list=None,  # 使用全局 PROXY_LIST
                use_proxy_rotation=use_proxy_rotation,
            )
        else:
            results = batch_login(
                count=args.batch,
                region=args.region,
                save=args.save,
                delay=args.delay,
                proxy=fixed_proxy,
                use_proxy_rotation=use_proxy_rotation,
            )
        if results:
            print(f"\n获取到 {len(results)} 个账户的凭证")
    # 单个模式
    else:
        # 单个模式使用固定代理或默认代理
        single_proxy = fixed_proxy or "127.0.0.1:7897"
        credentials = login_and_get_sessionid(
            region=args.region,
            timeout=args.timeout,
            auto_email=args.auto_email,
            proxy=single_proxy,
        )

        if credentials:
            print(f"\n获取到的凭证:")
            print(json.dumps({
                "sessionid": credentials["sessionid"][:30] + "...",
                "region": credentials["region"],
                "full_token": credentials["full_token"][:35] + "...",
            }, indent=2, ensure_ascii=False))

            if args.save:
                save_to_env(credentials)
                
                # 验证并显示积分
                credits = get_credits(credentials["full_token"])
                if credits:
                    print(f"\n账户积分: {credits['total']}")
            else:
                print("\n添加 --save 参数可自动保存到 .env")
