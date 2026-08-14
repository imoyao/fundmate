# MinerU 接入支付宝交割单识别 —— 评估与实施规划（2026-08-14）

> 触发：用户发现 MinerU 云 API（Agent 轻量免 Token / 精准解析需 Token），拟增强支付宝交割单导入识别。
> 范围：本次只做**评估 + 规划**，不写接入代码。结论需用户裁决分叉点（见 §7）。
> 现状基线：支付宝交割单导入已有两条路径 + 完整 AI 防护层 + 用户自带 key 规划（见 §2）。

---

## 1. 要解决的问题

用户从支付宝导出交割单往往只截**图**（手机截图 / 长图），而非规整 PDF。现有截图路径依赖火山方舟 ARK vision 多模态模型直接"看图说话"，存在：

- 表格密集的长截图识别不稳定（行错列、金额错位）；
- 支付宝交割单含大量表格/数字，通用 vision 模型在结构化抽取上不如专用文档解析器；
- token 成本高（截图信息密度大）。

MinerU 精准解析 API 专为**文档 OCR + 表格/公式结构化**设计，理论上比通用 vision 更适合"截图→结构化交易行"。

---

## 2. 现状盘点（代码事实）

### 2.1 支付宝交割单现有两条路径
| 路径 | 文件 | 输入 | 技术 | 成本 | 确定性 |
|------|------|------|------|------|--------|
| PDF 文本解析 | `importer/parsers/alipay_pdf.py` | 支付宝"基金交易明细"PDF | pdfplumber 提取原生文本表格 | 零 | 高（表格规整） |
| 截图/文本识别 | `ai_recognizer/recognizers/txn_recognizer.py` + ARK vision | 截图/粘贴文本 | 正则层 + ARK doubao vision LLM 兜底 | 按 token | 低（需人工核对） |

### 2.2 AI 识别防护层（已落地，`ai_recognizer/guards.py`）
- 每用户每日配额 `OCR_DAILY_QUOTA`（默认 5 次，存 `UserUsage` 表，按 feature 区分 ocr_import / txn_import）；
- 每分钟接口限流 `OCR_RATE_LIMIT_MAX`（默认 3）；
- 连续失败熔断（5 次 → 冷却 30 分钟）；
- 全站 token 预算 `ARK_DAILY_TOKEN_BUDGET`（默认 30 万 token/日，费用护栏，issue #823）。

### 2.3 用户自带 key 规划（已建，`docs/spec/integrations-plan.md`）
- 规划 `Credential` 表：AES-256-GCM 信封加密、family_id 归属、掩码展示；
- 系统默认 key（env）与用户 key 走**同一调用逻辑、数据面隔离**；
- 审计日志 `AuditLog`（L1）+ 家庭共享；
- 已是 P2 路线图项（原 P2-30 扩展）。

**结论：接入 MinerU 不是从零，防护层 / key 管理地基已大半存在，复用即可。**

---

## 3. MinerU 两模式 vs 现有 ARK vision 能力对比

| 维度 | ARK vision（现有） | MinerU Agent 轻量（免 Token） | MinerU 精准解析（需 Token） |
|------|------|------|------|
| 本质 | 通用多模态问答 | 文档转 Markdown（轻量） | 文档 OCR+表格/公式结构化（高精度） |
| 输出 | JSON 自由格式（靠 prompt） | Markdown | Markdown / 含图表格的完整 Zip |
| 单文件限制 | 取决于图片大小 | ≤10MB / ≤20 页 | ≤200MB / ≤200-600 页 |
| 表格/数字精度 | 中（通用模型） | 中 | 高（专用解析） |
| 免费策略 | 按方舟 token 计费（平台付费） | 完全免费、IP 限频 | 每日 1000-2000 页高优先级免费，Token 90 天有效期 |
| 适用 | 任意截图/文本 | 小文档快速预览 | 生产/批量/高精度 |

**关键判断**：支付宝交割单截图 = 表格密集型文档，**结构化抽取精度上 MinerU 精准解析 > ARK vision**。但 MinerU 输出是 Markdown，仍需一层"Markdown→交易行"解析（可复用现有 `txn_recognizer` 的正则层 + LLM 清洗，或写轻量 Markdown 表格解析器）。

---

## 4. 合理性评估

**值得做，但定位为"ARK vision 的增强替代 / 补充"，不是推倒重来**：
- 对截图类交割单，MinerU 精准解析精度更高、token 成本可能更低（文档解析比通用 vision 省 token）；
- 复用现有 guards 配额 + 用户 key 规划，增量成本低；
- 仍须保留"用户二次校验"兜底（§5），与现有批量导入一致。

