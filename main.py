"""
NodeSeek 自动签到 — 单文件版
用法: pip install curl_cffi requests && python main.py
配置: 同目录下创建 .env 文件（参考 .env.example）
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from curl_cffi import requests

# ── 常量 ──────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent
COOKIE_FILE = ROOT / ".nodeseek-cookie.json"
LOG_FILE = ROOT / "logs" / "checkin.log"

NODESEEK_TURNSTILE_KEY = "0x4AAAAAAAaNy7leGjewpVyR"
NODESEEK_LOGIN_URL = "https://www.nodeseek.com/signIn.html"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": UA,
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nodeseek.com",
    "Referer": "https://www.nodeseek.com/signIn.html",
    "sec-ch-ua": '"Not A(Brand";v="99", "Microsoft Edge";v="121", "Chromium";v="121"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
}

# ── .env 读取（不依赖 python-dotenv）───────────────────────────────────


def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


# ── 工具函数 ────────────────────────────────────────────────────────────


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_cookies() -> dict:
    try:
        return json.loads(COOKIE_FILE.read_text("utf-8"))
    except Exception:
        return {}


def save_cookies(data: dict):
    COOKIE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")


# ── YesCaptcha 解 Turnstile ────────────────────────────────────────────


def solve_captcha(client_key: str, base_url: str) -> str:
    log("[Captcha] 创建 YesCaptcha Turnstile 任务...")
    resp = requests.post(
        f"{base_url}/createTask",
        json={
            "clientKey": client_key,
            "task": {
                "type": "TurnstileTaskProxyless",
                "websiteURL": NODESEEK_LOGIN_URL,
                "websiteKey": NODESEEK_TURNSTILE_KEY,
            },
        },
        timeout=30,
    )
    data = resp.json()
    task_id = data.get("taskId")
    if not task_id:
        raise RuntimeError(f"创建验证码任务失败: {data}")

    log(f"[Captcha] 任务已创建: {task_id}，等待解决...")

    deadline = time.time() + 120
    while time.time() < deadline:
        time.sleep(5)
        result = requests.post(
            f"{base_url}/getTaskResult",
            json={"clientKey": client_key, "taskId": task_id},
            timeout=30,
        ).json()

        if result.get("status") == "ready" and result.get("solution", {}).get("token"):
            log("[Captcha] 验证码已解决")
            return result["solution"]["token"]
        if result.get("status") == "failed":
            raise RuntimeError(f"验证码任务失败: {result}")

    raise RuntimeError("验证码超时未解决")


# ── IMAP 接收邮箱验证码 ──────────────────────────────────────────────


def fetch_email_code(imap_host: str, imap_user: str, imap_pass: str,
                     wait: int = 90) -> str:
    """通过 IMAP 从邮箱中读取 NodeSeek 验证码"""
    import imaplib
    import email as email_lib
    from email.header import decode_header

    log(f"[IMAP] 连接 {imap_host} ({imap_user}) 读取验证码...")
    deadline = time.time() + wait

    # 先记录发验证码前已有的 nodeseek 邮件数量
    old_count = 0
    try:
        mail = imaplib.IMAP4_SSL(imap_host)
        mail.login(imap_user, imap_pass)
        mail.select("INBOX")
        _, data = mail.search(None, "FROM", "nodeseek")
        if data[0]:
            old_count = len(data[0].split())
        mail.logout()
    except Exception:
        pass

    log(f"[IMAP] 已有 {old_count} 封 NodeSeek 邮件，等待新验证码...")

    while time.time() < deadline:
        time.sleep(6)
        try:
            mail = imaplib.IMAP4_SSL(imap_host)
            mail.login(imap_user, imap_pass)
            mail.select("INBOX")

            # 直接搜索来自 nodeseek 的邮件
            _, data = mail.search(None, "FROM", "nodeseek")
            if not data[0]:
                mail.logout()
                continue

            all_ids = data[0].split()
            # 只看新增的 nodeseek 邮件
            if len(all_ids) <= old_count:
                mail.logout()
                continue

            # 从最新的开始读取
            new_ids = all_ids[old_count:]
            for mid in reversed(new_ids):
                _, msg_data = mail.fetch(mid, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)

                # 提取正文
                body = _get_email_body(msg)
                if not body:
                    continue

                log(f"[IMAP] 邮件内容: {body[:200]}")

                # 提取验证码（NodeSeek 是16进制字符串）
                patterns = [
                    r'验证码是([a-f0-9]{16,32})',
                    r'验证码[：:\s]*([a-f0-9]{16,32})',
                    r'([a-f0-9]{24})',
                ]
                for pattern in patterns:
                    match = re.search(pattern, body, re.IGNORECASE)
                    if match:
                        code = match.group(1)
                        log(f"[IMAP] 提取到验证码: {code}")
                        mail.logout()
                        return code

            mail.logout()
        except Exception as e:
            log(f"[IMAP] 读取异常: {e}")
            continue

    raise RuntimeError("等待邮箱验证码超时")


def _get_email_body(msg) -> str:
    """从邮件对象中提取正文文本"""
    import email as email_lib

    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        body = payload.decode(charset, errors="ignore")
                    except Exception:
                        body = payload.decode("utf-8", errors="ignore")
                    break
            elif ct == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        body = payload.decode(charset, errors="ignore")
                    except Exception:
                        body = payload.decode("utf-8", errors="ignore")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                body = payload.decode(charset, errors="ignore")
            except Exception:
                body = payload.decode("utf-8", errors="ignore")

    return body


# ── 浏览器指纹模拟 ────────────────────────────────────────────────────


def _generate_integrity_token() -> str:
    """生成浏览器指纹模拟 token（模拟 FingerprintJS visitorId）"""
    import hashlib
    import uuid
    raw = uuid.uuid4().hex + UA
    h = hashlib.md5(raw.encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def _parse_json(resp, context: str) -> dict:
    """解析 JSON 响应；被 Cloudflare 拦截时给出可读的错误信息"""
    try:
        return resp.json()
    except Exception:
        preview = re.sub(r"\s+", " ", resp.text)[:150]
        raise RuntimeError(f"{context}响应不是 JSON (HTTP {resp.status_code}): {preview}")


# ── 登录 ────────────────────────────────────────────────────────────────


def login(username: str, password: str, client_key: str, base_url: str,
          imap_host: str = "", imap_user: str = "", imap_pass: str = "") -> str:
    log(f"[Login] 正在登录账号: {username}")

    captcha_token = solve_captcha(client_key, base_url)

    session = requests.Session(impersonate="chrome110")

    # 先访问登录页面，获取 Cloudflare cookies
    log("[Login] 访问登录页面获取 Cloudflare cookies...")
    session.get(NODESEEK_LOGIN_URL, timeout=30)

    # 构造请求头：captcha token 放在 header 里，不在 body 里
    headers = {
        **BROWSER_HEADERS,
        "x-captcha-token": captcha_token,
        "x-captcha-source": "turnstile",
        "x-integrity-token": _generate_integrity_token(),
    }

    # 保存并使用 security_token（如果有）
    security_token = os.getenv("_NS_SECURITY_TOKEN", "")
    if security_token:
        headers["x-security-token"] = security_token

    # body 只包含 username 和 password
    resp = session.post(
        "https://www.nodeseek.com/api/account/signIn",
        json={"username": username, "password": password},
        headers=headers,
        timeout=30,
    )

    body = _parse_json(resp, "登录")

    # 检查是否需要邮箱验证
    redirect = body.get("redirect", "")
    if body.get("success") and "emailSignIn" in redirect:
        log("[Login] 账号需要邮箱验证，开始邮箱验证流程...")
        cookie = _login_via_email(session, username, redirect, client_key, base_url,
                                  imap_host, imap_user, imap_pass)
        if cookie:
            return cookie
        raise RuntimeError("邮箱验证登录失败")

    if body.get("success") is False or "失败" in body.get("message", ""):
        raise RuntimeError(f"登录失败: {body.get('message', body)}")

    # 保存服务器返回的 security-token
    sec_token = resp.headers.get("x-security-token", "")
    if sec_token:
        os.environ["_NS_SECURITY_TOKEN"] = sec_token

    cookie = _extract_cookies(session, resp)
    if not cookie:
        raise RuntimeError("登录成功但未获取到 Cookie")

    log("[Login] 登录成功，已获取 Cookie")
    return cookie


def _login_via_email(session, username: str, redirect: str,
                     client_key: str, base_url: str,
                     imap_host: str, imap_user: str, imap_pass: str) -> str:
    """通过邮箱验证码完成登录"""
    from urllib.parse import urlparse, parse_qs

    # 从 redirect URL 提取邮箱地址
    parsed = urlparse(redirect)
    params = parse_qs(parsed.query)
    email_addr = params.get("email", [username])[0]
    log(f"[EmailLogin] 邮箱地址: {email_addr}")

    # 1. 访问邮箱验证页面获取 session
    session.get(f"https://www.nodeseek.com{redirect.split('?')[0]}", timeout=30)

    # 2. 解一个新的 turnstile captcha 用于发送验证码
    captcha_token = solve_captcha(client_key, base_url)

    # 3. 发送邮箱验证码
    log("[EmailLogin] 发送邮箱验证码...")
    send_resp = session.post(
        "https://www.nodeseek.com/api/email",
        json={
            "email": email_addr,
            "mode": "totp",
            "token": captcha_token,
            "source": "turnstile",
            "version": "v3",
        },
        headers={
            **BROWSER_HEADERS,
            "Referer": f"https://www.nodeseek.com{redirect}",
        },
        timeout=30,
    )
    send_body = _parse_json(send_resp, "发送邮箱验证码")
    if not send_body.get("success"):
        raise RuntimeError(f"发送验证码失败: {send_body.get('message', send_body)}")

    log("[EmailLogin] 验证码已发送，等待接收...")

    # 4. 通过 IMAP 读取验证码
    code = fetch_email_code(imap_host, imap_user, imap_pass, wait=90)

    # 5. 提交验证码完成登录
    log(f"[EmailLogin] 提交验证码: {code}")
    login_resp = session.post(
        "https://www.nodeseek.com/api/account/emailSignIn",
        json={"email": email_addr, "code": code},
        headers={
            **BROWSER_HEADERS,
            "Referer": f"https://www.nodeseek.com{redirect}",
            "x-integrity-token": _generate_integrity_token(),
        },
        timeout=30,
    )
    login_body = _parse_json(login_resp, "邮箱验证登录")
    if not login_body.get("success"):
        raise RuntimeError(f"邮箱验证登录失败: {login_body.get('message', login_body)}")

    # 保存 security-token
    sec_token = login_resp.headers.get("x-security-token", "")
    if sec_token:
        os.environ["_NS_SECURITY_TOKEN"] = sec_token

    cookie = _extract_cookies(session, login_resp)
    if cookie:
        log("[EmailLogin] 邮箱验证登录成功，已获取 Cookie")
    return cookie


def _extract_cookies(session, resp) -> str:
    """从 session 和响应中提取 cookie 字符串"""
    cookies = []

    # 从 session cookies 提取
    if session.cookies:
        cookies = [f"{k}={v}" for k, v in session.cookies.items()]

    # 兜底：从 Set-Cookie header 提取
    if not cookies:
        for h in resp.headers.get("set-cookie", "").split(","):
            part = h.split(";")[0].strip()
            if "=" in part:
                cookies.append(part)

    # 兜底：从 resp.cookies 取
    if not cookies and resp.cookies:
        cookies = [f"{k}={v}" for k, v in resp.cookies.items()]

    return "; ".join(cookies) if cookies else ""


# ── 签到 ────────────────────────────────────────────────────────────────


def checkin(cookie: str, label: str = "") -> dict:
    random_mode = os.getenv("NS_RANDOM", "true") != "false"
    tag = f"[{label}]" if label else ""
    log(f"{tag}[签到] 开始签到 (random={random_mode})...")

    try:
        resp = requests.post(
            f"https://www.nodeseek.com/api/attendance?random={str(random_mode).lower()}",
            json={},
            headers={
                **BROWSER_HEADERS,
                "Referer": "https://www.nodeseek.com/board",
                "Cookie": cookie,
            },
            impersonate="chrome110",
            timeout=30,
        )
    except Exception as err:
        # 网络层错误（DNS/超时等），重登也没用，直接失败
        log(f"{tag}[签到] 请求失败: {err}")
        return {"ok": False, "message": str(err), "need_relogin": False}

    # 先拿到响应再解析：Cloudflare 拦截时返回的是 HTML 挑战页而非 JSON
    try:
        data = resp.json()
    except Exception:
        preview = re.sub(r"\s+", " ", resp.text)[:150]
        log(f"{tag}[签到] 响应不是 JSON (HTTP {resp.status_code}): {preview}")
        log(f"{tag}[签到] Cookie 已失效或被 Cloudflare 拦截，需要重新登录")
        return {"ok": False, "message": f"HTTP {resp.status_code} 非JSON响应", "need_relogin": True}

    message = data.get("message", "")

    if data.get("success"):
        log(f"{tag}[签到] {message or '签到成功'}")
        return {"ok": True, "message": message, "need_relogin": False}

    if "已签到" in message or "已完成" in message:
        log(f"{tag}[签到] 今日已签到")
        return {"ok": True, "message": "今日已签到", "need_relogin": False}

    if resp.status_code in (401, 403) or "未登录" in message:
        log(f"{tag}[签到] Cookie 已失效，需要重新登录")
        return {"ok": False, "message": "Cookie 失效", "need_relogin": True}

    log(f"{tag}[签到] 签到异常: {data}")
    return {"ok": False, "message": message, "need_relogin": False}


# ── 随机浏览帖子（模拟真人行为）──────────────────────────────────────


def maybe_browse(cookie: str, label: str = ""):
    """随机决定是否浏览帖子（50%概率），模拟真人行为"""
    import random
    if random.random() < 0.5:
        tag = f"[{label}]" if label else ""
        log(f"{tag}[浏览] 今天不浏览帖子，直接签到")
        return
    random_browse(cookie, label=label)


def random_browse(cookie: str, count: int = 3, label: str = ""):
    """随机浏览几个帖子，模拟真人行为，降低被封风险"""
    import random
    tag = f"[{label}]" if label else ""

    try:
        # 随机决定浏览 1-5 个帖子
        count = random.randint(1, 5)

        # 1. 先访问板块页面
        log(f"{tag}[浏览] 访问论坛首页...")
        board_resp = requests.get(
            "https://www.nodeseek.com/board",
            headers={
                **BROWSER_HEADERS,
                "Cookie": cookie,
            },
            impersonate="chrome110",
            timeout=20,
        )
        board_text = board_resp.text

        # 2. 从页面 HTML 中提取帖子 ID
        post_ids = re.findall(r'/post-(\d+)-1', board_text)
        # 去重
        post_ids = list(dict.fromkeys(post_ids))

        if not post_ids:
            log(f"{tag}[浏览] 未找到帖子，跳过浏览")
            return

        # 3. 随机挑选几个
        count = min(count, len(post_ids))
        selected = random.sample(post_ids, count)
        log(f"{tag}[浏览] 随机浏览 {count} 个帖子...")

        for i, post_id in enumerate(selected):
            resp = requests.get(
                f"https://www.nodeseek.com/post-{post_id}-1",
                headers={
                    **BROWSER_HEADERS,
                    "Referer": "https://www.nodeseek.com/board",
                    "Cookie": cookie,
                },
                impersonate="chrome110",
                timeout=15,
            )
            # 从帖子页面提取标题
            title_match = re.search(r'<title>(.*?)</title>', resp.text)
            title = title_match.group(1)[:30] if title_match else f"帖子{post_id}"

            delay = random.randint(3, 12)
            log(f"{tag}[浏览] ({i+1}/{count}) 浏览 [{title}] 停留{delay}秒")
            time.sleep(delay)

        log(f"{tag}[浏览] 浏览完毕")

    except Exception as e:
        log(f"[Browse] 浏览异常（不影响签到）: {e}")


# ── 主流程 ──────────────────────────────────────────────────────────────


def run_account(username: str, password: str, client_key: str, base_url: str,
                imap_host: str = "", imap_user: str = "", imap_pass: str = ""):
    import random

    cookies_store = load_cookies()
    cookie = cookies_store.get(username, {}).get("value")

    if cookie:
        # 随机决定是否浏览帖子
        maybe_browse(cookie, label=username)
        result = checkin(cookie, label=username)
        if result["ok"]:
            return
        if result["need_relogin"]:
            log(f"[{username}] Cookie 失效，重新登录")
        else:
            log(f"[{username}] 签到失败: {result['message']}")
            return

    cookie = login(username, password, client_key, base_url,
                   imap_host, imap_user, imap_pass)
    cookies_store[username] = {"value": cookie, "updatedAt": datetime.now().isoformat()}
    save_cookies(cookies_store)

    # 登录后随机浏览帖子+延迟，再签到，模拟真人
    maybe_browse(cookie, label=username)
    delay = random.randint(5, 20)
    log(f"[{username}] 浏览完毕，等待 {delay} 秒后签到...")
    time.sleep(delay)

    result = checkin(cookie, label=username)
    if result["ok"]:
        log(f"[{username}] {result['message']}")
    else:
        log(f"[{username}] 登录后签到仍失败: {result['message']}")


def main():
    load_env()

    client_key = os.getenv("YESCAPTCHA_KEY", "")
    base_url = os.getenv("YESCAPTCHA_BASE", "https://api.yescaptcha.com").rstrip("/")
    # 根据 IMAP_USER 邮箱后缀自动选择 IMAP 服务器
    def guess_imap_host(email_addr: str) -> str:
        """根据邮箱地址自动判断 IMAP 服务器"""
        domain = email_addr.split("@")[-1].lower() if "@" in email_addr else ""
        imap_map = {
            "qq.com": "imap.qq.com",
            "163.com": "imap.163.com",
            "126.com": "imap.126.com",
            "gmail.com": "imap.gmail.com",
            "outlook.com": "outlook.office365.com",
            "hotmail.com": "outlook.office365.com",
            "yahoo.com": "imap.mail.yahoo.com",
            "foxmail.com": "imap.qq.com",
        }
        return imap_map.get(domain, f"imap.{domain}")

    # ── 读取编号式账号配置：NS_USER1, NS_USER2, ... ──
    accounts = []
    i = 1
    while True:
        user = os.getenv(f"NS_USER{i}", "").strip()
        if not user:
            break
        pwd = os.getenv(f"NS_PASS{i}", "").strip()
        imu = os.getenv(f"IMAP_USER{i}", "").strip()
        imp = os.getenv(f"IMAP_PASS{i}", "").strip()
        if pwd:
            accounts.append({"user": user, "pwd": pwd, "imap_user": imu, "imap_pass": imp})
        else:
            log(f"[{user}] 未配置密码(NS_PASS{i})，跳过")
        i += 1

    # ── 兼容旧格式（逗号分隔） ──
    if not accounts:
        usernames = [s.strip() for s in os.getenv("NS_USERNAME", "").split(",") if s.strip()]
        passwords = [s.strip() for s in os.getenv("NS_PASSWORD", "").split(",") if s.strip()]
        imu_list = [s.strip() for s in os.getenv("IMAP_USER", "").split(",") if s.strip()]
        imp_list = [s.strip() for s in os.getenv("IMAP_PASS", "").split(",") if s.strip()]
        for idx, user in enumerate(usernames):
            pwd = passwords[idx] if idx < len(passwords) else ""
            imu = imu_list[idx] if idx < len(imu_list) else ""
            imp = imp_list[idx] if idx < len(imp_list) else ""
            if pwd:
                accounts.append({"user": user, "pwd": pwd, "imap_user": imu, "imap_pass": imp})

    if not accounts:
        log("未配置账号，请在 .env 中设置 NS_USER1/NS_PASS1 等")
        sys.exit(1)
    if not client_key:
        log("未配置 YESCAPTCHA_KEY")
        sys.exit(1)

    log(f"========== NodeSeek 签到开始，共 {len(accounts)} 个账号 ==========")

    for idx, acc in enumerate(accounts):
        log(f"── 账号 {idx+1}/{len(accounts)}: {acc['user']} ──")
        try:
            # 根据邮箱自动选择 IMAP 服务器，也可用 IMAP_HOST 环境变量强制指定
            imap_host = os.getenv("IMAP_HOST", "") or guess_imap_host(acc["imap_user"])
            run_account(acc["user"], acc["pwd"], client_key, base_url,
                        imap_host, acc["imap_user"], acc["imap_pass"])
        except Exception as err:
            log(f"[{acc['user']}] 异常: {err}")

    log("========== NodeSeek 签到结束 ==========")


if __name__ == "__main__":
    main()
