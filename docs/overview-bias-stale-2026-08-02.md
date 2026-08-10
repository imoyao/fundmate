# 乖离度可观测性（#13）修复概览 · 2026-08-02

## 一句话结论

原以为「乖离率 stale 落库」只是前端没显示，实测发现**更严重的根因：乖离率此前根本没落库**——`save_multi_items` 的入参结构与实际产出不匹配，整张表一直为空。本次把落库链路真正打通，并补上「数据滞后」可视提示。

## 根因（实证）

- `BiasJob._convert_to_records` / `TemperatureJob` 产出的是**扁平记录**（每条即一行：`item_type/item_code/item_name/data/stale`）。
- `service.save_multi_items` 却按**嵌套结构**处理（`batch.get('items', [])`），拿不到 `items` 就 `continue` —— 落库计数恒为 0。
- 同时原 `stale=False` 硬写，即便结构对齐也会丢 stale。

## 改动文件

| 文件 | 改动 |
|---|---|
| `backend/app/services/thermometer/service.py` | ① `save_multi_items` 重写：兼容扁平+嵌套入参、按 source 仅删一次旧数据再批量插入、`stale=sub.get('stale', False)`；② `get_multi_items` / `get_latest_multi_items` 去掉 `stale.is_(False)` 过滤，返回带 `stale` 标记（前者另加顶层 `stale`） |
| `frontend/src/api/temperature.ts` | `MultiItemsResponse` 的 items 与顶层补 `stale?: boolean` |
| `frontend/src/views/temperature/index.vue` | 乖离度表上方加「数据滞后提示」el-alert（东财不可用时）；行业列每行加「滞后」标签；`fetchBias` 计算 `biasStale` |

## 验证

- 后端：`tests/services/bias/` 共 **12 passed**（新增 `test_multi_stale_chain.py` 4 条：落库/读取/stale 透传/get_latest_multi_items/嵌套兼容）。
- 前端：`pnpm run typecheck` 中 `temperature.ts` 与 `index.vue` **0 错误**（其余报错为既有无关问题）。
- UI 截图自检：**未在沙箱执行**（无可用浏览器），请本地 `dev.cmd` 目视确认滞后横幅与每行「滞后」标签。

## 待办（非代码 / 待用户）

1. 退出 DevSidecar 后本机跑 `pdm run python scripts/diag_em.py`，坐实东财连接根因（此前 curl 实测两 host 均 schannel 失败）。
2. 任务 5 fallback（腾讯/新浪备用源）待退出代理后实网验证 symbol 格式与连通性再实现。
3. `git status` 确认改动后提交（注意 pre-commit 的 `ACC_PRODUCT_CONFIG_V3` 超限坑：`unset` 后再 `git commit`）。
