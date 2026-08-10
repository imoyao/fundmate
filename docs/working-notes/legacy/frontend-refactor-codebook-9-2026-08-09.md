# batch9 浠ｇ爜鎵嬪唽锛堝彲鐩存帴闃呰鐨勫叏閮ㄦ簮鐮侊級

> 鏈枃浠剁敱 `fundmate-optimization/batch9/` 涓嬪疄闄呬氦浠樻枃浠跺師鏍锋嫾鍚堬紝鐢ㄤ簬鍦ㄤ粎鏀寔 Markdown 鐨勫鎴风閲岄槄璇绘簮鐮併€?
> 鍏?11 涓枃浠躲€?

## `composables/portfolio/context.ts`

```ts
// src/composables/portfolio/context.ts
//
// 璺ㄧ粍浠跺叡浜笂涓嬫枃锛坧rovide/inject锛夈€傚３缁勪欢 provide锛屽瓙鍗＄墖 usePortfolioDetailContext() 娑堣垂銆?
import { inject, type InjectionKey } from "vue";
import type { PortfolioDetailContext } from "./types";

export const portfolioDetailContextKey: InjectionKey<PortfolioDetailContext> =
  Symbol("portfolioDetailContext");

export function usePortfolioDetailContext(): PortfolioDetailContext {
  const ctx = inject(portfolioDetailContextKey);
  if (!ctx) {
    throw new Error(
      "[portfolio] 蹇呴』鍦?PortfolioDetailIndex 鎻愪緵 portfolioDetailContextKey 鐨勭鍏堝唴浣跨敤",
    );
  }
  return ctx;
}
```

## `composables/portfolio/index.ts`

```ts
// src/composables/portfolio/index.ts
//
// 缁勫悎璇︽儏妯″潡缁熶竴鍑哄彛銆?
export * from "./types";
export * from "./usePortfolioDetail";
export * from "./context";
```

## `composables/portfolio/types.ts`

```ts
// src/composables/portfolio/types.ts
import type { Ref, ComputedRef } from "vue";

export type SortOrder = "ascending" | "descending" | null;

export interface EditForm {
  name: string;
  purpose: string;
  description: string;
  target_return: number | undefined;
  target_amount: number | undefined;
  target_date: string;
  benchmark: string;
}

/** 鏁版嵁灞傦紙usePortfolioDetail 鐨勮繑鍥炲€硷級 */
export interface PortfolioDetailData {
  portfolioId: ComputedRef<number>;
  loading: Ref<boolean>;
  portfolio: Ref<any>;
  linkedLedgers: Ref<any[]>;
  xirrData: Ref<any>;
  xirrLoading: Ref<boolean>;
  sortProp: Ref<string | null>;
  sortOrder: Ref<SortOrder>;
  holdings: Ref<any[]>;
  holdingsPage: Ref<number>;
  holdingsPageSize: number;
  editVisible: Ref<boolean>;
  saving: Ref<boolean>;
  allLedgers: Ref<any[]>;
  selectedLedgerIds: Ref<number[]>;
  editForm: Ref<EditForm>;
  sortedHoldings: ComputedRef<any[]>;
  pagedHoldings: ComputedRef<any[]>;
  fetchDetail: () => Promise<void>;
  fetchLinkedLedgers: () => Promise<void>;
  fetchHoldings: () => Promise<void>;
  fetchXirr: () => Promise<void>;
  openEditDialog: () => Promise<void>;
  handleUpdate: () => Promise<void>;
  handleDelete: () => Promise<void>;
  goToLedger: (id: number) => void;
  handleSortChange: (sort: { prop: string; order: SortOrder }) => void;
  refreshAll: () => Promise<void>;
}

/** 璺ㄧ粍浠跺叡浜笂涓嬫枃锛坧rovide/inject锛?*/
export interface PortfolioDetailContext {
  data: PortfolioDetailData;
}
```

## `composables/portfolio/usePortfolioDetail.ts`

