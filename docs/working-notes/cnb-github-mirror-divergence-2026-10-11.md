# CNB ↔ GitHub 镜像断链事故（2026-10-11）

> 结论一句话：**在 CNB 镜像仓合 PR，必然让每小时的代码镜像静默停摆。**
> 本记录留证并给出修法，规则已钉进 `AGENTS.md`「双端协作（CNB ↔ GitHub，强制）」。

## 1. 拓扑

```text
GitHub imoyao/fundmate   ← 原始仓：PR / CI / 分支保护都在这里
      │  ▲
      │  └── issue 评论回写（.github/workflows/cnb-github-backfill.yml，每日 18:30 UTC）
      │
      ▼ 代码镜像：每小时 fast-forward（CNB 侧 sync/mirror 分支上的 crontab）
CNB duoduobei/fundmate   ← 镜像仓：本应只读
```

关键约束：`sync/mirror` 的脚本**只允许 fast-forward**：

```bash
if git merge-base --is-ancestor "refs/dst/$b" "refs/src/$b"; then
  git push --quiet dst "refs/src/$b:refs/heads/$b"     # 快进
else
  echo "[$b] 无法快进：CNB 侧存在独有提交（dst=$D src=$S），已跳过，需人工处理"
  FAILED=1
fi
```

也就是说：**CNB 侧一旦有 GitHub 没有的提交，镜像立刻停止推进**，而且只打一行日志。

## 2. 断链是怎么发生的（带时间戳的证据）

镜像任务的每次运行都能从构建日志里读到它对 `dev` / `main` 的判定。逐小时取三帧：

| 运行时间（UTC） | 构建号 | 日志原文 |
|---|---|---|
| 10-11 01:00 | `cnb-nor-1k4k7irh8` | `[dev] 快进 13717eec -> 3be109f5` / `[main] 已一致 cc1d4220` |
| 10-11 02:00 | `cnb-833-1k4kb0iri` | `[dev] 快进 3be109f5 -> 48566488` / `[main] 已一致 cc1d4220` |
| **10-11 03:00** | `cnb-ldc-1k4keea6u` | `[dev] 快进 48566488 -> 0de73e21` / `[main] 已一致 cc1d4220` |

最后一帧把 CNB `dev` 停在 `0de73e21`（= GitHub PR #2048 的 merge commit），**之后它再没动过**。

同时，03:29 / 03:30 两个 PR **在 CNB 侧**被合并：

```text
510c787f  合并来自 feat/2-cnb-github-backfill 的合并请求 #116     ← 03:30
17e8e6be  feat(bridge): CNB → GitHub issue 评论回写（#2）
dc3feb28  合并来自 fix/2034-welcome-drop-structure-donut 的合并请求 #115  ← 03:29
49272b6a  fix(welcome): 移除资产构成环形图（归资产总览）(#2034)
0de73e21  ← 最后一次快进的落点，两侧共有
```

于是 `dev` 变成：CNB 独有 4 个提交，GitHub 独有 8 个提交（PR #2049 / #2051 那一串）。

**04:00 那一轮就是断链点**：`merge-base --is-ancestor` 判否 → `FAILED=1` → 任务报错停摆。

`main` 同理，只是更早：CNB `main` 停在 `4eeba908`（PR #114 在 CNB 侧合并的产物），
而 GitHub `main` 是 `cc1d4220`（发版 PR #1765）。CNB `main` 早已是分叉态。

## 3. 为什么这么难发现

1. **失败只打一行日志。** 任务红了没人盯（它是 crontab，不是 PR check），
   从外部看「停摆」和「正常」完全一样。
2. **`git push --dry-run` 对 `cnb.cool` 是假信号。** 实测：对任何 refspec 都返回
   `exit 0`，包括不存在的 ref（`nonexistent-ref-xyz`）和瞎编的 SHA（40 个 `9`）；
   同样的命令对 GitHub 会正常报错。任何「先 dry-run 预检」的 CNB 侧脚本都是空转。
3. **双端 PR 编号是独立空间。** CNB PR #115 / #116 在 GitHub 侧分别撞上 2021 年的
   dependabot PR，交叉引用不写仓库前缀必然误导。

## 4. 修法

### 4.1 一次性救援（本次）

把 CNB 侧的 4 个独有提交在 GitHub 侧重放：

```bash
git worktree add /tmp/wt -b rescue/2-cnb-commits <GitHub dev 的 tip>
git cherry-pick 49272b6a 17e8e6be                 # 两个改动本身
# 另两个是 CNB 的 merge commit，不重放（cherry-pick 不需要 merge commit）
```

其中 `49272b6a` 与 GitHub 侧已合的 #2050（`3a8264f0`）在 `OverviewSummaryCard.vue`
同一段模板上冲突 —— 冲突解法是**两边都要**：保留 #2050 的 `host-header` +
`PnlCalendarCaliberIcon` 同行结构，同时采用 #2034 的新标题「资产大类构成」与口径 tooltip。

顺带把两个「本不该缺」的东西补进版本控制：

- **`.cnb.yml` 首次入库**：这份配置此前只活在 CNB 的 `sync/mirror` 分支上，
  GitHub 仓根本看不到，等于镜像链路无人可评审（已核对：入库内容与该分支上的
  现存脚本**逐字节一致**，不含任何新增行为）；
- **`AGENTS.md` 新增「双端协作（CNB ↔ GitHub）」强制节**：把上面五条结论钉死。

### 4.2 根治（规则，已入库）

1. **CNB 侧只读** —— 禁直接 push、禁在 CNB 合 PR。根因是数学上不可共存：
   镜像只允许快进，而 CNB 侧合 PR 必然产生独有 merge commit。
2. 交叉引用必须带仓库前缀。
3. 别在 `dev` / `main` 上改镜像配置（会被同步覆盖或产生独有提交）。
4. 不用 `git push --dry-run` 对 CNB 做预检。
5. 断链的发现 = 比对两侧 SHA；修法 = cherry-pick 成 `rescue/` 分支回 GitHub。

## 5. 尚未闭环的项

- **`sync/mirror` 的可见性**：FAILED 只落日志，没有通知通道。
  与 #1568 那条「E2E 失败可见」是同一类问题（静默失效）。
- **救援 PR 合并后**，仍需人工确认下一轮镜像（每小时整点）恢复 `[dev] 已一致`，
  才算真正闭环。
