# -*- coding: utf-8 -*-
"""行情回补深度口径（#2860）的判据测试。

两处最容易写错、且写错后**不会报错**的地方：

1. `desired_start` 的两个上界取**更早**的那个，且保底是 5 年——只补到「首笔那年」会让
   走势卡的 5Y 档对 2023 年买入的标的一律降级；反过来只给 5 年，则 2010 年买入的标的
   又缺前半段。两个方向都不会抛异常，只是曲线从中间开始。
2. `first_transaction_dates` 的身份键归一。直接拿 `price_history.symbol`（`SH600383`）
   去比 `transactions.symbol_norm`（`EXCHANGE:SH600383`）一条都命中不了，于是所有标的
   都被判成「无流水」、一律退回 5 年保底——看起来正常，老标的永远补不上。
"""

from datetime import date, datetime, timedelta

from app.services.price_depth import (
    BASELINE_HISTORY_YEARS,
    FIRST_TXN_BUFFER_DAYS,
    desired_start,
    first_transaction_dates,
)


class TestDesiredStart:
    def test_first_txn_older_than_five_years_wins(self):
        """首笔早于 5 年 ⇒ 按首笔走（用户口径：2010 年买的就补到 2010）。"""
        start = desired_start(date(2010, 1, 5), date(2026, 11, 3))
        assert start == date(2010, 1, 5) - timedelta(days=FIRST_TXN_BUFFER_DAYS)

    def test_first_txn_within_baseline_still_gets_five_years(self):
        """首笔在 5 年内 ⇒ 仍保底 5 年。

        这一条最容易被「首笔优先」的直觉写错：2023 年买入的标的若只补到 2023，
        走势卡的 5Y 档对它永远降级——用户点得到却看不到。深度是「建仓档」与
        「5Y 档」两个消费者的**并集**，不是只伺候前者。
        """
        assert desired_start(date(2023, 2, 17), date(2026, 11, 3)) == date(2021, 11, 3)

    def test_falls_back_to_baseline_when_first_txn_is_recent(self):
        """首笔很新 ⇒ 仍是 5 年保底，不因为「刚买」只给几天。"""
        assert desired_start(date(2026, 10, 20), date(2026, 11, 3)) == date(2021, 11, 3)

    def test_no_transaction_gets_baseline(self):
        """纯自选 / 无流水：只剩保底，且必须是**具体日期**（None 在适配器里会退化）。"""
        assert desired_start(None, date(2026, 11, 3)) == date(2026 - BASELINE_HISTORY_YEARS, 11, 3)

    def test_earlier_of_the_two_bounds(self):
        """两个上界始终取更早者——用一对「首笔落在保底外侧 / 内侧」的数据把这条钉住。"""
        today = date(2026, 11, 3)
        assert desired_start(date(2020, 1, 1), today) < date(2021, 11, 3)
        assert desired_start(date(2024, 1, 1), today) == date(2021, 11, 3)

    def test_leap_day_baseline_does_not_raise(self):
        """2/29 往前 5 年落到平年：必须收敛到 2/28，而不是抛 ValueError。"""
        assert desired_start(None, date(2024, 2, 29)) == date(2019, 2, 28)


class TestFirstTransactionDates:
    @staticmethod
    def _position(make_position, symbol):
        return make_position(symbol=symbol, name=symbol, quantity=100, avg_price=1.0)

    def test_matches_exchange_norm(self, db, make_position, make_transaction):
        """`SH600383` 能命中 `EXCHANGE:SH600383` 形态的 symbol_norm。"""
        pos = self._position(make_position, 'SH600383')
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            symbol='SH600383',
            txn_type='buy',
            asset_type='stock',
            trade_date=datetime(2023, 5, 23, 10, 0, 0),
        )
        db.commit()

        assert first_transaction_dates(db, ['SH600383']) == {'SH600383': date(2023, 5, 23)}

    def test_matches_bare_code_via_exchange_identity(self, db, make_position, make_transaction):
        """裸码 `600383` 也应命中：调用方可能只拿到裸码，漏掉就等于「无流水」。"""
        pos = self._position(make_position, 'SH600383')
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            symbol='SH600383',
            txn_type='buy',
            asset_type='stock',
            trade_date=datetime(2023, 5, 23, 10, 0, 0),
        )
        db.commit()

        assert first_transaction_dates(db, ['600383']) == {'600383': date(2023, 5, 23)}

    def test_matches_norm_even_when_literal_symbol_is_blank(self, db, make_position, make_transaction):
        """`symbol` 为空、只有 `symbol_norm` 完整的行也必须命中。

        真库有 259 笔这样的存量（#2856 之前的卖出/分红流水 symbol 为空，symbol_norm
        已回填）。只按字面量比对时它们一律「查不到流水」，于是这些标的的深度退回
        5 年保底——不报错、不告警，老标的的前缀永远补不上。这条用例就是那个盲区的
        唯一探针：字面量与身份键**必须不一致**才有区分度。
        """
        from sqlalchemy import text

        pos = self._position(make_position, 'SH600383')
        txn = make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            symbol='SH600383',
            txn_type='sell',
            asset_type='stock',
            trade_date=datetime(2023, 5, 23, 10, 0, 0),
        )
        db.commit()
        # 绕过 mapper 事件直接清空字面量，模拟存量行（再 commit 会被重新填回）
        db.execute(text('UPDATE transactions SET symbol = :s WHERE id = :i'), {'s': '', 'i': txn.id})
        db.commit()

        assert first_transaction_dates(db, ['SH600383']) == {'SH600383': date(2023, 5, 23)}

    def test_takes_earliest_across_trade_and_confirm_date(self, db, make_position, make_transaction):
        """多笔取最早；`trade_date` 缺失的那笔用 `confirm_date` 兜底。"""
        pos = self._position(make_position, 'SH600383')
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            symbol='SH600383',
            txn_type='buy',
            asset_type='stock',
            trade_date=datetime(2024, 3, 1, 10, 0, 0),
        )
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            symbol='SH600383',
            txn_type='buy',
            asset_type='stock',
            allow_null_trade_date=True,
            confirm_date=date(2023, 5, 23),
        )
        db.commit()

        assert first_transaction_dates(db, ['SH600383']) == {'SH600383': date(2023, 5, 23)}

    def test_does_not_cross_venues(self, db, make_position, make_transaction):
        """场外 `OTC:004369` 不得被当成场内同码标的的首笔——串场会把深度按错的日期算。"""
        pos = self._position(make_position, 'OTC:004369')
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            symbol='004369',
            txn_type='buy',
            asset_type='fund',
            trade_date=datetime(2023, 1, 5, 10, 0, 0),
        )
        db.commit()

        assert first_transaction_dates(db, ['004369']) == {'004369': date(2023, 1, 5)}
        assert first_transaction_dates(db, ['SH600383']) == {}

    def test_empty_symbol_is_skipped(self, db):
        """空写法不进结果集（历史脏数据的 symbol_norm 是空串，归不到任何标的）。"""
        assert first_transaction_dates(db, ['', None]) == {}