```ts
// src/composables/portfolio/usePortfolioDetail.ts
//
// 鍏变韩鏍革細缁勫悎璇︽儏椤电殑鏁版嵁灞?+ 琛屼负灞傘€?// 鍘?portfolio/detail.vue锛堢害 18.9KB锛屽崟浣擄級鐨?ref/reactive/computed/鏂规硶鍏ㄩ儴鎼埌杩欓噷銆?//
// 閲嶈锛氱粡婧愮爜鏍稿锛宲ortfolio/detail.vue 涓嶅惈浠讳綍 ECharts 瀹炰緥
// 锛堟壒娆?1 娉ㄩ噴鏇捐鍒楀畠涓?ECharts 娉勬紡鐐癸紝宸叉洿姝ｏ紝瑙?batch9/README.md锛夈€?// 鍥犳鏈壒娆″彧鍋氥€岀粍浠舵媶鍒?+ 鐘舵€佷笅娌夈€嶏紝鏃犻渶鎺ュ叆 useEchartsLifecycle銆?
import { ref, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  getPortfolio,
  updatePortfolio,
  deletePortfolio,
  getPortfolioHoldings,
  getPortfolios,
} from "@/api/portfolio";
import { getLedgers, updateLedger } from "@/api/ledger";
import { http } from "@/utils/http";
import type {
  PortfolioDetailData,
  EditForm,
  SortOrder,
} from "./types";

export function usePortfolioDetail(): PortfolioDetailData {
  const route = useRoute();
  const router = useRouter();

  const portfolioId = computed(() => Number(route.params.id));

  const loading = ref(true);
  const portfolio = ref<any>(null);
  const linkedLedgers = ref<any[]>([]);
  const xirrData = ref<any>(null);
  const xirrLoading = ref(false);
  const sortProp = ref<string | null>(null);
  const sortOrder = ref<SortOrder>(null);

  const holdings = ref<any[]>([]);
  const holdingsPage = ref(1);
  const holdingsPageSize = 20;

  const editVisible = ref(false);
  const saving = ref(false);
  const allLedgers = ref<any[]>([]);
  const selectedLedgerIds = ref<number[]>([]);
  const editForm = ref<EditForm>({
    name: "",
    purpose: "",
    description: "",
    target_return: undefined,
    target_amount: undefined,
    target_date: "",
    benchmark: "",
  });

  // 鈹€鈹€ 娲剧敓 鈹€鈹€
  const sortedHoldings = computed(() => {
    if (!sortProp.value || !sortOrder.value) return [...holdings.value];
    const sorted = [...holdings.value];
    sorted.sort((a, b) => {
      const valA = a[sortProp.value as string] ?? 0;
      const valB = b[sortProp.value as string] ?? 0;
      return sortOrder.value === "ascending" ? valA - valB : valB - valA;
    });
    return sorted;
  });

  const pagedHoldings = computed(() => {
    const start = (holdingsPage.value - 1) * holdingsPageSize;
    return sortedHoldings.value.slice(start, start + holdingsPageSize);
  });

  // 鈹€鈹€ 鏁版嵁鍔犺浇 鈹€鈹€
  const fetchDetail = async () => {
    const res: any = await getPortfolio(portfolioId.value);
    portfolio.value = res?.data ?? res;
  };

  const fetchLinkedLedgers = async () => {
    const res: any = await getLedgers();
    const list: any[] = res?.data ?? res ?? [];
    linkedLedgers.value = list.filter(
      (l) => l.portfolio_id === portfolioId.value,
    );
  };

  const fetchHoldings = async () => {
    const res: any = await getPortfolioHoldings(portfolioId.value);
    holdings.value = res?.data ?? res ?? [];
  };

  const fetchXirr = async () => {
    xirrLoading.value = true;
    try {
      // TODO: 杩佺Щ涓?typed api锛堝 getPortfolioXirr锛?      xirrData.value = await http.request("get", "/api/performance/xirr/", {
        params: { scope: "portfolio", portfolio_id: portfolioId.value },
      });
    } finally {
      xirrLoading.value = false;
    }
  };

  const refreshAll = async () => {
    loading.value = true;
    try {
      await Promise.all([
        fetchDetail(),
        fetchLinkedLedgers(),
        fetchHoldings(),
        fetchXirr(),
      ]);
    } finally {
      loading.value = false;
    }
  };

  // 鈹€鈹€ 缂栬緫 鈹€鈹€
  const openEditDialog = async () => {
    const [ledgerRes, portfolioRes] = await Promise.all([
      getLedgers(),
      getPortfolios(),
    ]);
    allLedgers.value = (ledgerRes as any)?.data ?? ledgerRes ?? [];
    const portfolios: any[] = (portfolioRes as any)?.data ?? portfolioRes ?? [];
    void portfolios;
    selectedLedgerIds.value =
      portfolio.value?.linked_ledger_ids ??
      linkedLedgers.value.map((l: any) => l.id);
    editForm.value = {
      name: portfolio.value?.name ?? "",
      purpose: portfolio.value?.purpose ?? "",
      description: portfolio.value?.description ?? "",
      target_return: portfolio.value?.target_return,
      target_amount: portfolio.value?.target_amount,
      target_date: portfolio.value?.target_date ?? "",
      benchmark: portfolio.value?.benchmark ?? "",
    };
    editVisible.value = true;
  };

  const handleUpdate = async () => {
    saving.value = true;
    try {
      await updatePortfolio(portfolioId.value, editForm.value);
      await Promise.all(
        selectedLedgerIds.value.map((id) =>
          updateLedger(id, { portfolio_id: portfolioId.value }),
        ),
      );
      editVisible.value = false;
      await fetchDetail();
    } finally {
      saving.value = false;
    }
  };

  const handleDelete = async () => {
    await deletePortfolio(portfolioId.value);
    router.push("/asset/portfolios");
  };

  const goToLedger = (id: number) => {
    router.push(`/asset/ledgers/${id}`);
  };

  const handleSortChange = (sort: {
    prop: string;
    order: SortOrder;
  }) => {
    sortProp.value = sort.prop;
    sortOrder.value = sort.order;
  };

  return {
    portfolioId,
    loading,
    portfolio,
    linkedLedgers,
    xirrData,
    xirrLoading,
    sortProp,
    sortOrder,
    holdings,
    holdingsPage,
    holdingsPageSize,
    editVisible,
    saving,
    allLedgers,
    selectedLedgerIds,
    editForm,
    sortedHoldings,
    pagedHoldings,
    fetchDetail,
    fetchLinkedLedgers,
    fetchHoldings,
    fetchXirr,
    openEditDialog,
    handleUpdate,
    handleDelete,
    goToLedger,
    handleSortChange,
    refreshAll,
  };
}
```

