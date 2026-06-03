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

- 注册 [YesCaptcha](https://yescaptcha.com) 获取客户端 Key
- 准备邮箱 IMAP 授权码（不是登录密码）

### 2. 上传到服务器

```bash
scp main.py .env install.sh root@你的服务器IP:/opt/nodeseek/
```

### 3. 配置

```bash
ssh root@你的服务器IP
cp /opt/nodeseek/.env.example /opt/nodeseek/.env
nano /opt/nodeseek/.env
```

编辑 `.env`，填入你的真实信息：

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

### 4. 一键部署

```bash
bash /opt/nodeseek/install.sh
```

部署完成后会自动：
- 安装 Python 依赖
- 设置时区为上海
- 创建 systemd 定时任务（每天 ~9:05 签到）
- 开启开机自启

## 管理命令

```bash
# 手动签到一次
systemctl start nodeseek.service

# 查看日志
cat /opt/nodeseek/logs/checkin.log

# 查看定时器状态
systemctl status nodeseek.timer

# 修改配置后重载
systemctl daemon-reload
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
| `.env` | 配置文件（**不要泄露**） |
| `.env.example` | 配置模板 |
| `install.sh` | 一键部署脚本 |

## 注意事项

- `.env` 包含账号密码，**不要分享或上传到公开仓库**
- 每天签到时间有 0~5 分钟随机延迟，避免固定时间
- 随机浏览功能有 50% 概率跳过，模拟真人行为
