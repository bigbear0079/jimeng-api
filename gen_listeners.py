import re

with open('../jiedian', 'r', encoding='utf-8') as f:
    content = f.read()

# 只匹配 proxies 部分的节点
proxies_match = re.search(r'proxies:\s*\n(.*?)(?=proxy-groups:|$)', content, re.DOTALL)
if proxies_match:
    proxies_content = proxies_match.group(1)
else:
    proxies_content = content

# 匹配节点名称 - 只匹配 { name: xxx, type: 开头的
pattern = r"\{\s*name:\s*'?([^',}]+)'?\s*,\s*type:"
names = re.findall(pattern, proxies_content)

# 过滤
filtered = []
for n in names:
    n = n.strip().strip("'\"")
    # 过滤掉信息类节点和无效节点
    if n and not any(x in n for x in ['剩余流量', '距离下次', '套餐到期', '自动', '故障', '赔钱', 'mixed', '.com', '.top']):
        filtered.append(n)

# 去重保持顺序
seen = set()
unique = []
for n in filtered:
    if n not in seen:
        seen.add(n)
        unique.append(n)

print(f'Found {len(unique)} unique nodes')

# 生成 listeners
lines = ['listeners:']
port = 7891
for i, name in enumerate(unique[:82]):
    lines.append(f'  - name: mixed{i}')
    lines.append(f'    type: mixed')
    lines.append(f'    port: {port}')
    lines.append(f'    proxy: {name}')
    port += 1

result = '\n'.join(lines)
with open('listeners.yaml', 'w', encoding='utf-8') as f:
    f.write(result)

print(f'Generated listeners.yaml with {min(len(unique), 82)} entries')