## `views/asset/portfolio/PortfolioDetailIndex.vue`

```vue
<script setup lang="ts">
// src/views/asset/portfolio/PortfolioDetailIndex.vue
//
// 缁勫悎璇︽儏椤靛澹炽€傚師 portfolio/detail.vue锛堝崟浣擄級鎷嗕负锛?//   鍏变韩鏍?usePortfolioDetail锛堟暟鎹?+ 鏂规硶 + 2 涓?computed锛?//   5 涓睍绀?浜や簰缁勪欢锛圚eader / InfoCards / Xirr / HoldingsTable / LinkedLedgers / EditDialog锛?// 閫氳繃 provide(portfolioDetailContextKey, { data }) 涓嬪彂锛屽瓙缁勪欢 usePortfolioDetailContext() 娑堣垂銆?// 娉ㄦ剰锛氬師鏂囦欢鏃犱换浣?ECharts锛屾湰鎵规鍙媶缁勪欢銆佷笉鎺?useEchartsLifecycle锛堣 README锛夈€?// 鏇挎崲鍘熺粍浠跺彧闇€璺敱鎸囧悜鏈澹冲苟鍒犳棫鏂囦欢銆?
import { onMounted, provide } from "vue";
import { usePortfolioDetail } from "@/composables/portfolio/usePortfolioDetail";
import { portfolioDetailContextKey } from "@/composables/portfolio/context";
import PortfolioHeader from "./components/PortfolioHeader.vue";
import PortfolioInfoCards from "./components/PortfolioInfoCards.vue";
import XirrCard from "./components/XirrCard.vue";
import HoldingsTable from "./components/HoldingsTable.vue";
import LinkedLedgersCard from "./components/LinkedLedgersCard.vue";
import EditPortfolioDialog from "./components/EditPortfolioDialog.vue";

const data = usePortfolioDetail();
provide(portfolioDetailContextKey, { data });

// 椤跺眰瑙ｆ瀯 鈫?妯℃澘鑷姩瑙ｅ寘
const { loading, portfolio } = data;

onMounted(() => void data.refreshAll());
</script>

<template>
  <div class="portfolio-detail">
    <PortfolioHeader />

    <template v-if="loading">
      <el-card shadow="never">鍔犺浇涓?..</el-card>
    </template>
    <template v-else-if="portfolio">
      <PortfolioInfoCards />
      <XirrCard />
      <HoldingsTable />
      <LinkedLedgersCard />
    </template>

    <EditPortfolioDialog />
  </div>
</template>

<style scoped>
.portfolio-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
</style>
```

