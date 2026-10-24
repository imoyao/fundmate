# -*- coding: utf-8 -*-
"""可转债**下修历史**回填（#2585；手动回填型，按目标池）。

为什么单开一个 job 而不是塞进 `convertible_bond`：条款 job 是「一次调用换全市场」
的列表型（快照），下修历史是**逐只一次 HTTP**的事件流。两者的失败面、限流风险与
目标池纪律完全不同 —— 混在一起会让条款同步被迫按目标池跑（或反之让逐只抓取
在裸 `--full-sync` 下打全市场 550 次）。见 `docs/spec/data-strategy.md` §4.3.3。

目标池 = 用户触达的转债（自选 ∪ 持仓，经 `resolve_targets()['stock']` 过滤 11x/12x）。
池里混着股票与 ETF，故**非转债目标静默跳过**但计入 `not_bond`（不进 `errors`：
那不是失败，只是「这个目标不归本 job 管」）。

统计口径（四个数**必须**加总等于本轮目标数，否则说明有目标被静默吃掉）：

    with_records + no_records + not_bond + failed == total

`no_records`（源侧「暂无数据」）与 `failed`（抓取/解析失败）是**两件事**，不得合并
—— 前者是「这只债从没下修过」，后者是「我们没拿到」，合起来会让下修列静默显示
「无记录」（#2543 / #171 同族：空 ≠ 没拿到）。
"""

from typing import Any, Dict, List, Optional

from loguru import logger

from app.domains.securities.models import ConvertibleBondAdjustLog
from app.services.adapters.jsl_bond_adjust_adapter import SOURCE
from app.services.job_base import SyncJob
from app.services.sync.bulk_ops import set_if_changed, values_equal

#: 参与比较 / 落库的字段（唯一键 `symbol` + `shareholder_meeting_date` 单独处理）
_VALUE_FIELDS = (
    'bond_code',
    'name',
    'convert_price_before',
    'convert_price_after',
    'effective_date',
    'adjust_floor_price',
    'source',
)


def _bare_bond_code(target: str) -> Optional[str]:
    """目标池条目 → 转债 6 位码；非转债返回 ``None``。

    可转债代码空间有确定性惯例（沪 11xxxx / 深 12xxxx），先剥交易所前缀再按前缀判。
    不用 `get_normalizer()`：它按 A 股前缀推断市场，会把 113050（沪市转债）判成 SZ
    （`convertible_bond_job._bond_symbol` 踩过，故那里也是手写映射）。
    """
    s = (target or '').strip().upper()
    for prefix in ('SH', 'SZ', 'BJ'):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    s = s.split('.')[0]
    if len(s) == 6 and s.isdigit() and (s.startswith('11') or s.startswith('12')):
        return s
    return None


def _symbol_of(bond_code: str) -> str:
    """6 位转债码 → 标准 symbol（11x → SH，12x → SZ）。"""
    return f'SH{bond_code}' if bond_code.startswith('11') else f'SZ{bond_code}'


