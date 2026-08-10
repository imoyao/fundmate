# batch8 浠ｇ爜鎵嬪唽锛堝彲鐩存帴闃呰鐨勫叏閮ㄦ簮鐮侊級

> 鏈枃浠剁敱 `fundmate-optimization/batch8/` 涓嬪疄闄呬氦浠樻枃浠跺師鏍锋嫾鍚堬紝鐢ㄤ簬鍦ㄤ粎鏀寔 Markdown 鐨勫鎴风閲岄槄璇绘簮鐮併€?
> 鍏?11 涓枃浠躲€?

## `composables/panorama/context.ts`

```ts
// src/composables/panorama/context.ts
//
// 璺ㄧ粍浠跺叡浜笂涓嬫枃锛坧rovide/inject锛夈€?// 浠呮敞鍏ユ暟鎹眰 data锛涘浘琛?ref 鐢卞悇鍗＄墖閫氳繃 useWaterfallChart(data) 鑷鎸佹湁锛?// 涓嶈繘涓婁笅鏂囷紙閬垮厤璺ㄧ粍浠朵紶 Ref 鐨勮В鍖呭潙锛岃瑙佹壒娆?6 README锛夈€?
import { inject, type InjectionKey } from "vue";
import type { PanoramaContext } from "./types";

export const panoramaContextKey: InjectionKey<PanoramaContext> =
  Symbol("panoramaContext");

export function usePanoramaContext(): PanoramaContext {
  const ctx = inject(panoramaContextKey);
  if (!ctx) {
    throw new Error(
      "[panorama] 蹇呴』鍦?AssetPanoramaIndex 鎻愪緵 panoramaContextKey 鐨勭鍏堝唴浣跨敤",
    );
  }
  return ctx;
}
```

## `composables/panorama/index.ts`

```ts
// src/composables/panorama/index.ts
//
// 璧勪骇鍏ㄦ櫙妯″潡缁熶竴鍑哄彛銆?
export * from "./types";
export * from "./usePanoramaData";
export * from "./useWaterfallChart";
export * from "./context";
```

## `composables/panorama/types.ts`

```ts
// src/composables/panorama/types.ts
import type { Ref, ComputedRef } from "vue";

export type SankeyDisplayMode = "amount" | "percent" | "hidden";
export type BalanceTab = "assets" | "liabilities";
export type DetailView = string;

export interface SankeyData {
  nodes: any[];
  links: any[];
}

/** 鏁版嵁灞傦紙usePanoramaData 鐨勮繑鍥炲€硷級 */
export interface PanoramaData {
  allPositions: Ref<any[]>;
  allAssets: Ref<any[]>;
  ledgers: Ref<any[]>;
  totalAssets: Ref<number>;
  totalLiabilities: Ref<number>;
  totalPnl: Ref<number>;
  sankeyData: Ref<SankeyData>;
  loading: Ref<boolean>;
  sankeyDisplayMode: Ref<SankeyDisplayMode>;
  balanceTab: Ref<BalanceTab>;
  detailView: Ref<DetailView>;
  fetchData: () => Promise<void>;
  currentDetailGroups: ComputedRef<any[]>;
  assetBalanceRows: ComputedRef<any[]>;
  liabilityBalanceRows: ComputedRef<any[]>;
  typeDetailGroups: ComputedRef<any[]>;
  accountDetailGroups: ComputedRef<any[]>;
  allocationDetailGroups: ComputedRef<any[]>;
  getCSSColor: (varName: string) => string;
  getTypeRoute: (type: string) => string;
  handleGroupClick: (...args: any[]) => void;
  goToInventory: (...args: any[]) => void;
}

/** 璺ㄧ粍浠跺叡浜笂涓嬫枃锛坧rovide/inject锛?*/
export interface PanoramaContext {
  data: PanoramaData;
  // 鍥捐〃 ref 鐢卞悇鍗＄墖閫氳繃 useWaterfallChart(data) 鑷鎸佹湁锛屼笉杩涗笂涓嬫枃
}
```

## `composables/panorama/usePanoramaData.ts`

