# -*- coding: utf-8 -*-
"""指数日线点位同步任务（#275 基准对比 / #861 绩效分析底座）。

四路数据源（**先按代码显式指派、再按后缀兜底**，同一个 Job 内）：
- **万得系**（`.WI` 后缀）→ 韭圈儿公开接口（JiucaishuoAdapter，免登录 best-effort）。
  **例外**：`885002.WI` 在韭圈儿未收录，改由万得官方 MCP 取真实收盘
  （`WIND_MCP_INDEX_CODES` + `adapters/wind_index.py`，2026-10-23 实测 5537 条）。
  点位口径双模式（**仅韭圈儿路**）：
  - anchored：有真实收盘锚（如 881001 万得全A），反推派生、锚随最新收盘平移；
  - normalized：无估值锚的指数（885 系基金指数等）起点归一化 1000，逐日确定不漂移。
  口径与风险细节见 jiucaishuo_adapter.py 模块注释。万得 MCP 路是 `raw`（真实点位），
  **不参与**上面两种口径 —— 三种口径混在同一序列里会拼出凭空涨跌（同族教训 #2464）。
- **交易所指数**（`.SH` / `.SZ` 后缀）→ 腾讯日线直连（`adapters/direct_feeds.py`，
  2026-10-01 引入）。点位为**真实收盘价**，口径 `price_mode='raw'`。
- **中证专属码**（`.CSI` 后缀）→ 中证指数官网（`fetch_daily_csindex`，2026-10-14
  为 #167 基准补齐引入）。点位同为真实收盘、口径 `raw`。
  为什么必须单开这一路：**腾讯源没有中证专属码**（932000 实测 sh/sz 两形态均 0 行，
  而同期的 sh000852 正常），不是限流而是源侧不存在。
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
- 中证专属码（CSINDEX_INDEX_TARGETS）：**不分增量/全量**——中证官网一次请求即返回全序列
  （实测 932000 成立以来 773 条），做增量优化的收益是零；upsert 幂等，重跑无副作用。
"""

from datetime import date, timedelta
from typing import List, Optional

from loguru import logger

from app.domains.indices.models import IndexDaily
from app.services.adapters import wind_index
from app.services.adapters.direct_feeds import fetch_daily_csindex, fetch_daily_tencent
from app.services.job_base import JobStatus, SyncJob

