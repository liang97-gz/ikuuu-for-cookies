import requests
import re
import json
import os
import sys
import base64
from bs4 import BeautifulSoup

QL_SCRIPTS_DIR = '/ql/scripts'
sys.path.append(QL_SCRIPTS_DIR)
POSSIBLE_PATHS = [
    '/ql',
    '/ql/data/scripts',
    '/ql/scripts/notify',
    os.path.dirname(__file__)
]

for path in POSSIBLE_PATHS:
    if os.path.exists(os.path.join(path, 'notify.py')):
        sys.path.append(path)
        break

try:
    from notify import send
except ImportError:
    send = lambda title, content: None


# 从环境变量获取域名，默认为 ikuuu.win
IKUUU_HOST = os.getenv('IKUUU_HOST', 'ikuuu.win').strip()
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
# 获取PushPlus Token
PUSH_TOKEN = os.getenv('PUSHPLUS_TOKEN')

def parse_cookie_string(cookie_str):
    cookies_dict = {}
    if not cookie_str or not cookie_str.strip():
        return cookies_dict
    try:
        cookie_str = requests.utils.unquote(cookie_str)
        cookie_str = re.sub(r';\s*', '; ', cookie_str)
        cookie_str = re.sub(r'&', '; ', cookie_str)
        cookie_items = []
        if ';' in cookie_str:
            temp_items = cookie_str.split(';')
            for item in temp_items:
                item = item.strip()
                if item:
                    cookie_items.append(item)
        else:
            if '\n' in cookie_str:
                temp_items = cookie_str.split('\n')
                for item in temp_items:
                    item = item.strip()
                    if item:
                        cookie_items.append(item)
            else:
                cookie_items = [cookie_str]
        for item in cookie_items:
            item = item.strip()
            if not item:
                continue
            if '=' in item:
                parts = item.split('=', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    key = key.replace(' ', '').replace('%20', '').strip()
                    value = value.strip('"\'')
                    if key and value:
                        cookies_dict[key] = value
        cleaned_dict = {}
        for key, value in cookies_dict.items():
            cleaned_key = key
            if cleaned_key.startswith('%20'):
                cleaned_key = cleaned_key[3:]
            if cleaned_key.startswith(' '):
                cleaned_key = cleaned_key.lstrip()
            cleaned_dict[cleaned_key] = value
        return cleaned_dict
    except Exception as e:
        print(f"❌ 解析cookie失败: {e}")
        return cookies_dict

def validate_cookie(cookie_dict):
    if not cookie_dict:
        return False, "Cookie为空"
    cleaned_dict = {}
    for key, value in cookie_dict.items():
        cleaned_key = key.strip().replace(' ', '').replace('%20', '')
        cleaned_dict[cleaned_key] = value
    required_cookies = ['uid', 'email', 'key']
    missing_cookies = []
    for req_cookie in required_cookies:
        found = False
        for cookie_key in cleaned_dict.keys():
            if cookie_key.lower() == req_cookie.lower():
                found = True
                break
        if not found:
            missing_cookies.append(req_cookie)
    if missing_cookies:
        return False, f"缺少必需的cookie: {', '.join(missing_cookies)}"
    for req_cookie in required_cookies:
        actual_key = None
        for cookie_key in cleaned_dict.keys():
            if cookie_key.lower() == req_cookie.lower():
                actual_key = cookie_key
                break
        if actual_key:
            value = cleaned_dict[actual_key]
            if not value or len(value) < 2:
                return False, f"Cookie值 '{req_cookie}' 格式不正确"
    return True, "Cookie格式正确"

def get_remaining_flow(session):
    user_url = f'https://{IKUUU_HOST}/user'
    try:
        user_page = session.get(user_url, timeout=20)
        if user_page.status_code != 200:
            return "获取失败", f"状态码{user_page.status_code}"
        base64_match = re.search(r'var originBody = "([^"]+)"', user_page.text)
        if base64_match:
            try:
                base64_content = base64_match.group(1)
                decoded_content = base64.b64decode(base64_content).decode('utf-8')
                soup = BeautifulSoup(decoded_content, 'html.parser')
                flow_patterns = [
                    r'剩余流量[：:]?\s*([\d\.]+)\s*([GMK]B?)',
                    r'Traffic Left[：:]?\s*([\d\.]+)\s*([GMK]B?)',
                    r'Available[：:]?\s*([\d\.]+)\s*([GMK]B?)'
                ]
                for text_element in soup.find_all(string=True):
                    text = str(text_element).strip()
                    for pattern in flow_patterns:
                        match = re.search(pattern, text, re.IGNORECASE)
                        if match:
                            flow_value = match.group(1)
                            flow_unit = match.group(2)
                            return flow_value, flow_unit
            except:
                pass
        soup = BeautifulSoup(user_page.text, 'html.parser')
        flow_elements = soup.find_all(['div', 'span', 'p', 'td'])
        for element in flow_elements:
            text = element.get_text(strip=True)
            if any(keyword in text for keyword in ['剩余流量', 'Traffic', 'Available', '流量']):
                flow_match = re.search(r'([\d\.\,]+)\s*([GMK]B?)', text, re.IGNORECASE)
                if flow_match:
                    flow_value = flow_match.group(1).replace(',', '')
                    flow_unit = flow_match.group(2).upper()
                    return flow_value, flow_unit
        return "未找到", "流量信息"
    except Exception as e:
        return "获取异常", str(e)

def ikuuu_signin(cookie_str, account_name):
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": f"https://{IKUUU_HOST}",
        "Referer": f"https://{IKUUU_HOST}/user",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    })
    cookie_dict = parse_cookie_string(cookie_str)
    if not cookie_dict:
        flow_value, flow_unit = "签到失败", "无法获取"
        return False, f"Cookie格式错误或为空", flow_value, flow_unit
    is_valid, msg = validate_cookie(cookie_dict)
    if not is_valid:
        flow_value, flow_unit = "签到失败", "无法获取"
        return False, msg, flow_value, flow_unit
    for key, value in cookie_dict.items():
        session.cookies.set(key, value, domain=IKUUU_HOST)
    flow_value, flow_unit = get_remaining_flow(session)
    try:
        checkin_url = f'https://{IKUUU_HOST}/user/checkin'
        checkin_res = session.post(checkin_url, timeout=20)
        if checkin_res.status_code != 200:
            return False, f"签到失败（状态码{checkin_res.status_code}）", flow_value, flow_unit
        try:
            checkin_data = checkin_res.json()
            if checkin_data.get('ret') == 1:
                msg = checkin_data.get('msg', '签到成功')
                if 'traffic' in msg:
                    traffic_match = re.search(r'(\d+)([GMK]B)', msg)
                    if traffic_match:
                        traffic_amount = traffic_match.group(1)
                        traffic_unit = traffic_match.group(2)
                        msg = f"签到成功，获得{traffic_amount}{traffic_unit}流量"
                return True, msg, flow_value, flow_unit
            else:
                error_msg = checkin_data.get('msg', '未知错误')
                if '已签到' in error_msg or 'already' in error_msg.lower():
                    return True, "今日已签到过", flow_value, flow_unit
                else:
                    return False, f"签到失败：{error_msg}", flow_value, flow_unit
        except json.JSONDecodeError:
            if '已签到' in checkin_res.text or 'already' in checkin_res.text.lower():
                return True, "今日已签到过", flow_value, flow_unit
            elif '签到成功' in checkin_res.text or 'success' in checkin_res.text.lower():
                return True, "签到成功", flow_value, flow_unit
            else:
                return False, "签到响应格式异常", flow_value, flow_unit
    except requests.exceptions.Timeout:
        return False, "签到请求超时", flow_value, flow_unit
    except Exception as e:
        return False, f"签到异常：{str(e)}", flow_value, flow_unit

