# batch6 浠ｇ爜鎵嬪唽锛堝彲鐩存帴闃呰鐨勫叏閮ㄦ簮鐮侊級

> 鏈枃浠剁敱 `fundmate-optimization/batch6/` 涓嬪疄闄呬氦浠樻枃浠跺師鏍锋嫾鍚堬紝鐢ㄤ簬鍦ㄤ粎鏀寔 Markdown 鐨勫鎴风閲岄槄璇绘簮鐮併€?
> 鍏?14 涓枃浠躲€?

## `composables/welcome/context.ts`

```ts
// src/composables/welcome/context.ts
//
// welcome 璺ㄧ粍浠跺叡浜笂涓嬫枃锛坧rovide/inject锛夈€?
import { inject, type InjectionKey } from "vue";
import type { WelcomeContext } from "./types";

export const welcomeContextKey: InjectionKey<WelcomeContext> =
  Symbol("welcomeContext");

export function useWelcomeContext(): WelcomeContext {
  const ctx = inject(welcomeContextKey);
  if (!ctx) {
    throw new Error("useWelcomeContext 蹇呴』鍦?WelcomeIndex 鐨?provide 涔嬪唴浣跨敤");
  }
  return ctx;
}
```

## `composables/welcome/index.ts`

```ts
// src/composables/welcome/index.ts
export * from "./types";
export * from "./useWelcomeData";
export * from "./useWatchlistWidget";
export * from "./useWelcomeCharts";
export * from "./context";
```

## `composables/welcome/types.ts`

```ts
// src/composables/welcome/types.ts
//
// welcome锛堥椤电湅鏉匡級閲嶆瀯鐨勭被鍨嬪畾涔夈€?// 涓庡師 frontend/src/views/welcome/index.vue 鐨?<script setup> 1:1 瀵瑰簲銆?
import type { Ref } from "vue";
import type { SummaryData } from "@/api/types";

/** 鏀剁泭瓒嬪娍鐨勬椂闂寸矑搴︼紙鍘?trendMode锛?*/
export type TrendMode = "month" | "quarter";

/** 璐㈠姟鏅撮洦琛ㄩ潤鎬佹寚鏍囷紙鍘?financialMetrics锛?*/
export interface FinancialMetric {
  label: string;
  value: string | number;
  subLabel?: string;
}

/** 蹇冪悊璐︽埛闈欐€佹暟鎹紙鍘?mentalAccounts锛?*/
export interface MentalAccount {
  name: string;
  percent: number;
  amount: string | number;
  color: string;
}

/** 鍏变韩鏍革細鏁版嵁灞傦紙useWelcomeData 鐨勮繑鍥炲€硷級 */
export interface WelcomeData {
  summary: Ref<SummaryData | null>;
  portfolioXirr: Ref<any>;
  trendMode: Ref<TrendMode>;
  financialMetrics: FinancialMetric[];
  mentalAccounts: MentalAccount[];
  fetchSummary: () => Promise<void>;
  fetchXirr: () => Promise<void>;
  getCSSColor: (varName: string) => string;
}

/** 鑷€夌粍浠朵氦浜掑眰锛坲seWatchlistWidget 鐨勮繑鍥炲€硷級 */
export interface WelcomeWidget {
  showAddWatchlistModal: Ref<boolean>;
  watchlistWidgetKey: Ref<number>;
  watchlistWidgetRef: Ref<any>;
  watchlistTitle: Ref<string>;
  onWatchlistSelect: (item: any) => void;
  onWatchlistChanged: () => void;
}

/** 璺ㄧ粍浠跺叡浜笂涓嬫枃锛坧rovide/inject锛?*/
export interface WelcomeContext {
  data: WelcomeData;
  widget: WelcomeWidget;
  // 鍥捐〃 ref 鐢卞悇鍗＄墖缁勪欢閫氳繃 useXxxChart(data) 鑷鎸佹湁锛?  // 涓嶆斁鍏ヤ笂涓嬫枃锛堥伩鍏嶈法缁勪欢浼?Ref 鐨勮В鍖呴棶棰橈級銆?}
```

## `composables/welcome/useWatchlistWidget.ts`

