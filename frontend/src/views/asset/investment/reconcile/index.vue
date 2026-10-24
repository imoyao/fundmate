<template>
  <div class="reconcile-page">
    <!-- 页头：标题 + 数据日期胶囊 + 刷新（对齐 ledgers 页头模式） -->
    <ReconcileHeader
      :data-date="dataDate"
      :refreshing="refreshing"
      @refresh="handleRefresh"
    />

    <!-- 四态计数指标卡（MetricGrid 均分，待处理 featured 放大锚点） -->
    <ReconcileSummaryGrid :summary="summary" />

    <!-- 状态筛选：一级胶囊分段（design.md「Filter & Selection」；收敛到 SegmentedControl，
         见 docs/design/components.md，选中态软按钮） -->
    <div class="filter-bar">
      <SegmentedControl
        v-model="statusFilter"
        :options="STATUS_OPTIONS"
        aria-label="对账状态筛选"
      />
      <span class="filter-bar__count">共 {{ filteredItems.length }} 条</span>
    </div>

    <!-- 对账明细表：视觉基线走 src/style/el-table.css，页面不覆盖 -->
    <ReconcileTable
      v-model:page="page"
      v-model:page-size="pageSize"
      :items="pagedItems"
      :loading="loading"
      :total="filteredItems.length"
      :status-filter="statusFilter"
      :acting="acting"
      @cover="handleCover"
      @ignore="handleIgnore"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { ElMessage } from "element-plus";
import {
  getEaccountReconciliation,
  type ReconciliationItem,
  type ReconciliationData
} from "@/api/eaccount";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import ReconcileHeader from "./reconcileView/ReconcileHeader.vue";
import ReconcileSummaryGrid from "./reconcileView/ReconcileSummaryGrid.vue";
import ReconcileTable from "./reconcileView/ReconcileTable.vue";
import { useReconcileActions } from "./reconcileView/useReconcileActions";
import {
  STATUS_OPTIONS,
  errMsg,
  filterByStatus,
  slicePage,
  unwrap
} from "./reconcileView/reconcileModel";

defineOptions({ name: "InvestmentReconcile" });

const loading = ref(true);
const refreshing = ref(false);
const dataDate = ref("");
const items = ref<ReconciliationItem[]>([]);
const summary = ref<ReconciliationData["summary"] | null>(null);
const statusFilter = ref<string>("all");
/** 客户端分页：当前页码 + 每页条数（默认 50，大表格分页展示） */
const page = ref(1);
const pageSize = ref(50);

/** 一级状态筛选（客户端过滤：数据量小，切换即时，四态计数保持全量口径） */
const filteredItems = computed(() =>
  filterByStatus(items.value, statusFilter.value)
);

/** 客户端分页：在筛选结果上按当前页码切片（顶部「共 N 条」保持全量口径） */
const pagedItems = computed(() =>
  slicePage(filteredItems.value, page.value, pageSize.value)
);

/** 状态筛选切换时回到第一页，避免停留在旧筛选的高页码 */
watch(statusFilter, () => {
  page.value = 1;
});

async function fetchData() {
  loading.value = true;
  try {
    const res = await getEaccountReconciliation();
    const data = unwrap<ReconciliationData>(res);
    dataDate.value = data.data_date ?? "";
    items.value = Array.isArray(data.items) ? data.items : [];
    summary.value = data.summary ?? null;
    // 数据刷新后回到第一页（对账操作后列表重载，避免停留在过期页码）
    page.value = 1;
  } catch (e) {
    ElMessage.error(errMsg(e, "加载对账数据失败"));
  } finally {
    loading.value = false;
  }
}

async function handleRefresh() {
  refreshing.value = true;
  await fetchData();
  refreshing.value = false;
}

// ── 行内归因 / 忽略 ──
// 两条操作唯一的区别是 action 与措辞，差异全部收在 `useReconcileActions` +
// `ACTION_META` 里；页面只负责把行传下去。
const { actingRecordId, actingAction, runAttribution } =
  useReconcileActions(fetchData);

/** 传给表格的「哪个按钮在转圈」快照 */
const acting = computed(() => ({
  recordId: actingRecordId.value,
  action: actingAction.value
}));

function handleCover(row: ReconciliationItem) {
  void runAttribution(row, "cover");
}

function handleIgnore(row: ReconciliationItem) {
  void runAttribution(row, "ignore");
}

onMounted(fetchData);
</script>

<style scoped>
/* 页面根容器：字体继承全局 token + 全页数字等宽（design.md「数字等宽对齐落地规范」） */
.reconcile-page {
  font-family: var(--font-ui);
  font-variant-numeric: tabular-nums;
}

/* ===== 筛选栏 =====
   留在页面：它是「筛选 → 表格」这条链的一环，搬进表格会让筛选器与表格互为上下级，
   而顶部「共 N 条」与分页 total 同口径这件事就看不出来了。 */
.filter-bar {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-compact);
}

.filter-bar__count {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
