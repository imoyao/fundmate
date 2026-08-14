# 本地 Patch 记录（vendored: Sensitive-Word-Filter-CN）

本目录是 GitHub 仓库 [PerryLink/Sensitive-Word-Filter-CN](https://github.com/PerryLink/Sensitive-Word-Filter-CN)
的 vendored 内嵌副本（Apache-2.0）。该库**未发布到 PyPI**（官方源与阿里云镜像均
`No matching distribution`），故直接内嵌源码并跟踪上游。

## 上游信息

- 上游 URL: https://github.com/PerryLink/Sensitive-Word-Filter-CN
- vendored commit: `62f826e`（2026-08-14 clone，--depth 1）
- 跟踪方式: 在 `vendor/sensitive_word_filter_cn_src/` 下保留了 `.git`，可
  `git -C vendor/sensitive_word_filter_cn_src pull` 拉取上游更新；更新后用
  `git -C vendor/sensitive_word_filter_cn_src diff 62f826e..HEAD` 核对是否影响本地 patch。

## 本地 Patch

1. **`src/sensitive_word_filter_cn/utils.py` — 移除拼音首字母缩写变体**
   - 原版把每个中文词的两字首字母缩写也加入 DFA（如「白痴」→ `bc`、「笨蛋」→ `bd`、
     「傻瓜」→ `sg`）。这类两字母组合对任意含该连续字母的英文都会误命中，用户名校验
     场景误杀率极高（`abcd`/`basic`/`candy`/`David`/`Cindy` 等统统被拦）。
   - 已移除首字母变体，仅保留全拼与全拼带空格两种变体。仍能拦「大shagua」式拼音绕过，
     不再误伤正常英文用户名。
   - 若上游 `utils.py` 的 `to_pinyin_variants` 更新，需重新 apply 此修改。

## 依赖说明

运行时依赖（已通过 `pdm add` 安装到项目 venv）：

- `pypinyin`（拼音转换，项目原本已装）
- `opencc-python-reimplemented`（繁简体转换，import 名 `opencc`；本库所需，已新增）

CLI 入口（`cli.py`/`__main__.py`）依赖 `click`/`rich`，本项目不使用，未安装。
