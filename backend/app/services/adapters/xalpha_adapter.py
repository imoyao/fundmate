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
from typing import Any, Dict, List, Optional, Tuple

import requests
from loguru import logger

from app.services.adapters.base import DataSourceAdapter


def validate_redemption_schedule(schedule: List[dict]) -> List[str]:
    """赎回阶梯**结构校验**：返回问题清单，空列表表示阶梯可用。

    ## 为什么是模块级函数、不是类方法

    写侧（``FundService.apply_redeem_schedule``）需要它，而测试会整体替换
    ``XalphaAdapter`` 类符号；校验挂在类上时，那次替换会把校验也变成 Mock——
    返回值 truthy，于是「合法阶梯被拒写」这种假失败会伪装成代码 bug。
    校验是纯函数，跟适配器的网络能力无关，不该挂在会被替换的类上。

    ## 判定口径（2026-10-18 实测根因）

    写侧**失败即拒写**（fail closed）：费率缺失最多让用户手填，而一份内部矛盾、
    会把赎回费算成 0 的阶梯一旦落库就成了「权威数据」——界面看起来完全正常，
    错的只有金额（本机 245 只基金正是这么坏的）。

    拒写的情形：
      · 同区间出现两次（旧解析缺陷的直接产物，界面表现为「每档显示两次」）；
      · ``end_day <= start_day``（持有天数永远匹配不上，等于费率 0）；
      · 阶梯没覆盖 0 天起（持有 0 天的份额落到空档）；
      · 区间互相重叠（取哪个档取决于行序，金额不确定）。
    """
    problems: List[str] = []
    if not schedule:
        return problems  # 空阶梯 = 上游没给，调用方直接跳过写入，不算错误

    normalized: List[Tuple[int, Optional[int]]] = []
    for idx, item in enumerate(schedule):
        try:
            start = int(item['start_day'])
            raw_end = item.get('end_day')
            end = None if raw_end is None else int(raw_end)
            rate = float(item['rate'])
        except (KeyError, TypeError, ValueError):
            problems.append(f'第 {idx} 档字段缺失或类型非法: {item!r}')
            continue
        if start < 0:
            problems.append(f'第 {idx} 档起始天数为负: {start}')
        if end is not None and end <= start:
            problems.append(f'第 {idx} 档区间非法（end_day <= start_day）: {item!r}')
        if not (0 <= rate <= 100):
            problems.append(f'第 {idx} 档费率不在 0~100% 内: {rate}')
        normalized.append((start, end))

    if not normalized:
        return problems

    if min(s for s, _ in normalized) != 0:
        problems.append('阶梯未覆盖 0 天起：持有 0 天的份额匹配不到档位，赎回费会被算成 0')

    seen_ranges = set()
    for start, end in normalized:
        if (start, end) in seen_ranges:
            problems.append(f'区间重复: [{start}, {end})')
        seen_ranges.add((start, end))

    ordered = sorted(normalized, key=lambda t: (t[0], t[1] if t[1] is not None else float('inf')))
    prev_end: Optional[float] = None
    for start, end in ordered:
        if prev_end is not None and start < prev_end:
            problems.append(f'区间与上一档重叠（上界 {int(prev_end)} > 本档起点 {start}）')
            break
        prev_end = float('inf') if end is None else float(end)

    return problems


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
        # 沿用原 create_app 中的后端缓存配置。原先在应用启动期 import xalpha（约 1.4s），
        # 现已改为首次需要 xalpha 时（即本方法）才设置，避免拖慢启动/reload。
        from pathlib import Path

        import xalpha as xa

        Path('data/xalpha_cache').mkdir(parents=True, exist_ok=True)
        xa.set_backend(backend='csv', path='data/xalpha_cache')
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
        """获取指定日期的单位净值，失败返回 None。

        货币基金（Data.SYType == '每万份收益'）：lsjz 接口返回的是每万份收益而非
        单位净值，货币基金单位净值恒为 1.0，直接返回 1.0。
        """
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
            data_payload = data.get('Data')
            if not isinstance(data_payload, dict):
                return None
            if data_payload.get('SYType') == '每万份收益':
                return 1.0
            records = data_payload.get('LSJZList') or []
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
        """lsjz 日期范围增量拉取（含分页），无数据返回 []。

        货币基金在 lsjz 接口返回的是每万份收益（Data.SYType == '每万份收益'），
        与普通基金的单位净值语义不同，这里直接返回空列表，让调用方回退到
        pingzhongdata 的货币基金解析路径（见 fetch_fund_nav）。
        """
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
            if data_payload.get('SYType') == '每万份收益':
                # 货币基金：该接口返回万份收益而非单位净值，交由 pingzhongdata 路径处理
                return []
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

    # 持有期限单位 → 天。天天基金费率页混用「天」与「年」（个别用「月」），
    # 旧解析只认纯数字，于是「大于30天，小于等于2年」被当成「0~2天」——2 年变 2 天。
    _HOLD_UNIT_DAYS = {'年': 365, '个月': 30, '月': 30, '天': 1, '日': 1}
    _NUM_UNIT_RE = re.compile(r'(\d+)\s*(个月|年|月|天|日)')

    @classmethod
    def _parse_holding_range(cls, desc: str) -> Optional[Tuple[int, Optional[int]]]:
        """把费率页的「适用期限」文案解析成半开区间 ``[start_day, end_day)``（单位：天）。

        ## 为什么整段重写（2026-10-18 实测根因）

        页面写法有两种，旧版只认其中一种：

        - 旧写法「大于等于7天，小于30天」→ 命中 ``大于等于`` + ``小于`` 分支，正确；
        - **现写法「大于7天，小于等于30天」** → 含「小于」却不含「大于等于」，落进
          ``elif '小于' in desc`` 分支，起点被抹成 0，写成了 ``(0, 30)``。

        后果有两层，都不是显示层的小毛病：

        1. ``(0, 7, 1.5%)`` 与 ``(0, 7, 0.75%)`` 同时存在 → 费率分布弹窗每档显示两次；
        2. 正确档位被覆盖，而 ``estimate_redeem_fee._calc`` 取**首个匹配**——持有
           200 天的份额匹配不到任何档，赎回费被估成 **0**。本机实测 245 只基金的
           阶梯在结构上已经损坏（12 只同区间多行、7 只「年」被当「天」）。

        ## 上界语义

        本仓 ``end_day`` 是**不含**上界（界面文案「0~7天(不含)」），而页面写「小于等于N」，
        所以 ``小于等于N`` 要落成 ``end_day = N + 1``，``小于N`` 才是 ``N``。
        """
        text = desc.replace(' ', '').replace('（', '(').replace('）', ')')
        start: Optional[int] = None
        end: Optional[int] = None
        for part in re.split(r'[，,、]', text):
            m = cls._NUM_UNIT_RE.search(part)
            if not m:
                continue
            value = int(m.group(1)) * cls._HOLD_UNIT_DAYS[m.group(2)]
            # 顺序要紧：「大于等于」必须排在「大于」之前，「小于等于」排在「小于」之前
            if '大于等于' in part:
                start = value
            elif '大于' in part:
                start = value + 1
            elif '小于等于' in part:
                end = value + 1
            elif '小于' in part or '不满' in part or '少于' in part:
                end = value
        if start is None and end is None:
            return None
        return (0 if start is None else start, end)

    @staticmethod
    def _parse_redemption_schedule(feeinfo) -> List[dict]:
        """将赎回费率列表解析为结构化阶梯（``rate`` 保持**百分数**，由写入侧除以 100）。

        输入是费率页「适用期限 / 赎回费率」两列拍平后的序列::

            ['小于等于7天', '1.50%', '大于7天，小于等于30天', '0.75%', ...]

        区间与单位的坑见 :meth:`_parse_holding_range`（2026-10-18 实测根因）。
        """
        schedule: List[dict] = []
        if not isinstance(feeinfo, list) or len(feeinfo) < 2:
            return schedule

        for i in range(0, len(feeinfo) - 1, 2):
            desc = str(feeinfo[i])
            try:
                rate = float(str(feeinfo[i + 1]).rstrip('%').strip())
            except ValueError:
                continue
            parsed = XalphaAdapter._parse_holding_range(desc)
            if parsed is None:
                logger.debug(f'费率页持有期限无法解析，跳过该档: {desc!r}')
                continue
            start_day, end_day = parsed
            schedule.append({'start_day': start_day, 'end_day': end_day, 'rate': rate})

        # 首档下界归一：不少基金的页面首档写「大于等于1天，小于7天」（T+1 确认，最短
        # 持有 1 天，如 001678 / 001741 / 001880）。它的语义就是「不满 7 天的惩罚档」，
        # 若原样按 start_day=1 落库，持有 0 天的份额匹配不到任何档 → 赎回费算成 0。
        # 故把「首档且下界为 1」归一到 0；下界 ≥2（定开型等）不动，那属于产品规则，
        # 由 validate_redemption_schedule 判为不可用并拒写。
        if schedule:
            first = min(range(len(schedule)), key=lambda i: schedule[i]['start_day'])
            if schedule[first]['start_day'] == 1:
                schedule[first]['start_day'] = 0

        return schedule
