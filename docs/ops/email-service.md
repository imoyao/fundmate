---
title: 多多贝 · 邮箱配置方案文档
---

# 多多贝 · 邮箱配置方案文档

本文档规范「多多贝」项目邮箱系统的架构、配置步骤与日常运维。
采用 Resend（发信）+ Cloudflare Email Routing（收信转发） 的零成本方案。
目标：用 0 元额外费用、0 个额外邮箱账户，实现 @duoduobei.com 域名的专业收发信。

## 前置说明：方案选择与实施前提

本方案适用于拥有以下资源的个人开发者：

| 前提条件 | 说明 |
|---|---|
| ✅ 已购买域名 | 本文以 duoduobei.com 为例 |
| ✅ 域名已托管至 Cloudflare | 用于 DNS 管理 + Email Routing |
| ✅ 拥有一个个人邮箱 | 本文选用 QQ 邮箱（me@qq.com）作为收信终端 |
| ✅ 可访问 Resend 服务 | 用于发信，注册账号即可 |

### 为什么选择 QQ 邮箱作为收信终端？

| 考量 | 说明 |
|---|---|
| 国内访问稳定 | Gmail 在国内无法稳定访问，163 邮箱的"代发"功能会显示"由 xxx 代发"，影响品牌纯净度 |
| QQ 邮箱"其他邮箱"功能 | 支持通过第三方 SMTP 服务器发送，配合 Resend 可以实现纯净发信——对方只看到 support@duoduobei.com，不显示"由 xxx 代发" |
| 配置成本低 | 一次配置，长期使用，无需额外维护 |

### 整体架构

| 方向 | 服务 | 职责 |
|---|---|---|
| 发信（系统→用户） | Resend | 发送验证码、密码重置、系统通知等，显示发件人为 noreply@duoduobei.com |
| 收信（用户→你） | Cloudflare Email Routing | 将所有 @duoduobei.com 的来信转发至你的 QQ 邮箱（me@qq.com） |
| 回信（你→用户） | QQ 邮箱 + Resend SMTP | 通过 QQ 邮箱的"其他邮箱"功能，用 Resend 的 SMTP 服务器发送，对方看到 support@duoduobei.com |

## 一、邮箱地址规划

### 最终配置表

| 邮箱地址 | 用途 | 发信方式 | 收信方式 | 是否需要独立邮箱账户 |
|---|---|---|---|---|
| noreply@duoduobei.com | 系统自动发信（验证码、密码重置、通知） | Resend SMTP / API | 不接收来信 | ❌ 否 |
| support@duoduobei.com | 用户反馈、客服联系 | 个人邮箱以该地址回复 | Cloudflare 转发至 me@qq.com | ❌ 否 |
| hello@duoduobei.com | 外部合作、商务咨询 | 个人邮箱以该地址回复 | Cloudflare 转发至 me@qq.com | ❌ 否 |
| admin@duoduobei.com | 服务器警报、内部管理 | 个人邮箱以该地址回复 | Cloudflare 转发至 me@qq.com | ❌ 否 |
| me@qq.com | 你的个人收信终端 | — | 接收所有转发邮件 | ✅ 1 个（已有） |

> 个人邮箱以 me@qq.com 为例，实际使用你常用的 QQ 邮箱即可。

## 二、配置步骤

### 阶段一：配置 Resend 发信

#### Step 1：注册 Resend 账号

1. 访问 Resend 官网
2. 推荐使用 GitHub 账号直接登录
3. 完成注册

#### Step 2：添加并验证域名

1. 进入控制台 → Domains → Add Domain
2. 输入 duoduobei.com（不加 mail. 前缀）
3. Resend 会生成一组 DNS 记录（DKIM、SPF、MX）

需要在 Cloudflare DNS 中添加的记录：

| 记录类型 | 名称/Host | 值/内容 | 说明 |
|---|---|---|---|
| TXT | 由 Resend 生成 | 由 Resend 生成 | DKIM 记录 |
| TXT | 由 Resend 生成 | 由 Resend 生成 | SPF 记录 |
| MX | 由 Resend 生成 | 由 Resend 生成 | MX 记录 |

📌 提示：如果你的域名在 Cloudflare 托管，Resend 支持一键自动添加 DNS 记录。

4. 添加完成后，回到 Resend 点击 Check DNS 验证
5. 等待状态变为 Verified（通常几分钟）

#### Step 3：创建 API Key

1. 控制台 → API Keys → Create API Key
2. 权限选择 Sending access
3. 选择已验证的域名
4. 复制并保存 Key（仅显示一次，丢失需重新生成）

#### Step 4：获取 SMTP 凭证（用于 QQ 邮箱配置）

| 配置项 | 值 | 来源 |
|---|---|---|
| SMTP 服务器 | smtp.resend.com | 固定值 |
| 端口 | 465（SSL）或 587（STARTTLS） | |
| 用户名 | resend | 固定值 |
| 密码 | 你的 Resend API Key | 从 Step 3 获取 |

### 阶段二：配置 Cloudflare Email Routing 收信转发

#### Step 1：开启 Email Routing

