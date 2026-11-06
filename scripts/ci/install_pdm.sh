#!/usr/bin/env bash
# 安装 PDM（CI 与定时调度共用，本仓唯一入口）。
#
# ── 为什么是脚本，而不是写在 workflow 里（#2928 / #2803）──
# `schedule` 与 `pull_request_target` 事件**只读取默认分支（main）上的 workflow 定义**，
# 而本仓功能开发在 dev。把「装哪个版本的工具链」写进 workflow，等于把这类修复**锁死在
# main 上**：dev 改了不生效、CI 也不会因此变红——只有定时任务在夜里悄悄失败。
# 2026-11-05 的故障就是这么来的：dev 早已钉住 hishel<2，main 上的旧定义仍是裸
# `pip install pdm`，夜间调度连红在「安装依赖」，也没有 last_run_summary.json。
#
# 本文件由 job 里 checkout 的那个 ref（通常是 dev）决定 ⇒ **改这里，下一次运行即生效**，
# 不必等 main 同步。
#
# ── 版本口径 ──
# hishel 2.0.0 删掉了 SyncSqliteStorage，而 pdm 2.29.6 只声明 hishel>=1.4.0、没有上界
# ⇒ `pip install pdm` 装到 2.0.0 后，`pdm install` 在 "Resolving packages from lockfile"
# 阶段抛 `AttributeError: module 'hishel' has no attribute 'SyncSqliteStorage'`。
# 钉 <2 是短期取舍；PDM 发布兼容版本后解钉（同时删掉上面这段理由）。
set -euo pipefail

PYTHON="${PYTHON:-python}"

"$PYTHON" -m pip install --disable-pip-version-check pdm "hishel<2"

# 把实际装到的版本打出来：这类故障的第一现场就是「装到了哪个版本」，
# 有这一行才能在日志里一眼定性，不必再去翻 pip 的几十行 Collecting 输出。
echo "pdm: $(pdm --version 2>&1 | head -1)"
echo "hishel: $("$PYTHON" -m pip show hishel 2>/dev/null | sed -n 's/^Version: //p' | head -1)"