```ts
// src/composables/welcome/useWatchlistWidget.ts
//
// 棣栭〉鈥滄寔浠撳競鍊兼渶澶ц祫浜р€濆崱鐗囩殑浜や簰灞傘€?// 鍘?index.vue 鐨?showAddWatchlistModal / watchlistWidgetKey / watchlistWidgetRef /
// watchlistTitle / onWatchlistSelect / onWatchlistChanged 鎼埌杩欓噷銆?
import { ref, computed } from "vue";
import WatchlistWidget from "@/components/WatchlistWidget.vue";

export function useWatchlistWidget() {
  const showAddWatchlistModal = ref(false);
  const watchlistWidgetKey = ref(0);
  const watchlistWidgetRef = ref<InstanceType<typeof WatchlistWidget> | null>(
    null,
  );

  // 鍘?watchlistTitle 璁＄畻灞炴€?  const watchlistTitle = computed(() => {
    if (!watchlistWidgetRef.value) return "鑷€夎祫浜?;
    return watchlistWidgetRef.value.hasPinned
      ? "缃《璧勪骇"
      : "鎸佷粨甯傚€兼渶澶ц祫浜?;
  });

  // 鍘?onWatchlistSelect
  const onWatchlistSelect = (item: any) => {
    // TODO: 鎼繍鍘?onWatchlistSelect 閫昏緫
  };

  // 鍘?onWatchlistChanged锛氳嚜澧?key 寮哄埗 Widget 鍒锋柊
  const onWatchlistChanged = () => {
    watchlistWidgetKey.value++;
  };

  return {
    showAddWatchlistModal,
    watchlistWidgetKey,
    watchlistWidgetRef,
    watchlistTitle,
    onWatchlistSelect,
    onWatchlistChanged,
  };
}
```

## `composables/welcome/useWelcomeCharts.ts`

