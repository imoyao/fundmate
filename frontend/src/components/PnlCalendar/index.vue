<!--
  PnlCalendar · 收益日历（#1812 日视图 / #1925 三视图 / #1942 方格图与六态）

  一组件多容器：welcome 嵌入卡（满宽 12 列）、panorama「资产大类」原地切换、
  账户详情半宽容器，共用同一份数据与口径。

  三视图（#1925）× 两种形态（#1942）：
    日收益  按月翻；日历图（一屏一个月）/ 柱状图（一根柱 = 一天）
    月收益  按年翻；方格图（12 个月各一格）/ 柱状图（一根柱 = 一个月）
    年收益  **投资以来**全览，一格一年（区间固定，故无区间导航）；两种形态同上
    点击下钻：年格 → 该年的月格 → 该月的日日历
  三者**不是三条口径**，而是同一条日序列的三种切法——聚合下推在后端
  （`granularity` 参数），前端只做呈现，禁止二次盈亏计算。

  六态视觉与色彩纪律集中在 `PnlCalendarTile.vue`（格子）与 `PnlCalendarBars.vue`（柱）：
    updown       涨红跌绿柔和填充，色深 ∝ |收益|
    zero         灰底 + 0.00（真实为零）
    no_price     斜线纹理（balance 模式无历史价格序列，如银行理财/投顾/实物）
    no_data      虚线 + 「未同步」（开盘日却没取到当天估值）
    no_position  虚线 + 「无持仓」（建仓前 / 清仓后）
    closed       空白 + 「休市」（非 A 股开盘日；判据是后端交易日历，不是「有没有价格」）
  **缺数据绝不能画成 0**，这是本组件存在的核心理由之一。
  「休市」与「未同步」必须分开（#1942）：前者只能等开盘，后者要去跑同步任务。
-->

