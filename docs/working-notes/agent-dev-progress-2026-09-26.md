# 账本精灵开发进度与步骤边界（2026-09-26 起，#1121）

> **定位**：三份文档分工——
> - 怎么学（理论 + S1~S6 详设）→ `./agent-dev-learning-plan-2026-09-25.md`（工程主线）
> - 面试怎么用（简历 + 题库地图 + S0）→ `./agent-interview-prep-plan-2026-09-25.md`
> - **执行到哪了（每步边界 + 学习卡）→ 本文件**，随做随追加。
>
> **节奏约定**：一步 = 一个 PR + 一张步骤卡；每张卡阅读时间 ≤0.5 小时。超出即拆步，绝不让单步膨胀。

## 步骤总表

| 步 | 名称 | 边界（做 / 不做） | 状态 |
|---|---|---|---|
| S1-A | 通电最小闭环（后端） | 做：`POST /api/agent/chat/` 端点 + P1 服务端上下文注入 + `call_llm` 的 `response_format` 接线修复 + 5 个真实只读工具 + 单测；**不做**：前端页、传输退避、trace 落库 | ✅ 已完成（PR #1702 → dev；另发现并修复第三处接线缺陷「工具清单未注入 prompt」，见卡 #1） |
| S1-B | 前端最小对话页 | 做：`views/agent/` 页面 + `api/agent.ts`，三态（澄清/结果/错误）渲染；**不做**：流式输出、历史会话列表 | ✅ 已完成（**PR #1704**；三态验收全绿，见卡 #2） |
| S1-C | 退避与调用 trace | 做：`llm.py` 指数退避（429/5xx/超时可重试、4xx 不重试）+ 工具调用结构化日志；**不做**：trace 落库（归 S4） | ✅ 已完成（**PR #1708**，见卡 #3） |
| S2 | 记忆层 | 做：`agent_session` 表（先过数据准入四问）+ 后端权威会话 + 分层 prompt + 压缩；**不做**：跨会话长期记忆 | ✅ 已完成（**PR #1716**，见卡 #4） |
| S3 | 护栏与成本 | 做：`safety/` 三件套 + L1 铁律 + per-user 配额迁出内存（#1294） | 🚧 进行中：G1~G4 三件套 + 接线 ✅ **PR #1729**、**G7 L1 铁律** ✅ **PR #1730**（见卡 #5 与 G7 收尾段）；剩 G5 配额迁表 / G6 意图路由 |
| S4 | 可观测与评估 | 做：`agent_trace` 表 + 30 条评估集 + `scripts/agent_eval.py` | 待做 |
| S5 | 协议层 | 做：MCP server（stdio）；Skill 目录、多模型 failover 可裁 | 待做 |
| S6 | 面试收口 | 做：12 条追问口述 + 30 秒自介 + 简历定稿（证据逐条回填） | 待做 |

---

## Issue 依赖与排期（2026-09-26 登记，防「卡躺在看板上不管」）

> 本轮扫全仓 442 个 issue：**无里程碑 0 个**；`答非所问` / `意图漂移` / `历史栏` / `StaticPool` 正文零命中
> → 新登记 5 张（均挂 M6 + 象阵）。以下为依赖关系与**插入时机**，规则：**主线不因修卡停摆，修卡不脱离主线**。

### A 档 · 主线必经（按序，前一张不合并不开下一张）

| 序 | 卡 | 依赖（为什么必须在前） | 状态 |
|---|---|---|---|
| 1 | **S2 记忆层** `#1716` | — | ✅ **已合并 dev**（`40cc67778`，2026-09-26）→ 主线解锁，下一张 = `#1718` |
| 2 | **答非所问 / 意图跟随** `#1718` | 必须在 S2 后：改的 `agent_loop.py` 与 S2 同文件，先动必冲突 | ✅ **已合并 dev**（PR #1725，2026-09-27；issue 已由 dev 合入自动关闭） |
| 3 | **历史会话栏** `#1719` | 必须在 S2 后：读 `agent_session` 表 + 改 `api/agent.ts`/`index.vue` 同文件 | ✅ **已合并 dev**（PR #1726，2026-09-27） |
| 4 | **S3 护栏与成本** | 与 2/3 **可并行**（动 `safety/` + 配额，不同文件）；`#1294` 配额迁出内存归此 | ✅ 三件套 + 接线（**PR #1729**）、G7 L1 铁律（**PR #1730**）均已合并（见卡 #5）；剩 G5 配额迁表（需新表先过四问留痕）、G6 意图路由 |
| 5 | **S4 可观测与评估** | 内含 `#1718` 的**回归位**（30 条评估集把「答得对」变成可验证，防止改完又悄悄坏） | 待做 |
| 6 | `#1714` 可中断（停止按钮） | 依赖 S2 的服务端会话（取消标志要挂在会话上） | OPEN |
| 7 | `#1712` 结构化叙事渲染 | 与 2~5 **可并行**（纯前端渲染，不动记忆层） | ✅ **已合并 dev**（**PR #1724**，2026-09-27；issue 已关闭） |
| 8 | **S5 协议层 → S6 面试收口** | — | 待做 |

### B 档 · 择机插入（不占主线序位，靠触发条件，到点必须回头做）

| 卡 | 触发条件（到点即做，做完在本表打勾） |
|---|---|
| `#1721` StaticPool 假阳性 | ✅ **已完成**（**PR #1733**，2026-09-27，见卡 #6）——原触发条件「S4 建 `agent_trace` 之前必做」已提前满足 |
| `#1722` 全量测试提速 | ✅ **已完成**（2026-09-27，**PR #1734**，见「插曲卡：#1722」）——`--durations` 量化证实 87% 是 fixture setup → 模板库机制 + xalpha 打 `slow` 标，全量快集 **87m → 14m58s（≈ -83%）**，测试总数不变 |
| `#1720` 调度未开启 → 数据陈旧 | 你拍板「本机是否常开调度」时；或下次动 `scheduler-tasks.md` / 页面新鲜度提示时 |
| `docs/spec/tech-debt.md` 2026-09-26 两条 | 等你拍板（文档已登记，不另开卡） |

