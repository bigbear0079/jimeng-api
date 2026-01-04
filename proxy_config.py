"""
代理配置模块
自动判断运行环境，决定使用本机代理还是局域网代理
"""
import socket

# 代理服务器所在电脑的局域网 IP
PROXY_SERVER_LAN_IP = "192.168.1.173"

def get_local_ip():
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def is_local_machine():
    """判断是否在代理服务器本机运行"""
    local_ip = get_local_ip()
    return local_ip == PROXY_SERVER_LAN_IP or local_ip == "127.0.0.1"

def get_proxy_host():
    """获取代理主机地址"""
    return "127.0.0.1" if is_local_machine() else PROXY_SERVER_LAN_IP

# 代理主机地址（自动判断）
PROXY_HOST = get_proxy_host()

# 常用代理端口
DEFAULT_PROXY_PORT = 7897
PROXY_PORT_START = 7891
PROXY_PORT_END = 7972

# 便捷函数
def get_proxy_url(port=DEFAULT_PROXY_PORT):
    """获取代理 URL"""
    return f"http://{PROXY_HOST}:{port}"

def get_proxy_dict(port=DEFAULT_PROXY_PORT):
    """获取 requests 库使用的代理字典"""
    proxy_url = get_proxy_url(port)
    return {"http": proxy_url, "https": proxy_url}

def get_proxy_list():
    """获取代理列表（用于多代理轮询）"""
    return [f"{PROXY_HOST}:{port}" for port in range(PROXY_PORT_START, PROXY_PORT_END + 1)]

# 打印当前配置（调试用）
if __name__ == "__main__":
    print(f"本机 IP: {get_local_ip()}")
    print(f"是否本机运行: {is_local_machine()}")
    print(f"代理主机: {PROXY_HOST}")
    print(f"默认代理: {get_proxy_url()}")
