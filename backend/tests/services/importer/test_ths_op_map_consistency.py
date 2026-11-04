# tests/services/importer/test_ths_op_map_consistency.py
"""#2854：活表 / 死表不得漂移的守卫。

背景：`core/constants.THS_OP_TYPE_MAP` 模块名最像「真相源」、docstring 写得比活表
还全，但导入链路真正消费的是 `services/importer/mappings.THS_OP_MAP`。两表并存时
同样一个「红利入账」在活表是 `dividend_cash`、死表是 `dividend`——#2844 修
「两个分红码并存」时踩的就是这个分叉：谁先改哪张表，决定那笔钱算不算进收益。

本守卫不去删死表（它仍被零实例化的 TransactionParser 引用，删除面过大），
而是把「共同键归一后必须一致」钉成判据：将来有人只改一张表，这里立刻转红。
"""

from app.core.constants import THS_OP_TYPE_MAP
from app.services.importer.mappings import THS_OP_MAP


def _canonical(code: str) -> str:
    """死表的历史码 `dividend` 与活表的 `dividend_cash` 是同一个业务语义。"""
    return 'dividend_cash' if code == 'dividend' else code


def test_live_and_dead_maps_do_not_drift_on_common_keys():
    common = {k for k, v in THS_OP_TYPE_MAP.items() if v is not None} & set(THS_OP_MAP)
    assert common, '两表没有共同键，守卫形同虚设'

    drift = {
        k: (THS_OP_MAP[k], THS_OP_TYPE_MAP[k])
        for k in sorted(common)
        if _canonical(THS_OP_MAP[k]) != _canonical(THS_OP_TYPE_MAP[k])
    }
    assert not drift, f'活表与死表对同一操作名给出不同语义：{drift}'


def test_all_live_ops_are_registered_in_dead_map_or_explicitly_ignored():
    """活表新增操作名时，守卫提醒维护者：要么同步死表，要么在注释里说明为何不同步。"""
    from app.services.importer.mappings import THS_IGNORED_OPS

    missing = set(THS_OP_MAP) - set(THS_OP_TYPE_MAP) - set(THS_IGNORED_OPS)
    assert not missing, f'活表有、死表没有的操作名：{sorted(missing)}'
