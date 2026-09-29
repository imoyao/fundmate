# -*- coding: utf-8 -*-
"""PositionOut 必须透出 is_money_fund 三态（#1305 #11）。

背景：`positions.is_money_fund` 列（#863 引入）早已落库、迁移与三态查询也都已收口
（`is_money_fund.is_(True)`），但 **Out Schema 没声明该字段** —— Pydantic 的
`model_validate` 会把它静默丢掉，接口响应里根本看不到，前端也就无从按货基筛选。

三态语义：True=货基 / False=非货基 / None=**未判定**。None 绝不能被压成 False。
"""


def test_position_out_declares_tristate_field() -> None:
    from app.domains.positions.schemas import PositionOut

    assert 'is_money_fund' in PositionOut.model_fields, 'Out Schema 未声明 is_money_fund'
    field = PositionOut.model_fields['is_money_fund']
    assert field.default is None, '缺省必须是 None（未判定），不是 False'


def test_position_out_preserves_each_state(db, make_position) -> None:
    """核心回归（#11）：三种取值都要原样透出，且 None 不能塌成 False。"""
    from app.domains.positions.schemas import PositionOut

    cases = [
        (True, True),
        (False, False),
        (None, None),  # 未判定 —— 压成 False 就在这里被抓到
    ]
    for raw, expected in cases:
        pos = make_position(
            symbol='000198',
            name='天弘余额宝',
            market='SH',
            asset_type='fund',
            quantity=100.0,
            avg_price=1.0,
            current_price=1.0,
            is_money_fund=raw,
        )
        dumped = PositionOut.model_validate(pos).model_dump()
        assert 'is_money_fund' in dumped, '接口响应里丢了 is_money_fund'
        assert dumped['is_money_fund'] is expected, f'落库 {raw} → 透出 {dumped["is_money_fund"]}'
