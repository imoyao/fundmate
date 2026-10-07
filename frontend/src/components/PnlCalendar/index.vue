<!--
  PnlCalendar · 收益日历（#1812 日视图 / #1925 日·月·年三视图）

  一组件多容器：welcome 嵌入卡（满宽 12 列）、panorama「总资产构成」原地切换、
  账户详情半宽容器，共用同一份数据与口径。

  三视图（#1925）：
    日收益  按月翻；日历图 / 柱状图两种呈现角度
    月收益  按年翻；一根柱 = 一个月
    年收益  按年翻，一次看 YEAR_WINDOW 年；一根柱 = 一年
  三者**不是三条口径**，而是同一条日序列的三种切法——聚合下推在后端
  （`granularity` 参数），前端只做呈现，禁止二次盈亏计算。

  四态视觉与色彩纪律见 `PnlCalendarGrid.vue`（日历图）与 `PnlCalendarBars.vue`（柱状图）：
    updown   涨红跌绿柔和填充，色深 ∝ |收益|
    zero     灰底 + 0.00（真实为零）
    no_price 斜线纹理（balance 模式无历史价格序列，如银行理财/投顾/实物）
    closed   空白（非交易日/未同步/区间首日）
  **缺数据绝不能画成 0**，这是本组件存在的核心理由之一。
-->

<template>
  <div class="pnl-calendar">
    <!-- ===== 标题行：口径说明 + 粒度切换 + 形态切换 + 区间导航 ===== -->
    <SectionHeader title="收益日历" :info="CALIBER_NOTE">
      <template #action>
        <div class="flex flex-wrap items-center justify-end gap-2">
          <!-- 粒度：日 / 月 / 年。SegmentedControl 是全站唯一实现（#1717；静态守卫
               guard_segmented.py 拦截「改用 Element Plus 自带分段组件」与手写
               xxx-segmented 样式块的回潮） -->
          <SegmentedControl
            v-model="granularity"
            :options="GRANULARITY_OPTIONS"
            size="small"
            ariaLabel="切换收益粒度"
          />
          <!-- 形态只在日粒度下有意义：月 / 年视图的「一根柱」本身就对应一月 / 一年，
               再分日历图 / 柱状图没有第二个角度可切 -->
          <SegmentedControl
            v-if="granularity === 'day'"
            v-model="view"
            :options="VIEW_OPTIONS"
            size="small"
            ariaLabel="切换呈现形态"
          />
          <!-- 区间导航。`role="group"` + `aria-label` 是按钮组的正确 a11y 语义：
               组本身不是按钮，但需一个可访问名来把三枚按钮归为一组。顺带说明：守卫
               `guard_a11y_interaction.py` 的 `<(el-button|button)\b` 会把
               `el-button-group` 一并匹配上，这里给组加名是正解，不是为过守卫而塞的无用属性。 -->
          <el-button-group role="group" :aria-label="nav.groupAria">
            <el-button
              size="small"
              text
              :aria-label="nav.prev"
              :disabled="loading"
              @click="shift(-1)"
            >
              <IconifyIconOffline icon="ep:arrow-left" />
            </el-button>
            <el-button size="small" text :disabled="loading" @click="goCurrent">
              {{ rangeLabel }}
            </el-button>
            <el-button
              size="small"
              text
              :aria-label="nav.next"
              :disabled="loading"
              @click="shift(1)"
            >
              <IconifyIconOffline icon="ep:arrow-right" />
            </el-button>
          </el-button-group>
        </div>
      </template>
    </SectionHeader>

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

    <!-- ===== 主体：日历图 / 柱状图 ===== -->
    <template v-else>
      <PnlCalendarGrid
        v-if="granularity === 'day' && view === 'calendar'"
        :days="series?.days ?? []"
        :year="cursor.getFullYear()"
        :month-index="cursor.getMonth()"
      />

      <!-- 柱状图：三粒度共用一份几何，只是「一根柱」的含义不同（见文件头）。
           后端保证 days / periods 只有一侧非空，Bars 内部据此选边。 -->
      <PnlCalendarBars
        v-else
        :days="series?.days ?? []"
        :periods="series?.periods ?? []"
        :range-label="rangeLabel"
        :total="series?.month_total ?? 0"
      />

      <!-- ===== 合计行：一行小字，不占纵向空间（Voice & Content规范） ===== -->
      <div class="pnl-calendar__summary">
        <span class="pnl-calendar__summary-label">{{ rangeLabel }}合计</span>
        <MoneyDisplay
          :value="series?.month_total ?? null"
          size="sm"
          :show-currency="true"
        />
        <span class="pnl-calendar__summary-note">
          口径：总盈亏日差分，对存取款免疫
        </span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { Icon as IconifyIconOffline } from "@iconify/vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import PnlCalendarGrid from "./PnlCalendarGrid.vue";
import PnlCalendarBars from "./PnlCalendarBars.vue";
import { firstOfMonth, ymd } from "./helpers";
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
  }>(),
  { ledgerId: undefined }
);

const emit = defineEmits<{
  (e: "select-day", payload: { date: string; day: PnlCalendarDay }): void;
}>();
void emit; // 预留的「点某天看明细」事件，当前尚无消费方；保留契约避免破坏容器

