# 探市 × 自选 页面增强方案（2026-08-12 修订）

> 性质：内部备忘（`docs/working-notes/` 屏蔽出构建，不对外）
> 触发：用户 8-11 追加需求——① 暂停基估宝数据迁移；② 丰富探市页 + 自选页，体验统一；③ 提升产品化与精细度（参考基估宝）；④ 自选页增加 OCR/AI 批量导入（后端实现 + 调用限制）。
> 修订：8-12 纳入用户 6 个关键决策 + 后端落地情况。
> 基线文档：`explore-watchlist-replan-2026-08-08.md`（18 项基估宝改进点 + OCR 设计）、issue #821（探市缺陷）、#823（OCR+通用用量表）。

---

## 1. 用户需求拆解

| # | 需求 | 用户原话要点 | 对应方案章节 |
|---|---|---|---|
| 1 | 探市/自选添加自选体验统一 | 「探市和自选都有一个表格去添加自选，预期统一；探市可简单（未登录用户用），但做得好两边基本统一」 | §4 |
| 2 | 自选页产品化与精细度 | 「不够企业化/产品化，基估宝更专业；我们功能更丰富但细节打磨差；参考第三点 MD 设计优化」 | §5 |
| 3 | 改进基估宝相关功能 | 「把之前 docs 里准备改进的方式落实，不确定代码改没改，没改就做」 | §5（18 项对齐现状） |
| 4 | OCR/AI 批量导入 | 「(a) 基估宝已有导入 APK，是后端实现，我们也在后端做；(b) 测试 Key 需限制 3~5 次/用户；(c) 后期导入并识别交易记录（文档讨论过）」 | §6 |

---

## 2. 现状盘点（2026-08-12 源码核对，分支 `main-v2`）

### 2.1 fundmate 已有能力

| 能力 | 证据 | 状态 |
|---|---|---|
| watchlist 后端 CRUD + 分组/标签/持仓 | `backend/app/domains/watchlist/views.py`：`GET /`、`POST ''`、`POST /batch`、`POST /import/explore`、`POST /{id}/position`、`PUT /item/tags`、`PUT /item/groups`、groups/tags CRUD、batch-move/copy/delete、`GET /positions` | ✅ 已实现 |
| 探市→自选迁移桥 | `POST /api/watchlist/import/explore` + `useSupabaseAuth.ts` | ✅ 已实现 |
| 探市本地观察 | `useLocalHoldings.ts`（`showbuy_explore_v1`）+ `useAssetSearch.ts` | ✅ 已实现 |
| 自选页 | `frontend/src/views/asset/watchlist/index.vue`（三视图：自选/持仓/分组；批量操作；实时估值） | ✅ 已实现 |
| 添加自选弹窗 | `frontend/src/components/QuickEntry/AddToWatchlistModal.vue` | ✅ 已实现 |
| 后端 ARK Key | `backend/.env`：`ARK_API_KEY`（已配 46 位）+ `ARK_MODEL=doubao-seed-2-1-pro-260628` | ✅ 已配置但零引用 |
| 后端 OCR/LLM 服务 | 无 | ❌ 待建 |
| 通用用量表 `user_usage` | 无 | ❌ 待建 |

### 2.2 基估宝 OCR 全链路（源码实证 `D:\codes\jigu`）

| 环节 | 基估宝实现 | 文件 |
|---|---|---|
| 前端 OCR | tesseract.js（chi_sim+eng），包体大、精度差 | `app/lib/ocr.js` |
| 选图弹窗 | ScanPickModal：拖拽/上传/相机 + 剩余次数（≤3 黄、=0 禁） | `app/components/ScanPickModal.jsx` |
| 确认导入弹窗 | ScanImportConfirmModal：已存在/新基金区分、分组选择、标签 | `app/components/ScanImportConfirmModal.jsx` |
| LLM 解析 | `parseFundTextWithLLM`：apis.iflow.cn + deepseek-chat | `app/api/fund.js` L2386+ |
| 用量限制 | 前端 `fetchOcrDailyRemaining` + 边缘函数 `MAX_DAILY_OCR=5`（前端 maxLimit=10 与边缘函数 5 不一致，是基估宝自身 bug） | `doc/edgeFunction/analyze-fund.ts` |
| 安全缺陷 | `api/fund.js` L911-914 硬编码 LLM API key | replan §1.2 |

