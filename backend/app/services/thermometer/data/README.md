# 温度计历史基线数据目录

## `all_pb.csv`（禁止删除）

全A 个股历史 PB（市净率）中位序列，行业拥挤度计算的分母兜底数据。

- 约 2005 年至今每交易日一行（`date, middlePB`），~5000 行。
- 由 `scripts/prefetch_all_pb.py` 落盘（来源 legulegu `ak.stock_a_all_pb()`），供沙箱/离线环境命中本地缓存恢复分母。
- **这是基线数据，不是运行时缓存**：
  - 禁止删除（含手动删除、`.gitignore` 忽略、清理脚本误删）；
  - 必须入库追踪（误删/清空会导致行业拥挤度整组标灰）；
  - 已从 `../cache/` 迁出，目录名 `data/` 即表明其为基线而非可清理缓存。
- 刷新：`pdm run python scripts/prefetch_all_pb.py`，自动写回本文件后正常提交即可。
- 守卫：`scripts/guard_all_pb.py`（已接入 pre-commit，跨平台 Python 实现）会在行数骤降（< 1000 行，疑似被清空）时拒绝提交，防止误清空入库。