### C 档 · 邻域（不进本主线）

- `#1717` 资产总览闪烁 + 按钮组样式（你提的，挂 **M0 上线**）——独立处理，不排入 Agent 主线。
- `#1701` / `#1703` 已闭环；`#1121` 用 `Refs` 引用不自动关卡。

---

## 步骤卡 #1：S1-A 通电最小闭环（后端）

**分支**：`fix/1121-agent-s1a`（worktree `D:\codes\fundmate-1121`，基于 `origin/dev` 12d04d09）
**目标**：一句自然语言 → 真实持仓数据 → 自然语言总结，`curl` 可复现。

### 进（改动面）

1. **新建领域 `domains/agent/`**（`views.py` + `schemas.py`，零模型零迁移）+ `main.py` 注册 → 端点 `POST /api/agent/chat/`（挂 `guards` 四道闸 + 标准信封）。
2. **P1 越权修复（本步硬前置）**：`run_agent()` 增加服务端上下文参数；工具执行前**服务端权威值覆盖**前端候选值（合并点 `agent_loop.py:193`）——前端回传的 `collected_params` 从此只是候选，不是权威。
3. **接线修复**：`llm.call_llm` 补 `response_format` 形参并透传进 payload。真调必抛 `TypeError`（`agent_loop.py:175` 传了签名里不存在的参数），此前被测试 mock 掩盖。
4. **5 个真实只读工具**替换 demo 占位（持仓总览 / 组合 XIRR / 基金净值 / 温度计 / 自选表现），全部复用既有 service，零裸 SQL、零新表。
5. **单测**：HTTP 三态（澄清/结果/错误）+ P1 覆盖断言 + 每工具四例（正常/缺必填/未知参数/enum 越界）。

### 不做（防蔓延）

前端页面（S1-B）、传输退避（S1-C）、trace 落库（S4）、会话持久化（S2）、流式输出、`ledger_id` 级工具（现 5 工具只吃 `family_id`，该域注入点已留好）。

### 验收（2026-09-26 完成记录）

- ✅ 全量 `pytest -p no:xdist`：**2130 passed**（单进程，16 分钟）；新增 HTTP 层三态 + P1 覆盖断言 + 轮次闸 429、五工具真实只读 + schema 四例 + enum 探针；既有 agent_loop 用例零回归。
- ✅ `ruff check` / `ruff format --check` 零告警；视图厚度 / 跨域查询 / API 约定守卫全绿；`api.md` 自动段已重跑（132 路由）。
- ✅ 前端伪造 `family_id=999` → 被服务端权威值覆盖（`test_chat_p1_server_family_id_wins` 钉死）。
- ✅ 产物：commit `1d73ac977`（`fix/1121-agent-s1a`）→ **PR #1702 → dev**；范围外发现开单 **#1701**（Windows 本机 pytest 环境性失败，dev 基线既有）。
- ✅ CI 门禁：#1702 两轮全绿（gate / 后端 13m / deep-review「未发现实质缺陷」）；**已由维护者手动合并进 dev**（merge commit `3034b8df2`，2026-09-26），远端分支已随合并删除。
- ✅ 本地起服 curl 三态人工走查：已在 S1-B 期间完成（真后端 + 真 LLM），记录见卡 #2 验收。

**Windows 本机跑全量的两个环境前提**（dev 基线既有，见 #1701）：
① `PYTHONUTF8=1`（否则子进程脚本测试的 GBK 输出按 UTF-8 读崩）；
② 新装 venv 需手装 `psycopg2-binary`（pyproject 平台标记在 win32 上剔除了它，但迁移测试要建 `postgresql://` 引擎）。

**本步实际改动面（比计划多修 1 处）**：计划内的两处接线缺陷之外，实现时发现决策轮 prompt 从未携带 `TOOLS_METADATA`——模型根本拿不到工具清单，真实调用只能盲猜工具名（测试 mock 掩盖）。已在决策轮注入，回归钉在 `test_chat_result_carries_tools_metadata`。

### 你学什么（≤0.5h，读两处 + 答三问）

- 读：`agent_loop.py:136-230`（循环本体）+ `domains/agent/views.py`（端点侧）。
- 答：
  1. FC 循环里「模型推理 / 本地执行 / 结果回填」各对应哪几行代码？
  2. 为什么 `collected_params` 直接进工具就是越权？修复的本质是哪一对概念的翻转？（候选值 vs 权威值）
  3. error-as-observation 和静默失败差在哪？各自的代价是什么？

---

---

## 步骤卡 #2：S1-B 前端最小对话页

**分支**：`feat/1121-agent-s1b`（worktree `D:\codes\fundmate-1121`，基于 `origin/dev` `3034b8df2` = S1-A 合并后）
**目标**：浏览器里走通「对话 → 追问补参 → 出结果」三态，可截图进面试演示（补上 S1-A 卡遗留的三态人工走查）。

### 进（改动面）

