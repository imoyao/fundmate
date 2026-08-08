# -*- coding: utf-8 -*-
"""
Xalpha 数据源适配器（基金净值、费率）。

职责：
- 封装东财公开接口的调用（原 xa.fundinfo 依赖的 F10DataApi.aspx 已被东财废弃）
- 将返回数据转换为统一格式的字典列表
- 所有方法防御性地处理 None / 空数据 / 类型异常

数据源说明（2026-08-09 实证）：
- xalpha 0.12.4（最新版）的 fundinfo 在 csv 缓存后端下会调用已废弃的
  http://fund.eastmoney.com/f10/F10DataApi.aspx（404/空 body），构造必然失败。
- 替代方案（本文件实现，全部直连东财公开接口）：
  · 增量净值：api.fund.eastmoney.com/f10/lsjz（支持 startDate/endDate 日期范围过滤）
  · 全量净值：fund.eastmoney.com/pingzhongdata/{code}.js（一次 753KB 全量，含净值与累计净值）
  · 货币基金：pingzhongdata 的 Data_millionCopiesIncome（每万份收益）
  · 费率：fund.eastmoney.com/f10/jjfl_{code}.html（申购状态 + 赎回费率阶梯）
- lsjz 接口 WAF 校验 Referer 必须为 fund 域（quote 域会被拒），本文件显式覆盖
  requests_patch 注入的默认 Referer。
"""

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from app.services.sync.adapters.base import DataSourceAdapter

# 东财历史净值 JSON 接口：支持 pageIndex/pageSize 分页与 startDate/endDate 日期过滤
_LSJZ_API_URL = 'https://api.fund.eastmoney.com/f10/lsjz'
# 全量净值/货币基金收益脚本（单次请求返回全部历史）
_PINGZHONG_URL = 'http://fund.eastmoney.com/pingzhongdata/{code}.js'
# 费率页（申购状态 + 赎回费率阶梯）
_FEE_URL = 'https://fund.eastmoney.com/f10/jjfl_{code}.html'

# 东财时间戳为毫秒级 UTC+8
_TZ_BJ = timezone(timedelta(hours=8))

_EM_REFERER = 'https://fund.eastmoney.com/{code}.html'