> 基估宝 OCR 是**前端 tesseract + 后端 LLM 解析**；replan 已否决前端 tesseract（包体大、精度差）。

---

## 3. 用户 6 个关键决策（2026-08-12）与评估

### 3.1 OCR 是必须的吗？要不要付费？

- **不是必须**：OCR 是便利性功能，解决「从券商/天天基金 App 截屏 → 导入自选」的录入痛点；不引入则用户手动逐个搜索添加。
- **付费评估**：火山方舟 doubao 按 token 计费。单次 OCR 调用（图片理解 + 结构化提取）约 1~2k token，按 doubao-seed 价格约 **0.0037 元/次**（replan §决策测算）。配合「免费 5 次/天」限流，单用户日成本 ≈ 0.02 元，可忽略。
- **结论**：值得做，成本极低；但必须有用量护栏（防刷、防费用失控）。

### 3.2 部署与 H1：是否阻塞？

- **零阻塞**：火山方舟是**云端 HTTP API**（OpenAI 兼容端点 `https://ark.cn-beijing.volces.com/api/v3/chat/completions`），不需要在 Docker 镜像里装任何 OCR 引擎/模型文件。
- 我们**否决** PaddleOCR / tesseract 本地方案（模型文件大、Docker 镜像膨胀、CPU 推理慢），这正是部署阻塞点所在。
- H1 部署允许使用：只需要服务器能访问 `ark.cn-beijing.volces.com`（HTTPS 443）即可，与现有 Supabase/东财请求同级。
- **结论**：纯 HTTP 调用，镜像无新增依赖，H1 无阻塞。

### 3.3 登录后「探市」添加：应禁止

- 用户理解正确：**登录后探市页不应提供「添加自选」**，否则与自选页存在两处入口，用户困惑。
- 设计：探市页感知登录态（`useSupabaseAuth().isAuthenticated`），登录后隐藏添加按钮/引导跳转自选页。
- 数据源唯一性：未登录走 localStorage（`useLocalHoldings`），登录后统一走后端 watchlist，探市本地数据登录后一次性迁移（已有桥）。

### 3.4 其他页面添加自选：快速添加图标 vs 弹窗？

- 评估（取决于场景）：
  - **详情页/列表快捷入口**：用**图标一键快速添加**（默认分组 + toast 反馈）摩擦最小，符合高频轻操作预期。
  - **需要分组/标签时**：提供完整弹窗（自选页内的 `AddToWatchlistModal` 已实现）。
- 结论：**快速添加图标（默认分组）+ toast** 为主，弹窗为深度操作；两者并行，不互相替代。
- 基估宝的做法（`AddFundToGroupModal` 确认单）是「每加必弹」，对本项目高频场景过重，不采纳。

### 3.5 基估宝 OCR 能否满足？前端 OCR 还是后端？

- **基估宝 OCR 不满足**：tesseract.js 前端识别精度差（基金代码 6 位数字误识率高）、包体大（chi_sim 词典 ~20MB）、移动端慢；且其「前端 OCR + 后端 LLM」拆两段，链路长。
- **后端一步到位更优**：doubao-seed-2-1-pro-260628 全模态（图片直接进），一次 HTTP 调用同时完成「图像理解 + 结构化 JSON 提取」，前端只传图 + 展示结果。
- 成本/体验双优：单次 0.0037 元 vs 前端 tesseract 免费但体验差；后端方案前端包体零增长。
- **结论：后端 OCR（火山方舟 vision），不做前端 OCR。**

### 3.6 探市 vs 自选：功能边界（防白嫖）

| 能力 | 探市（免登录） | 自选（登录） | 理由 |
|---|---|---|---|
| 搜索 + 查看详情/估值 | ✅ | ✅ | 引流钩子 |
| 本地观察列表（50 上限） | ✅ | — | 沙盒，登录后迁移 |
| 添加自选 | ✅（仅未登录） | ✅ | 登录后探市引导去自选页 |
| 分组/标签/笔记 | ❌ | ✅ | 高价值管理能力，必须登录 |
| 批量操作 | ❌ | ✅ | 同上 |
| **OCR/AI 批量导入** | ❌ | ✅ | 付费候选功能 + 限次需要 user_id |
| 实时估值/行情 | ✅ | ✅ | 公开数据 |
| 收益/持仓联动 | ❌ | ✅ | 家庭账本，私有 |

