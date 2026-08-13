# 用户凭证与第三方集成规划（integrations-plan）

> 最后核实日期：2026-08-13
> 关联决策：D1（数据归属与分权）、D2（JWT 验签）、D12（user_preferences 与 AI Key 加密存储远期）
> 关联 roadmap：`P2-30`（用户偏好与 AI Key 加密存储）
> 关联 issue：见文末 §6

本文件规划「用户在前端粘贴自己的 API Key / Token，调用自己拥有的 MCP 或 Skill（含行情数据查询）」能力，并覆盖配套的**凭证加密存储**、**家庭共享模型**、**审计日志**三件套。本文档为规划基线，不含实现代码。

---

## 1. 现状盘点（2026-08-13 代码事实）

### 1.1 家庭 unit 已真实存在 ✅
- `Family` 实体 + `FamilyScopedMixin`（`backend/app/core/database.py:58-72`）提供 `family_id` 隔离键。
- 核心账本（交易/持仓/账本/组合/自选/策略标签/资产快照）均按 `family_id` 组织，查询经 `get_family_id()` 过滤。
- `User` 表含 `family_id` + `role`（admin/member/viewer），Supabase JWT（ES256+JWKS）真实多用户鉴权已落地（P1-22 完成），`P1-23 多用户家庭隔离地基` 进行中。

### 1.2 系统默认 MCP 通道（且慢温度计）已硬编码，本次**不改造** ✅
- `backend/app/services/thermometer/fetchers.py` 的 `QiemanFetcher` 走 MCP Streamable HTTP 拉取市场温度，key 读环境变量 `QIEMAN_API_KEY`（`constants.py:36 QIEMAN_MCP_URL`）。
- 这是**产品内置的系统能力**，由开发者（我们）提供，与用户的个人凭证是**两回事，必须隔离、互不污染**。
- 关键约束（用户裁决）：开发者本人配置自己的 key 时，应和系统默认通道**表现一致、可用**——即「系统默认 key（env）」与「用户 key（家庭凭证）」走**同一套调用逻辑**，仅来源不同。不能出现"我自己写的产品我自己用不了"。

### 1.3 审计日志：零基础 ❌
- 全仓库无 `AuditLog` / `OperationLog` / `request_id` / access log。仅有 loguru 应用调试日志 + `TimestampMixin`（created_at/updated_at，非操作审计）。
- 这是要从零建设的部分。

### 1.4 通用 MCP/Skill 调用层：零 ❌
- 无 `MCPClient` / `tool_call` 通用封装，仅 `QiemanFetcher` 一处硬编码实现。用户自有 MCP/Skill 无接入路径。

### 1.5 既定决策约束（来自 decisions.md）
- **D12（2026-08-08）**：`user_preferences` 与 AI Key 加密存储**不在当时实现**，理由是"避免过早引入加密依赖与密钥管理复杂度"。本次规划须遵守其精神：**加密方案从轻量起步（信封加密 + MASTER_KEY env），不强行上 KMS**。
- **D1（2026-08-07）**：核心账本按 `family_id` 共享层；`user_preferences` 等**个人数据按 `user_id` 私有层**。⚠️ 这和用户"key 家庭共享"的诉求存在张力，见 §3.2 待裁决点。

---

## 2. 目标与边界

### 2.1 要做的
1. 用户在前端粘贴自己的 API Key / Token（如自有 MCP server、第三方行情 Skill 的 key）。
2. key **加密存储**，前端可正常查看"支持的 skill / MCP 列表"与凭证状态（掩码展示）。
3. 用户调用**自己的** MCP / Skill 查询行情数据，走后端代理转发（后端只做密钥托管 + 转发，不持有数据）。
4. 调用与凭证操作产生**防抵赖审计日志**（L1 起步，计费点升 L2）。
5. 家庭共享：同一家庭的成员可共用一套凭证（若裁决采用家庭维度）。

### 2.2 不做的（本次边界）
- **不动系统默认且慢 MCP 通道**（硬编码 env key 保持原样），只保证它与用户凭证隔离、且共用同一调用逻辑。
- 不引入重型密钥管理（KMS / HSM）作为 MVP 必选项。
- 不实现按量计费（除非产品明确，见 §4 可选）。

---

## 3. 数据模型规划

### 3.1 凭证表 `Credential`
建议新增 domain `backend/app/domains/credentials/`：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | PK | |
| family_id / user_id | FK | **归属维度，见 §3.2 待裁决** |
| provider | str | 标识来源（如 `qieman` / `custom_mcp` / `some_skill`） |
| name | str | 用户自定义别名（"我的且慢key"） |
| ciphertext | blob/text | AES-256-GCM 密文（**不存明文**） |
| iv | blob | 随机向量 |
| created_by_user_id | FK | 操作人（审计用） |
| is_active | bool | 软禁用，不硬删（配合审计 append-only） |
| created_at / updated_at | ts | TimestampMixin |

