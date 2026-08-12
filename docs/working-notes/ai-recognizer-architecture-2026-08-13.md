# AI 识别导入分层架构（2026-08-13）

> 性质：内部设计文档（`docs/working-notes/` 屏蔽出构建，不对外）。
> 触发：用户提出 OCR/AI 批量导入不应只在自选页使用——持仓页也要用（多识别「买入/确认日期、买卖类型、金额/份额」字段）；且当前实现是单场景硬编码，无法自然复用。要求参考模板导入（`services/importer/`）的分层架构做同样抽象，设计后再实施。
> 状态：**P1-P4 已实施（2026-08-13），P5 部分落地**（详见 §7/§8 实施记录）。实施跟踪见 issue（引用本文档）。
> 关联：`explore-watchlist-enhancement-2026-08-12.md`（OCR 功能设计）、issue #823（OCR 截图导入 + 通用用量表）、`explore-watchlist-replan-2026-08-08.md`（OCR 设计基线）。

---

## 1. 背景与动机

### 1.1 为什么分层

现有 AI 识别（`backend/app/services/ocr_service.py`）是**单场景硬编码**：

- 只识别「6 位代码 + 名称」→ 喂给自选页；
- prompt、JSON 解析、清洗（`_validate_items`）、类型反查（`_enrich_items`）、防护、模型调用全部写死在函数里；
- 持仓导入场景要复用（识别字段多出买卖类型/申请日/确认日/金额/份额），只能复制粘贴再改。

用户明确批评「说到哪做到哪」的工作方式，要求**先整体设计，识别域对称模板导入做分层**，再动手。

### 1.2 两个场景的共性与差异

| 维度 | 自选导入（watchlist_import） | 持仓导入（txn_import） |
|---|---|---|
| 输入 | 持仓截图 / 粘贴文本 | 持仓/交易截图 / 粘贴文本 |
| 识别字段 | code、name | code、name、business_type（买入/卖出）、trade_date（申请日）、confirm_date（确认日）、amount、shares、nav、fee |
| 用途 | 批量加入自选观察 | 生成交易记录入账（走现有模板导入的 commit 管线） |
| 确认交互 | 勾选导入 | 表格逐行核对修正后一键入库（金额/份额/日期 AI 可能识别错，**必须人工确认**） |
| 落地域 | `watchlist` 域 | `transactions`/`importers` 域（`StandardTransactionRecord` 管线） |

### 1.3 前置基础（2026-08-13 已落地）

设计前的几轮修复，成为本架构可直接吸收的基础：

- **模型降级**：`ARK_MODEL` 默认 `doubao-seed-2-0-mini-260428`（识别代码+名称这类简单结构化任务，mini 成本约为旗舰 pro 的 1/10，实测图片/文本均胜任）；
- **正则优先分层**：`parse_text` 先正则提取（`代码 名称` 简单排版零成本），复杂排版才调便宜模型兜底；
- **名称消歧**：证券与基金共用 6 位数字代码段（如 002910 = 股票「庄园牧场」or 基金「易方达供给侧改革混合」），`_name_hits` 结合 OCR 名称消歧，两表都命中默认基金；
- **场内基金优先于 Funds 表**：基金主表会收录 ETF（510300 沪深300ETF华泰柏瑞也在 funds 表），场内代码段（5/159/16x）优先判 EXCHANGE；
- **三层防滥用防护**：接口限流（`OCR_RATE_LIMIT_MAX`）、连续失败熔断（`OCR_MELTDOWN_*`）、全站 token 预算（`ARK_DAILY_TOKEN_BUDGET`）——按 `feature` 复用给 txn_import；
- **用量表**：`user_usage(user_id, feature, period_date, count, quota)` 已支持按 feature 独立限次，`txn_import` 为预留 feature 名；
- **前端组件化**：`ImageUploader`（点击/拖拽/剪贴板粘贴三入口，v-model 绑定 File）已从 OCR 弹窗抽出，持仓导入直接复用。

## 2. 现状：模板导入的分层范本

`backend/app/services/importer/` 已是最佳范式，AI 识别域对称复刻：

