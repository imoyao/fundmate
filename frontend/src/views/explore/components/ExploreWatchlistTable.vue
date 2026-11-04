<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessageBox } from "element-plus";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import ExploreWatchlistSummaryBar from "./ExploreWatchlistSummaryBar.vue";
import ExploreWatchlistCards from "./ExploreWatchlistCards.vue";
import ExploreAnalysisDropdown from "./ExploreAnalysisDropdown.vue";
import { getTypeLabel } from "@/constants/assetType";
import { pricePrecision } from "@/utils/pricePrecision";

/**
 * 探市·观察列表（#984 explore/index.vue 拆分）。
 * 纯展示组件：汇总条 + 表格；数据经 props 注入，
 * 删除/深度分析跳转/刷新/档位切换经事件上抛由父页面编排。
 * 移动端（≤768px）表格降级为卡片列表（#821 P2-7，#808 §7.2）。
 *
 * #980 批 B5 二次拆分（纯搬运，零视觉/行为变更）：
 *   · 汇总条 → ExploreWatchlistSummaryBar.vue
 *   · 移动端卡片 → ExploreWatchlistCards.vue
 *   · 「分析 ▼」下拉（桌面与移动各一份）→ ExploreAnalysisDropdown.vue
 *   · 站点清单 → watchlistTools.ts 纯函数
 * 本文件只留桌面表格与断点判定。
 */
defineProps<{
  rows: any[];
  loading: boolean;
  totalCount: number;
  /** true = 未填成本份额的纯观察模式（隐藏盈亏列） */
  isPureObservationMode: boolean;
  summary?: {
    totalMarketValue: number;
    totalPnl: number;
  } | null;
  statusClass: string;
  statusText: string;
  refreshInterval: number;
  lastUpdateTime: string;
}>();

interface ExploreRow {
  symbol: string;
  type: string;
  name: string;
  id?: string | number;
}
const emit = defineEmits<{
  remove: [id: string];
  jump: [row: ExploreRow, command: string];
  refresh: [];
  "interval-change": [value: number];
  favorite: [row: ExploreRow];
}>();

function handleRemoveConfirm(id: string) {
  ElMessageBox.confirm("确定从观察列表中移除该资产吗？", "提示", {
    confirmButtonText: "确定",
    cancelButtonText: "取消",
    type: "warning"
  })
    .then(() => emit("remove", id))
    .catch(() => {});
}

// ================================================================
// 移动端断点（#821 P2-7）：≤768px 表格降级为卡片列表
// ================================================================
const MOBILE_MQ = "(max-width: 768px)";
const isMobile = ref(
  typeof window !== "undefined" && window.matchMedia(MOBILE_MQ).matches
);
let mq: MediaQueryList | null = null;

onMounted(() => {
  mq = window.matchMedia(MOBILE_MQ);
  isMobile.value = mq.matches;
  mq.addEventListener("change", onMqChange);
});

onBeforeUnmount(() => {
  mq?.removeEventListener("change", onMqChange);
});

function onMqChange(e: MediaQueryListEvent) {
  isMobile.value = e.matches;
}
</script>

<template>
  <section class="watchlist-section">
    <ExploreWatchlistSummaryBar
      :total-count="totalCount"
      :is-pure-observation-mode="isPureObservationMode"
      :summary="summary"
      :status-class="statusClass"
      :status-text="statusText"
      :refresh-interval="refreshInterval"
      :last-update-time="lastUpdateTime"
      @refresh="emit('refresh')"
      @interval-change="emit('interval-change', $event)"
    />

    <!-- 桌面端表格（视觉基线统一在 src/style/el-table.css 维护，勿在本页 :deep 覆盖） -->
    <el-table
      v-if="!isMobile"
      v-loading="loading"
      :data="rows"
      border
      style="width: 100%"
      empty-text="暂无观察资产，添加你关注的标的开始研究"
    >
      <el-table-column label="产品" min-width="180">
        <template #default="{ row }">
          <ProductDisplay
            :name="row.name"
            :symbol="row.symbol"
            :type-label="getTypeLabel(row.type)"
          />
        </template>
      </el-table-column>

      <el-table-column label="最新价" width="120" align="right">
        <template #default="{ row }"
          ><MoneyDisplay
            :value="row.price"
            :show-sign="false"
            :precision="pricePrecision(row.type)"
        /></template>
      </el-table-column>

      <el-table-column label="涨跌幅" width="110" align="right">
        <template #default="{ row }"
          ><RiseFallText :value="row.changePct"
        /></template>
      </el-table-column>

      <el-table-column
        v-if="!isPureObservationMode"
        label="当日盈亏"
        width="130"
        align="right"
      >
        <template #default="{ row }"
          ><MoneyDisplay :value="row.pnl ?? 0" :show-sign="true"
        /></template>
      </el-table-column>

      <el-table-column
        v-if="!isPureObservationMode"
        label="持仓收益"
        width="130"
        align="right"
      >
        <template #default="{ row }"
          ><MoneyDisplay :value="row.positionPnl ?? 0" :show-sign="true"
        /></template>
      </el-table-column>

      <el-table-column label="深度分析" width="120" align="center">
        <template #default="{ row }">
          <ExploreAnalysisDropdown
            :type="row.type"
            @command="
              (command: string) => emit('jump', row as ExploreRow, command)
            "
          />
        </template>
      </el-table-column>

      <el-table-column label="操作" width="140" align="center">
        <template #default="{ row }">
          <el-button
            link
            size="small"
            type="primary"
            @click="emit('favorite', row as ExploreRow)"
            >收藏</el-button
          >
          <el-button
            link
            size="small"
            style="color: var(--text-tertiary-ink)"
            @click="handleRemoveConfirm(row.id)"
            >删除</el-button
          >
        </template>
      </el-table-column>
    </el-table>

    <!-- 移动端卡片降级（#821 P2-7，#808 §7.2），细节见 ExploreWatchlistCards -->
    <ExploreWatchlistCards
      v-else
      :rows="rows"
      :loading="loading"
      :is-pure-observation-mode="isPureObservationMode"
      @jump="(row, command) => emit('jump', row, command)"
      @favorite="row => emit('favorite', row)"
      @remove="handleRemoveConfirm"
    />
  </section>
</template>

<style lang="scss" scoped>
/* ============================================================
   观察列表样式（自 index.vue 随组件迁移，#984）
   汇总条与移动端卡片的样式随各自组件走，这里只留区块外壳。
   ============================================================ */
.watchlist-section {
  max-width: var(--layout-content-width);
  padding: 0 24px 24px;
  margin: 0 auto;
}
</style>