```ts
// src/composables/panorama/usePanoramaData.ts
//
// 鍏变韩鏍革細璧勪骇鍏ㄦ櫙椤电殑鏁版嵁灞傘€?// 鍘?AssetPanorama.vue 鐨?allPositions/allAssets/ledgers/totalAssets/totalLiabilities/
// totalPnl/sankeyData/loading/sankeyDisplayMode/balanceTab/detailView + fetchData +
// 6 涓?computed锛坈urrentDetailGroups 绛夛級+ getCSSColor/getTypeRoute/handleGroupClick/
// goToInventory 鍏ㄩ儴鎼埌杩欓噷銆?
import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import { getPositions } from "@/api/positions";
import { getSummary, getSankeyData } from "@/api/summary";
import { getAssets } from "@/api/assets";
import { getLedgers } from "@/api/ledger";
import { getAllocationLabel } from "@/constants";
import type { PanoramaData, SankeyData } from "./types";

// 鍘熷唴鑱?EXCHANGE_RATES 鈥斺€?寤鸿鏀瑰紩鎵规1鐨?@/constants/exchangeRates
const EXCHANGE_RATES: Record<string, number> = { CNY: 1, USD: 7.25, HKD: 0.92 };

export function usePanoramaData(): PanoramaData {
  const allPositions = ref<any[]>([]);
  const allAssets = ref<any[]>([]);
  const ledgers = ref<any[]>([]);
  const totalAssets = ref(0);
  const totalLiabilities = ref(0);
  const totalPnl = ref(0);
  const sankeyData = ref<SankeyData>({ nodes: [], links: [] });
  const loading = ref(false);
  const sankeyDisplayMode = ref<"amount" | "percent" | "hidden">("amount");
  const balanceTab = ref<"assets" | "liabilities">("assets");
  const detailView = ref("category");

  const router = useRouter();

  // 鍘?fetchData锛氬苟琛屾媺鍙?+ 鏄犲皠銆傛槧灏勯€昏緫锛堢畻 totalAssets 绛夛級TODO 鎼繍
  const fetchData = async () => {
    loading.value = true;
    try {
      const [positions, summary, sankey, assets, ledgerList] = await Promise.all([
        getPositions(),
        getSummary(),
        getSankeyData(),
        getAssets(),
        getLedgers(),
      ]);
      allPositions.value = positions.data ?? positions ?? [];
      sankeyData.value = sankey.data ?? sankey ?? { nodes: [], links: [] };
      allAssets.value = assets.data ?? assets ?? [];
      ledgers.value = ledgerList.data ?? ledgerList ?? [];
      // TODO: 鎼繍鍘熸槧灏勯€昏緫 鈫?totalAssets / totalLiabilities / totalPnl
    } finally {
      loading.value = false;
    }
  };

  // 鈹€鈹€ 6 涓淳鐢?computed锛堝師 currentDetailGroups / assetBalanceRows 绛夛級鈹€鈹€
  // TODO: 鎼繍鍘熻绠楅€昏緫锛堟寜 detailView / balanceTab 鍒嗙粍锛?  const currentDetailGroups = computed(() => []);
  const assetBalanceRows = computed(() => []);
  const liabilityBalanceRows = computed(() => []);
  const typeDetailGroups = computed(() => []);
  const accountDetailGroups = computed(() => []);
  const allocationDetailGroups = computed(() => []);

  // 鍘?getCSSColor
  const getCSSColor = (varName: string): string => {
    if (typeof window === "undefined") return "";
    return getComputedStyle(document.documentElement)
      .getPropertyValue(varName)
      .trim();
  };

  // 鍘?getTypeRoute锛氱被鍨嬪悕 鈫?璺敱
  const getTypeRoute = (type: string): string => {
    // TODO: 鎼師鏄犲皠
    return `/asset/inventory?type=${type}`;
  };

  // 鍘?handleGroupClick锛氭寜 detailView 璺敱璺宠浆
  const handleGroupClick = (...args: any[]) => {
    // TODO: 鎼師閫昏緫
    void args;
  };

  // 鍘?goToInventory
  const goToInventory = (...args: any[]) => {
    router.push({ path: "/asset/inventory", query: { tab: args[0] } });
  };

  return {
    allPositions,
    allAssets,
    ledgers,
    totalAssets,
    totalLiabilities,
    totalPnl,
    sankeyData,
    loading,
    sankeyDisplayMode,
    balanceTab,
    detailView,
    fetchData,
    currentDetailGroups,
    assetBalanceRows,
    liabilityBalanceRows,
    typeDetailGroups,
    accountDetailGroups,
    allocationDetailGroups,
    getCSSColor,
    getTypeRoute,
    handleGroupClick,
    goToInventory,
  };
}

// 渚涘叾浠栨ā鍧楀紩鐢ㄥ唴鑱斿父閲忥紙濡傞渶瑕侊級
export { EXCHANGE_RATES, getAllocationLabel };
```