## `views/asset/portfolio/components/EditPortfolioDialog.vue`

```vue
<script setup lang="ts">
// 缁勫悎璇︽儏锛氱紪杈戠粍鍚堝脊绐椼€傚鐢?usePortfolioDetail 鐨?editForm / allLedgers /
// selectedLedgerIds / saving / handleUpdate銆傚師 edit dialog銆?// 椤跺眰瑙ｆ瀯 editVisible / editForm / selectedLedgerIds 浠ヤ究 v-model 鑷姩瑙ｅ寘銆?
import { usePortfolioDetailContext } from "@/composables/portfolio";

const { data } = usePortfolioDetailContext();
const { editVisible, editForm, allLedgers, selectedLedgerIds, saving } = data;
</script>

<template>
  <el-dialog
    v-model="editVisible"
    title="缂栬緫缁勫悎"
    width="520px"
    destroy-on-close
  >
    <el-form label-width="96px">
      <el-form-item label="鍚嶇О" required>
        <el-input v-model="editForm.name" />
      </el-form-item>
      <el-form-item label="鐢ㄩ€?>
        <el-input v-model="editForm.purpose" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="鎻忚堪">
        <el-input v-model="editForm.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="鐩爣鏀剁泭鐜?>
        <el-input-number v-model="editForm.target_return" :precision="2" :step="0.5" />
        <span class="suffix">%</span>
      </el-form-item>
      <el-form-item label="鐩爣閲戦">
        <el-input-number v-model="editForm.target_amount" :precision="2" :step="1000" />
      </el-form-item>
      <el-form-item label="鐩爣鏃ユ湡">
        <el-date-picker
          v-model="editForm.target_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="閫夋嫨鏃ユ湡"
        />
      </el-form-item>
      <el-form-item label="鍩哄噯鎸囨暟">
        <el-input v-model="editForm.benchmark" />
      </el-form-item>
      <el-form-item label="鍏宠仈璐︽埛">
        <el-select
          v-model="selectedLedgerIds"
          multiple
          filterable
          placeholder="閫夋嫨鍏宠仈璐︽埛"
          class="ledger-select"
        >
          <el-option
            v-for="l in allLedgers"
            :key="l.id"
            :label="l.name"
            :value="l.id"
          />
        </el-select>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="editVisible = false">鍙栨秷</el-button>
      <el-button type="primary" :loading="saving" @click="data.handleUpdate()">
        淇濆瓨
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.suffix {
  margin-left: 8px;
  color: var(--text-tertiary);
}
.ledger-select {
  width: 100%;
}
</style>
```

## `views/asset/portfolio/components/HoldingsTable.vue`

