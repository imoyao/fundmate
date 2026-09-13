# app/services/sync/jobs/market_snapshot_job.py
"""探市 20 大类资产每日快照落库（#1460，方案 B 最小版）。

背景
    `/api/market/overview` 原本每次（冷缓存）都要向 akshare 各源拉**每个资产的全量历史**
    再当场现算指标：冷启动 12~42s、完全依赖第三方源可用性、而且**不落库**——源挂了页面
    只剩 `—`，数据坏了也没人知道（2026-09-13 才发现 2 个汇率资产一直在展示 2023 年的
    「当日涨跌」）。本 job 把「每日算好的结果」落进 `market_multi_items`，端点即可
    毫秒级读库；实时取数降级为「库空」时的兜底。

设计要点（详见 docs/working-notes/market-snapshot-persist-plan-2026-09-13.md）
    - **只落结果、不落序列**：分位与 σ 每次取数时由数据源返回的全历史当场现算，
      库内不存收盘序列（`docs/spec/data-strategy.md` 的 L3 口径；实测 12/14 资产
      1492~8724 行，落序列既无必要也违背「不存多余数据」）。
    - **结构性软占位不入库**：海外 4 资产 / 中证2000 / 比特币是「源不存在」的**结构性事实**，
      由代码常量 `ASSET_CONFIG` 提供，落库等于每天重复写 6 行常量。
    - **取数复用 `MarketOverviewService.fetch_snapshot()`**，不另写一套——否则
      「页面算的分位」与「库里落的分位」迟早分叉。
    - **单资产失败落 `stale=True`**（不落上次的值）：读时回退最近一次成功值。
      这样「今天失败」这件事本身可审计，而页面仍有值可显示。
    - **交易日滞后守卫**：`trade_date` 落后同批次最大值超过 `STALE_TRADE_DAYS` 也置
      `stale=True`。这是「坏数据可见」的兜底——F6 那种落后 2 年的数据会被立刻抓住，
      不依赖任何人工巡检。

状态口径
    全部行取数失败 → `FAILED`（探市快照属关键 job，按 D9「连续 1 次失败即告警」）；
    部分失败 → `SUCCESS`，但失败明细写进 `stats.errors`（经
    `Orchestrator._save_sync_log` 落进 `sync_logs.error_detail`，可查）。
    **不采用「任一失败即 FAILED」**：单个源长期抖动会让 sync_logs 天天是失败，
    告警变成噪声，反而掩盖真事故。

幂等
    复用 `TemperatureService.save_multi_items` 的「同 source 当日先删后插」语义，
    同日重复跑只 upsert 同批行（唯一键 `(source, item_type, item_code, collected_at)`）。

保留期
    既有 `TemperatureService.cleanup_old_data()` 已按 1 年清理本表，**零新增代码**；
    该清理由 `temperature` job 调用（`thermometer/jobs.py:308`）。
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from app.core.time_utils import now_shanghai
from app.services.market_service import (
    ASSET_CONFIG,
    SNAPSHOT_BOND_ITEM_CODE,
    SNAPSHOT_BOND_ITEM_TYPE,
    SNAPSHOT_ITEM_TYPE,
    SNAPSHOT_SOURCE,
    STALE_TRADE_DAYS,
    MarketOverviewService,
)
from app.services.sync.adapters.null_adapter import NullAdapter
from app.services.sync.jobs.base import JobStatus, SyncJob
from app.services.thermometer.service import TemperatureService

# 债券收益率轨的行名（前端不消费本字段，仅便于人工查库辨识）
_BOND_ITEM_NAME = '中美国债10Y收益率'


class MarketSnapshotSyncJob(SyncJob):
    """探市 20 大类资产每日快照落库"""

    def __init__(self, db):
        # 取数在 market_service 内直连 akshare，不经数据源适配器 → NullAdapter 占位
        # （与 temperature / amac_institution / asset_snapshot 一致）
        super().__init__(NullAdapter(), db)

    def get_name(self) -> str:
        return 'market_snapshot'

    # run() 已重写，以下抽象方法仅满足 ABC 要求、运行期不被调用
    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        return []

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return raw_data

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        return data

    def _save_data(self, new_data: List[dict]) -> None:
        pass

    # ── 主流程 ──

    def run(self, full_sync: bool = False, targets: Optional[List[str]] = None) -> Dict[str, Any]:
        self._full_sync_flag = full_sync
        self.snapshot_time = now_shanghai()
        # 统一以 job 开始时刻的上海日期作为 collected_at，避免同批次跨午夜时取到不一致的「今日」
        collected_at = self.snapshot_time.date()

        self.logger.info('开始探市 20 大类资产每日快照')
        # force_refresh=True：本 job 是**每日权威写入**，必须反映 job 执行时刻的真实源数据。
        # 若复用缓存，可能出现「job 今天写的其实是几十分钟前某次 Web 请求算出的结果」，
        # 滞后守卫也会变成在守卫一批旧数据；多付一次全量取数的代价（每天一次）可以接受。
        snapshot = MarketOverviewService.fetch_snapshot(force_refresh=True)
        items = snapshot['items']

        # 同批次最大 trade_date = 「这批数据的最新市场日」，作为滞后守卫的参照
        max_trade_date = self._max_trade_date(items)

        rows: List[Dict[str, Any]] = []
        errors: List[str] = []
        ok = 0
        for asset, item in zip(ASSET_CONFIG, items):
            if not asset.get('available', True):
                continue  # 结构性软占位不入库
            row, err = self._asset_row(asset, item, collected_at, max_trade_date)
            rows.append(row)
            if err:
                errors.append(err)
            else:
                ok += 1

        bond_row, bond_err = self._bond_row(snapshot['bond_yield'], collected_at)
        rows.append(bond_row)
        if bond_err:
            errors.append(bond_err)
        else:
            ok += 1

        total = len(rows)
        try:
            written = TemperatureService.save_multi_items(rows)
        except Exception as e:  # noqa: BLE001 - 落库失败必须记成失败审计，不能静默
            self.logger.exception(f'探市快照落库失败: {e}')
            self.status = JobStatus.FAILED
            self.stats = {'total': total, 'success': 0, 'skipped': 0, 'failed': total, 'errors': [str(e)]}
            return self._build_result()

        failed = len(errors)
        # 全部失败才判 FAILED（见模块 docstring「状态口径」）
        self.status = JobStatus.FAILED if failed >= total else JobStatus.SUCCESS
        self.stats = {
            'total': total,
            'success': ok,
            'skipped': 0,
            'failed': failed,
            'written': written,
            'errors': errors,
        }
        self.logger.info(f'探市快照完成：写入 {written} 行，取数成功 {ok}/{total}，失败 {failed}')
        return self._build_result()

    # ── 行构造 ──

    def _asset_row(
        self,
        asset: Dict[str, Any],
        item: Dict[str, Any],
        collected_at: date,
        max_trade_date: Optional[date],
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """把资产项转成 `market_multi_items` 的一行。

        Returns:
            (row, error)：error 非空表示该行是降级行（`stale=True`）。
        """
        reason: Optional[str] = None
        if not item.get('available'):
            reason = item.get('reason') or '取数失败'
        else:
            lag = self._trade_lag_days(item.get('trade_date'), max_trade_date)
            if lag is not None and lag > STALE_TRADE_DAYS:
                reason = f'交易日滞后 {lag} 天（trade_date={item.get("trade_date")}）'
                self.logger.warning(f'探市资产 {asset["key"]} 数据滞后 {lag} 天，标记 stale')

        data: Dict[str, Any] = {
            'change_pct': item.get('change_pct'),
            'trade_date': item.get('trade_date'),
            'data_asof': item.get('data_asof'),
            'position': item.get('position'),
            'anomaly': item.get('anomaly'),
            'caliber': item.get('caliber'),
        }
        if reason:
            data['error'] = reason

        row = {
            'source': SNAPSHOT_SOURCE,
            'item_type': SNAPSHOT_ITEM_TYPE,
            'item_code': asset['key'],
            'item_name': asset['name'],
            'data': data,
            'collected_at': collected_at,
            'stale': bool(reason),
        }
        return row, (f'{asset["key"]}: {reason}' if reason else None)

    def _bond_row(
        self,
        bond_yield: Optional[Dict[str, Any]],
        collected_at: date,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """债券收益率轨一行。取不到也落一行 stale，让「今天没取到」可审计。"""
        stale = not bond_yield
        data: Dict[str, Any] = dict(bond_yield) if bond_yield else {'error': '债券收益率轨取数失败'}
        if bond_yield:
            data['data_asof'] = self.snapshot_time.strftime('%Y-%m-%d %H:%M:%S')
        row = {
            'source': SNAPSHOT_SOURCE,
            'item_type': SNAPSHOT_BOND_ITEM_TYPE,
            'item_code': SNAPSHOT_BOND_ITEM_CODE,
            'item_name': _BOND_ITEM_NAME,
            'data': data,
            'collected_at': collected_at,
            'stale': stale,
        }
        return row, (f'{SNAPSHOT_BOND_ITEM_CODE}: 取数失败' if stale else None)

    # ── 交易日滞后守卫 ──

    @staticmethod
    def _parse_trade_date(raw: Any) -> Optional[date]:
        """解析数据源给的 trade_date。解析不出返回 None（**不抛**——守卫不能成为新的失败点）。"""
        if raw is None:
            return None
        try:
            return datetime.strptime(str(raw).strip()[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None

    @classmethod
    def _max_trade_date(cls, items: List[Dict[str, Any]]) -> Optional[date]:
        """同批次资产里最大的 trade_date（作为「这批数据的最新市场日」）。"""
        best: Optional[date] = None
        for it in items:
            d = cls._parse_trade_date(it.get('trade_date'))
            if d is not None and (best is None or d > best):
                best = d
        return best

    @classmethod
    def _trade_lag_days(cls, raw: Any, ref: Optional[date]) -> Optional[int]:
        """该资产的 trade_date 落后参照日多少天；任一侧不可解析返回 None（不判定）。"""
        d = cls._parse_trade_date(raw)
        if d is None or ref is None:
            return None
        return (ref - d).days