## `composables/panorama/useWaterfallChart.ts`

```ts
// src/composables/panorama/useWaterfallChart.ts
//
// 鎺ョ璧勪骇鍏ㄦ櫙椤靛敮涓€鐨?ECharts 瀹炰緥鈥斺€旇祫浜х€戝竷鍥撅紙鍘?initWaterfallChart锛夈€?// 鍘熶唬鐮侊細鎵嬪啓 echarts.init / 鏃?resize 鐩戝惉 / 鏃?onUnmounted dispose /
// 鏃?onActivated锛?panorama 鏍囪 keepAlive 鍗寸己 鈫?鍒囧洖鍓嶅彴鍥捐〃绌虹櫧锛夈€?// 鏀圭敤鎵规 1 鐨?useEchartsLifecycle锛岀粺涓€ init/resize/dispose + keepAlive 閲嶇粯銆?//
// 鍗＄墖缁勪欢鍦ㄨ嚜韬?setup 鍐呰皟鐢?useWaterfallChart(data)锛屾嬁鍒?chartRef 鍚庣粦瀹?// <div ref="chartRef">锛堝瓧绗︿覆 ref锛岄伩鍏嶈法缁勪欢浼?Ref 鐨勮В鍖呭潙锛夈€?//
// 閰嶈壊鏀圭敤鎵规 1 鐨?getCssVar锛堝彇浠ｅ師鍐呰仈 getCSSColor 閲嶅瀹炵幇锛屽幓纭紪鐮侊級銆?
import { ref, watch, nextTick, type Ref } from "vue";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
import { getCssVar } from "@/composables/echarts/theme";
import type { PanoramaData } from "./types";

export interface ChartHandle {
  chartRef: Ref<HTMLElement | null>;
  render: () => void;
}

/** 璧勪骇鐎戝竷鍥?*/
export function useWaterfallChart(data: PanoramaData): ChartHandle {
  const chartRef = ref<HTMLElement | null>(null);

  // 鍘?initWaterfallChart锛歴tart / changes 涓虹‖缂栫爜绀轰緥鍊笺€?  // TODO: 鏀逛负浠?data.assetBalanceRows / data.totalLiabilities / data.totalPnl
  // 娲剧敓锛堜笂鏈熸湯 鈫?鍚勫垎绫诲彉鍔?鈫?璐熷€?鈫?鏈湡鏈級锛屼笅闈繚鐣欏師缁撴瀯浠ヤ究鍏堣窇閫氥€?  const build = (): EChartsOption => {
    const primaryColor = getCssVar("--brand-700");
    const infoColor = getCssVar("--color-info");
    const riseColor = getCssVar("--color-rise");
    const fallColor = getCssVar("--color-fall");
    const neutralColor = getCssVar("--color-neutral");

    const start = 2800000;
    const changes = [
      { name: "娴佸姩璧勯噾", value: -233251 },
      { name: "鍥哄畾璧勪骇", value: 0 },
      { name: "鎶曡祫鐞嗚储", value: 262225 },
      { name: "璐熷€?, value: -20406 },
    ];
    const end = start + changes.reduce((s, c) => s + c.value, 0);
    const cumulativeValues: number[] = [start];
    changes.forEach((item, index) => {
      cumulativeValues.push(cumulativeValues[index] + item.value);
    });
    const allData = [
      { name: "涓婃湡鏈?, height: start, change: start, isEndpoint: true },
      ...changes.map((item, index) => ({
        name: item.name,
        height: cumulativeValues[index + 1],
        change: item.value,
        isEndpoint: false,
      })),
      { name: "鏈湡鏈?, height: end, change: end, isEndpoint: true },
    ];

    return {
      tooltip: { trigger: "axis" },
      grid: { left: "8%", right: "4%", top: 20, bottom: 50, containLabel: true },
      xAxis: {
        type: "category",
        data: allData.map((d) => d.name),
        axisLabel: {
          rotate: 30,
          fontSize: 10,
          color: getCssVar("--text-tertiary"),
        },
        axisLine: { lineStyle: { color: getCssVar("--border-light") } },
      },
      yAxis: {
        type: "value",
        min: 0,
        splitLine: { lineStyle: { color: getCssVar("--border-light") } },
        axisLabel: {
          color: getCssVar("--text-tertiary"),
          fontSize: 11,
          formatter: (v: number) => v.toLocaleString(),
        },
      },
      series: [
        {
          type: "bar",
          data: allData.map((d) => d.height),
          barWidth: "30%",
          barMinHeight: 4,
          itemStyle: {
            borderRadius: 4,
            color: (params: any) => {
              const d = allData[params.dataIndex];
              if (d.isEndpoint && d.name === "涓婃湡鏈?) return primaryColor;
              if (d.isEndpoint && d.name === "鏈湡鏈?) return infoColor;
              if (d.change > 0) return riseColor;
              if (d.change < 0) return fallColor;
              return neutralColor;
            },
          },
          label: {
            show: true,
            position: "top",
            fontSize: 10,
            color: getCssVar("--text-secondary"),
            formatter: (params: any) => {
              const d = allData[params.dataIndex];
              if (d.isEndpoint) return "楼" + d.height.toLocaleString();
              if (d.change === 0) return "楼0";
              return (d.change >= 0 ? "+" : "") + d.change.toLocaleString();
            },
          },
        },
      ],
    };
  };

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

  // 鍘熷畧鍗細allPositions 涓虹┖鍒欒烦杩囷紱鍚屾椂鐩戝惉姹囨€诲€煎彉鍖栭噸缁?  watch(
    [
      () => data.allPositions.value.length,
      () => data.totalAssets.value,
      () => data.totalLiabilities.value,
      () => data.totalPnl.value,
    ],
    async () => {
      if (data.allPositions.value.length > 0 || data.totalAssets.value > 0) {
        await nextTick();
        render();
      }
    },
  );

  return { chartRef, render };
}
```

