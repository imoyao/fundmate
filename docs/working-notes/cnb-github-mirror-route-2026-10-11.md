# CNB ↔ GitHub 双向镜像：路线决策与落地设计（2026-10-11）

> 源 issue：CNB #118（本卡）
> 关联：#2（issue 镜像）、#116（CNB→GitHub 回写）、#123（main/dev 分叉）
> 结论：**要回流**；但「镜像」在本仓的正确形态不是双向同步，而是
> **单源 + 两条单向管道**。GL 的落点仍然是 GitHub。

## 1. 先回答那个问题：CNB 造的东西要不要回流 GitHub？

**要。** 理由不是「统一好看」，而是三条已经真实付过代价的：

1. **不回流 = 没有评审、没有回归网**。`be7896a6`（issue 镜像脚本 + `.cnb.yml`）就是活证据：
   它在 CNB 上诞生，GitHub 侧 `git rev-list --all --objects` 里**一个对象都没有**，
   连带 15 条单测、`docs/dev/github-cnb-mirror.md` 全部不在版本控制内。
2. **不回流 = 随时被下一次同步删掉**。同一条证据的另一面：因为 GitHub 没有它，
   `dev` 一旦被 GitHub `dev` 覆盖，`be7896a6` / `4eeba908` 就消失了（2026-10-11 实测）。
3. **不回流 = 双端编号空间打架**。CNB PR `#116` ≠ GitHub PR `#116`，交叉引用必须带仓库前缀，
   否则下一个读文档的人会去找一个 2021 年的 dependabot PR。

**所以「CNB 是只读镜像仓」这条规则本身是对的**——错的是让它成为「只能看不能改」之后，
却没有给改动一条合法的回家路。下面的设计就是把那条路修出来。

## 2. 实测现状（2026-10-11，全部可复现）

### 2.1 四个分支实测（全量 fetch，非浅克隆）

```text
                     GitHub (imoyao/fundmate)        CNB (duoduobei/fundmate)
dev   16e807c4  ←→  c5219ef7
main  cc1d4220  ←→  4eeba908
```

复现命令（必须全量 fetch——浅克隆会给出**虚假的分叉读数**，见 §2.4）：

```bash
git init /tmp/d3 && cd /tmp/d3
git remote add gh  https://github.com/imoyao/fundmate.git
git remote add cnb https://cnb.cool/duoduobei/fundmate.git
git fetch gh                      # 全量，23 个分支
git fetch cnb main dev
```

读数：

| 分支 | merge-base | CNB 独有 | GitHub 独有 | 判读 |
|---|---|---|---|---|
| `dev` | `0de73e21` | **6** | 8 | **真分叉**，两侧互不包含 |
| `main` | `cc1d4220` | **408** | 0 | `gh/main` **是** `cnb/main` 祖先（不是分叉） |

`main` 那 408 个「独有」里，只有 **2 个**是 CNB 自己造的
（`be7896a6` 镜像脚本 + `4eeba908` 它的 merge commit），其余 406 个是
`gh/main → gh/dev` 这 414 个提交的一部分——即 CNB `main` 停在发版后、又往前跑到了 `dev` 的位置。

**关键区别（决定修法）：**

- `dev` 是**真分叉**（双方各有独有提交）⇒ 需要双向 cherry-pick 救援；
- `main` 是**CNB 单方面领先**（GitHub 无独有）⇒ 理论上可以直接快进压回去，
  但那 2 个 CNB 自造提交会丢 ⇒ **不要压**，先把它们送回 GitHub 再让镜像自然对齐。

### 2.2 「CNB 独有提交」逐一核验为真

在**隔离的克隆**里只 fetch GitHub，再逐个 `git cat-file -e`（关键：不能复用含 CNB 对象的
本地对象库，否则会得到假阳性——本轮第一次测就是栽在这里）：

```bash
git init /tmp/iso && cd /tmp/iso
git remote add gh https://github.com/imoyao/fundmate.git
git fetch --depth=30 gh dev
# CNB dev 独有的 6 个：
for c in dc3feb2 49272b6 510c787 17e8e6b c5219ef b0485fe; do
  git cat-file -e "$c" && echo "存在" || echo "MISSING"
done
# → 六个全部 MISSING
```

### 2.3 断链是「静默」的——这是最贵的一条

`sync/mirror` 分支上的快进脚本只允许 fast-forward：

```bash
if git merge-base --is-ancestor "refs/dst/$b" "refs/src/$b"; then
  git push --quiet dst "refs/src/$b:refs/heads/$b"
else
  echo "[$b] 无法快进：CNB 侧存在独有提交（dst=$D src=$S），已跳过，需人工处理"
  FAILED=1
fi
```

判否时**只打一行日志**。任务是个 crontab（不是 PR check），红了没人盯——
从外部看「停摆」和「正常」一模一样。这正是 #118 讲的「静默降级」在流程层的同型事故。