<template>
  <div class="pnl-calendar">
    <!-- ===== 标题行 =====
         两种模式（#2050）：

         · `hostHeader=false`（默认）：组件自画完整 SectionHeader——标题 + 口径 ⓘ
           + 控件排。投资概览第三排、账户详情用此模式。

         · `hostHeader=true`：标题与口径 ⓘ **一并交给宿主**，组件只输出控件排
           （右对齐）。资产总览右卡用此模式——宿主必须自己画 `<h3>`（它要在
           「资产大类 / 收益日历」之间变），若组件再画一遍就会出现两个同名标题
           上下叠着（#2035 的旧 `hideTitle` 只抑制了 `<h2>` 文字，ⓘ 仍独占一行，
           形成孤立伪标题行——#2050 修的正是这个）。宿主侧用
           `PnlCalendarCaliberIcon` 在自画标题旁补上 ⓘ。 -->
    <SectionHeader
      v-if="!hostHeader"
      title="收益日历"
      info-label="收益日历的口径与图例说明"
    >
      <template #info>
        <PnlCalendarCaliberTip />
      </template>
      <template #action>
        <PnlCalendarActionBar
          v-model:granularity="granularity"
          v-model:view="view"
          v-model:value-mode="valueMode"
          :loading="loading"
          :range-label="rangeLabel"
          :granularities="allowedGranularities"
          @shift="shift"
          @go-current="goCurrent"
        />
      </template>
    </SectionHeader>
    <div v-else class="pnl-calendar__controls">
      <PnlCalendarActionBar
        v-model:granularity="granularity"
        v-model:view="view"
        v-model:value-mode="valueMode"
        :loading="loading"
        :range-label="rangeLabel"
        :granularities="allowedGranularities"
        @shift="shift"
        @go-current="goCurrent"
      />
    </div>

    <!-- ===== 加载 / 空态 / 错误 ===== -->
    <div v-if="loading" class="pnl-calendar__placeholder">
      <span class="text-sm" :style="{ color: 'var(--text-secondary)' }">
        收益日历加载中…
      </span>
    </div>

    <div v-else-if="error" class="pnl-calendar__placeholder">
      <span class="text-sm" :style="{ color: 'var(--text-secondary)' }">
        {{ error }}
      </span>
      <el-button size="small" text type="primary" @click="load">重试</el-button>
    </div>

    <!-- 无价格序列：明确说清原因，不画成零收益（否则用户以为坏了） -->
    <div v-else-if="!hasAnyPrice" class="pnl-calendar__placeholder">
      <IconifyIconOffline
        icon="ep:info-filled"
        class="text-base"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      />
      <span class="text-sm" :style="{ color: 'var(--text-secondary)' }">
        {{ emptyHint }}
      </span>
      <!-- 数据缺口要给出口：用户能一键跳到有数据的那一期，
           否则只能自己一次次翻区间试。 -->
      <el-button
        v-if="emptyIsDataGap && latestPriceLabel"
        size="small"
        text
        type="primary"
        @click="jumpToLatestPrice"
      >
        {{ jumpButtonText }}
      </el-button>
    </div>

    <!-- ===== 主体：方格图（日历图 / 月格 / 年格）/ 柱状图 =====
         外面这一层 `pnl-calendar__body` 只负责一件事：**跟随宿主的高度**
         （#2033）。宿主给了确定高度（资产总览右卡的等高容器）就填满，
         没给（welcome 满宽 / 账户详情半宽）就是自然高——高度约束只能由宿主施加，
         本组件不自带任何固定高度，那两处的排版因此与改动前逐像素一致。 -->
    <template v-else>
      <div class="pnl-calendar__body">
        <PnlCalendarGrid
          v-if="granularity === 'day' && view === 'calendar'"
          :days="series?.days ?? []"
          :year="cursor.getFullYear()"
          :month-index="cursor.getMonth()"
          :mode="valueMode"
        />

        <!-- 月 / 年视图的方格图（#1942）：一格一个期间，点击下钻 -->
        <PnlCalendarPeriodGrid
          v-else-if="granularity !== 'day' && view === 'calendar'"
          :periods="series?.periods ?? []"
          :granularity="granularity"
          :mode="valueMode"
          @select="selectPeriod"
        />

        <!-- 柱状图：三粒度共用一份几何，只是「一根柱」的含义不同（见文件头）。
             后端保证 days / periods 只有一侧非空，Bars 内部据此选边。 -->
        <!-- 柱状图三粒度共用（见文件头）。月 / 年视图的柱一根 = 一月 / 一年，
             点击也走 `selectPeriod` 下钻，与方格图交互对齐；日粒度是叶子，
             不传 `drillable`（柱不可点）。`drillable` 取 `canDrill`：宿主排掉了
             下一档粒度时（如 #2033 的右卡排掉日粒度），柱体与柱下提示一并撤掉，
             免得留一个「可点却没反应」的假 affordance。 -->
        <PnlCalendarBars
          v-else
          :days="series?.days ?? []"
          :periods="series?.periods ?? []"
          :range-label="rangeLabel"
          :total="series?.month_total ?? 0"
          :range-rate="series?.range_rate ?? null"
          :mode="valueMode"
          :drillable="canDrill"
          @select="selectPeriod"
        />

        <!-- ===== 合计行：一行小字，不占纵向空间（Voice & Content规范） ===== -->
        <div class="pnl-calendar__summary">
          <span class="pnl-calendar__summary-label">{{ rangeLabel }}合计</span>
          <MoneyDisplay
            :value="series?.month_total ?? null"
            size="sm"
            :show-currency="true"
          />
          <!-- 区间收益率与金额**同时**显示（#1942 ②）：切换口径是针对格子里那 30 个
             小数字的，合计行只有一个数，没必要让它随开关时隐时现。
             `null` = 算不出来（区间前一天没有基准）⇒ 显示 —，绝不显示 0.00%。 -->
          <span class="pnl-calendar__summary-sep" aria-hidden="true">·</span>
          <RiseFallText
            v-if="series?.range_rate != null"
            :value="series.range_rate"
            size="sm"
          />
          <span v-else class="pnl-calendar__summary-none">收益率 —</span>
          <span class="pnl-calendar__summary-note">
            口径：当日盈亏＝总盈亏变动，存取款不计入
          </span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import PnlCalendarGrid from "./PnlCalendarGrid.vue";
