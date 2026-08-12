# 交易人格测试 H5 小游戏：落地技术方案与排期评估

> 日期：2026-08-10
> 状态：规划文档（未实施）
> 权威来源：`C:\Users\imoyao\Downloads\投资人格测试设计_2026-08-10-11-41-07.json`（DeepSeek 讨论链导出，99 条消息）
> 代码实况：2026-08-10 三路探索（landing 配置 / 前端投资概览 / 后端数据模型）核实

---

## 1. 背景与产品定位

「多多贝」投资产品以海洋投资生态为隐喻，核心是**投资认知闭环**：人格测试（自报）→ 交易复盘（实测）→ 对比打脸（闭环）。

- **盲测 H5 = 自报钩子（获客）**：参考同花顺 A 股历史盲测，用原创净室题库测用户"自报"的投资人格，结果页留资（微信私域）。
- **投资账本 = 价值中枢（复盘）**：真实交易数据算出"实测"行为签名，与自报对比，形成认知闭环。
- **一台引擎、两层表面、一个闭环**：行为签名引擎（五维）→ 表面 A（人格测试/自报）→ 表面 B（交易复盘/实测）→ 闭环（自报 vs 实测对比）。

## 2. 讨论链共识摘要（已定稿，勿再推翻）

| 主题 | 共识 |
|---|---|
| 题库 | 原创净室题库（不抄同花顺）；7 关脱敏验证切片（Q0 定位层 2 题不计分 + 4 通用 + 3 分支）；必须脱敏（无点位/日期/代码） |
| 评分 | 五维体系：出击/纪律/专注/切换/逆向；多维增量制评分密钥；动态 min-max 归一化；raw_scores 落库供校准 |
| 分层 | 题库池 JSON 配置化（lite/standard/deep 组卷模板）；三层画像 T1 小白/退休、T2 跟风者、T3 老司机（T3 核心目标） |
| 真实数据映射 | 5 个行为因子：前 3 大持仓占比→出击、平均持仓时长→专注、年化换手率→纪律、跨板块切换次数→切换、暴跌日>3% 净买入→逆向；与盲测共用同一雷达引擎/归一化 |
| 数据同源 | H5 前端解耦独立 HTML；数据入库 Supabase `submissions` 表（`source='blind_test_h5'`、answers_json/raw_scores/norm_scores）；后期按 contact 反查做「自报 vs 实测」对比 |
| 留资（合规约束） | 个人开发者无公司资质：不注册系统、不用邮箱；个人微信二维码 + 6 位授权码（Excel 手动生成/发放）；微信群=热启动主阵地、公众号=长尾沉淀；结果页「截图即报告」+ 价值钩子文案 |
| 验证门槛 | 真实留资率 ≥40%、弃答率 ≤20%、样本 ≥30；v0.2 待办=Q4/Q5/Q7 密钥差异化 + 五维权重校准（30+ 样本后） |
| 暂缓项 | 「探索版」（AI 动态出题）暂缓：先静态题库池，积累 100+ 题后再议；已有蒙特卡洛稳态压力测试脚本（浏览器 Console 跑） |
| 数据源 | 万得全A 881001.WI 仅作概念锚点（付费）；实际用 akshare/东财/腾讯免费源；Supabase 免费额度覆盖种子期 30~100 人 |

## 3. 代码实况（2026-08-10 探索核实）

### 3.1 落地页（landing）

- `landing.template.html`：单页多 section 模板（nav/hero/ecosystem/scenarios/testimonials/core/features/compare/story/honesty/explore/promise/cta/footer），内联 `<style>` + 手绘贝壳 SVG 装饰。
- `landing.content.yml`：内容配置（brand/nav/hero/features/core/eco/scenarios/explore/compare/honesty/story/pro/testimonials/privacy/cta/footer/about/brandStory），经 `{{path}}`/`{{#each}}`/`{{#if}}`/`{{{ }}}` 注入模板。
- `scripts/build-landing.mjs`：读 yml → 按 `PAGES` 映射（landing/about/story 三页，各自独立模板）→ 渲染 → 内联 `site/style.css` → 校验残留令牌 → 写静态 HTML。**支持新增页面**（PAGES 加条目 + 建模板）。
- 根 `package.json`：`build:landing`/`build:about`/`build:story`/`build:pages`。
- `vercel.json`：仅 `build: pnpm run build:landing`（只构建 landing 单页），404 兜底。
- **无任何互动/游戏/答题区块**（唯一交互是 hero 鹦鹉螺点击喷泡彩蛋，装饰性）。