```vue
<script setup lang="ts">
// 缁勫悎璇︽儏锛氭寔浠撴槑缁嗚〃銆傛帓搴忥紙@sort-change锛? 鍓嶇鍒嗛〉锛坧agedHoldings锛夈€?// 鍘?holdings detail card銆傛暟鎹潵鑷?usePortfolioDetail.pagedHoldings / handleSortChange銆?
import { usePortfolioDetailContext } from "@/composables/portfolio";

const { data } = usePortfolioDetailContext();
const { pagedHoldings, holdingsPage, holdingsPageSize } = data;
</script>

<template>
  <el-card shadow="never" header="鎸佷粨鏄庣粏">
    <el-table
      :data="pagedHoldings"
      stripe
      size="default"
      :default-sort="{ prop: '', order: null }"
      @sort-change="data.handleSortChange"
    >
      <el-table-column prop="name" label="鍚嶇О" min-width="140" />
      <el-table-column prop="symbol" label="浠ｇ爜" width="120" />
      <el-table-column prop="market_value" label="甯傚€? width="140" align="right" sortable />
      <el-table-column prop="pnl" label="鐩堜簭" width="140" align="right" sortable>
        <template #default="{ row }">
          <RiseFallText :value="row.pnl" size="sm" />
        </template>
      </el-table-column>
      <el-table-column prop="weight" label="鏉冮噸" width="100" align="right" sortable />
    </el-table>

    <el-pagination
      v-model:current-page="holdingsPage"
      :page-size="holdingsPageSize"
      layout="total, prev, pager, next"
      :total="data.holdings.value.length"
      small
      class="holdings-pager"
    />
  </el-card>
</template>

<style scoped>
.holdings-pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
```

## `views/asset/portfolio/components/LinkedLedgersCard.vue`

```vue
<script setup lang="ts">
// 缁勫悎璇︽儏锛氬叧鑱旇处鎴疯〃銆傛瘡琛屻€屾煡鐪嬨€嶈烦杞埌瀵瑰簲璐︽湰锛坓oToLedger锛夈€?// 鍘?linked accounts card銆?
import { usePortfolioDetailContext } from "@/composables/portfolio";

const { data } = usePortfolioDetailContext();
const { linkedLedgers } = data;
</script>

<template>
  <el-card shadow="never" header="鍏宠仈璐︽埛">
    <el-table :data="linkedLedgers" stripe>
      <el-table-column prop="name" label="璐︽埛鍚? min-width="160" />
      <el-table-column prop="type" label="绫诲瀷" width="120" />
      <el-table-column prop="balance" label="浣欓" width="160" align="right">
        <template #default="{ row }">
          <MoneyDisplay :value="row.balance" size="sm" :show-currency="true" />
        </template>
      </el-table-column>
      <el-table-column label="鎿嶄綔" width="100" align="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="data.goToLedger(row.id)">
            鏌ョ湅
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>
```

## `views/asset/portfolio/components/PortfolioHeader.vue`

```vue
<script setup lang="ts">
// 缁勫悎璇︽儏锛氬ご閮ㄣ€傝繑鍥炴寜閽?+ 缁勫悎鍚?鐢ㄩ€?+ 缂栬緫 + 鍒犻櫎锛坧opconfirm锛夈€?// 鍘熸ā鏉块《閮ㄨ繑鍥炴寜閽?+ header 鍖猴紙name/purpose/edit/delete锛夈€?
import { usePortfolioDetailContext } from "@/composables/portfolio";

const { data } = usePortfolioDetailContext();
const { portfolio } = data;
</script>

<template>
  <div class="mb-4">
    <el-button text @click="$router.push('/asset/portfolios')">
      <IconifyIconOffline icon="ep:arrow-left" class="mr-1" /> 杩斿洖缁勫悎鍒楄〃
    </el-button>
  </div>

  <el-card shadow="never" v-if="portfolio">
    <div class="header-row">
      <div>
        <div class="portfolio-name">{{ portfolio.name }}</div>
        <div class="portfolio-purpose">{{ portfolio.purpose }}</div>
      </div>
      <div class="header-actions">
        <el-button @click="data.openEditDialog()">
          <IconifyIconOffline icon="ep:edit" class="mr-1" /> 缂栬緫
        </el-button>
        <el-popconfirm title="纭鍒犻櫎璇ョ粍鍚堬紵" @confirm="data.handleDelete()">
          <template #reference>
            <el-button type="danger" plain>
              <IconifyIconOffline icon="ep:delete" class="mr-1" /> 鍒犻櫎
            </el-button>
          </template>
        </el-popconfirm>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.portfolio-name {
  font-size: 18px;
  font-weight: 600;
}
.portfolio-purpose {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-top: 4px;
}
.header-actions {
  display: flex;
  gap: 8px;
}
</style>
```

