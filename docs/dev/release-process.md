---
title: 发版流程（Release → 更新日志）
status: v1（2026-10-20，`#1996` 收口）
owner: 协作
---

# 发版流程（Release → 更新日志）

> 一句话：**先让代码进 `main`（唯一一次 `dev → main` 的 PR），再对 `main` 的提交打 `v` tag
> 并建 Release。** Release 的 `published` 事件会自动写入 FeedLog 更新日志。

## 1. 分支与门禁

| 动作 | head → base | 说明 |
|---|---|---|
| 功能 / 文档 PR | `feat/*`、`fix/*`、`docs/*` → **`dev`** | 默认情况，全部走这条 |
| **发版 PR** | **`dev` → `main`** | 只做发版这一件事，不夹带其它改动 |

- `main` 受保护，required status check 是 `ci.yml` 的 `质量门禁汇总`（job id `gate`）。
- 发版 PR 合并后，`main` 只前进一个 merge commit；`dev` 继续开发，不因发版停摆。
- 不要把功能分支的 base 填成 `main`——「需要尽快生效」属于「该发版了」，
  正确做法是另开一张发版 PR（详见仓库根 `AGENTS.md` 的 PR 两张表）。

## 2. 版本号口径

- 现状：`frontend/package.json` = `0.1.0`；唯一 Release = `v0.1.0`（2026-10-09）。
- 规则：`vMAJOR.MINOR.PATCH`，预发布加后缀（`v0.1.1-beta.1`）。
- 0.x 阶段（M0 上线前）按「最小可用提升」升位：修 bug 升 PATCH，成组功能升 MINOR；
  1.0.0 留给正式发布。
- **不要用裸 `0.1.0`**：既有 tag 全部带 `v` 前缀，混用会让文档链接与 `gh release` 对不上；
  `scripts/release.py` 会直接拒绝。

## 3. Release notes 写什么

更新日志的读者是**用户**，不是开发者。写法：

- 写「用户能感知到什么」，不写「改了哪个文件 / 哪个 PR」；
- 每条一句话 + 一个使用场景，避免堆砌术语；
- 需要引用 issue 时写**完整 URL**（反馈站与站外读者点不开裸编号）；
- 建议分三类小标题：**新增 / 改进 / 修复**。

模板（保存为 `release-notes-vX.Y.Z.md`，UTF-8 无 BOM）：

```markdown
## 新增
- 产品详情页新增「指数关联 ETF 对比」，可直接看到规模与费率。

## 改进
- 对账 pending 差异在站外也会提醒，不再需要主动打开页面查看。

## 修复
- 修复账户名变更后按账户分组报 500 的问题。
```

## 4. 执行

```bash
# 1) 预演（默认 dry-run，只打印命令）
python scripts/release.py --tag v0.1.1 --notes-file release-notes-v0.1.1.md

# 2) 确认无误后真正执行
python scripts/release.py --tag v0.1.1 --notes-file release-notes-v0.1.1.md --apply
```

脚本固定做三件事，任一步失败即停：

1. `git tag -a <tag> <origin/main>` —— **不切换分支**（主仓库常驻 `dev`，切分支会打断 dev server）；
2. `git push origin refs/tags/<tag>`；
3. `gh release create <tag> --verify-tag --title ... --notes-file ...`。

`--verify-tag` 是刻意加的：它要求远端已有该 tag，避免 GitHub 从默认分支自行挑一个
你没看过的提交来建 Release。`--ref` 可改指向（例如热修时指向某个具体 commit），默认 `origin/main`。

## 5. 验证

```bash
gh run list --workflow=bridge-feedback.yml --event=release --limit 1
# 期望：conclusion = success
```

再打开 <https://feedback.duoduobei.com/changelog>，确认：

- 新条目**可见**（= `status='published'`，不是 draft）；
- 标题与 notes 是这一版的内容。

## 6. 已知坑

- **只有 `published` 触发**：`gh release create --draft` 不发事件，必须再 publish 一次。
- **重复触发**：同一 tag 再次触发现在会 UPDATE 同一条目（slug 由 tag 稳定，`#1996` 修复）。
  修复前每次触发都会插一条新的——看到同版本多条，先怀疑是不是旧版本脚本跑的。
- **裸编号点不开**：Release notes 里的 `#123` 在反馈站是纯文本；引用请写完整 URL。
- **closing keyword 分两套**：发版 PR（base=`main`）由 GitHub 原生关闭；
  功能 PR（base=`dev`）由 `close-linked-issues.yml` 兜底。别把两套当成同一套。
- **CNB 的 `main` 与 GitHub 的 `main` 无关**：发版只在 GitHub 侧做；
  镜像链路的取舍见 `docs/dev/github-cnb-mirror.md`。

## 7. 历史记录

| tag | 日期 | 说明 |
|---|---|---|
| `v0.1.0` | 2026-10-09 | 首个 Release，打通 `release → changelog` 通道。tag 指向 `d8921d9e`，它同时是 `dev` 与 `main` 的祖先。当时未走发版 PR；**保留现状、不重打 tag**（重打会改写已发布的 Release）。 |
