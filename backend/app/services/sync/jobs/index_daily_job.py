# -*- coding: utf-8 -*-
"""指数日线点位同步任务（#275 基准对比 / #861 绩效分析底座）。

两路数据源（按代码后缀分流，同一个 Job 内）：
- **万得系**（`.WI` 后缀）→ 韭圈儿公开接口（JiucaishuoAdapter，免登录 best-effort）。
  点位口径双模式：
  - anchored：有真实收盘锚（如 881001 万得全A），反推派生、锚随最新收盘平移；
  - normalized：无估值锚的指数（885 系基金指数等）起点归一化 1000，逐日确定不漂移。
  口径与风险细节见 jiucaishuo_adapter.py 模块注释。
- **交易所指数**（`.SH` / `.SZ` 后缀）→ 腾讯日线直连（`adapters/direct_feeds.py`，
  2026-10-01 引入）。点位为**真实收盘价**，口径 `price_mode='raw'`。
  为什么必须补这一路：韭圈儿只覆盖万得系，而绩效对比最常用的基准（沪深300 / 中证500
  / 创业板指…）是交易所指数——它们在 `index_daily` 里原先**一行都没有**，只能靠
  `market_service` 每次向 akshare 现拉（不落库、无历史序列，无法做跨年对比）。
  东财 push2his 不做备选：2026-10-01 实测**首次 200、第二次起即 RemoteDisconnected**
  （突发配额后限流），12 个目标根本跑不完。

写入语义：按 (index_code, trade_date) **upsert**（覆盖同日），非名录那种整体
重建——日线序列应只增不改（反推锚点平移会导致全序列微小漂移，重跑全量
以最新锚点为准，属预期行为）。

目标与增量策略：
- 万得系（WIND_INDEX_TARGETS）：全量取成立来（date='all'，万得全A 6464 条）；增量近 12 月。
- 交易所指数（TENCENT_INDEX_TARGETS）：全量分页翻到源侧耗尽（沪深300 约 7 页）；增量近 12 月。
"""

from datetime import date, timedelta
from typing import List, Optional

from loguru import logger

from app.domains.indices.models import IndexDaily
from app.services.adapters.direct_feeds import fetch_daily_tencent
from app.services.job_base import SyncJob

# 万得系指数目标清单（#275 定稿）：韭圈儿 gu_code 原生形态（.WI 后缀）。
# 来源：#275 2022 年评论梳理的「适用性广泛」万得基金系列指数 + 万得全A；
# 新增品种在此追加一行即可（接口通用，无每指数特判）。
# 可用性（2026-09-09 实测）：✅=韭圈儿已收录可取；⏳=暂未收录（detail 无序列），
# 保留在清单中——收录后自动生效（每日增量 warning 即跟进信号）。
WIND_INDEX_TARGETS: List[tuple] = [
    ('881001.WI', '万得全A'),  # ✅ anchored 6464 条
    # 以下 4 只宽基/风格指数为 2026-09-09 复核补齐（用户在韭圈儿页面可见，此前漏抓）
    ('881003.WI', '万得全A(除金融、石油石化)'),  # ✅ anchored（12月239条）
    ('881007.WI', '万得300除金融'),  # ✅ anchored（12月242条）
    ('8841425.WI', '万得小市值指数'),  # ✅ anchored（12月186条；源侧序列短于同期242，待观察）
    ('8841431.WI', '万得微盘股指数'),  # ✅ normalized（12月242条，源未给收盘锚）
    ('885000.WI', '万得普通股票型基金指数'),  # ✅ normalized 5503 条
    ('885001.WI', '万得偏股混合型基金指数'),  # ✅ normalized 5508 条
    ('885002.WI', '万得平衡混合型基金指数'),  # ⏳ 未收录
    ('885003.WI', '万得偏债混合型基金指数'),  # ✅ normalized 5502 条
    ('885005.WI', '万得债券型基金指数'),  # ⏳ 未收录
    ('885006.WI', '万得混合债券型一级基金指数'),  # ⏳ 未收录
    ('885007.WI', '万得混合债券型二级基金指数'),  # ✅ normalized 5503 条
    ('885008.WI', '万得中长期纯债型基金指数'),  # ⏳ 未收录
    ('889033.WI', '万得可转债等权指数'),  # ✅ normalized（12月239条，源未给收盘锚）
    ('885072.WI', '万得混合型FOF指数'),  # ⏳ 未收录
    ('885073.WI', '万得偏股混合型FOF指数'),  # ⏳ 未收录
    ('885074.WI', '万得平衡混合型FOF指数'),  # ⏳ 未收录
    ('885075.WI', '万得偏债混合型FOF指数'),  # ⏳ 未收录
]