### 3.2 ⚠️ 待裁决点：凭证归属维度（family vs user）
- **用户诉求**：家庭共享更方便（配偶自动可用）。
- **D1 既定**：个人数据按 `user_id` 私有。
- **建议裁决**：凭证采用 `family_id` 归属（与核心账本一致，复用 `FamilyScopedMixin`，消灭"个人/家庭"代码分支），单人用户 = 仅 1 成员的 family（系统自动建）。若需"某人藏私房 key 不让配偶看"的强需求，再补 `user_id` 私有层——目前无此需求，不做。
- **影响**：此裁决决定 §1.5 D1 是否需修订。建议在 issue 中由用户拍板。

### 3.3 审计表 `AuditLog`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | PK | |
| family_id | FK | 作用域（沿用现有隔离习惯） |
| user_id | FK | **实际操作人**（actor，永远记真人，不记家庭） |
| action | str | `CREDENTIAL_CREATE` / `CREDENTIAL_VIEW` / `CREDENTIAL_USE` / `MCP_CALL` / `SKILL_CALL` / `CREDENTIAL_DELETE` |
| resource | str | 客体（如 `credential:12` / `provider:qieman`） |
| detail | json | 上下文（不含明文 key；key 仅记 id 或哈希引用） |
| request_id | str | 串起 loguru 链路 |
| prev_hash / cur_hash | str | **L2 哈希链**（仅计费节点启用） |
| ts | ts | |

---

## 4. 功能拆解：必选 vs 可选

### 4.1 必选（MVP，构成 P2 落地）
| 项 | 说明 | 依赖 |
|----|------|------|
| B1 凭证加密存储 | AES-256-GCM 信封加密，MASTER_KEY 取 env；入库密文，查回明文仅经解密接口；前端掩码展示 | — |
| B2 凭证 CRUD + 家庭作用域 | 复用 `get_family_id()` / `require_roles()`；admin/member 可见可用，admin 可删 | §3.2 裁决 |
| B3 通用 MCP 调用层 `GenericMCPClient` | `list_tools()` / `call_tool()`，按 provider 配置 auth header；把 `QiemanFetcher` 迁入作为首个 provider 验证通用性（key 来源从 env 改为解密取出） | B1 |
| B4 系统/用户隔离 | 系统默认且慢通道（env key）与用户凭证（family 凭证）走同一调用逻辑、数据面/权限面分离，互不污染 | B3 |
| B5 审计日志 L1 | `@audit` 装饰器声明式落库，覆盖凭证增删查 + MCP/Skill 调用；隐私字段不落明文 | — |
| B6 前端：凭证管理页 + skill/MCP 列表 | 粘贴 key、查看掩码、展示支持的 skill/tool 列表 | B1-B3 |

### 4.2 可选（第二阶段 / 视产品而定）
| 项 | 说明 | 触发条件 |
|----|------|----------|
| O1 审计 L2 哈希链 | 防内部篡改，定时 `recompute_chain()` 校验断链 | 仅当**按量计费**时需要（见 O2） |
| O2 按量计费 | 调用消耗额度/扣费 | 产品明确商业模式后 |
| O3 异步审计落库 | Celery/Redis Stream，不拖慢主流程 | 高并发或 O1/O2 上线后 |
| O4 KMS / 信封密钥托管 | 升级 MASTER_KEY 管理 | 生产安全合规要求提升 |
| O5 多 auth 类型适配 | OAuth / 自定义 header 等非 Bearer 形态 | 用户接入的 MCP 出现非 Bearer 鉴权 |
| O6 凭证额度共享提示 | 家庭共用一 key 的额度池耗尽风险提示 | O2 计费上线后 |

---

## 5. 审计日志接入方式（呼应"不想一次次调用"）

- **装饰器 `@audit(action=...)`** 挂在视图函数上，自动抓 `get_family_id()` / `g.current_user` / 入参 / 结果，业务函数体零审计代码。
- **`after_request` 钩子**统一发 `request_id`，串起现有 loguru 链路，使操作日志与审计日志可关联。
- 操作日志（排障）与审计日志（追责）**同源不同处理**：同一次请求既产生排障用操作日志，也产生举证用审计记录，靠 `request_id` 关联，不重复写业务代码。
- 引用澄清：操作日志=给机器/问题看（排障）；审计日志=给人/责任看（防抵赖）。本规划审计日志仅覆盖高责任动作（B5），普通接口维持现有 loguru，不强行全量审计。

---

## 6. issue 与 roadmap 反链

- 新建 issue 跟踪本规划落地（建议定位 **P2**，优先级 Ⅱ 重要不紧急；原 `P2-30` 仅登记 AI Key 加密，本 issue 将其扩展为「家庭共享凭证 + 通用 MCP/Skill 调用 + 审计」并提升重要度）。
- `roadmap.md` 的 `P2-30` 改写为扩展版，反链本 issue 与本文件。
- 前置依赖：`P1-23 多用户家庭隔离地基`（进行中）为凭证挂 family_id 的地基。

---

## 7. 落地顺序建议

1. 审计地基（B5 表 + 装饰器 + request_id）—— 其他依赖它，当前为零。
2. 凭证加密存储 + 家庭作用域 CRUD（B1、B2）。
3. 通用 MCP 调用层，迁移且慢验证（B3、B4）。
4. 前端凭证管理 + skill 列表（B6）。
5. （可选）O1-O6 视产品推进。