## `views/asset/panorama/AssetPanoramaIndex.vue`

```vue
<script setup lang="ts">
// src/views/asset/panorama/AssetPanoramaIndex.vue
//
// 璧勪骇鍏ㄦ櫙椤靛澹炽€傚師 AssetPanorama.vue锛堝崟浣?God Component锛夋媶涓猴細
//   鍏变韩鏍?usePanoramaData锛堟暟鎹眰 + 6 涓?computed + getCSSColor 绛夛級
//   鍥捐〃鍔╂墜 useWaterfallChart锛堟帴 useEchartsLifecycle锛?//   5 寮犲崱鐗囩粍浠讹紙Summary / Sankey / Waterfall / Balance / Detail锛?// 閫氳繃 provide(panoramaContextKey, { data }) 涓嬪彂锛屽瓙缁勪欢 usePanoramaContext() 娑堣垂銆?// 鏇挎崲鍘熺粍浠跺彧闇€鎶婅矾鐢辨寚鍚戞湰澶栧３锛屽苟鍒犲幓鏃у崟浣撴枃浠躲€?
import { onMounted, provide } from "vue";
import { usePanoramaData } from "@/composables/panorama/usePanoramaData";
import { panoramaContextKey } from "@/composables/panorama/context";
import SummaryCards from "./components/SummaryCards.vue";
import SankeyCard from "./components/SankeyCard.vue";
import WaterfallCard from "./components/WaterfallCard.vue";
import BalanceCard from "./components/BalanceCard.vue";
import DetailCard from "./components/DetailCard.vue";

const data = usePanoramaData();
provide(panoramaContextKey, { data });

onMounted(() => void data.fetchData());
</script>

<template>
  <div class="panorama-page">
    <SummaryCards />

    <el-row :gutter="16">
      <el-col :xs="24" :lg="12">
        <SankeyCard />
      </el-col>
      <el-col :xs="24" :lg="12">
        <WaterfallCard />
      </el-col>
    </el-row>

    <BalanceCard />
    <DetailCard />
  </div>
</template>

<style scoped>
.panorama-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
</style>
```

## `views/asset/panorama/components/BalanceCard.vue`