### 2.4 三个探测陷阱（本轮全部踩过，写下来免得下一个人再踩）

#### 陷阱 1：`git push --dry-run` 对 `cnb.cool` 是假信号

对 `cnb.cool` **任何 refspec 都返回 exit 0** —— 包括不存在的 ref（`nonexistent-ref-xyz`）
和瞎编的 SHA（40 个 `9`）；同样的命令对 GitHub 会正常报错。
因此任何「先 `--dry-run` 预检再真推」的 CNB 侧脚本都是空转。要预检就比对 SHA。

#### 陷阱 2：共用一个对象库时，`git cat-file -e` 分不清提交来自哪个远端

第一轮我在同一个库里 fetch 了 GitHub 和 CNB，然后测「CNB 的 6 个提交在不在 GitHub」——
结果六个全部「存在」。**那是假阳性**：对象是从 CNB 拉进来的，留在同一个 store 里。

正确做法：**在只 fetch 过目标远端的干净库里测**。改法之后六个全部 MISSING，结论反转。

#### 陷阱 3：浅克隆（`--depth=N`）会给出**虚假的分叉读数**

同一组两端 SHA，不同 fetch 深度下 `rev-list --count` 的结果：

| 命令 | `--depth=5` | `--depth=2000` | 全量 fetch |
|---|---|---|---|
| `CNB main 独有` | 8 | 408 | **408** |
| `GH main 独有` | 0 | 0 | **0** |
| `gh/main..gh/dev` | — | 414 | **414** |

更要紧的是**布尔判定也会翻**：`main` 的 `merge-base` 在全量 fetch 下是 `cc1d4220`，
浅克隆下直接报 「Not a valid object name」或给出错误祖先关系。
本轮我用 `--depth=5` 先得到「`gh/main` 不是 `gh/dev` 祖先」，加深后变成「是」——**判反了**。

**结论：凡是要判断「两个远端分叉与否」，一律全量 fetch，不要用浅克隆。**
浅克隆只适合「看一眼某个分支的 tip 长什么样」。

## 3. 目标态：单源 + 两条单向管道（不是双向同步）

用户的原始表述是「双向镜像」：CNB 的 `dev` 与 GitHub 的 `dev` 同步，两个方向都要能感知。
**这个目标是对的，但「双向同步」是错的实现方式**——两个可写端点互相同步，
在冲突时没有仲裁者，最终必然互相覆盖（本仓 `feedlog_bridge.py` 的注释已经吃过一次这个亏）。

正确的形态是**单源（single source of truth）+ 两条单向管道**：

```text
                    ┌─────────────── 唯一写入端点 ───────────────┐
                    │      GitHub imoyao/fundmate               │
                    │   PR / CI / 分支保护 / 合并 全在这里        │
                    └───────────────────────────────────────────┘
                          ▲                          │
        管道 B（回写）     │                          │  管道 A（代码镜像）
        内容：CNB 侧讨论     │                          │  内容：代码分支
        方向：CNB → GitHub │                          │  方向：GitHub → CNB
        实现：GitHub 定时拉  │                          │  实现：CNB cron fast-forward
                          │                          ▼
                    ┌───────────────────────────────────────────┐
                    │      CNB duoduobei/fundmate               │
                    │   只读镜像：可读、可跑流水线、不可合并 PR    │
                    └───────────────────────────────────────────┘
```

**「双向」体现在管道方向，不体现在写入权限。** 两条管道各自单向，谁也不覆盖谁：

| | 管道 A（代码镜像） | 管道 B（讨论回写） |
|---|---|---|
| 方向 | GitHub `dev`/`main` → CNB 同名分支 | CNB issue 评论 → GitHub issue 评论 |
| 触发 | CNB `sync/mirror` 上的 cron（每小时） | GitHub Actions cron（每日 18:30 UTC） |
| 凭据落点 | CNB 侧（`CNB_TOKEN`，只推 CNB） | **GitHub 侧**（`GITHUB_TOKEN`，只写 GitHub） |
| 幂等 | SHA 比对（`is-ancestor`） | 评论末尾隐藏标记 `<!-- cnb-backfill: ... -->` |
| 冲突时 | 拒绝快进 + **必须喊出来**（见 §4） | 只增不覆盖，永不编辑 |

### 3.1 为什么管道 B 必须由 GitHub 拉，而不是 CNB 推

**CNB 构建环境里没有任何 GitHub 凭证**（`env` 全是 `CNB_*`；对 `api.github.com`
匿名 POST 返回 401）。而反方向的凭据是现成的：GitHub Actions 的 `GITHUB_TOKEN`
自动注入且带 `issues: write`。

所以「CNB → GitHub」在物理上就实现成 **GitHub 定时拉 CNB**。
这不是取舍，是唯一可行解——**不需要在 CNB 存 GitHub PAT**（存了也是长期高权限密钥，
比不存差得多）。

## 4. 让断链「大声失败」——本卡最该落地的一件事

