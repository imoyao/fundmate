# 账单导入页：UX 问题与商业化判断（评审）

> 2026-08-15 评审备忘。基于代码现状（`frontend/src/views/asset/investment/import/`）、
> 后端 OCR 成本护栏（`backend/app/services/ai_recognizer/guards.py`）、
> `docs/spec/pricing-tier.md`、以及既有 issues（#823/#826/#921/#929/#934/#935/#786）对一份
> 导入页优化讨论做一次判断，并拆出可落地的原子 issue。
> 本文件为内联评审：所有待办以 issue 草案形式内嵌，已建的原子 issue 在文末登记并引用既有 issue。

## 1. 一句话结论

这份优化讨论写得不错，但**它是在不了解已上线的 OCR 成本护栏与既有付费分层规范的前提下写的**。
结论分三层：

- **已实现、不要重建**：AI 识别的成本控制（每日配额 / 限流 / 熔断 / token 预算 / 用量条 / 5MB 上限）后端和前端都做完了，个人开发者成本爆炸的担心已被缓解（约 74 元/月 @1000 用户）。
- **真缺口、现在做**：三张卡片与账户选择视觉脱节、步骤条与标题冗余、图片未压缩、卡片文案静态——这几项工程上确实还没做，且成本低、体感强。
- **商业化待决策、不要现在硬上**：「Pro 徽章 + 付费墙」里"配额"已落地，但"Pro 会员层级"产品尚未定稿；按 `pricing-tier.md` 准则 3（免费→付费禁止），现在打 Pro 硬墙有踩雷风险，应作为独立定价工作流后置。

## 2. 现状核对（已实现部分，附引用）

| 讨论中的主张 | 实际现状 | 证据 |
| --- | --- | --- |
| AI 截图识别会让服务器成本爆炸 | 已建多层护栏：每日配额 5/用户/feature（`OCR_DAILY_QUOTA`）、每分钟限流 3（`OCR_RATE_LIMIT_MAX`）、连续失败 5 次熔断 30 分钟（`OCR_MELTDOWN_*`）、全站 token 预算 30 万/日（`ARK_DAILY_TOKEN_BUDGET`，关联 #823） | `backend/app/services/ai_recognizer/guards.py` |
| 需要"免费体验券/配额" | 已实现：前端用量条显示"今日持仓识别额度 剩余 X / 5 次"，三态（正常/紧张/用尽），按钮用尽即禁用，失败返还配额 | `frontend/src/views/asset/investment/import/components/AiImportModal.vue` |
| 图片上传限制 | 已实现：提示"文件不超过 5MB" | `ImageUploader` tip + 上传校验 |
| 手动录入应永久免费 | 已对齐：`pricing-tier.md` 把"核心记账、导入导出"列为免费不限次；OCR 为付费候选、免费兜底 5/天 | `docs/spec/pricing-tier.md` §1/§2/§5 |
| 成本可承受 | 单次 ≈ 0.0037 元；1000 用户 × 5/天顶格 ≈ 555 元/月，现实 20% 活跃 ≈ 74 元/月 | `docs/spec/pricing-tier.md` §5 |

> 因此讨论里"第四部分（AI 成本警示）+ 配额制 + 5MB 限制"属于**对已建基础设施的重新推导**，不应再投入工程重建。

## 3. 待办 vs 已实现对照（真缺口）

