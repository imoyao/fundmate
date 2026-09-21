# 温度计缓存目录（**已不再是运行时缓存落点**，#1539）

> 本目录现仅存本文件（一个说明）。**不要再往这里写运行时缓存。**

## 现状（2026-09-16 起，#1539）

原先三处缓存目录都硬编码在本目录下（**源码树内**，import 期绑定）：

| 原路径 | 现解析方式 |
|---|---|
| `cache/baostock_pb/` | `industry_crowding.baostock_cache_dir()` |
| `cache/em_industry_hist/` | `industry_crowding.em_hist_cache_dir()` |
| `cache/fundfof_crowding/` | `fundfof_crowding.fundfof_cache_dir()` |

现统一由 `app/core/cache.py::resolve_cache_subdir(name)` 解析到
**`CACHE_FILE_DIR`（缺省系统临时目录）** 下的同名子目录，与 `CacheService` 的 pickle 层同源：

```
$CACHE_FILE_DIR/                 # env 指定；缺省 tempfile.gettempdir()/fundmate_cache
├── cache_thermometer_self_calc.pkl   # CacheService（#1537）
├── baostock_pb/                      # 本目录原地址 → 现落这里
├── em_industry_hist/
└── fundfof_crowding/
```

原因：常量在 **import 那一刻**就绑定了环境，`CACHE_FILE_DIR` 只对 `CacheService` 生效，
「按环境指定缓存目录」（容器 / 只读文件系统 / CI / 测试隔离）会只生效一半；
源码树不可写时缓存还会静默失败。详见 `docs/spec/decisions.md` 与 issue #1531 / #1537 / #1539。

⚠️ **新增文件缓存一律走 `resolve_cache_file_dir()` / `resolve_cache_subdir()`**，
不要另立目录解析，也不要退回模块级常量——**必须在调用期解析**。

## ⚠️ 历史基线数据不在此处

全A中位 PB 历史 `all_pb.csv`（行业拥挤度分母兜底）位于 **`../data/all_pb.csv`**，
它是**基线数据而非运行时缓存，禁止删除**（见 `../data/README.md` 与 `scripts/guard_all_pb.py` 守卫）。
请勿把它放回本目录，也不要对 `data/all_pb.csv` 做 `.gitignore` 或清理。

## `.gitignore` 里为何还留着规则

`.gitignore` 的 `app/services/thermometer/cache/*/` 是**安全网**：万一有历史遗留
（或旧版本代码）在本目录重新生成子目录，不至于被误提交。规则本身无害，无需删除。