```ts
// src/composables/welcome/useWelcomeCharts.ts
//
// 鎺ョ welcome 棣栭〉鐨?4 涓?ECharts 瀹炰緥锛堝師 initCharts / handleResize /
// window resize 鐩戝惉 / onUnmounted dispose 鍏ㄩ儴鎵嬪啓锛夈€?// 鏀圭敤鎵规 1 鐨?useEchartsLifecycle锛岀粺涓€ init/resize/dispose + keepAlive 閲嶇粯銆?//
// 璁捐锛氭瘡涓浘琛ㄥ崱鐗囩粍浠跺湪鑷韩 setup 鍐呰皟鐢ㄥ搴旂殑 useXxxChart(data)锛?// 鎷垮埌 chartRef 鍚庣粦瀹?<div ref="chartRef">锛堝瓧绗︿覆 ref锛岄伩鍏嶈法缁勪欢浼?Ref 鐨勮В鍖呭潙锛夈€?// 鍘?4 涓浘琛細
//   1. useDistributionChart 鈫?璧勪骇鏋勬垚鍒嗗竷锛堥ゼ锛?//   2. useTrendChart        鈫?鏀剁泭瓒嬪娍锛堢嚎锛屽彈 trendMode 鎺у埗锛?//   3. useRiskChart         鈫?椋庨櫓鐑姏鍥撅紙鏌憋級
//   4. useMiniChart         鈫?璧勪骇鍙樺姩瓒嬪娍锛堣糠浣犳煴锛?
import { ref, watch, nextTick, type Ref } from "vue";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
import { ECHARTS_COLOR } from "@/composables/echarts/theme";
import type { WelcomeData } from "./types";

export interface ChartHandle {
  chartRef: Ref<HTMLElement | null>;
  render: () => void;
}

/** 璧勪骇鏋勬垚鍒嗗竷锛堥ゼ锛?*/
export function useDistributionChart(data: WelcomeData): ChartHandle {
  const chartRef = ref<HTMLElement | null>(null);

  // TODO: 浠?data.summary 鏋勫缓楗煎浘 option锛涢厤鑹插紩鐢?ECHARTS_COLOR锛屽幓纭紪鐮?  const build = (): EChartsOption => ({});

  const { render } = useEchartsLifecycle(
    [chartRef],
    [
      (el) => {
        const c = echarts.init(el);
        c.setOption(build());
        return c;
      },
    ],
    { keepAlive: true, autoRenderOnMount: false },
  );

  watch(
    () => data.summary.value,
    async (s) => {
      if (s) {
        await nextTick();
        render();
      }
    },
  );

  return { chartRef, render };
}

/** 鏀剁泭瓒嬪娍锛堢嚎锛夛紝鍙?data.trendMode锛坢onth/quarter锛夋帶鍒?*/
export function useTrendChart(data: WelcomeData): ChartHandle {
  const chartRef = ref<HTMLElement | null>(null);

  // TODO: 浠?data.summary + data.trendMode 鏋勫缓绾垮浘 option
  const build = (): EChartsOption => ({});

  const { render } = useEchartsLifecycle(
    [chartRef],
    [
      (el) => {
        const c = echarts.init(el);
        c.setOption(build());
        return c;
      },
    ],
    { keepAlive: true, autoRenderOnMount: false },
  );

  // 鏁版嵁鎴栫矑搴﹀垏鎹㈤兘閲嶇粯
  watch(
    [() => data.summary.value, () => data.trendMode.value],
    async ([s]) => {
      if (s) {
        await nextTick();
        render();
      }
    },
  );

  return { chartRef, render };
}

/** 椋庨櫓鐑姏鍥撅紙鏌憋級 */
export function useRiskChart(data: WelcomeData): ChartHandle {
  const chartRef = ref<HTMLElement | null>(null);

  // TODO: 鏋勫缓椋庨櫓鐑姏鍥?option
  const build = (): EChartsOption => ({});

  const { render } = useEchartsLifecycle(
    [chartRef],
    [
      (el) => {
        const c = echarts.init(el);
        c.setOption(build());
        return c;
      },
    ],
    { keepAlive: true, autoRenderOnMount: false },
  );

  watch(
    () => data.summary.value,
    async (s) => {
      if (s) {
        await nextTick();
        render();
      }
    },
  );

  return { chartRef, render };
}

/** 璧勪骇鍙樺姩瓒嬪娍锛堣糠浣犳煴锛?*/
export function useMiniChart(data: WelcomeData): ChartHandle {
  const chartRef = ref<HTMLElement | null>(null);

  // TODO: 鏋勫缓杩蜂綘鏌卞浘 option
  const build = (): EChartsOption => ({});

  const { render } = useEchartsLifecycle(
    [chartRef],
    [
      (el) => {
        const c = echarts.init(el);
        c.setOption(build());
        return c;
      },
    ],
    { keepAlive: true, autoRenderOnMount: false },
  );

  watch(
    () => data.summary.value,
    async (s) => {
      if (s) {
        await nextTick();
        render();
      }
    },
  );

  return { chartRef, render };
}
```

## `composables/welcome/useWelcomeData.ts`

```ts
// src/composables/welcome/useWelcomeData.ts
//
// 鍏变韩鏍革細棣栭〉鐪嬫澘鐨勬暟鎹眰銆?// 鍘?index.vue 鐨?summary / portfolioXirr / trendMode / fetchSummary / fetchXirr /
// getCSSColor / financialMetrics / mentalAccounts 鍏ㄩ儴鎼埌杩欓噷銆?
import { ref } from "vue";
import { getSummary } from "@/api/summary";
import { getPortfolioXirr } from "@/api/performance";
import type { SummaryData } from "@/api/types";
import type { FinancialMetric, MentalAccount, WelcomeData } from "./types";

// 璐㈠姟鏅撮洦琛ㄩ潤鎬佹寚鏍囷紙鍘?index.vue 鍐呰仈 financialMetrics锛?// TODO: 鎼繍鍘?financialMetrics 鏁扮粍锛坽 label, value, subLabel }[]锛?const financialMetrics: FinancialMetric[] = [];

// 蹇冪悊璐︽埛闈欐€佹暟鎹紙鍘?index.vue 鍐呰仈 mentalAccounts锛?// TODO: 鎼繍鍘?mentalAccounts 鏁扮粍锛坽 name, percent, amount, color }[]锛?const mentalAccounts: MentalAccount[] = [];

export function useWelcomeData(): WelcomeData {
  const summary = ref<SummaryData | null>(null);
  const portfolioXirr = ref<any>(null);
  const trendMode = ref<"month" | "quarter">("month");

  // 鍘?fetchSummary锛歴ummary.value = res.data
  const fetchSummary = async () => {
    const res = await getSummary();
    summary.value = res.data;
  };

  // 鍘?fetchXirr锛歱ortfolioXirr.value = res.data
  const fetchXirr = async () => {
    const res = await getPortfolioXirr();
    portfolioXirr.value = res.data;
  };

  // 鍘?getCSSColor锛氳В鏋?CSS 鍙橀噺棰滆壊
  const getCSSColor = (varName: string): string => {
    if (typeof window === "undefined") return "";
    const v = getComputedStyle(document.documentElement)
      .getPropertyValue(varName)
      .trim();
    return v || "";
  };

  return {
    summary,
    portfolioXirr,
    trendMode,
    financialMetrics,
    mentalAccounts,
    fetchSummary,
    fetchXirr,
    getCSSColor,
  };
}
```

