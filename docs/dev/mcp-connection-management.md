---
title: MCP 连接管理与用户凭据设计
---

# MCP 连接管理与用户凭据设计

> 状态：**设计待评审**（2026-11-27）。本文是 `mcp-integration.md` 的续篇，
> 补的是 S5 缺口（用户私有凭据）与「连接管理页面」的边界。
> 适用对象：给 Fund Mate 接第三方数据服务（同花顺投资账本、天天基金等）的开发者。

## 0. 一句话结论

**传输层已经够了，缺的是凭据层。** `services/mcp/` 的 `transport.py` / `base.py` /
`registry.py` 已经把「怎么和 MCP 说话」做完了；同花顺接不进来的唯一硬阻塞是
`credentials.py:101` 对 `USER_PRIVATE` 直接抛 `McpUserTokenMissing('用户凭据表尚未接入（S5）')`。
做完 S5，OAuth 2.1 授权码、扫码登录、静态 API Key 三种方式共用同一张表、同一条解析路径。

## 1. 两条真实路径（实测，不是推测）

用户提到的两个服务看起来都是「浏览器/扫码拿授权」，但协议形态完全不同，
**不能共用一套授权编排**。

| 维度 | 同花顺投资账本 | 天天基金 ttskill |
|---|---|---|
| 形态 | 远程 MCP server（streamableHttp） | **本地 CLI 基础包 + 业务 Skill 包** |
| 接入点 | `https://tzzb.10jqka.com.cn/mcp` | `ttskill invoke`（子进程，本机签名调用） |
| 认证 | OAuth 2.1 授权码 + PKCE S256 + DCR | **CLI 登录态**（`ttskill login` 扫码），明确禁用 `TTFUND_APIKEY` / `X-API-Key` |
| 用户在浏览器做什么 | 登录同花顺 + 同意授权 → 跳转回调 | 打开页面 → 用天天基金 App 扫码 → 确认授权 |
| 凭据持有方 | 我们拿到 `access_token` + `refresh_token`，自己存 | **CLI 自己存登录态**，我们只管进程调用与登录状态 |
| scope | `tools.read`（实测授权端点接受） | 无 scope 概念，按 `skill_id` 授权 |
| 数据归属 | `USER_PRIVATE`（个人账本持仓） | `USER_PRIVATE`（个人持仓查询） |

### 1.1 同花顺端点实测证据（2026-11-27）

```
POST https://tzzb.10jqka.com.cn/mcp  (initialize)
→ 401
WWW-Authenticate: Bearer resource_metadata="https://tzzb.10jqka.com.cn/.well-known/oauth-protected-resource"

GET /.well-known/oauth-protected-resource
→ authorization_servers: ["https://tzzb.10jqka.com.cn/"]
  tls_client_certificate_bound_access_tokens: true

GET /.well-known/oauth-authorization-server
→ authorization_endpoint: /oauth2/authorize
  token_endpoint: /oauth2/token
  registration_endpoint: /oauth2/register       (DCR，RFC 7591)
  code_challenge_methods_supported: ["S256"]
  grant_types: authorization_code, refresh_token, token-exchange
  response_types: ["code"]

POST /oauth2/register  (无 scope，redirect_uri=本机回环)
→ 200 {"client_id": "...", "token_endpoint_auth_method": "none"}

GET /oauth2/authorize?...&scope=tools.read
→ 302 Location: /pc/mcpAuth.html?...   （授权页存在，参数被接受）
```

**未验证的风险**：元数据声明 `tls_client_certificate_bound_access_tokens: true`。
注册阶段不需要客户端证书，但**签发的 token 是否强制 mTLS 绑定尚未验证**——
这决定我们拿到的 Bearer token 能否直接调通 `/mcp`。必须在首次授权完成后实测：
拿 `access_token` 直接 `POST /mcp`，看是 200 还是 401/证书错误。
若强制绑定，退路是用 DPoP（元数据也声明支持）或要求用户证书，需另开卡评估。

### 1.2 天天基金 ttskill 实测证据（官方文档原文要点）

安装指南 `https://skills.tiantianfunds.com/ttfund-skills/ttfund-skill-cli-install.md` 明确：

- `ttskill` 是 **CLI 登录型 Skill 的本地基础包**，负责基础包安装、业务包同步、
  扫码登录、本机签名调用；
- **「不需要配置 `TTFUND_APIKEY`」「不要使用 `X-API-Key` 调用 CLI 登录型能力」**；
- 用户只完成扫码或确认授权；Agent 主动 `ttskill login` 拉起；
- 调用走 `ttskill invoke`，请求体必须带 `skill_id` 与 `_skill_version`；
- 登录态失效返回 `cli_login_required` ⇒ 重新 `ttskill login`。

