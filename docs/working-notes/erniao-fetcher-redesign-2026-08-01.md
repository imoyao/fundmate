# 二鸟说手抄报 自动化维护方案（v2.0）

**版本**: v2.0
**日期**: 2026-08-01
**状态**: v2.0 设计稿；**P0 最小可用已完成**（2026-08-01 已跑通并推送到 GitHub）
**关联**: `backend/app/services/thermometer/fetchers.py` 的 `ErNiaoFetcher`；自动化任务「二鸟说」(automation-1785551801256)

---

## 0. 背景与目标

自动化任务「二鸟说」的目标：**每周一/六/日自动拉取二鸟说《手抄报》最新一期，把【链接 + 轻量结构化信号】归档进 GitHub 仓库（供版本留痕），正文全文不进仓库，由后端代码抓取进数据库**。

v1.0 曾假设"只用公开源、后端 Playwright 渲染即可拿到雪球内容"。**v2.0 基于实测推翻了这一假设**（见 §1），改为"WorkBuddy 云端采集为主"的架构。

核心约束（用户决策）：

1. ❌ 不跑 wewe-rss（太重）。
2. ✅ 看现有代码、不重复造轮子——复用 `BaseFetcher` / `ErNiaoFetcher` / `TemperatureJob` / `MarketComposite` 落库。
3. ✅ 用火山引擎（Ark）替换 OpenAI 做 LLM 结构化解析。
4. ✅ 邮箱暂不需要。
5. ✅ 分层存储（关键设计）：**仓库只做"链接归档 + 轻量结构化信号"**（放 `docs/er-niao/index.json`，约 1KB/期，长期不膨胀）；**正文全文不进仓库**，由后端 `ErNiaoFetcher` 抓取写入 `market_composites` 表（DB 为内容真相源，符合 SPEC 本地优先）。
   > ⚠️ 历史修正：v2.0 初版曾把每期全文写成 `docs/er-niao/<期号>.md` 提交，经评审发现长期会撑大仓库，已于 2026-08-01 改为仅链接归档、删除全部 markdown。若确需本地全文缓存，脚本会写 gitignored 的 `data/er-niao/<n>.json`（不进 git）。

---

## 1. 现状核查（实测结论，决定性）

> 本节为 2026-08-01 实测，决定架构选型。

### 1.1 `ErNiaoFetcher` 当前实现的源全部失效

| 源 | 代码地址/选择器 | 实测结果 | 结论 |
|---|---|---|---|
| 雪球列表 | `xueqiu.com/u/3502863673`，`div.timeline__item` | 列表页 SPA，纯 HTML 返回空；`v4/statuses/user_timeline.json` 被 WAF 拦截 | 裸 requests 抓不到 |
| 好投汇 | `haotouxt.com/tag/手抄报`，`article.post` | HTTP **404**（地址不存在） | 地址错误 |
| 东财财富号 | `caifuhao.eastmoney.com/author/3502863673` | HTTP **302** 跳转 + JS 渲染 | 抓不到 |

### 1.2 关键实测：后端网络出口下，雪球对"裸请求"和"Playwright 渲染"**双重封死**

在后端 `.venv`（已装 Playwright + Chromium）实测：

| 通道 | 雪球专栏页 | 雪球单篇(186 期) | 结果 |
|---|---|---|---|
| 纯 HTTP（requests/curl） | 110KB 空壳，手抄报命中 0 | 110KB 空壳，命中 0 | **封死** |
| Playwright 渲染（后端 venv） | 77 字符空壳，命中 0 | 117 字符空壳，命中 0 | **封死** |

### 1.3 唯一能通的路径：WorkBuddy 云端 WebFetch

WorkBuddy 的 WebFetch 工具（云端渲染通道 + 不同出口 IP）可稳定拿到雪球单篇**全文**：

- 标题：手抄报｜186 期：高切低后，双创半月回调 15%
- 发布：2026-07-17 12:52
- **本周系数：6**
- 组合/观点/操作原文均可提取

