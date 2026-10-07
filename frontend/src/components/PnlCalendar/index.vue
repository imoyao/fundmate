<!--
  PnlCalendar · 每日收益日历（#1812）

  一组件两容器：welcome 嵌入卡（满宽12 列）/ panorama 弹窗，共用同一份数据与口径。

  四态视觉（**缺数据绝不能画成 0**，这是本组件存在的核心理由之一）：
    updown   涨红跌绿柔和填充，色深 ∝ |收益|
    zero     灰底 + 0.00（真实为零）
    no_price 斜线纹理（balance 模式无历史价格序列，如银行理财/投顾/实物）
    closed   空白（非交易日/未同步/区间首日）

  色彩纪律（design.md 硬约束）：
    - 只走 --color-rise / --color-fall（**绿跌**，不用参考图的蓝跌）；
    - 禁硬编码色值，全部 CSS 变量，var() 引用的令牌必须真实存在（check_css_vars.mjs 守卫）；
    - 柔和填充而非饱和实心块，避免长时间浏览疲劳。

  口径：数值全部来自后端 as-of 派生，**前端不做二次盈亏计算**。
-->

<template>
  <div class="pnl-calendar">
    <!-- ===== 标题行：口径说明 + 视图切换 + 月份切换 ===== -->
    <SectionHeader title="收益日历" :info="CALIBER_NOTE">
      <template #action>
        <div class="flex items-center gap-2">
          <!-- 日历图 / 柱状图：共用同一份序列，切换的是呈现角度 -->
          <SegmentedControl
            v-model="view"
            :options="VIEW_OPTIONS"
            size="small"
            ariaLabel="切换收益视图"
          />
          <!-- 月份导航。`role="group"` + `aria-label` 是按钮组的正确 a11y 语义：
               组本身不是按钮，但需一个可访问名来把「上个月/今天/下个月」三枚按钮
               归为一组。顺带说明：守卫 `guard_a11y_interaction.py` 的
               `<(el-button|button)\b` 会把 `el-button-group` 一并匹配上，
               这里给组加名是正解，不是为过守卫而塞的无用属性。 -->
          <el-button-group role="group" aria-label="月份导航">
            <el-button
              size="small"
              text
              aria-label="上个月"
              :disabled="loading"
              @click="shiftMonth(-1)"
            >
              <IconifyIconOffline icon="ep:arrow-left" />
            </el-button>
            <el-button size="small" text :disabled="loading" @click="goToday">
              {{ monthLabel }}
            </el-button>
            <el-button
              size="small"
              text
              aria-label="下个月"
              :disabled="loading"
              @click="shiftMonth(1)"
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
      <!-- 数据缺口要给出口：用户能一键跳到有数据的那个月，
           否则只能自己一次次翻月份试。 -->
      <el-button
        v-if="emptyIsDataGap && latestPriceMonth"
        size="small"
        text
        type="primary"
        @click="jumpToLatestPriceMonth"
      >
        查看 {{ latestPriceMonth }} 有数据的月份
      </el-button>
    </div>

    <!-- ===== 主体：日历图 / 柱状图 ===== -->
    <template v-else>
      <div v-if="view === 'calendar'" class="pnl-calendar__grid-wrap">
        <div class="pnl-calendar__weekdays" aria-hidden="true">
          <span v-for="w in WEEKDAYS" :key="w">{{ w }}</span>
        </div>
        <div class="pnl-calendar__grid" role="grid">
          <div
            v-for="cell in calendarCells"
            :key="cell.key"
            class="pnl-calendar__cell"
            :class="[
              `is-${cell.state}`,
              {
                'is-today': cell.isToday,
                'is-void': cell.void,
                // 色深档位：仅加在有真实盈亏的格子上，零收益/无价/休市不参与映射
                [`lv-${cell.level}`]: cell.state === 'updown',
                'is-fall': cell.isFall
              }
            ]"
            role="gridcell"
            :aria-label="cell.ariaLabel"
          >
            <template v-if="!cell.void">
              <span class="pnl-calendar__day">{{ cell.day }}</span>
              <MoneyDisplay
                v-if="cell.state === 'updown' || cell.state === 'zero'"
                :value="cell.pnl"
                size="xs"
                :show-currency="false"
                :auto-color="false"
                :custom-color="cell.textColor"
              />
              <span v-else class="pnl-calendar__tag">{{
                STATE_TAG[cell.state]
              }}</span>
            </template>
          </div>
        </div>
      </div>

      <!-- 柱状图：月内逐日（与日历同一份序列，回答「月内起伏」） -->
      <PnlCalendarBars
        v-else
        :days="series?.days ?? []"
        :month-label="monthLabel"
        :month-total="series?.month_total ?? 0"
      />

      <!-- ===== 合计行：一行小字，不占纵向空间（Voice & Content规范） ===== -->
      <div class="pnl-calendar__summary">
        <span class="pnl-calendar__summary-label">{{ monthLabel }}合计</span>
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
import PnlCalendarBars from "./PnlCalendarBars.vue";
import {
  getPnlCalendar,
  type PnlCalendarDay,
  type PnlCalendarSeries,
  type PnlCalendarState
} from "@/api/summary";

