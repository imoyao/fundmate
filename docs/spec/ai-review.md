---
title: AI 代码审查（ai-review）机制与配置事实
---

# AI 代码审查（ai-review）机制与配置事实

本文件记录本仓 AI 代码审查链路的**实测机制事实**与**配置约束**，属**事实标准**。依据为 action 包源码逐行核对，非推测。

**核实日期**：2026-09-11（对应 `Nikita-Filonov/ai-review@v0.76.0`）

调整 `.ai-review-deep.yaml` 或排查「AI 没产出评论」之前，必读本文件。

## 1. 配置加载

- 配置优先级：**YAML > JSON > env > dotenv**（`ai_review/config.py`）。
- 本仓通过 env `AI_REVIEW_CONFIG_FILE_YAML` 指向根目录 `.ai-review-deep.yaml`。
- 本地可安装 `xai-review==0.76.0` 离线核对行为，无需触发 CI。

## 2. 执行线路

- `review-command: run` **只跑 inline + summary 两条线路，不含 context**（`cli/commands/run_review.py`）。
- 因此本仓的 `context_prompt_files` 属**死配置**，不要指望它生效。

## 3. Prompt 分层（易踩坑）

- YAML 的 `*_prompt_files` 进**用户消息**；只有 `system_*_prompt_files` 配合 `include_*_system_prompts` 才是 system。
- **system 优先级高于用户消息**：若只改前者、而内置 system 含冲突条款，**你的要求会被静默吞掉**。
  - 历史案例：内置 `default_system_summary.md` 禁止 markdown 且限制 1~4 句，压制了本仓的结构化摘要 → 已改用仓库自持的 `docs/configs/ai-review-system-summary.md`。

## 4. 配额与截断

- `max_inline_comments` / `max_context_comments` 的截断实现是 `comments[:limit]` —— **保留前 N 条、丢弃尾部**。
- 推论：prompt **必须要求模型按严重度降序输出**，否则高价值意见会被截掉。

## 5. 评论标记

- PR 上的 AI 评论以纯文本 tag 结尾：`#ai-review-inline` / `#ai-review-summary`。
- 可据此在 workflow 中判定「AI 是否真的产出过评论」。

## 6. 降噪策略

**结论：降噪靠结构性配置，不靠往 prompt 追加禁止条目。**

依据：曾用 16 天把 prompt 从 8.7KB 加到 29KB（近半是逐 PR 案例），模型仍在**已被明确禁止过的类别**上继续误报 —— 证明「清单式追加」不可收敛。

有效配置组合：

| 配置项 | 取值 | 作用 |
|--------|------|------|
| `review.mode` | `ONLY_ADDED_WITH_CONTEXT` | 默认 `FULL_FILE_DIFF` 会把整文件含历史行送入，是误报主因 |
| `max_inline_comments` / `max_context_comments` | `5` / `3` | 硬上限，实测生效（此前 29~52 条） |
| `inline_comment_fallback` | `false` | 关闭「定位失败降级为普通评论」的刷屏路径 |
| `agent.enabled` | **`false`** | 见第 7 节 |

**回归护栏**：`scripts/verify_ai_review_config.py`（离线，不调 LLM）。用改动前的 YAML 跑会报 11 条 FAIL。

> **2026-09-18 边界补充（#1577）**：结构降噪已到顶。第 4 次 `# added` 幻觉复发出现在**换池后的最新最强付费档**
> （`doubao-seed-2-1-pro-260915`）上，证明残余误报属**模型行为**——既不是措辞问题（点 1 早已证明），
> 也不是档位问题（原先的推断被本次反证推翻）。故后续不再追加 prompt 禁令，**也不引入自动证据校验层**
> （issue #1577 方案 B 已评估为不做：按原样写法实测会漏 #1496、并会误杀 #1491 的真意见，而删除 PR 评论不可逆，
> 误杀代价高于噪声代价，见 `docs/spec/decisions.md` 2026-09-18）。现状口径维持：**deep-review 产出不作为合并依据**，
> 误报按案例库登记 + 人工忽略处理。

## 7. `agent.enabled` 必须保持 false

v0.76.0 的 agent 模式在本仓环境下**必然失败**：

1. 包内只读命令白名单（`services/policy/service.py`）仅含 `ls` / `cat` / `rg` / `grep` / `git show|diff|log|rev-parse|ls-files`，**不可配置扩展**；
2. CI runner 未预装 ripgrep → `FileNotFoundError: 'rg'`；
3. 即便装上 rg，模型查看文件片段仍会使用 `sed -n '1,140p'` → `Agent command blocked by policy` → `iteration N returned unstructured response` → `Empty LLM output` → **零评论**。