### 3.2 前端（frontend）

- 投资概览 = `src/views/welcome/index.vue`（路由 `router/modules/home.ts:24-45`，`/` redirect `/welcome`）：当前仅问候语 + 记账天数 + 未读消息，**无雷达图/人格画像/行为分析 UI**。
- 概览聚合走 `/api/summary/`（`src/api/summary.ts`，getSummary/getSankeyData/getDistributions/getPositionGroups/snapshots）；**无 `/api/overview`**。
- 图表依赖已具备：**echarts ^6.1.0 + vue-echarts ^8.0.1 + chart.js ^4.5.1**（`frontend/package.json:60-78`），雷达图零新增依赖。
- 路由机制：业务路由**静态声明**在 `router/modules/*.ts`（home.ts/asset.ts/remaining.ts），`utils.ts:26` 的 import.meta.glob 仅用于后端动态路由 addAsyncRoutes——**与 AGENTS.md「新建即自动成路由」描述不符**（文档债，见 §7.8）。
- 既有债（已解决 2026-08-10）：`welcome/index.vue` 的 Emoji（📬/👋/🌊，:15/:36/:53）经 D18 决策定为**文案内容例外**（欢迎语/消息场景允许），AGENTS.md 与 conventions.md §3.6 已同步加例外说明，不再视为债。

### 3.3 后端（backend/app）

- 18 个领域包（assets/auth/families/funds/importers/ledgers/performance/portfolios/positions/price_history/securities/strategy/summary/temperature/transactions/users/utils/watchlist）。
- 关键表：`positions`（symbol/quantity 最小单位/avg_price 分/allocation）、`assets`（amount 分/major_category）、`transactions`（trade_date/quantity/price/import_hash 唯一）、`users`（supabase_id/role）、`summary.asset_snapshots`（net_worth 分）、`strategy_tags`（持仓风格标签）。
- **无任何行为分析/人格/雷达图/行为签名代码或表**；**无 `user_preferences` 表**（用户偏好类数据无落库载体）。
- 鉴权：`core/auth.py` 白名单机制，`PUBLIC_PREFIXES` 含 health/temperature/securities/search/funds/search；当前用户从 `g.current_user` 取（`CURRENT_USER_ID` 已退役）。
- 测试：`tests/` 按 core/domains/services 分层，`conftest.py` 提供 app/client/db/make_position/make_asset/make_transaction 夹具（内存 SQLite）。

## 4. 技术选型评估（问题 1：模板 vs 框架）

**结论：分层，不引入重型框架。**

| 承载物 | 方案 | 理由 |
|---|---|---|
| 盲测 H5 | **独立静态 HTML + 原生 JS**（或轻量 Vue CDN），静态托管 EdgeOne Pages / Vercel | 本质是互动小游戏（7 关答题/计分/雷达图/结果页），landing 模板机制（yml 内容注入）承载不了应用逻辑；但无需 SSR/复杂状态，重型框架是过度建造 |
| landing 内容页 | 维持现有模板机制 | 内容型页面，yml 注入已够用；`PAGES` 映射支持新增页面 |
| 博客文章 | 若为刚需，用 VitePress（已有文档站）或独立静态博客；**不并入 landing 模板** | 博客需 markdown 渲染/列表/标签，模板机制会吃力；VitePress 已在本仓库验证过 |

**关键判断**：H5 与 landing 是**两个独立部署单元**。H5 走独立 HTML（讨论链共识"前端解耦"），landing 保持内容页定位。`vercel.json` 目前只构建 landing 单页，H5 需独立部署路径（EdgeOne Pages 或 Vercel 独立项目）。