defineOptions({ name: "PnlCalendar" });

const props = withDefaults(
  defineProps<{
    /** 账户ID：不传=家庭级，传=该账户级（账户维度天然支持，见设计文档 §3） */
    ledgerId?: number;
    /** 容器形态：embedded=嵌入卡（welcome）；dialog=弹窗（panorama） */
    variant?: "embedded" | "dialog";
  }>(),
  { ledgerId: undefined, variant: "embedded" }
);

const emit = defineEmits<{
  (e: "select-day", payload: { date: string; day: PnlCalendarDay }): void;
}>();

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"] as const;
const VIEW_OPTIONS = [
  { label: "日历图", value: "calendar" },
  { label: "柱状图", value: "bar" }
] as const;

/** 四态的紧凑标签（格内空间有限，tooltip 里有完整解释） */
const STATE_TAG: Record<PnlCalendarState, string> = {
  updown: "",
  zero: "0.00",
  // 用户明确要求：不要说「无历史价格序列」——那是实现语言，用户看不懂，
  // 且会被误解成「我的理财出问题了」。产品语言是「暂无每日估值」。
  no_price: "暂无估值",
  closed: "休市",
  // #1917：部分断档。数值照常显示，只是可信度低——用「※」标记，
  // 用户扫一眼就知道「这天有东西没更新到」，aria/tooltip 有完整说明。
  partial: "※"
};

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
  "斜线格「暂无每日估值」= 该产品按日无估值序列（银行理财、投顾组合、实物资产等），不是收益为零。";

/**
 * 空态文案。**不要**命名为 `emptyText`——那是 `MoneyDisplay` 的 prop 名，
 * 同名会让模板里的 `{{ emptyText }}` 被解析到组件实例上（TS2339）。
 *
 * 必须区分两种「空」（#1812 上线首日的教训）：
 * · `data_gap`      该月一条价格数据都没有 → 多半是每日快照任务没跑，
 *                   要告诉用户「上个月有」，并给个可点的跳转；
 * · `unpriced_only` 持仓确实按日无估值序列 → 属产品属性，说清即可。
 * 混成一句「没有历史价格序列」会把上一种说成用户的持仓有问题。
 */
const EMPTY_DATA_GAP = (lastDate: string) =>
  `本月还没有每日估值数据。最近一次估值：${lastDate}。` +
  "通常是每日快照任务未运行所致，并非账户异常。";

const EMPTY_NO_VALUATION =
  "账户里的产品按日没有估值序列（银行理财、投顾组合、实物资产等），" +
  "因此没有每日收益。";

const series = ref<PnlCalendarSeries | null>(null);
const loading = ref(false);
const error = ref("");
const view = ref<"calendar" | "bar">("calendar");

