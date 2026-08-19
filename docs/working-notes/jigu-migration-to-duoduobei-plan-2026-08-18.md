# 极谷（jigu）新旧站 Supabase 数据迁移与 SSO 打通规划（2026-08-18）

> 性质：内部规划备忘（`docs/working-notes/` 屏蔽出构建，不对外）。
> 规划人：研究主导（基于既有文档 + 代码核对 + Supabase 官方最佳实践调研）。
> 关联：`docs/spec/site-architecture-and-traffic-routing.md`（权威 HOS）§4.1 / §5；`docs/working-notes/jigu-migration-plan-2026-08-11.md`（旧方案，场景不同，见 §一）。

## 执行摘要

你记忆里"找不到的文档"就是 `docs/spec/site-architecture-and-traffic-routing.md`，其第五章「极谷新旧迁移策略」已经把策略定好了：新极谷指向主站同一个 Supabase project，旧极谷发通知引导用户用同邮箱重注册、后台脚本按 `user_id` 复制业务数据，旧站保留只读窗口后 301。本次需求（jigu.masantu.com → jigu.duoduobei.com，都是 Supabase）完全落在该策略内，因此不需要重新设计，只需落地执行。

最关键的一点：你 8-11 那版 `jigu-migration-plan` 是"jigu → fundmate SQLite"的迁移，涉及精度换算、去重、字段映射等大量复杂度；而**本次是 jigu → jigu（同构 Supabase）**，业务数据就是 `user_configs.data` 这一个 JSON blob，因此最稳的无损迁移就是**原样搬 JSON、只换 `user_id`**，零字段转换、零精度风险，比旧方案简单一个量级。

时间上：若 jigu.masantu.com 基本是你自己单用户，工程约 2.5–3 天、你本人重注册 10 分钟，约 1 周内可下线旧站；若旧站有多个真实用户，工程约 1 周，但日历时间取决于用户重注册窗口，建议保留旧站只读 2–4 周再 301。你担心的"机构与主站 SSO 打通"由"共享 Supabase project + 父域 cookie"免费解决，真正要写代码的是把 jigu 的会话存储从 localStorage 改为 `.duoduobei.com` 父域 cookie（约 2.5 天）。

## 一、先定位你"找不到的那份文档"

仓库里有两份相关文档，容易混：

- `docs/spec/site-architecture-and-traffic-routing.md`（权威 HOS）—— 这是你记忆里那份。第四章 §4.1 已定「极谷 ↔ app 必选 SSO = 同 Supabase project + 父域 cookie」，第五章 §5 专门写「极谷新旧迁移策略」，正是本次场景。
- `docs/working-notes/jigu-migration-plan-2026-08-11.md`（旧方案，场景不同）—— 它要解决的是把极谷用户数据迁进 fundmate 的 SQLite（持仓/自选/标签/分组的字段映射 + Money 精度换算 + 去重 bug 修复）。**本次需求不是这个**，不要照搬它的 D1–D5 决策和字段映射表，否则会把简单问题复杂化。

结论：以 `site-architecture-and-traffic-routing.md` §5 为权威依据，本规划是其执行化拆解。

## 二、现状核对（基于代码与文档）

核对了 `D:\codes\jigu` 与 `D:\codes\fundmate` 的现状，关键事实如下：

- jigu 的业务数据全在 Supabase `user_configs` 表，每行一个用户，`data` 字段是 json，存的是该用户全部本地数据的镜像（holdings / favorites / groups / tags / transactions 等，与 8-11 文档 §1.1 的 key 清单一致）。`user_id` 关联 `auth.users`。
- jigu 连 Supabase 是**纯 env 驱动**：`app/lib/supabase.js` 只读 `NEXT_PUBLIC_SUPABASE_URL` 和 `NEXT_PUBLIC_SUPABASE_ANON_KEY`，无任何硬编码 project URL。架构文档说的"改 env 不改代码"成立——把 jigu.duoduobei.com 指向主站 project 只需改部署环境变量。
- 新极谷的建表/RLS/函数脚本已就绪：`D:\codes\jigu\doc\supabase.sql`（含 `user_configs` 表、`update_user_config_full/partial`、`get_ytd_percentile`、`ocr_daily_usage` 限流等）。只需把它应用到**主站 Supabase project**（与 fundmate 现有表并存，是纯增量，不冲突）。
- 主站架构已明确：`jigu.duoduobei.com` 与 `app.duoduobei.com` 指向同一 project，用户池天然共享；SSO 机制是 `@supabase/ssr` 把 session 存到 `.duoduobei.com` 父域 cookie。但 jigu 当前是纯静态导出 SPA（`output: export`，无 server runtime），用的是 `@supabase/supabase-js` 的 localStorage 持久化，并非 cookie——这是后期 SSO 要补的真实代码改动点。