1. **`api/agent.ts`**：三态联合类型 `AgentTurn` + 白名单 `AgentSessionState`（对齐后端 `ALLOWED_KEYS`）；`http.request` 单独 120s 超时——全局 axios 10s 装不下「决策轮 + 叙事轮」两轮模型调用（同 `ocr.ts` 做法）。
2. **`views/agent/index.vue`**：消息列表 + 三态气泡（用户 / 助手 / 服务提示）+ 等待动画 + 指标 chips + 示例问题空态；`session_id` 前端生成（后端轮次闸按 `user_id+session_id` 计数），`session_state` 每轮**原样回传**。
3. **`router/modules/agent.ts`**：静态路由手工注册——**本仓路由并非 views glob 自动生成**（`router/utils.ts:211` 的 glob 消费端传空数组，AGENTS.md 该条与实现不符，已开 **#1703** 跟踪）；rank 段位 200+ 沿用 `asset.ts` 的模块隔离思路。
4. **设计同步**：`docs/design/components.md` §ChatBubble + `frontend/design.md` / `design.dark.md` 对话气泡条目（全部语义令牌，暗色零覆写）。

### 不做（防蔓延）

流式输出、历史会话列表与会话切换、移动端专属交互、指标染涨跌色（汇总值非涨跌语义，涨红跌绿只留给行级行情）。

### 关键决策

- **IME 组词保护**：Enter 发送前查 `e.isComposing`——否则中文输入法选词回车会被当发送。
- **Emoji 渲染时剔除**：全站禁 Emoji 只有约定、无 lint 兜底，模型输出在页面内用正则兜底。
- **错误分层**：401/403 不入聊天气泡（全局拦截器已提示，避免双报错）；429/503/超时用后端信封 message 入泡，保持对话上下文连续。

### 验收（2026-09-26 完成记录）

- [x] `pnpm typecheck`（tsc + vue-tsc）零错误
- [x] `pnpm lint`（eslint + prettier + stylelint）零错误；e2e 另过 `prettier --check e2e/**/*.ts`
- [x] `pnpm test:e2e`：**8/8**（新增 `agent-chat.spec.ts` 三态渲染回归 + 既有 7 例零回归）
- [x] 本地起服三态人工走查（补 S1-A 卡遗留项，curl 实抓、信封与后端逐字段一致）：
  - **clarify**：「招商中证白酒多少钱一份」→ 追问 6 位基金代码，`missing_params=['fund_codes']`；
  - **result**：「持仓总市值」→ 真实 XIRR 数据（组合价值 68.04 万、XIRR 54.63%），`data` 为扁平标量；
  - **error**：污染 `collected_params` 注入 schema 外参数 → 未知参数双败 → `分析失败：未知参数: __probe_unknown__`，**零编造**（确定性触发：候选值两轮都摘不掉模型自己没发过的键）。
- [x] 截图留档：`frontend/test-results/agent-chat-s1b-three-states.png`（三态同屏 + 侧边栏入口；产物目录已 gitignore）

### UI 二次打磨（2026-09-26 追加，随 PR #1704）

用户提供竞品截图作方向参考，同分支追加一轮视觉打磨（**能力清单不照抄**——竞品的「行为解读」等后端没有的工具一律不放）：

- **空态 hero**：两行大标题 + 「账本精灵」品牌渐变词（`@supports` 回退实色）+ 示例问题块列表（图标 + hover 描边）。
- **消息头像行**：24px 圆形头像（助手 `MagicStick` / 服务提示 `WarningFilled` 危险色）+ 角色标签；气泡**尾角收小**（助手左下 / 用户右下）。
- **底部 dock**：能力快捷 chips 横滚（投资表现 / 持仓价值 / 市场温度，与示例问题同源于 `QUICK_ACTIONS`）+ 胶囊输入（`focus-within` 走 focus ring）+ 44px 圆形发送按钮（`aria-label="发送"`）。
- 门禁复跑全绿：typecheck / lint / E2E **8/8**（五个 E2E 锚点文案「试着问一句 / Enter 发送 / 发送 / 服务提示 / 新对话」全部保留）；截图 `agent-chat-polish-hero.png` / `agent-chat-polish-dialog.png`。
- 设计同步：`docs/design/components.md` §ChatBubble、`frontend/design.md` 对话气泡表（描边 `--border-light` → `--border-subtle`，新增 hero / dock 规则）。

### 你学什么（≤0.5h，读一处 + 答三问）

- 读：`views/agent/index.vue` 的 `send()` 与 `describeError()`。
- 答：
  1. `session_state` 为什么原样回传而不是每轮重建？G3 白名单校验防的是什么攻击面？
  2. 前端错误处理为什么把 401/403 与 429/503 分开？各自由谁负责提示？
  3. 「views glob 自动成路由」在本仓为什么不成立？静态注册的代价与收益各是什么？

---

## 步骤卡 #3：S1-C 退避与调用 trace

**分支**：`feat/1121-agent-s1c`（worktree `D:\codes\fundmate-1121`，快进到 `origin/dev` `eb5493cd0` = #1705 合并后）
**目标**：LLM 调用失败不再「所有异常一锅端傻重试」，工具执行必留痕——线上排障按 `[llm.call]` / `[agent.tool]` 两个 tag 就能捞出全链路。

### 进（改动面）

1. **`llm.py` 分类退避**：
   - `_classify_failure()`：**429 / 5xx / 超时 / 连接失败 / 响应体异常 → 可重试；其余 4xx 立即终止**（401 key 错、400 参数错，退避 N 次也照样 503，重试只是白拉长失败路径）。分类顺序敏感：HTTPError 也是 RequestException、requests 的 JSONDecodeError 也是 ValueError，先特后泛才贴得对标签。
   - `_backoff_seconds()`：指数退避 `base × 2ⁿ`（base=1.5 → 1.5/3/6s）；429 带**数值型** `Retry-After` 头时听服务端的（封顶 30s，防回超大值挂死工作线程）；HTTP-date 形式不解析，回落指数退避。
   - `[llm.call]` 结构化行：成功 `ok attempt=… tokens=… elapsed=…`、重试 `retry attempt=1/2 reason=http=502 backoff=1.50s`、立即终止 `fail-fast attempt=1 reason=http=401`、耗尽 `fail attempts=… last_err=…`。
   - **对外契约不变**：耗尽/终止都抛 `OCR_SERVICE_UNAVAILABLE` 503（API-First 冻结，前端 S1-B 分层错误处理不受影响）。
