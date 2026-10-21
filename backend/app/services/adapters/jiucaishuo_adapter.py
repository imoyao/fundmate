# -*- coding: utf-8 -*-
"""韭圈儿（funddb.cn = jiucaishuo.com）指数数据适配器（#1365 / #275）。

数据源为公开 H5 接口（免登录、无签名），接口契约实测留档见
docs/working-notes/index-catalog-sources-research-2026-09-08.md「韭圈儿专项结论」。
决策修订记录：2026-09-08 曾定调「不逆向韭圈儿」；2026-09-09 实测确认
index-basic / fundindex/detail 为免登录公开端点（无签名机制），属公开源
best-effort 接入，非逆向。**稳定性风险自担**：私有接口可能无通知变更，
930950（中证偏股基金）/ 399317（国证A指）始终是权威 fallback。

接口（POST application/json）：
- /v2/guzhi-new2/index-basic   最新收盘价 + PE/PB/估值分位（免登录）
- /v2/fundindex/detail         近 N 月累计收益率序列（date=月数，上限 120=10 年）

万得全A（881001.WI）点位为**反推派生数据**：P(t) = P_now × (1+r(t)) / (1+r_end)。
口径为价格指数（非全收益）；锚点随最新收盘平移，区间越长累积误差越大——
每日增量自愈，不做跨年回测级依赖（回测口径另议，#275）。

健壮性约定（与 TiantianAdvisorAdapter 同源）：
- 模块级节流：相邻任意请求间隔 ≥ REQUEST_INTERVAL 秒；
- 指数退避重试：单接口最多 MAX_RETRIES 次，仍失败抛 RuntimeError 由上层容错；
- requests.Session 复用连接；UA/Referer 伪装为韭圈儿 H5 端（公开可见）。
"""

import json
import threading
import time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import requests
from loguru import logger

API_BASE = 'https://api.jiucaishuo.com'
API_BASIC = API_BASE + '/v2/guzhi-new2/index-basic'
API_DETAIL = API_BASE + '/v2/fundindex/detail'
# 行业恐贪 PH/TF 值（免登录，2026-10-20 逆向 APK 实测；JS 标记 need_login:!1）
API_EMOTION = API_BASE + '/v2/guzhi-new2/ins-emotion'
# 基金投资风格箱月度历史（免登录，2026-10-20 逆向 APK 实测；JS 标记 need_login:!1）
API_STYLE_HISTORY = API_BASE + '/v2/tubiao/get-style-history'
# 相似基金 + 相似度分（免登录，2026-10-21 实测 code=0；JS 标记 need_login:!1，#2480）
API_SIMILAR_FUNDS = API_BASE + '/v2/fund-lists/simfund'
# 行业 PB-ROE 散点（免登录，2026-10-21 实测 code=0；JS 标记 need_login:!1，#2481）
API_PBROE = API_BASE + '/v2/guzhi-new2/pbroe-sg2'

HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': (
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
    ),
    'Referer': 'https://app.jiucaishuo.com/',
}

REQUEST_INTERVAL = 2.0
MAX_RETRIES = 3
RETRY_BACKOFF = (2, 4, 8)
TIMEOUT = 25

# 韭圈儿 H5 端固定版本参数（公开抓包可见，无敏感信息）
COMMON_PAYLOAD = {'type': 'h5', 'version': '2.5.9', 'ss': ''}

# 'all' 模式下接口首点为 1970-01-01 占位伪点（实测，2026-09-09），必须剔除
PLACEHOLDER_DATE = '1970-01-01'

# 数据来源标记（落库/审计用）
EMOTION_SOURCE = 'jiucaishuo_industry'
SIMILAR_SOURCE = 'jiucaishuo_similar'
PBROE_SOURCE = 'jiucaishuo_pbroe'

_throttle_lock = threading.Lock()
_last_request_at = 0.0