const VIEW_OPTIONS = [
  { label: "日历图", value: "calendar" },
  { label: "柱状图", value: "bar" }
] as const;

const GRANULARITY_OPTIONS = [
  { label: "日收益", value: "day" },
  { label: "月收益", value: "month" },
  { label: "年收益", value: "year" }
] as const;

/**
 * 年粒度一次看几年（#1925）。
 *
 * 取 3 而非 5：区间长度与耗时**线性**（真实库 151 笔持仓实测——
 * 365 天 1.3s、1827 天 3.6s），1096 天约 2.0s，已是「点一下等一会儿」的上限；
 * 再长会让切粒度变成明显卡顿。要拉长窗口，先复测 `services/pnl_calendar.py`
 * 的区间耗时，别只改这个数。
 */
const YEAR_WINDOW = 3;

const series = ref<PnlCalendarSeries | null>(null);
const loading = ref(false);
const error = ref("");
const view = ref<"calendar" | "bar">("calendar");
const granularity = ref<PnlCalendarGranularity>("day");

/**
 * 游标，永远存**某月 1 号**（避免时区漂移）。
 *
 * 日粒度用「年 + 月」；月 / 年粒度只读 `getFullYear()`。三种粒度共用一个游标，
 * 在粒度之间来回切时不会丢失「你原本在看哪个月」（`shift` 也刻意保留月序号）。
 */
const cursor = ref<Date>(firstOfMonth(new Date()));

/**
 * 口径说明挂在标题旁的 (i) 图标上，**不占正文空间**。
 * 首句用人话，后面才是口径细节。
 */
const CALIBER_NOTE =
  "今日收益 = 总盈亏的变化，充值、提现不计入。" +
  "例：先有 1 万浮盈，再充 5 万，总盈亏仍是 1 万——今天显示的不会是 6 万。" +
  "｜口径：按「总盈亏」逐日差分，非逐笔持仓的当日涨跌（基金按净值日切、" +
  "股票按交易日切，两者在同一天未必同价，故与「总资产日环比」有出入是正常的）。" +
  "建仓当日不记盈亏，显示「—」——建仓那一刻浮盈本来就是 0。" +
  "斜线格「暂无每日估值」= 该产品按日无估值序列（银行理财、投顾组合、实物资产等），不是收益为零。" +
  "月 / 年视图是同一份日盈亏的合计，不另算。";

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

/** 当前粒度要请求的闭区间。月 / 年粒度整段取自然年，由后端按粒度聚合。 */
function rangeFor(): { start: string; end: string } {
  const year = cursor.value.getFullYear();
  const month = cursor.value.getMonth();
  if (granularity.value === "month") {
    return { start: `${year}-01-01`, end: `${year}-12-31` };
  }
  if (granularity.value === "year") {
    return {
      start: `${year - YEAR_WINDOW + 1}-01-01`,
      end: `${year}-12-31`
    };
  }
  const last = new Date(year, month + 1, 0).getDate();
  return {
    start: `${year}-${String(month + 1).padStart(2, "0")}-01`,
    end: ymd(new Date(year, month, last))
  };
}

/** 当前浏览区间的标签（导航中键、合计行、柱状图 aria 三处共用，必须同一份） */
const rangeLabel = computed(() => {
  const year = cursor.value.getFullYear();
  const g = granularity.value;
  if (g === "day") return `${year} 年 ${cursor.value.getMonth() + 1} 月`;
  if (g === "month") return `${year} 年`;
  return `${year - YEAR_WINDOW + 1}–${year} 年`;
});

/** 导航语义随粒度切换：日=按月翻，月 / 年=按年翻 */
const nav = computed(() => {
  const isDay = granularity.value === "day";
  return {
    groupAria: isDay ? "月份导航" : "年份导航",
    prev: isDay ? "上个月" : "上一年",
    next: isDay ? "下个月" : "下一年"
  };
});

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
  return "该区间";
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
  if (granularity.value !== "day") {
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
  const { start, end } = rangeFor();
  try {
    const { data } = await getPnlCalendar({
      start_date: start,
      end_date: end,
      ledger_id: props.ledgerId,
      granularity: granularity.value
    });
    series.value = data;
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
  // 月 / 年粒度按年平移；**保留月序号**，切回日粒度时仍落在你原来那个月
  cursor.value = new Date(c.getFullYear() + delta, c.getMonth(), 1);
}

function goCurrent() {
  // 三种粒度都把游标放回「今天所在的那个月」：日粒度看当月，
  // 月 / 年粒度取 getFullYear()，自然就是今年 / 今天的年份
  cursor.value = firstOfMonth(new Date());
}

watch(() => props.ledgerId, load);
watch(cursor, load);
// 粒度切换时游标不动（这是有意的：切粒度不该顺手把你翻到别的区间），
// 故必须单独监听它触发重取——否则会拿日粒度的 payload 直接当月视图渲染。
watch(granularity, load);
onMounted(load);

defineExpose({ reload: load });
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.pnl-calendar {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 合计行：一行小字 */
.pnl-calendar__summary {
  display: flex;
  gap: 10px;
  align-items: baseline;
  padding-top: 10px;
  font-size: 12px;
  border-top: 1px solid var(--border-light);
}

.pnl-calendar__summary-label {
  color: var(--text-secondary);
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
