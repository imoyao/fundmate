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
| S1-B | 前端最小对话页 | 做：`views/agent/` 页面 + `api/agent.ts`，三态（澄清/结果/错误）渲染；**不做**：流式输出、历史会话列表 | 待做 |
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
- ⬜ 待办：CI 门禁绿；本地起服 curl 三态人工走查（随 S1-B 一起）。

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

*后续步骤卡（#2 = S1-B……）完成时追加。*