1. 登录 Cloudflare 控制台，进入 duoduobei.com 域名
2. 左侧菜单：Compute → Email Service → Email Routing
3. 点击 Onboard Domain，选择 duoduobei.com
4. Cloudflare 会自动添加 MX 和 TXT 记录

⚠️ 注意：如果域名已在其他邮件服务中使用，开启 Email Routing 会替换 MX 记录，旧邮件服务将停止工作。

#### Step 2：添加目标地址

1. 在 Email Routing 面板中，进入 Destination Addresses
2. 添加 me@qq.com 作为目标地址
3. Cloudflare 会发送验证邮件到该邮箱，点击验证链接完成确认

#### Step 3：配置路由规则

推荐方式：开启 Catch-all

1. 进入 Routing Rules
2. 启用 Catch-all 规则
3. 操作选择 Send to an email，目标选 me@qq.com
4. 保存

Catch-all 效果：所有发送到 *@duoduobei.com 的邮件都会转发到 me@qq.com，无需为每个地址单独配置。

### 阶段三：配置 QQ 邮箱回复来信（让对方看到域名邮箱）

#### 适用场景

当你收到用户发送到 support@duoduobei.com 的邮件后，在 QQ 邮箱中回复时，希望对方看到的发件人是 support@duoduobei.com，而不是 me@qq.com。

#### 配置步骤

1. 登录 QQ 邮箱（mail.qq.com）
2. 进入 设置 → 账户 → 其他邮箱（或"发件人管理"）
3. 点击 添加其他邮箱地址
4. 输入你要使用的域名邮箱地址，如 support@duoduobei.com
5. 发信设置选择 "通过其他邮箱的 SMTP 服务器发送"
6. 填写 Resend SMTP 信息：
   - SMTP 服务器：smtp.resend.com
   - 端口：587 或 465
   - 用户名：resend
   - 密码：你的 Resend API Key
7. QQ 邮箱会发送验证邮件到 support@duoduobei.com（通过 Cloudflare 转发到 me@qq.com）
8. 登录 me@qq.com，点击验证链接完成确认

#### 使用方式

配置完成后，在 QQ 邮箱写信时，点击发件人下拉框，选择 support@duoduobei.com 即可。

✅ 效果：对方收到的邮件发件人只显示 support@duoduobei.com，不会出现"由 QQ 邮箱代发"的提示。

### 阶段四：在网站中集成发信

#### 方式一：SMTP 配置（适用于通用邮件库）

在网站后台配置发件服务器：

| 配置项 | 值 |
|---|---|
| SMTP 服务器 | smtp.resend.com |
| 端口 | 587 或 465 |
| 加密 | STARTTLS（587）或 SSL（465） |
| 用户名 | resend |
| 密码 | 你的 Resend API Key |
| 发件地址 | noreply@duoduobei.com |
| 发件名称 | 多多贝 |

#### 方式二：API 直调（推荐，更灵活）

Resend 提供简洁的 REST API：

Python 示例（使用 Resend SDK）：

```python
import resend

resend.api_key = "re_your_api_key"

params = {
    "from": "多多贝 <noreply@duoduobei.com>",
    "to": ["user@example.com"],
    "subject": "你的验证码",
    "html": "<h1>验证码：123456</h1>"
}

email = resend.Emails.send(params)
print(email)
```

⚠️ 重要：from 字段的域名必须是在 Resend 已验证的域名。

## 三、费用总结

| 项目 | 费用 | 说明 |
|---|---|---|
| Resend 免费版 | ¥0 | 3,000 封/月，1 个域名 |
| Cloudflare Email Routing | ¥0 | 完全免费 |
| QQ 邮箱（已有） | ¥0 | 使用现有 QQ 邮箱 |
| 合计 | ¥0/月 | 仅需已购买的域名成本 |

## 四、配置检查清单

| 检查项 | 状态 | 备注 |
|---|---|---|
| [ ] Resend 账号已注册 | ☐ | https://resend.com |
| [ ] duoduobei.com 域名已添加并验证 | ☐ | Domains → Verified |
| [ ] DNS 记录（DKIM/SPF/MX）已添加 | ☐ | 在 Cloudflare DNS 中确认 |
| [ ] API Key 已创建并保存 | ☐ | 权限：Sending access |
| [ ] Cloudflare Email Routing 已开启 | ☐ | 并添加 me@qq.com 为目标 |
| [ ] Catch-all 路由规则已配置 | ☐ | 所有 @duoduobei.com → me@qq.com |
| [ ] QQ 邮箱已添加域名邮箱作为发件人 | ☐ | 设置→账户→其他邮箱 |
| [ ] 测试收发信正常 | ☐ | 用外部邮箱测试收发 |
| [ ] 网站 SMTP/API 配置已完成 | ☐ | 发件地址 noreply@duoduobei.com |

---

文档版本：v1.1 | 更新日期：2026-08-10 | 作者：阿垚

变更记录：

- v1.0：初始版本
- v1.1：前置说明增加方案选择理由；示例邮箱从 me@163.com 改为 me@qq.com；新增"阶段三：QQ 邮箱配置"
