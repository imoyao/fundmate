# 账本精灵对话 Agent 原子 Issue 草稿（2026-08-17）

> 性质：内部备忘（`docs/working-notes/`，屏蔽出构建，不对外）。
> 来源：决策 D19（2026-08-17）+ `agent-guardrail-layer-design-2026-08-17.md` §9 实施计划。
> 用途：可直接粘贴进 GitHub 创建 issue；每个 issue 独立承载一件事，用引用串联，不耦合。
> 象限：全部 **Q2（重要不紧急）**。护栏层 4 个可立即开做（与 Q1 未决正交）；功能层 2 个排 Q1 闭环后早赢；行为解读排后。
> 关联文档：`docs/spec/roadmap.md` §2.7；`docs/working-notes/agent-guardrail-layer-design-2026-08-17.md`。

---

## Issue 1 — 账本精灵护栏子包骨架 + L3 输出词法过滤（G1+G2）

**标题**：`feat(guard): ai_recognizer/safety 包骨架 + L3 输出词法过滤`

**象限**：Q2 ｜ **Labels**：`ai`, `guardrail`, `backend`

**正文**：

### 背景
账本精灵对话 Agent 的最大风险是越界（预测/建议/荐股）。护栏设计已定型（`agent-guardrail-layer-design-2026-08-17.md` §7），本 issue 落地最硬的 L3 输出侧词法过滤 + 包骨架。

### 目标
1. 新建 `backend/app/services/ai_recognizer/safety/` 包，含 `intent_guard.py` / `output_filter.py` / `repeat_tracker.py` 三个**纯函数**模块骨架（先不接模型即可验证）。
2. `output_filter.py` 实现 §7.2 的 R1–R10 规则（涨跌方向预测 / 买卖时点 / 弱建议 / 评级荐股 / 收益承诺 / 机械止损止盈 / 主观评价 / 伪装成分析的建议 / 假设性诱导 / 绝对化断言），含白名单豁免（「不建议」类、历史事实陈述放行）与预置免责声明模板常量。
3. 过滤器输出 `(blocked: bool, hit_rules: list[str], sanitized_text: str)`，在 `llm.py` 返回链路末端统一调用（对话 Agent 模式）。

### 验收标准
- `output_filter` 为无状态纯函数，单测覆盖：每条规则正例拦截、白名单误伤放行、多规则命中合并免责。
- 命中即替换为对应免责模板，绝不透传越界原文；高频命中记录 `guard_hit` 审计日志（类别/规则/脱敏片段）。
- 不引入编排框架；不触碰 DB。

### 反链
`docs/spec/roadmap.md` §2.7；`agent-guardrail-layer-design-2026-08-17.md` §7/§8。

---

## Issue 2 — 输入侧意图护栏 + 会话内重复追问检测（G3+G4）

**标题**：`feat(guard): 输入侧意图护栏 intent_guard + 重复追问检测 repeat_tracker`

**象限**：Q2 ｜ **Labels**：`ai`, `guardrail`, `backend`

**正文**：

### 目标
1. `intent_guard.py` 实现 §6 的 A（意图分类：数据查询/通用知识/预测/建议/情绪施压）、B（正则模式命中越界句式）、D（情绪+建议复合插风险提示）、E（通用知识补数据检测，协同 output_filter）。
2. `repeat_tracker.py` 实现 C：同一问题归一化后连续追问 N 次 → 强制标准话术，会话内状态（内存或 Redis）。
3. 命中预测/建议类直接阻断不进模型，比 L3 更早更省 token。

### 验收标准
- 意图分类与正则命中单测覆盖 A/B/D/E 各场景与边界（含「伪装成分析的建议」）。
- `repeat_tracker` 归一化（去空格/标点/全半角）正确，N 次阈值可配置，标准话术替换生效。
- 预测/建议类消息被前置拦截，不调用 LLM。

### 反链
同上；`agent-guardrail-layer-design-2026-08-17.md` §6。

---

## Issue 3 — per-user token 配额 + Serverless 限流（G5）

**标题**：`feat(guard): guards.py per-user token 配额 + 网关/Redis 限流`

**象限**：Q2 ｜ **Labels**：`ai`, `guardrail`, `backend`, `infra`

**正文**：

### 背景
`guards.py` 现有 `ARK_DAILY_TOKEN_BUDGET=300000` 无 per-user 维度，且 SCF 多实例下计数器按实例重置（I1 债）。

### 目标
1. 新增 per-user 配额表（或 Redis key），记录各用户 token 消耗。
2. 网关层拦截超配额请求。
3. **隐蔽坑（必读）**：限流计数**禁止写 SCF 实例内存字典**（并发多实例互相独立会击穿），须走 API 网关或云 Redis 存消耗。