```vue
<script setup lang="ts">
// 璧勪骇鍏ㄦ櫙锛氳祫浜ц礋鍊哄崱鐗囥€?// 鍘?assetBalanceRows / liabilityBalanceRows 涓や釜 computed 鐨勫睍绀哄眰銆?// balanceTab锛坅ssets / liabilities锛夊垏鎹㈢敱 el-segmented 缁戝畾锛堝師閫昏緫锛夈€?
import { computed } from "vue";
import { usePanoramaContext } from "@/composables/panorama";
import type { BalanceTab } from "@/composables/panorama";

const { data } = usePanoramaContext();

const {
  balanceTab,
  assetBalanceRows,
  liabilityBalanceRows,
  totalAssets,
  totalLiabilities,
} = data;

const tabOptions: { label: string; value: BalanceTab }[] = [
  { label: "璧勪骇", value: "assets" },
  { label: "璐熷€?, value: "liabilities" },
];

const rows = computed(() =>
  balanceTab.value === "assets" ? assetBalanceRows.value : liabilityBalanceRows.value,
);
const total = computed(() =>
  balanceTab.value === "assets" ? totalAssets.value : totalLiabilities.value,
);
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="balance-header">
        <span>璧勪骇璐熷€?/span>
        <el-segmented v-model="balanceTab" :options="tabOptions" />
      </div>
    </template>

    <el-table :data="rows" stripe>
      <el-table-column prop="name" label="绫诲埆" />
      <el-table-column prop="value" label="閲戦">
        <template #default="{ row }">
          <MoneyDisplay :value="row.value" size="sm" :show-currency="true" />
        </template>
      </el-table-column>
      <el-table-column prop="percent" label="鍗犳瘮">
        <template #default="{ row }">{{ row.percent }}%</template>
      </el-table-column>
    </el-table>

    <div class="balance-total">
      鍚堣锛?MoneyDisplay :value="total" size="sm" :show-currency="true" />
    </div>
  </el-card>
</template>

<style scoped>
.balance-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.balance-total {
  margin-top: 12px;
  text-align: right;
  color: var(--text-secondary);
}
</style>
```

## `views/asset/panorama/components/DetailCard.vue`

```vue
<script setup lang="ts">
// 璧勪骇鍏ㄦ櫙锛氭槑缁嗗垎缁勫崱鐗囥€?// 鍘?currentDetailGroups锛堟寜 detailView 鍦?type/account/allocation 闂村垏鎹級+ handleGroupClick銆?// detailView 鐢?el-segmented 缁戝畾锛涘垎缁勭偣鍑?鈫?data.handleGroupClick / goToInventory銆?
import { usePanoramaContext } from "@/composables/panorama";

const { data } = usePanoramaContext();

const { detailView, currentDetailGroups } = data;

const viewOptions = [
  { label: "鍒嗙被", value: "category" },
  { label: "绫诲瀷", value: "type" },
  { label: "璐︽埛", value: "account" },
  { label: "閰嶇疆", value: "allocation" },
];

const onGroupClick = (group: any) => {
  // 鍘?handleGroupClick 鎸?detailView 璺敱锛沢oToInventory 璺宠祫浜ф竻鍗?  data.handleGroupClick(group);
};
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="detail-header">
        <span>璧勪骇鏄庣粏</span>
        <el-segmented v-model="detailView" :options="viewOptions" />
      </div>
    </template>

    <el-row :gutter="16">
      <el-col
        v-for="group in currentDetailGroups"
        :key="group.name"
        :xs="24"
        :sm="12"
        :md="8"
      >
        <el-card shadow="hover" class="group-card" @click="onGroupClick(group)">
          <div class="group-name">{{ group.name }}</div>
          <div class="group-total">
            <MoneyDisplay :value="group.total" size="sm" :show-currency="true" />
          </div>
          <div class="group-pnl">
            <RiseFallText :value="group.totalPnl" suffix="" size="sm" />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </el-card>
</template>

<style scoped>
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.group-card {
  cursor: pointer;
  margin-bottom: 12px;
}
.group-name {
  font-weight: 600;
}
.group-total {
  margin-top: 4px;
}
.group-pnl {
  margin-top: 2px;
}
</style>
```

## `views/asset/panorama/components/SankeyCard.vue`

```vue
<script setup lang="ts">
// 璧勪骇鍏ㄦ櫙锛氳祫閲戞祦鍚戞鍩哄浘鍗＄墖銆?// 澶嶇敤椤圭洰鏃㈡湁鍏ㄥ眬缁勪欢 <SankeyChart>锛坧rops: data {nodes,links} / display-mode锛夈€?// 鍘熸ā鏉匡細<SankeyChart :data="sankeyData" :display-mode="sankeyDisplayMode" />銆?// 鏄剧ず绮掑害鍒囨崲锛堥噾棰?/ 鐧惧垎姣?/ 闅愯棌锛夌粦瀹?sankeyDisplayMode锛堝師 el-segmented锛夈€?
import { usePanoramaContext } from "@/composables/panorama";
import type { SankeyDisplayMode } from "@/composables/panorama";

const { data } = usePanoramaContext();

const { sankeyData, sankeyDisplayMode } = data;

const displayOptions: { label: string; value: SankeyDisplayMode }[] = [
  { label: "閲戦", value: "amount" },
  { label: "鐧惧垎姣?, value: "percent" },
  { label: "闅愯棌", value: "hidden" },
];
</script>

<template>
  <el-card shadow="never" header="璧勯噾娴佸悜">
    <template #header>
      <div class="sankey-header">
        <span>璧勯噾娴佸悜</span>
        <el-segmented
          v-model="sankeyDisplayMode"
          :options="displayOptions"
        />
      </div>
    </template>

    <SankeyChart :data="sankeyData" :display-mode="sankeyDisplayMode" />
  </el-card>
</template>

<style scoped>
.sankey-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
```

