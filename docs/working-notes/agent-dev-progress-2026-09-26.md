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
| S2 | 记忆层 | 做：`agent_session` 表（先过数据准入四问）+ 后端权威会话 + 分层 prompt + 压缩；**不做**：跨会话长期记忆 | 🚧 进行中（分支 `feat/1121-agent-s2`，见卡 #4） |
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
  - 开发中踩坑一枚（值得进面试故事）：`test_chat_result_carries_tools_metadata` 曾报 `StaleDataError: UPDATE agent_session 匹配 0 行`——测试库 StaticPool 单连接下，请求中途工具链 `with get_session() as db:` 退出时 `close()` 的连接复位会把**同一连接上未提交的 INSERT 回滚掉**（最小复现证实：`b.close()` 后行数归零）。生产各 Session 走独立连接只回滚自己的事务，不受影响；测试侧规避 = 会话行先经 `db` fixture 提交（用例内有注释）。

### 你学什么（≤0.5h，读两处 + 答三问）

- 读：`agent_loop.run_agent` 的 prompt 组装段 + `session_store.load_or_create`。
- 答：
  1. 「关键信息卡 / 滚动摘要 / 最近 N 轮原文」三层各解决什么丢失模式？为什么关键卡必须永不压缩？
  2. 轮次闸从内存挪进表，除了「重启不丢」还顺带修了什么一致性问题？
  3. 为什么压缩失败要选「截断」而不是「不压缩」？两种失败各长什么样？

---

*后续步骤卡（#5 = S3 护栏与成本……）完成时追加。*
