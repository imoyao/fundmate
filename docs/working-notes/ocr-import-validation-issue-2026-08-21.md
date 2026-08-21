# AI 导入（粘贴文本）产品存在性校验 — Issue 草稿（2026-08-21）

> 性质：内部备忘（`docs/working-notes/`，屏蔽出构建，不对外）。
> 来源：2026-08-21 自选页 AI 导入弹窗评审。
> 用途：可直接粘贴进 GitHub 创建 issue。
> 关联组件：`frontend/src/components/QuickEntry/OcrImportModal.vue`；`frontend/src/api/ocr.ts`；后端 `api/ocr` 的 `parseImportText`。

---

## Issue — 粘贴文本导入必须校验产品存在性，未识别行返回错误信息

**标题**：`feat(ocr): 粘贴文本导入增加产品存在性校验，未识别行返回行级错误`

**Labels**：`backend`, `ocr`, `watchlist`, `P2`

### 背景

当前自选页「AI 导入 → 粘贴文本」只要输入 **6 位数字**就会被当作产品解析并入候选列表，未校验该代码是否真实存在。若用户输入不存在的代码（如 000000、错位代码），预览里会出现无法识别的"产品"，直接入库后是脏数据，且用户无感知——不符合《多多贝》设计语言"温暖、精致、可信赖"的原则。

### 需求

1. **预览时必须校验产品存在性**：粘贴文本点击「开始识别」后，后端对每一行代码做产品反查，**必须是系统能识别出的真实基金/股票**才能进入候选列表。
2. **未识别行返回错误信息**：若某行无法识别为产品（代码不存在 / 格式非法 / 名称无法反查），后端返回行级错误，前端在文本域下方用行内错误提示展示（`--color-danger-system` 危险色小字，不弹全局红提示），例如：`第 3 行「123456」未识别到对应产品，请检查`。

### 行为设计

- `POST /api/ocr/parse-import-text` 响应体扩展：
  - `items`: 仅包含**校验通过**的行（现状保留）
  - `errors`: `[{ line: number, code: string, message: string }]`（新增）
- 前端 `OcrImportModal`：
  - `items.length === 0 && errors.length > 0` → 显示行内错误（首个 error 或汇总），不进入候选列表
  - `items.length > 0 && errors.length > 0` → 候选列表展示有效行，同时在文本域下方提示"第 N 行未识别，已跳过"
  - 现有「整体未识别」行内提示保留作为兜底
- 配额语义：**校验失败（全部行无效）应不消耗/返还配额**，与现有一致（后端失败返还配额）。

### 验收标准

- 输入含不存在的 6 位代码：不进入候选列表，返回行级错误并在文本域下方展示
- 输入混合有效+无效行：有效行正常入候选，无效行有明确的行号提示
- 全部无效：不消耗配额，展示行内错误
- 单测覆盖：存在/不存在/格式非法/名称仅反查失败 四种场景

### 反链

- `frontend/src/api/ocr.ts`（`parseImportText`）
- `frontend/src/components/QuickEntry/OcrImportModal.vue`（`handleRecognize` / `textError`）
- 后端 `api/ocr/views.py`（`parse_import_text`）
- 《多多贝 设计语言》：错误提示走行内小字 + `--color-danger-system`，不做全局弹红