2. **`tools.py` 必留痕**：`ToolExecutor.run` 成功打 `[agent.tool] ok name=… elapsed=…`，失败/未注册打 `fail … err=…`——**每次执行必有痕迹**，不依赖上层是否再记。
3. **单测**：新文件 `test_llm_backoff.py` **10 例**（假 `requests.post` 剧本驱动；睡眠、`_record_tokens`、`ARK_API_KEY`、`ARK_RETRIES=2` 全换桩：401 快败、5xx 指数 [1.5,3.0]、429 认头、429 无头回落、超时耗尽→503、坏 JSON/空 choices 重试、首试成功不 sleep 且 `[llm.call] ok` 留痕、payload 带 `response_format`）+ `test_tools.py` 追加 **2 例**（loguru sink 断言成功/失败都留 `[agent.tool]` 痕）。

### 不做（防蔓延）

trace 落库（归 S4 `agent_trace` 表）、重试耗时/成功率 metrics 上报、HTTP-date 形式 `Retry-After` 解析、上游限流并发信号量（与 S3 配额一起看）。

### 关键决策

- **为什么 4xx 不重试**：4xx 是「请求本身错了」，不是「服务暂时不行」——退避重试的语义前提（瞬态故障）不成立；fail-fast 让坏请求立刻变成可诊断的 503。
- **为什么耗尽后仍抛 503**：错误码与信封已冻结，换码会破坏前端按 429/503/超时分层入泡的处理（S1-B 卡「错误分层」）。
- **bare except + 分类表**：服务边界收全再分类，任何意外异常都收敛成干净 503 信封而非 500 裸栈；分类表兜底 `unexpected` 一律不重试。

### 验收（2026-09-26 完成记录）

- [x] 目标测试 `tests/services/ai_recognizer/`：**35 passed**（含新增 12 例，15.6s）
- [x] `ruff check` / `ruff format --check` 零告警
- [x] 全量 `pytest -p no:xdist`（单进程）：**2142 passed**（31m17s，exit 0）——较 S1-A 基线 2130 恰 +12（新增用例数吻合），既有零回归
- [x] `lint-md` 只读检查本步进度文档：0 警告 0 错误；无前端/路由改动（E2E 与 `api.md` 自动段不涉及）
- [x] 产物：commit `a70c269e5`（`feat/1121-agent-s1c`）→ **PR #1708 → dev**（待合并）

### 你学什么（≤0.5h，读两处 + 答三问）

- 读：`llm.py` 的 `_classify_failure` / `_backoff_seconds` / `call_llm` 主循环。
- 答：
  1. 指数退避的「指数」解决什么问题？固定间隔的缺陷在哪？什么情况下该加抖动（jitter），本步为什么没加？
  2. 429 的 `Retry-After` 为什么必须封顶？不封顶时服务端（或中间层）能怎么伤害你的 worker？
  3. `[llm.call]` 为什么成功也要打日志？只有失败才打会漏掉什么排障场景（提示：慢成功 / token 突增）？

---

---

## 步骤卡 #4：S2 记忆层——后端权威会话 + 分层记忆

**分支**：`feat/1121-agent-s2`（worktree `D:\codes\fundmate-1121`，基于 `origin/dev` `ee7c388d2` = #1708/#1713 合并后）
**目标**：把「前端持有会话」翻转为「后端权威 + 分层记忆」——20 轮后仍记得第 1 轮说过的标的，单轮 prompt 有上界，前端篡改 `session_id` 读不到别人的会话。

### 数据准入四问（新表 `agent_session`，`conventions.md` / `data-strategy.md` 强制）

1. **谁在用**：`POST /api/agent/chat/` 每轮读写（会话续接 / 分层 prompt 组装 / G4 轮次闸）；后续读路径：#1714 取消标志、方案 A 历史栏（另卡）。
2. **什么场景**：用户发首轮建会话 → 续聊 / 刷新恢复；>6 轮触发压缩；超 10 轮轮次闸。
3. **缺了会怎样**：P2（前端持有 → 丢最早信息）、P4（状态可篡改）、轮次闸重启即失效——这是缺陷修复的必需载体，无降级空间。
4. **成本**：每会话 1 行；JSON 列全部硬截断（单轮原文两侧各 ≤800 字、摘要 ≤3000 字、关键卡 ≤800 字）→ 单行有界；行数随「用户数 × 日会话数」线性；零新增外部请求（压缩复用既有 LLM 调用与四道闸）。

**列 → 当场指定读者**：`session_id`（API 往返 + 归属校验）、`user_id`（越权校验 / 查询）、`goal`（prompt + 未来历史栏标题）、`summary` / `key_facts` / `messages`（prompt 组装三料：摘要 + 关键卡 + 最近 3 轮原文）、`state`（追问延续：missing/collected 参数）、`turn_count`（G4 闸 + 压缩触发）、`created_at/updated_at`（TimestampMixin，历史栏排序）。

### 进（改动面）