```
importer/
├── base.py          BaseImportParser（parse/validate 抽象 + 文件读取工具）
├── parsers/         平台解析器子类（standard/ths_stock/tiantian_fund/alipay_*），source 标识
├── registry.py      注册表：get_parser(source)，新平台只加一行注册
├── orchestrator.py  ImportOrchestrator：parse → validate → enrich → commit → metadata_update
├── records.py       StandardTransactionRecord（统一输出 dataclass）+ SBImportError
├── mappings.py      业务类型/中文映射
└── template_config.py
```

API：`POST /api/importers/parse`（上传解析预览）→ `POST /api/importers/confirm`（确认入库，去重哈希幂等）。

## 3. 目标架构

```
backend/app/services/
├── importer/                      # 模板导入（已有，不动）
└── ai_recognizer/                 # ★ AI 识别域（新增，对称 importer 设计）
    ├── base.py                    # BaseRecognizer 抽象基类（+ 模板方法）
    ├── registry.py                # 注册表：get_recognizer(key)，新场景一行注册
    ├── schemas.py                 # 各场景候选行 dataclass
    │   ├── WatchlistCandidate     #   code/name/type/market/venue/symbol
    │   └── TransactionCandidate   #   + business_type/dates/amount/shares/nav/fee
    ├── catalog.py                 # 类型/名称反查（证券/基金表消歧，从 ocr_service 抽出共享）
    ├── guards.py                  # 限流/熔断/token 预算 + user_usage 操作（从 ocr_service 抽出）
    ├── llm.py                     # _call_ark：模型/超时/重试/token 记录（抽出）
    └── recognizers/
        ├── watchlist_recognizer.py   # 自选场景（代码+名称）
        └── txn_recognizer.py         # 持仓场景（代码+名称+买卖+日期+金额+份额）
```

### 3.1 BaseRecognizer 抽象（对称 BaseImportParser）

```python
class BaseRecognizer(ABC):
    key: str                 # 注册标识：watchlist_import / txn_import
    feature: str             # 用量表 feature：ocr_import / txn_import
    max_items: int           # 单次最多返回条数（防单次调用爆量）

    @abstractmethod
    def build_prompt(self, kind: str) -> list[dict]:
        """场景化 prompt：含输出 JSON schema 约束（字段集由场景定）。"""

    @abstractmethod
    def extract(self, raw: str) -> list[dict]:
        """LLM 输出 → 结构化行（JSON 解析 + 字段映射/默认值补齐）。"""

    @abstractmethod
    def validate(self, items: list[dict]) -> list[dict]:
        """清洗校验候选行。
        自选：6 位代码 + 名称；持仓：代码 + 买卖类型 + 金额/份额/日期合法性。"""

    # ── 模板方法（子类不覆盖，通用流程）──
    def recognize_text(self, text: str) -> list[dict]:
        """文本识别：正则层（零成本）→ LLM 层（便宜模型兜底）→ validate。"""

    def recognize_image(self, image_bytes: bytes) -> list[dict]:
        """图片识别：LLM vision（便宜模型）→ extract → validate。"""

    def enrich(self, items: list[dict]) -> list[dict]:
        """类型/名称反查（catalog.py）：证券/基金表消歧，回填权威名称。"""
```

### 3.2 识别与提交分离（核心原则）

- **AI 识别域只产出候选行**（`schemas.py` 的 dataclass），不碰业务表；
- **提交由各业务域负责**：
  - 自选：watchlist 域逐条创建（现自选页 `OcrImportModal` 已如此，端到端不变）；
  - 持仓：复用 `importer/orchestrator.commit`——`TransactionCandidate` 映射为 `StandardTransactionRecord`，走既有去重哈希（`import_hash`）+ 交易入库 + 元数据回填管线；
- 好处：AI 域与业务表解耦，新增场景（如「收益/分红识别」）只需新识别器 + 映射到提交方。

### 3.3 用量 / 防护天然复用

- `user_usage` 表按 `(user_id, feature, period_date)` 独立限次；`ocr_import` / `txn_import` 互不影响；
- 限流 / 连续失败熔断 / 全站 token 预算抽到 `guards.py`，两场景共用同一层（token 预算全站共享，防费用失控）；
- API 按 `feature` 参数返回对应配额（见 §5）。

## 4. 场景识别器设计

### 4.1 watchlist_recognizer（自选，现逻辑迁入）