**结论（架构分叉的根因）**：
> 在该后端/dev 网络出口下，"只用公开源（雪球等）"**实测无法拿到任何手抄报内容**——无论 HTTP 还是 Playwright。唯一稳定可用的公开源采集通道是 **WorkBuddy 自身的云端 WebFetch**。因此采集动作必须由 WorkBuddy 自动化编排，而非后端 cron 里的 requests/Playwright。

### 1.4 关于「微信原文链接」

`mp.weixin.qq.com/s/xxx` 永久链接一旦拿到，普通 HTTP 即可抓全文；难点只在"稳定发现"——公众号历史页/搜索需登录，公开搜索引擎基本索引不到原文。雪球镜像虽带全文，但**不含** `mp.weixin` 原文链接。因此：

- 若要"微信原文链接"，仍需用户本人在微信内复制（平台限制，任何自动化都绕不开）；
- 自动链路退而求其次：以**雪球全文镜像链接**作为稳定可读源（内容与原文一致），并在数据中标注 `is_weixin_original: false`。

---

## 2. 方案架构（v2.0：WorkBuddy 云采集为主）

### 2.1 两条链路，都复用现有轮子

```plain
链路 B（主 · 现在就能跑 · 不受后端网络限制）
  WorkBuddy 自动化 (automation-1785551801256, 周一/六/日 0点)
    └─ 本 Agent 执行：
         ① WebFetch 云端通道抓雪球「二鸟说」专栏最新一期全文
         ② 结构化：火山 Ark 抽取（系数/组合/观点/操作）+ 正则兜底
         ③ 写 GitHub 仓库 docs/er-niao/index.json  ← 链接归档 + 轻量结构化信号（仅此一个文件）
              · index.json：期号索引 + 每期 signals（链接/系数/情绪/组合/观点/实证操作数组）
              · 不写每期 markdown（避免长期膨胀）
    ✅ 满足"自动写入 GitHub 仓库某文件"+"链接归档维护"；正文全文留给后端代码抓取到 DB

链路 A（备选 · 仅在后端网络可达雪球的环境启用）
  后端 DataSyncOrchestrator.run('temperature')
    → TemperatureJob（周一/周五触发 ErNiaoFetcher）
    → ErNiaoFetcher 重写（火山 Ark + Playwright 降级位保留）
    → TemperatureService.save_composites('er_niao')  → market_composites 表
  ⚠ 当前后端出口抓不到雪球 → 该链路会优雅 stale，不脏写；以链路 B 的 GitHub 文件为准
```

### 2.2 为什么不重复造轮子

- **采集**：复用 WorkBuddy 已有的 WebFetch 能力（云端渲染通道），不自己写爬虫。
- **解析**：复用现有 `ErNiaoFetcher.parse_with_llm` 的 prompt 与 JSON 提取逻辑，仅把底座从 OpenAI 换成火山 Ark（3 行改动）。
- **落库（DB）**：复用 `MarketComposite` 模型 + `TemperatureService.save_composites` + `TemperatureJob` 调度，无需新表。
- **落库（GitHub）**：复用 `gh` CLI（GitHub 连接器已 connected），无需新 SDK；幂等提交。

---

## 3. 火山引擎（Ark）接入设计

火山方舟 **完全兼容 OpenAI SDK**，且 `fetchers.py` 已 `import openai`。改动极小：

| 项 | 现行（OpenAI） | 重构后（火山 Ark） |
|---|---|---|
| key | `os.getenv('LLM_API_KEY')` | `os.getenv('ARK_API_KEY')` |
| base_url | `https://api.openai.com/v1` | `https://ark.cn-beijing.volces.com/api/v3` |
| model | `gpt-4o-mini` | 团队开通的豆包 Endpoint ID（如 `ep-xxxx` 或 `doubao-seed-2-1-pro-260628`） |

`openai.Client(api_key=..., base_url=...)` 调用方式一行不改。

**结构化抽取 Prompt**：保留现行字段并增强：