## 三、关键结论：本次迁移比旧方案简单得多

旧方案（jigu → fundmate SQLite）之所以复杂，是因为要跨存储形态做 ETL：JSON → 关系表、元/份浮点 → 整数分/0.0001 份、还要修极谷"分组汇总重复"的 bug。本次 jigu → jigu 是**同构搬迁**：

- 源与目标都是 `user_configs.data` 这一个 JSON blob，内容语义完全一致，直接 `INSERT` 即可，**无损且无需任何字段转换**。
- 不需要走 fundmate 的 `Money` 精度换算（那是 fundmate 内部契约，与极谷内部存储格式无关）。
- 不需要去重（极谷的重复 bug 是它前端汇总逻辑的问题，搬 JSON 不会引入新 bug；是否在新站修那是 jigu 自身的事，与迁移无关）。
- 唯一要做的是把每行的 `user_id` 从旧 project 的 UUID 换成新 project 中对应同一邮箱用户的 UUID。

所以"快速 + 无损"的核心就是：写一个服务端脚本，用旧 project 的 `service_role` key 读出 `auth.users`（拿 email）和 `user_configs`（拿 data），按 email 映射到新 project 的 `user_id`，整行 `data` 写入新 project。脚本跑完，数据即完整转移。

## 四、迁移方案（Phase 1：快速 + 无损）

### P1.1 新站指向主站 project（约 0.5 天，纯运维）
1. 在主站 Supabase project 执行 `D:\codes\jigu\doc\supabase.sql`，建立 `user_configs` 等表 + RLS + 函数（增量，与 fundmate 表无冲突）。
2. 部署 jigu 到 EdgeOne Pages，绑定 `jigu.duoduobei.com`，环境变量 `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` 填**主站 project** 的值（不改代码）。
3. 在 Supabase Auth 的 Redirect URLs 登记 `https://jigu.duoduobei.com/**`（GitHub OAuth 单 App 方案见 §五）。

### P1.2 迁移脚本（约 1–1.5 天）
写一个 Node/Python 服务端脚本（**只用 service_role key，绝不进前端/仓库**），逻辑：
1. 用旧 project 的 `auth.admin.listUsers()` 分页遍历全部用户（默认每页 50，需 `perPage` 翻页），收集 `old_user_id → lower(email)`。
2. 用新 project 的 `auth.admin.listUsers()` 同样收集 `email → new_user_id`；对新 project 里**尚未注册**的邮箱，用 `admin.createUser`（或发魔术链接邀请）先建账号再回填。
3. 读旧 project `user_configs` 全量，按 email 映射，把 `data` 原样 `upsert` 进新 project（必要时先 `update_user_config_full` 保持设备冲突语义一致）。
4. 迁移前统一 `lower(email)` 归一并去重；先 `--dry-run`（只 count 比对、不写库），确认行数一致后再正式跑。

> 关于 auth.users 的两种处理（需你拍板，本规划默认按架构文档推荐做法）：
> - **方案 A（架构文档推荐，不合并密码）**：用户在旧站用同邮箱在新站重注册/魔术链接登录，产生全新 UUID；脚本只搬业务数据。优点：干净、无密码哈希冲突噩梦；缺点：用户需重设密码/重登一次。
> - **方案 B（Supabase 官方整库迁移 auth schema）**：把旧 project 的 `auth` schema（含密码哈希）整体迁入新 project，并**把新 project 的 JWT Secret 改成与旧 project 相同**，用户无需重设密码。优点：用户无感；缺点：需统一 JWT Secret（会使 anon/service_role key 重生），且若两 project 都已有活跃用户会触发 UUID 主键冲突，故仅当新 project 是全新空库时稳妥。
> 考虑到主站 project 已有 fundmate 活跃用户，方案 B 在此不适用，**推荐方案 A**。

### P1.3 小范围验证（约 0.5 天）
挑 1–2 个账号（含你自己的）先 dry-run 再正式迁移，登录新站核对：持仓/自选/分组/标签完整、收益历史（`fundDailyEarnings` 等运行时数据不迁，由新站重算，符合预期）。