def _opt_float(value: Any) -> Optional[float]:
    """宽松数值转换：None / 空串 / 不可解析一律 None（「未提供」不退化成 0）。"""
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class JiucaishuoAdapter:
    """韭圈儿指数数据适配器（独立于 akshare/xalpha 数据源体系）。"""

    def get_name(self) -> str:
        return 'jiucaishuo'

    def get_version(self) -> str:
        return '1.0.0'

    def __init__(self) -> None:
        self.logger = logger
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    # ── HTTP ──

    def _post(self, path: str, payload: dict) -> Dict[str, Any]:
        global _last_request_at
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        last_error: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            with _throttle_lock:
                wait = REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
                if wait > 0:
                    time.sleep(wait)
                try:
                    resp = self._session.post(
                        path if path.startswith('http') else API_BASE + path, data=body, timeout=TIMEOUT
                    )
                finally:
                    _last_request_at = time.monotonic()
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') != 0:
                    raise RuntimeError(f'{path} 业务失败: {data}')
                return data
            last_error = RuntimeError(f'{path} HTTP {resp.status_code}')
            backoff = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
            self.logger.warning(f'{path} 第 {attempt + 1} 次请求失败（{last_error}），{backoff}s 后重试')
            time.sleep(backoff)
        raise RuntimeError(f'{path} 重试 {MAX_RETRIES} 次仍失败: {last_error}')

    # ── 纯解析（便于单测，不触网） ──

    @staticmethod
    def parse_index_basic(resp: Dict[str, Any]) -> Dict[str, Any]:
        """解析 index-basic 响应 → {gu_name, close, pe, pb, pe_pct}。"""
        d = resp.get('data') or {}
        out: Dict[str, Any] = {'gu_name': d.get('gu_name')}
        for row in d.get('table') or []:
            name = row.get('name')
            try:
                if name == '收盘价':
                    out['close'] = float(row['new_value'])
                elif name == '市盈率':
                    out['pe'] = float(row['new_value'])
                    pct = (row.get('new_percent_value') or {}).get('value')
                    out['pe_pct'] = pct
                elif name == '市净率':
                    out['pb'] = float(row['new_value'])
            except (KeyError, TypeError, ValueError):
                continue
        # 基金指数（885xxx）无估值表、无收盘价属正常形态 → 调用方走 normalized 模式
        # 股票/宽基指数必有收盘价；若连宽基也缺收盘价，说明接口形态变更，
        # 由 fetch_index_daily 的 rows 为空校验兜底报错，不在解析层误杀
        return out

    @staticmethod
    def parse_return_series(resp: Dict[str, Any]) -> Tuple[List[str], List[float]]:
        """解析 fundindex/detail 响应 → (日期列表, 累计收益率%列表)。series[0]=本指数。"""
        tb = ((resp.get('data') or {}).get('tb_data')) or {}
        xs = tb.get('x_data') or []
        series = tb.get('series') or []
        if not xs or not series:
            raise ValueError('fundindex/detail 响应无序列数据（接口形态可能已变更）')
        rets = [float(v) for v in series[0].get('data') or []]
        if len(xs) != len(rets):
            raise ValueError(f'x_data({len(xs)}) 与 series({len(rets)}) 长度不一致')
        return [str(x) for x in xs], rets

    # ── 面向 Job 的高层接口 ──

    def fetch_index_daily(self, gu_code: str, months: int | str = 120) -> Dict[str, Any]:
        """获取指数点位序列（反推派生）+ 最新快照。

        返回 {gu_code, gu_name, snapshot, rows}；
        rows = [{'trade_date': 'YYYY-MM-DD', 'close': float, 'ret_pct': float}]。
        """
        basic_resp = self._post(
            API_BASIC,
            {'gu_code': gu_code, 'category': 'pe', 'year': 10, **COMMON_PAYLOAD},
        )
        basic = self.parse_index_basic(basic_resp)

        detail_resp = self._post(
            API_DETAIL,
            {
                'gu_code': gu_code,
                'date': months,
                'ben': '',
                'search_code': '',
                's_time': '',
                'e_time': '',
                'line_type': 'sy',
                'is_close': 2,
                **COMMON_PAYLOAD,
            },
        )
        xs, rets = self.parse_return_series(detail_resp)

        # 双模式（#275）：
        # - anchored：index-basic 有收盘价锚（股票/宽基指数如 881001）→ 真实点位，
        #   P(t) = P_now × (1+r(t)/100) / (1+r_end/100)，锚随最新收盘平移；
        # - normalized：基金指数（885xxx）无估值表 → 起点归一化 1000，
        #   P(t) = 1000 × (1+r(t)/100)，逐日确定不漂移（upsert 稳定）。
        #   基金指数对比只看相对涨跌，归一化满足用途；口径由 price_mode 标注。
        if 'close' in basic:
            price_mode = 'anchored'
            r_end = rets[-1]
            base = basic['close'] / (1 + r_end / 100)
        else:
            price_mode = 'normalized'
            base = 1000.0
        rows = []
        for x, v in zip(xs, rets):
            if x == PLACEHOLDER_DATE:
                # 'all' 模式首点为 1970-01-01 占位伪点（与真实首点同为 0），必须剔除
                continue
            try:
                trade_date = date.fromisoformat(x)
            except ValueError:
                self.logger.warning(f'无法解析日期 {x!r}，跳过该行')
                continue
            rows.append({'trade_date': trade_date, 'close': round(base * (1 + v / 100), 4), 'ret_pct': v})
        if not rows:
            raise ValueError('收益率序列解析后为空（日期格式可能已变更）')
        self.logger.info(
            f'韭圈儿 {gu_code} 序列 {len(rows)} 条（months={months}，{price_mode}），最新收盘 {basic.get("close")}'
        )
        return {
            'gu_code': gu_code,
            'gu_name': basic.get('gu_name'),
            'price_mode': price_mode,
            'snapshot': basic,
            'rows': rows,
        }

    def fetch_industry_emotion(self) -> List[Dict[str, Any]]:
        """行业恐贪 PH/TF 值列表（免登录，2026-10-20 逆向 APK 实测）。

        端点 /v2/guzhi-new2/ins-emotion：空参即可，JS 标记 need_login:!1（游客可访问）。
        返回 [{'name': '军工PH值', 'num': 42.0, 'color': ..., 'target_url': ...}, ...]；
        name 保留上游原文（不做本地枚举硬编码，上游改清单不影响解析）。
        """
        resp = self._post(API_EMOTION, dict(COMMON_PAYLOAD))
        rows = resp.get('data') or []
        if not rows:
            raise ValueError('ins-emotion 响应无数据（接口形态可能已变更）')
        return rows

    # ── 投资风格箱（晨星式 8 分类）月度历史 ──

    @staticmethod
    def parse_style_history(resp: Dict[str, Any]) -> Dict[str, Any]:
        """解析风格箱历史（纯函数，便于单测，不触网）。

        返回 ``{'dates': [...], 'styles': [{'name': ..., 'color': ..., 'values': [...]}, ...]}``。

        - ``dates`` 为上游日期轴（月末 + 当月最新点），原样保留；
        - ``styles`` 每条与日期轴**等长**（实测 000001：8 条 × 283 点）；
        - 每时点 8 个值合计 = 100（百分比暴露，0 表示该风格无暴露）；
        - ``name`` 保留上游原文（大盘成长/大盘价值/中盘成长/中盘价值/小盘成长/
          小盘价值/港股风格/固收风格），不做本地枚举硬编码。

        长度不一致即抛错：风格箱是「每序列对齐同一日期轴」的矩阵数据，
        对不齐说明接口形态已变更，静默截断会比失败更糟（错位数据无人察觉）。
        """
        data = resp.get('data') or {}
        dates = data.get('category_lists') or []
        series = data.get('info_lists') or []
        if not dates or not series:
            raise ValueError('风格箱历史响应无数据（接口形态可能已变更）')
        styles: List[Dict[str, Any]] = []
        for s in series:
            name = s.get('name')
            values = s.get('data') or []
            if not name:
                raise ValueError(f'风格序列缺少 name 字段（接口形态可能已变更）: {s!r:.200}')
            if len(values) != len(dates):
                raise ValueError(f'风格序列 {name!r} 与日期轴长度不一致（{len(values)} vs {len(dates)}，接口形态可能已变更）')
            styles.append({'name': name, 'color': s.get('color') or '', 'values': values})
        return {'dates': dates, 'styles': styles}

    def fetch_fund_style_history(self, fund_code: str) -> Dict[str, Any]:
        """拉取单只基金的投资风格箱月度全历史（免登录，2026-10-20 逆向 APK 实测）。

        端点 ``/v2/tubiao/get-style-history``：晨星式 8 分类风格箱，月度频率，
        覆盖基金成立起全历史（实测 000001：283 点，2003-04 起；货基 161 点；新基金 24 点）。

        ⚠️ ``cycle`` 必须传 ``'1y'``：实测 ``'all'`` **只返回近 37 点**（2023-10 起），
        ``'1y'``/``'3y'`` 才返回全量——参数名与实际语义相反，勿被名字误导。

        ⚠️ QDII 口径存疑：270042 广发纳指100 实测返回「固收风格 81.28 / 大盘成长 18.72」，
        海外资产映射明显不合理。落库原值 + 展示层注明来源；QDII 不作为风格筛选依据
        （见 fund_style_tag_feasibility.md §4）。
        """
        payload = {'fund_code': fund_code, 'category': '', 'cycle': '1y', **COMMON_PAYLOAD}
        parsed = self.parse_style_history(self._post(API_STYLE_HISTORY, payload))
        parsed['fund_code'] = fund_code
        self.logger.info(f'韭圈儿风格箱 {fund_code}: {len(parsed["dates"])} 时点 × {len(parsed["styles"])} 风格')
        return parsed

    # ── 相似基金（#2480）──

    @staticmethod
    def parse_similar_funds(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析相似基金响应 → [{fund_code, fund_name, similarity, income_1y_pct}, ...]。

        - ``similarity`` 取 ``sml_topn_fd``（0-100 相似度分）。上游**只给前若干名打分**，
          其余为 null——保持 None 不补 0：「没打分」与「得分 0」是两件事；
        - ``income_1y_pct`` 取 ``fund_income_12``（近 1 年收益率 %，字符串转 float）；
        - ``window`` 取上游 ``param``（如「近1年」），逐条原样带上；
        - ⚠️ ``fund_income_1000`` 字段**不透出**：三种候选口径（万份收益/成立以来/
          千元收益）经 2026-10-21 三组样本交叉验证全部不成立（货基组自相矛盾），
          语义未实证的数字不进公开响应——宁缺毋假。原始响应留契约文档备查；
        - 空 ``data`` 是合法形态（上游无相似基金），返回空列表；``data`` 键缺失
          （None）才是接口形态变更，抛错。
        """
        rows = resp.get('data')
        if rows is None:
            raise ValueError('simfund 响应无 data 字段（接口形态可能已变更）')
        items: List[Dict[str, Any]] = []
        for row in rows:
            code = row.get('fund_code')
            if not code:
                continue
            items.append(
                {
                    'fund_code': str(code),
                    'fund_name': row.get('fund_simple_name') or '',
                    'similarity': _opt_float(row.get('sml_topn_fd')),
                    'income_1y_pct': _opt_float(row.get('fund_income_12')),
                    'window': row.get('param'),
                }
            )
        return items

    def fetch_similar_funds(self, fund_code: str) -> Dict[str, Any]:
        """拉取单只基金的相似基金列表（免登录，2026-10-21 实测）。

        端点 ``/v2/fund-lists/simfund``：返回相似基金 + 相似度分 + 近 1 年收益对照。
        按需取、不落库（快照概念，实时性要求低；缓存在 service 侧，见 #2480）。

        上游返回结构见 :func:`parse_similar_funds`；调用方（service）负责降级——
        本方法在上游形态异常时抛错，由上层转成「空列表 + 降级标记」。
        """
        resp = self._post(API_SIMILAR_FUNDS, {'fund_code': fund_code, **COMMON_PAYLOAD})
        items = self.parse_similar_funds(resp)
        self.logger.info(f'韭圈儿相似基金 {fund_code}: {len(items)} 只')
        return {'fund_code': fund_code, 'items': items, 'source': SIMILAR_SOURCE}

    # ── 行业 PB-ROE 散点（#2481）──

    @staticmethod
    def parse_industry_pbroe(resp: Dict[str, Any]) -> Dict[str, Any]:
        """解析行业 PB-ROE 散点响应 → {title, x_label, y_label, update_time, series}。

        ``series`` = [{industry, roe, pb}, ...]（ROE 可负——房地产实测 -16.78，
        PB-ROE 模型下负盈利行业照样在图上，不做剔除）。

        ``update_time`` 为上游数据日期（实测与当日同步），原样透出——展示层
        据此标注「数据更新至 X」，不伪装成实时。
        """
        data = resp.get('data') or {}
        raw_series = data.get('series') or []
        if not raw_series:
            raise ValueError('pbroe-sg2 响应无 series（接口形态可能已变更）')
        points: List[Dict[str, Any]] = []
        for s in raw_series:
            name = s.get('name')
            if not name:
                continue
            points.append({'industry': name, 'roe': _opt_float(s.get('x1')), 'pb': _opt_float(s.get('y1'))})
        if not points:
            raise ValueError('pbroe-sg2 series 解析后为空（接口形态可能已变更）')
        return {
            'title': data.get('title') or 'A股行业PB-ROE',
            'x_label': data.get('_x') or 'ROE(%)',
            'y_label': data.get('_y') or 'PB',
            'update_time': data.get('update_time'),
            'series': points,
        }

    def fetch_industry_pbroe(self) -> Dict[str, Any]:
        """拉取全行业 PB-ROE 矩阵（免登录，2026-10-21 实测）。

        端点 ``/v2/guzhi-new2/pbroe-sg2``：一次请求拿申万一级全行业 ROE×PB。
        结构见 :func:`parse_industry_pbroe`。
        """
        parsed = self.parse_industry_pbroe(self._post(API_PBROE, dict(COMMON_PAYLOAD)))
        self.logger.info(f'韭圈儿行业 PB-ROE: {len(parsed["series"])} 个行业（更新 {parsed["update_time"]}）')
        return parsed
