# FeedLog (dbb-feedback) 中文环境初始化指南

> 目标仓库：`imoyao/dbb-feedback`（FeedLog fork）
> 部署方式：Cloudflare Workers + R2 + Hyperdrive(PostgreSQL)
> 本文档面向接手部署/二次部署的开发者

## 前置准备

1. Cloudflare 账号（Workers 免费额度足以支撑中小流量）
2. PostgreSQL 数据库（需启用 `vector` 扩展）——推荐 Neon 免费层或 Supabase
3. 域名（可选，但建议绑定自定义域名）

## 第一步：Cloudflare 资源创建

```bash
# 1. 创建 R2 存储桶（用于用户上传的附件/图片）
wrangler r2 bucket create feedlog

# 2. 创建 Hyperdrive 配置（PostgreSQL 加速代理）
wrangler hyperdrive create feedlog \
  --connection-string="postgresql://user:password@host:5432/feedlog"
# 记录返回的 Hyperdrive ID，填入 wrangler.toml

# 3. 部署 Worker
wrangler deploy
```

## 第二步：必需环境变量（Secret）

```bash
# 会话加密密钥（生成：openssl rand -hex 32）
wrangler secret put BETTER_AUTH_SECRET

# 管理员邮箱（逗号分隔多个，需在首次注册前设置）
wrangler secret put SYSTEM_ADMIN_EMAILS
# 输入你的邮箱，例如：admin@example.com

# PostgreSQL 连接串（直接连接，非 Hyperdrive）
# 桥接脚本也需要这个，建议同时记下来
wrangler secret put DATABASE_URL
# postgresql://user:password@host:5432/feedlog
```

## 第三步：可选但推荐的配置

### AI 功能（智谱免费模型）

```bash
wrangler secret put OPENAI_API_KEY     # 智谱 API Key
wrangler secret put OPENAI_BASE_URL    # https://open.bigmodel.cn/api/paas/v4
wrangler secret put OPENAI_TEXT_MODEL  # glm-4-flash（免费）
```

> 未设置时 AI 功能（相似想法合并、AI 更新日志）自动禁用，不影响核心功能。

### GitHub OAuth 登录

在 GitHub `Settings → Developer settings → OAuth Apps` 创建应用：
- Homepage URL: `https://你的域名`
- Callback URL: `https://你的域名/api/auth/callback/github`

```bash
wrangler secret put GITHUB_CLIENT_ID
wrangler secret put GITHUB_CLIENT_SECRET
```

### 配置公开 URL

```bash
wrangler secret put BETTER_AUTH_URL
# https://feedback.duobeibei.com（替换为实际域名）
```

## 第四步：首次访问初始化

1. 浏览器打开 Worker 域名（或绑定的自定义域名）
2. 首次访问会触发自动数据库迁移（`/setup` 路由，由 `runtime-migrate` 处理）
3. 用管理员邮箱注册/登录（支持邮箱密码或 GitHub OAuth）
4. 进入管理后台 → 创建组织（建议名：**多倍贝**）
5. 创建看板（Board）：
   - **功能建议**（Feature Requests）：用户提交新功能想法
   - **问题反馈**（Bug Reports）：报 bug 用
   - **使用咨询**（Q&A）：使用问题/帮助
6. 配置 Roadmap 状态（中文版已翻译，默认即可）：
   - 规划中 → 进行中 → 已上线
7. 在每个看板的设置中开启「公开发布」（允许未登录用户提交）

## 第五步：品牌定制

修改 `app.config.ts` 或通过管理后台：
- 站点名称：多倍贝反馈中心
- Logo：上传 `branding/` 目录下的 logo
- 主题色：`#10B981`（多倍贝品牌绿）

## 第六步：桥接配置（FeedLog ↔ GitHub Issues）

详见 fundmate 仓库的 `.github/workflows/bridge-feedback.yml`。

需要在 dbb-feedback 仓库设置 secret：
```bash
gh secret set DATABASE_URL --repo imoyao/dbb-feedback
# 填入 PostgreSQL 直连串（不是 Hyperdrive ID）
```

需要在 fundmate 仓库设置 secrets：
```bash
gh secret set FEEDLOG_DATABASE_URL --repo imoyao/fundmate
# 同上，桥接脚本用同一个数据库连接串
```

## 常见问题

### Q: Hyperdrive 连接不上？
确认 PostgreSQL 端已开启 `vector` 扩展：
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Q: 首次访问 500 错误？
检查 Cloudflare Workers Logs（`wrangler tail`），常见原因：
- `DATABASE_URL` 格式错误或网络不通
- `pgvector` 扩展未安装
- Secret 未设置（`BETTER_AUTH_SECRET` 为空）

### Q: 用户无法提交反馈？
检查看板设置中「公开发布」是否开启。FeedLog 默认需要登录才能提交，需手动改为公开模式。

### Q: 如何从 SaaS 版迁移数据？
自部署版没有 SaaS 数据导入功能。如果之前用了 feedlog.ai 的免费版，需要手动导出后通过 SQL 导入 PostgreSQL。官方目前未提供导出工具。

## 维护

```bash
# 定期同步上游代码（也可通过 GitHub Actions 自动同步）
git checkout main
git pull upstream main
git push origin main
```

上游仓库：https://github.com/linkcraftstudio/feedlog
自动同步：`.github/workflows/sync-upstream.yml`（每周自动检查合并）