1. **`domains/agent/models.py` 新表**（user 域）+ `DATA_DOMAIN_REGISTRY` 登记 + `docs/dev/db-data-domain.md` user 域清单同步（硬规则 §1 双登记）。
2. **`session_store.load_or_create`**：`session_id` 缺省 → **服务端生成 uuid**；提供但不存在 / 不属于当前用户 → 一律 404（`RESOURCE_NOT_FOUND`，不泄露存在性）——修 P2/P4。
3. **请求契约演化（计划内，本卡文档化）**：请求去掉 `session_state`、`session_id` 改可选；响应三态统一携带 `session_id`。前端只回传 id，状态与历史全部服务端持有；G3 白名单保留为**加载路径的防线**（DB 内容过白名单），注入面从「每轮可注入」收敛为「不可注入」。
4. **G4 轮次闸入库**：`agent_session.turn_count` 取代 `_AGENT_TURN_COUNTER` 内存字典（重启不丢、多实例一致）；`guards` 只留 `AGENT_MAX_TURNS` 常量与读取器。
5. **分层 prompt**：`[L1 system] + [goal] + [关键信息卡] + [滚动摘要] + [最近 3 轮原文] + [已收集参数]`，替换整段 `json.dumps(全部 history)`；所有层硬截断 → **单轮 prompt 有界**。
6. **滚动压缩**：`turn_count > 6` 且原文超窗 → 把最旧轮次用 `doubao-seed-2-0-mini` 压成摘要（追加进 `summary`）+ 抽关键信息卡（替换式，当前焦点优先）；压缩失败降级为硬截断并打 `[agent.memory]` 日志——**有界性优先于完整性，完整性由摘要层兜底**。
7. **前端**：`api/agent.ts` / `index.vue` 改为「首轮不带 id、回传后回带」；404（会话失效）自动落回新开会话；E2E fixture 同步契约形状。

### 不做（防蔓延）

- 跨会话用户画像（理由：写入价值未验证 + 隐私面扩大，学习计划已明确标注可选且不做）。
- 历史会话列表 UI（方案 A 页内栏，另卡）；SSE 流式；#1714 取消标志（依赖本卡合并后开工）。
- 消息向量检索 / RAG（分层文本记忆已覆盖验收，向量属过度工程）。

### 关键决策

- **状态存哪**：`state`（追问参数）与 `messages`（原文）分列——参数是**结构化工作内存**（白名单校验），原文是**记忆素材**（截断 + 压缩），生命周期与校验规则都不同，混在一列会把 G3 白名单逼成对原文的校验器。
- **压缩失败降级方向**：宁可硬截断丢最早（有日志可观测），也不放任 prompt 无界（炸 token 预算）；完整性靠摘要层在下次成功压缩时补回。
- **越权一律 404 不 403**：403 泄露「这个 id 存在」，404 不泄露；与 `get_owned_or_404` 的既有口径一致。

### 验收（2026-09-26 完成记录）

- [x] 20 轮后仍能回答第 1 轮提到的标的 → `test_agent_memory.py::test_twenty_turns_retain_first_turn_and_prompt_bounded`：压缩 mock 做「完美回灌」，断言第 20 轮 prompt 含 `110011`，且压缩确实发生（`session.summary` 非空、原文层压回 ≤8 条）。
- [x] 单轮 prompt 收敛有上界 → 同用例断言 20 轮 prompt 全部 ≤ `PROMPT_BOUND`（由层常量推导：硬截断原文层 + 摘要 ≤3000 + 关键卡 ≤800 + 固定开销）；压缩失败降级用例 `test_compress_failure_degrades_to_hard_cap` 证明断链时上界仍成立（原文层截到 ≤12 条）。
- [x] 伪造 / 越权 `session_id` → 404 → `test_chat_session_forged_or_unknown_id_404`：存在但不属于自己 404、根本不存在也 404（不泄露存在性）。
- [x] 刷新续聊仅凭 `session_id` 恢复 → `test_chat_session_server_side_continuity`：客户端两次请求均不带任何状态，第 2 轮决策 prompt 含第 1 轮原文（服务端回放），响应 `session_id` 同值。
- [x] 全量 `pytest -p no:xdist` 单进程绿 + `ruff` 零告警；前端 `typecheck` / `lint` 双 0。
  - 全量：**2147 passed**（36m01s，exit 0，0 失败）——较 S1-C 基线 2142 净 +5（S2 新增续接/越权 404/轮次闸/20 轮记忆/上界/压缩降级，同时契约演化删掉 `init_session` / `merge_user_input` 旧用例，增删相抵）。
  - 已过：`ruff check` 零告警；定向 79 例（agent 三文件 + 数据域 + 晚绑定 + ai_recognizer 全目录）全绿；`typecheck` 0；`lint`（eslint/prettier/stylelint）0；`check_api_conventions.py --write` 132 端点无 diff；E2E `agent-chat.spec.ts` 1 passed。
  - 时长口径（防误读）：全量基线本就是 16~31 分钟档（S1-A 16m / S1-C 31m17s），慢在**单进程强制**（xdist 多 worker 会 OOM，AGENTS 硬规定）+ 我并行跑 typecheck/lint/E2E 抢 CPU，不是某个用例变慢。
- [x] 产物：commit `95f3a6aa8`（`feat/1121-agent-s2`，15 文件 +584/-198）→ **PR #1716 → dev 已合并**（`40cc67778`；数据准入四问在 PR 正文留痕）
  - 开发中踩坑一枚（值得进面试故事）：`test_chat_result_carries_tools_metadata` 曾报 `StaleDataError: UPDATE agent_session 匹配 0 行`——测试库 StaticPool 单连接下，请求中途工具链 `with get_session() as db:` 退出时 `close()` 的连接复位会把**同一连接上未提交的 INSERT 回滚掉**（最小复现证实：`b.close()` 后行数归零）。生产各 Session 走独立连接只回滚自己的事务，不受影响；测试侧规避 = 会话行先经 `db` fixture 提交（用例内有注释）。

### 你学什么（≤0.5h，读两处 + 答三问）