class XalphaAdapter(DataSourceAdapter):
    def __init__(self):
        self._fund_nav_errors = set()
        self.logger = logger.bind(adapter='xalpha')

    def get_name(self) -> str:
        return 'xalpha'

    def get_version(self) -> str:
        # xalpha 库已不再承担数据获取，仅保留版本号语义（沿用既有接口约定）
        import xalpha as xa

        return getattr(xa, '__version__', 'unknown')

    # ── 基础请求 ──

    @staticmethod
    def _em_headers(fund_code: str) -> Dict[str, str]:
        """东财 fund 域请求头。

        lsjz / jjfl_ / pingzhongdata 均校验 Referer 必须为 fund 域
        （quote.eastmoney.com 会被 WAF 拒绝，2026-08-09 实证）；
        UA/nid cookie 由 requests_patch 全局注入，此处仅覆盖 Referer。
        """
        return {'Referer': _EM_REFERER.format(code=fund_code)}

    def _fetch_pingzhong(self, fund_code: str) -> Optional[str]:
        """拉取 pingzhongdata 脚本正文，失败返回 None"""
        try:
            resp = requests.get(
                _PINGZHONG_URL.format(code=fund_code),
                headers=self._em_headers(fund_code),
                timeout=30,
            )
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            self._log_fund_error_once(fund_code, f'pingzhongdata 获取失败: {e}')
            return None

    @staticmethod
    def _parse_ts_ms(ts_ms) -> date:
        """毫秒时间戳（UTC+8）转日期"""
        return datetime.fromtimestamp(int(ts_ms) / 1e3, tz=_TZ_BJ).date()

    # ── 基金净值（单日） ──

    def fetch_fund_nav_by_date(self, fund_code: str, target_date: date) -> Optional[float]:
        """获取指定日期的单位净值，失败返回 None。"""
        try:
            resp = requests.get(
                _LSJZ_API_URL,
                params={
                    'fundCode': fund_code,
                    'pageIndex': 1,
                    'pageSize': 50,
                    'startDate': target_date.strftime('%Y-%m-%d'),
                    'endDate': target_date.strftime('%Y-%m-%d'),
                },
                headers=self._em_headers(fund_code),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            records = (data.get('Data') or {}).get('LSJZList') or []
            if not records:
                return None
            nav = records[0].get('DWJZ')
            return float(nav) if nav else None
        except Exception as e:
            logger.warning(f'xalpha 获取基金 {fund_code} 在 {target_date} 的净值失败: {e}')
            return None

    # ── 基金净值（全量/增量） ──

    def fetch_fund_nav(self, fund_code, start_date=None, end_date=None) -> List[dict]:
        """获取基金净值序列（统一记录格式，含 is_money_fund 标记）。

        策略：
        - 增量（start_date 给定）：先试 lsjz 日期范围接口（小请求）；
          返回空时回退 pingzhongdata 判定货币基金（货币基金无单位净值，lsjz 必然为空）。
        - 全量（start_date 为空）：pingzhongdata.js 一次拉全（753KB，无需 299 页分页）。
        """
        try:
            if start_date is not None:
                records = self._fetch_lsjz_incremental(fund_code, start_date, end_date)
                if records:
                    return records

            page_text = self._fetch_pingzhong(fund_code)
            if page_text is None:
                return []
            if 'Data_millionCopiesIncome' in page_text[:800]:
                return self._parse_money_fund_records(fund_code, page_text, start_date, end_date)
            return self._parse_normal_full_records(fund_code, page_text)
        except Exception as e:
            self._log_fund_error_once(fund_code, f'净值获取失败: {e}')
            return []

    def _fetch_lsjz_incremental(self, fund_code, start_date, end_date) -> List[dict]:
        """lsjz 日期范围增量拉取（含分页），无数据返回 []"""
        start = start_date.strftime('%Y-%m-%d') if start_date else ''
        end = end_date.strftime('%Y-%m-%d') if end_date else ''
        records: List[dict] = []
        page = 1
        while True:
            resp = requests.get(
                _LSJZ_API_URL,
                params={
                    'fundCode': fund_code,
                    'pageIndex': page,
                    'pageSize': 100,
                    'startDate': start,
                    'endDate': end,
                },
                headers=self._em_headers(fund_code),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            data_payload = data.get('Data')
            if not isinstance(data_payload, dict):
                break
            rows = data_payload.get('LSJZList') or []
            for row in rows:
                records.append(
                    {
                        'fund_code': fund_code,
                        'date': date.fromisoformat(row['FSRQ']),
                        'unit_nav': float(row.get('DWJZ') or 0),
                        'acc_nav': float(row.get('LJJZ') or 0),
                        'is_money_fund': False,
                    }
                )
            total = int(data_payload.get('TotalCount') or 0)
            if len(records) >= total or not rows:
                break
            page += 1
            if page > 500:
                break
        return records

    def _parse_normal_full_records(self, fund_code: str, page_text: str) -> List[dict]:
        """从 pingzhongdata 解析普通基金全量净值（Data_netWorthTrend + Data_ACWorthTrend）"""
        m = re.search(r'Data_netWorthTrend = (\[.*?\]);', page_text, re.S)
        if not m:
            return []
        trend = json.loads(m.group(1).replace('null', 'None'))
        ltot = []
        m2 = re.search(r'Data_ACWorthTrend = (\[.*?\]);', page_text, re.S)
        if m2:
            try:
                ltot = json.loads(m2.group(1).replace('null', 'None'))
            except json.JSONDecodeError:
                ltot = []

        records = []
        for i, item in enumerate(trend):
            unit_nav = float(item.get('y') or 0)
            acc_nav = float(ltot[i][1]) if i < len(ltot) else unit_nav
            records.append(
                {
                    'fund_code': fund_code,
                    'date': self._parse_ts_ms(item['x']),
                    'unit_nav': unit_nav,
                    'acc_nav': acc_nav,
                    'is_money_fund': False,
                }
            )
        return records

    def _parse_money_fund_records(self, fund_code: str, page_text: str, start_date=None, end_date=None) -> List[dict]:
        """从 pingzhongdata 解析货币基金每万份收益（Data_millionCopiesIncome: [[ts, 万份收益], ...]）"""
        m = re.search(r'Data_millionCopiesIncome = (\[.*?\]);', page_text, re.S)
        if not m:
            return []
        try:
            income_list = json.loads(m.group(1).replace('null', 'None'))
        except json.JSONDecodeError:
            return []

        records = []
        for ts_ms, income in income_list:
            d = self._parse_ts_ms(ts_ms)
            if start_date and d < start_date:
                continue
            if end_date and d > end_date:
                continue
            records.append(
                {
                    'fund_code': fund_code,
                    'date': d,
                    'unit_nav': float(income),
                    'is_money_fund': True,
                }
            )
        return records

    def get_fund_with_type(self, fund_code: str):
        """
        [已弃用] 原返回 xa.fundinfo 对象；xalpha 数据路径已废弃（见模块头），
        净值请改用 fetch_fund_nav，本方法仅保留签名兼容调用方。
        """
        self._log_fund_error_once(fund_code, 'get_fund_with_type 已弃用（xalpha 数据路径废弃），请改用 fetch_fund_nav')
        return None, False

    # ── 基金列表（不支持） ──

    def fetch_fund_list(self) -> List[dict]:
        raise NotImplementedError('xalpha 不支持全市场基金列表')

    # ── 净值解析辅助（兼容旧调用方/测试） ──

    def _parse_nav_dataframe(self, nav_df, fund_code: str) -> List[dict]:
        """将 DataFrame 转换为统一格式的字典列表（保留兼容，不再由内部调用）"""
        records = list()
        nav_df = self._filter_nav_by_date(nav_df)
        for idx, row in nav_df.iterrows():
            records.append(
                {
                    'fund_code': fund_code,
                    'date': self._extract_date(idx),
                    'unit_nav': float(row.get('netvalue', 0)),
                    'acc_nav': float(row.get('totvalue', 0)),
                }
            )
        return records

    @staticmethod
    def _filter_nav_by_date(nav_df) -> Any:
        """过滤净值 DataFrame 的日期范围（预留扩展）"""
        return nav_df

    @staticmethod
    def _extract_date(idx) -> date:
        """从 DataFrame 索引中提取日期对象"""
        if hasattr(idx, 'date'):
            return idx.date()
        return __import__('pandas').Timestamp(idx).date()

    def _log_fund_error_once(self, fund_code: str, message: str) -> None:
        """同一只基金的同类型错误只记录一次，避免日志刷屏"""
        if fund_code not in self._fund_nav_errors:
            self.logger.warning(f'基金 {fund_code}: {message}')
            self._fund_nav_errors.add(fund_code)

    # ── 基金经理（不支持） ──

    def fetch_fund_manager(self, fund_code: str) -> List[dict]:
        raise NotImplementedError('xalpha 不支持基金经理信息，请使用 AkshareAdapter')

    # ── 股票相关（不支持） ──

    def fetch_stock_list(self, market: Optional[str] = None) -> List[dict]:
        raise NotImplementedError('xalpha 不支持股票列表')

    def fetch_stock_price(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[dict]:
        raise NotImplementedError('xalpha 不支持股票行情')

    # ── 费率信息 ──

    def fetch_fund_fee(self, fund_code: str) -> Dict[str, Any]:
        """
        获取基金费率信息（直连 jjfl_ 费率页 + pingzhongdata 申购费率）。
        返回字典包含 purchase_rate 和 redemption_schedule。解析失败返回空字典。
        """
        try:
            page_text = self._fetch_pingzhong(fund_code)
            if page_text is None:
                return {}
            if 'Data_millionCopiesIncome' in page_text[:800]:
                return {}  # 货币基金无申购/赎回费率
            purchase_rate = self._extract_purchase_rate(page_text)
        except Exception as e:
            self.logger.warning(f'xalpha 初始化基金 {fund_code} 失败: {e}')
            return {}

        result = {}
        if purchase_rate is not None:
            result['purchase_rate'] = purchase_rate

        schedule = self._fetch_redemption_schedule(fund_code)
        if schedule:
            result['redemption_schedule'] = schedule

        return result

    def _extract_purchase_rate(self, page_text: str) -> Optional[float]:
        """从 pingzhongdata 提取申购费率（fund_Rate，如 1.0 表示 1.0%）"""
        try:
            m = re.search(r'fund_Rate\s*=\s*([0-9.]+)\s*;', page_text)
            if m:
                return float(m.group(1))
        except (ValueError, AttributeError):
            pass
        return None

    def _fetch_redemption_schedule(self, fund_code: str) -> List[dict]:
        """从 jjfl_ 费率页解析赎回费率阶梯"""
        try:
            resp = requests.get(
                _FEE_URL.format(code=fund_code),
                headers=self._em_headers(fund_code),
                timeout=15,
            )
            resp.raise_for_status()
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(resp.text, 'lxml')
            anchor = soup.find('a', {'name': 'shfl'})
            if not anchor:
                return []
            fee_table = anchor.parent.parent.next_sibling.next_sibling
            feeinfo = [
                cell.get_text(strip=True)
                for row in fee_table.find_all('tr')
                for cell in row.find_all('td')
                if cell.get_text(strip=True) != '---'
            ]
            if not feeinfo or len(feeinfo) % 2 != 0:
                return []
            for item in feeinfo:
                if '开放期' in item or '封闭' in item or '开放日期' in item or '运作期' in item:
                    return []
            return self._parse_redemption_schedule(feeinfo)
        except Exception as e:
            self.logger.warning(f'基金 {fund_code} 赎回费率解析失败: {e}')
            return []

    @staticmethod
    def _parse_redemption_schedule(feeinfo) -> List[dict]:
        """
        将赎回费率列表解析为结构化阶梯。

        格式: ['小于7天', '1.50%', '大于等于7天，小于30天', '0.75%', ...]
        解析后: [{"start_day": 0, "end_day": 7, "rate": 1.5}, ...]
        """
        schedule = list()
        if not isinstance(feeinfo, list) or len(feeinfo) < 2:
            return schedule

        import re

        for i in range(0, len(feeinfo), 2):
            if i + 1 >= len(feeinfo):
                break

            desc = feeinfo[i]
            rate_str = feeinfo[i + 1]

            # 解析费率百分比
            try:
                rate = float(rate_str.rstrip('%'))
            except (ValueError, AttributeError):
                continue

            # 解析天数区间
            numbers = re.findall(r'\d+', desc)
            if not numbers:
                continue

            if '大于等于' in desc and '小于' in desc:
                start = int(numbers[0])
                end = int(numbers[1]) if len(numbers) > 1 else None
            elif '小于' in desc:
                start = 0
                end = int(numbers[0])
            elif '大于等于' in desc:
                start = int(numbers[0])
                end = None
            else:
                continue

            schedule.append({'start_day': start, 'end_day': end, 'rate': rate})

        return schedule
