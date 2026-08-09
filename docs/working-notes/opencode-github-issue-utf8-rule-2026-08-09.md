# OpenCode 通过 GitHub API 创建 issue 的编码规范（必读）

> 适用对象：任何以 `imoyao` 账号调用 GitHub API / `gh`` 创建 issue、discussion、PR 的自动化通道（含 OpenCode、远程 agent）。
> 背景：2026-08-09 发现 #859–#862 四个 issue 标题为中文乱码（`?????(?? Discussion #152 ????)`，中文全部变成 `?`），系创建时未正确处理 UTF-8 编码所致。已改写成干净中文 issue 并补交叉引用。

## 问题根因

- 标题/正文里的**中文在提交到 GitHub 之前就已经损坏**（GitHub 服务端不会把中文变 `?`）。
- `?` 是单字节编码（Latin-1 / Windows-1252 / `C` locale）无法表示 UTF-8 中文字节时用的替换符，说明创建环境的字符编码不是 UTF-8，或字符串在 Python/Shell 层被按 `latin-1` 错误编码/解码。
- 这 4 个 issue 都是「把 Discussion 转成 issue」的中文内容，批量创建时统一翻车；纯英文 issue 未暴露。

## 强制规则（下次提 issue 必须遵守）

1. **运行环境必须是 UTF-8 locale**：在调 `gh` / 跑 Python 脚本创建 issue 前，确保
   - shell：`export LANG=C.UTF-8; export LC_ALL=C.UTF-8`（Linux/macOS）；PowerShell 默认 UTF-8，勿用 `chcp` 切到非 UTF-8 代码页。
   - Python：设置 `PYTHONUTF8=1` 或脚本顶部 `# -*- coding: utf-8 -*-` + 显式 `.encode('utf-8')`，禁止用 `latin-1`/`ascii` 编解码中文。
2. **用文件传中文，不靠内联字面量**：优先 `gh issue create --title-file <file> --body-file <file>`，文件以 UTF-8 无 BOM 保存；避免 `gh issue create --title "$(中文变量)"` 在非 UTF-8 终端里被截断。
3. **创建后校验**：`gh issue view <n> --json title` 回读标题，确认中文正常（无 `?`、无 `Ã©` 类 mojibake）后再继续，否则立即删掉重建。
4. **禁止提交疑似乱码 issue**：标题或正文出现连续 `?` 或 `Ã`/`Â` 等 mojibake 特征时，视为创建失败，不许保留。

## 关联

- 受影响 issue：#859（原 Discussion #152）、#860（#603）、#861（#639）、#862（#127），均已改写为干净中文。
- 复盘：本次整理由本地 agent 接手，发现上述 4 个 issue 已被 OpenCode 以乱码形式创建，重写为中文后保留为 canonical issue。