- 读：`agent_loop.run_agent` 的 prompt 组装段 + `session_store.load_or_create`。
- 答：
  1. 「关键信息卡 / 滚动摘要 / 最近 N 轮原文」三层各解决什么丢失模式？为什么关键卡必须永不压缩？
  2. 轮次闸从内存挪进表，除了「重启不丢」还顺带修了什么一致性问题？
  3. 为什么压缩失败要选「截断」而不是「不压缩」？两种失败各长什么样？

---

## 步骤卡 #5：S3 护栏三件套——输入拦截 / 输出过滤 / 重复追问

**分支**：`feat/1121-agent-s3-safety`（worktree `D:\codes\fundmate-1121`，基于 `origin/dev` `40cc67778` = #1716 合并后，后 rebase 到 `0ae54a3d7` = #1723/#1725/#1726 合并后）
**目标**：模型不听 prompt 时也拦得住——**能在输入侧拦掉的，就不花钱让模型生成再拦**；输出侧逐句兜底；同一问法反复追问不给模型松口机会。
**PR**：#1729（`Refs #1121`，不自动关卡）

### 数据准入（本次**零新增表/列/job/抓取目标** → 四问结论留痕）

1. **谁在用**：`POST /api/agent/chat/` 每轮两次——进模型前 `check_input`，出模型后 `filter_output`；无新增存储项。
2. **什么场景**：用户任一提问（预测/建议类直接回标准话术），任一回复（命中句替换为免责声明）。
3. **缺了会怎样**：护栏缺位 = 模型可能输出买卖建议、收益承诺（产品合规风险）。补的是**计算逻辑**不是数据，没有「可存可不存」的字段。
4. **成本**：每次请求若干次正则（微秒级），零外部请求；`repeat_tracker` 为进程内 dict（上限 512 会话防无界），单实例不共享属既有技术债，**随 #1294 一并迁移，故不预支新表**。

### 进（改动面）

1. **`safety/intent_guard.py`**：B1~B4 越界句式（预测 / 建议 / 评价 / 收益承诺）命中即拦，带标准话术；A 意图分类（预测/建议/情绪/查询/知识）；D 情绪复合打 `risk_notice` 不硬拦。
2. **`safety/output_filter.py`**：R1~R10 + E1 逐句扫描，命中句替换为对应类别免责声明；事实标记词白名单豁免（R5b）；全角数字/百分号/句点归一化。
3. **`safety/repeat_tracker.py`**：NFKC 归一化 + 去标点 → 同一问法连续 N 次强制标准话术；`dict + threading.Lock` + 会话数上限淘汰。
4. **`agent_loop.run_agent` 三处接线**：输入拦截与重复追问置于**轮次闸之前**早退；`clarify`（`used_tools=False` 启用 E1）与 `narrative`（`used_tools=True`）各过一次 filter；情绪复合在回复前加 `RISK_NOTICE`。
5. **测试 4 文件 87 例**：纯函数单测 + 接线集成，不触网（护栏行为确定性可测，不靠 mock LLM「看它乖不乖」）。

### 不做（防蔓延）

- **G7**（L1 数据真实性铁律注入）：与 #1725 / #1724 在 prompt 区撞车，**排 #1725 合并后单独做**——已于 2026-09-27 另卡实施（PR #1730），见下方「G7 收尾」。
- **G5**（per-user 配额迁表）：需新表，须完整走四问并留痕后另开卡；**G6**（意图路由）另卡。
- 进度文档以外的设计文档状态回填（`agent-guardrail-layer-design-2026-08-17.md` §2/§9）随本 PR 一并完成。

### 关键决策

- **拦截放轮次闸之前**：轮次闸（G4）约束的是模型调用成本，拦截回合零模型调用，不该占用用户分析轮次预算；但**原文照常落库**——#1719 历史回放必须看得到这段问答，否则刷新后凭空消失。
- **话术给安全出口**（「我可以帮你查 X」）而非干瘪拒绝：否则用户只会换个问法再来，正好撞上重复追问检测——两者是同一套设计的两半。
- **D 情绪复合拆成两个 pattern**：`怎么办`（建议意图）与 `亏惨了`（情绪词）单侧都不触发，只有复合才插免责声明；合成一个大正则会把普通求助也强插免责。
- **误伤优先收敛而非放宽规则**：`过去一年年化 12.3%` 是 XIRR 真算出来的事实，被拦等于产品自我阉割 → R5b 只在**缺事实标记词**时命中（§7.1「误伤用白名单修正」）。
- **命中句替换、不整篇拒答**（§7.3）：合规内容保留；E1（未调工具却谈市场判断）例外整段替换，因为没有事实基础可保留。

### 验收（2026-09-27 完成记录）