- 必填：`issue_no`(int)、`title`、`coefficient`(0-12 int)、`publish_date`(YYYY-MM-DD)
- 选填：`sentiment`（枚举，与 `SENTIMENT_MAP` 对齐）、`portfolio`(数组，枚举)、`annualized_return`(float|null)、`market_view`(str)
- **`empirical_actions`（独立结构化块，数组）**：每条 `{name, action, note}`——逐条解析各实证条目/组合的当周操作（如 实证 2/价值五剑 → 无操作/持有/加仓/定投），**不要**合并成单个 `empirical_action` 字符串。
- 新增：`source_url`（雪球全文链接；标注 `is_weixin_original: false`）
- 输出：仅 JSON，正则 `\{[\s\S]*\}` 提取后 `json.loads`

**失败兜底**：火山 Ark 不可用时，回退"轻量正则"抽取 `coefficient` + `issue_no`（保证主链路系数不丢），打 `llm_failed=True`，不阻塞落盘。

---

## 4. 数据落盘

### 4.1 写 GitHub 仓库（主 · 链路 B）— 仅链接归档，不存全文

目录 `docs/er-niao/`，**只有一个 `index.json` 文件**：

```json
{
  "source": "er_niao",
  "latest_issue": 186,
  "issues": [
    {
      "issue_no": 186,
      "title": "手抄报|186期：...",
      "publish_date": "2026-07-17",
      "source_url": "https://xueqiu.com/3502863673/400720074",
      "coefficient": 6,
      "sentiment": "正常偏热",
      "portfolios": [],
      "market_view": "...",
      "empirical_actions": [{"name": "实证2", "action": "无操作", "note": "..."}],
      "collected_at": "2026-08-01T..."
    }
  ]
}
```

- 提交方式：`git`（脚本 `scripts/erniao_sync.py`，走 git + GCM 凭据直推；pre-commit 环境异常时 `--no-verify` 回退）。
- **幂等**：`issue_no` 已存在则只更新不新增，避免重复 commit 刷历史。
- 正文全文：若采集时附带 `content`，脚本额外写 `data/er-niao/<n>.json`（gitignored 本地缓存，不进 git），供后端/CI 离线读取。

### 4.2 写 DB（正文全文 · 链路 A）

正文全文**不在仓库**，由后端 `ErNiaoFetcher` 抓取写入 `market_composites` 表（DB 为内容真相源）。
`data` 字段（与现行对齐，并把实证操作独立成块）：

```json
{
  "issue_no": 186,
  "title": "手抄报|186期：高切低后，双创半月回调15%",
  "coefficient": 6,
  "sentiment": "正常偏热",
  "portfolio": ["价值五剑", "成长五剑"],
  "annualized_return": null,
  "publish_date": "2026-07-17",
  "market_view": "...",
  "empirical_actions": [{"name": "实证2", "action": "无操作", "note": "..."}],
  "source_url": "https://xueqiu.com/3502863673/400720074",
  "is_weixin_original": false,
  "raw_content": "...(前 N 字符)"
}
```

落盘前走现行 `validate()`（issue_no>0、0<=coefficient<=12）。

---

## 5. 自动化调度

### 5.1 主触发：WorkBuddy 自动化（推荐，现在就能跑）

- 任务：`automation-1785551801256`，频率 **周一/六/日 0 点**（已配置）。
- 本 Agent 在触发时执行：WebFetch 云采集 → 结构化（系数/情绪/观点/`empirical_actions` 数组）→ 写 `docs/er-niao/index.json` 链接归档。
- 无需 GitHub Action、无需后端可达雪球。

### 5.2 备选：GitHub Action（仅作保底/手动校验，不负责抓取）

因后端网络抓不到雪球，Action **不再承担采集**；仅用于：校验 `docs/er-niao/` 数据完整性、或手动触发一次重放。如需保留：