## `views/asset/panorama/components/SummaryCards.vue`

```vue
<script setup lang="ts">
// 璧勪骇鍏ㄦ櫙锛氶《閮ㄦ眹鎬诲崱鐗囥€傛壙杞芥€昏祫浜?/ 鎬昏礋鍊?/ 鎬荤泩浜?+ 鍒锋柊銆?// 鍘?AssetPanorama 妯℃澘椤堕儴涓変釜 <MoneyDisplay> + 鍒锋柊鎸夐挳锛屾澶勬娊绂讳负鐙珛鍗＄墖銆?// MoneyDisplay / RiseFallText / IconifyIconOffline 涓哄叏灞€娉ㄥ唽缁勪欢锛屾ā鏉夸腑鐩存帴浣跨敤銆?
import { usePanoramaContext } from "@/composables/panorama";

const { data } = usePanoramaContext();

// 椤跺眰瑙ｆ瀯 鈫?妯℃澘鑷姩瑙ｅ寘
const { totalAssets, totalLiabilities, totalPnl, loading } = data;
</script>

<template>
  <el-card shadow="never">
    <div class="summary-header">
      <span class="summary-title">璧勪骇鍏ㄦ櫙</span>
      <el-button
        :loading="loading"
        text
        bg
        @click="data.fetchData()"
      >
        <IconifyIconOffline icon="ep:refresh" />
        鍒锋柊
      </el-button>
    </div>

    <el-row :gutter="16">
      <el-col :span="8">
        <div class="metric">
          <span class="metric-label">鎬昏祫浜?/span>
          <MoneyDisplay
            :value="totalAssets"
            size="hero"
            :show-sign="false"
            :show-currency="true"
          />
        </div>
      </el-col>
      <el-col :span="8">
        <div class="metric">
          <span class="metric-label">鎬昏礋鍊?/span>
          <MoneyDisplay
            :value="totalLiabilities"
            size="md"
            :show-sign="false"
            :show-currency="true"
          />
        </div>
      </el-col>
      <el-col :span="8">
        <div class="metric">
          <span class="metric-label">鎬荤泩浜?/span>
          <MoneyDisplay
            :value="totalPnl"
            size="md"
            :show-currency="true"
          />
        </div>
      </el-col>
    </el-row>
  </el-card>
</template>

<style scoped>
.summary-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.summary-title {
  font-size: 16px;
  font-weight: 600;
}
.metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.metric-label {
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
```

## `views/asset/panorama/components/WaterfallCard.vue`

```vue
<script setup lang="ts">
// 璧勪骇鍏ㄦ櫙锛氳祫浜х€戝竷鍥惧崱鐗囥€?// 閫氳繃 useWaterfallChart(data) 鑷鎸佹湁 chartRef锛堝瓧绗︿覆 ref 缁戝畾锛夛紝涓嶈繘涓婁笅鏂囥€?// 鍘熸墜鍐?echarts.init / 鏃?resize / 鏃?onUnmounted / 鏃?onActivated
// 鈫?鐜扮粺涓€鐢?useEchartsLifecycle 鎺ョ锛坘eepAlive 閲嶇粯宸蹭慨澶嶏級銆?
import { usePanoramaContext } from "@/composables/panorama";
import { useWaterfallChart } from "@/composables/panorama/useWaterfallChart";

const { data } = usePanoramaContext();
const { chartRef } = useWaterfallChart(data);
</script>

<template>
  <el-card shadow="never" header="璧勪骇鐎戝竷">
    <div ref="chartRef" class="waterfall-chart"></div>
  </el-card>
</template>

<style scoped>
.waterfall-chart {
  width: 100%;
  height: 320px;
}
</style>
```