# 万得系指数目标清单（#275 定稿）：韭圈儿 gu_code 原生形态（.WI 后缀）。
# 来源：#275 2022 年评论梳理的「适用性广泛」万得基金系列指数 + 万得全A；
# 新增品种在此追加一行即可（接口通用，无每指数特判）。
# 可用性（2026-09-09 实测）：✅=韭圈儿已收录可取；⏳=韭圈儿暂未收录（detail 无序列），
# 保留在清单中——收录后自动生效（每日增量 warning 即跟进信号）。
# ⚠️ `885002.WI` 已改走万得 MCP（见下方 `WIND_MCP_INDEX_CODES`），此处保留行只为
# 「清单 = 我们跟踪哪些指数」这一件事，**不代表**数据源归属。
WIND_INDEX_TARGETS: List[tuple] = [
    ('881001.WI', '万得全A'),  # ✅ anchored 6464 条
    # 以下 4 只宽基/风格指数为 2026-09-09 复核补齐（用户在韭圈儿页面可见，此前漏抓）
    ('881003.WI', '万得全A(除金融、石油石化)'),  # ✅ anchored（12月239条）
    ('881007.WI', '万得300除金融'),  # ✅ anchored（12月242条）
    ('8841425.WI', '万得小市值指数'),  # ✅ anchored（12月186条；源侧序列短于同期242，待观察）
    ('8841431.WI', '万得微盘股指数'),  # ✅ normalized（12月242条，源未给收盘锚）
    ('885000.WI', '万得普通股票型基金指数'),  # ✅ normalized 5503 条
    ('885001.WI', '万得偏股混合型基金指数'),  # ✅ normalized 5508 条
    ('885002.WI', '万得平衡混合型基金指数'),  # ✅ 万得 MCP（WIND_MCP_INDEX_CODES）
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

# ── 中证官网目标清单（#167 基准补齐，2026-10-14 引入）──────────────────────────
# 中证专属码（932xxx / 930x50 一类）**腾讯源不存在**：实测 sh932000 / sz932000 均 0 行，
# 而 sh000852 正常有数据 —— 不是限流，是源侧没有这个代码。故单开一路走中证官网
# （`fetch_daily_csindex`，一次请求给全序列，无需分页）。
# 代码形态 `.CSI` 与 index_catalog 的 exchange='CSI' 命名空间一致，且与腾讯/万得的
# `.SH` / `.WI` 后缀在**字符串层面**即可分流（不看前缀、不做正则）。
CSINDEX_INDEX_TARGETS: List[tuple] = [
    ('932000.CSI', '中证2000'),  # ✅ 2026-10-14 实测 773 条（2023-08-01 起，成立以来）
    # 债券族基准（#167 收尾）：中证全债此前被记为「无公开行情通道」缺口（见下方
    # TENCENT_INDEX_TARGETS 的债券段注释），2026-10-14 实测中证官网可直取 5287 条
    # （2005-01-04 起，真实收盘）⇒ 用 `.CSI` 路补上。它替换了原先挂在映射上、却
    # 因韭圈儿未收录而永远取不到序列的 `885005.WI`（见 `fund_benchmark.BENCH_BOND_FUND`）。
    ('H11001.CSI', '中证全债指数'),  # ✅ 2026-10-14 实测 5287 条（2005 起）
]

DEFAULT_TARGETS = [code for code, _name in WIND_INDEX_TARGETS + TENCENT_INDEX_TARGETS + CSINDEX_INDEX_TARGETS]

# ── 数据源归属（同后缀 ≠ 同源）────────────────────────────────────────────────
# `.WI` 只是代码形态，**不决定数据源**。`885002.WI`（万得平衡混合型基金指数）在韭圈儿
# **未收录**（2026-10-21 实测 `disabled=True` / `data={}` / `series` 长度 0），但万得
# 官方 MCP **可取真实收盘**（2026-10-23 实测 5537 条，2003-12-31 起，2026-10-22 收
# 7206.3199）。`#2476` 曾把它记成「源侧没有这个指数」，实际是「我们没接这条源」——
# 归因错了差点把映射换成语义不符的 `H11022.CSI`（万得平衡混合型 ≠ 中证红利低波）。
#
# 为什么是**显式清单**、而不是「韭圈儿失败就自动回退万得」：运行时回退会在某天韭圈儿
# 恢复时**静默换源**，而两条源**不是同一尺度**（2026-10-23 实测同日同码：
# `885001.WI` 韭圈儿 925.6 / 万得 10877.345；`885000.WI` 935.7 / 14769.2608）——
# 拼接后就是一段凭空涨跌（同族教训 #2464）。源归属必须是代码里的常量，不是当天谁先失败。
WIND_MCP_INDEX_CODES: frozenset = frozenset({'885002.WI'})

# ── 源侧「确实未收录」的代码清单（#2475）──────────────────────────────────────
# 判据不是「猜」，是 2026-10-21 逐码实测：**韭圈儿** fundindex/detail 返回 HTTP 200 +
# `code=0`，但 `data={}` / `tb_data.x_data=None` / `series` 长度 0，且 index-basic 带
# `disabled=True`；同时 `index_daily` 表这些码**一行历史都没有**。
#
# ⚠️ 这里的「未收录」**只指韭圈儿**，不等于万得没有：`885002.WI` 已证万得可取
# （见上方 `WIND_MCP_INDEX_CODES`）。说「源侧没有」时必须说清是哪条源，否则下一个人
# 会重演 #2476 的误判 —— 把「我们没接」当成「数据不存在」。
#
# 保留在 WIND_INDEX_TARGETS 里是刻意的：韭圈儿收录后自动生效，无需改代码。
# 但它们不该每天记一条 error —— 每天 7 条「假故障」会把 `errors` 变成噪音，
# 真出故障时没人看得出（红灯一旦常态化就没人看）。
# 降级为 info 并单独计数（`stats['unlisted']`），失败明细仍可查。
KNOWN_UNLISTED: frozenset = frozenset(
    {
        '885005.WI',  # 万得债券型基金指数
        '885006.WI',  # 万得混合债券型一级基金指数
        '885008.WI',  # 万得中长期纯债型基金指数
        '885072.WI',  # 万得混合型FOF指数
        '885073.WI',  # 万得偏股混合型FOF指数
        '885074.WI',  # 万得平衡混合型FOF指数
        '885075.WI',  # 万得偏债混合型FOF指数
    }
)


class IndexDailySyncJob(SyncJob):
    batch_size = 5  # 每目标 2 个 HTTP 请求，batch 无需大

    @property
    def _allow_empty_data(self) -> bool:
        # 数据源失败/非交易日返回空时静默跳过，不阻断整体同步
        return True

    def get_name(self) -> str:
        return 'index_daily'

    @staticmethod
    def _resolve_targets(targets: List[str]) -> List[str]:
        """`'__full__'` 是编排器的全量占位符，不是真实代码；空清单即取默认全清单。"""
        return [t for t in targets if t != '__full__'] or DEFAULT_TARGETS

    def _count_total(self, targets: Optional[List[str]], fetched: int) -> int:
        """分母 = 本次真的会去试的代码数（`'__full__'` 展开；`targets=None` 也取默认全清单）。

        未收录的码（现 7 个）照样算进分母（「试过了，韭圈儿没有」是事实），但不进
        `failed` / `errors` —— 它们不是故障（#2475）。
        """
        return len(self._resolve_targets(targets or []))

    def _decide_final_status(self) -> JobStatus:
        """**全部**目标都失败才判 FAILED；部分失败保留 SUCCESS（#2475）。

        这是基类兜底的**更严口径**，保留覆盖的理由：本 job 的 `_count_total` 把源侧
        未收录、因而不记 failed 的代码也计进分母（`total > 可失败目标数`），于是基类那句
        `failed >= total` 在这里永远不会成立 —— 若删掉本方法，「30 个已收录目标全挂 +
        7 个韭圈儿未收录」会退回假绿。基类口径见 `SyncJob._decide_final_status`（#2495）。

        为什么部分失败不红：本 job 每天跑，30+ 个目标里偶发单点抖动是常态，
        「有一个挂掉就红」会让它天天红；红灯常态化的代价是真故障被淹没
        （同族教训见 #1179 / #171）。失败明细仍通过 `stats['failed']` 与 `errors`
        落在 sync_logs 里，排查时看得见。

        为什么全部失败必须红：那是数据源整体不可用，与「今天没有新数据」是两件事
        —— 后者是本 job 合法状态（非交易日 / 源侧未收录），前者必须有人知道。
        """
        failed = self._failed_target_count()
        if failed and not self.stats.get('success'):
            self.logger.error(f'{failed} 个指数日线目标全部失败，判定为 FAILED')
            return JobStatus.FAILED
        return JobStatus.SUCCESS

    # ── 抓取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        codes = self._resolve_targets(targets)
        names = dict(WIND_INDEX_TARGETS + TENCENT_INDEX_TARGETS + CSINDEX_INDEX_TARGETS)
        out = []
        for code in codes:
            code = code.strip()
            if not code:
                continue
            if code.upper().endswith('.CSI'):
                item = self._fetch_csindex_target(code, names.get(code, code), full_sync)
                if item:
                    out.append(item)
            elif code.upper().endswith('.WI'):
                if code.upper() in WIND_MCP_INDEX_CODES:
                    # 韭圈儿未收录、万得 MCP 可取：源归属是常量，不做运行时回退
                    item = self._fetch_wind_mcp_target(code, names.get(code, code), full_sync)
                    if item:
                        out.append(item)
                    continue
                # 万得系（韭圈儿）：全量取成立来（date='all'）；增量拉近 12 月（自愈缺口，2 请求/目标）
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
                    if code in KNOWN_UNLISTED:
                        # 源侧确实没有这只（#2475 实测 disabled=True / data={}）：
                        # 不是故障，降级 info 且不进 errors，只计数
                        self.stats['unlisted'] = self.stats.get('unlisted', 0) + 1
                        self.logger.info(f'指数日线 {code} 源侧未收录（已知），跳过: {e}')
                        continue
                    # 单目标失败不阻断其他目标（best-effort 数据源，fallback 见 #275）
                    self.logger.warning(f'指数日线 {code} 获取失败: {e}')
                    # #1833：记 errors —— 否则 targets 非空时基类一律记 success，
                    # 「全部目标失败」与「今天没数据」在 sync_logs 里完全同形。
                    self.stats.setdefault('errors', []).append(
                        {'gu_code': code, 'stage': 'fetch_daily', 'error': str(e)}
                    )
            else:
                item = self._fetch_tencent_target(code, names.get(code, code), full_sync)
                if item:
                    out.append(item)
        return out

    def _fetch_csindex_target(self, code: str, name: Optional[str], full_sync: bool) -> Optional[dict]:
        """中证官网指数（`.CSI` 后缀）：真实收盘，`price_mode='raw'`。

        与腾讯路的差别只有「源」：中证官网**一次请求返回全序列**（实测 932000 成立以来
        773 条），故没有分页，也没有 `start_date` 定界的坑——增量与全量是同一个请求，
        幂等 upsert 自行去重（重跑不产生副作用）。全量/增量的区分在此**不改变行为**，
        这是刻意的：为一个 1 请求的接口做增量优化，收益是零。
        """
        rows = fetch_daily_csindex(code.rsplit('.', 1)[0])
        if not rows:
            self.logger.warning(f'指数日线 {code}({name or code}) 中证官网无数据，跳过')
            return None
        return {
            'gu_code': code,
            'gu_name': name or code,
            'source': 'csindex',
            'price_mode': 'raw',
            'rows': [{'trade_date': date.fromisoformat(d), 'close': close} for d, close in rows],
        }

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

    def _fetch_wind_mcp_target(self, code: str, name: Optional[str], full_sync: bool) -> Optional[dict]:
        """万得 MCP 路（`WIND_MCP_INDEX_CODES`）：真实收盘，`price_mode='raw'`。

        与另两路的差别只有「源」与「口径」：
        - `source='wind'` / `price_mode='raw'`（真实点位，非反推锚、非归一化）；
        - 全量/增量都是**一次请求**（上游按日期区间返回，实测全历史 5537 条），
          与中证官网同理，增量优化的收益是零。

        降级语义（#2476 / §9）：**未配置**（缺 Token 或地址）只记 `stats['degraded']` +
        warning，不记 errors —— 「可选组件没配」不是数据源故障；但**绝不静默返回空**，
        否则前端「暂无基准」会被当成「这只指数没有数据」。配置了却失败则照常进 errors。
        """
        if not wind_index.is_available():
            self.stats['degraded'] = self.stats.get('degraded', 0) + 1
            self.logger.warning(
                f'指数日线 {code} 需要 Wind MCP，但 WIND_MCP_TOKEN / WIND_MCP_URL 未配置，本次跳过（降级，不当作无数据）'
            )
            return None
        try:
            rows = wind_index.fetch_index_daily(code, full_sync=full_sync)
        except Exception as e:
            # 配置齐了还失败 = 真故障（鉴权 / 额度 / 上游形态变更），必须进 errors
            self.logger.warning(f'指数日线 {code} Wind 取数失败: {e}')
            self.stats.setdefault('errors', []).append({'gu_code': code, 'stage': 'fetch_daily_wind', 'error': str(e)})
            return None
        if not rows:
            self.logger.warning(f'指数日线 {code}({name or code}) Wind 无数据，跳过')
            return None
        return {
            'gu_code': code,
            'gu_name': name or code,
            'source': 'wind',
            'price_mode': 'raw',
            'rows': rows,
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