| 讨论点 | 现状 | 判定 | 内联 issue |
| --- | --- | --- | --- |
| 一、卡片与下拉框脱节：默认禁用、选中亮起 | AI/上传卡点击有 toast 校验；但 `goToManualEntry`/`goToLiabilityForm` 直接 `router.push` 不校验账户；三卡常驻可点、视觉未联动 | **真缺口，做** | I-1 |
| 一、卡片文案按账户类型动态变化 | 静态文案；但 `ledgerType`/`ledgerTypeLabel`/`ledgerTypeMap` 数据可用 | **真缺口，做** | I-2 |
| 二、步骤条与标题冗余 | `steps[0].title="选择导入账户"` 与页面 `h3` 标题重复；el-steps 默认高度偏高 | **真缺口，做** | I-3 |
| 三、卡片宽度/内边距呼吸感 | 当前 `.mode-card { width:240px; padding:32px 24px }`，垂直内边距已接近 `--space-loose` | **微调，随 I-3 顺带** | I-3 |
| 四、图片压缩降本 | `ImageUploader` 仅 5MB 上限，无压缩 | **真缺口（新增成本优化），做** | I-4 |
| 四、Pro 徽章 + 软付费墙 | 配额已落地；但产品无"Pro"层级，且 `pricing-tier.md` 准则 3 禁"免费转收费" | **后置决策，不现在做** | I-5（决策项） |

## 4. 内联待办 Issues（草案）

### I-1 `feat(import): 三张卡片与账户选择联动（未选时禁用灰显，选中后亮起可点）`
- 现状：上方账户下拉框（`selectedLedgerId`）与下方三张卡片（`手动录入`/`AI 截图识别`/`负债录入`）视觉脱节。
  `openAiImport` 与上传卡点击时有 `ElMessage.warning("请先选择…")` 校验，但
  `goToManualEntry`（跳转 `/asset/inventory/investment/manual`）与 `goToLiabilityForm`（跳转 `/asset/asset-entry`）
  直接 `router.push`、**不校验账户**；三卡常驻可交互态。
- 期望：当 `selectedLedgerId` 为空时，三张 `.mode-card` 设 `:disabled` 且 `opacity:0.5`（灰显）；
  选中账户后亮起为可点。这与讨论"默认禁用、选中亮起"一致，且不引入硬墙（仅视觉+交互耦合）。
- 关联：`#823`（OCR 配额上下文）、本评审。

### I-2 `feat(import): 卡片文案按所选账户类型动态变化（股票→交割单 / 基金→对账单）`
- 期望：选中账户后，卡片标题/副标题按 `ledger_type` 动态变化，例如股票账户→"导入股票交割单"、
  基金账户→"导入基金对账单"、负债账户→"录入负债明细"。数据可用 `ledgerType`/`ledgerTypeLabel`
  （`useImportWizard.ts`）。提升"聪慧感"，与讨论一致。
- 关联：`#823`、I-1（同组件改动，建议同一分支连续提交）。

### I-3 `fix(import): 步骤条压扁 + 主标题去冗余（改为"交易流水导入"）`
- 现状：页面 `h3.import-group-title` 为"选择导入账户"，而 `el-steps` 第 0 步 `steps[0].title` 也是
  "选择导入账户"，二者重复；el-steps 默认高度偏高。
- 期望：主标题改为 `交易流水导入`；el-steps 改为纯文字小步骤条或高度压缩约 30%，步骤文案
  `1 选择账户 / 2 上传文件 / 3 预览修正 / 4 完成`。顺带把 `.mode-card` 宽度 `240px→320px`、
  保持 `padding` 规范（接近 `--space-loose`），父容器 `justify-content:center` 居中。
- 关联：`#786`（导入系统开发决策）、`#823`、本评审 §3。

### I-4 `feat(uploader): 上传前前端压缩图片（≤1080p / quality 0.8）降低 AI token 成本`
- 现状：`ImageUploader` 仅限制文件 ≤5MB，未做画质压缩。AI 识别按 token 计费，高清大图直接推高输入成本。
- 期望：上传前用 `canvas` 将图片长边压缩至 ≤1080px、`quality≈0.8`，降低上传带宽与 AI 输入 token。
  这是讨论"规避图片大、单次成本高"的工程落地，且是**已建护栏之外的额外降本**。
- 关联：`#823`（成本护栏）、`#935`（MinerU 支付宝截图增强，共用上传链路）。

