# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:24
# File : akshare_adapter.py
# -*- coding: utf-8 -*-
# app/services/sync/adapters/akshare_adapter.py
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.symbol_utils import get_normalizer
from app.services.sync.adapters.base import DataSourceAdapter

# 基金经理全量接口（东财 fund_manager_em）偶发抖动，首次拉取的有限重试策略
_FUND_MANAGER_RETRY = 3
_FUND_MANAGER_RETRY_SLEEP = 3  # 秒


class AkshareAdapter(DataSourceAdapter):
    def __init__(self):
        self._fund_manager_cache = None
        # 是否已发起过全量拉取（注意：不能用 hasattr(_fund_manager_cache) 判定，
        # 该属性在 __init__ 即存在，会导致「首次拉取」分支永不执行、经理同步恒空转）
        self._fund_manager_fetched = False
        self.logger = logger.bind(adapter='akshare')

    def get_name(self) -> str:
        return 'akshare'

    def get_version(self) -> str:
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
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
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()

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
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()

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
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()

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
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()

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
        """获取指定基金的基金经理，全量数据仅请求一次，失败后静默跳过

        该接口（东财 fund_manager_em）偶发抖动；此前一次失败就把缓存置 None，
        导致本轮后续所有基金都静默返回空（表现为「经理全量同步跑了但一条没进」）。
        故首次拉取做有限重试，只有连续重试均失败才标记为不可用。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()

        # 已经请求过（成功或失败），直接使用缓存结果
        if self._fund_manager_fetched:
            df = self._fund_manager_cache
            if df is None or df.empty:
                return []
            # 有缓存数据，按基金代码筛选
            return self._filter_managers(df, fund_code)

        # 第一次请求全量数据（带重试，规避偶发抖动）
        df = None
        for attempt in range(_FUND_MANAGER_RETRY):
            try:
                df = ak.fund_manager_em()
                break
            except Exception as e:  # noqa: BLE001
                if attempt == _FUND_MANAGER_RETRY - 1:
                    self.logger.warning(f'基金经理全量接口不可用: {e}，后续将跳过所有经理同步')
                else:
                    self.logger.warning(f'基金经理全量接口第 {attempt + 1}/{_FUND_MANAGER_RETRY} 次失败: {e}，稍后重试')
                    time.sleep(_FUND_MANAGER_RETRY_SLEEP)

        # 无论成败只拉一次：成功则缓存 df，失败则缓存 None 并跳过本轮后续基金。
        # 缺了这一步会退化为「逐基金重复全量请求」（#1286 回填实测踩坑）。
        self._fund_manager_fetched = True

        if df is None or df.empty:
            if df is not None:
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
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()

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

    # ── 分红 / 送股（#1179） ──

    @staticmethod
    def _parse_dividend_date(value):
        if value is None:
            return None
        if isinstance(value, (date, datetime)):
            return value.date() if isinstance(value, datetime) else value
        s = str(value).strip()
        if not s or s in ('NaT', 'nan', 'None'):
            return None
        for fmt in ('%Y-%m-%d', '%Y/%m/%d'):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _to_ratio(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def fetch_stock_dividend(self, symbol: str) -> List[dict]:
        """股票分红/送股实施方案（ak.stock_dividend_cninfo）。"""
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.stock_dividend_cninfo(symbol=symbol)
            if df is None or df.empty:
                return []
            normalizer = get_normalizer()
            norm, _, _ = normalizer.normalize(symbol)
            out = []
            for _, row in df.iterrows():
                ex_date = self._parse_dividend_date(row.get('除权日'))
                if not ex_date:
                    continue
                out.append(
                    {
                        'symbol': norm or symbol,
                        'dividend_type': str(row.get('分红类型', '')),
                        'bonus_ratio': self._to_ratio(row.get('送股比例')),
                        'transfer_ratio': self._to_ratio(row.get('转增比例')),
                        'cash_ratio': self._to_ratio(row.get('派息比例')),
                        'regist_date': self._parse_dividend_date(row.get('股权登记日')),
                        'ex_date': ex_date,
                        'pay_date': self._parse_dividend_date(row.get('派息日')),
                        'arrive_date': self._parse_dividend_date(row.get('股份到账日')),
                        'desc': str(row.get('实施方案分红说明', '')),
                        'source': 'akshare_cninfo',
                    }
                )
            return out
        except Exception as e:
            self.logger.error(f'获取股票 {symbol} 分红失败: {e}')
            return []

    def fetch_fund_dividend(self, fund_code: str) -> List[dict]:
        """基金分红公告（ak.fund_announcement_dividend_em）。"""
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.fund_announcement_dividend_em(symbol=fund_code)
            if df is None or df.empty:
                return []
            out = []
            for _, row in df.iterrows():
                d = self._parse_dividend_date(row.get('公告日期'))
                if not d:
                    continue
                out.append(
                    {
                        'symbol': fund_code,
                        'ann_title': str(row.get('公告标题', '')),
                        'ann_date': d,
                        'report_id': str(row.get('报告ID', '')),
                        'source': 'akshare_fund_ann',
                    }
                )
            return out
        except Exception as e:
            self.logger.error(f'获取基金 {fund_code} 分红公告失败: {e}')
            return []

    # ── 基金规模 / 近似股票仓位（#1286 数据底座，复用 akshare 现成接口） ──

    def fetch_fund_scale(self) -> List[dict]:
        """全市场开放式基金规模（ak.fund_scale_open_sina）。

        接口仅给「最近总份额」与「单位净值」，不直接给规模列；规模由调用方按
        shares×nav 估算（亿元）。返回 [{fund_code, shares, nav}]。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.fund_scale_open_sina()
            if df is None or df.empty:
                return []
            out = []
            for _, row in df.iterrows():
                code = str(row.get('基金代码', '')).strip()
                if not code or len(code) != 6 or not code.isdigit():
                    continue
                out.append(
                    {
                        'fund_code': code,
                        'shares': self._to_ratio(row.get('最近总份额')),
                        'nav': self._to_ratio(row.get('单位净值')),
                    }
                )
            self.logger.info(f'获取到 {len(out)} 只基金规模数据')
            return out
        except Exception as e:
            self.logger.error(f'获取基金规模失败: {e}')
            return []

    def fetch_fund_top_holdings(self, fund_code: str) -> List[dict]:
        """单只基金前十大重仓（ak.fund_portfolio_hold_em）。

        返回 [{stock_code, stock_name, ratio(占净值比例)}]；调用方累加 top10 作为近似股票仓位。
        单基金抓取，失败静默返回空，由 Job 控制重试/跳过。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.fund_portfolio_hold_em(symbol=fund_code)
            if df is None or df.empty:
                return []
            out = []
            for _, row in df.iterrows():
                out.append(
                    {
                        'stock_code': str(row.get('股票代码', '')).strip(),
                        'stock_name': str(row.get('股票名称', '')),
                        'ratio': self._to_ratio(row.get('占净值比例')),
                    }
                )
            return out
        except Exception as e:
            self.logger.warning(f'获取基金 {fund_code} 重仓失败: {e}')
            return []

    def fetch_index_constituents_csindex(self, index_code: str) -> List[dict]:
        """中证系指数成分（ak.index_stock_cons_csindex）。

        返回 [{symbol, stock_name, index_name}]；非 csindex 系列指数会抛错，由 Job 回退 sina。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.index_stock_cons_csindex(symbol=index_code)
            if df is None or df.empty:
                return []
            out = []
            for _, row in df.iterrows():
                out.append(
                    {
                        'symbol': str(row.get('成分券代码', '')).strip(),
                        'stock_name': str(row.get('成分券名称', '')),
                        'index_name': str(row.get('指数名称', '')),
                    }
                )
            return out
        except Exception as e:
            self.logger.warning(f'csindex 成分获取失败 {index_code}: {e}')
            return []

    def fetch_index_constituents_sina(self, index_code: str) -> List[dict]:
        """新浪指数成分（ak.index_stock_cons），csindex 系列缺失时的回退。

        返回 [{symbol, stock_name, in_date}]。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.index_stock_cons(symbol=index_code)
            if df is None or df.empty:
                return []
            has_date = '日期' in df.columns
            out = []
            for _, row in df.iterrows():
                out.append(
                    {
                        'symbol': str(row.get('品种代码', '')).strip(),
                        'stock_name': str(row.get('品种名称', '')),
                        'in_date': str(row.get('日期', '')) if has_date else None,
                    }
                )
            return out
        except Exception as e:
            self.logger.warning(f'sina 成分获取失败 {index_code}: {e}')
            return []

    def fetch_index_catalog(self) -> List[dict]:
        """新浪指数名录（ak.index_stock_info），#1286/#1365 聚合搜索底座之三源之一。

        返回 [{index_code, name, exchange, source}]，归一化为 SH000300 形态。

        兼容两种 akshare 版本形态（#1366 实测）：
        - 旧版：中文列名（代码/名称），代码带 sh/sz 前缀 → 直接拆前缀；
        - 新版（≥1.18.x）：英文列名（index_code/display_name），裸 6 位码无前缀
          → 按交易所惯例归属（39 开头=SZ，其余=SH）；归属歧义由三源去重优先级
          （csindex/cni 后到覆盖不可能——sina 优先，但归属错误风险已被
          「名录仅收录指数、000xxx 沪 / 399xxx 深」的惯例约束收敛）。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.index_stock_info()
            if df is None or df.empty:
                return []
            code_col = self._pick_col(df, ('index_code', '代码'))
            name_col = self._pick_col(df, ('display_name', '名称', '简称'))
            out = []
            for _, row in df.iterrows():
                raw = str(row[code_col]).strip().lower()
                if not raw:
                    continue
                exchange = ''
                if raw.startswith('sh'):
                    exchange, index_code = 'SH', raw[2:]
                elif raw.startswith('sz'):
                    exchange, index_code = 'SZ', raw[2:]
                elif len(raw) == 6 and raw.isdigit():
                    # 新版裸码：39 开头为深交所指数，其余（000/880/950 等）归沪
                    index_code = raw
                    exchange = 'SZ' if raw.startswith('39') else 'SH'
                else:
                    index_code = raw
                out.append(
                    {
                        'index_code': index_code,
                        'name': str(row[name_col]).strip(),
                        'exchange': exchange,
                        'source': 'sina',
                    }
                )
            return out
        except Exception as e:
            self.logger.warning(f'新浪指数名录获取失败: {e}')
            return []

    @staticmethod
    def _pick_col(df, keywords: tuple) -> str:
        """按子串匹配 DataFrame 列名（防 akshare 版本间列名漂移 + 控制台 mojibake 误判）。"""
        for c in df.columns:
            if any(k in str(c) for k in keywords):
                return c
        raise KeyError(f'未找到含 {keywords} 的列，实际列: {list(df.columns)}')

    def fetch_index_catalog_csindex(self) -> List[dict]:
        """中证指数官网全量名录（ak.index_csindex_all），#1365 三源合并之中证源。

        中证专属代码唯一来源：930950（中证偏股基金）/932000（中证2000）/
        000510（中证A500）等。exchange 记 'CSI' 作统一编码命名空间前缀。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.index_csindex_all()
            if df is None or df.empty:
                return []
            code_col = self._pick_col(df, ('指数代码', '代码'))
            name_col = self._pick_col(df, ('简称', '名称'))
            return [
                {
                    'index_code': str(r[code_col]).strip().zfill(6),
                    'name': str(r[name_col]).strip(),
                    'exchange': 'CSI',
                    'source': 'csindex',
                }
                for _, r in df.iterrows()
                if str(r[code_col]).strip()
            ]
        except Exception as e:
            self.logger.warning(f'中证指数名录获取失败: {e}')
            return []

    def fetch_index_catalog_cni(self) -> List[dict]:
        """国证指数官网全量名录（ak.index_all_cni），#1365 三源合并之国证源。

        国证专属代码唯一来源：399303（国证2000）/399317（国证A指，
        万得全A 881001 的权威免费替代）等。exchange 记 'CNI'。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.index_all_cni()
            if df is None or df.empty:
                return []
            code_col = self._pick_col(df, ('指数代码', '代码'))
            name_col = self._pick_col(df, ('简称', '名称'))
            return [
                {
                    'index_code': str(r[code_col]).strip().zfill(6),
                    'name': str(r[name_col]).strip(),
                    'exchange': 'CNI',
                    'source': 'cni',
                }
                for _, r in df.iterrows()
                if str(r[code_col]).strip()
            ]
        except Exception as e:
            self.logger.warning(f'国证指数名录获取失败: {e}')
            return []

    # ── 可转债条款（#1285 消费侧 / #1393） ──

    @staticmethod
    def _num(value) -> Optional[float]:
        """宽松转 float，缺失/不可解析返回 None（区别于 _to_ratio 的 0.0 兜底）。"""
        if value is None:
            return None
        s = str(value).strip()
        if s in ('', 'nan', 'None', '--', '-'):
            return None
        try:
            return float(s)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _int(value) -> Optional[int]:
        """宽松转 int（强赎天计数等），缺失返回 None。"""
        f = AkshareAdapter._num(value)
        return int(f) if f is not None else None

    @staticmethod
    def _cell(row, *keys):
        """按候选列名宽松取值（防 akshare 版本间列名漂移）；全缺返回 None。"""
        for k in keys:
            if k in row.index:
                v = row[k]
                if v is not None and str(v).strip() not in ('', 'nan', 'None', '--'):
                    return v
        return None

    def fetch_convertible_bond_redeem(self) -> List[dict]:
        """集思录可转债强赎数据（ak.bond_cb_redeem_jsl）。

        覆盖静态条款主集：现价、正股、规模 / 剩余规模、转股价、强赎触发价、
        **强赎天计数**、强赎条款。返回键为 canonical 字段名，Job 负责归一 symbol。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.bond_cb_redeem_jsl()
            if df is None or df.empty:
                return []
            out = []
            for _, row in df.iterrows():
                code = str(self._cell(row, '代码', '转债代码') or '').strip()
                if not code:
                    continue
                out.append(
                    {
                        'bond_code': code.zfill(6),
                        'name': str(self._cell(row, '名称', '转债名称') or ''),
                        'price': self._num(self._cell(row, '现价', '转债现价')),
                        'stock_name': str(self._cell(row, '正股名称', '正股简称') or ''),
                        'stock_code_raw': str(self._cell(row, '正股代码') or '').strip(),
                        'issue_size': self._num(self._cell(row, '规模', '发行规模')),
                        'remain_size': self._num(self._cell(row, '剩余规模')),
                        'convert_price': self._num(self._cell(row, '转股价')),
                        'force_redeem_price': self._num(self._cell(row, '强赎触发价')),
                        'redeem_count': self._int(self._cell(row, '强赎天计数')),
                        'redeem_clause': str(self._cell(row, '强赎条款') or ''),
                        'source': 'akshare_jsl',
                    }
                )
            self.logger.info(f'获取到 {len(out)} 条可转债强赎数据')
            return out
        except Exception as e:
            self.logger.error(f'获取可转债强赎数据失败: {e}')
            return []

    def fetch_convertible_bond_basic(self) -> List[dict]:
        """可转债基本信息（ak.bond_zh_cov）：评级 / 到期日。

        列名可能随 akshare 版本漂移，故宽松取列；缺失项返回 None，由 Job 与强赎
        数据按 bond_code 合并（不强求齐全）。接口不可用时返回空，不影响主链路。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.bond_zh_cov()
            if df is None or df.empty:
                return []
            out = []
            for _, row in df.iterrows():
                code = str(self._cell(row, '债券代码', '转债代码', '代码') or '').strip()
                if not code:
                    continue
                out.append(
                    {
                        'bond_code': code.zfill(6),
                        'name': str(self._cell(row, '债券简称', '转债简称', '名称') or ''),
                        'rating': self._cell(row, '债券评级', '信用评级', '评级'),
                        'maturity_date': self._cell(row, '到期时间', '到期日'),
                        'source': 'akshare_bond_zh_cov',
                    }
                )
            self.logger.info(f'获取到 {len(out)} 条可转债基本信息')
            return out
        except Exception as e:
            self.logger.warning(f'获取可转债基本信息失败: {e}')
            return []