- prompt：输出 `[{code(6位数字), name}]`；
- 正则层：`(\d{6})\s*([\u4e00-\u9fa5A-Za-z]{2,12})` 提取「代码 名称」简单排版；
- 校验：`_validate_items`（6 位数字代码）；
- 反查：`catalog.enrich`（Securities → 场内代码规则 → Funds → 兜底 + 名称消歧）。

### 4.2 txn_recognizer（持仓，新能力）

- prompt：输出 `[{code, name, business_type(买入/卖出/申购/赎回), trade_date(YYYY-MM-DD), confirm_date, amount, shares, nav, fee}]`；
- 正则层：提取「代码 + 金额/份额」候选（代码段可靠，金额/份额需配合 LLM 或表回填）；
- 校验：代码 6 位数字；business_type 在枚举内；amount/shares/nav 数值合法；日期可解析；
- **确认日回填**（待用户拍板）：截图通常只有申请日（trade_date），确认日按现有 `fund-confirm-dates` 接口的 T+1 规则回填或留空由导入管线处理；
- 反查：`catalog.enrich` 同自选场景（识别标的是基金还是股票 → 决定份额/净值精度）。

## 5. API 设计（向后兼容）

现有 `/api/ocr/*` 语义泛化，`scenario` 参数驱动 registry：

```
POST /api/ocr/recognize?scenario=watchlist_import   # 图片识别（默认，兼容现状）
POST /api/ocr/parse?scenario=watchlist_import       # 文本识别（默认，兼容现状）
POST /api/ocr/recognize?scenario=txn_import         # 持仓图片识别
POST /api/ocr/parse?scenario=txn_import             # 持仓文本识别
GET  /api/ocr/usage?feature=ocr_import|txn_import   # 按 feature 查剩余次数
```

- 请求体不变（`image_base64` / `text`），响应按场景返回对应候选行数组；
- `scenario` 缺省 = `watchlist_import`（旧前端零改动）；
- 用量查询增加 `feature` 参数（缺省 `ocr_import`）。

## 6. 前端复用

- `ImageUploader` 组件（点击/拖拽/剪贴板粘贴）直接复用；
- 确认弹窗按场景配置：
  - 自选：候选列表勾选（现状 `OcrImportModal`）；
  - 持仓：表格逐行核对/修正（日期/买卖/金额/份额可编辑）→ 一键入库；
- 持仓确认弹窗可参考基估宝 `ScanImportConfirmModal`（区分已存在/新交易）+ 现有交割单导入预览表格。

## 7. 实施计划（P1-P5 状态，2026-08-13 更新）

| 阶段 | 内容 | 说明 | 状态 |
|---|---|---|---|
| P1 | `ai_recognizer/` 骨架：base / llm / guards / registry / catalog，从 ocr_service 平移 | 行为不变，纯重构；`ocr_service` 改为薄封装 | ✅ 已落地 |
| P2 | `watchlist_recognizer`：正则/mini/消歧/类型反查迁入 | 自选导入回归，`test_ocr_import.py` 29 用例保持绿 | ✅ 已落地 |
| P3 | `txn_recognizer`：持仓字段 prompt + extract + validate | 新能力；`tests/services/test_ai_recognizer.py` 18 用例（mock LLM） | ✅ 已落地 |
| P4 | API 泛化（scenario 参数）+ 前端持仓确认弹窗 | 持仓导入闭环（复用 `/api/importers/confirm` 管线） | ✅ 已落地 |
| P5 | 统一导入抽象（可选） | 实测重叠真实存在 → 采用「管线级共享」而非顶层统一抽象 | ✅ 部分落地 |

### 实施记录（2026-08-13）

**P1+P2（纯重构，已回归）**
- `ai_recognizer/` 按 §3 落地：base（BaseRecognizer 模板方法 + `extract_json_array`/`is_valid_code` 共享工具）、guards（用量/限流/熔断/token 预算，原样迁出）、llm（`call_llm` 泛化：system_prompt 按场景传入）、catalog（`enrich` 类型/名称反查 + `name_hits` 消歧；**改为 `dict(it)` 保留场景额外字段**，供 txn 透传）、registry（`get_recognizer(scenario)`，缺省/未知回退 watchlist_import，对称 importer/registry 一行注册）、schemas（WatchlistCandidate / TransactionCandidate 数据契约）。
- `ocr_service.py` → 薄外观层：保留旧 API（`recognize`/`parse_text`/`_enrich_items`/`_name_hits`/guards 全符号），行为不变；views 与旧测试零改动（白盒测试改为打 `guards`/`llm` 模块，因状态已迁权威模块）。
- `catalog.enrich` 保持函数内懒导入 `SessionLocal`，测试隔离无需额外打补丁；conftest 改打 `ai_recognizer.guards.SessionLocal`。

