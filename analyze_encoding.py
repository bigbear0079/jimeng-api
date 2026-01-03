"""分析 Dreamina 注册 API 的编码方式"""

def encode_mix_mode(text: str) -> str:
    """使用 mix_mode=1 编码（XOR 5 然后转 hex）"""
    result = []
    for char in text:
        encoded_byte = ord(char) ^ 5
        result.append(f'{encoded_byte:02x}')
    return ''.join(result)

def decode_mix_mode(hex_str: str) -> str:
    """解码 mix_mode=1 编码"""
    result = []
    for i in range(0, len(hex_str), 2):
        byte = int(hex_str[i:i+2], 16)
        decoded_char = chr(byte ^ 5)
        result.append(decoded_char)
    return ''.join(result)

# 测试
if __name__ == "__main__":
    # 原始数据
    email = 'jillayne714ad2@fk.chessgamingworld.com'
    code = '4F338G'
    password = 'playgameHaha8'
    
    # 编码
    encoded_email = encode_mix_mode(email)
    encoded_code = encode_mix_mode(code)
    encoded_password = encode_mix_mode(password)
    
    print("=== 编码测试 ===")
    print(f"Email: {email}")
    print(f"Encoded: {encoded_email}")
    print()
    print(f"Code: {code}")
    print(f"Encoded: {encoded_code}")
    print()
    print(f"Password: {password}")
    print(f"Encoded: {encoded_password}")
    
    # 验证解码
    print()
    print("=== 解码验证 ===")
    print(f"Decoded email: {decode_mix_mode(encoded_email)}")
    print(f"Decoded code: {decode_mix_mode(encoded_code)}")
    print(f"Decoded password: {decode_mix_mode(encoded_password)}")