/** 当前月份的首日（存该月1 日，避免时区漂移） */
const cursor = ref<Date>(firstOfMonth(new Date()));

function firstOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function ymd(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

const monthLabel = computed(
  () => `${cursor.value.getFullYear()} 年 ${cursor.value.getMonth() + 1} 月`
);

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

const latestPriceMonth = computed(() => {
  const d = series.value?.latest_price_date;
  if (!d) return "";
  const m = d.slice(0, 7);
  return m === monthLabel.value ? "" : m.replace("-", " 年 ") + " 月";
});

const emptyHint = computed(() =>
  emptyIsDataGap.value
    ? EMPTY_DATA_GAP(series.value?.latest_price_date ?? "—")
    : EMPTY_NO_VALUATION
);

function jumpToLatestPriceMonth() {
  const d = series.value?.latest_price_date;
  if (!d) return;
  const [y, m] = d.split("-").map(Number);
  cursor.value = new Date(y, m - 1, 1);
}

const dayMap = computed(() => {
  const map = new Map<string, PnlCalendarDay>();
  for (const d of series.value?.days ?? []) map.set(d.date, d);
  return map;
});

/** 当月最大绝对盈亏，用于色深映射（避免除零） */
const maxAbsPnl = computed(() => {
  let max = 0;
  for (const d of series.value?.days ?? []) {
    if (d.daily_pnl != null) max = Math.max(max, Math.abs(d.daily_pnl));
  }
  return max;
});

/** 色深档位：0（浅）/ 1（中）/ 2（深），由 |收益| / 月内最大值 决定 */
function intensity(pnl: number | null): 0 | 1 | 2 {
  if (pnl == null || maxAbsPnl.value === 0) return 0;
  const ratio = Math.abs(pnl) / maxAbsPnl.value;
  if (ratio >= 0.6) return 2;
  if (ratio >= 0.25) return 1;
  return 0;
}

interface CalendarCell {
  key: string;
  void: boolean;
  day: number;
  date: string;
  state: PnlCalendarState;
  pnl: number | null;
  isToday: boolean;
  isFall: boolean;
  /** 色深档位 0/1/2，由 |收益| / 月内最大绝对值 决定 */
  level: 0 | 1 | 2;
  textColor: string;
  ariaLabel: string;
}

const calendarCells = computed<CalendarCell[]>(() => {
  const year = cursor.value.getFullYear();
  const month = cursor.value.getMonth();
  const first = new Date(year, month, 1);
  // getDay(): 0=周日 → 转为周一为 0 的偏移
  const leading = (first.getDay() + 6) % 7;
  const totalDays = new Date(year, month + 1, 0).getDate();
  const todayStr = ymd(new Date());

  const cells: CalendarCell[] = [];
  for (let i = 0; i < leading; i += 1) {
    cells.push({
      key: `void-${i}`,
      void: true,
      day: 0,
      date: "",
      state: "closed",
      pnl: null,
      isToday: false,
      isFall: false,
      level: 0,
      textColor: "",
      ariaLabel: ""
    });
  }

  for (let d = 1; d <= totalDays; d += 1) {
    const date = ymd(new Date(year, month, d));
    const day = dayMap.value.get(date);
    const state: PnlCalendarState = day?.state ?? "closed";
    const pnl = day?.daily_pnl ?? null;
    cells.push({
      key: date,
      void: false,
      day: d,
      date,
      state,
      pnl,
      isToday: date === todayStr,
      isFall: pnl != null && pnl < 0,
      level: intensity(pnl),
      textColor: textColorFor(state, pnl),
      ariaLabel: ariaFor(date, state, pnl)
    });
  }
  return cells;
});

/** 文字色用 -ink 级（AA 达标），底色用柔和填充 —— 二者分工见 design.md 涨跌色应用 */
function textColorFor(state: PnlCalendarState, pnl: number | null): string {
  // partial 与 updown 同用 -ink 级文字（AA 达标）：涨跌方向必须可读，
  // 区别靠底色 + 「※」承载，不能靠降级文字色。
  if ((state === "updown" || state === "partial") && pnl != null) {
    return pnl > 0 ? "var(--color-rise-ink)" : "var(--color-fall-ink)";
  }
  return "var(--text-tertiary-ink)";
}

function ariaFor(
  date: string,
  state: PnlCalendarState,
  pnl: number | null
): string {
  if (state === "no_price") return `${date}：无价格序列，不参与收益计算`;
  if (state === "closed") return `${date}：非交易日或数据未同步`;
  // #1917：数值可信但该日有标的数据不全，必须说清「不全」而非「无」
  if (state === "partial")
    return `${date}：收益 ${pnl ?? 0} 元（该日部分标的未更新估值，数据不完整）`;
  if (state === "zero") return `${date}：收益 0.00 元`;
  return `${date}：收益 ${pnl ?? 0} 元`;
}

async function load() {
  loading.value = true;
  error.value = "";
  const year = cursor.value.getFullYear();
  const month = cursor.value.getMonth();
  const last = new Date(year, month + 1, 0).getDate();
  try {
    const { data } = await getPnlCalendar({
      start_date: `${year}-${String(month + 1).padStart(2, "0")}-01`,
      end_date: ymd(new Date(year, month, last)),
      ledger_id: props.ledgerId
    });
    series.value = data;
  } catch (e) {
    error.value = "收益日历加载失败，请稍后重试";
    series.value = null;
  } finally {
    loading.value = false;
  }
}

function shiftMonth(delta: number) {
  cursor.value = new Date(
    cursor.value.getFullYear(),
    cursor.value.getMonth() + delta,
    1
  );
}

function goToday() {
  cursor.value = firstOfMonth(new Date());
}

watch(() => props.ledgerId, load);
watch(cursor, load);
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

/* 窄屏（弹窗形态）压缩格子高度，但字号有下限，保证可读 */
.pnl-calendar__grid-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pnl-calendar__weekdays {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;

  span {
    font-size: 11px;
    color: var(--text-tertiary-ink);
    text-align: center;
  }
}

.pnl-calendar__grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
}