- [x] 越界提问零模型调用即回标准话术 → `test_safety_wiring.py::test_prediction_input_blocked_without_model_call`（断言 `call_llm` 调用数 0、`turn_count` 不变、`data == {}`、原文与话术已落库）；连续 10 次越界也不消耗轮次预算。
- [x] 数据查询不被误拦 → 8 条纯函数用例（温度 / 涨跌幅 / 持仓 / 净值 / 复利）+ 接线层 4 条正常查询回归。
- [x] 情绪复合不硬拦但加风险提示 → `test_emotion_composite_not_blocked_but_noticed` + 接线层 `RISK_NOTICE` 前缀断言；单侧（纯情绪 / 纯求助）不触发。
- [x] 输出侧命中句替换、事实句保留 → `test_replace_only_offending_sentence`（三句里合规两句原样保留）；全角 `年化８．５％` 与裸 `预期年化 8%` 均命中，`历史年化 8.5%` 放行。
- [x] 同一问法连续 3 次 → 强制标准话术且第 3 次不调模型（换标点仍算同一问；换问法重新计数；跨会话隔离）。
- [x] 全量 `pytest -p no:xdist`：**2187 passed / 3 failed**——3 例即 #1727 已知的 TURSO/libsql 环境性失败（`.env` 带 `TURSO_DATABASE_URL`、Windows 无 `sqlalchemy-libsql`），非本 PR 引入；`ruff check` / `ruff format --check` 全绿；设计文档 `lint-md` 0 警告。
- [x] 产物：commit `e9de85782`（9 文件 +1064）+ `5170d0bed`（设计文档 §2/§9 回填 G1~G4 状态）→ **PR #1729**，required check `质量门禁汇总` = SUCCESS。
  - 踩坑两枚（可进面试故事）：① 初版 D 情绪判定用一个大正则，`怎么办` 先被建议线索吃掉 → 情绪复合**永不触发**，拆成「情绪词 ∩ 建议意图」才符合 §6-D 的「插提示而非硬拦」；② `_normalize` 漏了全角句点 `．`，`年化８．５％` 会从这条缝漏过——归一化必须覆盖规则里出现的**每一种**数字形态，且要与 `unicodedata.NFKC`（repeat 侧用）口径对齐。

### G7 收尾（2026-09-27，PR #1730）

S3 的最后一块拼图（L1 软约束）：铁律 + 自查三问 + can/cannot 清单抽成单一常量 `_L1_DATA_TRUTH`，
注入**决策轮**（契约 → 铁律 → 工具清单，先立规矩再给能力）与**叙事轮**（写数字的地方）两处，
两轮共用一份文案防漂移；❌ 四条与输入侧 B1~B4 拦截同口径——L1 决定模型**是否生成**、L3 兜住
**已生成**的文本，构成纵深防御（设计 §4 注：同花顺实证单靠 L1 会越界，故 L1 从不单独依赖）。
清单符号用纯文本「能 / 不能」而非 ✅/❌：system prompt 会诱导模型输出同形态文字，本项目禁 Emoji
（语义逐条对齐 §4，仅符号替换）。测试 3 例只断言 prompt 内容与点位——L1 是确定性文本，
「模型听不听话」由 L3 的 87 例兜底，不做脆弱的 prompt 快照对比。
至此 S3 只剩 G5（配额迁表，需新表先过四问）与 G6（意图路由）。

### 你学什么（≤0.5h，读两处 + 答三问）

- 读：`safety/intent_guard.py` 的 `_BLOCK_RULES` 与 `classify` 判定顺序、`agent_loop.run_agent` 开头的接线段（轮次闸之前的 40 行）。
- 答：
  1. 输入侧拦截为什么要放在轮次闸**之前**？放在之后各付出什么代价（成本 / 用户体验 / 语义）？
  2. 「宁可误伤、不可漏放」在本实现里靠什么把误伤面收回来？为什么白名单要绑「事实标记词」而不是调低规则阈值？
  3. 护栏做成纯函数带来什么可测试性差异？对比「mock LLM 跑一遍看输出」的测法，各自测得到、测不到什么？


## 步骤卡 #6：#1721 测试库连接模型（A 档插曲提前完成，测试基建）

> **边界**：只改测试基建（conftest 引擎模型 + 回归判据 + 文档），不碰任何 `services/*` 业务代码；
> 不做 #1722 提速（下一张卡）、不做 S4 评估集。

### 数据准入（本卡**零新增表 / 列 / job**——四问结论留痕）

改的是测试基础设施（引擎连接模型），不涉及数据实体，四问不适用；无数据策略变更、无注册表登记。

### 进（改动面）

- `backend/tests/conftest.py`：测试引擎 `sqlite:///:memory:` + StaticPool → **临时文件库（`tmp_path/_fixture_*.db`）+ 显式 `QueuePool`**；fixture 收尾 `engine.dispose()`。
- `backend/tests/core/test_session_connection_model.py`（新）：2 例回归判据——旧模型下**红**（直译 issue 的 `UPDATE 匹配 0 行`）、新模型**恒绿**。
- `docs/pytest/conftest.md`：新增「测试库连接模型」专节（陷阱 + 四坑 + 判据 + 磁盘提示）。

### 关键决策（方案五步探索，每步实测排除——详见 conftest docstring）

| # | 方案 | 实测结果 |
|---|---|---|
| 1 | StaticPool（原实现） | 假阳性根因：跨会话共连接，B.close() 的 reset 连带回滚 A 未提交事务 |
| 2 | shared-cache 内存 URI | 连接独立了，但**表级锁**：A 未提交写持表锁、B 读同表立即 `database table is locked`（不排队）→ 弃用 |
| 3 | `file:` 裸 URL / `mode=memory` | 裸 `file:` 过不了 `make_url`；`mode=memory` 被方言判内存库给 `SingletonThreadPool`（同线程单连接 = 没改） |
| 4 | **临时文件库 + 显式 QueuePool** | 复现转绿 ✓（核心采纳，与生产连接/事务模型同构） |
| 5 | `PRAGMA journal_mode=WAL` | 每用例 ×2 引擎多 3800 次文件打开，47 分钟全量偶发 2 例 `unable to open database file` ERROR at setup；单进程串行下与 DELETE journal 无锁差异 → 去掉，引擎保持惰性 |

**撞名雷**：`clean_db(app)` 是 **autouse**（每用例必建 fixture 库文件），与用例自建 `tmp_path/market.db` 撞名
→ fixture 落盘的表污染用例自建库（`test_db_data_domain` 16 例曾全红）→ fixture 文件加 `_fixture_` 前缀后全绿。

### 验收（2026-09-27 完成记录）

