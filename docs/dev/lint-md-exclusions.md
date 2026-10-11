# lint-md 排除规则说明

`docs:lint-md`（即 `lint-md docs`）跑的是中文 markdown 规范守卫。本文件记录被刻意排除的路径与理由，避免后来人重复排查。

## `docs/working-notes/legacy/**`（26 个文件）

该目录的文件在**仓库历史里已经是乱码**：GBK 内容被按 UTF-8 落盘，解码失败处的字节已丢失，无法逆向恢复（`text.encode('gbk').decode('utf-8')` 会抛 `UnicodeEncodeError`，试过 `gbk` / `gb18030` / `latin-1` / `cp1252` / `big5` 均不可逆）。

**连带后果**：乱码吃掉了换行符，多行被拼成 100~383 字符的长行，于是 `no-long-code` 在该目录报出 **211 处**——这是乱码的**次生现象**，不是格式问题，改行宽既修不好也不该修。故整目录排除。

恢复条件：拿到可信原文后，删掉 `.lintmdrc` 里的 `**/working-notes/legacy/**` 即可重新纳入检查。

## 踩过的坑：glob 必须以 `**/` 开头

`.lintmdrc` 的 `excludeFiles` 由 `lint-md-cli` 直接传给 node-glob 的 `ignore`，匹配的是**展开后的绝对路径**。写成相对形式（`docs/working-notes/legacy/**`）实测**完全不生效**——错误数一条不少。正确写法是 `**/working-notes/legacy/**`。

来源：`node_modules/lint-md-cli/bin/helper/file.js`（`glob.sync(..., { ignore: excludeFiles })`，入参是 `path.resolve()` 后的绝对路径）。
