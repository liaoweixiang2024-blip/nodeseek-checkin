# NodeSeek 自动签到

NodeSeek 论坛自动签到工具，支持多账号、Cookie 自动续期、邮箱验证码自动获取、随机浏览模拟真人行为。

## 功能

- ✅ 每日自动签到（支持随机/固定模式）
- ✅ 多账号支持
- ✅ Cookie 自动保存 + 失效自动重新登录
- ✅ 邮箱验证码自动获取（支持 QQ / 163 / Gmail 等邮箱）
- ✅ YesCaptcha 自动解 Cloudflare Turnstile 验证码
- ✅ 随机浏览帖子，模拟真人行为，降低封号风险
- ✅ 一键部署脚本，systemd 定时任务 + 开机自启

## 快速开始

### 1. 准备

- 注册 [YesCaptcha](https://yescaptcha.com/i/CnxOIp) 获取客户端 Key
- 准备邮箱 IMAP 授权码（不是登录密码）

### 2. 一键安装

在服务器上以 root 执行一行命令：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/liaoweixiang2024-blip/nodeseek-checkin/main/install.sh)
```

脚本会自动完成：
- **环境检查**：检测包管理器，缺 `git` / `python3` / `pip` 自动补齐
- **拉取代码**：从 GitHub 克隆到 `/opt/nodeseek`
- **安装依赖**：`pip install curl_cffi`（预编译包失败会自动装编译依赖重试）
- **配置服务**：写入 systemd service + timer，开机自启，每天 09:05 ±5 分钟签到
- **保留配置**：已存在的 `.env` 永远不覆盖；没有则从模板生成

> 国内服务器若连不上 GitHub，可先在本机 `scp install.sh root@服务器IP:/root/`，再 `bash /root/install.sh`。

### 3. 配置账号

```bash
nano /opt/nodeseek/.env
```

填入你的真实信息：

```env
# 账号1
NS_USER1="你的用户名或邮箱"
NS_PASS1="你的密码"
IMAP_USER1="你的邮箱"
IMAP_PASS1="你的邮箱授权码"

# YesCaptcha
YESCAPTCHA_KEY="你的YesCaptcha客户端Key"

# 签到模式：true=随机签到（鸡腿多），false=固定签到
NS_RANDOM="true"
```

### 4. 验证

```bash
systemctl start nodeseek.service      # 手动签到一次
tail -30 /opt/nodeseek/logs/checkin.log   # 看签到结果
```

## 管理命令

```bash
# 手动签到一次
systemctl start nodeseek.service

# 看签到日志
tail -30 /opt/nodeseek/logs/checkin.log

# 看运行报错（脚本 import 阶段失败只会出现在这里）
journalctl -u nodeseek.service -n 50 --no-pager

# 查看定时器状态
systemctl list-timers nodeseek.timer --no-pager

# 升级（重新跑安装命令即可，.env 会保留）
bash <(curl -fsSL https://raw.githubusercontent.com/liaoweixiang2024-blip/nodeseek-checkin/main/install.sh)

# 卸载
bash install.sh --uninstall
```

## 多账号

在 `.env` 中按编号添加即可：

```env
NS_USER1="账号1"
NS_PASS1="密码1"
IMAP_USER1="邮箱1"
IMAP_PASS1="授权码1"

NS_USER2="账号2"
NS_PASS2="密码2"
IMAP_USER2="邮箱2"
IMAP_PASS2="授权码2"
```

以此类推，支持无限个账号。

## 邮箱授权码获取方式

| 邮箱 | 获取方式 |
|------|----------|
| QQ 邮箱 | 设置 → 账户 → POP3/IMAP → 开启 → 生成授权码 |
| 163 邮箱 | 设置 → POP3/SMTP/IMAP → 开启 → 设置客户端授权密码 |
| Gmail | 开启两步验证 → 应用专用密码 |

## 工作流程

```
启动 → 读取配置 → 遍历每个账号 →
  ├─ 有 Cookie？
  │   ├─ 随机浏览帖子（50%概率）
  │   ├─ 签到
  │   └─ Cookie 失效？→ 自动重新登录 → 签到
  └─ 无 Cookie → 登录（自动解验证码 + 邮箱验证码）→ 签到
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `main.py` | 主程序（单文件，纯 Python） |
| `.env` | 配置文件（**不要泄露**，已 gitignore） |
| `.env.example` | 配置模板 |
| `install.sh` | 一键安装 / 升级 / 卸载脚本 |
| `.nodeseek-cookie.json` | 登录 Cookie 缓存（自动生成，已 gitignore） |
| `logs/checkin.log` | 签到日志（自动生成，已 gitignore） |

## 注意事项

- `.env` 包含账号密码和 API Key，**注意保管不要泄露**
- 每天签到时间有 0~5 分钟随机延迟，避免固定时间
- 随机浏览功能有 50% 概率跳过，模拟真人行为
