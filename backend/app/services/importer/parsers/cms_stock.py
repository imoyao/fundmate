# -*- coding: utf-8 -*-
"""
招商证券（CMS）历史交割单解析器。

## 策略模式落点

继承 `BaseImportParser`，实现 `parse()` / `validate()`，输出标准
`StandardTransactionRecord`；在 `registry.py` 注册一行即可接入。编排器
（分派 / 哈希 / enrich / 预览 / 落库）、去重口径、前端预览全部复用，
不新增任何分支到 orchestrator。

## 样本事实（2026-11-07 对真实导出文件逐行实证，522 条数据行）

**扩展名是 .xls，内容却不是 Excel BIFF**：文件头是 GB18030 编码的中文字段名 +
制表符，是**制表符分隔的纯文本**。所以：
- 不能用 `pandas.read_excel` 打开（两个引擎都会失败），必须按文本解码；
- 也不能只用 `gbk`：GB18030 是其超集，用 GB18030 一次覆盖全部常用中文；
- 大量单元格是 Excel 公式文本 `="0.0000"` / `="000000000059"`（券商防 Excel
  把代码、金额吃成科学计数法），读值前必须剥掉 `="` 与末尾 `"`。

表头固定 21 列（顺序即列序）：
    币种 / 证券名称 / 成交日期 / 成交价格 / 成交数量 / 发生金额 / 资金余额 /
    剩余数量 / 合同编号 / 流水号 / 业务名称 / 印花税 / 佣金 / 经手费 /
    证管费 / 结算费 / 过户费 / 其他费用 / 证券代码 / 股东代码 / 备注

**尾部空列会被券商导出程序整段截断**：有证券信息的行 20 列、无证券信息的
银行转账行只有 18 列。故一律按列索引补齐到表头长度，不能用 `csv.DictReader`
（缺列会整体错位，把「业务名称」读成费用，且静默不报错）。

## 金额口径（有 161 条买卖行逐行验证的恒等式）

- `发生金额` 是**已扣/已加费用的净额**：卖出为正、买入为负、银行转取为负；
- `成交价格 × 成交数量` 是毛额，且
  `买入: |净额| = 毛额 + 费用` / `卖出: |净额| = 毛额 - 费用`（样本零例外）；
- 沪市可转债（110/111/113/118 段）的「成交数量」单位是**手**，
  1 手 = 10 张（价格按每张报），深市转债（123/127/128 段）与股票是**张/股**。
  实证：`|净额| / |价格×数量|` 在这些代码段恒为 10.00 或 1.00，且补齐 10 倍后
  毛额恒等式 161/161 成立。故本解析器把沪市转债数量换算成「张」再落 `shares`，
  否则 `份额 × 净值` 会差 10 倍，持仓成本与前端「金额不一致」判据全错。
- 费用列为 7 列；标准记录只有 4 个拆分项，映射为
  `佣金 → commission`、`印花税 → stamp_duty`、`过户费+结算费 → transfer_fee`、
  `经手费+证管费+其他费用 → other`，四列之和恒等于聚合 `fee`
  （模型层不变量见 `domains/transactions/models.py:154`）。

## 打新中签：折叠成一行 buy，而不是忽略

打新 6 连行（中签 / 扣款 / 确认缴款 / 扣款回冲 / 托管转出 / 新股入账）交给
`importer/ipo_events.py::IpoEventFolder` 折叠成一条标准 `buy` 记录：本金取组内
净现金流（冲正对自然抵消）、份额取「本金 ÷ 中签价」（天然抹平沪市手/张 10 倍差）。
**不能整体忽略**：样本 6 笔中签对应 6 笔上市后清仓卖出，缺买入时卖出只会落成
`position_id=None` 的孤儿流水，持仓成本与已实现盈亏全错。申购代码与上市代码
不同且交割单内无法可靠关联，故由 `SymbolAliasResolver` 归一；候选不唯一时保留
申购码并写 `link_warning`，让用户在预览页补全，绝不猜、绝不静默丢行。
业务名声明见 `mappings.py::CMS_IPO_*`。

## 刻意不导入的行

报价回购、申购配号见 `mappings.py::CMS_IGNORED_OPS` 的逐条理由。它们不是
「不认识」：有样本、确认过按标准交易入账会算错，故显式忽略并计入
`ignored_row_count`；折叠消耗的行也计入该计数，保证行数对账恒等式
`source_row_count == len(records) + len(errors) + ignored_row_count`（#2854 口径）。
未登记的新业务名一律抛 `CmsUnknownOperation` → 带行号与原文的 `SBImportError`，
绝不静默丢行。

## 隐私

`股东代码` / `资金余额` / `剩余数量` 等账户标识列一律不写入 `raw_text`
或任何落库字段；解析器只取交易事实所需列。测试数据全部为虚构样本。
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

from app.core import database
from app.core.config import IMPORTER__EASTMONEY_ALIAS
from app.core.constants import CASH_SYMBOL, PositionSource
from app.core.symbol_utils import get_normalizer
from app.core.venues import EXCHANGE
from app.services.import_records import SBImportError, StandardTransactionRecord
from app.services.importer.base import BaseImportParser
from app.services.importer.eastmoney_alias_resolver import EastMoneyAliasResolver
from app.services.importer.ipo_events import (
    IpoEventFolder,
    IpoEventPolicy,
    IpoRow,
    to_decimal,
)
from app.services.importer.mappings import (
    CMS_CASH_TRANSFER_OPS,
    CMS_IGNORED_OPS,
    CMS_IPO_ANCHOR_OPS,
    CMS_IPO_CASH_OPS,
    CMS_IPO_CREDIT_OPS,
    CMS_IPO_LISTED_CODE_PREFIXES,
    CMS_IPO_MEMBER_OPS,
    CMS_IPO_PRICE_OP,
    CMS_NO_CODE_INCOME_ASSET_TYPES,
    CMS_OP_MAP,
    VALID_OP_TYPES,
)
from app.services.importer.utils import parse_date


class CmsIgnoredOperation(Exception):
    """白名单内的非交易行 / 空行：有意忽略，不报错，但计入行数对账。"""


class CmsUnknownOperation(Exception):
    """未登记的业务名：必须报错并带出券商原文，不能静默丢行。"""

    def __init__(self, op: str):
        self.op = op
        super().__init__(op)


def _is_likely_new_stock_ipo(op: str) -> bool:
    """疑似「新股申购中签」的业务名（无样本时的保守判定）。

    只影响**错误提示的措辞**，不参与任何数据口径：即使判错，最坏结果是文案多一句
    解释，不会产出错记录。判据取「含中签」，或「含申购且含缴款」——已登记的转债
    打新业务名在 `folder.owns()` 就被折叠器接管了，走到这里的必然是未登记项。

    拿到真实新股交割单后，应改为显式业务名清单（同 `CMS_IPO_*` 的做法），
    并把新股纳进正式的折叠口径。
    """
    return '中签' in op or ('申购' in op and '缴款' in op)


# 招商打新链的事件声明；折叠逻辑在 ipo_events.py，换券商只需换这张表。
CMS_IPO_POLICY = IpoEventPolicy(
    platform='cms_stock',
    anchor_ops=CMS_IPO_ANCHOR_OPS,
    member_ops=CMS_IPO_MEMBER_OPS,
    cash_ops=CMS_IPO_CASH_OPS,
    credit_ops=CMS_IPO_CREDIT_OPS,
    price_op=CMS_IPO_PRICE_OP,
)


class CMSStockParser(BaseImportParser):
    """招商证券历史交割单解析器（source='cms_stock'）。"""

    source = PositionSource.BROKER_CMS.value
    venue = EXCHANGE  # 交割单覆盖的是沪深场内证券

    # 文件是 GB18030 文本；UTF-8 优先是为了兼容用户自行另存的 UTF-8 版本。
    # 不用基类的 _decode_bytes（只试 gbk），GB18030 是 gbk 超集、一次覆盖更稳。
    ENCODINGS: Tuple[str, ...] = ('utf-8-sig', 'gb18030')

    # 表头识别：前 20 行内找同时含这三个列名的行。刻意不含「业务名称」——
    # 它是必填列之一，缺它时应走「缺少必要列」报出具体列名，而不是笼统报「未找到表头」。
    HEADER_MARKERS = ('成交日期', '成交价格', '发生金额')
    HEADER_SCAN_LINES = 20

    # 缺一列即判定「选错模板」，明确报错而不是解析出一堆错位数据。
    REQUIRED_COLUMNS = (
        '币种',
        '证券名称',
        '成交日期',
        '成交价格',
        '成交数量',
        '发生金额',
        '合同编号',
        '流水号',
        '业务名称',
        '证券代码',
    )

    # 招商交割单的 7 个费用明细列；缺任一列则不拆分（四列全 None）。
    FEE_SOURCE_COLUMNS = ('印花税', '佣金', '经手费', '证管费', '结算费', '过户费', '其他费用')

    # 沪市可转债「手 → 张」换算（1 手 = 10 张，价格按每张报价）。
    SH_CONVERTIBLE_BOND_LOT_PREFIXES = ('110', '111', '113', '118')
    LOT_TO_SHEET = Decimal('10')

    SUPPORTED_CURRENCIES = frozenset({'', '人民币'})

    def __init__(self, alias_resolver=None):
        self.normalizer = get_normalizer()
        # 申购代码 → 上市代码。默认接入东财引导的持久化别名解析器（默认开启，可由
        # IMPORTER__EASTMONEY_ALIAS=0 关闭）；离线/抖动时回落 link_warning，不阻断导入。
        # 测试可显式传入 NullAliasResolver / InMemoryAliasResolver 以隔离网络。
        #
        # 会话入口用 `database.get_session`（#1608）：不能 `from ... import SessionLocal`
        # 后在模块级绑进默认参数——那是早绑定，测试重定向会话时补丁会静默失效。
        self.alias_resolver = alias_resolver or EastMoneyAliasResolver(
            session_factory=database.get_session, enabled=IMPORTER__EASTMONEY_ALIAS
        )
        # #2854 行数对账：每次 parse() 覆盖，由 orchestrator 在同一次调用链内取走。
        self.source_row_count: Optional[int] = None
        self.ignored_row_count: int = 0
        # 观测值：打新折叠出的建仓事件数 / 其中代码待补全数（供预览与后续自动化）。
        self.folded_event_count: int = 0
        self.pending_alias_count: int = 0

    # ── 解析主流程 ──

    def parse(self, file_bytes: bytes) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        records: List[StandardTransactionRecord] = []
        errors: List[SBImportError] = []
        self.source_row_count = None
        self.ignored_row_count = 0
        self.folded_event_count = 0
        self.pending_alias_count = 0

        rows = self._read_rows(file_bytes)
        if rows is None:
            errors.append(SBImportError(0, None, '无法识别文件编码，请将文件另存为 UTF-8 或 GBK 文本后重新上传'))
            return records, errors

        header_idx, header = self._locate_header(rows)
        if header is None:
            errors.append(
                SBImportError(
                    0,
                    None,
                    f'未找到表格表头（需包含 {" / ".join(self.HEADER_MARKERS)}），请确认上传的是招商证券历史交割单',
                )
            )
            return records, errors

        missing = [c for c in self.REQUIRED_COLUMNS if c not in header]
        if missing:
            errors.append(
                SBImportError(0, None, f'缺少必要列: {", ".join(missing)}。请确认上传的是招商证券历史交割单导出文件')
            )
            return records, errors

        fee_split = all(c in header for c in self.FEE_SOURCE_COLUMNS)
        data_rows = rows[header_idx + 1 :]
        self.source_row_count = len(data_rows)

        # 打新链按「事件」收集，不逐行产流水；finalize 时折叠成标准 buy 记录。
        folder = IpoEventFolder(
            CMS_IPO_POLICY,
            resolver=self.alias_resolver,
            normalizer=self.normalizer,
            source=self.source,
            listed_code_prefixes=CMS_IPO_LISTED_CODE_PREFIXES,
        )

        ignored = 0
        for offset, cells in enumerate(data_rows):
            line_num = header_idx + offset + 2
            row = self._row_to_dict(header, cells)
            op = self._text(row, '业务名称')
            if folder.owns(op):
                try:
                    folder.collect(self._ipo_row(row, op, line_num))
                except Exception as e:  # 单行失败不中断整批（基类契约）
                    errors.append(SBImportError(line_num, None, f'打新中签行解析失败: {e}'))
                continue
            try:
                record = self._parse_row(row, fee_split)
                if record is not None:
                    records.append(record)
            except CmsIgnoredOperation:
                ignored += 1
            except CmsUnknownOperation as e:
                errors.append(
                    SBImportError(
                        line_num,
                        '业务名称',
                        self._unknown_op_message(e.op),
                        raw_value=e.op,
                    )
                )
            except Exception as e:  # 单行失败不中断整批（基类契约）
                errors.append(SBImportError(line_num, None, f'行解析失败: {e}'))

        folded, folded_errors, consumed = folder.finalize()
        records.extend(folded)
        errors.extend(folded_errors)
        # 折叠消耗的行也计入 ignored：恒等式 #2854 保持不变。
        ignored += consumed
        self.folded_event_count = len(folder.events)
        self.pending_alias_count = len(folder.pending_alias)
        self.ignored_row_count = ignored
        return records, errors

    # ── 文件读取 ──

    def _read_rows(self, file_bytes: bytes) -> Optional[List[List[str]]]:
        """按编码解码成二维文本行；完全空白行不计入数据行。"""
        for enc in self.ENCODINGS:
            try:
                text = file_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
            rows = [line.split('\t') for line in text.splitlines() if line.strip()]
            if rows:
                return rows
        return None

    def _locate_header(self, rows: List[List[str]]) -> Tuple[Optional[int], Optional[List[str]]]:
        for idx, cells in enumerate(rows[: self.HEADER_SCAN_LINES]):
            header = [self._clean_cell(c) for c in cells]
            if all(marker in header for marker in self.HEADER_MARKERS):
                return idx, header
        return None, None

    @staticmethod
    def _clean_cell(value: str) -> str:
        """剥离 BOM、首尾空白与券商防科学计数法的 Excel 公式文本外壳 `="..."`。"""
        text = (value or '').strip().lstrip('\ufeff')
        if len(text) >= 3 and text.startswith('="') and text.endswith('"'):
            text = text[2:-1]
        return text.strip()

    @classmethod
    def _row_to_dict(cls, header: List[str], cells: List[str]) -> dict:
        """按列索引对齐；尾部被截断的列补空串，多余列忽略。"""
        padded = (cells + [''] * len(header))[: len(header)]
        return {name: cls._clean_cell(value) for name, value in zip(header, padded)}

    # ── 行解析 ──

    def _ipo_row(self, row: dict, op: str, line_no: int) -> IpoRow:
        """只传交易事实字段给折叠器；账户标识列（股东代码/资金余额/备注）不进入。"""
        return IpoRow(
            line_no=line_no,
            op=op,
            code=self._text(row, '证券代码'),
            name=self._text(row, '证券名称'),
            trade_date=self._parse_trade_date(row),
            price=to_decimal(row.get('成交价格')),
            quantity=to_decimal(row.get('成交数量')),
            amount=to_decimal(row.get('发生金额')),
        )

    def _parse_row(self, row: dict, fee_split: bool) -> StandardTransactionRecord:
        op = self._text(row, '业务名称')
        if not op:
            raise CmsIgnoredOperation()  # 空行 / 汇总行
        if op in CMS_IGNORED_OPS:
            raise CmsIgnoredOperation()

        trade_date = self._parse_trade_date(row)
        currency = self._text(row, '币种')
        if currency not in self.SUPPORTED_CURRENCIES:
            # 项目无汇率换算能力；按人民币入账等于算错，宁可显式报错。
            raise ValueError(f'不支持的结算币种: {currency}')

        if op in CMS_CASH_TRANSFER_OPS:
            return self._parse_cash_transfer(row, op, trade_date)

        business_type = CMS_OP_MAP.get(op)
        if business_type is None:
            raise CmsUnknownOperation(op)
        if business_type not in VALID_OP_TYPES:
            raise ValueError(f'不支持的业务类型: {op}')

        symbol_raw = self._text(row, '证券代码')
        name = self._text(row, '证券名称')
        net = self._decimal(row.get('发生金额'))
        fee, breakdown = self._parse_fee(row, fee_split)

        # 无代码收益行（利息归本）：券商原文就不给标的，用系统现金占位符，
        # 否则前端判「代码未匹配」，这笔真实收益永远勾不上。
        if not symbol_raw and op in CMS_NO_CODE_INCOME_ASSET_TYPES:
            asset_type = CMS_NO_CODE_INCOME_ASSET_TYPES[op]
            symbol = CASH_SYMBOL
            suggested_type = None
        else:
            try:
                normalized, _, suggested_type = self.normalizer.normalize(symbol_raw, venue=EXCHANGE)
            except Exception:
                normalized, suggested_type = None, None
            symbol = normalized or symbol_raw
            asset_type = suggested_type or 'stock'

        quantity = abs(self._decimal(row.get('成交数量')))
        price = abs(self._decimal(row.get('成交价格')))
        factor = self.LOT_TO_SHEET if symbol_raw[:3] in self.SH_CONVERTIBLE_BOND_LOT_PREFIXES else Decimal('1')
        shares = quantity * factor
        gross = price * quantity * factor

        return StandardTransactionRecord(
            confirm_date=trade_date,
            trade_date=trade_date,
            asset_type=asset_type,
            symbol=symbol,
            name=name or symbol or op,
            business_type=business_type,
            amount=abs(net),
            account_name='',  # enrich 阶段由前端所选账户回填
            shares=shares,
            nav=price,
            fee=fee,
            fee_commission=breakdown[0],
            fee_stamp_duty=breakdown[1],
            fee_transfer_fee=breakdown[2],
            fee_other=breakdown[3],
            transaction_id=self._transaction_id(row, op, trade_date),
            source=self.source,
            raw_op_type=op,
            venue=EXCHANGE,
            # 招商不提供「成交金额」列，毛额由 价格×数量（含手→张换算）算出，
            # 已用 161 条买卖行验证其等于 |发生金额| ± 费用。
            trade_amount=gross,
            # commit 链路对 cash / 银证转账行按 abs(net_amount) 入账，必须给值（不能留 0）。
            net_amount=abs(net),
        )

    def _parse_cash_transfer(self, row: dict, op: str, trade_date: date) -> StandardTransactionRecord:
        net = self._decimal(row.get('发生金额'))
        if net == 0:
            raise ValueError(f'资金划转「{op}」的发生金额为 0')
        return StandardTransactionRecord(
            confirm_date=trade_date,
            trade_date=trade_date,
            asset_type='cash',
            symbol=CASH_SYMBOL,
            name=op,
            business_type='deposit' if net > 0 else 'withdraw',
            amount=abs(net),
            account_name='',
            transaction_id=self._transaction_id(row, op, trade_date),
            source=self.source,
            raw_op_type=op,
            venue='',  # 银证转账不发生在交易场所
            net_amount=abs(net),
        )

    # ── 辅助 ──

    @staticmethod
    def _unknown_op_message(op: str) -> str:
        """未登记业务名的报错文案。

        新股申购中签与「不认识的新业务」是两种性质：前者我们能说清原因与补救方式，
        后者只能说「未登记」。分开写，用户才知道下一步该干什么——而不是被
        「无法识别」误导成「文件有问题」。
        """
        if _is_likely_new_stock_ipo(op):
            return (
                f'业务名「{op}」属于新股申购中签，当前版本仅支持可转债打新，该行未纳入导入；'
                '请在「完整记账 → 证券买入」中手动补录这笔建仓：'
                '标的填上市代码，价格填中签价（发行价），份额填中签数量；'
                '否则日后卖出会找不到成本'
            )
        return f'无法识别的业务名称「{op}」，该行未纳入导入'

    @staticmethod
    def _text(row: dict, key: str) -> str:
        value = row.get(key, '')
        return value.strip() if isinstance(value, str) else str(value or '').strip()

    @staticmethod
    def _decimal(value) -> Decimal:
        """数值字符串 → Decimal；空 / 占位符 / 非法值一律为 0，不抛异常。"""
        if value is None:
            return Decimal('0')
        text = str(value).strip().replace(',', '')
        if not text or text in ('-', '--', '/', '—', 'nan', 'None'):
            return Decimal('0')
        try:
            return Decimal(text)
        except (InvalidOperation, ValueError):
            return Decimal('0')

    @classmethod
    def _parse_fee(cls, row: dict, fee_split: bool) -> Tuple[Decimal, Tuple]:
        """返回 (聚合 fee, (佣金, 印花税, 过户费, 其他))；不可拆分时四元组全 None。"""
        values = {col: cls._decimal(row.get(col)) for col in cls.FEE_SOURCE_COLUMNS}
        fee = sum(values.values(), Decimal('0'))
        if not fee_split:
            return fee, (None, None, None, None)
        return fee, (
            values['佣金'],
            values['印花税'],
            values['过户费'] + values['结算费'],
            values['经手费'] + values['证管费'] + values['其他费用'],
        )

    def _parse_trade_date(self, row: dict) -> date:
        raw = self._text(row, '成交日期')
        parsed = parse_date(raw)
        if parsed is None:
            raise ValueError(f'无效的成交日期: {raw}')
        return parsed

    @classmethod
    def _transaction_id(cls, row: dict, op: str, trade_date: date) -> str:
        """幂等键。

        带日期与业务名两个维度：同一流水号在打新流程里会被多行共用（样本中
        (日期, 流水号) 522 行只有 510 个不同值，(日期, 流水号, 业务名) 则是 522/522）。
        流水号缺失时回落合同编号；两者皆无则返回空串，由编排器走内容哈希去重。
        """
        serial = cls._text(row, '流水号') or cls._text(row, '合同编号')
        if not serial or serial == '0':
            return ''
        return f'{trade_date:%Y%m%d}-{serial}-{op}'

    # ── 校验 ──

    def validate(
        self, records: List[StandardTransactionRecord]
    ) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        valid: List[StandardTransactionRecord] = []
        errors: List[SBImportError] = []
        for i, record in enumerate(records):
            line_num = i + 2
            if not record.symbol:
                errors.append(SBImportError(line_num, 'symbol', '证券代码不能为空'))
            elif record.amount == Decimal('0'):
                errors.append(SBImportError(line_num, 'amount', '金额不能为0'))
            else:
                valid.append(record)
        return valid, errors