## 5. 雷达图映射方案（问题 2：前期测试 → 后期行为分析）

**一台引擎、两层表面、一个闭环**，前端零新增依赖（echarts 已具备）：

```
行为签名引擎（五维：出击/纪律/专注/切换/逆向，min-max 归一化）
        │
        ├── 表面 A：盲测自报 → submissions 表（source='blind_test_h5'）
        │       前端：H5 结果页雷达图（echarts radar）
        │
        └── 表面 B：实测行为 → 后端 behavior 领域计算 5 行为因子
                前端：投资概览 welcome/index.vue 雷达图
        │
        └── 闭环：按 contact 反查，自报 vs 实测对比（后期）
```

- **前期**：投资概览雷达图数据源 = 盲测结果（submissions 表 norm_scores），用户授权码关联后展示。
- **后期**：数据源切换为行为分析 API（`/api/behavior/signature/`），同一雷达组件、同一归一化引擎，前端只换数据源。
- **前端落地**：`welcome/index.vue` 增加雷达图卡片（vue-echarts RadarChart），数据源按阶段切换；H5 结果页独立实现同款雷达图（原生 JS 或轻量 echarts CDN）。

## 6. 「自己分析」可行性评估（问题 3）

**结论：可行性高，5 个行为因子中 4 个可直接从现有数据计算，1 个需复用市场数据源。**

| 行为因子 | 计算方式 | 数据来源 | 可行性 |
|---|---|---|---|
| 出击（集中度） | 前 3 大持仓市值占比 | `positions.allocation` | ✅ 现成 |
| 专注（持仓时长） | 平均持仓时长 | `transactions.trade_date` | ✅ 现成 |
| 纪律（换手率） | 年化换手率 | `transactions` | ✅ 现成 |
| 切换（赛道漂移） | 跨板块切换次数 | `transactions` + `positions.asset_type` | ✅ 现成 |
| 逆向（暴跌逆势买入） | 暴跌日（指数跌 >3%）净买入 | `transactions` + 市场指数数据（复用 temperature 模块 akshare/东财源） | ⚠️ 需接市场数据 |

**主要工作在后端**：新增 `behavior` 领域包（models/schemas/views），计算逻辑 + `/api/behavior/signature/` 端点；前端仅加雷达图组件。**无数据采集障碍**（不涉及券商持仓自动爬取，仅用用户已录入的账本数据，合规边界内）。

## 7. 预留接口与数据表设计（问题 4）

### 7.1 引流方式（讨论链已定稿）

- 个人微信二维码 + 6 位授权码（Excel 手动生成/发放）——不注册系统、不用邮箱（个人开发者合规约束）。
- 微信群 = 热启动主阵地；公众号 = 长尾沉淀。
- H5 结果页「截图即报告」+ 价值钩子文案（如"30 天后用真实交易数据对比你的自报人格"）。

### 7.2 Supabase `submissions` 表（讨论链已定稿）

```sql
submissions (
  id            uuid pk,
  user_id       uuid null,          -- 匿名可答，登录用户可关联
  source        text default 'blind_test_h5',
  quiz_version  text,               -- lite/standard/deep
  answers_json  jsonb,              -- 原始作答
  raw_scores    jsonb,              -- 五维原始分（供校准）
  norm_scores   jsonb,              -- min-max 归一化后（供雷达图）
  personality_type text,            -- T1/T2/T3 画像
  contact       text null,          -- 授权码/微信标识（后期反查闭环）
  created_at    timestamptz default now()
)
```

### 7.3 后端预留（v0.2+）

- 新增 `backend/app/domains/behavior/`：`models.py`（behavior_signatures 表：user_id/family_id/五维得分/计算日期/数据窗口）、`schemas.py`、`views.py`（`/api/behavior/signature/`，尾斜杠）。
- 鉴权：行为签名属家庭核心账本数据，**必须登录**（不进白名单），与 `g.current_user` 绑定。
- 前端 `src/api/behavior.ts` + `types.d.ts` 类型（禁止 any）。

