# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:24
# File : akshare_adapter.py
# -*- coding: utf-8 -*-
# app/services/sync/adapters/akshare_adapter.py
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import akshare as ak
from loguru import logger

from app.core.symbol_utils import get_normalizer
from app.services.sync.adapters.base import DataSourceAdapter


class AkshareAdapter(DataSourceAdapter):
    def __init__(self):
        self._fund_manager_cache = None
        self.logger = logger.bind(adapter='akshare')

    def get_name(self) -> str:
        return 'akshare'

    def get_version(self) -> str:
        return getattr(ak, '__version__', 'unknown')

    # ── 股票列表 ──

    # app/services/sync/adapters/akshare_adapter.py

    def _parse_fund_info_dataframe(self, df, fund_code: str) -> Dict[str, Any]:
        """
        将 ak.fund_info_ths 返回的 DataFrame 解析为结构化字典。
        返回空字典表示解析失败。
        """
        if df is None or df.empty:
            self.logger.warning(f'fund_info_ths 返回空: {fund_code}')
            return {}

        # 列名是 "字段" 和 "值"
        if '字段' not in df.columns or '值' not in df.columns:
            self.logger.warning(f'fund_info_ths 列名异常: {df.columns.tolist()}')
            return {}

        info = dict(zip(df['字段'], df['值']))
        if not info:
            return {}

        result = dict()
        result['fund_type_raw'] = info.get('投资类型', '') or info.get('基金类型', '')
        result['company_name'] = info.get('基金管理人', '')
        result['fund_full_name'] = info.get('基金全称', '')
        raw_date = info.get('成立日期', '')
        if raw_date:
            try:
                result['create_time'] = datetime.strptime(raw_date.strip(), '%Y-%m-%d').date()
            except (ValueError, IndexError):
                self.logger.warning(f'{fund_code} 成立日期解析失败: {raw_date}')
        benchmark = info.get('业绩比较基准', '')
        if benchmark and benchmark != '无':
            result['benchmark'] = benchmark
        manager_names = info.get('基金经理', '')
        if manager_names:
            result['manager_names'] = [n.strip() for n in manager_names.split(',') if n.strip()]
        return result

    def fetch_stock_price(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[dict]:
        """
        获取 A 股股票历史行情（使用新浪财经接口 ak.stock_zh_a_daily）

        Args:
            symbol: 标准化代码，如 SH600519, SZ000001
            start_date: 起始日期，默认一年前
            end_date: 结束日期，默认今天

        Returns:
            包含字段: symbol, trade_date, open, high, low, close, volume, adj_close, source
        """
        try:
            normalizer = get_normalizer()
            # 直接使用已有的 to_sina_code 方法
            sina_symbol = normalizer.to_sina_code(symbol)
            if not sina_symbol:
                logger.warning(f'无法转换为新浪代码: {symbol}')
                return []

            # 默认日期范围：最近一年
            if start_date is None:
                start_date = date.today() - timedelta(days=365)
            if end_date is None:
                end_date = date.today()

            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')

            logger.debug(f'请求新浪日线: {sina_symbol} {start_str} -> {end_str}')

            # 调用新浪接口
            df = ak.stock_zh_a_daily(symbol=sina_symbol, start_date=start_str, end_date=end_str, adjust='qfq')

            if df is None or df.empty:
                logger.info(f'{symbol} 在 {start_str} ~ {end_str} 无行情数据')
                return []

            records = []
            for _, row in df.iterrows():
                trade_date_raw = row['date']
                if isinstance(trade_date_raw, str):
                    trade_date = datetime.strptime(trade_date_raw, '%Y-%m-%d').date()
                else:
                    trade_date = trade_date_raw.date() if hasattr(trade_date_raw, 'date') else trade_date_raw

                records.append(
                    {
                        'symbol': symbol,
                        'trade_date': trade_date,
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': float(row['volume']),
                        'adj_close': float(row['close']),
                        'source': 'akshare_sina',
                    }
                )

            logger.debug(f'{symbol} 获取到 {len(records)} 条行情')
            return records

        except Exception as e:
            logger.error(f'获取股票 {symbol} 历史行情失败: {e}')
            return []

    def fetch_stock_list(self, market: Optional[str] = None) -> List[dict]:
        """获取 A 股股票（含沪深北）"""
        try:
            df = ak.stock_info_a_code_name()
            if df is None or df.empty:
                return []

            normalizer = get_normalizer()
            records = []
            for _, row in df.iterrows():
                raw_code = str(row['code'])
                normalized, mkt, _ = normalizer.normalize(raw_code)
                if normalized:
                    records.append(
                        {
                            'symbol': normalized,
                            'name': str(row['name']),
                            'market': mkt or 'CN_A',
                            'type': 'stock',
                            'currency': 'CNY',
                        }
                    )
            return records
        except Exception as e:
            logger.error(f'获取股票列表失败: {e}')
            return []

    def fetch_daily_spot_all(self) -> List[dict]:
        """获取全市场 A 股当日实时行情（作为日线数据），仅用于增量同步"""
        try:
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return []

            normalizer = get_normalizer()
            records = []
            for _, row in df.iterrows():
                raw_code = str(row['代码'])
                normalized, _, _ = normalizer.normalize(raw_code)
                if not normalized:
                    continue
                records.append(
                    {
                        'symbol': normalized,
                        'trade_date': date.today(),  # 注意：非交易日可能无数据，届时由调用方处理
                        'open': row['今开'],
                        'high': row['最高'],
                        'low': row['最低'],
                        'close': row['最新价'],
                        'volume': row['成交量'],
                        'adj_close': row['最新价'],  # 当日无复权，用最新价代替
                        'source': 'akshare_spot',
                    }
                )
            return records
        except Exception as e:
            logger.error(f'获取实时行情失败: {e}')
            return []

    # ── 基金列表 ──
    def fetch_fund_list(self) -> List[dict]:
        """
        使用 akshare 官方接口获取全市场公募基金基本信息。
        接口：ak.fund_name_em() 返回所有基金的代码、简称、类型。
        """
        try:
            # 使用 fund_name_em 替代 fund_em_fund_name（后者在当前版本中不可用）
            df = ak.fund_name_em()
            if df is None or df.empty:
                self.logger.error('akshare fund_name_em 返回空数据')
                return []

            records = []
            for _, row in df.iterrows():
                code = str(row['基金代码']).strip()
                if not code or len(code) != 6 or not code.isdigit():
                    continue
                records.append(
                    {
                        'fund_code': code,
                        'name': row['基金简称'],
                        'fund_type': row.get('基金类型', ''),
                        'company_name': '',  # 该接口不直接提供公司名
                    }
                )
            self.logger.info(f'获取到 {len(records)} 只基金')
            return records
        except Exception as e:
            self.logger.error(f'获取基金列表失败: {e}')
            return []

    def fetch_fund_nav(
        self,
        fund_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[dict]:
        raise NotImplementedError

    def fetch_fund_manager(self, fund_code: str) -> List[dict]:
        """获取指定基金的基金经理，全量数据仅请求一次，失败后静默跳过"""
        # 如果已经请求过（无论成功或失败），直接使用缓存结果
        if hasattr(self, '_fund_manager_cache'):
            df = self._fund_manager_cache
            if df is None or df.empty:
                return []
            # 有缓存数据，按基金代码筛选
            return self._filter_managers(df, fund_code)

        # 第一次请求全量数据
        try:
            df = ak.fund_manager_em()
        except Exception as e:
            self.logger.warning(f'基金经理全量接口不可用: {e}，后续将跳过所有经理同步')
            self._fund_manager_cache = None  # 标记为失败，永久跳过
            return []

        if df is None or df.empty:
            self.logger.warning('基金经理全量数据为空')
            self._fund_manager_cache = None
            return []

        self._fund_manager_cache = df
        self.logger.info(f'获取到 {len(df)} 条基金经理数据')
        return self._filter_managers(df, fund_code)

    def _filter_managers(self, df, fund_code: str) -> List[dict]:
        """从全量数据中筛选某基金的经理"""
        try:
            filtered = df[df['现任基金代码'].str.contains(fund_code, na=False)]
            if filtered.empty:
                return []

            managers = []
            seen = set()
            import hashlib

            for _, row in filtered.iterrows():
                name = str(row['姓名'])
                company = str(row.get('所属公司', ''))
                mgr_code = hashlib.sha256(f'{name}_{company}'.encode()).hexdigest()[:12]
                if mgr_code in seen:
                    continue
                seen.add(mgr_code)
                managers.append(
                    {
                        'fund_code': fund_code,
                        'name': name,
                        'mgr_code': mgr_code,
                        'company': company,
                    }
                )
            return managers
        except Exception as e:
            self.logger.warning(f'筛选基金经理出错: {e}')
            return []

    def fetch_fund_detail(self, fund_code: str) -> Dict[str, Any]:
        """
        获取单只基金的详细信息 (ak.fund_info_ths)
        返回字典，键为 model 字段名，值为解析后的数据。解析失败返回空字典。
        """
        result = {}
        try:
            df = ak.fund_info_ths(symbol=fund_code)
            if df is None or df.empty:
                self.logger.warning(f'fund_info_ths 返回空: {fund_code}')
                return result

            # 将两列 DataFrame 转换为 dict
            info = dict(zip(df['字段'], df['值']))
            if not info:
                return result

            # 基金类型 -> fund_type_id (先存原始字符串，后续由 Job 映射)
            raw_type = info.get('投资类型', '') or info.get('基金类型', '')
            result['fund_type_raw'] = raw_type

            # 基金管理人 -> company_id (Job 中根据名称查找或创建)
            company_name = info.get('基金管理人', '')
            result['company_name'] = company_name

            # 成立日期 -> create_time
            raw_date = info.get('成立日期', '')
            if raw_date:
                try:
                    result['create_time'] = datetime.strptime(raw_date.strip(), '%Y-%m-%d').date()
                except (ValueError, IndexError):
                    self.logger.warning(f'{fund_code} 成立日期解析失败: {raw_date}')

            # 业绩比较基准 -> benchmark
            benchmark = info.get('业绩比较基准', '')
            if benchmark and benchmark != '无':
                result['benchmark'] = benchmark

            # 风险等级 -> risk_level (字符串转数字)
            risk_str = info.get('风险等级', '')
            if risk_str:
                risk_mapping = {
                    '低风险': 1,
                    '中低风险': 2,
                    '中风险': 3,
                    '中高风险': 4,
                    '高风险': 5,
                }
                for key, val in risk_mapping.items():
                    if key in risk_str:
                        result['risk_level'] = val
                        break

            # 基金全称 -> full_name
            result['fund_full_name'] = info.get('基金全称', '')

            # 管理费率、最高申购费、最高赎回费可作为费率参考
            result['management_fee'] = info.get('管理费', '')  # 字符串 "1.20%"
            result['max_purchase_fee'] = info.get('最高申购费', '')
            result['max_redeem_fee'] = info.get('最高赎回费', '')

            # 基金经理姓名 -> managers (仅姓名，无编码)
            manager_names = info.get('基金经理', '')
            if manager_names:
                result['manager_names'] = [n.strip() for n in manager_names.split('、') if n.strip()]

        except Exception as e:
            self.logger.warning(f'获取基金 {fund_code} 详情失败: {e}')
        return result