含义：**Fund Mate 不能绕过 CLI 直接持有天天基金的 token**，也不应该替用户管理它。
我们要做的是「CLI 生命周期管理 + 登录态探测 + 调用编排」，不是 OAuth 凭据表。

### 1.3 关键区别：为什么不能合并成一套

同花顺：凭据是**我们持有的 bearer token**，可以加密入库、刷新、跨请求复用。
天天基金：凭据是**CLI 进程持有的登录态**，我们只能通过 `ttskill` 命令间接使用，
进程/用户目录状态才是真相源。

把它们塞进同一张 `user_mcp_credentials` 表会导致「表里有一行但 CLI 没登录」的假连接。
故两条路分开：

- 同花顺 → S5 凭据表（`auth_type='oauth2'`）
- 天天基金 → CLI 连接状态（`connector_type='cli'`，记录安装版本与登录探测结果，不存 token）

## 2. 凭据层设计（S5）

### 2.1 表：`user_mcp_credentials`

对齐 `mcp-integration.md` §8 的预留形状，按**多用户**（不是多租户）隔离：
隔离键用 `user_id`，即 `users.id`。Fund Mate 的 `users` 表已是 Supabase Auth 的本地映射，
不需要引入 `tenant_id` 层。

```python
class UserMcpCredential(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'user_mcp_credentials'
    __table_args__ = (
        UniqueConstraint('user_id', 'provider', name='uq_user_mcp_user_provider'),
    )

    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'),
                     nullable=False, index=True, comment='归属用户（多用户隔离键）')
    provider = Column(String(50), nullable=False, comment='mcp registry 的 provider 名')
    auth_type = Column(String(20), nullable=False, default='oauth2',
                       comment='oauth2 / static_token（cli 型不进本表）')

    cipher_text = Column(Text, nullable=False, comment='Fernet 加密的凭据 JSON（token / key）')
    refresh_cipher = Column(Text, nullable=True, comment='Fernet 加密的 refresh_token')
    expires_at = Column(DateTime, nullable=True, comment='过期时间；空表示不过期')
    token_endpoint = Column(String(500), nullable=True,
                            comment='刷新端点；只允许 https + 白名单域名（SSRF）')
    key_version = Column(Integer, nullable=False, default=1,
                         comment='加密密钥版本，支持轮换')

    status = Column(String(20), nullable=False, default='active',
                    comment='active / expired / revoked')
    last_refreshed_at = Column(DateTime, nullable=True)
    last_error_kind = Column(String(40), nullable=True,
                             comment='对应 McpErrorKind；不存 token/明文')
```

**硬约束**：

1. `cipher_text` 解密后才是 token；本模块任何日志、异常、API 响应**不得出现明文**。
   沿用 `mcp/credentials.py` 的「绝不记录 token」纪律。
2. `user_id` 是隔离键，`family_id` **不参与**——授权是个人行为，不随家庭共享。
   这与 `UserPreference` 的选择一致（`users/models.py` 的注释已写明理由）。
3. 表里**没有 `url` 列**（继承 §8 决定）：用户不能自带 MCP 地址。
   新增服务只在 registry 里登记常量地址，避免 SSRF。
4. `token_endpoint` 若允许来自服务端元数据（DCR 场景），必须是 https 且域名在
   provider 白名单内，否则视为配置错误。

### 2.2 加密

`MCP_CREDENTIAL_KEY`（env）→ Fernet。注意 `cryptography` 目前只是 `pdm.lock` 的传递依赖，
**必须在 `pyproject.toml` 显式声明**后才能 import。
`key_version` 支持轮换：解密按行内版本取密钥，加密永远用当前版本。

### 2.3 `resolve_token` 改法

`credentials.py:82` 的 `resolve_token(provider, scope, user_id)` 保持签名不变，
只把 S5 分支从抛错改为查表：

```python
if normalized is DataScope.USER_PRIVATE:
    if not user_id:
        raise McpUserTokenMissing('缺少用户标识', provider=provider)
    cred = load_credential(user_id, provider)   # 解密 + 过期检查 + 必要时刷新
    if cred is None:
        raise McpUserTokenMissing('用户尚未连接该服务', provider=provider)
    return cred
```

**绝不回退系统 Token** 这条不变（D1 红线）。调用点无需改动。

## 3. 授权编排层（新增）

放在 `services/mcp/oauth.py`（同花顺型）。职责：