### P1.4 通知 + 只读窗口 + 301（运维约 0.5 天，窗口期人为决定）
1. 旧站发站内/邮件通知：引导用户去 `jigu.duoduobei.com` 用同邮箱注册/魔术链接登录，数据已为其备好。
2. 旧站切只读（停止写入、保留查询）作为过渡窗口；窗口结束（用户基本迁完）后 301 到新极谷或主站对应入口。
3. 旧 project 保留备份不立即删，便于回滚。

## 五、SSO 打通方案（Phase 2：机构与主站打通，后期）

"机构与主站 SSO 打通"本质是让 jigu 用户并入主站 Supabase 用户池并实现跨子域自动登录。由于 Phase 1 已让 jigu.duoduobei.com 共用主站 project，**用户池天然共享，SSO 的"身份互通"已免费获得**；真正要补的是"登录一个、全站登录"的会话共享，以及补齐 OAuth 配置。

- **P2.1 父域 cookie 会话（约 1 天，真实代码改动）**：jigu 当前用 `@supabase/supabase-js` 的 `persistSession` + localStorage；纯静态导出无 server runtime，不能用 `@supabase/ssr`。改为自定义 storage 适配器，把 session 写到 `document.cookie`（`domain=.duoduobei.com; path=/; SameSite=None; Secure`），初始化时 `createClient(URL, anonKey, { auth: { persistSession: true, storage: cookieStorage } })`。两个子域读同一父域 cookie 即实现跨子域自动登录。注意：HTTPS 强制（Secure 必需）、cookie 4KB 上限（session 含 access/refresh JWT，必要时拆分）、XSS 风险（非 HttpOnly cookie 可被 JS 读，须做输出转义 + CSP，应用层用 `getUser()` 向服务端校验会话而非信任 `getSession()`）。
- **P2.2 GitHub OAuth 单 App（约 0.5 天）**：只需一个 GitHub OAuth App，回调填 Supabase 的 `auth/v1/callback`；在 Supabase Redirect URLs 同时登记 `https://app.duoduobei.com/**` 与 `https://jigu.duoduobei.com/**`（支持通配符）。该说法经验证准确。
- **P2.3 跨子域联调（约 0.5 天）**：在 app 登录后访问 jigu 应已登录；反向同理；登出双向生效。
- **P2.4 安全加固（约 0.5 天）**：`getUser()` 服务端校验、CSP、cookie 安全属性复核。

> 说明：本文把"机构与主站打通"理解为"jigu 用户并入主站 Supabase 用户池 + 跨子域 SSO"，即架构文档 §4.1 已定方案。若你指的是其它含义（例如把 AMAC 机构实体/机构账户作为独立主体接入主站权限体系），请告知，我会单列方案。

## 六、时间评估

直接回答"多久能完成"：

- **单用户场景（旧站基本是你自己）**：P1.1–P1.3 约 2.5–3 天工程，你本人用同邮箱重注册约 10 分钟，脚本跑完即无损转移；若无需等他人，约 1 周内可 301 下线旧站。SSO（P2）可并行或随后做，约 2.5 天。
- **多用户场景**：工程总量约 1 周（P1 约 3 天 + P2 约 2.5 天）；但日历时间由"用户重注册窗口"主导，建议旧站保留只读 2–4 周再 301。窗口期内你这边工程已完工，只是等用户迁完。

| 阶段 | 工作项 | 工期（人天） | 是否阻塞日历 |
|---|---|---|---|
| P1.1 | 新站建表 + 部署 + 指向主 project | 0.5 | 否 |
| P1.2 | 迁移脚本（listUsers + email 映射 + upsert + dry-run） | 1–1.5 | 否 |
| P1.3 | 小范围验证 | 0.5 | 否 |
| P1.4 | 通知 + 只读窗口 + 301 | 0.5（运维） | **是（窗口期人为决定）** |
| P2.1 | 父域 cookie 会话适配器 | 1 | 否 |
| P2.2 | GitHub OAuth 单 App + 双 Redirect | 0.5 | 否 |
| P2.3 | 跨子域联调 | 0.5 | 否 |
| P2.4 | 安全加固（getUser/CSP） | 0.5 | 否 |
| **合计** | | **约 5–5.5** | 窗口期另计 |

## 七、风险与回滚

