---
title: worktree gitdir 反删恢复手册
status: v1（2026-09-28，源 #1737 第 3 次复发）
owner: 阿垚
---

# worktree gitdir 反删恢复手册

> 适用故障：`.git/worktrees/<name>/` 被清空，导致该 worktree 内所有 git 命令报 `fatal: not a git repository`。
> 事故原点、时间线与复发史见 issue **#1737**；本册是它「要做的事」第 4 项，把当时临时摸索出来的恢复手法固化成可复用步骤。
> **根因（动作者）至今未确认**，见 §7——本册只管恢复与取证，不声称能根治。

## 1. 症状识别

在 worktree 目录内执行任意 git 命令报错：

```plain
fatal: not a git repository: D:/codes/fundmate/.git/worktrees/<name>
```

且主仓侧 `git worktree list` 已不再列出该 worktree。

关键判断：**工作区源码文件通常完好无损**，坏的是 git 元数据（gitdir）。这一点决定了它可以救回来——见 §2。

## 2. 为什么能救回来（原理）

worktree 的 gitdir 只是一层**指针目录**，包含四个小文件，真正的对象数据与分支引用都存在主仓公共区：

| gitdir 内容 | 作用 | 丢失影响 |
|:---|:---|:---|
| `HEAD` | 指向当前分支 ref | 不知道自己站在哪 |
| `commondir` | 指回主仓 `.git` | 找不到对象库 |
| `gitdir` | 反向指回 worktree 的 `.git` 指针文件 | 反向引用断裂 |
| `config` | worktree 级配置（含 `core.worktree`） | 配置缺失 |
| `index` | 该 worktree 的暂存区索引 | 改动集看起来全乱 |

据此：

1. **丢的是指针，不是数据**：objects 在主仓 `.git/objects/`（或替代品），分支 ref 在主仓 `refs/heads/<branch>`，两者都没丢 ⟹ 可以重建。
2. **`git read-tree HEAD` 只写索引**：它把 HEAD 提交的树写进 `index`，不碰工作区任何文件 ⟹ 对源码零风险。这是本手法安全性的核心。
3. **唯一不可救的情形**：删除恰好发生在 `git commit` 进行中，此时 index 锁、暂存快照、`ORIG_HEAD` 可能一并丢失 ⟹ 可能丢提交。此类不要照搬本册，先人工核对。

## 3. 恢复四步

以下用 PowerShell，路径以主仓 `D:\codes\fundmate`、worktree 名 `fundmate-1121`、分支 `feat/xxx` 为例，按需替换。

### 第 0 步：先确认，别急着 add

```powershell
# 主仓：看看 gitdir 是否真的没了，分支 ref 还在不在
Test-Path D:\codes\fundmate\.git\worktrees\fundmate-1121
git -C D:\codes\fundmate rev-parse --verify refs/heads/feat/xxx
```

分支 ref 存在 ⟹ 可重建。若连分支 ref 本身都取不出来，**先停下来**，见 §5。

### 第 1 步：重建最小 gitdir（四件套）

```powershell
$gd = 'D:\codes\fundmate\.git\worktrees\fundmate-1121'
New-Item -ItemType Directory -Force -Path $gd | Out-Null
Set-Content -Path "$gd\HEAD"        -Value 'ref: refs/heads/feat/xxx' -NoNewline
Set-Content -Path "$gd\commondir"   -Value '../..'                    -NoNewline
Set-Content -Path "$gd\gitdir"      -Value 'D:/codes/fundmate-1121/.git'
Copy-Item   -Path D:\codes\fundmate\.git\config -Destination "$gd\config"
```

要点：

- `HEAD` 与 `commondir` 用 `-NoNewline` 写，**不要带 BOM、不要带换行**（带 BOM 会让 git 解析失败）；
- `gitdir` 用正斜杠路径；
- `config` 直接复制主仓 `.git\config`（含 remote / core 配置）。

