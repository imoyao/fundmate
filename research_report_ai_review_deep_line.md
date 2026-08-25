# AI Code Review 双线路接入：实现说明与实测报告

日期：2026-08-23。分支：`feat/ghost-duplicate-scan`（提交 `9918f05`，已推送）。

## 一、Token 校验结论

`backend/.env` 中的 `ARK_API_KEY_DEEPSEEK` 经实测**可用**（火山方舟 `ark.cn-beijing.volces.com/api/v3`，OpenAI 兼容）：

- `GET /models` 返回 200，目录可见 130 个模型。
- 实际可调用（chat/completions 返回 pong）：
  - `deepseek-v4-flash-ga-260731`（Flash，快而便宜）
  - `deepseek-v4-pro-ga-260813`（Pro，更强，带深度思考）
  - `doubao-seed-2-0-mini-260428`（既有 OCR 在用）
- 目录可见但**未开通权限**（调用 404）：`deepseek-v3-*`、`deepseek-r1-*`、`glm-4-7-*`、`doubao-seed-1-6-*` 等。
- 注意：当前 `ARK_API_KEY_DEEPSEEK` 与 `ARK_API_KEY` 是**同一个 key 值**。若希望深度审查独立计费/限额，需在火山方舟控制台另建 key。

## 二、双线路实现方案

复用现有 `Nikita-Filonov/ai-review@v0.76.0` action，在同一 workflow 并行两个 job：

| 线路 | job | 模型 | 模式 | 成本 | 输出 |
|---|---|---|---|---|---|
| 免费快速（原） | `ai-review` | 智谱 GLM-4.7-Flash | `run-summary` | 免费 | PR 留一条总结评论 |
| 深度完整（新） | `deep-review` | 火山方舟 DeepSeek V4 Pro | `run`（summary + context + inline） | 按量计费 | 逐行 inline + 跨文件 + 深度总结 |

新增/修改文件：

- `.github/workflows/ai-review.yml`：追加 `deep-review` job，温度 0.1、max_tokens 16000、API URL `https://ark.cn-beijing.volces.com/api/v3/`。
- `.ai-review.yaml` 与 `.ai-review-deep.yaml`：两份配置现已指向**同一份**共享 prompt（见下），强度差异由各自 `review-command`（`run-summary` / `run`）+ prompt 内「按 review-command 自适应」段落区分，无需两份内容。
- `docs/configs/ai-review-prompt.md`：两条线路共用的**单一权威 prompt**——审查强度定位（`run-summary` 偏总结性但深入、`run` 偏逐行 + 跨文件 + 严重度分级、宁多报）、严重度分级（阻断/主要/次要）、7 大审查维度（逻辑/精度/契约/安全/性能/可维护性/测试）、fundmate 专属清单（含双库 `DATA_DOMAIN_REGISTRY` 约束、`get_db()` 已知遗留 #1085 不阻塞、N+1/全表加载 OOM 风险、loguru、信封、前端 any 禁令、独立脚本豁免等）、三种输出模式说明。

> 修订（2026-08-25，PR #1092）：原 `docs/configs/ai-review-deep-prompt.md` 与 `docs/configs/ai-review-summary-prompt.md` 两份独立 prompt 已合并为上述单一 `ai-review-prompt.md`，两份旧文件已删除；两个 yaml 的三个 `*_prompt_files` 全部改为指向它。以后调整审查规则只需改一处。

## 三、实测效果

用 DeepSeek V4 Flash 对真实 diff（#1075 信封修复，49 行）按深度 prompt 实测，120s 内输出完整审查报告，质量要点：

- 正确识别信封从 `{code:200,...}` 到 `{data,message}` 的契约变更，并提示「需确认前端是否依赖 code 字段」的核查点。
- 指出错误分支 `message: str(e)` 可能泄露内部异常信息；建议 loguru 记录堆栈、对外返回通用文案。
- 指出新增测试只覆盖成功响应、未覆盖错误信封（真实缺口，可补测）。
- 次要建议：`error_code` 魔法字符串宜收敛为常量；成功响应是否也带 `error_code` 需与前端确认；`except Exception` 范围过广应留日志。
- 「已核对」清单逐维度说明，非空评。

结论：深度线路效果达标，输出颗粒度与深度明显优于免费总结，可投入 PR 日常审查。

## 四、待办（需人工完成）

1. GitHub 仓库 Settings → Secrets → Actions 新增 `ARK_API_KEY_DEEPSEEK`（与本地 `.env` 同值）。未配置前 `deep-review` job 会因缺 secret 报错，免费线路不受影响。
2. （可选）若深度线路需要独立计费，在火山方舟控制台另建 key 并同步替换 `.env` 与 GitHub Secret。
3. 首个 PR 触发后可观察两条评论的分工，按需微调共享 prompt（`docs/configs/ai-review-prompt.md`）或模型（如换 `deepseek-v4-flash-ga-260731` 降本）。

## 五、备注

过程中发现另一并发 agent 把主工作区切到了 `feat/import-backfill-null-hash`，曾导致未提交改动丢失；本改动已改走 `git worktree` 在独立目录完成并提交，避免互相干扰。