## `views/asset/portfolio/components/PortfolioInfoCards.vue`

```vue
<script setup lang="ts">
// 缁勫悎璇︽儏锛氬熀纭€淇℃伅鍗＄墖锛堝叧鑱旇处鎴锋暟 / 鐩爣鏀剁泭鐜?/ 鍩哄噯鎸囨暟锛夈€?// 鍘?basic info cards row锛堝叧鑱旇处鎴?/ 鐩爣鏀剁泭鐜?/ 鍩哄噯鎸囨暟锛夈€?
import { usePortfolioDetailContext } from "@/composables/portfolio";

const { data } = usePortfolioDetailContext();
const { portfolio, linkedLedgers } = data;
</script>

<template>
  <el-row :gutter="16">
    <el-col :span="8">
      <el-card shadow="never">
        <div class="info-label">鍏宠仈璐︽埛</div>
        <div class="info-value">{{ linkedLedgers.length }} 涓?/div>
      </el-card>
    </el-col>
    <el-col :span="8">
      <el-card shadow="never">
        <div class="info-label">鐩爣鏀剁泭鐜?/div>
        <div class="info-value">
          {{ portfolio?.target_return != null ? portfolio.target_return + "%" : "鈥? }}
        </div>
      </el-card>
    </el-col>
    <el-col :span="8">
      <el-card shadow="never">
        <div class="info-label">鍩哄噯鎸囨暟</div>
        <div class="info-value">{{ portfolio?.benchmark || "鈥? }}</div>
      </el-card>
    </el-col>
  </el-row>
</template>

<style scoped>
.info-label {
  font-size: 12px;
  color: var(--text-tertiary);
}
.info-value {
  font-size: 20px;
  font-weight: 600;
  margin-top: 4px;
}
</style>
```

## `views/asset/portfolio/components/XirrCard.vue`

```vue
<script setup lang="ts">
// 缁勫悎璇︽儏锛氱粍鍚堟敹鐩婏紙XIRR锛夊崱鐗囥€傚勾鍖栨敹鐩婄巼 / 褰撳墠甯傚€?/ 鎬绘姇鍏?/ 鎬绘敹鐩?+ 鍒锋柊銆?// 鍘?XIRR yield card銆倄irrData 鏉ヨ嚜 http.request锛堣 usePortfolioDetail.fetchXirr锛夈€?
import { usePortfolioDetailContext } from "@/composables/portfolio";

const { data } = usePortfolioDetailContext();
const { xirrData, xirrLoading } = data;
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="xirr-header">
        <span>缁勫悎鏀剁泭 (XIRR)</span>
        <el-button :loading="xirrLoading" text bg @click="data.fetchXirr()">
          <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 鍒锋柊
        </el-button>
      </div>
    </template>

    <el-row :gutter="16">
      <el-col :span="6">
        <div class="metric-label">骞村寲鏀剁泭鐜?/div>
        <RiseFallText :value="xirrData?.annualized_return ?? 0" suffix="%" size="md" />
      </el-col>
      <el-col :span="6">
        <div class="metric-label">褰撳墠甯傚€?/div>
        <MoneyDisplay :value="xirrData?.current_value ?? 0" size="md" :show-currency="true" />
      </el-col>
      <el-col :span="6">
        <div class="metric-label">鎬绘姇鍏?/div>
        <MoneyDisplay :value="xirrData?.total_invested ?? 0" size="md" :show-currency="true" />
      </el-col>
      <el-col :span="6">
        <div class="metric-label">鎬绘敹鐩?/div>
        <MoneyDisplay :value="xirrData?.total_return ?? 0" size="md" :show-currency="true" />
      </el-col>
    </el-row>
  </el-card>
</template>

<style scoped>
.xirr-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.metric-label {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-bottom: 4px;
}
</style>
```