import PnlCalendarPeriodGrid from "./PnlCalendarPeriodGrid.vue";
import PnlCalendarBars from "./PnlCalendarBars.vue";
import PnlCalendarCaliberTip from "./PnlCalendarCaliberTip.vue";
import PnlCalendarActionBar from "./PnlCalendarActionBar.vue";
import {
  ALL_GRANULARITIES,
  defaultGranularity,
  firstOfMonth,
  nextGranularity,
  rangeFor,
  rangeLabelFor,
  type PnlCalendarValueMode
} from "./helpers";
import {
  getPnlCalendar,
  type PnlCalendarDay,
  type PnlCalendarGranularity,
  type PnlCalendarSeries
} from "@/api/summary";

defineOptions({ name: "PnlCalendar" });

const props = withDefaults(
  defineProps<{
    /** 账户ID：不传=家庭级，传=该账户级（账户维度天然支持，见设计文档 §3） */
    ledgerId?: number;
    /**
     * 宿主是否自带标题行（#2050）。
     *
     * PnlCalendar 的三处容器——投资概览第三排、资产总览右卡、账户详情——共用同一份
     * 口径。资产总览那处外面套了卡片标题（`OverviewSummaryCard` 必须自己画 `<h3>`，
     * 因为它要在「资产大类 / 收益日历」两态之间变，还挂着返回开关）。
     *
     * 旧 `hideTitle` 只抑制 `<h2>` 文字，`#info` 口径图标仍独占一行（窄容器下被控件行
     * 挤断后只剩残影）。`hostHeader` 模式下本组件**完全不画 `SectionHeader`**——标题、
     * 口径图标、控件三者由宿主一行排开，宿主用 `PnlCalendarCaliberIcon` 画图标。
     * 另两处不传即为 `false`，行为与改动前完全一致。
     */
    hostHeader?: boolean;
    /**
     * 本宿主允许的粒度档位（#2033）；不传 = 三档全开（welcome / 账户详情）。
     *
     * **日粒度的家在投资概览页**（welcome 第三排的满宽日历）：那是唯一容得下
     * 「一屏 5 列 × 数行」日历的地方。资产总览右卡是**与左卡并排的等高兄弟容器**
     * （卡片体锁死 280px），日粒度在那里既排不下也读不清，故由宿主传
     * `["month", "year"]` 把它摘掉——同时**不提供任何入口**（没有「展开/查看大图」），
     * 日粒度的需求去 welcome 即可，二者各归其位。
     *
     * 只挡控件排不够：方格与柱体的点击下钻也会一路走到日粒度，
     * 所以 `selectPeriod` 与 `canDrill` 也读同一份约束（见 `helpers.nextGranularity`）。
     */
    granularities?: readonly PnlCalendarGranularity[];
  }>(),
  { ledgerId: undefined, hostHeader: false }
);

const emit = defineEmits<{
  (e: "select-day", payload: { date: string; day: PnlCalendarDay }): void;
}>();
void emit; // 预留的「点某天看明细」事件，当前尚无消费方；保留契约避免破坏容器

const series = ref<PnlCalendarSeries | null>(null);
const loading = ref(false);
const error = ref("");
const view = ref<"calendar" | "bar">("calendar");

/**
 * 宿主允许的粒度档位（#2033）；空数组视作不约束，保持三档。
 *
 * 三处容器里只有资产总览右卡会传，另外两处读到的就是 `ALL_GRANULARITIES`，
 * 于是默认粒度仍是日粒度、控件排仍是三档——行为与改动前完全一致。
 */
const allowedGranularities = computed<readonly PnlCalendarGranularity[]>(() =>
  props.granularities?.length ? props.granularities : ALL_GRANULARITIES
);

/**
 * 默认粒度取允许集合里最靠前的一档（#2033）：排掉日粒度后自动落到月粒度，
 * 而不是留在一个「控件里选不到」的粒度上。
 */
const granularity = ref<PnlCalendarGranularity>(
  defaultGranularity(allowedGranularities.value)
);

/**
 * 能否继续下钻（#2033）。`false` 时方格 / 柱体不可点、柱下提示也一并消失——
 * 留一个点下去没反应的控件比不给控件更糟。
 */