已四次复现（PR #1414 / #1415 / #1417 / #1418）。

> **配套改动已同步（2026-09-11）**：`docs/configs/ai-review-prompt.md` §〇 原先写着
> 「agent 模式已开启，你可以执行只读命令」并据此要求「先核实再发言」——与本节结论直接冲突。
> 后果是模型面对**不存在的能力**：要么闭嘴（另一条零评论路径），要么编造 `file:行号` 假装核实过。
> 该节已改写为「**没有文件系统与命令能力，不得对仓库做任何断言**」，§一 / §六 / §七 / §八 的
> 相关表述同步收紧；`docs/configs/ai-review-known-false-positives.md` 顶部补了口径说明。
> **凡改动 `.ai-review-deep.yaml` 或 prompt，请同时核对本节**——这是本仓最易反复漂移的一处。

> **排障指引**：AI 零产出时，**先读日志找 `Empty LLM output` / `blocked by policy`**，不要先怀疑额度或模型档位。模型只要真跑完，会在结论里列出「已核对」的行号。

## 8. 健康探测与运行期故障转移

**探测选型 ≠ 运行期可用。** `scripts/llm_health_probe.py` 只发一次极短请求（`max_tokens: 5`），
与真实审查（长上下文 + 多轮）的限流概率**完全不同**。两次实测：
2026-09-10 PR #1412（智谱 code 1302）、2026-09-17 PR #1567（智谱 code 1305）——
**探测 200 通过、真实调用 429、零评论**；同一轮里其它健康候选探测过却用不上，
因为 ai-review v0.76.0 只接受**一套** `model / endpoint / token`，没有跨模型重试。

**2026-09-17 起改为两轮故障转移**（`.github/workflows/ai-review.yml`）：
第 1 轮零产出 → 用 `EXCLUDE_MODELS` 排除该模型重新探测 → 换一个候选重试第 2 轮；
第 2 轮仍零产出才判 job 失败。校验逻辑抽到 `scripts/ai_review_verify_guard.js`（两轮共用，避免复制漂移）。
多出的成本只落在失败运行上（这类运行本来就得人工重跑）。

**候选池（2026-09-17 重排：越新越强越前——老模型弱，找不出问题）**，全部走方舟同一把 key：

| 档位 | 模型 | 日期 | 备注 |
|------|------|------|------|
| pro | `doubao-seed-2-1-pro-260915` | 2026-09-15 | 默认首选 |
| pro | `deepseek-v4-pro-ga-260813` | 2026-08-14 | 暂停中（安全体验模式），恢复后自动可用 |
| cheap | `deepseek-v4-1-flash-260910` | 2026-09-14 | |
| cheap | `glm-5-3-flash-260828` | 2026-09-03 | 方舟托管 |
| cheap | `deepseek-v4-flash-ga-260731` | 2026-08-03 | 暂停中（同上） |
| cheap | `doubao-seed-2-1-turbo-260628` | 2026-06-16 | 兜底 |

- **已删除**：智谱独立线路（原 `free` 档 `glm-4.7-flash` / `glm-4-flash` / `glm-4v-flash`）——
  实测常 429 且产出价值低，纯浪费 Actions 分钟；GLM 家族改由方舟托管的 `glm-5-3-flash` 承接，
  `ZHIPU_API_KEY` secret 可删。
- **暂停中的模型保留在候选池**：`deepseek-v4-{flash,pro}-ga-*` 当前被账号的方舟「安全体验模式」
  限额暂停（429 `SetLimitExceeded`），探测标 429 后自动跳过、不影响其它候选；在方舟「模型开通」页
  调整或关闭该模式后，**无需改代码**即可自动重新参与（删掉反而要多改一次代码）。
- 推论（不变）：**未要求 infra 执行时，该 check 的绿色不作数**。

## 9. 相关文件

- 配置：`.ai-review-deep.yaml`（仓库根目录）
- 提示词：`docs/configs/ai-review-prompt.md`、`docs/configs/ai-review-system-summary.md`、`docs/configs/ai-review-known-false-positives.md`
- 护栏与探测：`scripts/verify_ai_review_config.py`、`scripts/llm_health_probe.py`
- 产出校验（防假成功，两轮共用）：`scripts/ai_review_verify_guard.js`——**回归用例**：`scripts/tests/ai_review_verify_guard.test.js`（#1584；`pnpm test:scripts`，或 CI job「守卫:脚本单测 (scripts)」；零新依赖、纯 mock 无网络）——**2026-09-18 起（#1581）**该脚本另统计 AI 评论里的「生成标记」类幻觉（`# added` 等固定形态，inline + summary 双通道）并写进 job summary：**只计数、不删除评论、不改变 job 成败**。
