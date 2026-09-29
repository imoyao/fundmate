---
title:全局配置（conftest)
---

# 什么是 conftest.py

可以理解成一个专门存放 fixture 的配置文件

实际开发场景
------

多个测试用例文件（test\_\*.py）的所有用例都需要**用登录功能来作为前置操作**，那就不能把登录功能写到某个用例文件中去了

如何解决上述场景问题
-----------

conftest.py 的出现，就是为了解决上述问题，单独管理一些全局的 fixture

conftest.py 配置 fixture 注意事项
------------------------

* pytest 会默认读取 conftest.py 里面的所有 fixture
* conftest.py 文件名称是固定的，不能改动
* conftest.py 只对同一个 package 下的所有测试用例生效
* 不同目录可以有自己的 conftest.py，一个项目中可以有多个 conftest.py
* 测试用例文件中不需要手动 import conftest.py，pytest 会自动查找

## 测试库连接模型（#1721，本仓特有）

本仓 `backend/tests/conftest.py` 的 `app` fixture 用**临时文件库**（`tmp_path/_fixture_*.db`）
+ 显式 `QueuePool`，使每个 Session 走独立连接、独立事务——连接/事务模型与生产（文件
SQLite + QueuePool）同构。

**为什么不用 `StaticPool`（原实现，全进程单连接）**：B 会话 `close()` 归还连接时的
reset（rollback）会把 A **未提交**的事务连带回滚；生产各 Session 各持连接、只回滚自己的
事务，此现象不可能发生。S2（PR #1716）实测假阳性：`StaleDataError: UPDATE agent_session
matched 0 row(s)`——根因是"未提交的行被他处 close 连带回滚"，后续 UPDATE 匹配 0 行。

**四个踩过的坑（勿回退，实测记录）**：

1. shared-cache 内存 URI（`?mode=memory&cache=shared`）：连接独立了，但 shared-cache 是
   **表级锁**——A 未提交写持表锁时，B 读同表立即 `OperationalError: database table is
   locked`（不排队等待），而"A 持未提交写 + B 读"在测试里是常态；
2. 裸 `file:` 开头的 URL 过不了 SQLAlchemy `make_url` 解析（须写 `sqlite:///file:...`
   形式）；
3. URL 含 `mode=memory` 时方言判为内存库、默认给 `SingletonThreadPool`（同线程复用同一
   连接，等于没改）——文件库方言默认才是 `QueuePool`，此处显式写出防漂移；
4. 引擎创建后跑 `PRAGMA journal_mode=WAL`（想对齐生产的 WAL）会给每个用例 ×2 引擎多一次
   文件打开（全量 3800+ 次），47 分钟全量实测偶发 2 例 `unable to open database file`
   直接 ERROR at setup——单进程串行测试下 DELETE journal 与 WAL 的锁差异为零，不值得为
   对齐买失败面，故引擎保持惰性（首次查询才开文件）。

**另一个坑**：fixture 建的文件名必须带 `_fixture_` 前缀（`_fixture_app.db` /
`_fixture_market.db`）——`clean_db(app)` 是 **autouse**（每个用例都会创建这两个文件），
而部分用例在**同一个 `tmp_path`** 下自建 `market.db` / `user.db`（如
`tests/core/test_db_data_domain.py`），同名同路径会让 fixture 落盘的表污染用例自建库，
表现为 `get_table_names()` 比预期集合多出一批表。

**判据（回归保护，恒绿才算此模型成立）**：`backend/tests/core/test_session_connection_model.py`
的两个用例——"他处 close 不得回滚我的未提交写"。新写涉及会话行的用例时**不需要**再逐个
手工"先提交会话行"。

**本地磁盘提示**：`tmp_path` 默认落在系统盘 TEMP。系统盘空间耗尽时症状是
`OperationalError: database or disk is full`（大量用例集体 ERROR）——此时把临时根指到大盘：
`PYTEST_DEBUG_TEMPROOT=<大盘>:\pytest_tmp`（CI/Linux 无需此步）。

## 模板库机制（#1722，均匀慢根治）

> 背景：`--durations=30` 实测全量 91m56s 中 **30 项有 24 项是 `setup`**，粗算 `app` fixture
> 占总时长约 87%——每用例都做 `Base.metadata.create_all` ×2（全套表 DDL）+
> `create_app()` → `init_db()`（10+ `migrate_*` ×2 引擎 + seed）。文件库模型（#1721）把这笔
> 纯 DDL 开销落到了磁盘上，全量从 36m 涨到 92m。解法是**只建一次库，之后字节复制**。

**机制**（`tests/conftest.py`）：

1. **首测建模板**：第一个进 `app` fixture 的用例走完整路径（create_all + create_app/init_db），
   在 `create_app()` 完成后、**测试体执行前** `dispose` 断开全部连接（回滚未提交页）再把
   `_fixture_app.db` / `_fixture_market.db` 复制到
   `.pytest_cache/fixture_tpl/<指纹>/`——模板是「schema + migrations + seed 完成态、**零业务数据**」。
   - 截取时机必须在测试体写入**之前**：若在 teardown 复制，首测写入的业务脏数据会随模板
     污染后续**所有**用例（这是本机制最隐蔽的坑）。
   - 复制前必须 `dispose`：池中连接可能持有未提交页，直接复制会把半截页写进模板。
2. **后续用例走模板**：`shutil.copyfile` ×2 秒级落地，`monkeypatch.setattr('app.main.init_db',
   lambda: None)` 跳过 init_db 重活。**`app` 对象仍每用例新建**（工厂本身便宜），故 config /
   路由不存在跨用例泄漏；#1608 引擎为查询期解析，patch 引擎指向照旧生效。
3. **指纹失效**：模板目录名 = `sha256(app/**.py 全部内容 + conftest.py)[:16]`（进程内只算一次）。
   schema / 迁移逻辑 / fixture 本身任何变更 → 指纹变 → 自动重建模板，杜绝「模板过期 → 缺表假红」。
   手工强制重建：删 `backend/.pytest_cache/fixture_tpl/` 即可（`.pytest_cache` 已在 .gitignore）。
4. **建模板时顺带清理其它指纹目录**，只保留当前一个（防缓存目录膨胀）。

**收益（2026-09-27 实测）**：`test_position_source_enum.py` 14 例 35.26s → 15.71s（-55%）；
`tests/domains` 692 例 4m30s（0.39s/例，此前全量均值 1.87s/例）；**全量快集
`-m "not slow"` 约 87m → 14m58s（≈ -83%）**，2223 用例总数与断言不变。归因与验收明细见
#1722 两条评论。

**联网冒烟的 slow 标记**：`tests/test_xalpha.py` 模块级 `pytestmark = pytest.mark.slow`
（`xa.indexinfo('000300')` 单例实测 259s，且是 `try/except + print` 无断言）。CI 的
`-m "not slow"` 因此**不再是空操作**（此前全仓 0 处打标，排除逻辑形同虚设）。
本地日常快集：`pytest -p no:xdist -m "not slow"`；提交前仍跑全量（含 slow）。

**并行度结论**：本机制**不引入任何并行**（单进程硬约束不变，无 OOM 回归面）；
提速全部来自「省重复建库」，测试总数与断言零变化。

## 参考文档

1. [Pytest 系列(2-3)-conftest 详解 - 我是小菜鸡丫丫 - 博客园](https://www.cnblogs.com/kxtomato/p/16600613.html)