const canDrill = computed(
  () => nextGranularity(granularity.value, allowedGranularities.value) !== null
);

/**
 * 数字口径（#1942 ②）：金额 / 收益率。
 *
 * 纯前端开关——两个口径的数都已随响应下发（`days[].rate` / `periods[].rate`），
 * 切换时**不发请求、不做计算**，故不需要进 `watch([...], load)` 的触发源。
 * 不做持久化：这是「现在想看哪个」的临时视角，不是需要记住的偏好
 * （与粒度 / 形态同档，刷新即回默认的金额）。
 */
const valueMode = ref<PnlCalendarValueMode>("amount");

/**
 * 「投资以来」的起点（#1942）。年视图要**投资以来每一年占一格**，就必须知道起点，
 * 不能靠前端写死一个年数窗口。该字段由后端随每次响应下发（最早一笔改变份额的流水），
 * 故任何一个粒度加载成功后都会更新它。
 */
const firstTxnDate = ref<string | null>(null);

/**
 * 游标，永远存**某月 1 号**（避免时区漂移）。
 *
 * 日粒度用「年 + 月」；月粒度只读 `getFullYear()`；年粒度**不使用游标**——
 * 它的区间恒为「投资以来 → 今年」（见 `rangeFor`）。三种粒度共用一个游标，
 * 在粒度之间来回切时不会丢失「你原本在看哪个月」（`shift` 也刻意保留月序号）。
 */
const cursor = ref<Date>(firstOfMonth(new Date()));

/**
 * 空态文案。**不要**命名为 `emptyText`——那是 `MoneyDisplay` 的 prop 名，
 * 同名会让模板里的 `{{ emptyText }}` 被解析到组件实例上（TS2339）。
 *
 * 必须区分两种「空」（#1812 上线首日的教训）：
 * · `data_gap`      当前区间一条价格数据都没有 → 多半是每日快照任务没跑，
 *                   要告诉用户「别处有」，并给个可点的跳转；
 * · `unpriced_only` 持仓确实按日无估值序列 → 属产品属性，说清即可。
 * 混成一句「没有历史价格序列」会把上一种说成用户的持仓有问题。
 */
const EMPTY_DATA_GAP = (lastDate: string, scope: string) =>
  `${scope}还没有每日估值数据。最近一次估值：${lastDate}。` +
  "通常是每日快照任务未运行所致，并非账户异常。";

const EMPTY_NO_VALUATION =
  "账户里的产品按日没有估值序列（银行理财、投顾组合、实物资产等），" +
  "因此没有每日收益。";

/** 当前浏览区间的标签（导航中键 / 区间标签、合计行、柱状图 aria 共用同一份） */
const rangeLabel = computed(() =>
  rangeLabelFor(granularity.value, cursor.value, firstTxnDate.value)
);

/**
 * 点某格下钻（#1942）：年格 → 该年的月格 → 该月的日日历。
 *
 * 实现是「改游标 + 改粒度」两步，靠 `watch([cursor, granularity], load)` 合并成
 * **一次**请求（数组式 watch 在同一 tick 内只触发一次）——若沿用旧的两条独立
 * watcher，下钻会连发两次相同区间的请求。
 *
 * ⚠️ #2033：宿主可以排掉某一档粒度（资产总览右卡排掉日粒度）。**下钻也必须
 * 在动手之前问**：方格与柱体的点击路径与控件排是两条独立入口，只在控件里藏掉
 * 日粒度而这里照旧切换，用户就会掉进一个本卡装不下的形态，且没有任何控件能切回来。
 */
function selectPeriod(period: string): void {
  if (granularity.value === "year") {
    if (!nextGranularity("year", allowedGranularities.value)) return;
    cursor.value = new Date(Number(period), 0, 1);
    granularity.value = "month";
    return;
  }
  if (granularity.value === "month") {
    if (!nextGranularity("month", allowedGranularities.value)) return;
    cursor.value = new Date(
      Number(period.slice(0, 4)),
      Number(period.slice(5)) - 1,
      1
    );
    granularity.value = "day";
  }
}

