# -*- coding: utf-8 -*-
"""自选提醒的**编排层**：家庭设置、逐标的规则、扫描投递。

三层分工（低耦合的落点，改任一层不必动另两层）：

| 层 | 文件 | 只负责 |
|---|---|---|
| 规则 | `alerts.rules` | 阈值口径 / 触发判据 / 文案（纯函数，无 DB） |
| 行情 | `alerts.quotes` | 批量取价（两次 IN 查询，与标的数同阶） |
| 编排 | 本文件 | 家庭隔离、规则与默认值的合并、调 `notification_service.emit_many` |

## 多租户口径（必须逐条满足）
1. **用户数据一律带 `family_id`**：规则经 `watchlist.id` 归属家庭，设置表自带
   `family_id`；越权与不存在一律 404（不泄漏「这条规则存在但不属于你」）。
2. **市场数据只读且共享**：行情由 `watchlist_alert_prices` 批量取，不夹带任何
   用户态过滤，也就没有跨家庭泄漏面。
3. **通知按家庭投递**：`emit_many(db, family_id, ...)` 的 `dedup_key` 由
   `(family_id, dedup_key)` 唯一约束兜底，同家庭同键一天只留一条。
4. **扫描成本与家庭规模同阶**：一次扫描 = 1 次自选查询 + 1 次规则查询 +
   2 次行情查询 + 1 批通知写入，与「有多少家庭」无关；调用方只扫当前家庭。

## 触发时机
站内通知是**懒生成**（`notification_service` 模块 docstring 第 2 条）：读接口里
顺带跑一次扫描即可，不额外起调度器。`GET /api/watchlist/alerts/` 就是这样做的，
与 `strategy_engine.allocation.refresh_reminders` 同一取舍。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from app.domains.watchlist.models import WatchlistAlert, WatchlistAlertSettings, WatchlistItem
from app.services import notification_service
from app.services.alerts import quotes as prices
from app.services.alerts import rules

# ── 家庭设置 ──


def get_settings(db: Session, family_id: int) -> dict[str, dict]:
    """家庭提醒默认口径：库里有用户改过的行就覆盖，缺行用代码默认值补齐。

    返回 `{alert_type: {is_enabled, threshold_value, window_days, level, is_customized}}`。
    `is_customized` 让前端能区分「这是系统默认」与「用户设过」——用户没设过的东西
    不该显示成他设的。
    """
    rows = db.query(WatchlistAlertSettings).filter(WatchlistAlertSettings.family_id == family_id).all()
    stored = {r.alert_type: r for r in rows}
    result: dict[str, dict] = {}
    for alert_type, defaults in rules.DEFAULT_SETTINGS.items():
        row = stored.get(alert_type)
        result[alert_type] = {
            'alert_type': alert_type,
            'is_enabled': bool(row.is_enabled) if row else defaults['is_enabled'],
            'threshold_value': float(row.threshold_value) if row else defaults['threshold_value'],
            'window_days': (row.window_days if row else defaults['window_days']),
            'level': defaults['level'],
            'is_customized': row is not None,
        }
    return result


def update_settings(db: Session, family_id: int, updates: Sequence[dict[str, Any]]) -> dict[str, dict]:
    """更新家庭默认口径（按类型 upsert）；只落「用户确实改过」的类型。"""
    existing = {
        r.alert_type: r
        for r in db.query(WatchlistAlertSettings).filter(WatchlistAlertSettings.family_id == family_id).all()
    }
    for item in updates:
        alert_type = rules.normalize_alert_type(item.get('alert_type', ''))
        if alert_type not in rules.MAGNITUDE_TYPES:
            raise ValueError('到价提醒是逐标的配置，不接受家庭默认值')
        threshold = rules.validate_threshold(alert_type, item.get('threshold_value'))
        window_days = rules.validate_window(item.get('window_days')) if alert_type == rules.ALERT_DRAWDOWN else None
        enabled = bool(item.get('is_enabled', False))
        row = existing.get(alert_type)
        if row is None:
            row = WatchlistAlertSettings(
                family_id=family_id,
                alert_type=alert_type,
                is_enabled=enabled,
                threshold_value=threshold,
                window_days=window_days,
            )
            db.add(row)
            existing[alert_type] = row
        else:
            row.is_enabled = enabled
            row.threshold_value = threshold
            row.window_days = window_days
    db.flush()
    return get_settings(db, family_id)


# ── 逐标的规则 ──


def _owned_item(db: Session, family_id: int, item_id: int) -> Optional[WatchlistItem]:
    """归属校验：不属于本家庭按「不存在」处理（不区分 403/404）。"""
    return db.query(WatchlistItem).filter(WatchlistItem.id == item_id, WatchlistItem.family_id == family_id).first()


def _owned_alert(db: Session, family_id: int, alert_id: int) -> Optional[WatchlistAlert]:
    """规则归属校验：必须经 `watchlist` 关联到本家庭。"""
    return (
        db.query(WatchlistAlert)
        .join(WatchlistItem, WatchlistItem.id == WatchlistAlert.item_id)
        .filter(WatchlistAlert.id == alert_id, WatchlistItem.family_id == family_id)
        .first()
    )


def _alert_to_dict(alert: WatchlistAlert, item: Optional[WatchlistItem] = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        'id': alert.id,
        'item_id': alert.item_id,
        'alert_type': alert.alert_type,
        'threshold_value': float(alert.threshold_value) if alert.threshold_value is not None else None,
        'is_active': bool(alert.is_active),
        'last_triggered_at': alert.last_triggered_at.isoformat() if alert.last_triggered_at else None,
    }
    if item is not None:
        data['symbol'] = item.symbol
        data['name'] = item.name or item.symbol
        data['asset_type'] = item.asset_type
        data['venue'] = item.venue
    return data


def list_alerts(db: Session, family_id: int, *, item_id: Optional[int] = None) -> list[dict[str, Any]]:
    """本家庭的提醒规则（可按标的过滤），带标的展示名供前端直接渲染。"""
    query = (
        db.query(WatchlistAlert, WatchlistItem)
        .join(WatchlistItem, WatchlistItem.id == WatchlistAlert.item_id)
        .filter(WatchlistItem.family_id == family_id)
    )
    if item_id is not None:
        query = query.filter(WatchlistAlert.item_id == item_id)
    rows = query.order_by(WatchlistAlert.item_id, WatchlistAlert.id).all()
    return [_alert_to_dict(alert, item) for alert, item in rows]


def upsert_alert(
    db: Session,
    family_id: int,
    item_id: int,
    *,
    alert_type: str,
    threshold_value: float,
    is_active: bool = True,
) -> dict[str, Any]:
    """新建或覆盖某标的某类型的规则（同标的同类型只留一行，唯一约束兜底）。"""
    item = _owned_item(db, family_id, item_id)
    if item is None:
        raise LookupError('自选记录不存在')
    normalized = rules.normalize_alert_type(alert_type)
    threshold = rules.validate_threshold(normalized, threshold_value)
    row = (
        db.query(WatchlistAlert)
        .filter(WatchlistAlert.item_id == item.id, WatchlistAlert.alert_type == normalized)
        .first()
    )
    if row is None:
        row = WatchlistAlert(item_id=item.id, alert_type=normalized, threshold_value=threshold, is_active=is_active)
        db.add(row)
    else:
        row.threshold_value = threshold
        row.is_active = is_active
        # 重新设置即视为「新的到价线」：清掉上次触发记录，避免历史状态干扰判断
        row.last_triggered_at = None
    db.flush()
    db.refresh(row)
    return _alert_to_dict(row, item)


def update_alert(
    db: Session,
    family_id: int,
    alert_id: int,
    *,
    threshold_value: Optional[float] = None,
    is_active: Optional[bool] = None,
) -> Optional[dict[str, Any]]:
    """改阈值 / 启停；两者都不传等于空操作（仍然做归属校验）。"""
    row = _owned_alert(db, family_id, alert_id)
    if row is None:
        return None
    if threshold_value is not None:
        row.threshold_value = rules.validate_threshold(row.alert_type, threshold_value)
    if is_active is not None:
        row.is_active = bool(is_active)
    db.flush()
    item = db.query(WatchlistItem).filter(WatchlistItem.id == row.item_id).first()
    return _alert_to_dict(row, item)


def delete_alert(db: Session, family_id: int, alert_id: int) -> bool:
    row = _owned_alert(db, family_id, alert_id)
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def get_item_alerts(db: Session, family_id: int, item_id: int) -> Optional[dict[str, Any]]:
    """抽屉用：某标的的规则 + 生效口径 + 最新报价（前端据此提示「现价」）。"""
    item = _owned_item(db, family_id, item_id)
    if item is None:
        return None
    settings = get_settings(db, family_id)
    rows = db.query(WatchlistAlert).filter(WatchlistAlert.item_id == item.id).all()
    by_type = {r.alert_type: r for r in rows}
    window_days = int(settings[rules.ALERT_DRAWDOWN]['window_days'] or 60)
    quote = prices.load_quotes(db, [(item.symbol, item.asset_type)], window_days).get(item.symbol)
    return {
        'item': {
            'id': item.id,
            'symbol': item.symbol,
            'name': item.name or item.symbol,
            'asset_type': item.asset_type,
            'venue': item.venue,
        },
        'rules': [_alert_to_dict(r) for r in rows],
        'effective': _effective_summary(by_type, settings),
        'quote': {
            'latest': quote.latest if quote else None,
            'prev': quote.prev if quote else None,
            'window_high': quote.window_high if quote else None,
            'as_of': quote.as_of.isoformat() if quote and quote.as_of else None,
        },
    }


def _effective_summary(by_type: dict[str, WatchlistAlert], settings: dict[str, dict]) -> dict[str, dict]:
    """把「逐标的规则 + 家庭默认」合成前端可展示的生效口径（含来源）。"""
    summary: dict[str, dict] = {}
    for alert_type in rules.MAGNITUDE_TYPES:
        rule = by_type.get(alert_type)
        family_cfg = settings[alert_type]
        if rule is not None:
            summary[alert_type] = {
                'is_enabled': bool(rule.is_active),
                'threshold_value': float(rule.threshold_value),
                'window_days': family_cfg['window_days'],
                'source': 'item',
            }
        elif family_cfg['is_enabled']:
            summary[alert_type] = {
                'is_enabled': True,
                'threshold_value': family_cfg['threshold_value'],
                'window_days': family_cfg['window_days'],
                'source': 'family',
            }
        else:
            summary[alert_type] = {
                'is_enabled': False,
                'threshold_value': family_cfg['threshold_value'],
                'window_days': family_cfg['window_days'],
                'source': 'off',
            }
    return summary


# ── 扫描与投递 ──


def refresh_alerts(db: Session, family_id: int, *, today: Optional[date] = None) -> dict[str, Any]:
    """跑一次本家庭的提醒扫描并写入站内通知，返回本次统计。

    只在「有规则可比」时才查行情：家庭没有任何提醒配置 ⇒ 一次自选查询就返回，
    不给没开提醒的用户增加任何读成本。
    """
    items = db.query(WatchlistItem).filter(WatchlistItem.family_id == family_id).all()
    if not items:
        return {'evaluated': 0, 'created': 0, 'triggered': []}

    rows = db.query(WatchlistAlert).filter(WatchlistAlert.item_id.in_([item.id for item in items])).all()
    settings = get_settings(db, family_id)
    family_on = _has_family_default(settings)
    if not rows and not family_on:
        return {'evaluated': 0, 'created': 0, 'triggered': []}

    rules_by_item: dict[int, dict[str, WatchlistAlert]] = {}
    for row in rows:
        rules_by_item.setdefault(row.item_id, {})[row.alert_type] = row

    window_days = int(settings[rules.ALERT_DRAWDOWN]['window_days'] or 60)
    quotes = prices.load_quotes(db, [(item.symbol, item.asset_type) for item in items], window_days)

    day = today or date.today()
    candidates: list[dict[str, Any]] = []
    fired: list[WatchlistAlert] = []
    targeted = [item for item in items if item.id in rules_by_item or family_on]
    for item in targeted:
        item_candidates, item_fired = _evaluate_item(item, rules_by_item.get(item.id, {}), settings, quotes, day)
        candidates.extend(item_candidates)
        fired.extend(item_fired)

    created = notification_service.emit_many(db, family_id, candidates)
    if fired:
        stamp = datetime.now()
        for rule in fired:
            rule.is_active = False
            rule.last_triggered_at = stamp
        db.flush()
    return {'evaluated': len(targeted), 'created': created, 'triggered': [r.id for r in fired]}


def _has_family_default(settings: dict[str, dict]) -> bool:
    return any(settings[t]['is_enabled'] for t in rules.MAGNITUDE_TYPES)


def _evaluate_item(
    item: WatchlistItem,
    item_rules: dict[str, WatchlistAlert],
    settings: dict[str, dict],
    quotes: dict[str, prices.SymbolQuote],
    day: date,
) -> tuple[list[dict[str, Any]], list[WatchlistAlert]]:
    """评估单个标的：返回到价触发的规则 + 全部通知候选（不写库）。"""
    quote = quotes.get(item.symbol)
    if quote is None or quote.latest is None:
        return [], []

    display_name = item.name or item.symbol
    as_of = quote.as_of or day
    candidates: list[dict[str, Any]] = []
    fired: list[WatchlistAlert] = []

    for alert_type in rules.PRICE_TYPES:
        rule = item_rules.get(alert_type)
        if rule is None or not rule.is_active:
            continue
        if not rules.price_triggered(alert_type, quote.latest, float(rule.threshold_value)):
            continue
        title, body = rules.price_message(display_name, alert_type, quote.latest, float(rule.threshold_value))
        candidates.append(_candidate(title, body, rules.PRICE_LEVEL, item.symbol, f'price:{rule.id}', as_of))
        fired.append(rule)

    pct_cfg = _effective_magnitude(item_rules.get(rules.ALERT_CHANGE_PCT), settings[rules.ALERT_CHANGE_PCT])
    if pct_cfg is not None:
        pct = rules.change_pct(quote.latest, quote.prev)
        if rules.pct_triggered(pct, pct_cfg['threshold_value']):
            title, body = rules.pct_message(display_name, pct, pct_cfg['threshold_value'], as_of)
            candidates.append(_candidate(title, body, pct_cfg['level'], item.symbol, 'pct', as_of))

    drawdown_cfg = _effective_magnitude(item_rules.get(rules.ALERT_DRAWDOWN), settings[rules.ALERT_DRAWDOWN])
    if drawdown_cfg is not None:
        drawdown = rules.drawdown_pct(quote.latest, quote.window_high)
        if rules.drawdown_triggered(drawdown, drawdown_cfg['threshold_value']):
            window = int(drawdown_cfg['window_days'] or 60)
            title, body = rules.drawdown_message(display_name, drawdown, drawdown_cfg['threshold_value'], window, as_of)
            candidates.append(
                _candidate(title, body, drawdown_cfg['level'], item.symbol, 'dd', rules.weekly_anchor(as_of))
            )

    return candidates, fired


def _effective_magnitude(rule: Optional[WatchlistAlert], family_cfg: dict) -> Optional[dict[str, Any]]:
    """幅度类生效口径：逐标的规则优先（停用即关），否则看家庭默认。"""
    if rule is not None:
        if not rule.is_active:
            return None
        return {
            'threshold_value': float(rule.threshold_value),
            'window_days': family_cfg['window_days'],
            'level': family_cfg['level'],
        }
    if not family_cfg['is_enabled']:
        return None
    return {
        'threshold_value': float(family_cfg['threshold_value']),
        'window_days': family_cfg['window_days'],
        'level': family_cfg['level'],
    }


def _candidate(title: str, body: str, level: str, symbol: str, suffix: str, anchor: date) -> dict[str, Any]:
    """通知候选：去重键 = 来源:标的:锚点（锚点是行情日期 / 周锚点，不是「今天」）。

    用行情日期而不是「今天」：同一份行情跨天不重复提醒（周末看周五的跌幅，
    周一不会被同一条数据再提醒一次）。
    """
    return {
        'level': level,
        'category': rules.NOTIFICATION_CATEGORY,
        'title': title,
        'body': body,
        'dedup_key': notification_service.build_dedup_key('watchlist_alert', f'{symbol}:{suffix}', anchor),
        'source_type': 'watchlist_alert',
        'source_key': symbol,
    }
