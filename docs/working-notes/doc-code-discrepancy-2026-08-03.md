# 文档与代码误差追踪（会议纪要）（2026-08-03）

> 性质：内部备忘（`docs/working-notes/` 屏蔽出构建，不对外）。
> 建立：2026-08-03。用途：记录 `docs/` 与实际代码的偏差，便于后续修正与追踪。
> 维护方式：发现一条加一条；修正后在「状态」列标注已解决。

## 一、已发现偏差

| # | 偏差点 | 文档说法 | 代码实际 | 状态 |
|---|--------|----------|----------|------|
| 1 | 鉴权实现 | `docs/dev/flask-auth.md` 称已实现 Flask-praetorian 登录/找回/重置 | `main.py` 未注册任何 auth 蓝图；`ledgers/views.py` 等用硬编码常量 `CURRENT_USER_ID` | **已解决**（2026-10-17 核实 + 修文）：现为 Supabase JWT 验签 + 白名单中间件（`backend/app/core/auth.py:39-65,236`），`main.py:26` 注册 `auth_bp`（`domains/auth/views.py`）；`flask-auth.md` 已加「历史留档」状态说明并把「已实现 praetorian」标注为 V1 记录 |
| 2 | 鉴权方案命名 | 文档只提 praetorian/JWT | 用户口述 login「借助 Subversion」实为 **Supabase**（`frontend/package.json` 含 `@supabase/supabase-js`） | **已解决**（2026-10-17 核实）：`frontend/package.json:58-59`（`@supabase/ssr` / `@supabase/supabase-js`），docs 内 Supabase 表述已统一（如 `docs/dev/db-choice.md:6`），全仓无 Subversion 残留 |
| 3 | 目录结构 | `docs/features/overview.md` 引用 `backend/app/models/transaction.py`、`account.py`、`fund.py` | 实际已重构到 `backend/app/domains/*/models.py` | **已解决**（2026-10-17 核实，此前已改）：`docs/features/overview.md:14,18,19` 已指向 `backend/app/domains/{funds,accounts,transactions}/models.py`；docs 内无 `app/models/{transaction,account,fund}` 残留 |
| 4 | 启动/建表方式 | README 用 `flask db migrate/upgrade`（flask-migrate） | `main.py` 用 `Base.metadata.create_all`（无迁移） | **已解决**（2026-10-17 核实 + 修文）：根 `README.md` 已走 PDM（无 migrate 字样）；`backend/README.md` 仍留模板旧命令，本次加「已过时」对照横幅；`main.py:152` 调 `init_db()` → `core/database.py:483,506` `create_all` |
| 5 | 依赖管理 | `docs/dev/index.md` 用 `requirements/dev.txt` + pip-compile-multi | 仓库实际为 `pyproject.toml` + pdm（`pdm.lock`） | **已解决**（2026-10-17 修文）：`docs/dev/index.md` 的后端环境 / 建表 / 更新数据三段改写为 PDM + `create_all` + `pdm run sync`；仓库无 `requirements/` 目录 |
| 6 | 多币种建模 | SPEC(overview) 称 `positions` 含 `currency` | `transactions/models.py` 未见 currency 列（positions 模型未读，待核对） | **已核实：文档正确，无需改**（2026-10-17）：`backend/app/domains/positions/models.py:56` 确有 `currency`（default `'CNY'`），且序列化读者在 `positions/schemas.py:50,86,129`；`transactions` 无 currency 列属预期（金额/价格均为整数分、无逐行币种） |
| 7 | 启动依赖风险 | 文档未列为 blocker | `main.py` 顶部 `import xalpha`（gitee 源），依赖 akshare/playwright；本地无网或安装失败会直接起不来 | **已解决**（2026-10-17 核实）：`main.py` 顶部已无 `import xalpha`，改为 `services/adapters/xalpha_adapter.py:55-59` 首次调用时惰性导入（注释写明原先启动期 import 约 1.4s），启动期可运行性风险不再成立，故不另补风险说明 |
| 8 | 命名 | 内部名「叽咕」、产品名「多多贝」、前端包名 `duoduobei`、README 称 "FMP/showbuy" | 对外命名不统一 | **已解决**（2026-10-17 核实）：根 `README.md` / `AGENTS.md` 统一为「多多贝」，`showbuy` 仅存于 `backend/pyproject.toml:2` 历史项目名且已在 AGENTS 登记；`backend/README.md` 的 `FMP` 标题随第 4 条横幅一并说明 |
| 9 | 前端模板基线 | docs 未说明 | 实际基于 **pure-admin-thin**（非完整 pure-admin） | **已澄清**（2026-10-17 核实，无需动作）：`docs/spec/architecture.md:27`、`docs/spec/frontend-naming.md:20` 均已写明 pure-admin-thin 骨架 |

## 二、决策记录（本会话）

- **鉴权方向**：用户要求单用户→家庭成员多用户，且拒绝写死变量。建议继续用 **Supabase Auth** + Flask 侧薄 JWT 校验中间件（替换 `CURRENT_USER_ID`），不在后端自造 JWT。
- **裁剪范围收窄**：保留 error/404 与「付费拦截」所需能力；仅删除 RBAC 用户/角色**管理后台页**与权限演示页（Supabase 控制台已管）。
- **优先总纲**：先定 landing 配置 + 品牌故事 + 产品设计故事 三份文档，作为 UI/规划的唯一真相源，避免返工。

## 三、待办（owner / 期限）

- [x] 统一鉴权方案（Supabase vs praetorian）并修正 `flask-auth.md` — owner: 你 — 接身份前（2026-10-17：Supabase Auth 已落地，`flask-auth.md` 已标注为历史留档）
- [x] 同步 docs 路径到 `domains/` 结构 — owner: 你（2026-10-17：`docs/features/overview.md` 已指向 domains，`docs/dev/index.md` 结构描述同批修正）
- [x] 统一依赖/启动方式（pdm vs requirements，create_all vs migrate）— owner: 你（2026-10-17：`docs/dev/index.md` 改 PDM；`backend/README.md` 加过时横幅）
- [x] 确认多币种建模位置（positions.currency?）— owner: 你（2026-10-17：`positions/models.py:56` 有 currency；transactions 无属预期）
- [x] 将 xalpha/akshare 启动依赖记录为「可运行性风险」— owner: 你（2026-10-17：启动期 import 已改惰性，风险不再成立，无需记录）
- [x] 对外命名统一（叽咕/多多贝/duobeibao/FMP）— owner: 你