- [x] 新写用例不再需手工「先提交会话行」：回归判据 2 例接管（旧模型红 → 新模型绿，红→绿闭环实测）；
- [x] 文档入口：`docs/pytest/conftest.md` 专节（陷阱 + 四坑 + 判据）；
- [x] 全量 pytest 零回归：**2223 passed / 3 failed / 0 errors**（69m48s），3 failed = **#1727 libsql 环境性基线**（`test_db_factory` 1 + `test_db_lazy_engine` 2，与历史基线一致）；
- [x] `ruff check` + `ruff format --check` 全绿、`lint-md` 0 警告。
- PR：**#1733**（`Closes #1721`，合入 dev 自动关卡）。

### 踩坑（面试可讲的两枚）

1. **环境假红淹没真信号**：首跑全量 32 failed——归因后 **29 个根因是 C 盘 0 GB**（SQLite temp / pytest capture 写系统盘；reconcile 的 `except` 吞掉异常 + loguru handler 又因磁盘炸 → 表现为「全 0 + assert 0==1」的假象，日志里看不到 disk-full 字样）。诊断路径：单跑绿 → 目录跑绿 → 磁盘修复后组合复现 1297 passed → 归因。教训：**先验环境基线，再怀疑代码**（当时若直接「修测试」会修错 29 个）。
2. **worktree git 元数据被反删**（`HEAD`/`config`/`index` 缺失）：`git status` 把所有文件显示为 staged-delete——**此刻 commit 等于删库**。修复：重建 `HEAD`（分支指针）+ `git reset --mixed HEAD`（只重建索引、不碰工作区文件）。

### 你学什么（0.5h，读两处 + 答三问）

- 读：`tests/conftest.py` 的 `_make_file_engine` docstring（四坑）+ `tests/core/test_session_connection_model.py` 两例判据。
- 答：
  1. StaticPool 下「B 的 close 回滚 A 的事务」为什么在生产不会发生？shared-cache 内存库把连接拆开了为什么又不行（锁模型差异在哪）？
  2. 「autouse fixture × 用例自建同名文件」这类撞名雷，为什么旧的内存库模型永远踩不到？换成文件库后为什么加前缀比改用例更对？
  3. 首跑全量 32 failed 里 29 个是磁盘满——如果当时直接「修测试」会怎样？你的诊断顺序（单跑 / 目录 / 组合 / 环境）各自排除了什么？

---

## 插曲卡：#1722 全量测试提速（B 档测试基建，不占 S 序位、不占 #7 编号）

**分支**：`feat/1722-pytest-speedup`（worktree `D:\codes\fundmate-1121`，基于 `origin/dev` 89051b135）
**PR**：**#1734**（`Closes #1722`，合入 dev 自动关卡）
**原则**：issue 纪律「先量化、禁止直接开分片」——durations 榜单先行，结论出来才动刀。

### 量化（验收①，已进 issue 评论）

- 基线全量 **91m56s**（2223 例）；`--durations=30` 显示 **30 项里 24 项是 `setup`**，粗算 fixture 占 **~87%** → 判定「均匀慢（每用例重复建库）」而非「少数坏测试拖尾」；
- 次要拖尾：`test_xalpha::test_indexinfo` 真联网 259s（`try/except + print` 无断言）；
- 附加发现：`slow` marker **注册了但全仓 0 处使用**——CI 的 `-m "not slow"` 一直是空操作。

### 改动（三件）

1. `tests/conftest.py` **模板库机制**：首测走完整路径（create_all + init_db）建「完成态、零业务数据」模板，**截取于测试体写入前 + 先 dispose**；后续用例 `shutil.copyfile` ×2 + patch `app.main.init_db`；模板目录 = `sha256(app/**.py + conftest)` 指纹，源码一变自动重建（防模板过期假红；新迁移必被指纹捕获，patch 掉 init_db 吞不掉未来迁移）。
2. `tests/test_xalpha.py` 模块级 `pytestmark = pytest.mark.slow`——启用空转的标记体系。
3. `docs/pytest/conftest.md` 专节（机制 / 时机坑 / 指纹 / 并行度结论 / 快集命令）。

### 结果（验收②③）

- 快集 `-m "not slow"` **~87m → 14m58s（≈ -83%）**，超额 ≥40% 线；**2223 例总数与断言不变**（2215 passed + 8 deselected；3 failed 恒为 #1727 基线）；
- 优化后 durations：setup 从 24/30 霸屏降到 top10 仅 3 项、最大 14.35s → 8.78s（守卫类 subprocess，非 app fixture）——**均匀慢根治**；
- **不引入任何并行**（单进程硬约束原样，OOM 回归面为零），提速 100% 来自「2223 次建库 → 1 次 + 字节复制」。

### 踩坑（面试可讲的一枚）

**模板截取时机**：若在 teardown 才复制模板，首测写入的业务脏数据会随模板**污染后续所有用例**——且症状是「测试居然还绿」的**假绿**，比假红难查一个量级。解法是把截取点钉在 `create_app` 完成后、测试体执行前，且先 `dispose` 回滚未提交页。这与 #1721「StaticPool 假阳性」是同一类课：**测试基建的坑永远表现为『信号与事实不符』，先修模型再修用例**。

### 你学什么（0.5h）

- 读：`tests/conftest.py` 的指纹/模板四函数 + `docs/pytest/conftest.md` 专节。
- 答：
  1. 为什么「慢」的根因判定要靠 durations 而不是直觉？24/30 是 setup 这个分布排除了哪些假设？
  2. 模板机制里防「假红」和防「假绿」的手段分别是什么？为什么指纹能保证 patch 掉 `init_db` 也不吞未来迁移？
  3. 为什么不加「全量 ≤ X 分钟」的时间断言做守卫？

---

*后续步骤卡（#7 = S4 可观测与评估……）完成时追加。*