## `views/welcome/WelcomeIndex.vue`

```vue
<script setup lang="ts">
import { onMounted, provide } from "vue";
import {
  useWelcomeData,
  useWatchlistWidget,
  welcomeContextKey,
} from "@/composables/welcome";
import AddToWatchlistModal from "@/components/QuickEntry/AddToWatchlistModal.vue";
import AssetSummaryCards from "./components/AssetSummaryCards.vue";
import ReturnTrendCard from "./components/ReturnTrendCard.vue";
import XirrCard from "./components/XirrCard.vue";
import WatchlistCard from "./components/WatchlistCard.vue";
import RiskHeatmapCard from "./components/RiskHeatmapCard.vue";
import FinancialBarometerCard from "./components/FinancialBarometerCard.vue";
import MentalAccountsCard from "./components/MentalAccountsCard.vue";

const data = useWelcomeData();
const widget = useWatchlistWidget();

// 渚涙ā鏉夸娇鐢紙椤跺眰 ref 鑷姩瑙ｅ寘锛?const { showAddWatchlistModal, onWatchlistChanged } = widget;

// 璺ㄧ粍浠跺叡浜笂涓嬫枃
provide(welcomeContextKey, { data, widget });

// 鍘?onMounted锛歠etchSummary().then(() => nextTick(initCharts)) + fetchXirr()
// 鍥捐〃鏀逛负 useEchartsLifecycle(autoRenderOnMount:false) + watch(summary) 鑷姩 render
onMounted(() => {
  void Promise.all([data.fetchSummary(), data.fetchXirr()]);
});
</script>

<template>
  <div
    class="welcome-page min-h-full p-4 md:p-8"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <div class="mb-8">
      <h1 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">
        鍒汉鎭愭儳鎴戣椽濠紝鍒汉璐┆鎴戞洿璐┆
      </h1>
    </div>

    <!-- Row1锛氬搴祫浜х湅鏉?+ 鏀剁泭瓒嬪娍 -->
    <div class="grid xl:grid-cols-12 gap-4">
      <AssetSummaryCards class="xl:col-span-7" />
      <ReturnTrendCard class="xl:col-span-5" />
    </div>

    <!-- Row2锛氬勾鍖栨敹鐩婅拷韪?-->
    <XirrCard class="mt-4" />

    <!-- Row3锛氳嚜閫?+ 椋庨櫓鐑姏鍥?-->
    <div class="grid lg:grid-cols-12 gap-4 mt-4">
      <WatchlistCard class="lg:col-span-5" />
      <RiskHeatmapCard class="lg:col-span-7" />
    </div>

    <!-- Row4锛氳储鍔℃櫞闆ㄨ〃 + 蹇冪悊璐︽埛 -->
    <div class="flex flex-col lg:flex-row gap-4 mt-4">
      <FinancialBarometerCard class="lg:flex-1" />
      <MentalAccountsCard class="lg:w-96" />
    </div>

    <!-- 鍔犺嚜閫夊脊绐楋紙鍘?AddToWatchlistModal锛寁-model 浠ョ粍浠剁湡瀹?prop 涓哄噯锛?-->
    <AddToWatchlistModal
      v-model="showAddWatchlistModal"
      @added="onWatchlistChanged"
    />
  </div>
</template>
```

## `views/welcome/components/AssetSummaryCards.vue`

