# -*- coding: utf-8 -*-
"""
同花顺股票交割单解析器。

完整迁移旧 TransactionParser 的同花顺逻辑，独立实现 parse() 和 validate()。
"""

import decimal
import io
import math
import re
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple

import pandas as pd
from loguru import logger

from app.core.constants import CASH_SYMBOL, PositionSource
from app.core.symbol_utils import get_normalizer
from app.core.venues import EXCHANGE, OTC
from app.services.import_records import SBImportError, StandardTransactionRecord
from app.services.importer.base import BaseImportParser
from app.services.importer.mappings import THS_OP_MAP, THS_OTC_OPS, VALID_OP_TYPES


class THSStockParser(BaseImportParser):
    """同花顺股票交割单解析器"""

    source = PositionSource.BROKER_THS.value

    def __init__(self):
        self.normalizer = get_normalizer()

    # ── 解析 ──

    def parse(self, file_bytes: bytes) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        """解析同花顺交割单文件"""
        records = []
        errors = []

        # 1. 读取文件为 DataFrame
        df = self._read_file_to_dataframe(file_bytes)
        if df is None:
            errors.append(SBImportError(0, None, '无法自动识别文件编码，请将文件另存为 UTF-8 编码的 CSV 后重新上传'))
            return records, errors

        if df.empty:
            errors.append(SBImportError(0, None, '文件中未找到有效数据'))
            return records, errors

        # 2. 校验必填列
        col_errors = self._validate_required_columns(df)
        if col_errors:
            errors.extend(col_errors)
            return records, errors

        # 3. 预处理 DataFrame（合同编号格式化、费用合并）
        self._preprocess_dataframe(df)

        # 4. 逐行解析
        records, row_errors = self._iterrows_to_records(df)

        # 配对（兑息+税 / 兑付+股份转出）不在这里做：它按 business_type 收集角色，
        # 对所有平台解析器一致，统一由 orchestrator 在解析完成后跑（importer/linking.py）。
        errors.extend(row_errors)

        return records, errors

    # ── 文件读取 ──

    def _read_file_to_dataframe(self, file_bytes: bytes) -> Optional[pd.DataFrame]:
        # 1. Excel 优先
        for engine in ['openpyxl', 'xlrd']:
            try:
                df = pd.read_excel(io.BytesIO(file_bytes), engine=engine)
                if df is not None and not df.empty:
                    return df
            except Exception:
                continue

        # 2. 同花顺文件固定为制表符分隔，优先 utf-8-sig，其次 gbk
        for enc in ['utf-8-sig', 'gbk']:
            try:
                df = pd.read_csv(
                    io.BytesIO(file_bytes),
                    sep='\t',
                    encoding=enc,
                    encoding_errors='ignore',
                    dtype={'证券代码': str, '合同编号': str},
                )
                if df.empty:
                    continue
                df.dropna(how='all', inplace=True)
                df.columns = df.columns.str.strip()
                if any(self._contains_chinese(col) for col in df.columns):
                    return df
            except Exception:
                continue

        # 3. 极少数情况尝试逗号分隔（仅一次）
        try:
            df = pd.read_csv(
                io.BytesIO(file_bytes),
                sep=',',
                encoding='utf-8-sig',
                encoding_errors='ignore',
                dtype={'证券代码': str, '合同编号': str},
            )
            if not df.empty:
                df.dropna(how='all', inplace=True)
                df.columns = df.columns.str.strip()
                if any(self._contains_chinese(col) for col in df.columns):
                    return df
        except Exception:
            pass

        # 4. HTML 兜底
        for enc in ['utf-8', 'gbk']:
            try:
                dfs = pd.read_html(io.BytesIO(file_bytes), encoding=enc)
                if dfs:
                    df = dfs[0]
                    df.columns = df.columns.str.strip()
                    if any(self._contains_chinese(col) for col in df.columns):
                        return df
            except Exception:
                continue

        return None

    @staticmethod
    def _contains_chinese(text: str) -> bool:
        """检测字符串是否包含中文字符"""
        return bool(re.search(r'[\u4e00-\u9fff]', text))

    # ── 列校验与预处理 ──

    def _validate_required_columns(self, df: pd.DataFrame) -> List[SBImportError]:
        """检查必填列是否存在"""
        required = ['证券代码', '操作', '成交数量', '成交均价', '交收日期']
        missing = [c for c in required if c not in df.columns]
        if missing:
            return [SBImportError(0, None, f'缺少必要列: {", ".join(missing)}。请确认上传的是同花顺历史交割单导出文件')]
        return []

    def _preprocess_dataframe(self, df: pd.DataFrame) -> None:
        # 合同编号格式化
        if '合同编号' in df.columns:
            df['合同编号'] = df['合同编号'].apply(self._format_contract_id)
        # 清理证券代码的 Excel 浮点后缀（仅去掉 ".0"，保留末尾零）
        if '证券代码' in df.columns:
            df['证券代码'] = df['证券代码'].apply(lambda x: re.sub(r'\.0$', '', str(x)) if pd.notna(x) else '')
        # 费用合并
        fee_cols = ['佣金', '印花税', '过户费', '其他杂费']
        available_fee = [c for c in fee_cols if c in df.columns]
        if available_fee:
            df['fee'] = df[available_fee].apply(
                lambda row: sum(float(v) for v in row if pd.notna(v) and str(v).strip() not in ('', '0')),
                axis=1,
            )
        else:
            df['fee'] = 0.0

    # ── 逐行解析 ──

    def _iterrows_to_records(self, df: pd.DataFrame) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        """遍历 DataFrame 行，调用 _parse_row 解析"""
        records = []
        errors = []
        for idx, raw_dict in enumerate(df.to_dict('records')):
            line_num = idx + 2
            try:
                record = self._parse_row(raw_dict, line_num)
                if record:
                    records.append(record)
            except Exception as e:
                errors.append(SBImportError(line_num, None, f'行解析失败: {str(e)}'))
        return records, errors

    @staticmethod
    def _safe_str(raw: dict, key: str, default: str = '') -> str:
        """安全获取字典值，将 NaN 或字符串 'nan' 统一返回默认值"""
        val = raw.get(key, default)
        if isinstance(val, float) and math.isnan(val):
            return default
        if isinstance(val, str) and val.strip().lower() == 'nan':
            return default
        return str(val).strip()

    @staticmethod
    def _safe_decimal(raw_val: float) -> Decimal:
        """将浮点数安全转为 Decimal，NaN/Inf 转为 0"""
        try:
            if math.isnan(raw_val) or math.isinf(raw_val):
                return Decimal('0')
            return Decimal(str(raw_val))
        except (decimal.InvalidOperation, ValueError):
            return Decimal('0')

    @staticmethod
    def _safe_float(raw: dict, key: str, default: float = 0.0) -> float:
        """安全获取浮点值，NaN 或缺失时返回默认值"""
        val = raw.get(key, default)
        if isinstance(val, float) and math.isnan(val):
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    # #2137：同花顺交割单费用明细的源列（与 _preprocess_dataframe 的 fee_cols 同源）
    FEE_BREAKDOWN_SOURCE_COLUMNS = ('佣金', '印花税', '过户费', '其他杂费')

    # 差额推导手续费的上限（占成交额比例）。真实费率（佣金 + 印花税 + 过户费）
    # 远低于 5%，超过这条线基本是「金额录错 / 数量单位错」，不能当费用吃掉。
    FEE_GAP_MAX_RATIO = Decimal('0.05')

    @classmethod
    def _derive_fee_from_amount_gap(
        cls,
        business_type: str,
        fee: float,
        fee_breakdown: tuple,
        trade_amount: Decimal,
        quantity: float,
        price: float,
        net_amount_raw: Decimal,
    ) -> float:
        """费用列缺失时，用「发生金额 − 成交额」的差额兜补手续费（2026-11-02）。

        ## 为什么不按费率估算

        用户口径是「实际多付（买入）或少收（卖出）的钱就是手续费」——这是交割单上
        算出来的实测值，不是猜。而本仓 `ledgers.fee_config` 16 个账户全为空，按空白
        配置估算等于制造虚假精度：让「估算值」看起来像「交割单真值」。

        ## 三条边界（缺一条就会把真错误静默吃成手续费）

        1. **只在费用列全空时启用**：四列任一行有值说明来源给了明细，以它为准，
           不覆盖。差额与明细不符时留给前端的「差额超过手续费」提示，由人判断。
        2. **方向校验**：买入发生额 = 成交额 + 费（差为正），卖出 = 成交额 − 费
           （差为负）。方向不符说明这不是费用（金额录错 / 数量单位错 / 列取反了），
           此时不推导，让校验层照旧报「金额与数量×价格不符」。
        3. **上限**：|差| > 成交额 5% 视为数据错误，不推导。

        差额基准优先用交割单的「成交金额」列，缺失时回落到 数量 × 均价——
        均价可能已被四舍五入，成交额列才是券商给的原值。
        """
        if business_type not in ('buy', 'sell'):
            return fee
        if fee and fee > 0:
            return fee
        if any(p is not None for p in fee_breakdown):
            return fee

        gross = abs(trade_amount) if trade_amount else Decimal('0')
        if gross <= 0:
            gross = abs(Decimal(str(quantity)) * Decimal(str(price)))
        net = abs(net_amount_raw)
        if gross <= 0 or net <= 0:
            return fee

        gap = net - gross
        if business_type == 'sell':
            gap = -gap
        if gap <= 0:
            return fee
        if gap > gross * cls.FEE_GAP_MAX_RATIO:
            return fee
        return float(round(gap, 2))

    @classmethod
    def _parse_fee_breakdown(
        cls, raw: dict
    ) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """读取交割单四列费用明细（#2137），返回 (佣金, 印花税, 过户费, 其他杂费)，单位元。

        四列**全在**才拆分；任一缺列 → 全 None（未拆分）。模型的拆分不变量是
        「四列齐全且其和=fee」，缺列时按 0 补齐会把「来源没给这一列」演成
        「来源给了 0」——费用汇总时两类无法区分。缺列的老模板退回聚合 fee
        单值（_preprocess_dataframe 的合并逻辑），行为与改造前一致。
        """
        if any(col not in raw for col in cls.FEE_BREAKDOWN_SOURCE_COLUMNS):
            return (None, None, None, None)
        return (
            cls._safe_decimal(cls._safe_float(raw, '佣金')),
            cls._safe_decimal(cls._safe_float(raw, '印花税')),
            cls._safe_decimal(cls._safe_float(raw, '过户费')),
            cls._safe_decimal(cls._safe_float(raw, '其他杂费')),
        )

    # ── 行解析 ──

    def _parse_row(self, raw: dict, line_num: int) -> Optional[StandardTransactionRecord]:
        """解析单行同花顺记录"""
        op_type_cn = self._safe_str(raw, '操作')

        # 处理带问号的特殊格式
        otc_match = re.match(r'^(OTC\S+)\?([-]?\d+(?:\.\d+)?)', op_type_cn)
        if otc_match:
            op_type_cn = otc_match.group(1)
        general_match = re.match(r'^([^?]+)\?([-]?\d+(?:\.\d+)?)', op_type_cn)
        if general_match and not op_type_cn.startswith('OTC'):
            op_type_cn = general_match.group(1)

        # 资金划转特殊处理
        if op_type_cn in ('银行转证券', '证券转银行', 'OTC资金划出', 'OTC资金划入', 'OTC现金宝交', 'OTC资管转让'):
            return self._parse_cash_transfer(raw, op_type_cn)

        # 业务类型映射
        business_type = THS_OP_MAP.get(op_type_cn)
        if business_type is None:
            logger.debug(f'无法识别的同花顺操作类型: [{op_type_cn}] (line {line_num})')
            return None

        if business_type not in VALID_OP_TYPES:
            raise ValueError(f'不支持的同花顺操作类型: {op_type_cn}')

        # venue（#1662）：同花顺交割单里既有场内证券、也有场外开放式基金申赎。场所由
        # **操作类型**决定（THS_OTC_OPS，见 mappings.py 的证据链）—— 这是「入场时本来就
        # 已知」的信息，不需要（也不允许）靠代码数字猜。
        venue = OTC if op_type_cn in THS_OTC_OPS else EXCHANGE

        # 代码标准化（同时获取 suggested_type）：venue 传给归一化器，
        # 场外路径**不做交易所推断**（否则 004369 → SZ004369）。
        symbol_raw = self._safe_str(raw, '证券代码')
        try:
            normalized, _, suggested_type = self.normalizer.normalize(symbol_raw, venue=venue)
        except Exception:
            normalized, suggested_type = None, None
        symbol = normalized if normalized else symbol_raw

        # 根据 venue / suggested_type 确定资产类型
        if venue == OTC:
            # 场外基金 / 资管计划：裸码 + 基金语义（是否货基由写入层的名录判定落 is_money_fund）
            asset_type = 'fund'
        elif suggested_type:
            asset_type = suggested_type  # 可能为 'money_fund', 'reverse_repo' 等
        elif business_type == 'dividend_cash' and op_type_cn == '利息归本':
            asset_type = 'cash'
        else:
            asset_type = 'stock'

        # 提取字段并构建标准记录
        trade_date = self._parse_ths_date(raw)
        contract_id = self._safe_str(raw, '合同编号')
        quantity = self._safe_float(raw, '成交数量')
        price = self._safe_float(raw, '成交均价')
        fee = self._safe_float(raw, 'fee')
        # 费用拆分（#2137）：同花顺交割单固定带 佣金/印花税/过户费/其他杂费 四列
        # （_preprocess_dataframe 已保留原列，仅另算合并值 df['fee']），逐类透传；
        # 源文件缺列时（老模板 / 资金划转等无费用行）四列留 None = 未拆分。
        fee_breakdown = self._parse_fee_breakdown(raw)
        # 金融口径收口（#1375 阶段二）：金额域直接进 Decimal，raw→float→Decimal 的桥接收敛为一处
        trade_amount = self._safe_decimal(self._safe_float(raw, '成交金额'))
        net_amount_raw = self._safe_decimal(self._safe_float(raw, '发生金额'))

        actual_amount = self._compute_actual_amount(business_type, trade_amount, net_amount_raw)
        net_amount_abs = abs(net_amount_raw)

        # 费用兜底（2026-11-02）：交割单费用列全空时，用发生金额与成交额的差额
        # 反推手续费——「实际多付/少收的钱就是费用」，比按空配置估算可靠
        fee = self._derive_fee_from_amount_gap(
            business_type, fee, fee_breakdown, trade_amount, quantity, price, net_amount_raw
        )

        return StandardTransactionRecord(
            confirm_date=trade_date,
            trade_date=trade_date,
            asset_type=asset_type,
            symbol=symbol,
            name=self._safe_str(raw, '证券名称') or symbol,
            business_type=business_type,
            amount=self._safe_decimal(actual_amount),
            account_name='',  # 前端会覆盖
            shares=self._safe_decimal(quantity),
            nav=self._safe_decimal(price),
            fee=self._safe_decimal(fee),
            # #2137：交割单费用明细逐类透传（缺列时为 None=未拆分）
            fee_commission=fee_breakdown[0],
            fee_stamp_duty=fee_breakdown[1],
            fee_transfer_fee=fee_breakdown[2],
            fee_other=fee_breakdown[3],
            transaction_id=contract_id,
            source=self.source,
            raw_op_type=op_type_cn,  # 保留原始中文操作类型
            venue=venue,
            trade_amount=trade_amount,
            net_amount=net_amount_abs,
        )

    def _parse_cash_transfer(self, raw: dict, op_type_cn: str) -> StandardTransactionRecord:
        """处理资金划转类型"""
        net_amount_raw = self._safe_decimal(self._safe_float(raw, '发生金额'))
        return StandardTransactionRecord(
            confirm_date=self._parse_ths_date(raw),
            asset_type='cash',
            symbol=CASH_SYMBOL,
            name=op_type_cn,  # 使用操作类型作为名称
            business_type='deposit' if net_amount_raw >= 0 else 'withdraw',
            amount=abs(net_amount_raw),
            account_name='',
            source=self.source,
        )

    # ── 辅助方法 ──

    def _parse_ths_date(self, raw: dict) -> date:
        """从同花顺行字典中提取交收日期（YYYYMMDD），返回 date 对象"""
        date_str = self._safe_str(raw, '交收日期')
        if not date_str:
            raise ValueError('交收日期为空')
        try:
            return datetime.strptime(date_str, '%Y%m%d').date()
        except ValueError:
            raise ValueError(f'无效的日期格式: {date_str}')

    @staticmethod
    def _compute_actual_amount(business_type: str, trade_amount: Decimal, net_amount_raw: Decimal) -> Decimal:
        if business_type == 'tax':
            # 扣税：取发生金额的绝对值，然后强制为负
            return -abs(net_amount_raw) if net_amount_raw != 0 else -abs(trade_amount)
        elif business_type in ('buy', 'sell'):
            return abs(net_amount_raw) if net_amount_raw != 0 else abs(trade_amount)
        else:
            return abs(net_amount_raw)

    @staticmethod
    def _format_contract_id(x) -> str:
        if x is None or (isinstance(x, float) and math.isnan(x)) or str(x).strip() in ('', 'nan', 'None'):
            return ''
        try:
            return str(int(float(x))).zfill(10)
        except (ValueError, TypeError):
            return str(x).strip()

    # ── 校验 ──

    def validate(
        self, records: List[StandardTransactionRecord]
    ) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        valid_records = []
        errors = []
        for i, record in enumerate(records):
            line_num = i + 2
            if not record.symbol:
                errors.append(SBImportError(line_num, 'symbol', '证券代码不能为空'))
            elif record.amount == Decimal('0'):
                errors.append(SBImportError(line_num, 'amount', '金额不能为0'))
            else:
                valid_records.append(record)
        return valid_records, errors