**P3（新能力）**
- `txn_recognizer`：prompt 输出 code/name/business_type/trade_date/confirm_date/amount/shares/nav/fee；中文买卖词归一（买入/申购/认购→buy，卖出/赎回→sell，现金分红/红利再投资）；日期容错（斜杠/缺段→`YYYY-MM-DD`，非法清空并记 warnings）；validate 要求代码 6 位 + 类型在枚举内 + 金额/份额至少其一。
- 正则层：`代码 名称? 买卖 金额` 简单排版零成本，其余自然语言夹杂排版落入 LLM（便宜模型）。

**P4（API 泛化 + 前端提交闭环）**
- 后端：`/api/ocr/recognize|parse` 新增请求体 `scenario`（缺省 watchlist_import 旧前端零改动）；`/api/ocr/usage?feature=ocr_import|txn_import` 按 feature 独立限次；txn 场景返回与 `parse_and_preview` **同构的预览行**（`op_type`/`op_type_label`/`trade_date`/`quantity`/`price`/`amount` 等），前端零改造直接复用既有「预览与修正」表格。
- **P5 部分的管线级共享（importer 轻量增强，行为不变）**：`records.compute_record_hash`（哈希口径抽为模块函数，`BaseImportParser.compute_import_hash` 委托）、`ImportOrchestrator.preview_records`（外部候选记录 → enrich + 哈希 + 行转换 + 去重标记），AI 提交复用 `commit_from_preview` 既有入库链路。未做「AI 与模板解析共用顶层超类」——两者关注点不同，共享边界就是预览/入库管线。
- 前端：`src/api/ocr.ts` 增加 scenario 参数与 `OcrTxnRow` 类型；导入页（`investment/import`）新增「AI 截图/文本识别」入口与 `AiImportModal`（复用 `ImageUploader`，图片/文本双入口，展示 txn_import 独立额度），识别行灌入既有 `previewData` 预览表格逐行人工核对 → 一键 `/api/importers/confirm`。

## 8. 待用户拍板的决策点（2026-08-13 已按此执行，可推翻）

1. **P5 统一抽象**：不再做顶层统一抽象——AI 域与模板解析域保有各自抽象（BaseRecognizer / BaseImportParser），共享收敛到预览/入库管线（`orchestrator.preview_records` + `compute_record_hash`），理由：识别与解析关注点不同（结构化抽取 vs 表格式映射），强行统一反而引入空泛中间层。
2. **确认日回填**：本版不做 T+1 自动回填。候选行保留 trade_date（申请日，截图通常只有它）；confirm_date 缺失的**预览行以申请日入账**（前端表格 trade_date 列可改），用户核对时可直接改成确认日。若后续发现大量按确认日对净值的需求，再加 `fund-confirm-dates` T+1 回填。
3. **持仓确认交互**：AI 出表格（预览行）→ 导入页既有预览表格逐行核对/修正（日期/买卖/金额/份额可编辑）→ 一键确认走 `/api/importers/confirm`；**无自动入库**，所有 AI 识别交易必须人工确认。
4. **scenario 传参位置**：recognize/parse 走请求体 JSON 字段（Pydantic 校验），usage 走查询参数 `feature`——与设计稿 §5 的查询参数略有出入，实现以此为准。


## 9. 关联

- 基线：`explore-watchlist-enhancement-2026-08-12.md` §6（OCR 后端设计）、`explore-watchlist-replan-2026-08-08.md` §9.6
- issue：#823（OCR 截图导入 + 通用用量表）、#919（反馈站）
- 模板导入范本：`backend/app/services/importer/`（base / parsers / registry / orchestrator / records）
- 待办：P1-P5 实施完成后关闭实施跟踪 issue，并在 §7 打勾