```vue
<script setup lang="ts">
import { useWelcomeContext, useDistributionChart } from "@/composables/welcome";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";

const { data } = useWelcomeContext();
const { summary } = data;
// 璧勪骇鏋勬垚鍒嗗竷锛堥ゼ锛夛細鏈崱鐗囪嚜绠″浘琛?ref锛岄伩鍏嶈法缁勪欢浼?Ref
const { chartRef } = useDistributionChart(data);
</script>

<template>
  <div
    class="rounded-xl p-6"
    :style="{
      backgroundColor: 'var(--bg-card)',
      border: '1px solid var(--border-default)',
    }"
  >
    <h3
      class="text-sm font-medium"
      :style="{ color: 'var(--text-secondary)' }"
    >
      瀹跺涵璧勪骇鐪嬫澘
    </h3>
    <div class="grid grid-cols-3 gap-4 mt-4">
      <div>
        <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">鎬昏祫浜?/p>
        <!-- 瀛楁鍚嶄互 @/api/types 鐨?SummaryData 涓哄噯 -->
        <MoneyDisplay :value="summary?.total_assets" />
      </div>
      <div>
        <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">绱鏀剁泭</p>
        <MoneyDisplay :value="summary?.total_profit" />
      </div>
      <div>
        <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">鏈湀鍙樺姩</p>
        <MoneyDisplay :value="summary?.monthly_change" />
      </div>
    </div>
    <div ref="chartRef" class="h-64 mt-4"></div>
  </div>
</template>
```

## `views/welcome/components/FinancialBarometerCard.vue`

```vue
<script setup lang="ts">
import { useWelcomeContext, useMiniChart } from "@/composables/welcome";

const { data } = useWelcomeContext();
const { financialMetrics } = data;
// 璧勪骇鍙樺姩瓒嬪娍锛堣糠浣犳煴锛?const { chartRef } = useMiniChart(data);
</script>

<template>
  <div
    class="rounded-xl p-6"
    :style="{
      backgroundColor: 'var(--bg-card)',
      border: '1px solid var(--border-default)',
    }"
  >
    <h3
      class="text-sm font-medium"
      :style="{ color: 'var(--text-secondary)' }"
    >
      璐㈠姟鏅撮洦琛?    </h3>
    <div class="grid grid-cols-4 gap-4 mt-4">
      <div v-for="m in financialMetrics" :key="m.label">
        <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
          {{ m.label }}
        </p>
        <p class="text-lg font-semibold">{{ m.value }}</p>
        <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
          {{ m.subLabel }}
        </p>
      </div>
    </div>
    <div ref="chartRef" class="h-40 mt-4"></div>
  </div>
</template>
```

## `views/welcome/components/MentalAccountsCard.vue`

```vue
<script setup lang="ts">
import { useWelcomeContext } from "@/composables/welcome";

const { data } = useWelcomeContext();
const { mentalAccounts } = data;
</script>

<template>
  <div
    class="rounded-xl p-6"
    :style="{
      backgroundColor: 'var(--bg-card)',
      border: '1px solid var(--border-default)',
    }"
  >
    <h3
      class="text-sm font-medium"
      :style="{ color: 'var(--text-secondary)' }"
    >
      蹇冪悊璐︽埛
    </h3>
    <ul class="mt-4 space-y-3">
      <li v-for="a in mentalAccounts" :key="a.name">
        <div class="flex justify-between text-sm">
          <span>{{ a.name }}</span>
          <span>{{ a.amount }}</span>
        </div>
        <div class="h-2 rounded bg-gray-200 mt-1 overflow-hidden">
          <div
            class="h-2 rounded"
            :style="{ width: a.percent + '%', backgroundColor: a.color }"
          ></div>
        </div>
      </li>
    </ul>
  </div>
</template>
```

## `views/welcome/components/ReturnTrendCard.vue`