const hasAnyPrice = computed(() => series.value?.has_any_price === true);

/**
 * 空态归因（#1812 上线首日的教训）。
 * `latest_price_date` 为空 ⇒ 该区间一条价格数据都没取到 ⇒ **数据缺口**；
 * 否则说明价格有、只是持仓按日无估值序列 ⇒ 属产品属性。
 */
const emptyIsDataGap = computed(() => {
  const cov = series.value?.coverage;
  if (!cov) return false;
  // 完全没有覆盖 ⇒ 缺口；有覆盖但 priced=0 ⇒ 持仓本身无估值序列
  return cov.priced_positions === 0 && !series.value?.latest_price_date;
});

/** 空态里的「哪儿没数据」——粒度不同说法不同，别在年视图里说「本月」 */
const emptyScope = computed(() => {
  const g = granularity.value;
  if (g === "day") return "本月";
  if (g === "month") return "本年";
  // 年视图的区间就是「投资以来」，说「该区间」不如直说
  return "投资以来";
});

const emptyHint = computed(() =>
  emptyIsDataGap.value
    ? EMPTY_DATA_GAP(series.value?.latest_price_date ?? "—", emptyScope.value)
    : EMPTY_NO_VALUATION
);

/** 有数据的最近一期（已正在看则回空串，跳转按钮随之隐藏） */
const latestPriceLabel = computed(() => {
  const d = series.value?.latest_price_date;
  if (!d) return "";
  const year = d.slice(0, 4);
  // 年视图区间恒为「投资以来 → 今年」，最新数据必然落在区间内，没有可跳的去处
  // （区间与游标无关，真跳了也不会换区间——这种按钮是骗人的，故一律不显示）
  if (granularity.value === "year") return "";
  if (granularity.value === "month") {
    return year === String(cursor.value.getFullYear()) ? "" : `${year} 年`;
  }
  const monthKey = d.slice(0, 7);
  const curKey =
    `${cursor.value.getFullYear()}-` +
    String(cursor.value.getMonth() + 1).padStart(2, "0");
  return monthKey === curKey ? "" : monthKey.replace("-", " 年 ") + " 月";
});

const jumpButtonText = computed(
  () =>
    `查看 ${latestPriceLabel.value} 有数据的${granularity.value === "day" ? "月份" : "年份"}`
);

function jumpToLatestPrice() {
  const d = series.value?.latest_price_date;
  if (!d) return;
  // 只改游标即可：三种粒度都从 cursor 取年（月 / 年）或年 + 月（日）
  const [y, m] = d.split("-").map(Number);
  cursor.value = new Date(y, m - 1, 1);
}

async function load() {
  loading.value = true;
  error.value = "";
  const { start, end } = rangeFor(
    granularity.value,
    cursor.value,
    firstTxnDate.value
  );
  // 年视图的区间依赖 `first_txn_date`。正常路径是「先进日视图 → 拿到起点 → 再切年」，
  // 起点早已就位；只有冷启动直接点「年收益」时才可能还没有。此时先按回落区间取一次，
  // 响应里带的起点写回后**再取一次正确区间**，避免「投资以来」被截成一年。
  // `needsFirstTxn` 在请求前求值，第二次调用时 firstTxnDate 已非空 ⇒ 不会再递归。
  const needsFirstTxn =
    granularity.value === "year" && firstTxnDate.value === null;
  try {
    const { data } = await getPnlCalendar({
      start_date: start,
      end_date: end,
      ledger_id: props.ledgerId,
      granularity: granularity.value
    });
    series.value = data;
    if (data.first_txn_date) firstTxnDate.value = data.first_txn_date;
    if (needsFirstTxn && firstTxnDate.value) {
      await load();
      return;
    }
  } catch {
    error.value = "收益日历加载失败，请稍后重试";
    series.value = null;
  } finally {
    loading.value = false;
  }
}