def pushplus_push(title, content):
    """Pushplus推送"""
    if not PUSH_TOKEN:
        print("⚠️ 未配置PUSHPLUS_TOKEN，跳过Pushplus推送")
        return False
    try:
        print("🚀 推送消息到Pushplus...")
        data = {
            "token": PUSH_TOKEN,
            "title": title,
            "content": content,
            "template": "markdown"
        }
        response = requests.post(
            "https://www.pushplus.plus/send",
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        result = response.json()
        if result.get('code') == 200:
            print("✅ Pushplus推送成功")
            return True
        else:
            print(f"❌ Pushplus推送失败: {result.get('msg')}")
            return False
    except Exception as e:
        print(f"❌ Pushplus推送异常: {str(e)}")
        return False

def send_notification(results):
    success_count = sum(1 for res in results if res['success'])
    failure_count = len(results) - success_count

    # 生成标题，直接体现结果
    if len(results) == 1:
        # 单账户直接把签到结果放标题
        res = results[0]
        if "已签到" in res['message']:
            title = f"✅ iKuuu - {res['message']}"
        else:
            status_emoji = "✅" if res['success'] else "❌"
            title = f"{status_emoji} iKuuu签到 - {res['message']}"
    else:
        # 多账户统计结果放标题
        title = f"iKuuu签到完成 成功:{success_count} 失败:{failure_count}"

    message = [
        f"🔔 **签到完成** | 成功：{success_count} 失败：{failure_count}",
        f"🌐 **当前域名**：{IKUUU_HOST}",
        "================================"
    ]
    for index, res in enumerate(results, 1):
        status = "✅ 成功" if res['success'] else "❌ 失败"
        message.append(f"{index}. **{res['account_name']}**")
        message.append(f"  - 状态：{status}")
        message.append(f"  - 详情：{res['message']}")
        message.append(f"  - 剩余流量：{res['flow_value']} {res['flow_unit']}")
        message.append("---")
    message.append(f"\n🕒 **执行时间**：" + __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    # 尝试青龙通知
    try:
        send(title, "\n".join(message))
    except:
        pass
    
    # Pushplus推送
    if PUSH_TOKEN:
        pushplus_push(title, "\n".join(message))

def parse_multiple_cookies(cookies_str):
    accounts = []
    if not cookies_str or not cookies_str.strip():
        return accounts
    lines = cookies_str.strip().splitlines()
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '||' in line:
            parts = line.split('||', 1)
            if len(parts) == 2:
                account_name = parts[0].strip()
                cookie_str = parts[1].strip()
                if account_name and cookie_str:
                    accounts.append((account_name, cookie_str))
        else:
            account_name = f"账户{line_num}"
            accounts.append((account_name, line))
    return accounts

if __name__ == "__main__":
    # 打印当前使用的域名
    print(f"🌐 使用域名: {IKUUU_HOST}")
    
    cookies_str = os.getenv('IKUUU_COOKIES')
    if not cookies_str:
        print("❌ 未找到环境变量 IKUUU_COOKIES")
        exit(1)
    accounts = parse_multiple_cookies(cookies_str)
    if not accounts:
        print("❌ 未找到有效的cookie配置")
        exit(1)
    results = []
    for (account_name, cookie_str) in accounts:
        print(f"\n处理账户: {account_name}")
        success, msg, flow_value, flow_unit = ikuuu_signin(cookie_str, account_name)
        results.append({
            'account_name': account_name, 
            'success': success, 
            'message': msg,
            'flow_value': flow_value,
            'flow_unit': flow_unit
        })
        print(f"结果: {msg} | 剩余流量: {flow_value} {flow_unit}")
    send_notification(results)
    print("\n脚本执行完成")