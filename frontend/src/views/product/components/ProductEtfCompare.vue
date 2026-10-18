<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch
} from "vue";
import { RouterLink } from "vue-router";
import {
  fetchIndexEtfCompare,
  type IndexEtfCompareResult,
  type IndexEtfCompareRow,
  type IndexEtfCompareWindows
} from "@/api/products";
import { productRoute } from "@/utils/productIdentity";

/**
 * 详情页「关联 ETF 对比表」子区块（#2275 · P0）：同指数场内 ETF 的购买决策横向比较。
 *
 * ## 为什么是表
 *
 * 同跟踪一只指数的 ETF 收益几乎同质，**费率差即净收益差、规模决定冲击成本**；
 * 用户此前只能逐只跳第三方比较（#2275 背景）。P0 给：最新净值 / 当日涨幅 /
 * 成交额 / 近 1·3·6·12 月涨跌幅 / 跟踪差；#2333 补上规模与运行费率两列
 * （东财 F10 + 同花顺双源 + 小表缓存，后端 etf_scale_fee 服务）。
 *
 * #2334（形态 B）：对比表**上方**加「优选 ETF」小卡区块——后端按跟踪差降序、
 * 门槛内取前三算好 `recommend_rank`（1/2/3），前端最多展示 3 只、第 1 名品牌色
 * 突出；`recommend_rank` 全为 null 时**整块不渲染**（不是空壳标题）。
 *
 * ## 口径与降级
 *
 * - ETF 清单来自本地 `channel_links`（名称匹配建链，覆盖率约 66.4%，#1419）——
 *   对比表**继承该边界**，列不全是数据源边界而非缺陷；无关联 → 整块不渲染
 *   （父组件按 `peer_role === "etf"` 决定挂载）；
 * - 净值止于 T-1（与 `fund_nav_job` 同纪律）；当日涨幅/成交额为新浪现货快照
 *   （东财 spot 实测 push2delay 不可靠，2026-10-17 三连挂）；
 * - **跟踪差 = ETF 近 1 年涨幅 − 指数近 1 年涨幅**：ETF 用场内价格（含折溢价
 *   噪声），是购买决策的粗粒度贴合度参考，**非严格跟踪误差**（title 标注）；
 * - 优选小卡的跟踪差与表内同源同口径，缺失显「—」；
 * - 任一字段失败 → 「—」，不阻塞整表。
 *
 * 本组件是 ProductRelatedSection 的**子区块**（同卡内渲染）。
 */
const props = defineProps<{
  /** 指数代码（裸 6 位码或带前缀形态，后端归一） */
  symbol: string;
}>();

const DASH = "—";

const loading = ref(false);
const failed = ref(false);
const data = ref<IndexEtfCompareResult | null>(null);

const rows = computed(() => data.value?.rows ?? []);

/** 有任何一行存在即渲染（哪怕行情字段全降级，表壳 + 名称/跳转仍有价值） */
const hasRows = computed(() => rows.value.length > 0);

// ── 优选小卡（#2334 形态 B）────────────────────────────────────────
// 后端按「跟踪差降序、门槛内 Top3」算好 recommend_rank（1/2/3）；null = 不参评。

/** 优选行：参评行按名次升序、至多 3 只（后端契约本就是 Top3，截断是防御） */
const recommendRows = computed(() => {
  const picks = rows.value
    .filter(
      (row): row is IndexEtfCompareRow & { recommend_rank: number } =>
        row.recommend_rank != null
    )
    .sort((a, b) => a.recommend_rank - b.recommend_rank)
    .slice(0, 3);
  return picks.map(row => ({
    code: row.code,
    name: row.name,
    rank: row.recommend_rank,
    tracking: row.tracking_diff_y1,
    route: productRoute({ assetType: "etf", symbol: row.code })
  }));
});

/** 渲染门禁（失败态铁律）：至少一行参评才画整块；全 null 时整块消失、不留空壳标题 */
const hasRecommend = computed(() => recommendRows.value.length > 0);