## 8. 落地方案瑕疵清单（问题 5）

| # | 瑕疵 | 严重性 | 缓解 |
|---|---|---|---|
| 1 | 授权码 Excel 手动生成/发放，规模化瓶颈 | 中 | 种子期（30~100 人）可接受；v0.2 再评估自动化 |
| 2 | 个人微信二维码营销有封号风险 | 高 | 控制频次、内容合规；微信群为主阵地分散风险 |
| 3 | 样本 ≥30 门槛，冷启动慢 | 中 | 微信群热启动 + 公众号长尾双通道 |
| 4 | 自报 vs 实测对比需用户同时留资 + 使用账本，转化链路长 | 高 | 结果页价值钩子引导；先验证留资率再投入账本 |
| 5 | 万得全A 881001.WI 付费 | 低 | akshare/东财/腾讯免费源替代（temperature 模块已验证） |
| 6 | 题库脱敏维护成本 | 低 | 题库 JSON 配置化，脱敏规则写入生成脚本 |
| 7 | `vercel.json` 只构建 landing 单页，H5 无部署路径 | 中 | H5 独立部署（EdgeOne Pages / Vercel 独立项目） |
| 8 | AGENTS.md「新建即自动成路由」与实际不符（静态声明于 router/modules/*.ts） | 低 | 文档债，另立任务修正 AGENTS.md |
| 9 | `welcome/index.vue` 存在 Emoji 债（违反 AGENTS.md） | 低 | 接入雷达图时一并清理 |
| 10 | 后端无 `user_preferences` 表，用户偏好无落库载体 | 低 | 行为签名表设计时一并考虑 |

## 9. 排期与优先级（问题 6）

**无硬性时间节点，按价值密度与依赖关系排序。**

| 优先级 | 阶段 | 内容 | 依赖 | 验证指标 |
|---|---|---|---|---|
| P0 | 种子期验证 | 盲测 H5 静态页（lite 题库 7 关）+ 计分 + 结果页 + 留资（授权码/微信） | 无 | 留资率 ≥40%、弃答率 ≤20%、样本 ≥30 |
| P1 | 数据闭环 | Supabase `submissions` 表 + 数据入库 + 简单看板 | P0 | 数据完整率、弃答漏斗 |
| P2 | 行为引擎 | 后端 `behavior` 领域 + 5 行为因子计算 + `/api/behavior/signature/` | P1 | 因子计算正确性（单测） |
| P3 | 概览集成 | `welcome/index.vue` 雷达图（前期接盲测，后期接行为分析） | P1/P2 | 雷达图数据正确渲染 |
| P4 | 内容沉淀 | 博客/复盘内容（若需要） | 无 | — |

**可行性/收益率评估**：
- P0 是**零成本验证**（静态页 + Supabase 免费额度），收益率 = 留资率验证（≥40% 门槛决定是否继续）。
- P2/P3 是账本核心价值（复盘闭环），但依赖用户使用账本，转化链路长——**先 P0 验证留资，再决定账本投入**，符合"先验证后建造"原则。
- 暂缓：「探索版」（AI 动态出题）等题库池 100+ 题后再议。

## 10. 决策记录

- 2026-08-10：技术选型分层（H5 独立静态页 / landing 维持模板 / 博客用 VitePress 或独立方案），不引入重型框架。
- 2026-08-10：雷达图前端零新增依赖（echarts 已具备），后端新增 `behavior` 领域包。
- 2026-08-10：排期按 P0→P4 价值密度排序，无硬性节点；P0 先行验证留资率。

## 11. 待办与后续

- [ ] P0 盲测 H5 静态页开发（题库 JSON + 计分引擎 + 结果页 + 留资）
- [ ] Supabase `submissions` 表建表 + RLS 策略
- [ ] 修正 AGENTS.md 路由机制描述（文档债）
- [ ] 清理 `welcome/index.vue` Emoji 债（接入雷达图时）
- [ ] 蒙特卡洛稳态压力测试脚本落地（浏览器 Console）
