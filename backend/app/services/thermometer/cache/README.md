# 温度计运行时缓存目录

本目录仅存放**运行时缓存**（可安全删除，系统会自动重建）：

- `baostock_pb/`：baostock 路径的本地 PB 缓存（parquet），仅供离线兜底。

## ⚠️ 历史基线数据已迁出

全A中位 PB 历史 `all_pb.csv`（行业拥挤度分母兜底）**已迁移至 `../data/all_pb.csv`**。
它是**基线数据而非运行时缓存，禁止删除**（详见 `../data/README.md` 与 `scripts/guard_all_pb.py` 守卫）。
请勿把 `all_pb.csv` 放回本目录，也不要对 `data/all_pb.csv` 做 `.gitignore` 或清理。
