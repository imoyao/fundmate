# -*- coding: utf-8 -*-
"""冷集写入硬上限（#2872）：把「冷集范围」前置到落库入口。

## 为什么需要它

`cold_set_guard`（#2123）是**事后巡检**：靠 cron / 手动跑，发现时行已经在库里了。
`backend/scripts/clean_daily_worth_retention.py` 是**事后清理**：要快照、要 `--apply`。
两者都发生在「写完之后」，而 `data-strategy.md` §4.3 真正要防的是「反复小批量灌」——
每次给几十只冷集基金补全历史，单看都在合法范围内，累起来把刚清掉的 800 万行灌回来
（实测 1.22 GB 膨胀，删掉 91.6% 的 `daily_worth` 行才降到 130 MB）。

本模块把同一条口径**前置到写入路径**：一次写入里「冷集 + 保留窗口外」的行超过硬上限，
直接拒绝该批写入并给出可操作的处置建议，而不是先落库、再等巡检/清理收场。

## 为什么是「拒绝」而不是「裁剪」

写进 `daily_worth` 又会被 `clean_daily_worth_retention.py` 删掉的行，本身是「写了就删」。
但**静默丢弃**在这里是更坏的选择：

- `SyncJob._execute_batches` 在这批写完后就 `stats['success'] += len(new_data)`，
  在 `_save_data` 里悄悄少写会让「成功行数」与库里的真实行数对不上；
- 冷集与热集是**会变**的（今天不持有，明天建仓），静默丢掉历史后，用户建仓那一刻
  才发现老数据不在了 —— 而清理脚本 §5.4 明确「残缺冷集基金属该补不该删」。

拒绝写入是可回滚的：换小 `--targets` 批次重跑即可，数据一行没丢。

## 为什么 fail-open

守卫自身故障（热集来源表缺失 / 查询报错）**绝不能阻断同步**：净值断更比多写几行严重
得多，而且 `SyncLog.get_last_sync_time` 只认 `status='success'`，一次误拦会把增量起点
永久钉在那一天（#1550 实测静默失败一个月）。此时保持原样写入、留 WARNING，
膨胀交回 `cold_set_guard` 巡检兜底 —— 三层防线只让最外层（写入期）fail-open。
"""

from datetime import date, timedelta
from typing import Any, Dict, Optional, Sequence, Set

from loguru import logger
from sqlalchemy.orm import Session

from app.services.cold_set_guard import RETENTION_DAYS, _hot_codes

# 单次写入允许的「冷集 + 保留窗口外」行数上限。
#
# 取值依据（不是拍脑袋）：一只基金 10 年日频净值约 2,500 行，一个 batch 默认 50 只 ——
#   · 事故形态「50 只 × 全历史」≈ 12.5 万行，超上限 6 倍，必拦；
#   · 合理形态「补 5 只冷集基金的全历史」≈ 1.25 万行，放行；
#   · 「补 8 只全历史」≈ 2 万行，正好卡在线上（`>` 而非 `>=`，等于阈值仍放行）。
# 窗口内的行**不计入**：它们正是 `data-strategy.md` 允许落库的部分，冷集保留 1 年。
MAX_COLD_ROWS_PER_WRITE = 20_000


def load_hot_codes(db: Session) -> Optional[Set[str]]:
    """热集代码集合；拿不到时返回 None（调用方 fail-open）。

    `cold_set_guard._hot_codes` 在来源表缺失时**故意**抛 `SystemExit`（宁可报错也不能
    少算热集 —— 少算会把「仅自选、未持有」的基金误判成冷集）。写入路径不能继承这个
    语义：那边是「删错了无法挽回」，这边是「不拦最多多写几行」。故在此把
    `SystemExit` 一并接住，降级为「本次不判定」。
    """
    try:
        return _hot_codes(db)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - 守卫故障不得阻断同步
        logger.warning(f'冷集写入守卫：热集口径不可用（{exc}），本次跳过上限校验')
        return None


def count_cold_out_of_window(
    records: Sequence[Dict[str, Any]],
    hot: Optional[Set[str]],
    *,
    keep_days: int = RETENTION_DAYS,
    today: Optional[date] = None,
    date_key: str = 'date',
    code_key: str = 'fund_code',
) -> int:
    """统计「冷集 + 保留窗口外」的行数（`hot` 为 None 时返回 0，即 fail-open）。

    窗口口径与 `clean_daily_worth_retention.py` 的 `--keep-days`（默认 365）一致：
    同一批行，「热集全留、冷集只留近 N 天」，两端口径不一致就会出现
    「写进来又被清掉」的往返。
    """
    if hot is None or not records:
        return 0

    cutoff = (today or date.today()) - timedelta(days=keep_days)
    overflow = 0
    for record in records:
        if record.get(code_key) in hot:
            continue
        value = record.get(date_key)
        # 日期不是 date 的一律不计：校验阶段已保证 shape，这里遇到异常值
        # 说明上游出了问题，交给 `_validate_data` 那侧报，不要在这里二次判定。
        if isinstance(value, date) and value < cutoff:
            overflow += 1
    return overflow


def enforce_cold_write_cap(
    db: Session,
    records: Sequence[Dict[str, Any]],
    *,
    job_name: str,
    cap: Optional[int] = None,
    keep_days: int = RETENTION_DAYS,
    today: Optional[date] = None,
    stats: Optional[Dict[str, Any]] = None,
) -> int:
    """写入前校验冷集溢出量；超上限则抛 `ValueError`（不落库、不丢数据）。

    `cap` 缺省取 `MAX_COLD_ROWS_PER_WRITE`（在**调用时**读取模块属性，便于测试与
    按环境调参；若写成默认参数会在函数定义时绑定，改模块常量就不再生效）。

    `stats` 传入 job 的 stats 字典时，把本批溢出量累加进 `cold_set_overflow`，
    随 `sync_logs` 一起落库 —— 排查「写了多少冷集历史」不必翻日志。

    Returns:
        本次写入里「冷集 + 保留窗口外」的行数（0 表示没有冷集历史写入）。

    Raises:
        ValueError: 溢出量 > `cap`。消息必须可操作 —— 运维看到的只有这一行日志。
    """
    limit = MAX_COLD_ROWS_PER_WRITE if cap is None else cap
    hot = load_hot_codes(db)
    overflow = count_cold_out_of_window(records, hot, keep_days=keep_days, today=today)
    if stats is not None:
        stats['cold_set_overflow'] = stats.get('cold_set_overflow', 0) + overflow
    if overflow > limit:
        raise ValueError(
            f'[{job_name}] 冷集写入超上限：本次待写入 {overflow} 行属于「冷集 + 保留窗口外」'
            f'（上限 {limit} 行，窗口 {keep_days} 天）。\n'
            '冷集 = 不在「持仓 ∪ 自选 ∪ 流水」里的标的；这些行落库后会被 '
            'clean_daily_worth_retention.py 按同一窗口清掉，属「写了就删」的无效膨胀'
            '（#2123 实测 1.22 GB）。\n'
            '处置：① 缩小 --targets 分批回填；② 确需长期保留就先加入自选（成为热集）'
            '再回填；③ 用户浏览触发的按需取走 fund_service 的另一条路径，不受此限。'
        )
    if overflow:
        logger.info(f'[{job_name}] 本批含冷集历史 {overflow} 行（上限 {limit}），已放行')
    return overflow
