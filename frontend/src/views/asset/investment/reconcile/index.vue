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

    <!-- 对账明细：筛选 + 表格 + 分页收在面板组件里，与对账中心域 A 共用同一份实现
         （2026-10-28 反馈：两份手抄实现已经漂移过一次——工作台抄错系统份额字段、丢差异列与分页） -->
    <EaccountReconcilePanel
      :items="items"
      :loading="loading"
      :acting="acting"
      @cover="handleCover"
      @ignore="handleIgnore"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage } from "element-plus";
import {
  getEaccountReconciliation,
  type ReconciliationItem,
  type ReconciliationData
} from "@/api/eaccount";
import EaccountReconcilePanel from "@/components/EaccountReconcilePanel/index.vue";
import { useEaccountActions } from "@/components/EaccountReconcilePanel/useActions";
import { errMsg, unwrap } from "@/components/EaccountReconcilePanel/model";
import ReconcileHeader from "./reconcileView/ReconcileHeader.vue";
import ReconcileSummaryGrid from "./reconcileView/ReconcileSummaryGrid.vue";

defineOptions({ name: "InvestmentReconcile" });

const loading = ref(true);
const refreshing = ref(false);
const dataDate = ref("");
const items = ref<ReconciliationItem[]>([]);
const summary = ref<ReconciliationData["summary"] | null>(null);

async function fetchData() {
  loading.value = true;
  try {
    const res = await getEaccountReconciliation();
    const data = unwrap<ReconciliationData>(res);
    dataDate.value = data.data_date ?? "";
    items.value = Array.isArray(data.items) ? data.items : [];
    summary.value = data.summary ?? null;
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
// 两条操作唯一的区别是 action 与措辞，差异全部收在 `useEaccountActions` +
// `ACTION_META` 里；页面只负责把行传下去。
const { actingRecordId, actingAction, runAttribution } =
  useEaccountActions(fetchData);

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
</style>
