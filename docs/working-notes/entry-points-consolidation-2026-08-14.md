# 记账入口整合梳理与排期（2026-08-14）

> 触发：用户对"代码有点失控"的担忧，要求梳理手动记账 / 资产简记 / 截图导入 / 交割单导入四条入口，明确复用点，并调整导入功能排期优先级。
> 范围：评估 + 梳理 + 固化判断 + 拆 Issue；**不动业务代码**。
> 配套：MinerU 识别增强评估见 `mineru-alipay-ocr-eval-2026-08-14.md`；导入系统宪法见 `docs/spec/importer-architecture.md`。

---

## 1. 四条入口现状盘点（代码事实）

| 入口 | 前端位置 | 写库路径 | 是否走 ImportOrchestrator | 识别/兜底 |
|------|---------|---------|--------------------------|----------|
| 手动记账 | `views/asset/investment/manual/index.vue`（约 350 行，壳） | `components/QuickEntry/BuyForm.vue` / `SellForm.vue` 内 `handleSubmit` 直写 `createPosition` | **否** | 无 |
| 资产简记（全局托盘快捷买入） | `components/QuickEntry/BuyForm.vue`（约 900 行，含表单+提交） | 同上，组件内直写 `createPosition` | **否** | 无 |
| 截图导入 | `domains/ocr/views.py` + 前端导入页 | `ai_recognizer` → `process_buy_or_deposit` | **是** | ARK vision + guards 配额 + 二次校验 |
| 交割单导入 | `importer/parsers/*` + 前端导入页 | `ImportOrchestrator` 统一管线 | **是** | PDF 文本 / AI 识别 + `import_hash` 去重 |

### 关键发现（根因）
- 手动记账壳 `manual/index.vue` 已抽出 `useQuickEntrySubmit`（`composables/useQuickEntry.ts:29`），但**该 composable 只是壳**——其 `handleSubmit`（第 36 行）最终仍调用 `buyFormRef.value?.handleSubmit()`，即 BuyForm 组件内部自带、直写 `createPosition` 的旧逻辑。
- 资产简记（全局托盘）复用的就是同一个 `BuyForm.vue`，同样直写 `createPosition`。
- 因此：**后端 ImportOrchestrator / `process_buy_or_deposit` / guards / `import_hash` 去重已统一且成熟，但前端两条"手动类"入口完全没走它，各自直写 `createPosition`**。

### "代码失控感"的准确来源
不是后端失控，是**前端手动类入口与后端导入管线双轨**：
- 校验逻辑（如本次 #932 修的整手约束）后端 `trade_rules.validate_buy` 已正确，但前端 `BuyForm` 直写 `createPosition` 时校验走的是哪一层、是否与后端一致，需逐入口核对——两轨意味着同一业务规则可能两处实现、两处漂移。
- `BuyForm.vue` 约 900 行，表单 + 提交 + 兜底耦合在一个组件里，全局托盘和 manual 壳都依赖它，改动风险集中。

---

## 2. 整合判断（已与用户确认）

1. **后端没失控**：识别 / 解析 / 去重 / 写库（BaseRecognizer / ImportOrchestrator / `process_buy_or_deposit` / guards）已统一，新增源按 `BaseRecognizer` 模板接入即可（见 #921）。
2. **前端有重复 + 缺统一提交层**：手动记账、资产简记两条入口应收敛到**同一个前端提交适配层**，该层调用后端导入管线（而非直写 `createPosition`），使「前端手动录入」与「截图/交割单导入」走同一条写库 + 校验 + 去重路径。
3. **资产简记加截图导入难度**：后端低（接 `txn_import` scenario，复用现有 OCR 通道 + `process_buy_or_deposit`），UX 中（托盘需加图片选择 + 预览确认流）。

---

## 3. 复用点固化

- 手动记账 / 资产简记 → 接入 `ImportOrchestrator` 的 `txn_import` scenario（或等价 preview→confirm→write 管线），复用 `process_buy_or_deposit` 的整手校验 + `import_hash` 去重。
- 截图导入（无论来自资产简记托盘还是导入页）→ 复用 `ai_recognizer` + guards 配额 + 二次校验预览。
- 交割单导入 → 已有，稳定，作为"标杆管线"。

**目标态**：四条入口最终都汇入 `ImportOrchestrator` 写库，前端只负责"采集表单/图片/文件 → 调统一提交层 → 渲染预览确认"，不再各自直写 `createPosition`。

---

## 4. 排期优先级（用户裁决：导入是核心留存功能）

| 优先级 | 事项 | Issue | 理由 |
|--------|------|-------|------|
| P0 前排 | 导入稳定性（截图/交割单管线加固，含 guards 配额边界、长图限制） | 归入 #823 / #921 | 核心留存，任何识别源都依赖这条管线 |
| P0 | 前端统一提交层：手动记账 + 资产简记收敛到 ImportOrchestrator，移除双轨直写 | 新建（见 §5-1） | 消除"失控感"根因，校验规则单一来源 |
| P1 | 资产简记托盘加截图导入入口 | 新建（见 §5-2） | 后端低成本，增强采集便利性 |
| P2 | MinerU 识别增强（盲测 → 接入 `MinerURecognizer`） | 新建（见 §5-3，关联 #922/#823/#921） | 增强非阻断，先盲测再投入 |

---

## 5. 拆分 Issue 索引

所有 Issue 描述开头须加：`> 本 Issue 遵循 docs/spec/importer-architecture.md 规范`，并 `relates to` 关联项。

| # | Issue | 标题 | 象限 | 关联 |
|---|-------|------|------|------|
| 1 | #933 | 前端统一提交层：手动记账 + 资产简记收敛到 ImportOrchestrator（去双轨直写） | Q1:RED 重要紧急 | #823 #921 #932 |
| 2 | #934 | 资产简记托盘增加截图导入入口（接 txn_import scenario） | Q2:YELLOW 重要不紧急 | #823 #921 #933 |
| 3 | #935 | MinerU 精准解析接入支付宝截图识别增强（先盲测） | Q2:YELLOW 重要不紧急 | #922 #823 #921 |

（#932 买入校验根因修复已建并标 Q2，本梳理引用。#933~#935 均已加入 Project #3 并设象限、互相关联。）

---

## 6. 落地节奏

1. 定稿本梳理 + `mineru-alipay-ocr-eval-2026-08-14.md`（当前文档）。
2. 建 §5 的 3 个 Issue，挂 Project 象限字段，互相关联。
3. **不动任何业务代码**，等各 Issue 进入实现阶段再编码；P0 前端统一提交层优先于 P1 资产简记截图入口（后者依赖前者奠定的统一提交层）。
