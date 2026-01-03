#!/usr/bin/env python3
"""
生成 Clash Verge listeners 配置
将每个代理节点映射到本地端口 (7891, 7892, ...)
"""

import yaml
import re

def extract_proxy_names(proxy_file):
    """从代理配置文件中提取所有代理名称"""
    with open(proxy_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 解析 YAML
    config = yaml.safe_load(content)
    
    # 提取代理名称
    proxy_names = []
    if 'proxies' in config:
        for proxy in config['proxies']:
            if 'name' in proxy:
                name = proxy['name']
                # 跳过信息类节点（流量、重置、到期）
                if any(skip in name for skip in ['剩余流量', '距离下次重置', '套餐到期']):
                    continue
                proxy_names.append(name)
    
    return proxy_names

def generate_listeners_config(proxy_names, start_port=7891):
    """生成 listeners 配置"""
    listeners = []
    
    for i, name in enumerate(proxy_names):
        port = start_port + i
        listener = {
            'name': f'mixed{i}',
            'type': 'mixed',
            'port': port,
            'proxy': name
        }
        listeners.append(listener)
    
    return {'listeners': listeners}

def main():
    proxy_file = '../proxy'  # 代理配置文件路径
    output_file = 'listeners.yaml'
    
    print("正在读取代理配置...")
    proxy_names = extract_proxy_names(proxy_file)
    print(f"找到 {len(proxy_names)} 个代理节点")
    
    print("\n正在生成 listeners 配置...")
    config = generate_listeners_config(proxy_names)
    
    # 写入 YAML 文件
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    print(f"✓ 配置已保存到: {output_file}")
    print(f"✓ 端口范围: 7891 - {7891 + len(proxy_names) - 1}")
    
    # 打印前几个示例
    print("\n前5个 listeners 示例:")
    for listener in config['listeners'][:5]:
        print(f"  - name: {listener['name']}")
        print(f"    type: {listener['type']}")
        print(f"    port: {listener['port']}")
        print(f"    proxy: {listener['proxy']}")
        print()

if __name__ == '__main__':
    main()