```vue
<script setup lang="ts">
import { useWelcomeContext, useTrendChart } from "@/composables/welcome";

const { data } = useWelcomeContext();
const { trendMode } = data;
// 鏀剁泭瓒嬪娍锛堢嚎锛夛紝鍙?trendMode 鎺у埗
const { chartRef } = useTrendChart(data);
</script>

<template>
  <div
    class="rounded-xl p-6"
    :style="{
      backgroundColor: 'var(--bg-card)',
      border: '1px solid var(--border-default)',
    }"
  >
    <div class="flex items-center justify-between">
      <h3
        class="text-sm font-medium"
        :style="{ color: 'var(--text-secondary)' }"
      >
        鏀剁泭瓒嬪娍
      </h3>
      <el-button-group>
        <el-button
          :type="trendMode === 'month' ? 'primary' : 'default'"
          size="small"
          @click="trendMode = 'month'"
        >
          鏈?        </el-button>
        <el-button
          :type="trendMode === 'quarter' ? 'primary' : 'default'"
          size="small"
          @click="trendMode = 'quarter'"
        >
          瀛?        </el-button>
      </el-button-group>
    </div>
    <div ref="chartRef" class="h-64 mt-4"></div>
    <p class="mt-2 text-sm" :style="{ color: 'var(--text-secondary)' }">
      椋庨櫓璇勫垎 <b>65</b>/100
    </p>
  </div>
</template>
```

## `views/welcome/components/RiskHeatmapCard.vue`

```vue
<script setup lang="ts">
import { useWelcomeContext, useRiskChart } from "@/composables/welcome";

const { data } = useWelcomeContext();
const { summary } = data;
// 椋庨櫓鐑姏鍥撅紙鏌憋級
const { chartRef } = useRiskChart(data);
</script>

<template>
  <div
    class="rounded-xl p-6"
    :style="{
      backgroundColor: 'var(--bg-card)',
      border: '1px solid var(--border-default)',
    }"
  >
    <h3
      class="text-sm font-medium"
      :style="{ color: 'var(--text-secondary)' }"
    >
      椋庨櫓鐑姏鍥?    </h3>
    <div ref="chartRef" class="h-64 mt-4"></div>
    <!-- TODO: 鍥句緥 -->
  </div>
</template>
```

## `views/welcome/components/WatchlistCard.vue`

```vue
<script setup lang="ts">
import { useWelcomeContext } from "@/composables/welcome";
import WatchlistWidget from "@/components/WatchlistWidget.vue";

const { widget } = useWelcomeContext();
const {
  showAddWatchlistModal,
  watchlistWidgetKey,
  watchlistWidgetRef,
  watchlistTitle,
  onWatchlistSelect,
  onWatchlistChanged,
} = widget;
</script>

<template>
  <div
    class="rounded-xl p-6"
    :style="{
      backgroundColor: 'var(--bg-card)',
      border: '1px solid var(--border-default)',
    }"
  >
    <div class="flex items-center justify-between mb-4">
      <h3
        class="text-sm font-medium"
        :style="{ color: 'var(--text-secondary)' }"
      >
        {{ watchlistTitle }}
      </h3>
      <el-button text type="primary" size="small" @click="showAddWatchlistModal = true">
        + 鍔犺嚜閫?      </el-button>
    </div>
    <WatchlistWidget
      :key="watchlistWidgetKey"
      ref="watchlistWidgetRef"
      @select="onWatchlistSelect"
      @changed="onWatchlistChanged"
    />
  </div>
</template>
```

## `views/welcome/components/XirrCard.vue`

```vue
<script setup lang="ts">
import { useWelcomeContext } from "@/composables/welcome";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";

const { data } = useWelcomeContext();
const { portfolioXirr } = data;
</script>

<template>
  <div
    class="rounded-xl p-6"
    :style="{
      backgroundColor: 'var(--bg-card)',
      border: '1px solid var(--border-default)',
    }"
  >
    <h3
      class="text-sm font-medium"
      :style="{ color: 'var(--text-secondary)' }"
    >
      骞村寲鏀剁泭杩借釜
    </h3>
    <div class="grid grid-cols-3 gap-4 mt-4">
      <div>
        <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
          骞村寲鏀剁泭鐜?XIRR)
        </p>
        <RiseFallText :value="portfolioXirr?.xirr" />
      </div>
      <div>
        <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
          褰撳墠甯傚€?        </p>
        <MoneyDisplay :value="portfolioXirr?.current_value" />
      </div>
      <div>
        <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
          绱鎶曞叆
        </p>
        <MoneyDisplay :value="portfolioXirr?.total_invested" />
      </div>
    </div>
  </div>
</template>
```