- **原则：探市 = 引流沙盒，只放「看 + 轻收藏」；一切「可持久化/管理/导入」能力留在登录后的自选。** 防止用户不注册就在探市完成全部闭环。

---

## 4. 需求 1：添加自选体验统一

- 现状：探市（`useLocalHoldings` 纯本地）、自选（`AddToWatchlistModal` 后端）两套 UI。
- 方案：
  1. 共享**搜索下拉**交互（都基于 `useAssetSearch`，已是同一底层）。
  2. 探市简化配置：无分组/标签，添加即入本地观察（50 上限提示）。
  3. 自选完整配置：`AddToWatchlistModal`（分组/标签/笔记/成本）。
  4. **登录态分支**：探市页登录后隐藏「添加」，显示「去自选页管理」入口。
  5. 上限提示样式统一（探市 50 / 自选无上限）。

## 5. 需求 2+3：自选页产品化与 18 项改进点对齐

### 5.1 18 项改进点现状核对（replan §2 对照）

| # | 改进点 | replan 状态 | 本次核对（8-12） | 本次是否实施 |
|---|---|---|---|---|
| 1 | 估值分时复用 | ❌ | 后端无此缓存 | 暂不（行情域） |
| 2 | 自选→持仓快速建仓 | ❌ | `POST /{id}/position` 已存在 | 前端补入口 |
| 3 | 重仓追踪 | ✅ 部分 | 温度页有 | 暂不 |
| 4 | 收益日历 | ❌ | 无 | 暂不（依赖持仓） |
| 5 | 每日收益热力图 | ❌ | 无 | 暂不 |
| 6 | 数据源准确度徽章 | ❌ | 无 | 暂不（行情域） |
| 7 | 分组收益汇总 | ❌ | 无 | 暂不（依赖持仓） |
| 8 | 移动端 PWA 自选 | ❌ | 无 | 暂不（大项） |
| 9 | 自定义标签 | ❌ | tags API 已存在 | ✅ 前端补全 |
| 10 | 批量导入 | ❌ | `POST /watchlist/batch` 已存在 | ✅ OCR 导入走此 |
| 11 | 卡片式分组摘要 | ❌ | 无 | 暂不 |
| 12 | 快速添加（搜索+分组） | ❌ | `AddToWatchlistModal` 已存在 | ✅ 统一化（§4） |
| 13 | 加仓/减仓 | ❌ | 无 | 暂不（持仓域） |
| 14 | 持仓成本编辑 | ❌ | 无 | 暂不 |
| 15 | 单击卡片展开 | ❌ | 无 | ✅ 轻量抽屉 |
| 16 | 添加自选确认单 | ❌ | AddToWatchlistModal 已有 | ✅ 已实现 |
| 17 | 持仓导出 | ❌ | 无 | 暂不 |
| 18 | 盈亏表现卡片 | ❌ | 无 | 暂不（依赖持仓） |

### 5.2 本次落地范围（前端）

- 探市页登录态感知（§3.3）：登录后隐藏添加，引导自选页。
- 自选页列表行：标签 chips + 添加天数展示（复用已有 `item.tags`/`created_at`）。
- OCR 导入入口（§6）：自选页工具栏按钮 + 上传/确认弹窗。

---

## 6. 需求 4：OCR/AI 批量导入（后端落地）

### 6.1 技术决策