**风险/不确定（须实测才能下结论）**：
- 效果对比需盲测：拿 10-20 张真实支付宝截图，分别跑 ARK vision 与 MinerU，比字段准确率；
- MinerU 免费额度随 Token（90 天）过期、政策可能调整——平台维度用量不能依赖"长期免费"；
- MinerU 输出 Markdown 后多一层解析，端到端准确率需重新评估。

---

## 5. 必带兜底（用户明确要求，不可省略）

无论哪种识别源，AI 结果**一律不直接入库**：
1. 识别产出候选交易行 → 前端预览表格（代码/名称/买卖/金额/份额/日期）；
2. 逐行人工核对，warnings 字段标红可疑项（日期/金额识别不出已清空者）；
3. 用户确认/修正后 `process_buy_or_deposit` 等走既有写库 + `import_hash` 去重；
4. 与现有批量导入流程完全一致，不另立旁路。

---

## 6. 收费 / 免费分层与配额模型（用户未想清部分，给出方案）

### 6.1 三种用户层级
| 层级 | key 来源 | 用量归属 | 限额策略 |
|------|---------|---------|---------|
| 免费体验用户 | 平台默认 Token（MinerU 或 ARK） | 消耗**平台总池** | 严格限量（如每用户 2 次/日，复用 `OCR_DAILY_QUOTA` 但调低体验档 quota） |
| 收费用户 | 平台付费 Token（高优先级/按量） | 消耗**平台总池**（已付费） | 较高配额（如 20-50 次/日），按套餐分级 |
| 自带 key 用户 | 用户自己在 `Credential` 录入的 MinerU/ARK Token | 消耗**用户各自额度** | 平台只限接口频控（防刷服务器），不限业务次数（用户自有额度兜底） |

### 6.2 配额模型核心问题：平台总池 vs 每 key 子配额
**建议采用"平台总池 + 每用户子配额"双层**：
- **平台总池**（费用护栏）：MinerU/ARK 平台 Token 的每日免费/付费额度是**集中**的，设全站日预算（类比现有 `ARK_DAILY_TOKEN_BUDGET`），超限全站熔断——保护平台不被刷爆；
- **每用户子配额**：在总池内给每用户分日配额（`UserUsage.quota`），免费体验档低、收费档高；
- **自带 key 用户**：脱离平台总池，只受接口频控（服务器资源护栏），业务次数由用户自己 Token 额度决定。

即：**平台用量 = 总池（费用）∩ 每人子配额（公平）；用户自带 key = 仅频控（资源）**。这与现有 guards 三层防护一脉相承，只是把"key 来源"作为第四个维度接入 `assert_available`。

### 6.3 多 key 管理（用户后期 key 很多分不清用哪个）
沿用 `integrations-plan.md` 的 `Credential` 表，但需补**用途标签**避免混乱：
- `Credential` 增加 `scope`/`usage_tag` 字段（如 `alipay_ocr` / `watchlist` / `txn_import`），用户录入时选"这个 key 用来干嘛"；
- 调用时按 feature 匹配对应 scope 的 key（如交割单识别只挑 `usage_tag='alipay_ocr'` 的凭证），而非让用户手动指定；
- 前端凭证管理页按 usage_tag 分组展示，解决"key 太多分不清"。
- 同 scope 多 key 时按 `is_active` + 最近失败冷却做简单轮询/降级（MVP 可先做"首个 active"，不做负载均衡）。

---

## 7. 待用户裁决的分叉点

1. **先做效果盲测还是直接排期开发？** 建议先盲测（拿真实截图对比 ARK vs MinerU 准确率）再决定投入，避免为"可能更好"买单。
2. **MinerU 用平台 Token 还是强制用户自带？** 免费体验可用平台 Token（限额），收费/高频强制自带 key（§6.1）。是否同意？
3. **MinerU 模式选择**：截图多为长图（可能超 20 页限制）→ 轻量免 Token 版大概率不够，需精准解析（Token）。是否接受"精准解析"的 Token 90 天续期运维成本？
4. **Credential 增加 usage_tag** 是否纳入 integrations-plan 的本期范围，还是后置？
5. **新 Issue 定位**：建议新建 `mineru-ocr-enhancement` issue，关联 integrations-plan（#P2-30 扩展）与现有 ocr 防护层（#823），象限 Q2（重要不紧急，属增强非阻断）。

---

## 8. 推荐落地顺序（若推进）

1. **盲测对比**（0.5d）：真实支付宝截图 ×N，ARK vs MinerU 字段准确率，出数据再决策；
2. 若 MinerU 胜出：在 `ai_recognizer` 新增 `MinerURecognizer`（实现 `BaseRecognizer`），复用 guards + txn_recognizer 的 Markdown→行解析；
3. `Credential` 补 `usage_tag`，调用按 feature 选 key；
4. 配额双层（总池 + 子配额）接入 `assert_available`；
5. 前端：凭证管理页按 tag 分组 + 交割单识别入口的体验/收费/自带 key 三档。