/** 名次称谓：第 1 名带「优选」前缀突出，2/3 名只标名次 */
function recommendLabel(rank: number): string {
  return rank === 1 ? "优选 · 第 1" : `第 ${rank}`;
}

/** 指数基准行：任一窗口有值才渲染（全 null 时画一行「—」没有信息量） */
const indexBaseline = computed<IndexEtfCompareWindows | null>(() => {
  const w = data.value?.index_returns;
  if (!w) return null;
  return WINDOWS.some(x => w[x.key] != null) ? w : null;
});

// ── 横向滚动的右缘渐隐 ───────────────────────────────────────────────
// 仅在真的可滚且未滚到尽头时显示遮罩：常显的渐隐会让人以为表格被截断。
const scroller = ref<HTMLElement | null>(null);
const scrollable = ref(false);
const atEnd = ref(false);

const showFade = computed(() => scrollable.value && !atEnd.value);

function measure() {
  const el = scroller.value;
  if (!el) {
    scrollable.value = false;
    return;
  }
  const overflow = el.scrollWidth - el.clientWidth;
  scrollable.value = overflow > 2;
  atEnd.value = overflow > 2 && el.scrollLeft >= overflow - 2;
}

onMounted(() => {
  window.addEventListener("resize", measure);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", measure);
});

const WINDOWS = [
  { key: "m1", label: "近1月" },
  { key: "m3", label: "近3月" },
  { key: "m6", label: "近6月" },
  { key: "y1", label: "近1年" }
] as const;

