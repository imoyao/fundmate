# lint-md 排除规则说明

`docs:lint-md`（即 `lint-md docs`）跑的是中文 markdown 规范守卫。本文件记录被刻意排除的路径与理由，避免后来人重复排查。

## 当前排除项

| 路径 | 理由 |
|---|---|
| `**/node_modules/**`、`**/.git/**` | 非文档内容，无需检查 |
| `**/working-notes/legacy/worktile-archive-2021-2026-08-09.md` | 归档的 Worktile 原始卡片全文，含**从外部文章整段粘贴**的正文与表格，非本仓写作内容；`no-long-code` 报 14 处，均为原文形态，不改写（改写即失真） |

## 历史排除项：`docs/working-notes/legacy/**`（2026-10-11 收窄）

原先整目录排除，因 27 个前端重构文件在**仓库历史里即为乱码**：内容按错误编码落盘，解码失败处的字节在写入时已丢失，无法逆向恢复（`gbk` / `gb18030` / `latin-1` / `cp1252` / `big5` 均试过，全部不可逆）。乱码吃掉了换行符，把多行拼成 100~383 字符的长行，于是 `no-long-code` 在该目录报出 **211 处**——这是乱码的**次生现象**，改行宽既修不好也不该修。

**处置**：Issue #2042 核对确认这批内容不可读、不可逆、且已被后续实现取代，已整批删除；目录内仅保留完全可读的 `worktile-archive-2021`。故排除项由整目录收窄为**该单个文件**，其余目录重新纳入检查。详见 `docs/working-notes/legacy/README.md`。

## 踩过的坑：glob 必须以 `**/` 开头

`.lintmdrc` 的 `excludeFiles` 由 `lint-md-cli` 直接传给 node-glob 的 `ignore`，匹配的是**展开后的绝对路径**。写成相对形式（`docs/working-notes/legacy/**`）实测**完全不生效**——错误数一条不少。正确写法是 `**/working-notes/legacy/**`。

来源：`node_modules/lint-md-cli/bin/helper/file.js`（`glob.sync(..., { ignore: excludeFiles })`，入参是 `path.resolve()` 后的绝对路径）。

## 通用坑：lint-md fixer 非幂等

`lint-md@0.2.0` 的 `--fix` 对**缩进代码块**有非幂等 bug：它把缩进代码块首行当成围栏行，每跑一轮就往行尾追加一个 `plain`，与内容无关，永不收敛。故 `pnpm run docs:lint-md` 默认**只读报告**；确需自动修复时显式跑 `docs:lint-md:fix`，且必须先看 `git diff` 再提交。
