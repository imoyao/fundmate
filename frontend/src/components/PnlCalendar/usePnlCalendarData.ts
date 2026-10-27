/**
 * PnlCalendar 的数据与导航状态机（#980 从 `index.vue` 抽出，纯搬运）。
 *
 * 这里装的是「取数区间怎么算、游标怎么动、下钻走哪一档」——三视图（日 / 月 / 年）
 * 共用同一份规则。`index.vue` 只剩模板装配，改视觉时不必翻两百行脚本。
 *
 * 三条硬约束（搬出来也一条都不能松）：
 * 1. **不二次计算盈亏**：聚合下推在后端（`granularity` 参数），前端只呈现。
 * 2. **下钻必须在动手之前问** `nextGranularity`（#2033）：宿主可以排掉某一档，
 *    而方格与柱体的点击路径与控件排是两条独立入口，只挡控件挡不住点击。
 * 3. **游标永远存某月 1 号**：避免时区漂移，也让日 / 月粒度来回切时不丢「你在看哪个月」。
 */

import { computed, onMounted, reactive, ref, watch } from "vue";
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
  emptyHintFor,
  isDataGap,
  jumpButtonTextFor,
  latestPriceLabelFor
} from "./emptyState";
import {
  getPnlCalendar,
  type PnlCalendarGranularity,
  type PnlCalendarSeries
} from "@/api/summary";

export function usePnlCalendarData(opts: {
  /** 账户 ID：不传 = 家庭级（`undefined` 会让 axios 丢掉该参数） */
  ledgerId: () => number | undefined;
  /** 宿主允许的粒度档位；不传 / 空数组 = 三档全开（#2033） */
  granularities: () => readonly PnlCalendarGranularity[] | undefined;
}) {
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
  const allowedGranularities = computed<readonly PnlCalendarGranularity[]>(
    () =>
      opts.granularities()?.length ? opts.granularities()! : ALL_GRANULARITIES
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
    () =>
      nextGranularity(granularity.value, allowedGranularities.value) !== null
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

  /** 当前浏览区间的标签（导航中键 / 区间标签、合计行、柱状图 aria 共用同一份） */
  const rangeLabel = computed(() =>
    rangeLabelFor(granularity.value, cursor.value, firstTxnDate.value)
  );

  const hasAnyPrice = computed(() => series.value?.has_any_price === true);

  /** 空态归因（#1812 上线首日的教训），判据见 `emptyState.isDataGap` */
  const emptyIsDataGap = computed(() => isDataGap(series.value));

  const emptyHint = computed(() =>
    emptyHintFor(series.value, granularity.value)
  );

  /** 有数据的最近一期（已正在看则回空串，跳转按钮随之隐藏） */
  const latestPriceLabel = computed(() =>
    latestPriceLabelFor(series.value, granularity.value, cursor.value)
  );

  const jumpButtonText = computed(() =>
    jumpButtonTextFor(latestPriceLabel.value, granularity.value)
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
        ledger_id: opts.ledgerId(),
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
  watch([opts.ledgerId, cursor, granularity], load);

  // 宿主中途收窄粒度集合时（宿主很少会动态改，但组件不该假设它不变）：
  // 当前粒度若已不在集合内，落到默认档，绝不停留在「控件里选不到」的那一档。
  watch(allowedGranularities, allowed => {
    if (allowed.includes(granularity.value)) return;
    granularity.value = defaultGranularity(allowed);
  });
  onMounted(load);

  /**
   * 返回 `reactive(...)` 而不是裸对象，是为了让**模板侧拿到解包后的类型**：
   * `reactive` 的类型是 `UnwrapNestedRefs`，属性在类型层就是 `boolean` / `string`
   * 而不是 `Ref<boolean>`。若直接返回 `{ loading, ... }`，`index.vue` 里
   * `v-if="cal.loading"` 在 `vue-tsc` 眼里是「Ref 恒真」——运行时被 proxyRefs 兜住
   * 不出错，但类型层会误报，且 reviewer 看不出这是真值判断还是引用判断。
   * 赋值方向同样成立：`v-model:granularity="cal.granularity"` 写回时 reactive 代理
   * 会把赋值转成 `granularity.value = ...`（Vue 的 ref 解包语义）。
   */
  return reactive({
    series,
    loading,
    error,
    view,
    granularity,
    valueMode,
    allowedGranularities,
    canDrill,
    cursor,
    rangeLabel,
    hasAnyPrice,
    emptyIsDataGap,
    emptyHint,
    latestPriceLabel,
    jumpButtonText,
    selectPeriod,
    jumpToLatestPrice,
    load,
    shift,
    goCurrent
  });
}
