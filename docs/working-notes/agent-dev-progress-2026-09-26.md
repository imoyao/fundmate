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
| S1-C | 退避与调用 trace | 做：`llm.py` 指数退避（429/5xx/超时可重试、4xx 不重试）+ 工具调用结构化日志；**不做**：trace 落库（归 S4） | 待做 |
| S2 | 记忆层 | 做：`agent_session` 表（先过数据准入四问）+ 后端权威会话 + 分层 prompt + 压缩；**不做**：跨会话长期记忆 | 待做 |
| S3 | 护栏与成本 | 做：`safety/` 三件套 + L1 铁律 + per-user 配额迁出内存（#1294） | 待做 |
| S4 | 可观测与评估 | 做：`agent_trace` 表 + 30 条评估集 + `scripts/agent_eval.py` | 待做 |
| S5 | 协议层 | 做：MCP server（stdio）；Skill 目录、多模型 failover 可裁 | 待做 |
| S6 | 面试收口 | 做：12 条追问口述 + 30 秒自介 + 简历定稿（证据逐条回填） | 待做 |

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

*后续步骤卡（#3 = S1-C……）完成时追加。*