### 第 2 步：重建索引（只动 index）

```powershell
cd D:\codes\fundmate-1121
git read-tree HEAD
```

### 第 3 步：核对改动集是否精确

```powershell
git status --porcelain -uall
```

把输出的改动清单与你心里「应该有的改动」**逐条人工比对**。2026-09-27 那次为 7 改 2 新，重建后完全一致，才继续正常作业。

对不上 ⟹ 见 §5，**不要** `git add -A`。

### 第 4 步：快照备份

```powershell
$gd   = 'D:\codes\fundmate\.git\worktrees\fundmate-1121'
$bak  = "D:\codes\fundmate\.git.corrupt.safe\worktrees.fundmate-1121.bak"
Copy-Item -Path $gd -Destination $bak -Recurse -Force
```

重建一次的代价是几分钟，被再次清空的代价是重来一遍——所以务必快照。

## 4. 恢复验收清单

- [ ] `git -C <worktree> rev-parse --git-dir` 正常返回
- [ ] `git -C <worktree> worktree list` 重新列出该 worktree
- [ ] `git status --porcelain -uall` 的改动集与实际改动**逐条一致**
- [ ] `git diff` 能出内容，`git log -3` 能出历史
- [ ] 试提交一次（哪怕只是 `--dry-run` 或空提交前的 `git diff --cached`）确认路径通
- [ ] gitdir 已快照进 `.git.corrupt.safe\worktrees.<name>.bak`

## 5. 禁忌与边界

1. **改动集对不上，禁止 `git add -A`**：此时 index 修复基线与你的实际改动不一致，`add -A` 会把错误快照固化成提交，反而制造真事故。先倒回去看 §3 第 1 步的 `HEAD` 是不是指错了分支。
2. **禁止 `git checkout -f` / `git reset --hard`**：本故障不损工作区，这两个命令才是真正会毁工作区的操作。
3. **commit 进行中受灾**：不要照搬本册，先人工核对 `ORIG_HEAD`、reflog 与 `MERGE_MSG` 残留。
4. **`prune` 不是恢复手段**：`git worktree prune` 只清理元数据；在 gitdir 已空的场景下跑它只会把记录抹掉。**先救，后 prune。**

## 6. 复发取证模板

再发时按此模板留痕（直接贴到 #1737 评论），不要凭记忆描述：

| 字段 | 取值办法 |
|:---|:---|
| 精确时间戳 | `(Get-Item D:\codes\fundmate\.git\worktrees).LastWriteTime` + 主仓 `.git\logs\HEAD` 尾部条目时间 |
| `.git/worktrees` 目录 mtime | 同上；mtime 变化即说明有子项被增删 |
| 同时段 `D:\codes` 下新建目录 | `Get-ChildItem D:\codes -Directory \| Sort-Object CreationTime -Descending \| Select-Object -First 10` |
| 同时段是否有 worktree 写操作 | 回忆/翻会话日志：`git worktree add / remove / prune`、IDE/工具的批量 worktree 操作 |
| 是否并行跑 pytest / build | pytest 与本次故障无因果关系，但需留证排除 |
| 受影响 worktree 清单 | `git -C D:\codes\fundmate worktree list`（事发前 vs 事发后对比） |

## 7. 未完成：根因未定

三次事件同族（2026-09-25 主仓 `.git` 内容被移入 `.git.corrupt.safe/`；2026-09-27 一批 `origin/*` 远程跟踪引用被清；2026-09-27 worktree gitdir 整目录被清空），嫌疑方向三条，**均未证实**：

1. WorkBuddy 的 worktree 批量操作；
2. 并行运行的其他 agent 会话；
3. 某个工具脚本。

动作者没有明确结论之前，本册只提供「恢复 + 快照 + 取证」，不做针对性封堵——盲改配置的风险高于复发风险。拿到结论后再在本册追加「根治」章节。