现状：断链只打一行日志，外部无异样。这是 §2.3 描述的、也是 #118 全卡的主题。
**修法分三层，按成本从低到高：**

### 层 1：镜像任务失败必须在 CNB 侧可见（必做）

CNB 的 crontab 失败目前只进构建日志。要让它冒泡到人能看见的地方，两条路：

- **CNB issue 提醒**：任务失败时用 `CNB_TOKEN` 在 CNB 建一张卡（或评论到既有卡）。
  代价低，且 CNB 侧本来就有 issue 视图；
- **`exit 1` 已被 git 传上去**：确认 `FAILED=1` 真的让 job 变红（当前脚本 `exit $FAILED`，
  已正确）。

### 层 2：加一条「独立性断言」（必做，很便宜）

在 `sync/mirror` 的脚本里，每次运行都断言**单向性**而不是只看 SHA：

```bash
# 快进前先断言：CNB 侧不能有 GitHub 没有的提交
git fetch --quiet src "+refs/heads/$b:refs/src/$b"
if ! git merge-base --is-ancestor "refs/dst/$b" "refs/src/$b"; then
  echo "::error::[$b] CNB 侧存在独有提交，镜像已断链"
  # 打印双方 SHA + 独有提交清单，便于直接照做救援
  git log --oneline "refs/src/$b..refs/dst/$b" | head -20
  exit 1
fi
```

关键增量是**失败时打印独有提交清单**——现在只打两串 SHA，接手的人还得自己查。

### 层 3：反向守卫——拦在「制造分叉」的那一刻（建议做）

断链的成因是**在 CNB 侧合了 PR**。与其事后发现，不如当场拦：

- **CNB 侧**：`.cnb.yml` 加一条 `pull_request` 触发器，命中 CNB PR 时直接 fail
  并评论「本仓 CNB 侧只读，请到 GitHub 开 PR」；
- **GitHub 侧**：`AGENTS.md` 已有「双端协作（CNB ↔ GitHub，强制）」节（在
  `rescue/2-cnb-commits` 分支上），把它合入 `dev` 即生效。

> ⚠️ 层 3 的 CNB 侧守卫是**在 CNB 仓上拦截 CNB 行为**，属于「配置写在会被执行的地方」——
> 正好避开了 #118 里 `sync/mirror` 那个「配置写在不会执行的路径上」的坑。

## 5. 我建议的落点：分三步，每步独立可验证

### 第 0 步：先止血（当前唯一阻塞项）

四个分支两两分叉，管道 A 现在是**停摆**状态，谈什么都轮不到。
先做救援：

1. 把 CNB 侧 `dev` 的 6 个提交在 GitHub 侧重放成 `rescue/` 分支 → PR 到 GitHub `dev`；
2. `main` 的 8 个独有提交同理（其中包含 issue 镜像的整套资产）；
3. 合完之后两侧回到同一条线，管道 A 恢复快进。

> 这一步**已经有人做过一半**：`rescue/2-cnb-commits` 分支（CNB 侧，14 个提交相对 `main`）
> 已含 `cherry-pick` 结果 + `AGENTS.md` 双端协作节 + 断链事故留证文档。
> 但它**本身也只在 CNB 侧**——正是「救援物没回家」的又一个同型样本。

### 第 1 步：把「CNB 造的资产」正规化进 GitHub

`.cnb.yml`、两个 bridge 脚本、单测、文档 —— 全部走 GitHub PR 入库。
入库之后 **CNB 侧才真正可以是只读的**：因为它的配置在 GitHub 有版本、有评审、有回归网。

### 第 2 步：落地 §4 的三层守卫

层 1 + 层 2 是必做（成本低、直接对主题）；层 3 建议做。

## 6. 我不建议做的（以及为什么）

| 不建议 | 为什么 |
|---|---|
| **真正的双向同步**（两侧都可写、互相 push） | 无仲裁者，冲突时必然互覆盖；本仓已有 feedlog bridge 的前车之鉴 |
| **把 CNB 当第二写入端点** | 会立刻制造分叉 ⇒ 管道 A 停摆。数学上不可共存（fast-forward 要求单向） |
| **在 CNB 存 GitHub PAT 让 CNB 推 GitHub** | 长期高权限密钥 + 现有 `GITHUB_TOKEN` 已够用；拉模式零新增密钥 |
| **给镜像任务加 `--force`** | 会静默抹掉 CNB 侧改动。断链要「大声失败」，不是「自动抹平」 |
| **把 `dev`/`main` 的 `.cnb.yml` 也加上镜像配置** | `dev`/`main` 是同步**目标**，配置写那儿会被下一次同步覆盖或产生独有提交 |

## 7. 一句话总结

**目标态不是「两个仓双向同步」，而是「GitHub 单源 + 两条单向管道 + 断链必须大声失败」。**
CNB 造的东西要回流——但回流的方式是**把 CNB 当作者的改动走 GitHub PR 回家**，
而不是让两个仓互相同步。