### I-5 `product: 导入页 AI 识别"Pro/付费锚点"呈现方案（依赖 pricing-tier 定稿，勿提前打 Pro 标签）`
- 判断：OCR 配额（免费 5/天）已由 `#823`/`guards.py` 实现，前端用量条已显示"剩余 X/5 次"，
  **成本控制已具备**；但产品尚无"Pro"会员层级（`pricing-tier.md` 仅把 OCR 列为"付费候选"）。
- 建议（对齐讨论的"得体配额制"）：
  1. **现在不要新增"Pro"徽章/硬墙**：避免把当前免费路径转为收费，违反 `pricing-tier.md` §1 准则 3
     （免费→付费禁止）。保留现有"免费额度"体面 UX——无锁图标、仅浅灰提示剩余次数，与讨论一致。
  2. **免费层维持每日 5 次**：不降为"每月 5–10 次"（每日更控成本，且符合 §5 成本测算）；
     手动 CSV 录入永久免费、无配额（对齐准则 1/3）。
  3. **"Pro 升级锚点"作为独立定价工作流后置**：待 `pricing-tier.md` 与品牌边界
     （`docs/design/brand-v1.7.md`）、`#826`（付费/免费分层定稿）明确会员层级后，再在用量用尽时
     呈现轻量升级引导。重度用户自然转化，符合讨论"漏斗"思路。
- 关联：`#826`、`#823`、`docs/spec/pricing-tier.md`、`docs/working-notes/watchlist-paid-features-discussion-2026-08-14.md`。

## 5. 商业化判断（给产品决策者的补充）

- 讨论的核心矛盾——"让用户进来" vs "成本别被打穿"——**已被现有配额制解决**，无需硬墙。
- 配额节奏建议保持**每日**而非每月：每日 5 次对个人开发者更可控，且 §5 成本测算基于每日口径；
  若未来上线付费层，用"更高/月度/无限额度"作为升级卖点，而非削减现有免费每日额度。
- "手动录入永久免费"与 `pricing-tier.md` 完全自洽，是转化兜底，不要在其上设任何门槛。

## 6. 关联引用

- 代码：`frontend/src/views/asset/investment/import/index.vue`、`composables/useImportWizard.ts`、
  `components/AiImportModal.vue`、`frontend/src/components/ImageUploader/index.vue`
- 后端：`backend/app/services/ai_recognizer/guards.py`、`backend/app/domains/usage/models.py`
- 规范：`docs/spec/pricing-tier.md`
- 既有 issues：`#823`（OCR 配额）、`#921`（OCR 分层架构）、`#929`（持仓导入复用）、
  `#934`（资产简记托盘截图入口）、`#935`（MinerU 支付宝截图增强）、`#826`（付费/免费分层定稿）、
  `#786`（导入系统开发决策）
- 相关讨论：`docs/working-notes/mineru-alipay-ocr-eval-2026-08-14.md`、
  `docs/working-notes/watchlist-paid-features-discussion-2026-08-14.md`

## 7. 待建 Issues（内联草案，尚未建 GitHub issue）

> 下列原子 issue 草案内联于本文 §4，符合"文档与 issues 内联"的要求。是否建为 GitHub issue 由用户定夺；
> 若创建，正文首行标注 `[AI 创建] · AI-Created-By: CodeBuddy AI · 2026-08-15`，并引用 §6 既有 issue。

- I-1：`feat(import): 三张卡片与账户选择联动（未选时禁用灰显，选中后亮起可点）`
- I-2：`feat(import): 卡片文案按所选账户类型动态变化（股票→交割单/基金→对账单）`
- I-3：`fix(import): 步骤条压扁 + 主标题去冗余（改为"交易流水导入"）`
- I-4：`feat(uploader): 上传前前端压缩图片（≤1080p/quality 0.8）降低 AI token 成本`
- I-5：`product: 导入页 AI 识别"Pro/付费锚点"呈现方案（依赖 pricing-tier 定稿，勿提前打 Pro 标签）`