class BondAdjustLogSyncJob(SyncJob):
    """可转债下修历史同步（逐只抓取，按目标池限量）。"""

    #: 本轮目标的分桶计数。四个桶**始终存在**（初值 0），这样 `stats` 自带口径，
    #: 读结果的人不必猜「缺这个键是不是没跑」。
    _BUCKETS = ('with_records', 'no_records', 'not_bond')

    def __init__(self, adapter, db):
        super().__init__(adapter, db)
        for key in self._BUCKETS:
            self.stats[key] = 0

    @property
    def _allow_empty_data(self) -> bool:
        # 空目标池 = 用户当前没有触达任何转债 ⇒ 显式跳过，不是故障。
        # 反例：当成失败会让「还没自选转债」的用户每天看到一条红灯。
        return True

    def get_name(self) -> str:
        return 'bond_adjust_log'

    # ── 抓取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for target in targets:
            bond_code = _bare_bond_code(target)
            if bond_code is None:
                self._bump('not_bond')
                continue
            symbol = _symbol_of(bond_code)
            try:
                items = self.adapter.fetch_adjust_logs(bond_code)
            except Exception as exc:  # noqa: BLE001 - 单只失败不拖垮整批（计入 errors 显性上报）
                self._bump('failed')
                self.stats['errors'].append(f'{target}: {exc}')
                logger.warning(f'下修历史抓取失败 {target}: {exc}')
                continue
            if not items:
                self._bump('no_records')
                continue
            self._bump('with_records')
            for item in items:
                rows.append(
                    {
                        'symbol': symbol,
                        'bond_code': bond_code,
                        'shareholder_meeting_date': item.get('shareholder_meeting_date'),
                        **{k: item.get(k) for k in _VALUE_FIELDS if k != 'bond_code'},
                        'source': SOURCE,
                    }
                )
        logger.info(
            f'下修历史抓取：有记录 {self.stats.get("with_records", 0)} 只 / '
            f'暂无数据 {self.stats.get("no_records", 0)} 只 / '
            f'非转债 {self.stats.get("not_bond", 0)} 个 / '
            f'失败 {self.stats.get("failed", 0)} 只（明细 {len(rows)} 行）'
        )
        return rows

    def _bump(self, key: str) -> None:
        self.stats[key] = self.stats.get(key, 0) + 1

    # ── 校验 / 去重 / 落库 ──

    def _validate_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for r in raw_data:
            # 唯一键两列缺一不可：股东大会日缺失会让同一事件反复长新行。
            # **不静默丢弃**——解析层已保证这两列非空，走到这里说明有 bug，
            # 记为失败让它在 errors 里显形（静默丢会让 job 报 success 而 0 行落库）。
            if not r.get('symbol') or not r.get('shareholder_meeting_date'):
                self.stats['errors'].append(f'下修记录缺唯一键: {r!r}')
                logger.error(f'下修记录缺唯一键，已丢弃: {r!r}')
                continue
            out.append(r)
        return out

    def _deduplicate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批内按 (symbol, 股东大会日) 去重；与库内**完全相同**的记录直接跳过。

        为什么不是「库内已有就跳过」：历史事件本身不变，但**生效日期可被公告顺延**
        （源侧会改这一格）。一律跳过会让这类更正永远进不来；一律 upsert 又会让
        每轮重复跑都产生写库往返（Turso 上每次都是 HTTP，见 #2522）。故按值判等：
        完全相同 → skipped；有差异 → 放行给 `_save_data` 做覆盖。
        """
        seen: Dict[tuple, Dict[str, Any]] = {}
        for r in data:
            seen[(r['symbol'], r['shareholder_meeting_date'])] = r

        existing = self._load_existing({r['symbol'] for r in seen.values()})
        out = []
        for key, r in seen.items():
            row = existing.get(key)
            if row is not None and all(values_equal(getattr(row, f), r.get(f)) for f in _VALUE_FIELDS):
                continue
            out.append(r)
        return out

    def _load_existing(self, symbols: set) -> Dict[tuple, ConvertibleBondAdjustLog]:
        """按 symbol 批量取库内已有行 → ``{(symbol, 股东大会日): row}``。"""
        if not symbols:
            return {}
        rows = self.db.query(ConvertibleBondAdjustLog).filter(ConvertibleBondAdjustLog.symbol.in_(symbols)).all()
        return {(row.symbol, row.shareholder_meeting_date): row for row in rows}

    def _save_data(self, new_data: List[Dict[str, Any]]) -> None:
        existing = self._load_existing({r['symbol'] for r in new_data})
        inserted = updated = 0
        for r in new_data:
            key = (r['symbol'], r['shareholder_meeting_date'])
            row = existing.get(key)
            if row is None:
                row = ConvertibleBondAdjustLog(
                    symbol=r['symbol'],
                    shareholder_meeting_date=r['shareholder_meeting_date'],
                )
                self.db.add(row)
                inserted += 1
            else:
                updated += 1
            for field in _VALUE_FIELDS:
                # 源是全量快照（每次返回该债的完整下修史），故**空值也照写**：
                # 这里没有「本轮没取到」与「源说没有」的区别，留着旧值反而成脏数据。
                set_if_changed(row, field, r.get(field))
        self.db.commit()
        logger.info(f'写入可转债下修历史 {len(new_data)} 条（新增 {inserted} / 更新 {updated}）')

    # ── 结果补充 ──

    def _build_result(self) -> Dict[str, Any]:
        result = super()._build_result()
        # 四个分桶与 total 加总必须相等；不等说明有目标既没进桶也没记失败
        buckets = ('with_records', 'no_records', 'not_bond', 'failed')
        result['stats']['bucket_sum'] = sum(self.stats.get(k, 0) for k in buckets)
        if result['stats']['bucket_sum'] != result['stats'].get('total', 0):
            logger.warning(
                f'下修历史统计不自洽：分桶合计 {result["stats"]["bucket_sum"]} '
                f'!= 目标数 {result["stats"].get("total", 0)}'
            )
        return result