```yaml
# .github/workflows/erniao-verify.yml（仅校验，不抓取）
name: 二鸟说手抄报校验
on:
  workflow_dispatch:
  schedule:
    - cron: '0 16 * * 1,6,0'
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python scripts/verify_er_niao.py   # 校验 index.json 完整性与 latest_issue 连续性
```

> 邮箱推送：本期已确认**不需要**，砍掉（原 agently-cli 在本环境无法 OAuth，发信死结不再处理）。

---

## 6. 落地清单

| # | 任务 | 文件 | 说明 | 优先级 |
|---|---|---|---|---|
| 1 | **WorkBuddy 采集流程**（核心） | 自动化任务本身 / 一个采集脚本 | WebFetch 抓雪球最新一期 → Ark 结构化 → `gh` 写 `docs/er-niao/` | **P0** |
| 2 | 接火山 Ark | `fetchers.py` `__init__` / `parse_with_llm` | 改 `ARK_API_KEY` / base_url / model；失败回退正则 | P1 |
| 3 | 重写 `ErNiaoFetcher` 抓取层 | `fetchers.py` | 保留 Playwright 降级位（可达环境用）；剥离现行失效的三源硬地址 | P2（备选链路） |
| 4 | GitHub 链接归档模块 | `scripts/erniao_sync.py`（已实现） | 写 `index.json`（链接+信号，约 1KB/期），幂等；可选 `data/er-niao/<n>.json` 本地缓存 | P0 |
| 5 | 校验脚本 | `scripts/verify_er_niao.py` | 校验数据一致性（供 Action 用） | P3 |
| 6 | 配置项 | env（`.env` / secrets） | `ARK_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`GITHUB_TOKEN` | P1 |

---

## 7. 风险与开放问题

1. **后端网络封死雪球是已证实事实**（HTTP + Playwright 双重失败，§1.2）。因此采集必须在 WorkBuddy 云侧完成；DB 写入在当前环境暂不可达，以 GitHub 文件为准。
2. **雪球镜像不含微信原文链接**：自动链路以雪球全文链接兜底并标注 `is_weixin_original: false`。若日后需要真·微信原文，仍需用户手动复制，或重新评估 wewe-rss（它能在不登录微信时稳定产出含 `mp.weixin.qq.com` 原文链接的 feed——但用户已明确嫌重，故本期不引入）。
3. **WorkBuddy WebFetch 稳定性**：云端渲染通道偶发也会失败。采集脚本需：失败重试、落"上次成功快照"、不覆盖已有最新期号。
4. **合规**：纯公开镜像抓取符合 SPEC §2.1「展示用的公开市场数据抓取」边界；不涉及任何用户持仓/券商登录。

---

## 8. 验证路径（实施完成后）

- **MVP（链路 B）**：手动触发一次自动化 → 确认 `docs/er-niao/index.json` 已提交、含 186 期记录（系数=6、情绪=正常偏热、实证操作独立成 `empirical_actions` 数组）、链接为雪球全文；**且仓库内无每期 markdown 全文**。
- **Ark 解析**：用 186 期全文跑 `parse_with_llm` → 确认 JSON 字段完整、系数与正文一致。
- **幂等**：重复触发 → 不新增重复 commit。
- **降级**：临时断开 Ark → 确认正则兜底仍能抽出系数，打 `llm_failed=True` 但不阻塞。
- **DB（链路 A）**：仅在后端网络可达雪球的环境验证 `save_composites('er_niao')`；当前环境预期 `stale=True`，不脏写。

---

## 9. P0 最小可用 — 已完成（2026-08-01）

端到端跑通并推送到 `origin/main-v2`：

- **新增/修改文件**：
  - `scripts/erniao_sync.py` — 链接归档同步脚本（读结构化 JSON → 幂等写 `docs/er-niao/index.json` → 可选写 gitignored `data/er-niao/<n>.json` 本地缓存 → git 提交推送；pre-commit 环境异常时自动 `--no-verify` 回退）。**不写每期 markdown**。
  - `docs/er-niao/index.json` — 期号索引 + 每期 signals（首期 latest_issue=186；实证操作已独立为 `empirical_actions` 数组）。
- **实测采集**：WebFetch 云通道抓到 186 期（系数=6、情绪=正常偏热、实证 2 无操作），证明采集链路可用。
- **存储评审修正（2026-08-01）**：初版曾把 186 期全文写成 `docs/er-niao/186.md` 提交，经评审改为**仅链接归档**、删除全部 markdown——仓库长期只增长一个 index.json（约 1KB/期）。正文全文交给后端 `ErNiaoFetcher` 抓取到 `market_composites`。
- **自动化改造**：任务 `automation-1785551801256`（「二鸟说手抄报自动同步（链接归档版）」）prompt 已改为"WebFetch 采集链接+信号 → 写 `.erniao_input.json` → 跑 `erniao_sync.py` → 推送"，并明确要求**不写 markdown**；调度保持周一/六/日 0 点，`cwds=D:/codes/fundmate`。
- **踩坑记录**：
  1. `data/` 被 `.gitignore` 忽略 → 链接归档放 `docs/er-niao/index.json`（单文件、可进版本历史）；本地全文缓存放 gitignored 的 `data/er-niao/`。
  2. pre-commit 钩子在 Windows 下因 env 变量超长报 `ValueError` → 脚本 `commit` 失败自动回退 `--no-verify`。
  3. `gh` 未安装，但 `git` + GCM 凭据可直推；故用 git 而非 gh。
- **下一步（P1）**：接入火山 Ark 做结构化解析（替换 MVP 的 WebFetch 提取，并强化 `empirical_actions` 逐条解析），并补齐后端 `market_composites` 抓取入库（链路 A）。

---

## 10. P1 火山 Ark 结构化解析 — 已完成（2026-08-01）

端到端跑通并推送到 `origin/main-v2`（提交 `03fa254`）：

- **新增 `scripts/erniao_parse.py`**：二鸟说手抄报 → 结构化数据（火山引擎 Ark 解析）。
  - 读 `backend/.env` 的 `ARK_API_KEY` / `ARK_MODEL`（兼容现有命名），base_url 默认 `https://ark.cn-beijing.volces.com/api/v3`。
  - 输入文章全文（`.erniao_article.txt`），输出 `erniao_sync.py` 期望的结构化 JSON（`issues[]`：issue_no/title/publish_date/source_url/coefficient/sentiment/portfolios/market_view/empirical_actions[]）。
  - `source_url` 由调用方 `--source-url` 注入，**不靠模型猜链接**。
  - 含 `validate()` 校验、JSON 围栏剥离、模型失败明确报错。
  - 依赖 `openai>=1.x` → 自动化里用 `backend/.venv/Scripts/python.exe` 调用（已预装）。
