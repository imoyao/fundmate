# 火山方舟可用模型列表与维护规则（2026-09-28）

> **为什么有这份文档**：2026-09-28 核验三个指定模型（两 lite 一 pro）时发现，「模型能不能用」
> 分散在三层，任一层单独看都会得出错结论——2.0 Pro 在注册列表里但状态 Retiring（调用 404）、
> 2.1 Pro 注册在售但账号限额 429、deepseek-ga 系 09-27 还暂停 09-28 已恢复。
> 故立**单一列表 + 维护规则**；复跑工具 `scripts/ark_model_probe.py`（纯标准库，任意 Python 可跑）。

## 三层判读（只有第三层是最终答案）

| 层 | 数据源 | 回答什么 | 回答不了什么 |
|---|---|---|---|
| 1 注册面 | `GET /api/v3/models`（本 key 可见 135 个） | 模型是否存在：无 `status` 字段 37 个（推断在售）/ `Retiring` 29 个（退役中）/ `Shutdown` 69 个（已下线） | 账号当前能不能调 |
| 2 账号限额 | 无静态接口，只在调用错误里暴露 | 429 `SetLimitExceeded` = 账号 2130637670 自设用量上限，**按模型粒度**暂停（同账号 A 模型 429 不代表 B 模型也不可用） | 模型是否退役 |
| 3 实测 | `chat/completions` 真打一条 | **最终答案** | 历史趋势 |

**纪律**：写「可用」必须是第 3 层实测 OK。Retiring 模型的 404 报文是
`does not exist or you do not have access to it`——**存在性与权限混在一个报错里**，
先查第 1 层注册面再下结论，别把「退役」误判成「没权限」。

## 快照（2026-09-28，key = `ARK_API_KEY`，账号 2130637670）

| 模型 | 注册面 | 实测 | 消费点 / 说明 |
|---|---|---|---|
| `doubao-seed-2-0-mini-260428` | 在售 | ✅ OK | 账本精灵 / OCR 默认（`llm.py` `ARK_MODEL` 缺省值） |
| `doubao-seed-2-0-lite-260428` | 在售 | ✅ OK | lite 候选（本日指定核验①） |
| `doubao-seed-2-1-lite-260915` | 在售 | ✅ OK | lite 候选（本日指定核验②） |
| `doubao-seed-2-0-pro-260215` | Retiring | ❌ 404 | 本日指定核验③——**退役中不可调**；404 报文误导（把 Retiring 说成「不存在或无权」） |
| `doubao-seed-2-1-pro-260915` | 在售 | ❌ 429 | deep-review pro 首选；账号限额暂停（**PR #1743 deep-review 红灯的根因同此**） |
| `doubao-seed-2-1-turbo-260628` | 在售 | ❌ 429 | deep-review cheap 兜底，同账号限额暂停 |
| `deepseek-v4-pro-ga-260813` | 在售 | ✅ OK | deep-review pro——⚠️ **09-27 曾 429 暂停，09-28 实测已恢复** |
| `deepseek-v4-1-flash-260910` | 在售 | ❌ 429 | deep-review cheap，账号限额暂停 |
| `deepseek-v4-flash-ga-260731` | 在售 | ✅ OK | deep-review cheap——⚠️ **曾暂停，已恢复** |
| `glm-5-3-flash-260828` | 在售 | ✅ OK | deep-review cheap（方舟托管 GLM） |

**对 deep-review 的影响**：下次跑大概率能选到模型（pro 首选 2.1 Pro 仍 429，但
`deepseek-v4-pro-ga` 已恢复可顶）；若要豆包 Pro 参与，需到方舟控制台调高 / 取消账号用量上限（分钟级动作）。

**当前健康集（实测 OK，可直接选用）**：`2-0-mini`、`2-0-lite`、`2-1-lite`、
`deepseek-v4-pro-ga`、`deepseek-v4-flash-ga`、`glm-5-3-flash`。

## 消费点（改模型先看这里）

1. `backend/app/services/ai_recognizer/llm.py`——`ARK_MODEL` 缺省 `doubao-seed-2-0-mini-260428`
   （账本精灵对话与 OCR 共用，`.env` 可覆盖）。
2. `scripts/llm_health_probe.py`——`CANDIDATES` 池（deep-review 自动选型；CI 用
   `ARK_API_KEY_CODEREVIEW`，pro / cheap 两档轮询 + 轮换兜底）。
3. `.github/workflows/ai-review.yml`——顶部注释是候选池的人读版。

⚠️ **过时注释留痕（范围外，改到时顺手修）**：`ai-review.yml` 与 `llm_health_probe.py` 把
`deepseek-v4-{flash,pro}-ga-*` 标注为「暂停中」——2026-09-28 实测**已恢复**（见快照表）。
两个文件均为另一线（AI review）的配置，本 PR 不动它们，仅在此留痕防结论悬空。

## 维护规则

1. **复跑**：`PYTHONUTF8=1 python scripts/ark_model_probe.py`
   （Windows 管道下不设 `PYTHONUTF8=1` 会按 GBK 编码中文导致控制台乱码，文件本身不受影响；
   stdlib only；key 取环境变量 `ARK_API_KEY`，缺省回退 `backend/.env`；key 永不回显）。
2. **更新时机**：① 换 / 增模型候选时；② deep-review 红灯（429 / 404）排查时；③ 每月例行一次。
3. **改列表必同步的四处**：消费点 2（`llm.py` / `llm_health_probe.py`，3 中的 yaml 注释随其一动）
   + 脚本 `CANDIDATES` + 本快照表——**不另开第五份清单**。
4. 账号限额**会漂移**（按日 / 按量重置），历史快照只代表当日；任何「可用」结论以当次实测为准。