# ── 交易所指数目标清单（腾讯源，2026-10-01 实测 12/12 可取）────────────────────
# 前 6 项与 `services/bias/constants.py::BENCHMARK_INDICES`（乖离率侧的宽基基准）**逐字对齐**，
# 由 tests 锁定一致性。**刻意不 import 那个常量**：那会让 sync 家族反向依赖 bias 家族，
# 与 `architecture.md` §6「家族包内只留该家族独有实现」相悖（守卫 R5 的立法意图）。
# 名称用「申万/交易所通称」而非公示全称；代码↔名称已用新浪 hq 快照逐只交叉核对
# （2026-10-01：12/12 名称与收盘价均可对上，无错配）。
# 债券基准用 000012.SH（上证国债指数）+ 399481.SZ（企债指数）两段近似：
# 常用的中证全债 **H11001 无公开行情通道**（腾讯 sh11001/sz11001 空、新浪返回空），
# 缺口单列，不用假数据顶替（data-strategy「参考展示类」口径，宁缺勿错）。
TENCENT_INDEX_TARGETS: List[tuple] = [
    ('000001.SH', '上证指数'),
    ('000016.SH', '上证50'),
    ('000300.SH', '沪深300'),
    ('000905.SH', '中证500'),
    ('000906.SH', '中证800'),
    ('000852.SH', '中证1000'),
    ('000688.SH', '科创50'),
    ('399001.SZ', '深证成指'),
    ('399005.SZ', '中小100'),
    ('399006.SZ', '创业板指'),
    ('399481.SZ', '企债指数'),
    ('000012.SH', '上证国债指数'),
]

DEFAULT_TARGETS = [code for code, _name in WIND_INDEX_TARGETS + TENCENT_INDEX_TARGETS]


class IndexDailySyncJob(SyncJob):
    batch_size = 5  # 每目标 2 个 HTTP 请求，batch 无需大

    @property
    def _allow_empty_data(self) -> bool:
        # 数据源失败/非交易日返回空时静默跳过，不阻断整体同步
        return True

    def get_name(self) -> str:
        return 'index_daily'

    # ── 抓取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        # '__full__' 是编排器的全量占位符，不是真实代码
        codes = [t for t in targets if t != '__full__'] or DEFAULT_TARGETS
        names = dict(WIND_INDEX_TARGETS + TENCENT_INDEX_TARGETS)
        out = []
        for code in codes:
            code = code.strip()
            if not code:
                continue
            if code.upper().endswith('.WI'):
                # 万得系：全量取成立来（date='all'）；增量拉近 12 月（自愈缺口，2 请求/目标）
                months = 'all' if full_sync else 12
                try:
                    out.append(
                        {
                            'gu_code': code,
                            'gu_name': names.get(code, code),
                            'source': 'jiucaishuo',
                            **self.adapter.fetch_index_daily(code, months),
                        }
                    )
                except Exception as e:
                    # 单目标失败不阻断其他目标（best-effort 数据源，fallback 见 #275）
                    self.logger.warning(f'指数日线 {code} 获取失败: {e}')
            else:
                item = self._fetch_tencent_target(code, names.get(code, code), full_sync)
                if item:
                    out.append(item)
        return out

    def _fetch_tencent_target(self, code: str, name: Optional[str], full_sync: bool) -> Optional[dict]:
        """交易所指数（腾讯源）：取到**带交易日**的日线，可直接落 index_daily。

        全量翻到成立以来（分页），增量取近 12 月——与万得系的口径对齐，便于两路混跑。
        """
        start_date = None if full_sync else date.today() - timedelta(days=365)
        rows = fetch_daily_tencent(code, start_date=start_date)
        if not rows:
            self.logger.warning(f'指数日线 {code}({name or code}) 腾讯源无数据，跳过')
            return None
        return {
            'gu_code': code,
            'gu_name': name or code,
            'source': 'tencent',
            # 腾讯给的是指数真实收盘价：既非韭圈儿的「反推派生锚」，也非「归一化 1000」，
            # 故单列 raw 口径，避免下游把三种口径混为一谈
            'price_mode': 'raw',
            'rows': [{'trade_date': date.fromisoformat(d), 'close': close} for d, close in rows],
        }

    # ── 校验 / 去重 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        out = []
        for item in raw_data:
            rows = item.get('rows') or []
            if not rows:
                self.logger.warning(f'指数日线 {item.get("gu_code")} 序列为空，跳过')
                continue
            out.append(item)
        return out

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 行内按 trade_date 去重（保留首现）；跨次运行靠 _save_data 的 upsert 覆盖
        for item in data:
            seen = set()
            rows = []
            for r in item['rows']:
                if r['trade_date'] in seen:
                    continue
                seen.add(r['trade_date'])
                rows.append(r)
            item['rows'] = rows
        return data

    # ── 落库（upsert）──

    def _save_data(self, new_data: List[dict]) -> None:
        for item in new_data:
            index_code = item['gu_code']
            price_mode = item.get('price_mode', 'anchored')
            # 2026-10-01 起本 job 是双源（韭圈儿 / 腾讯），source 不能再写死成 jiucaishuo
            source = item.get('source', 'jiucaishuo')
            rows = item['rows']
            existing = {
                r.trade_date: r
                for r in self.db.query(IndexDaily)
                .filter(
                    IndexDaily.index_code == index_code,
                    IndexDaily.trade_date.in_([r['trade_date'] for r in rows]),
                )
                .all()
            }
            inserted = updated = 0
            for r in rows:
                row = existing.get(r['trade_date'])
                if row is None:
                    self.db.add(
                        IndexDaily(
                            index_code=index_code,
                            trade_date=r['trade_date'],
                            close=r['close'],
                            ret_pct=r.get('ret_pct'),
                            source=source,
                            price_mode=price_mode,
                        )
                    )
                    inserted += 1
                else:
                    row.close = r['close']
                    row.ret_pct = r.get('ret_pct')
                    row.price_mode = price_mode
                    row.source = source
                    updated += 1
            self.db.commit()
            logger.info(f'指数日线 {index_code}({price_mode}): 新增 {inserted} / 更新 {updated}（共 {len(rows)} 条）')