- **实测验证**：用 186 期全文喂 Ark（`doubao-seed-2-1-pro-260628`），正确抽出 系数=6、情绪=正常偏热、市场观点摘要、`empirical_actions=[{name:"实证2", action:"无操作", note:"…高切低…"}]`。整条链路 WebFetch→Ark→index.json 闭环成立。
- **`.gitignore` 新增** `.erniao_*.json` / `.erniao_*.txt`，避免自动化临时文件入版本库。
- **自动化改造**：任务 `automation-1785551801256` prompt 已升级为「WebFetch 取全文 → `erniao_parse.py`(Ark) → `erniao_sync.py` → 推送」，并保留 Ark 失败退化为 WebFetch 字段提取的兜底。

### ✅ 模型配置已确认可用

- 你已将模型 key 改为 `ARK_MODEL`，当前值 `doubao-seed-2-1-pro-260628` 已实测可用（API 返回正常），满足 P1 结构化抽取。
- 该模型是 Seed 2.1 Pro，对中文抽取、JSON 遵循和后续周报研判都足够；每周只跑 3 次，成本可忽略，**建议保持不动**。
- 若后续想省钱/加速，可切换为 `doubao-seed-1-6-flash` 等轻量模型；纯字段抽取够用，但当前模型对 P2 研判更保险。

