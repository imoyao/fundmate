# dependabot 的 pnpm 锁：为什么会坏，以及怎么修

> 关联：#2434（自动重生成通道）、#2394 / #2395 / #2397（2026-10-20 一天内三连踩）。
> 判据：`scripts/guard_dependabot_lockfile_regen.py`（阻断）；
> 回归网：`scripts/tests/test_dependabot_lockfile_regen.py`（6 个变异探针）。

## 1. 现象

dependabot 升级 npm 依赖的 PR 上，**质量门禁必红**：

```text
ERR_PNPM_LOCKFILE_MISSING_DEPENDENCY  Cannot install with "frozen-lockfile"
because pnpm-lock.yaml is missing a dependency
```

而 PR 的 diff 里 `package.json` 只改了一个版本号，`pnpm-lock.yaml` 是 dependabot 自己重写的。

## 2. 根因：锁不是 pnpm 写的

dependabot **不运行 pnpm**，它用自家的解析器**文本级重写** `pnpm-lock.yaml`。
写出来的锁会丢掉 **peer-suffixed 条目**——形如：

```yaml
  '@vitejs/plugin-vue-jsx@5.1.6(vite@7.0.0)(vue@3.5.44)':
```

这类条目是 pnpm 对「同一包在不同 peer 组合下的多个实例」的表示方式。
少了它，`--frozen-lockfile` 的完整性校验直接失败。

**这不是本仓配置错**，上游同族问题：

- dependabot-core #11135 —— pnpm lockfile v9 的 peer-suffix 处理
- dependabot-core #12244 —— 同类条目丢失
- dependabot-core #10758 —— monorepo 下更明显

所以处置方向不是「把 dependabot 配好」（做不到），而是**用一个 pnpm 认可的重生成步骤兜住**。

## 3. 自动通道

`.github/workflows/dependabot-lockfile-regen.yml`，触发 `pull_request_target`
（`opened` / `synchronize` / `reopened`），**只处理 `dependabot[bot]` 作者 + base=dev**。

它做四件事：

1. 检出 PR 分支，跑 **dev 上那一版** `scripts/regen_pnpm_lockfile.mjs`
   （`git show origin/dev:… > /tmp/…`，不在 PR 分支上执行未评审内容）；
2. 脚本：以 `origin/dev` 的锁为基线 → 按 PR 的 `package.json` 重生成 → 把改动过的依赖
   **钉回 manifest 声明的版本** → 解包 `--frozen-lockfile --ignore-scripts` 自证；
3. 有差异则作为一个追加提交推回 dependabot 分支；
4. 推回后的 runs 会进 approval-required（GITHUB_TOKEN 递归防护，见 #2289），
   复用 `scripts/pr_autorebase_approve.py` 批准；批准失败只打 `::warning::`
   —— 锁已经修好，把这一步判红是失实的。

日志里的自证行（每次运行必打）：

```text
LOCKFILE_REGEN dir=frontend base=origin/dev changed=1 pinned=1/1 frozen=pass applied=yes
```

失败态（**绝不推坏锁**）：

| 退出码 | 含义 | 处置 |
|---|---|---|
| 0 | 重生成成功（有没有差异都算成功） | — |
| 1 | `--frozen-lockfile` 自证失败 | 脚本已回滚锁文件；workflow 报 `::error::` 并退出，不推送 |
| 2 | 拿不到输入（base 锁取不到 / manifest 缺失 / pnpm 报错） | **结论不可信**，不得当成功 |

### 为什么「以 dev 锁为基线」而不是在坏锁上原地修

实测（2026-10-20）：对坏锁直接 `pnpm install --lockfile-only`，缺的 peer 条目不会被补回来
——重生成把「已缺的部分」当成「不需要」。基线取 `dev`（一份 pnpm 认可的完整解），
等价于「从已知完整的解出发，只应用本次 bump 的差异」。

### 为什么要 pin（`pnpm update <pkg>@<ver>`）

manifest 里 dependabot 写的是 `^1.20.0`；`--lockfile-only` 会解析到**当时最新**
（可能是 1.20.5）。那等于 PR 声称升到 1.20.0、实际装 1.20.5——评审看到与实际装的不一致。
故脚本从 manifest 的声明里取出精确版本再钉一次，**但不改 manifest**（manifest 归 PR 所有）。

## 4. 人工兜底（自动通道没生效时）

> 2026-10-20 实测可用，约 15 分钟。以下命令在**功能分支的 worktree** 里跑。

```bash
# 0) 确认是「锁坏了」而不是「依赖真的冲突」
pnpm install --frozen-lockfile --ignore-scripts
#   ERR_PNPM_LOCKFILE_MISSING_DEPENDENCY  -> 走下面
#   ERR_PNPM_PEER_DEP_ISSUES / 版本冲突    -> 不是本文的场景，去看依赖本身

# 1) 以 dev 的锁为基线，按本 PR 的 manifest 重生成
node scripts/regen_pnpm_lockfile.mjs --dir frontend --base-ref origin/dev --apply
node scripts/regen_pnpm_lockfile.mjs --dir .        --base-ref origin/dev --apply   # 根目录有改动时才跑

# 2) 自证（脚本内部已跑过；这一步是给人看的）
pnpm --dir frontend install --frozen-lockfile --ignore-scripts

# 3) 只提交锁文件
git add frontend/pnpm-lock.yaml
git commit -F <utf8 提交信息文件>
git push
```

只改 `pnpm-lock.yaml`，**不要**顺手改 `package.json`——那是 dependabot 的意图声明。

## 5. 验证记录（2026-10-20）

| 步骤 | 结果 |
|---|---|
| 模拟 dependabot（只改 manifest，锁不动）`pnpm install --frozen-lockfile` | 复现红：`ERR_PNPM_OUTDATED_LOCKFILE` |
| `node scripts/regen_pnpm_lockfile.mjs --dir frontend --base-ref origin/dev --apply` | `changed=1 pinned=1/1 frozen=pass`，退出 0 |
| 重生成后锁里 axios 的版本 | `1.20.0`（等于 manifest 声明，未被解析到更新的补丁版） |
| manifest 是否被脚本改写 | 否（字节级比对一致） |
| dev 基线下重生成是否幂等 | 是（lock 字节级一致，sha256 相同） |
| 失败态：`--dir nope` / `--base-ref origin/does-not-exist` | 均退出 2，不冒充成功 |

**尚未验证**：workflow 在真实 dependabot PR 上端到端跑通（需要下一轮 dependabot PR，
2026-10-26 周一 08:00）。在那之前，本文件描述的是「机制已就绪 + 逻辑已本地验证」，
不是「已经在生产跑绿」。**不要把 PR 合并当成端到端验收。**

## 6. 已知边界

- **dependabot 后续更新会覆盖**：它每次同步可能 force-push 自己的分支，
  把本 workflow 追加的提交冲掉。这不影响结论——新一轮 `synchronize` 会再重生成一次。
- **只覆盖 pnpm 生态**：pip（`backend/`）不用锁文件完整性校验，不在本通道范围。
- **不处理 major 升级失败**：本通道只修「锁结构坏了」，依赖真的冲突（peer 不兼容）
  仍需人工判断。
- **推送权限依赖仓库设置**：`pull_request_target` + `contents: write` 下可写同仓分支；
  若仓库改为 fork-only 协作，此通道需重新评估。