### 验收标准
- per-user 维度配额生效，单用户超额即拦截并返回明确错误信封。
- 多实例并发下配额不被击穿（用 Redis/网关验证，非本地 dict）。
- 不破坏现有全站预算逻辑。

### 反链
`agent-guardrail-layer-design-2026-08-17.md` §8；roadmap §2.7.3。

---

## Issue 4 — registry 意图路由 + system prompt 注入 L1 铁律（G6+G7）

**标题**：`feat(guard): registry 意图路由 + 账本精灵 system prompt 注入 L1 铁律`

**象限**：Q2 ｜ **Labels**：`ai`, `guardrail`, `backend`

**正文**：

### 目标
1. `registry.py` 引入意图路由：A 前置分类结果决定走「查询工具链」还是「直接拦截/标准话术」（对话精灵用）。
2. 账本精灵 system prompt 注入 L1 数据真实性铁律（复用同花顺 `AGENTS.md` 原文）+ can/cannot 边界清单。

### 验收标准
- 路由按前置分类正确分发，预测/建议类不进入查询链路。
- system prompt 含「工具先行、数据为真、严禁编造」「宁可说不知道」等铁律与 can/cannot 清单。
- 与现有 `watchlist_import` / `txn_import` scenario 静态注册不冲突。

### 反链
`agent-guardrail-layer-design-2026-08-17.md` §8；roadmap §2.7。

---

## Issue 5 — 快速记账对话入口（NLP→importer + 前端逐行确认）

**标题**：`feat(agent): 账本精灵快速记账对话入口（NLP 识别 + 逐行确认）`

**象限**：Q2 ｜ **Labels**：`ai`, `agent`, `frontend`, `backend`

**正文**：

### 背景
后端识别已 ~80%（`ai_recognizer` 识别模式），缺前端「精灵输入框」与逐行确认 UI。

### 目标
1. 前端新增对话入口（精灵输入框），自然语言 → 后端识别为交易候选行。
2. 识别出的日期/金额/份额**前端逐行核对**（L0 硬约束：写走 importer，无自动入库后门）。
3. 复用现有 importer 管线，不新建写入路径。

### 验收标准
- 用户用自然语言描述一笔买卖，系统生成候选行并逐行展示待确认。
- 确认后经 importer 入库，与现有记账数据一致；未确认绝不入库。
- 不破「禁止 skip_lot_check 类后门」铁律。

### 反链
roadmap §2.7.1；`ai-recognizer-architecture-2026-08-13.md`。

---

## Issue 6 — 持仓/表现自然语言查询层（NL→工具链）

**标题**：`feat(agent): 持仓/表现自然语言查询层（NL→summary_service/performance）`

**象限**：Q2 ｜ **Labels**：`ai`, `agent`, `backend`

**正文**：

### 背景
数据 ~60% 齐（`summary_service`/`performance` 已算持仓/收益），缺自然语言查询层。

### 目标
1. NL → 工具链：解析用户问句，调用查持仓 / 算 XIRR / 查净值等只读工具。
2. 数值全走代码算，模型只做降维描述（趋势/对比），绝不报精确数值序列。
3. **隐蔽坑（必读）**：工具函数取数，只把算好的 4~5 个指标值传给模型，不重传全量历史记录（控 token 成本，roadmap §2.7.3）。

### 验收标准
- 用户用自然语言问「我这半年表现怎么样」「某基金持仓多少」，系统返回基于代码算出的准确数据 + 模型自然语言描述。
- 所有数值来自工具返回，模型输出可溯源到工具结果。
- 不引入新数据源。

### 反链
roadmap §2.7.1/§2.7.3；`agent-guardrail-layer-design-2026-08-17.md` §5（L2 工具约束）。

---

## Issue 7 — 持仓行为解读 / 诊断叙事

**标题**：`feat(agent): 持仓行为解读 / 诊断叙事（排后）`

**象限**：Q2 ｜ **Labels**：`ai`, `agent`, `backend`

**正文**：

### 背景
四个功能中投入最大（全新 ~20%），依赖 Issue 1–6 的护栏与查询层，排最后做。

### 目标
1. 拉取用户历史持仓/交易 → 拼 prompt → llm 叙事（行为模式梳理、思考框架）。
2. 仅做「降维描述」，不越界（受 L1/L3 硬约束）。
3. 工具函数取数，仅传算好的指标（年化/最大回撤/波动率/集中度等）。

### 验收标准
- 输出为行为模式描述 + 思考框架，无买卖建议/收益承诺（L3 兜底）。
- 所有结论可溯源到代码算出的指标。
- 依赖 Issue 1–4 护栏与 Issue 6 查询层先落地。

### 反链
roadmap §2.7.1；`agent-guardrail-layer-design-2026-08-17.md` §1（越界风险）。