/** 收益率文本：null → 「—」；正负带符号（红涨绿跌由 valueClass 处理） */
function pctText(value: number | null): string {
  return value == null ? DASH : `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function pctClass(value: number | null): Record<string, boolean> {
  return {
    "etf-cmp__num--rise": value != null && value > 0,
    "etf-cmp__num--fall": value != null && value < 0
  };
}

function navText(row: IndexEtfCompareRow): string {
  return row.nav == null ? DASH : row.nav.toFixed(4);
}

/** 成交额：元 → 亿 / 万（两档够用，ETF 成交额量级大） */
function amountText(row: IndexEtfCompareRow): string {
  const amount = row.amount;
  if (amount == null) return DASH;
  if (amount >= 1e8) return `${(amount / 1e8).toFixed(2)}亿`;
  if (amount >= 1e4) return `${(amount / 1e4).toFixed(1)}万`;
  return amount.toFixed(0);
}

/** 跟踪差文本：非严格跟踪误差，title 必须带口径警示（表内与优选小卡同源复用） */
function trackingText(value: number | null): string {
  return value == null ? DASH : `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

/** 规模文本（#2333）：后端已给亿元；腾讯兜底口径为市价（title 标注） */
function scaleText(row: IndexEtfCompareRow): string {
  return row.scale_yi == null ? DASH : `${row.scale_yi.toFixed(2)}亿`;
}

/** 费率文本（#2333）：管理费 / 托管费（%/年），单缺只显不缺的那只，双缺「—」 */
function feeText(row: IndexEtfCompareRow): string {
  const mgmt = row.mgmt_fee_pct;
  const custody = row.custody_fee_pct;
  if (mgmt == null && custody == null) return DASH;
  const parts = [
    mgmt == null ? null : `管理 ${mgmt.toFixed(2)}%`,
    custody == null ? null : `托管 ${custody.toFixed(2)}%`
  ].filter((x): x is string => x != null);
  return parts.join(" / ");
}

const TRACKING_TITLE =
  "ETF 近 1 年涨幅 − 指数近 1 年涨幅；含折溢价噪声，非严格跟踪误差，仅作贴合度参考";

const SCALE_TITLE =
  "基金规模 = 交易所份额 × 净值（深市源自带净值，沪市复用净值列）；交易所源不可用时以腾讯行情市价口径兜底，可能与资产净值有小幅偏差";

const FEE_TITLE =
  "运作费率（%/年）：管理费率 / 托管费率，来自东财 F10 与同花顺，双源失败沿用最近 30 天内缓存";

const footnote = computed(() => {
  const d = data.value;
  if (!d) return "";
  const navPart = d.as_of ? `净值截至 ${d.as_of}（T-1 口径）` : "";
  const spotPart = "当日行情来自新浪财经";
  return [navPart, spotPart].filter(Boolean).join(" · ");
});

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  data.value = null;
  try {
    const res = await fetchIndexEtfCompare(props.symbol);
    data.value = res.data;
  } catch {
    // 对比表是补充信息，接口失败不阻塞关联标的区块其余内容
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
// 行挂载后表格宽度才确定，此时再测一次能否横滚
watch(rows, () => nextTick(measure));
</script>

<template>
  <section class="etf-cmp">
    <h3 class="etf-cmp__title">关联 ETF 对比</h3>

    <p v-if="loading" class="etf-cmp__hint">正在读取关联 ETF 行情…</p>

    <!-- 接口失败 / 无关联 ETF：整块静默收敛（父层同样按 peer_role 门控挂载） -->
    <p v-else-if="failed || !hasRows" class="etf-cmp__hint">
      {{ DASH }}
    </p>

    <template v-else>
      <!-- 优选小卡（#2334 形态 B）：hasRecommend 门禁——recommend_rank 全为
           null 时整块不出现（不渲染空壳标题）；整卡可点进 ETF 详情（与表内
           名称跳转同一路由惯例，无路由时退化为只读卡片） -->
      <div v-if="hasRecommend" class="etf-cmp__picks">
        <p class="etf-cmp__picks-title">优选 ETF</p>
        <ul class="etf-cmp__picks-list">
          <li
            v-for="pick in recommendRows"
            :key="pick.code"
            class="etf-cmp__pick"
            :class="{ 'etf-cmp__pick--first': pick.rank === 1 }"
          >
            <component
              :is="pick.route ? RouterLink : 'span'"
              :to="pick.route || undefined"
              class="etf-cmp__pick-link"
            >
              <span class="etf-cmp__pick-rank">
                {{ recommendLabel(pick.rank) }}
              </span>
              <span class="etf-cmp__pick-name" :title="pick.name || pick.code">
                {{ pick.name || pick.code }}
              </span>
              <span class="etf-cmp__pick-meta">
                <span class="etf-cmp__pick-code">{{ pick.code }}</span>
                <span class="etf-cmp__pick-tracking" :title="TRACKING_TITLE">
                  <span class="etf-cmp__pick-tracking-label">跟踪差</span>
                  <span
                    class="etf-cmp__pick-tracking-value"
                    :class="pctClass(pick.tracking)"
                  >
                    {{ trackingText(pick.tracking) }}
                  </span>
                </span>
              </span>
            </component>
          </li>
        </ul>
        <p class="etf-cmp__picks-note">按跟踪差（近1年）排序，门槛内取前三。</p>
      </div>

      <div class="etf-cmp__scroll-wrap">
        <div ref="scroller" class="etf-cmp__scroll" @scroll="measure">
          <table class="etf-cmp__table">
            <thead>
              <tr>
                <th class="etf-cmp__th">代码</th>
                <th class="etf-cmp__th">名称</th>
                <th class="etf-cmp__th etf-cmp__th--num">最新净值</th>
                <th class="etf-cmp__th etf-cmp__th--num">当日涨幅</th>
                <th class="etf-cmp__th etf-cmp__th--num">成交额</th>
                <th class="etf-cmp__th etf-cmp__th--num" :title="SCALE_TITLE">
                  规模
                </th>
                <th class="etf-cmp__th etf-cmp__th--num" :title="FEE_TITLE">
                  费率（年）
                </th>
                <th
                  v-for="w in WINDOWS"
                  :key="w.key"
                  class="etf-cmp__th etf-cmp__th--num"
                >
                  {{ w.label }}
                </th>
                <th
                  class="etf-cmp__th etf-cmp__th--num"
                  :title="TRACKING_TITLE"
                >
                  跟踪差（近1年）
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.code" class="etf-cmp__row">
                <td class="etf-cmp__td etf-cmp__td--mono">{{ row.code }}</td>
                <td class="etf-cmp__td">
                  <RouterLink
                    v-if="productRoute({ assetType: 'etf', symbol: row.code })"
                    class="etf-cmp__link"
                    :to="productRoute({ assetType: 'etf', symbol: row.code })!"
                  >
                    {{ row.name || row.code }}
                  </RouterLink>
                  <span v-else>{{ row.name || row.code }}</span>
                </td>
                <td class="etf-cmp__td etf-cmp__td--num">
                  {{ navText(row) }}
                </td>
                <td
                  class="etf-cmp__td etf-cmp__td--num"
                  :class="pctClass(row.change_pct)"
                >
                  {{ pctText(row.change_pct) }}
                </td>
                <td class="etf-cmp__td etf-cmp__td--num">
                  {{ amountText(row) }}
                </td>
                <td class="etf-cmp__td etf-cmp__td--num" :title="SCALE_TITLE">
                  {{ scaleText(row) }}
                </td>
                <td class="etf-cmp__td etf-cmp__td--num" :title="FEE_TITLE">
                  {{ feeText(row) }}
                </td>
                <td
                  v-for="w in WINDOWS"
                  :key="w.key"
                  class="etf-cmp__td etf-cmp__td--num"
                  :class="pctClass(row.returns[w.key])"
                >
                  {{ pctText(row.returns[w.key]) }}
                </td>
                <td
                  class="etf-cmp__td etf-cmp__td--num"
                  :class="pctClass(row.tracking_diff_y1)"
                  :title="TRACKING_TITLE"
                >
                  {{ trackingText(row.tracking_diff_y1) }}
                </td>
              </tr>
            </tbody>
            <!-- 指数基准行：跟踪差的比较基准同列摆放，让「差」可逐行验算 -->
            <tfoot v-if="indexBaseline">
              <tr>
                <td class="etf-cmp__td etf-cmp__td--mono">
                  {{ data?.index_code }}
                </td>
                <td class="etf-cmp__td">指数</td>
                <td class="etf-cmp__td etf-cmp__td--num">{{ DASH }}</td>
                <td class="etf-cmp__td etf-cmp__td--num">{{ DASH }}</td>
                <td class="etf-cmp__td etf-cmp__td--num">{{ DASH }}</td>
                <td class="etf-cmp__td etf-cmp__td--num">{{ DASH }}</td>
                <td class="etf-cmp__td etf-cmp__td--num">{{ DASH }}</td>
                <td
                  v-for="w in WINDOWS"
                  :key="w.key"
                  class="etf-cmp__td etf-cmp__td--num"
                  :class="pctClass(indexBaseline[w.key])"
                >
                  {{ pctText(indexBaseline[w.key]) }}
                </td>
                <td class="etf-cmp__td etf-cmp__td--num">{{ DASH }}</td>
              </tr>
            </tfoot>
          </table>
        </div>
        <span v-if="showFade" class="etf-cmp__fade" aria-hidden="true" />
      </div>

      <p v-if="footnote" class="section-footnote section-footnote--spaced">
        {{ footnote }}
      </p>
      <p class="section-footnote section-footnote--attached">
        对比表按成交额排序；跟踪差含折溢价噪声、非严格跟踪误差；规模与费率为
        按需抓取的第三方公开数据，缺失时显示「—」。
      </p>
    </template>
  </section>
</template>

<style scoped>
.etf-cmp {
  margin-top: var(--space-4);
}

.etf-cmp__title {
  margin: 0 0 var(--space-3);
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.etf-cmp__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 12 列宽表（#2333 补规模/费率两列）：窄屏横向滚动（不压缩列宽逐字竖排），滚动条贴卡内边缘 */
.etf-cmp__scroll-wrap {
  position: relative;
  min-width: 0;
}

.etf-cmp__scroll {
  min-width: 0;
  overflow-x: auto;
}

.etf-cmp__table {
  width: 100%;
  min-width: 760px;
  border-collapse: collapse;
}

.etf-cmp__th {
  padding: 0 var(--space-2) var(--space-2);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary-ink);
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid var(--border-default);
}

.etf-cmp__th--num {
  text-align: right;
}

.etf-cmp__row {
  border-bottom: 1px solid
    color-mix(in srgb, var(--border-default) 45%, transparent);
}

.etf-cmp__td {
  padding: var(--space-2);
  font-size: var(--text-label);
  color: var(--text-primary);
  white-space: nowrap;
}

.etf-cmp__td--mono {
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.etf-cmp__td--num {
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.etf-cmp__num--rise {
  /* #2314：文字色统一 -ink 文字级令牌（图形级 --color-rise 禁作前景文字，design.md:131） */
  color: var(--color-rise-ink);
}

.etf-cmp__num--fall {
  color: var(--color-fall-ink);
}

.etf-cmp__link {
  color: var(--text-primary);
  text-decoration: none;

  &:hover,
  &:focus-visible {
    color: var(--brand-ink); /* #2314：前景文字用品牌文字级 */
  }

  &:focus-visible {
    outline: 2px solid var(--brand-700);
    outline-offset: 2px;
  }
}

/* ── 优选小卡（#2334 形态 B）────────────────────────────────────────
   对比表上方的速览层：小卡视觉与表卡同族（同命名空间、同文字级令牌）。
   第 1 名用品牌软底 + 品牌边框（软按钮「选中态」同款语言）拉开层级，
   2/3 名为中性小卡——不引入表外新色，暗色由 token 自动切换。 */
.etf-cmp__picks {
  margin-bottom: var(--space-3);
}

.etf-cmp__picks-title {
  margin: 0 0 var(--space-2);
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
}

.etf-cmp__picks-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--space-2);
  padding: 0;
  margin: 0;
  list-style: none;
}

.etf-cmp__pick {
  min-width: 0;
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

/* 第 1 名：品牌软底 + 品牌边框，强调层级明显高于 2/3 名的中性卡 */
.etf-cmp__pick--first {
  background: var(--brand-100);
  border-color: var(--brand-400);
}

.etf-cmp__pick-link {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
  padding: var(--space-2) var(--space-3);
  color: inherit;
  text-decoration: none;
  border-radius: inherit;

  &:hover {
    background: var(--bg-soft);
  }

  &:focus-visible {
    outline: 2px solid var(--brand-700);
    outline-offset: 2px;
  }
}

.etf-cmp__pick--first .etf-cmp__pick-link:hover {
  background: var(--brand-200);
}

.etf-cmp__pick-rank {
  align-self: flex-start;
  padding: 0 var(--space-2);
  font-size: 12px;
  font-weight: 500;
  line-height: 18px;
  color: var(--text-tertiary-ink);
  background: var(--bg-muted);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
}

/* 第 1 名名次标：品牌文字级令牌（--brand-ink，AA 达标），勿用图形级 --brand-700 */
.etf-cmp__pick--first .etf-cmp__pick-rank {
  color: var(--brand-ink);
  border-color: var(--brand-400);
}

.etf-cmp__pick-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

.etf-cmp__pick--first .etf-cmp__pick-name {
  font-weight: 600;
}

.etf-cmp__pick-meta {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  justify-content: space-between;
  min-width: 0;
}

.etf-cmp__pick-code {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.etf-cmp__pick-tracking {
  display: inline-flex;
  gap: var(--space-1);
  align-items: baseline;
  min-width: 0;
}

.etf-cmp__pick-tracking-label {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.etf-cmp__pick-tracking-value {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.etf-cmp__picks-note {
  margin: var(--space-2) 0 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

/* 脚注族已迁至共享类 .section-footnote（#2320）：来源是**分隔型**（--spaced，
   与上方表格拉开），口径说明是**续接型**（--attached，紧随来源、属同一组信息）。 */

/* 右缘渐隐：固定在可视区右缘，不随内容滚动；pointer-events:none 不挡点击 */
.etf-cmp__fade {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 28px;
  pointer-events: none;
  background: linear-gradient(to right, transparent, var(--bg-card));
}

/* 基准行不是「又一只 ETF」：弱化底色区分，避免被当成可买标的 */
.etf-cmp__table tfoot .etf-cmp__td {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-muted);
  border-bottom: none;
}
</style>