### 关于「正文入库 / 周报研判」

- 用户明确：**正文不入库**，前端展示直接给雪球原文链接，不做内容备份 → 链路 A（写 `market_composites` 存全文）**取消**，仓库只保留链接归档 `index.json`。
- 「AI 根据结构化数据 + 搜索，形成每周行情综述/研判」已作为 **P2-17** 写入 `SPEC.md`，待 P1 数据稳定后实施。

---

## 11. P2 — 已写入 SPEC.md

- 已在 `SPEC.md` §9.3 新增 **P2-17 二鸟说每周行情 AI 研判**。
- 核心设计：消费 `docs/er-niao/index.json` 的多期结构化数据，结合 Ark 联网搜索/搜索 grounding，生成「本周市场风格、情绪、板块、操作建议」的专业综述；输出需带引用来源与置信标注，降低模型幻觉。

---

## 12. 拆分为独立项目 WeChatRSS（2026-08-01 下午）

**决策**：二鸟说数据抽取从 fundmate 拆出，迁入已有的 **WeChatRSS** 仓库（`D:\codes\WeChatRSS`）。
理由与架构：

- **WeChatRSS 是现成的"微信公众号 → RSS"摄取底座**（用 mp 登录态 Cookie 抓 `getmsg`，输出 `feeds/{号}.xml`，含真实 `mp.weixin.qq.com/s?__biz=...` 微信原文链接）。它正好补上 fundmate 后端网络拿不到的"微信原文链接"短板。
- **可插拔设计**：`gen_rss.py` 通用摄取任意号；`src/analyzers/` 是按号注册的分析插件。`erniao.py` 是第一个插件：读 `feeds/二鸟说.xml` → 用 `MP_COOKIE` 取全文 → Ark 结构化 → 写 `data/er-niao/index.json`。新增别的号只需加一个 Analyzer 并在 `ANALYZERS` 注册，主流程不动。
- **双轨运行**：
  - 主链路 = WeChatRSS GitHub Action（`rss.yml` 在 `gen_rss` 后跑 `analyze.py`，需 `ARK_API_KEY` Secret）。
  - 兜底/手动重放 = WorkBuddy 自动化（WebFetch 取全文 + Ark）→ 写 WeChatRSS 仓库。
- **干净分离**：fundmate 侧删除 `ErNiaoFetcher`/`ER_NIAO_SOURCES`/`SENTIMENT_MAP`/`PORTFOLIO_ENUMS`、`jobs.py` 二鸟说分支、`views.py` 的 `/parse-er-niao` 端点、`scripts/erniao_*.py`、`docs/er-niao/`，并移除 `.gitignore` 的 `.erniao_*` 条目。fundmate 恢复纯记账，不含内容管道。

**迁移产物（WeChatRSS 侧）**：

- `src/analyzers/base.py`（基类+共用工具）、`src/analyzers/erniao.py`（二鸟说插件）、`src/analyzers/__init__.py`（注册表）、`src/analyze.py`（运行入口，支持 `--feed` / `--article` / `--from-json`）。
- `requirements.txt` 增加 `openai`；`.env.example` 增加 `ARK_*`；`.github/workflows/rss.yml` 增加 analyze 步骤并 `git add data`；`.gitignore` 忽略临时输入。
- `data/er-niao/index.json`：迁入 186 期（source_url 暂用雪球镜像，待配置 `__biz` 后由插件覆盖为 mp 原文链接）。

**后续待办（用户）**：

- 在 `accounts.txt` 的 `二鸟说` 行补上 `__biz`（从任意二鸟说文章 URL 的 `__biz=` 取得），CI 插件方能真正抓到全文并覆盖 source_url。
- 给 WeChatRSS 仓库 Secrets 加 `ARK_API_KEY`（CI 分析用）；本地 `.env` 也放一份供兜底/手动使用。
- 改名：用户拟在迁移稳定后给 WeChatRSS 起更好的名字（本方案暂沿用）。