.pnl-calendar__cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  justify-content: center;

  /* aspect-ratio 保证格子近正方；min-height 兜底窄屏 */
  min-height: 62px;
  padding: 6px 2px;
  cursor: default;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  /* `.is-partial::after` 的斜纹叠加层需要相对定位的父元素（#1917） */
  position: relative;
  border-radius: 8px;
  transition:
    transform 0.15s ease,
    box-shadow 0.15s ease;
}

.pnl-calendar__day {
  font-size: 11px;
  line-height: 1;
  color: var(--text-tertiary-ink);
}

/* ── 四态视觉 ──
   updown 用柔和填充 + 涨红跌绿（**绿跌**，非参考图的蓝跌）。

   **色深上限 12% 是算出来的，不是随手填的**（实测 2026-10-06，WCAG AA 4.5:1）：
   底色 = color-mix(涨跌色, --bg-card, N%)，格内有两类文字都要达标——
     N=12% 涨：盈亏字 4.81:1 / 日期数字 4.59:1✅
     N=14% 涨：盈亏字 4.68:1 / 日期数字 4.47:1❌（日期数字跌破 AA）
   即**涨色的 12% 是硬顶**（跌色可到 24%，但两色必须同刻度，否则色深含义不一致）。
   这正是 design.md 警告的坑：日期数字走 --text-tertiary-ink（4.59:1）刚好压线，
   若图省事用 --text-tertiary（白底仅 3.69:1）则任何一档都必然不合格。
   ⇒ 色深只表达「相对大小」，**绝不允许为了视觉冲击加深到底色**。 */
.is-updown {
  border-color: var(--border-subtle);
}

.is-updown.lv-1 {
  background: color-mix(in srgb, var(--color-rise) 7%, var(--bg-card));
  border-color: color-mix(in srgb, var(--color-rise) 18%, var(--border-light));
}

