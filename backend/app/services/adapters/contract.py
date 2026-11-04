# -*- coding: utf-8 -*-
"""上游响应结构契约（#2543）：把「上游长什么样」钉进代码，漂移即显性失败。

WHY
===
2026-10-23 的 ``fund_scale`` job 报红（生产 run ``39971621884``），日志里躺着
akshare 抛的 ``"['基金代码', '基金简称', ...] not in index"``——**上游把列名改了**。

适配层是 ``row.get('基金代码')`` 这种取值写法，列名一改有两条路：

1. akshare 自己先抛 ``KeyError`` → 被 ``except Exception: return []`` **吞成空列表**；
2. akshare 不抛错（改的只是我们依赖之外的列）→ ``row.get`` 静默返回 ``None``
   → 代码校验不过 → 整行 ``continue`` → **同样返回空列表**。

两条路的终点都是 ``[]``，和「上游今天真的没数据」**长得一模一样**。job 层的
``_require_non_empty`` 能把它判红（那次确实红了），但报出来的是「返回空数据」，
真正的原因（列名漂移）只留在源日志里——下一次要有人去翻日志才看得出。

所以这笔债的本质不是「没取到数」，而是**契约漂移被静默吞掉**。本模块把契约钉成
常量 + 断言：漂移当场抛 ``UpstreamContractError``，并把「缺哪些列 / 现有哪些列」
一并写进异常，下一轮值班不用翻源日志就能定位。

边界
====
- **只判必填列缺失**（破坏性）。多出未知列**只 warning**：上游加列不是漂移，
  但值得留痕——多半意味着该更新这份契约快照了。
- **不在此做网络请求**。本模块只认「已经拿到手的列」。
- 抛 ``UpstreamContractError``（``RuntimeError`` 子类）而非 ``ValueError``：
  契约漂移与「值不合法」是两件事，分开后 job 层与测试能按需单独捕获。

用法
====
    from app.services.adapters.contract import assert_columns

    assert_columns(
        df.columns,
        required=FUND_SCALE_REQUIRED_COLUMNS,
        known=FUND_SCALE_KNOWN_COLUMNS,
        source='akshare.fund_scale_open_sina',
    )
"""

from typing import Any, Iterable, Sequence, Tuple

from loguru import logger

__all__ = ['UpstreamContractError', 'assert_columns']


class UpstreamContractError(RuntimeError):
    """上游响应结构与代码里钉的契约不符（列名 / 列语义漂移）。

    属性 ``missing`` / ``present`` 供调用方与测试断言，不必反解 message 文本。
    """

    def __init__(
        self,
        message: str,
        *,
        missing: Sequence[str] = (),
        present: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.missing: Tuple[str, ...] = tuple(missing)
        self.present: Tuple[str, ...] = tuple(present)


# 异常里最多列出多少列：上游一次改几十个列名时，全量拼进 message 会把日志刷爆，
# 但**必须**给出「现有列」的样本——否则值班只能重新抓一次上游才能知道变成了什么。
_MAX_LISTED_COLUMNS = 20


def _clip(cols: Sequence[str]) -> str:
    shown = list(cols[:_MAX_LISTED_COLUMNS])
    tail = '' if len(cols) <= _MAX_LISTED_COLUMNS else f' …(共 {len(cols)} 列)'
    return f'{shown}{tail}'


def assert_columns(
    columns: Iterable[Any],
    *,
    required: Sequence[str],
    known: Sequence[str],
    source: str,
) -> None:
    """断言「拿到的列」覆盖契约里的必填列，缺即抛错；多出未知列只告警。

    参数
    ====
    columns
        上游实际列名（``df.columns`` 或任意可迭代对象），元素会按 ``str`` 归一化并去空格。
    required
        必填列。**缺任意一个即抛** ``UpstreamContractError``。
    known
        已知列全集（通常等于 ``required`` 加上游当前还会返回、但我们不用的列）。
        用于识别「上游新增了列」——不判红，只 warning。
    source
        上游标识（如 ``akshare.fund_scale_open_sina``），只用于错误信息与日志。
    """
    # 用 `is None` 而不是 `columns or []`：pandas 的 Index / Series 的真值是**歧义**的，
    # `bool(Index)` 直接抛 ValueError（本模块首次接入时被自家测试抓到）。
    cols = [] if columns is None else [str(c).strip() for c in columns]

    missing = [c for c in required if c not in cols]
    if missing:
        raise UpstreamContractError(
            f'{source} 上游列名契约不符：缺必填列 {missing}；实际列 {_clip(cols)}。'
            '（上游改列名？核对后同步本仓的契约常量，别把 row.get 的静默 None 当没数据）',
            missing=missing,
            present=cols,
        )

    extra = [c for c in cols if c not in known]
    if extra:
        # 不判红：上游加列不影响取值。但这是「契约快照过期」的信号，留痕以便更新。
        logger.warning(
            '{} 上游出现契约外的新列 {}：不影响本次取值，但建议核对后更新契约快照',
            source,
            _clip(extra),
        )
