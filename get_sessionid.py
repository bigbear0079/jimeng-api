"""
使用已注册的账户登录 Dreamina 并获取 sessionid
"""

import undetected_chromedriver as uc
import time
import json
import os

# 已注册的账户信息
EMAIL = "jones700ae9@is.awesomesaucemail.org"
PASSWORD = "Dreamina2026!Aa"
REGION = "us"

# Cookie 名称列表
SESSION_COOKIE_NAMES = ["sessionid", "sessionid_ss", "sid_tt", "sid_guard"]


def login_and_get_sessionid():
    """登录并获取 sessionid"""
    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options)
    
    try:
        print("正在打开 Dreamina 登录页面...")
        driver.get("https://dreamina.capcut.com/ai-tool/image/generate")
        time.sleep(3)
        
        # 点击 Sign in 按钮
        try:
            sign_in_buttons = driver.find_elements("xpath", "//*[contains(text(), 'Sign in')]")
            for btn in sign_in_buttons:
                try:
                    btn.click()
                    print("✓ 已点击 Sign in 按钮")
                    time.sleep(2)
                    break
                except:
                    continue
        except Exception as e:
            print(f"点击 Sign in 失败: {e}")
        
        # 点击 "Continue with email"
        time.sleep(2)
        email_buttons = driver.find_elements("xpath", "//*[contains(text(), 'Continue with email')]")
        for btn in email_buttons:
            try:
                btn.click()
                print("✓ 已点击 Continue with email")
                time.sleep(2)
                break
            except:
                continue
        
        # 填入邮箱
        time.sleep(1)
        email_inputs = driver.find_elements("css selector", "input.lv_new_sign_in_panel_wide-input")
        if not email_inputs:
            email_inputs = driver.find_elements("css selector", "input[type='email'], input[type='text']")
        
        for inp in email_inputs:
            try:
                inp.clear()
                inp.send_keys(EMAIL)
                print(f"✓ 已填入邮箱: {EMAIL}")
                break
            except:
                continue
        
        # 填入密码
        time.sleep(0.5)
        password_inputs = driver.find_elements("css selector", "input[type='password']")
        for inp in password_inputs:
            try:
                inp.clear()
                inp.send_keys(PASSWORD)
                print("✓ 已填入密码")
                break
            except:
                continue
        
        # 点击登录按钮
        time.sleep(1)
        login_buttons = driver.find_elements("css selector", "button.lv_new_sign_in_panel_wide-sign-in-button")
        if not login_buttons:
            login_buttons = driver.find_elements("xpath", "//button[contains(text(), 'Log in') or contains(text(), 'Sign in')]")
        
        for btn in login_buttons:
            try:
                if btn.is_enabled():
                    btn.click()
                    print("✓ 已点击登录按钮")
                    break
            except:
                continue
        
        # 等待登录完成并获取 sessionid
        print("等待登录完成...")
        time.sleep(10)
        
        # 获取 cookies
        cookies = driver.get_cookies()
        sessionid = None
        
        for cookie in cookies:
            cookie_name = cookie["name"].lower()
            if cookie_name in SESSION_COOKIE_NAMES:
                sessionid = cookie["value"]
                if sessionid and len(sessionid) > 20:
                    print(f"\n✓ 获取到 sessionid!")
                    print(f"  Cookie 名称: {cookie['name']}")
                    print(f"  sessionid: {sessionid[:30]}...")
                    
                    # 添加地区前缀
                    full_token = f"us-{sessionid}"
                    print(f"  完整 token: {full_token[:35]}...")
                    
                    # 保存到 .env 文件
                    save_to_env(full_token, REGION)
                    
                    return {
                        "sessionid": sessionid,
                        "region": REGION,
                        "full_token": full_token,
                        "email": EMAIL,
                    }
        
        print("✗ 未能获取 sessionid，请检查登录状态")
        print("当前 cookies:")
        for cookie in cookies:
            print(f"  {cookie['name']}: {cookie['value'][:30]}...")
        
        input("按 Enter 键关闭浏览器...")
        return None
        
    finally:
        driver.quit()


def save_to_env(full_token: str, region: str, env_file: str = ".env"):
    """保存到 .env 文件"""
    # 获取下一个账户编号
    account_id = 1
    if os.path.exists(env_file):
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
        
        if existing_ids:
            account_id = max(existing_ids) + 1
    
    # 写入 .env 文件
    with open(env_file, "a", encoding="utf-8") as f:
        f.write(f"\n# 即梦账户{account_id}\n")
        f.write(f"JIMENG_TOKEN_{account_id}={full_token}\n")
        f.write(f"JIMENG_REGION_{account_id}={region}\n")
    
    print(f"✓ 已保存到 {env_file} (账户 {account_id})")


if __name__ == "__main__":
    result = login_and_get_sessionid()
    if result:
        print("\n登录成功！")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("\n登录失败")
