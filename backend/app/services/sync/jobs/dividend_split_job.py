# app/services/sync/jobs/dividend_split_job.py
"""
分红 / 送转 / 配股自动抓取与记账（#1179 引入，#541 重写）。

数据源：akshare
- 股票分红送转：`stock_dividend_cninfo`（送股 / 转增 / 派息比例 + 关键日期）
- 股票配股：`stock_pg_em`（配股比例 / 配股价 / 股权登记日 / 缴款期 / 上市日）
- 基金分红：`fund_open_fund_info_em(indicator='分红送配详情')`（每 10 份分红额 + 除息日）
- 基金拆分：`fund_open_fund_info_em(indicator='基金拆分')`

#541 修的是「有链路、但静默丢数据」的三段：
1. 基金分红原先只拿到「公告日期」，`amount` 恒为 0，被导入校验整体剔除——一条都到不了库；
2. 股票同一方案里的「派息」与「送转」被折叠成一条，现金那半分被吞；
3. 配股完全没有实现。

落库仍走 `ImportOrchestrator.commit`，复用手动导入路径（送股关联持仓、import_hash
幂等去重、无持仓时孤儿降级），不新增写入口。

## 幂等键不依赖持有份额（#541 的关键设计）

`compute_record_hash` 默认把 `shares` / `nav` 算进去，而分红/送转的金额恰恰是
「持有份额 × 比例」——用户事后加仓，同一笔分红就会算出一个**新的 hash**，
于是同一事实被记第二遍；反过来更糟：先记了一次 `amount=0` 的脏数据，
正确值永远撞不上同一个 hash，**永久不可自愈**（#1833 踩过这个坑）。

故本 job 给每条流水挂 `transaction_id`（`compute_record_hash` 在有流水号时
只用 `source|transaction_id`），把幂等键钉在**事件本身**：
`除权日|代码|业务类型|比例键`。用户加仓只改变持有份额，不改变事件。
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from app.core.money import Money
from app.core.venues import EXCHANGE, OTC
from app.domains.positions.models import Position, PositionImportMeta
from app.domains.transactions.models import Transaction
from app.services.import_records import StandardTransactionRecord, compute_record_hash
from app.services.importer.orchestrator import ImportOrchestrator
from app.services.job_base import SyncJob

# 事件回看窗口：方案抓的是全history，但只有「最近」的事件才可能有对应持仓变动，
# 太久远的历史方案既算不准也不该补记。留 400 天覆盖年报 + 中期两次分红。
EVENT_LOOKBACK_DAYS = 400

# 分红方式（position_import_meta.dividend_preference，E账户导入时带过来）
_REINVEST_HINTS = ('红利转投', '红利再投', '再投资')


class DividendSplitSyncJob(SyncJob):
    """分红 / 送转 / 配股抓取与记账"""

    def get_name(self) -> str:
        return 'dividend_split'

    @property
    def _allow_empty_data(self) -> bool:
        return True

    # ── 持仓上下文 ──

    def _family_id(self) -> int:
        """本次写入归属的家庭。

        原先两处硬编码 `family_id=1`（全仓仅此文件），多家庭下别人的分红会被记进 1 号家庭。
        口径复用 `position_service._resolve_family_id` 的优先级（显式 > 上下文 > 遗留兜底）。
        """
        return getattr(self, 'family_id', 1)

    def _position_context(self, symbol: str) -> Optional[dict]:
        """该标的的持仓上下文：持有份额 + 归属账户（**ledger_id / Account ID**）。

        **必须带上归属账户**：下游 `process_orphan_dividend/split` 靠它找持仓，为空就
        一条也匹配不上，于是每笔分红都被记成「孤儿」——账上看得见流水、却挂不到持仓，
        也不会重算成本与份额（#541 实测：`imported=1, orphan=1` 正是这个形态）。

        账户键用 `ledger_id` 而不是 `account_name`：`ledgers.name` 是用户随时可改的显示名，
        而 `positions.account_name` 是建仓时抄下的快照字符串。用户改一次账户名，按名字匹配
        就永久失配，且**不抛错**（流水照落，挂不到持仓）；两个账户同名时还会互相串账。
        `ledger_id` 是不变量（`UNIQUE(ledger_id, symbol)` 就是按它定义的）。

        持仓跨多账户时取份额最大的那个账户：分红按账户结算，混记会让单账户口径失真。
        """
        rows = self._position_rows(symbol)
        if rows is None:
            return None
        if not rows:
            return {'shares': Decimal('0'), 'ledger_id': None}
        total = sum(Money.min_unit_to_shares(r.quantity) for r in rows)
        primary = max(rows, key=lambda r: r.quantity or 0)
        return {
            'shares': Decimal(str(total)),
            'ledger_id': primary.ledger_id,
        }

    def _position_rows(self, symbol: str) -> Optional[List[Position]]:
        """该标的的全部持仓行；**查询失败返回 None**（#1833）。

        早先这里 `except Exception: return Decimal('0')`，于是持仓查询一失败就被当成
        「持有 0 股」，直接把 amount=0 的分红流水写进库——而幂等去重之后会把这条
        脏记录当重复跳过，**永久不可自愈**。「查不到」与「确实是 0」必须区分。
        """
        try:
            return self.db.query(Position).filter_by(symbol=symbol, family_id=self._family_id()).all()
        except Exception as e:
            self.logger.warning(f'{symbol} 持仓查询失败，跳过其分红/送转事件：{e}')
            self.stats.setdefault('errors', []).append({'symbol': symbol, 'stage': 'holding_query', 'error': str(e)})
            return None

    def _holding_shares(self, symbol: str) -> Optional[Decimal]:
        ctx = self._position_context(symbol)
        return None if ctx is None else ctx['shares']

    def _is_reinvest(self, symbol: str) -> bool:
        """该标的的默认分红方式是否「红利再投」。

        取 `position_import_meta.dividend_preference`（E 账户导入时带过来的一列）；
        没导入过 / 为空 ⇒ 按现金分红（基金默认方式，也是用户手工记账的既有口径）。
        """
        rows = self._position_rows(symbol)
        if not rows:
            return False
        ids = [p.id for p in rows]
        try:
            metas = self.db.query(PositionImportMeta).filter(PositionImportMeta.position_id.in_(ids)).all()
        except Exception as e:
            self.logger.warning(f'{symbol} 分红方式查询失败，按现金分红处理：{e}')
            return False
        for meta in metas:
            pref = (meta.dividend_preference or '').strip()
            if pref and any(hint in pref for hint in _REINVEST_HINTS):
                return True
        return False

    # ── 抓取 ──

    @staticmethod
    def _asset_type_of(ev: dict) -> str:
        """由**事件来源**判定品种：股票 / 基金。

        不能让 `_is_stock(code)` 独自决定。`000001` 既是平安银行也是华夏成长混合——
        裸 6 位码在股票与基金两个空间里**是同一串数字**，任何按代码段的推断都会有一半判错
        （这与 `core/venues` 里「场外基金代码与交易所代码段共用同一数字空间」是同一个坑）。
        上游不可能搞错自己抓的是什么：`akshare_cninfo` / `akshare_pg` 只有股票有，
        `akshare_fund_*` 只有基金有。
        """
        source = str(ev.get('source') or '')
        if source.startswith('akshare_fund'):
            return 'fund'
        if source in ('akshare_cninfo', 'akshare_pg'):
            return 'stock'
        return 'stock' if DividendSplitSyncJob._is_stock(str(ev.get('symbol') or '')) else 'fund'

    @staticmethod
    def _fetch_as_stock(code: str, positions) -> bool:
        """抓取分流：该抓「股票分红送转 / 配股」还是「基金分红 / 拆分」。

        **以库内持仓的 asset_type 为准**，代码段只作没有持仓时的兜底。
        反例（#541 实测踩到）：`000001` 既是平安银行（股票）也是华夏成长混合（基金），
        裸 6 位码在两个代码空间里是同一串数字——按代码段推断必然有一半判错，
        于是手里是华夏成长，却去抓了平安银行的历年分红。
        数据源和代码段都不认人，只有**用户自己的持仓**知道手里是什么。
        """
        types = {p.asset_type for p in (positions or []) if p.asset_type}
        if len(types) == 1:
            return next(iter(types)) not in ('fund', 'money_fund')
        if types:
            return False  # 同一代码多种 asset_type（脏数据）：认不出就不抓，别猜
        return DividendSplitSyncJob._is_stock(code)

    @staticmethod
    def _is_stock(code: str) -> bool:
        """按代码段的缺省推断（无持仓信息时用；判据见 `_fetch_as_stock`）。

        `normalize()` 返回的市场码是 `SH` / `SZ` / `BJ`，**不是** `CN_A_SH` 那类组合码
        （#541 实测：按旧白名单判断，`SH600000` 会一路落到 else 分支被当成基金，
        于是分红按「每份」算成 0 元并被校验剔除——整类事件静默消失）。
        """
        from app.core.symbol_utils import derive_security_type, get_normalizer, split_symbol

        raw = str(code or '').strip().upper()
        if not raw:
            return False
        norm, mkt, kind = get_normalizer().normalize(raw)
        if kind in ('fund', 'money_fund', 'bond', 'reverse_repo'):
            return False
        if mkt not in ('SH', 'SZ', 'BJ'):
            return False
        bare = norm[-6:] if norm else ''
        market, _ = split_symbol(norm or raw)
        return derive_security_type(bare, market) in ('stock', 'etf')

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        events: List[dict] = []
        stock_bare: List[str] = []
        for code in targets:
            try:
                rows = self._position_rows(code)
                if self._fetch_as_stock(code, rows or []):
                    stock_bare.append(code)
                    events.extend(self.adapter.fetch_stock_dividend(code))
                else:
                    events.extend(self.adapter.fetch_fund_dividend(code))
                    events.extend(self.adapter.fetch_fund_split(code))
            except Exception as e:
                self.logger.warning(f'{code} 分红/送转抓取跳过: {e}')
                self.stats.setdefault('errors', []).append({'code': code, 'error': str(e)})

        # 配股：接口单次返回全市场，**在这里按目标池过滤**，不退化成全库（数据策略 §3）
        if stock_bare and hasattr(self.adapter, 'fetch_stock_rights_issue'):
            try:
                events.extend(self.adapter.fetch_stock_rights_issue(stock_bare))
            except Exception as e:
                self.logger.warning(f'配股方案抓取跳过: {e}')
                self.stats.setdefault('errors', []).append({'stage': 'rights_issue', 'error': str(e)})
        return events

    # ── 转换为统一记录 ──

    @staticmethod
    def _num(value) -> Decimal:
        """上游数值 → Decimal；缺失 / NaN / 无法解析一律 0。

        不能写成 `Decimal(str(value or 0))`：`float('nan')` 是真值，`str(nan)` 得 'nan'，
        `Decimal('nan')` 之后参与比较**不抛错也不为真**（NaN 的一切比较都是 False），
        于是整条事件被静默跳过——上游 NaN 极常见（送股比例为空是常态）。
        """
        if value is None:
            return Decimal('0')
        try:
            d = Decimal(str(value))
        except (ArithmeticError, ValueError):
            return Decimal('0')
        if not d.is_finite():
            return Decimal('0')
        return d

    @staticmethod
    def _event_key(ex_date: date, symbol: str, kind: str, ratio_key: str) -> str:
        """事件幂等键：只由「哪次事件」决定，**不含持有份额**（见模块 docstring）。"""
        return f'{ex_date.isoformat()}|{symbol}|{kind}|{ratio_key}'

    def _build_record(
        self,
        *,
        symbol: str,
        asset_type: str,
        ex_date: date,
        kind: str,
        ratio_key: str,
        name: str = '',
        amount: Decimal = Decimal('0'),
        shares: Decimal = Decimal('0'),
        nav: Decimal = Decimal('0'),
        notes: str = '',
        source: str = 'akshare_dividend',
        ledger_id: Optional[int] = None,
    ) -> StandardTransactionRecord:
        rec = StandardTransactionRecord(
            confirm_date=ex_date,
            asset_type=asset_type,
            symbol=symbol,
            name=name,
            business_type=kind,
            amount=amount,
            shares=shares,
            nav=nav,
            # 账户归属不是可选装饰：下游按 ledger_id + symbol 关联持仓，留空就匹配不上，
            # 分红会被静默降级成孤儿流水（#541）。此处**只给 ledger_id**——账户名可改，
            # 拿它当身份键，用户改个名字这批流水就全挂不上持仓了。
            ledger_id=ledger_id,
            source=source,
        )
        # venue 必须显式声明（#541 / #1662）：`_build_import_data` 在 venue 缺失时按
        # asset_type 推断，`asset_type='fund'` 会被推成 OTC，于是 symbol 被剥掉交易所前缀
        # （`SH600000` → `600000`），下游按 (symbol, ledger_id) 一条也匹配不上，
        # 每笔分红都降级成孤儿流水。股票的除权/配股事件只发生在场内，基金与之相反。
        rec.venue = EXCHANGE if asset_type != 'fund' else OTC
        rec.transaction_id = self._event_key(ex_date, symbol, kind, ratio_key)
        rec.import_hash = compute_record_hash(rec.source, rec)
        # 备注走 raw_text：_build_import_data 的 notes 固定为空串，说明文字只能从这里取
        rec.raw_text = notes
        return rec

    def _events_to_records(self, ev: dict) -> List[StandardTransactionRecord]:
        """一条上游事件 → 0~N 条流水。

        股票混合方案（「10送3股派0.6元」）会拆成两条：现金分红 + 送转股。
        此前折叠成一条，现金那半分被整笔吞掉。
        """
        symbol = ev.get('symbol')
        ex_date = ev.get('ex_date') or ev.get('ann_date')
        if not symbol or not ex_date:
            return []
        if isinstance(ex_date, str):
            try:
                ex_date = date.fromisoformat(ex_date)
            except ValueError:
                return []
        today = date.today()
        if ex_date > today + timedelta(days=1):
            return []  # 未来事件：还没发生，不该记账
        if ex_date < today - timedelta(days=EVENT_LOOKBACK_DAYS):
            return []

        ctx = self._position_context(symbol)
        if ctx is None:
            # 持仓查询失败 ≠ 持有 0 股：写 0 金额流水会被幂等键锁死（#1833）
            return []
        held = ctx['shares']
        acct = {'ledger_id': ctx['ledger_id']}
        asset_type = self._asset_type_of(ev)
        name = ev.get('desc') or ev.get('title') or ''

        records: List[StandardTransactionRecord] = []

        # ① 配股：缴款 + 股份增加，两条流水挂在同一个事件键上
        if ev.get('rights_ratio'):
            ratio = self._num(ev.get('rights_ratio'))
            price = self._num(ev.get('rights_price'))
            if ratio > 0 and price > 0 and held > 0:
                sub_shares = (held * ratio / Decimal('10')).quantize(Decimal('0.0001'))
                amount = (sub_shares * price).quantize(Decimal('0.01'))
                pay_date = ev.get('pay_end') or ev.get('pay_start') or ex_date
                ratio_key = f'10配{ratio}@{price}'
                records.append(
                    self._build_record(
                        symbol=symbol,
                        asset_type=asset_type,
                        ex_date=pay_date,
                        kind='buy',  # 配股缴款 = 按配股价买入，抬高成本、增加份额
                        ratio_key=ratio_key,
                        name=name,
                        amount=amount,
                        shares=sub_shares,
                        nav=price,
                        notes=f'配股缴款 {sub_shares} 股 × {price} 元（{ratio_key}）',
                        source='akshare_rights',
                        **acct,
                    )
                )
                records[-1].raw_op_type = '配股缴款'
            return records

        # ② 基金拆分：每 1 份 → ratio 份，零成本份额增加
        if ev.get('split_ratio'):
            ratio = self._num(ev.get('split_ratio'))
            if ratio > 0 and held > 0:
                add = (held * (ratio - 1)).quantize(Decimal('0.0001'))
                if add > 0:
                    records.append(
                        self._build_record(
                            symbol=symbol,
                            asset_type='fund',
                            ex_date=ex_date,
                            kind='split',
                            ratio_key=f'1:{ratio}',
                            name=name,
                            shares=add,
                            notes=f'基金拆分 1:{ratio}，份额增加 {add}',
                            source='akshare_fund_split',
                            **acct,
                        )
                    )
            return records

        # 上游缺失值用 NaN 表达（pandas），`str(nan)` 会让 Decimal 直接抛 InvalidOperation，
        # 故一律经 _num 收口：非有限值 → 0（「没有这一项」，而非「这一项是 0」）。
        cash_ratio = self._num(ev.get('cash_ratio'))  # 股票：每 10 股派息元
        per_share = self._num(ev.get('per_share'))  # 基金：每 1 份分红元

        # ③ 基金分红：现金分红 / 红利再投
        if per_share > 0:
            amount = (held * per_share).quantize(Decimal('0.01'))
            kind = 'dividend_reinvest' if self._is_reinvest(symbol) else 'dividend_cash'
            rec = self._build_record(
                symbol=symbol,
                asset_type='fund',
                ex_date=ex_date,
                kind=kind,
                ratio_key=f'每份{per_share}',
                name=name,
                amount=amount,
                notes=f'基金分红 每份 {per_share} 元 × {held} 份',
                source='akshare_fund_fh',
                **acct,
            )
            records.append(rec)
            return records

        # ④ 股票现金分红：每 10 股派息
        if cash_ratio > 0:
            amount = (held * cash_ratio / Decimal('10')).quantize(Decimal('0.01'))
            records.append(
                self._build_record(
                    symbol=symbol,
                    asset_type=asset_type,
                    ex_date=ex_date,
                    kind='dividend_cash',
                    ratio_key=f'10派{cash_ratio}',
                    name=name,
                    amount=amount,
                    notes=f'现金分红 10派{cash_ratio}元 × 持有{held}股',
                    **acct,
                )
            )

        # ⑤ 股票送股 / 转增：零成本份额增加（均价自动稀释）
        bonus = self._num(ev.get('bonus_ratio'))
        transfer = self._num(ev.get('transfer_ratio'))
        if bonus > 0 or transfer > 0:
            add = (held * (bonus + transfer) / Decimal('10')).quantize(Decimal('0.0001'))
            if add > 0:
                records.append(
                    self._build_record(
                        symbol=symbol,
                        asset_type=asset_type,
                        ex_date=ex_date,
                        kind='split',
                        ratio_key=f'送{bonus}转{transfer}',
                        name=name,
                        shares=add,
                        notes=f'送转股 10送{bonus}转{transfer} × 持有{held}股，份额增加 {add}',
                        **acct,
                    )
                )
        return records

    # ── 校验 ──

    def _validate_data(self, raw_data: List[dict]) -> List[StandardTransactionRecord]:
        out: List[StandardTransactionRecord] = []
        for ev in raw_data:
            for rec in self._events_to_records(ev):
                # 送转 / 拆分是零成本份额增加，金额天然为 0；只有现金类记录才要求金额 > 0
                if rec.business_type in ('split', 'buy'):
                    if (rec.shares or 0) <= 0:
                        continue
                elif (rec.amount or 0) <= 0:
                    # 金额算不出来（无持仓 / 比例缺失）→ 不落 0 值假流水
                    continue
                out.append(rec)
        return out

    # ── 去重（import_hash 幂等） ──

    def _deduplicate(self, data: List[StandardTransactionRecord]) -> List[StandardTransactionRecord]:
        if not data:
            return []
        seen = set()
        batch_unique = []
        for r in data:
            h = r.import_hash
            if h in seen:
                continue
            seen.add(h)
            batch_unique.append(r)
        hashes = [r.import_hash for r in batch_unique if r.import_hash]
        if not hashes:
            return batch_unique
        existing = set(
            h for (h,) in self.db.query(Transaction.import_hash).filter(Transaction.import_hash.in_(hashes)).all()
        )
        return [r for r in batch_unique if r.import_hash not in existing]

    # ── 落库 ──

    def _save_data(self, new_data: List[StandardTransactionRecord]) -> None:
        if not new_data:
            return
        _ensure_ledger_id(self.db, self._family_id(), new_data)
        orch = ImportOrchestrator(self.db, family_id=self._family_id())
        result = orch.commit(new_data)
        self.logger.info(f'分红/送转/配股落库: imported={result.get("imported")} orphan={result.get("orphan_count")}')
        self.stats.setdefault('detail', []).append(
            {'batch': len(new_data), 'imported': result.get('imported'), 'orphan': result.get('orphan_count')}
        )


def _ensure_ledger_id(db, family_id: int, records: List[StandardTransactionRecord]) -> None:
    """给「无账本」的记录补上该家庭的默认账本。

    `import_hash` 幂等键是 `(ledger_id, import_hash)` 唯一索引 + `COALESCE(ledger_id,-1)`；
    全部用 NULL 时所有自动抓取的分红会挤在同一个 `-1` 哨兵桶里，跨账本也不会重导，
    但读侧按 ledger 过滤就看不见。故能定到账本就定到账本：

    - 有持仓：用持仓所在账本（分红本就属于那个账户）；
    - 没有持仓：孤儿流水落到该家庭最早的账本（与手动记账默认账本同口径）。
    """
    from app.domains.ledgers.models import Ledger

    if all(r.ledger_id is not None for r in records):
        return
    default_ledger = db.query(Ledger).filter_by(family_id=family_id).order_by(Ledger.id.asc()).first()
    pos_ledger: Dict[str, int] = {}
    for rec in records:
        if rec.ledger_id is not None:
            continue
        if rec.symbol not in pos_ledger:
            row = db.query(Position).filter_by(symbol=rec.symbol, family_id=family_id).first()
            if row and row.ledger_id:
                pos_ledger[rec.symbol] = row.ledger_id
            elif default_ledger:
                pos_ledger[rec.symbol] = default_ledger.id
        if rec.symbol in pos_ledger:
            rec.ledger_id = pos_ledger[rec.symbol]
            rec.import_hash = compute_record_hash(rec.source, rec)
