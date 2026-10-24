# tests/core 包标记：使本目录内的测试可以相对导入兄弟辅助模块
# （如 migrations_pg_fake.PgFake，#2534）。pytest 默认 prepend 导入模式下，
# 带上该文件后本目录测试以 tests.core.* 导入，sys.path 注入 backend/ 根。