- **email 映射失败**：大小写/未确认邮箱导致映射不到新 user_id → 迁移前统一 `lower(email)` 去重；未注册用户先 `admin.createUser` 再回填。
- **误迁移 / 覆盖**：脚本默认 `--dry-run` 只比对行数；正式跑前备份旧 project；新 project 用 `upsert` 幂等，可重复跑。
- **会话安全**：父域 cookie 必须 `SameSite=None; Secure` + HTTPS；非 HttpOnly 有 XSS 泄露 refresh token 风险，须 CSP + `getUser()` 服务端校验。
- **共享 JWT Secret 冲突（仅方案 B）**：主站已有活跃用户，不推荐整库合并 auth；坚持方案 A 规避。
- **旧站数据回滚**：旧 project 保留不删，旧站只读期可随时恢复写入。

## 八、本规划所依据的假设（陈述，非提问）

1. jigu.duoduobei.com 将指向**主站同一个 Supabase project**（依架构文档 §4.1/§5）。
2. "机构与主站 SSO 打通" = jigu 用户并入主站用户池 + 跨子域自动登录（依架构文档 §4.1）。
3. 迁移采用"原样搬 `user_configs.data` JSON、按 email 重映射 user_id"（无损、不引旧方案的精度/去重复杂度）。
4. auth.users 采用方案 A（用户同邮箱重注册，不硬合并密码）；若需保留密码请改方案 B 但仅在主 project 为空库时稳妥。
5. jigu.masantu.com 用户规模未知：单用户则近即时完成，多用户则需 2–4 周窗口——请按实际用户数套用 §六。
6. **数据归属分两阶段（用户 2026-08-18 明确）**：阶段一仅把 JSON 整包迁到主 project（jigu 立即可用）；阶段二再把 JSON 解析进 fundmate 结构化表，届时 fundmate 的丰富库为权威源、jigu 不再读 JSON。即本规划 = 阶段一，8-11 旧方案 = 阶段二，二者先后衔接而非二选一。

## 九、用户澄清与 FAQ（2026-08-18 补充）

**Q1：用户能否无感知、直接重新登录？**
分两层。已拥有主站（app.duoduobei.com）账号的用户，靠 `.duoduobei.com` 父域 cookie，访问 jigu 自动登录——真·无感知。仅用过旧 jigu、主站无账号的用户，需在新网址（jigu.duoduobei.com）至少认证一次；最省事是用**魔法链接（passwordless 邮件 OTP）**：输邮箱 → 点邮件链接 → 主 project 自动建号并建立会话，数据早已在库等他，全程无需设密码、基本一键。故"无感知"对纯 jigu 老用户是"一次点击"，非完全零动作。

**Q2：若用户先在新站注册了，数据如何迁移？**
迁移脚本按 email 映射 + `upsert`（幂等），与注册先后无关。脚本跑时，对新 project 内"已存在该邮箱用户"直接定位其新 `user_id` 写入 JSON；"尚未注册"才先 `admin.createUser` 再回填。故用户抢先注册不冲突，脚本只是补数据。阶段一以旧站 JSON 为准（覆盖即可）；阶段二 structured 落地时再单独评估合并策略（避免覆盖用户已手动录入的新数据）。

**Q3：密码是否变化、是否用新密码？**
是。方案 A 不硬合并 `auth.users`，旧 masantu project 的密码哈希不带入主 project；用户在新 project 设的新密码（或魔法链接根本不设密码）即今后密码，旧密码随旧 project 退役作废。仅方案 B（整库合并 auth + 统一 JWT Secret）可保留旧密码，但主 project 已有 fundmate 活跃用户、UUID 主键会冲突，故不可用。结论：用新密码，属方案 A 固有取舍。

## 十、2-3 用户场景：阶段一执行清单与所需信息（2026-08-18 补充）

用户确认：A 股极谷仅 2–3 人使用，目标尽快退役旧站、尽快上线主线 APP 让用户迁到 `app.duoduobei.com`。在此规模下，阶段一应走**最稳路径 = JSON 原样落到主 project（零转换、零损耗）**，结构化入 fundmate 表（8-11 旧方案）作为阶段二在 APP 就绪后做。