.is-updown.lv-2 {
  background: color-mix(in srgb, var(--color-rise) 12%, var(--bg-card));
  border-color: color-mix(in srgb, var(--color-rise) 28%, var(--border-light));
}

.is-updown.is-fall.lv-1 {
  background: color-mix(in srgb, var(--color-fall) 7%, var(--bg-card));
  border-color: color-mix(in srgb, var(--color-fall) 18%, var(--border-light));
}

.is-updown.is-fall.lv-2 {
  background: color-mix(in srgb, var(--color-fall) 12%, var(--bg-card));
  border-color: color-mix(in srgb, var(--color-fall) 28%, var(--border-light));
}

/* 零收益：灰底 + 0.00，语义是「真的是零」 */
.is-zero {
  background: var(--bg-hover);
  border-color: var(--border-light);
}

/* 部分断档（#1917）：中性底 + 斜纹。
   ⚠️ 为什么不用涨跌底色：实测（WCAG AA，tint 12% 最深档）涨色叠斜纹后
   盈亏字 4.26 / 日期数字 4.07，双双跌破 4.5；即使把斜纹压到 3% 仍不合格——
   涨色 tint 12% 本身已接近上限（纯底 4.81 / 日期 4.59 刚好压线），没有余量。
   「数据不全」本就与涨跌无关，用中性底语义更准，对比度余量充足（3~12% 全通过）。
   涨跌方向改由 `-ink` 文字色 + 正负号承载，见 textColorFor()。

   用 `::after` 叠加层：`.pnl-calendar__cell` 用了 `background` 简写，
   会把 `background-image` 一并重置（同 specificity 下按源码顺序输赢，不可靠）。 */
.is-partial {
  background-color: var(--bg-hover);
  border-color: color-mix(in srgb, var(--text-tertiary) 30%, var(--border-light));
}

.is-partial::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background-image: repeating-linear-gradient(
    45deg,
    transparent,
    transparent 5px,
    color-mix(in srgb, var(--text-tertiary) 10%, transparent) 5px,
    color-mix(in srgb, var(--text-tertiary) 10%, transparent) 8px
  );
}

/* 文字层须在斜纹之上，否则金额与日期数字会被盖住 */
.pnl-calendar__day,
.pnl-calendar__amount {
  position: relative;
  z-index: 1;
}

/* 无价格序列：斜线纹理，与「零收益」「休市」三者可辨 */
.is-no_price {
  background: repeating-linear-gradient(
    45deg,
    transparent,
    transparent 4px,
    color-mix(in srgb, var(--text-tertiary) 12%, transparent) 4px,
    color-mix(in srgb, var(--text-tertiary) 12%, transparent) 7px
  );
  border-color: var(--border-subtle);
}

.pnl-calendar__tag {
  font-size: 10px;
  line-height: 1;
  color: var(--text-tertiary-ink);
}

/* 休市 / 首日：留白，不画任何数字（避免"看起来是 0"） */
.is-closed {
  background: transparent;
  border-color: var(--border-light);
}

/* 今日：细边框高亮，不改变底色 */
.is-today {
  outline: 2px solid var(--color-rise);
  outline-offset: -2px;
}

.is-void {
  background: transparent;
  border-color: transparent;
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

/* 响应式：窄屏压缩格子但保字号下限（design.md 可读性要求）。
   断点走 _breakpoints.scss 单一来源（`bp.below("sm")` = < 640px），
   禁手写像素——guard_breakpoints.py 会拦。 */
@include bp.below("sm") {
  .pnl-calendar__cell {
    min-height: 52px;
    padding: 4px 1px;
  }

  .pnl-calendar__day {
    font-size: 10px;
  }

  .pnl-calendar__summary {
    flex-wrap: wrap;
  }

  .pnl-calendar__summary-note {
    width: 100%;
    margin-left: 0;
  }
}
</style>