function shift(delta: number) {
  const c = cursor.value;
  if (granularity.value === "day") {
    cursor.value = new Date(c.getFullYear(), c.getMonth() + delta, 1);
    return;
  }
  // 月粒度按年平移；**保留月序号**，切回日粒度时仍落在你原来那个月。
  // （年视图不调用本函数：它没有区间导航。）
  cursor.value = new Date(c.getFullYear() + delta, c.getMonth(), 1);
}

function goCurrent() {
  // 把游标放回「今天所在的那个月」：日粒度看当月，月粒度取 getFullYear()，
  // 自然就是今年的年份。年视图不调用（区间恒为投资以来）。
  cursor.value = firstOfMonth(new Date());
}

// 三条触发源合并成一个数组式 watch：下钻要同时改「游标 + 粒度」，
// 若拆成多条 watcher 会在同一 tick 里连发两次相同区间（由 `selectPeriod` 造成）。
watch([() => props.ledgerId, cursor, granularity], load);

// 宿主中途收窄粒度集合时（宿主很少会动态改，但组件不该假设它不变）：
// 当前粒度若已不在集合内，落到默认档，绝不停留在「控件里选不到」的那一档。
watch(allowedGranularities, allowed => {
  if (allowed.includes(granularity.value)) return;
  granularity.value = defaultGranularity(allowed);
});
onMounted(load);

defineExpose({ reload: load });
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.pnl-calendar {
  display: flex;
  flex-direction: column;
  gap: 14px;

  /* #2033：跟随宿主的高度。宿主给了确定高度（资产总览右卡的等高容器，280px）
     这里就是 280px，整列由下方的 body 吃掉剩余空间；宿主高度不定
     （welcome 满宽 / 账户详情半宽）时百分比高度解析为 auto，仍是自然高——
     **高度约束只能由宿主施加**，本组件不自带任何固定高度。 */
  height: 100%;
}

/* 主体区（方格图 / 柱状图 + 合计行）：`flex: 1` 吃掉控件排以外的高度，
   `min-height: 0` 让内部（年格网格外层的滚动容器）真能收缩——没有它，
   flex 项的自动最小尺寸会把内容高度顶回来，装不下时卡片就被撑破而不是内部滚动。 */
.pnl-calendar__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}

/* 年视图的区间标签（替代区间导航按钮组：年视图区间固定，按不动的按钮是骗人的） */
.pnl-calendar__range {
  font-size: 13px;
  color: var(--text-secondary);
}

/* 合计行：一行读完，但必须比格子里的小数字更重。
   它是「这个区间到底赚没赚」的答案，是用户扫完整张图后**唯一会去找**的那个数；
   原先与格内 13px 数字同权重（MoneyDisplay size=sm），用户很难一眼定位。
   现在金额升到 md（16px）并给整行一条极淡的底色带 —— 用底色而不是加边框分隔线，
   是因为这一行已经紧跟在格子下面，再加一条横线会读成「新的一段的表头」。 */
.pnl-calendar__summary {
  display: flex;
  gap: 10px;
  align-items: baseline;
  padding: 8px 10px;
  font-size: 12px;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}

.pnl-calendar__summary-label {
  font-weight: 500;
  color: var(--text-secondary);
}

/* 金额与收益率之间的分隔点：只做视觉断句，不承载信息（aria-hidden） */
.pnl-calendar__summary-sep {
  color: var(--border-default);
}

/* 「收益率 —」：不可算（缺区间前一天基准）时的占位，与 0.00% 严格区分 */
.pnl-calendar__summary-none {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.pnl-calendar__summary-note {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-tertiary-ink);
}

.pnl-calendar__placeholder {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  justify-content: center;
  min-height: 140px;
  padding: 16px;
  text-align: center;
}

/* 响应式：窄屏（弹窗 / 半宽容器）让合计行换行。
   断点走 _breakpoints.scss 单一来源（`bp.below("sm")` = < 640px），
   禁手写像素——guard_breakpoints.py 会拦。
   日历格子的窄屏压缩随其样式一起住在 `PnlCalendarGrid.vue`。 */
@include bp.below("sm") {
  .pnl-calendar__summary {
    flex-wrap: wrap;
  }

  .pnl-calendar__summary-note {
    width: 100%;
    margin-left: 0;
  }
}
</style>