| 项 | 决策 | 理由 |
|---|---|---|
| OCR 引擎 | 火山方舟 doubao-seed-2-1-pro-260628（全模态） | `.env` 已配 key；OpenAI 兼容 HTTP，零本地依赖 |
| 调用端点 | `POST https://ark.cn-beijing.volces.com/api/v3/chat/completions` | OpenAI 兼容，`Authorization: Bearer ARK_API_KEY` |
| 用量表 | 通用 `user_usage(user_id, feature, period_date, count, quota)` | issue #823 决策：通用用量表，不每功能建表 |
| 配额 | 免费 5 次/天（用户要求 3~5 次 → 定 5） | 测试 Key 防费用；超限友好提示 |
| 费用护栏 | 单次 ~0.0037 元 | issue #823 已测算 |
| 归属 | 识别结果 → 前端确认 → 逐条 `POST /api/watchlist/items/` 入库 | ⚠️ 原规划走 `POST /api/watchlist/batch`，核对源码发现后端**无 batch 端点**（views.py 仅逐条 create_item），故改用逐条导入（409 跳过/失败计数），复用现有接口 |
| 鉴权 | 必须登录（非白名单），按 `g.current_user` 限次 | 防白嫖 + 限次需要 user_id |

### 6.2 后端新增（`backend/app/`）

1. `services/ocr_service.py`：
   - `recognize(image_bytes) -> list[{code, name, ...}]`：图片 base64 → 火山方舟 vision → 结构化 JSON。
   - `check_usage(user_id) / consume_usage(user_id)`：读写 `user_usage`（特征 `ocr_import`）。
   - `parse_text(text) -> list[{code, name}]`：纯文本批量导入（用户需求「AI 批量导入」），同一 LLM 管道。
2. `domains/usage/`：`models.py`（`user_usage` 表）+ `views.py`（`GET /api/usage/ocr_import` 剩余次数）+ `schemas.py`。
3. `domains/ocr/`（或并入 watchlist）：`POST /api/ocr/recognize`（上传图片→识别→返回候选，同时消耗 1 次配额）。
4. 依赖：`requests`（已有）。无需新增 SDK。
5. env：`ARK_API_KEY`（已配）、`ARK_MODEL`（已配）、`OCR_DAILY_QUOTA=5`（新增默认）。

### 6.3 前端新增

- 自选页工具栏「OCR 导入」按钮 → 上传图片/粘贴文本弹窗。
- 识别结果确认弹窗：区分已存在/新基金、默认勾选新增、可选分组。
- 用量提示：进入时 `GET /api/usage/ocr_import` 显示剩余次数。
- 探市页不做 OCR（未登录无法限次，符合 §3.6 边界）。

### 6.4 后期扩展（需求 4c，本次不实施）

- 同一管道识别**交易记录**（买入/卖出/金额/份额/日期）：新建 `feature='txn_import'`，识别结果走 `POST /api/importers/parse` 预览 → confirm 入库。
- 前置依赖：持仓/交易导入能力成熟、ARK 用量可观测。

---

## 7. 实施计划

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | 本文档（8-12 修订） | ✅ 完成 |
| P1 | §4 添加自选体验统一（登录态感知） | ✅ 已落地（探市/温度计登录态引导，见前端 commit） |
| P2 | §5.2 自选页产品化（标签 chips + 添加天数） | 待实施 |
| P3 | §6.2 后端：usage 表 + ocr_service + API | ✅ 已落地（见代码） |
| P4 | §6.3 前端：OCR 上传/确认弹窗 + 用量提示 | ✅ 已落地（OcrImportModal + 自选页入口） |
| P5 | 后期：交易记录识别（§6.4） | 待实施 |

## 8. 风险与开放问题

| 项 | 说明 |
|---|---|
| ARK_API_KEY 配额 | 用户测试 Key 有限额；正式上线需独立计费账号或充值 |
| 火山方舟模型计费 | 图片输入按 token 计费，需监控用量（usage 表已埋点） |
| OCR 精度 | 基金代码 6 位数字，识别后须与东财基金列表校验（复用 useFundFuzzyMatcher 思路，后端校验） |
| 探市页登录态 | 探市是免登录页，登录态读取需 `useSupabaseAuth`（已存在） |
| 上传文件大小 | 需限制图片 ≤5MB，前端压缩后再传 |

## 9. 关联

- replan 基线：`explore-watchlist-replan-2026-08-08.md`
- issue：#821（探市缺陷）、#823（OCR+通用用量表）
- 基估宝参考：`D:\codes\jigu\app\components\Scan*.jsx`、`app\hooks\useScanImport.js`、`app\api\fund.js`（L2386 parseFundTextWithLLM、L2430 fetchOcrDailyRemaining）、`doc\edgeFunction\analyze-fund.ts`
