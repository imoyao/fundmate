# -*- coding: utf-8 -*-
"""账本精灵协作式取消注册表（#1714 L2）.

为什么是进程内注册表而非 DB 列（决策留言见 issue #1714，2026-09-27）：
- 当前部署为后端 Flask **单实例单进程**（本机常驻 + 单实例部署；vercel/wrangler
  只是前端托管），标志的写入方（cancel 端点）与读取方（run_agent 检查点）同进程，
  注册表检查点**零 IO**；
- DB 列方案在单实例下反而更贵：正在跑的请求持有独立 ORM 会话，跨请求写库后
  本请求不可见（隔离级别），检查点须用独立 DB 会话重查——每次检查点一次连接
  +查询，为单实例引入不值；
- **失效边界**：多 worker / 多实例部署下本注册表失效。升级路径：检查点接口
  （request_cancel / is_cancelled_since / clear）不变，把实现换成 agent_session
  行的 cancel 列或 Redis。

时序语义（时间戳方案，2026-09-27 定稿）：
- 标志带置位时刻（time.monotonic），检查点只认「本轮开始之后」的置位——
  用户点停止后立即发下一轮时，旧轮残留标志对新轮不可见（不误取消新轮）；
- 不做入口 clear：入口清标志会误清「请求刚发出、用户极快点停止」的合法置位
  （竞态窗口），时间戳比较天然替代它；
- finally clear 负责回收；从未再对话的会话残留项由 request_cancel 的容量
  自愈兜底（取消是低频操作，阈值触发全清无害）。
"""

import threading
import time

_LOCK = threading.Lock()
_CANCELLED: dict = {}  # session_id -> 置位时刻（time.perf_counter()）
_MAX_ENTRIES = 1000  # 容量自愈阈值：僵尸标志（无 run_agent 消费）堆积时全清


def request_cancel(session_id: str) -> None:
    """标记会话取消（cancel 端点调用；幂等，后置位覆盖早置位）."""
    with _LOCK:
        if len(_CANCELLED) >= _MAX_ENTRIES and session_id not in _CANCELLED:
            _CANCELLED.clear()  # 容量自愈：僵尸标志（正常由 run_agent finally 回收）
        _CANCELLED[session_id] = time.perf_counter()


def is_cancelled_since(session_id: str, started_at: float) -> bool:
    """检查点查询（run_agent 调用）：只认本轮开始之后的置位.

    started_at 是本轮 run_agent 记录的 time.perf_counter() 起点；置位时刻早于
    它的标志属于上一轮（用户点停止后立即发新轮的场景），不得误取消本轮。
    时钟必须用 perf_counter（Windows QPC 纳秒级）而非 monotonic（实测
    GetTickCount64 粒度 ~15.6ms，同粒度内两次取值相同会把「本轮前的置位」
    误判为不早于起点——2026-09-27 测试实锤）。
    """
    with _LOCK:
        requested_at = _CANCELLED.get(session_id)
        return requested_at is not None and requested_at >= started_at


def clear(session_id: str) -> None:
    """清除标志（run_agent finally 调用，负责回收本轮消费的标志）."""
    with _LOCK:
        _CANCELLED.pop(session_id, None)
