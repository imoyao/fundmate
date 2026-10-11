# legacy/ 子目录说明

本目录归档**不适合建 issue、但有长期参考价值**的原始材料。

## 内容清单

| 文件 | 说明 |
|---|---|
| `worktile-archive-2021-2026-08-09.md` | Worktile 2021 年看板归档（16 张卡片原始描述全文）：晨星爬虫方案、开源金融数据对比、竞品观察，及雪球 IRR/XIRR/Modified Dietz 论证全文。迁移处置见 `../worktile-migration-map-2026-08-09.md` |

## 已删除：前端重构系列（2026-10-11，Issue #108）

原先此处有 27 个文件（`frontend-refactor-*.md`、`delete-orphans.sh`），记录 2026-08-09 的前端大规模重构（batches / codebooks / reference / guides）。

**删除原因：内容在入库前即已损坏，不可读、不可逆，且工作已被后续实现取代。**

- **不可逆**：这批文件在首次入库提交 `63f01202`（2026-08-10）的 blob 中**已是乱码**——损坏发生在入库之前（源头 `fundmate-optimization/` 目录已不存在）。乱码吃掉换行符，把多行拼成 100~383 字符长行。试过 `gbk` / `gb18030` / `latin-1` / `cp1252` / `big5` 全部不可逆（解码失败处的字节在写入时已丢失）。**仓库历史里没有完好原文可回取**（父提交同样是乱码）。
- **已被取代**：codebook 快照描述的重构（`composables/import/*`、`useEchartsLifecycle` 等）后来已按另一路径正式落地——见 `frontend/src/views/asset/investment/import/`（composables + components + 单测）与 `frontend/src/composables/echarts/`。快照代码不再是最新实现，无追认价值。
- **无未迁移结论**：删前逐份核对，正文叙述部分 100% 为乱码（零个正常中文常用字），无法提取任何可信结论；`tech-debt.md` 中追到这批笔记的卡片其来源结论在正式文档中均有独立记录。

保留 `worktile-archive-2021` 是因为它**完全可读**（未乱码），且被迁移备忘明确引用。

## 连带清理

- `.lintmdrc` 的 `excludeFiles` 移除 `**/working-notes/legacy/**`——目录已无乱码文件，无需再排除，重新纳入 markdown lint 检查。
- `docs/dev/lint-md-exclusions.md` 同步移除对应条目。