### 10.1 阶段一执行步骤（仅 2–3 人）
1. **主 project 建表**：在主站 Supabase project 执行 `D:\codes\jigu\doc\supabase.sql`（增量，与 fundmate 表不冲突）—— 一次性。
2. **搬运脚本**：用旧 masantu project 的 `service_role` 读 `auth.users`（拿 email）+ `user_configs`（拿 data）；用主 project 的 `service_role` 按 email 映射新 `user_id`，把 `data` 原样 `upsert` 进主 project 的 `user_configs`。`--dry-run` 先比对行数，再正式跑。
3. **上线新极谷（过渡）**：部署 jigu 到 EdgeOne Pages 绑 `jigu.duoduobei.com`，env 填**主 project** 的 URL/anon key（改 env 不改代码）。旧 masantu 切只读 → 301。
4. **用户迁移**：2–3 人去 `jigu.duoduobei.com` 用同邮箱**魔法链接（passwordless OTP）**一键登录（数据已在库）；若已有主站账号则靠 `.duoduobei.com` 父域 cookie 自动登录。
5. **阶段二（APP 就绪后）**：把 JSON 解析进 fundmate SQLite 结构化表（8-11 方案），引导用户去 `app.duoduobei.com`，jigu 转只读/301 到 app。

> 为什么不直接跳过 jigu.duoduobei.com 直奔 APP：阶段一是"零转换字节拷贝"，几乎不可能丢/错数据；结构化 ETL 需 APP 的导入链路就绪且要逐字段映射（精度/去重），风险更高。2–3 人下两跳总成本仍极低，但第一跳先把数据安全带到主生态、旧站即可下线，符合"尽快退役"。若你确认 APP 导入链路已就绪且想省一跳，可把 10.1.2 的落点直接改为 fundmate SQLite（需追加 §10.2 之外的"fundmate invest.db 写权限 + user 映射"信息）。

### 10.2 需要你提供的信息（实现搬家）

**A. 旧 masantu project（只读源）**
- 项目 URL（形如 `https://zhfiyyupbegeyvnigenk.supabase.co`）
- `service_role` key（**机密**，服务端读 `auth.users` 必需；anon key 列不出用户）—— 不进仓库，走本地环境变量/未跟踪文件。

**B. 主站 Supabase project（写入目标）**
- 项目 URL
- `service_role` key（写 `user_configs` + 必要时 `admin.createUser` 建 2–3 个账号）
- anon key（给 `jigu.duoduobei.com` 部署 env）

**C. 用户邮箱清单**：确认就是这 2–3 个（脚本可从旧 project 枚举，但需你核对无遗漏/无测试账号混入）。

**D. `jigu.duoduobei.com` 部署落点**：EdgeOne Pages 项目是否已建、env 变量注入方式（我交付 env 值由你填，或你给我部署权限我配）。

**E. 决策确认**：保留 `jigu.duoduobei.com` 作过渡（推荐，零代码）还是跳过直奔 APP（需 APP 导入链路就绪）。

> 安全红线：`service_role` key 拥有绕过 RLS 的完全权限，绝对禁止提交仓库/前端；脚本从本地 `.env`（gitignore）或你本机环境变量读取，跑完我不留副本。旧 project 迁移前不删、保留备份。

## 十一、References

1. [极谷新旧迁移策略与 SSO（权威 HOS）— site-architecture-and-traffic-routing.md](https://github.com/imoyao/fundmate/blob/main/docs/spec/site-architecture-and-traffic-routing.md)
2. [旧方案（场景不同，勿照搬）— jigu-migration-plan-2026-08-11.md](https://github.com/imoyao/fundmate/blob/main/docs/working-notes/jigu-migration-plan-2026-08-11.md)
3. [jigu Supabase 建表/函数脚本 — D:\codes\jigu\doc\supabase.sql](https://github.com/imoyao/jigu/blob/main/doc/supabase.sql)
4. [jigu Supabase 客户端（纯 env 驱动）— D:\codes\jigu\app\lib\supabase.js](https://github.com/imoyao/jigu/blob/main/app/lib/supabase.js)
5. [Supabase – Migrating Auth Users between Projects](https://supabase.com/docs/guides/troubleshooting/migrating-auth-users-between-projects)
6. [Supabase – auth.admin.listUsers (JS)](https://supabase.com/docs/reference/javascript/auth-admin-listusers)
7. [Supabase – Client Initialization (persistSession / storage)](https://supabase.com/docs/reference/javascript/auth-init)
8. [Supabase – Redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls)
9. [Microsoft Learn – SameSite=None 需 Secure](https://learn.microsoft.com/zh-cn/aspnet/samesite/system-web-samesite)