| 阶段 | 动作 |
|---|---|
| `begin(provider, user_id)` | DCR 注册（按 provider 缓存 client_id）→ 生成 PKCE verifier/challenge + state → 返回授权 URL |
| `callback(provider, state, code)` | 校验 state → code 换 token → 加密入 `user_mcp_credentials` |
| `refresh(provider, user_id)` | 过期前刷新 → 更新密文；失败转 `McpAuthError` |
| `revoke(provider, user_id)` | 调 `revocation_endpoint` + 标记本表 `revoked` |

**回调地址**：后端固定一个 `/api/mcp/oauth/<provider>/callback`，不要每个用户一个。
state 里带 user_id 与随机 nonce，落库校验，防 CSRF。

**安全**：state 一次性、5 分钟过期；PKCE verifier 存服务端 session 或加密 cookie，
不落日志；client_secret 若 DCR 返回，随凭据一起加密，不写 env。

## 4. CLI 连接层（天天基金型）

放在 `services/mcp/cli_connector.py`。职责：

- 探测 `ttskill` 是否安装（`ttskill skill list --json`）；
- 发起 `ttskill login`（子进程，**需要能打开浏览器/二维码**——见 §6 限制）；
- 调用 `ttskill invoke`，把 `skill_id` / `_skill_version` 传进去；
- 探测 `cli_login_required` → 标记为需要重新登录。

**不存 token**。表里另建一张轻量 `mcp_cli_connection(user_id, connector_type, version,
login_status, last_checked_at)` 记录状态，供管理页显示。

## 5. 连接管理页面

**前端入口**：设置页新增「数据连接」区块，列出已登记服务 + 连接状态
（`未连接 / 已连接 / 需重新授权 / 已过期`），每个服务三个动作：连接、刷新、断开。

**API 端点**（新增，需走 `check_api_conventions.py --write`）：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/mcp/connections/` | 当前用户的连接列表与状态 |
| POST | `/api/mcp/connections/<provider>/authorize/` | 发起 OAuth，返回授权 URL |
| POST | `/api/mcp/connections/<provider>/callback/` |  OAuth 回调（可 PUBLIC） |
| POST | `/api/mcp/connections/<provider>/refresh/` | 手动刷新 |
| DELETE | `/api/mcp/connections/<provider>/` | 断开/撤销 |
| POST | `/api/mcp/cli/<connector>/login/` | 拉起 CLI 登录（天天基金） |

**权限**：所有端点按 `g.current_user.id` 取用户，禁止接受 body 里的 `user_id`
（否则水平越权）。这是多用户隔离的落点。

## 6. 已知边界与必须先拍板的事

1. **CLI 扫码的宿主限制**：`ttskill login` 需要打开本机浏览器并等待扫码。
   在云服务器 / 无桌面环境的 Fund Mate 部署里这一步不可用。
   本地开发可行；生产 SaaS 形态需另做「远程扫码代理」（把二维码传给前端展示、
   轮询登录态）——这是独立工程，不在本期。
2. **SSRF 决策变更**：`mcp-integration.md` §11 写死「不允许用户自带 MCP URL」。
   本文保持这条。管理页只展示 registry 里登记的服务，不提供 URL 输入框。
   若将来要开放，需先走 `decisions.md` 记录决策 + SSRF 白名单 + 出站代理，属显式变更。
3. **mTLS 风险**：见 §1.1，首次授权后必须实测 token 是否可用于 `/mcp`。
4. **PRO 门禁**：S5 原计划与 `PRO_FEATURES` 绑定（`entitlement_check.py`）。
   本期是否付费化未定，凭据表本身不依赖门禁，可独立落地。

## 7. 分阶段施工（每阶段可独立合并/回滚）

| 阶段 | 内容 | 完成判据 |
|---|---|---|
| S5a | `user_mcp_credentials` 表 + Fernet 加密 + `resolve_token` 接表 | 用户无凭据 ⇒ `McpUserTokenMissing`；绝不回退系统 Token（变异探针） |
| S5b | 同花顺 provider + OAuth 编排（begin/callback/refresh） | 授权后 `resolve_token` 返回可用 token；`POST /mcp` 实调一次成功 |
| S5c | 连接管理 API + 前端设置页 | A 用户看不到 B 用户的连接；断开后再调用抛 `McpUserTokenMissing` |
| S5d | 天天基金 CLI 连接层 | `ttskill login` 可拉起；`cli_login_required` 能被探测并提示 |
| S5e | 付费门禁（若决定做） | 无 Pro 时连接页提示升级，凭据表不写明文 |

## 8. 与现有文档的关系

- `mcp-integration.md` §8/§9 的 S5 → 由本文展开；
- `oauth2.md` → 本文的 OAuth 编排遵循其中的 state/PKCE 约定；
- 本文不改变 `transport.py` / `base.py` / `registry.py` 的任何契约（§10 三条判据仍成立）。
