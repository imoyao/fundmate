# -*- coding: utf-8 -*-
"""重复追问检测（设计 §6-C，防「反复追问软化」式越界）。

用户对同一问题（归一化后）连续追问 N 次，说明他不接受前面的回答、试图把模型
「问软」——此时不再让模型自由发挥，改回**强制标准话术**（同一段确定的话术，
模型没有机会在第 4 次时给出越界答案）。

状态形态（设计明说「会话内状态，可内存或 Redis」）：本模块用**进程内 dict + 锁**，
单实例部署下够用；多实例水平扩展后会各记各的——与 `guards.py` 三件套同属
「单实例内存实现」的既有技术债，迁移去向一并由 #1294（防护层多实例化）承载，
故此处不新建表、不预支数据准入（**零新增表列**）。

会话数按上限做 LRU 式淘汰，防止 dict 无界增长（同一进程内 session_id 来自前端，
可被任意构造——不淘汰就是个内存放大器）。
"""

import os
import re
import threading
import unicodedata

from dotenv import load_dotenv

load_dotenv()  # 独立脚本直接 import 时也能读到 .env（与 guards.py 同口径）

# 连续同问达该阈值即强制标准话术（第 N 次起）
REPEAT_THRESHOLD = int(os.getenv('AGENT_REPEAT_THRESHOLD', '3'))
# 内存里最多保留多少个会话的计数（超出按插入顺序淘汰最旧的，防 dict 无界）
REPEAT_MAX_SESSIONS = int(os.getenv('AGENT_REPEAT_MAX_SESSIONS', '512'))

STANDARD_REPLY = (
    '我注意到你把同一个问题连着问了第 {} 次，说明前面的回答没能解决你的顾虑。'
    '先把事实摆清楚：我只能查已经发生的数据，不能预测涨跌、不给买卖建议、也不承诺收益。'
    '如果你想换角度，可以让我查这几样——历史净值走势、你的持仓成本与浮亏、当前市场温度；'
    '或者告诉我你真正纠结的点，我按事实帮你梳理。'
)

# 归一化时剔除的字符：标点 / 空白 / 引号 / 全角括号等（「近一年涨跌幅？」==「近一年涨跌幅」）
_STRIP_CHARS = ''.join(ch for ch in ('，。！？；：、,.!?;:\'"“”‘’（）()[]【】<>《》—…· \t\r\n　'))


def normalize(text: str) -> str:
    """归一化：全角转半角 → 去标点空白 → 小写。

    目的：让「近一年涨跌幅？」与「近一年涨跌幅」被认作同一问，
    否则换个标点就能绕过 N 次计数，检测形同虚设。
    """
    if not text or not isinstance(text, str):
        return ''
    text = unicodedata.normalize('NFKC', text)  # 全角 → 半角（含全角数字/字母）
    text = text.translate(str.maketrans('', '', _STRIP_CHARS))
    return re.sub(r'\s+', '', text).lower()


class RepeatTracker:
    """按 session 记录「最近一次问法」与连续同问次数。

    线程安全：读改写在锁内完成（web 服务器是多线程的，无锁计数会丢更新）。
    """

    def __init__(self, threshold: int = REPEAT_THRESHOLD, max_sessions: int = REPEAT_MAX_SESSIONS):
        self.threshold = max(1, int(threshold))
        self.max_sessions = max(1, int(max_sessions))
        self._counts: dict = {}  # {session_id: [归一化问法, 连续次数]}
        self._lock = threading.Lock()

    def record(self, session_id: str, text: str) -> bool:
        """记录一次提问。

        :returns: True 表示「已达到阈值」——调用方应改回标准话术，**不要**再调模型。
        """
        key = str(session_id or '')
        norm = normalize(text)
        if not key or not norm:
            return False
        with self._lock:
            prev = self._counts.get(key)
            if prev is not None and prev[0] == norm:
                prev[1] += 1
            else:
                # 换了问法 → 重新计数（连续性是本规则的定义，不同问题互不相干）
                self._counts[key] = [norm, 1]
                self._evict_locked(key)
            return self._counts[key][1] >= self.threshold

    def reset(self, session_id: str) -> None:
        """丢弃某会话的计数（换新对话 / 会话结束时调用）。"""
        with self._lock:
            self._counts.pop(str(session_id or ''), None)

    def count(self, session_id: str) -> int:
        """当前会话的连续同问次数（测试与诊断用）。"""
        with self._lock:
            prev = self._counts.get(str(session_id or ''))
            return prev[1] if prev else 0

    def _evict_locked(self, just_key: str) -> None:
        """超上限时淘汰最旧条目（dict 保持插入序，Python 3.7+）。调用方须已持锁。"""
        if len(self._counts) <= self.max_sessions:
            return
        for key in list(self._counts):
            if key == just_key:
                continue
            self._counts.pop(key, None)
            if len(self._counts) <= self.max_sessions:
                break

    def __len__(self) -> int:
        with self._lock:
            return len(self._counts)


# 进程内单例：调用方只用这一个（测试可自建实例，避免共享状态串味）
repeat_tracker = RepeatTracker()
