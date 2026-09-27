# Windows 本机 pytest 的环境前提（三类环境性失败）

> 内部备忘 · 2026-09-27
>
> 起因：`#1701`（两处）与 `#1727`（第三处）是**同一族**问题——「测试依赖了调用方环境」，在本机红、
> 在 CI 绿（或反之），且报错点离真因很远。原先只有 `#1701` 的两条记在
> `agent-dev-progress-2026-09-26.md`（agent 开发日志里），跨领域难找，故收拢到本文件。
>
> 注：`#1727` 是修 `#1719`（「历史会话栏」功能卡）时跑全量取证发现的，所以那张卡页脚写着
> 「范围外发现自 #1719」——**`#1719` 本身与本节无关**，别把它当成同族卡。

---

## 1. 三类环境前提 / 陷阱

| # | 现象 | 根因 | 现状 |
|---|------|------|------|
| **#1701-①** | 子进程脚本测试的 GBK 输出按 UTF-8 读 → 崩 | 本机 Windows 默认 `cp936`，子进程 `print` 中文出 GBK | 跑全量前设 `PYTHONUTF8=1` |
| **#1701-②** | 迁移测试建 `postgresql://` 引擎 → 缺 `psycopg2` | `pyproject` 的 `sys_platform != "win32"` 平台标记在 win32 上剔除了 `psycopg2-binary`，但迁移测试要建 postgres 引擎 | 新装 venv 需**手装** `psycopg2-binary` |
| **#1727** | `tests/core/test_db_factory.py` + `test_db_lazy_engine.py` 共 3 例必红：`NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:sqlite.libsql` | 本机 `backend/.env` 带真实 `TURSO_DATABASE_URL`，它在 import 期经 `load_dotenv()` 进了 `os.environ`；这 3 例把 `APP_ENV` 推到 `production`，market 域于是路由到 turso（`_normalize_db_url` 归一为 `sqlite+libsql://`），而 Windows 装不了 `sqlalchemy-libsql` | **已修**（PR 见 #1727）——见第 3 节 |

> 三类都不是代码回归：它们在**主仓 `dev` 工作区**同样复现，且 CI 不受影响（Ubuntu + 无 `.env`）。
> 判据：某天本机全量突然红几条、而 CI 全绿，先按本表对号，别急着怀疑自己改坏了。

## 2. 为什么 CI 绿而本机红（#1727 的具体机制）

1. `.env` 不入库（gitignored），CI 上没有 `TURSO_DATABASE_URL` → `for_app('production')` 回退
   `DATABASE_URL` → 本地 SQLite，全程不碰 libsql 方言；
2. 本机 `.env` 有 `TURSO_DATABASE_URL`（自 2026-09-15 起）→ 任何把 `APP_ENV` 设为 `production`
   又**真建引擎**的用例都会炸；
3. 两个子进程探针把 `os.environ` **整份**交给子进程，而子进程 `import app.main` 时会再跑一次
   `load_dotenv()` —— 所以「从 env 里删掉」做不到中和，**必须显式给值**。

## 3. 修复口径（#1727 定下，后续同类照此办理）

**在测试侧中和，不碰生产路由、不动 `pyproject` 平台标记。**

- 生产侧 `db_factory` 的行为是对的（`production` 就该优先 Turso）；Windows 装不了 libsql 是
  **开发机限制**，不是产品缺陷。为测试去放宽平台标记或给生产代码加分支，是把开发机问题带进产品；
- 测试侧两处下手：
  - **子进程探针**：`_probe_env()` 显式把 `TURSO_DATABASE_URL` 指向本地 SQLite（空串/删除都不可靠，见第 2 节第 3 条）；
  - **进程内用例**：`_reset_and_set()` 默认把 `TURSO_DATABASE_URL` 中和成本地 SQLite，
    显式传入者以传入值为准（验证 turso 归一化的用例不受影响）；
  - 附带一条：mock 了 `create_engine` 的用例，**所有**建引擎调用都要落在 mock 内，
    否则「环境里恰好没有 turso」就成了隐含前提（#1727 的原始形态）。

**可观测性要求**：由测试基础设施承担的不变量（如上面的默认中和）必须**自己有一条用例钉住**，
否则它退化成没人能发现、也没人能回归的摆设。见
`tests/core/test_db_factory.py::test_reset_and_set_neutralizes_ambient_turso`。

## 4. 本机复现 / 验证命令

```bash
cd backend
P="D:/codes/fundmate/backend/.venv/Scripts/python.exe"   # 本机 pdm 已损坏，用主仓 venv

# 复现 #1727（等价于「.env 里有 TURSO_DATABASE_URL」）
APP_ENV=development TURSO_DATABASE_URL='turso://x@example.turso.io/db?authToken=dummy' \
  PYTHONPATH="$PWD" "$P" -m pytest -p no:xdist -q \
  tests/core/test_db_factory.py tests/core/test_db_lazy_engine.py

# CI 口径（无 .env / 无 TURSO）
env -u TURSO_DATABASE_URL -u APP_ENV PYTHONPATH="$PWD" "$P" -m pytest -p no:xdist -q \
  tests/core/test_db_factory.py tests/core/test_db_lazy_engine.py
```

两者都应全绿（各 26 passed）。修复前前者 3 failed。

## 5. 还有哪些测试会碰 `APP_ENV`

全仓只有 3 个测试文件设置 `APP_ENV`：`test_db_factory.py`、`test_db_lazy_engine.py`、
`test_db_data_domain.py`（后者设的是 `development`，安全）。新增同类用例请走
`_reset_and_set()`，不要裸调 `monkeypatch.setenv`。
