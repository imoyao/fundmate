# Issue 分诊与派活闸门（2026-10-18）

源：CNB `#564`。用户拍板四件事——**先回流已关的 → 分诊/打标签/写评论 → 派活每轮 3 张、
每天两轮 → 合入不打 automerge，人工验证后合并**。本文记录实测数据与判据推导，
口径已写进 `AGENTS.md`「Issue 分诊与派活（D58）」。

## 一、看板有多脏（实测，2026-10-18）

| 指标 | 实测 |
|---|---|
| CNB open 卡 | **198** 张 |
| 其中带 `GitHub 同步` 标签 | 145 张 |
| 其中 `GitHub 同步` 卡**不在** `github_cnb_state.json` 里 | **48** 张（open）+ 约 300 张（closed） |
| 状态文件只认出 | 107 张（open+closed），认正文后 **452** 张 |

结论：**先回流再分诊**。脏看板上做出的判断不值钱——扫「全部 open 卡」的作业读到的
是假库存（这正是本卡第一轮评估里 197/198 的来源）。

## 二、回流的两处缺口（`scripts/bridge/mirror_state_sync.py`）

1. **只认状态文件 ⇒ 认卡不全**。`mirrored_cards()` 只查 `github_cnb_state.json`，
   而那是**缓存**（只在建卡成功的路径写入）。48 张 open 卡因此永远进不了 `plan()`——
   一条永远不会被执行的代码被读成「已经对齐」。与 CNB `#450` 的 224 张重复卡同因。
   修法：**缓存优先、卡面正文兜底**（URL 优先，抠不到再用 `GitHub 编号：#N`）。
2. **认不出编号的卡被静默丢弃**。现改为：open 的逐张列出，closed 的只计数
   （实测认不出的 open 卡只有 1 张；346 张认不出的多为已关闭，列出来只会淹没真问题）。

两处都被 `scripts/tests/test_mirror_state_sync.py::TestMirrorCardDiscovery`（7 条）钉住，
并做过回退探针（`if False and …` ⇒ CAUGHT）。

## 三、分诊：固定枚举，判据全机械

`scripts/triage/issue_triage.py`，一卡一次，只贴标签 + 写一条评论，**不改代码**：

| kind | 判据 | next |
|---|---|---|
| `stale` | 归档标签 / 正文「不再做 / 已被替代」 | `close` |
| `tracker` | 引用 ≥2 张其他卡 / 标题含「系列」/ 卡面整行加粗 | `archive` |
| `decision` | 卡面**明写**「需拍板 / 待决策」 | `product_gate` |
| `task` | 有可逐条对照的验收标准 | `dispatch_npc`（需过闸门） |
| `discuss` | 以上都不是 | `human_review` |

198 张实测分布：`tracker` 74 / `task` 70 / `discuss` 26 / `stale` 23 / `decision` 5。

**一个必须记住的坑**：镜像卡的溯源块是模板文字，里面有 `AGENTS.md` 与
`scripts/bridge/…`。不切掉的话，10+ 张无关的卡会被判成 `risk=high`
（首版实测踩到）。`strip_mirror_header()` 只在「首个 `---` 之前出现 `GitHub 编号：`」
时才切——人工卡里的 `---` 不能被误伤。

## 四、派活闸门与额度

闸门 = `kind=task` + `size=S` + `risk=low` + 卡面不出现
`money.py` / `db_factory.py` / `conventions.md` / `AGENTS.md` / `.cnb.yml` /
`scripts/guard_*` / `migrations/`；另有一条 design 护栏（改文案/视觉要同步 `design.md`）。

**实测可派数量为 0**（198 张全扫）。不是判据坏了：存量里确实没有「又小又干净」的活。
低风险且有验收的卡有 17 张，但都卡在 `size=M`。**不得为了跑满额度降标准。**

额度是**两条**：分诊每轮 50 张（无副作用）、派活每轮 3 张、每天两轮（要开 PR、要人 review）。
合并成一个数的话，130+ 张待分诊的卡要跑三周，期间看板一直是脏的。
被额度挡掉的卡必须报出来（`⏸️ 另有 N 张因额度未处理`）。

## 五、合入：不贴 automerge（用户拍板）

绿灯 ≠ 审查通过：`.ai-review-deep.yaml` 在 `upstream_unavailable` 时把判定 job 判成
**skipped（不是 pass）**，门禁分不清「通过」与「没跑」。人工合入是最后一道能看见这件事的关口。

## 六、护栏

- `scripts/tests/test_issue_triage.py`：36 条，含 **3 个变异探针**
  （模板当判据 / 闸门漏掉 size / 两条额度混一）。其中「`需决策` 标签存在」那条
  是探针 MISSED 后补的——补之前删掉标签追加，**一条用例都不会红**。
- 「两条额度混一」那条连改五版才咬住真问题，最后**承认其中一半不可观测**（见用例 docstring）：探针 MISSED 时先问「改这段到底改没改变行为」，没改变就别造假用例。
- 并入 `ci.yml` 的 `scripts_test` job，**不新增 job**（不动 `gate.needs`）。
- 登记在 `guard_rule_registry.py` 的 `RULE_REGISTRY`。
