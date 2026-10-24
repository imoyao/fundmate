<script setup lang="ts">
// 交易流水·时间线视图（按交易日折叠，当日收支汇总）。
//
// 滚动懒加载收在组件内部：容器随视图挂载/卸载，用模板 `@scroll` 就自动跟着生命周期走，
// 不必像原来那样在父层手动 addEventListener + watch(viewMode) 解绑重绑。
import { computed, ref, watch } from "vue";
import type { TransactionRecord } from "@/api/transactions";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { txnTypeLabel } from "@/constants";
import {
  dayBalanceOf,
  groupByDate,
  recentDatesOf,
  signedAmount,
  statusLabel,
  statusTag,
  timelineDotClass,
  timelineIcon,
  typeTag
} from "./transactionListModel";

const props = defineProps<{
  transactions: TransactionRecord[];
  loading: boolean;
  loadingMore: boolean;
  hasMore: boolean;
}>();

const emit = defineEmits<{ edit: [row: any]; "load-more": [] }>();

const activeDates = ref<string[]>([]);
const scrollEl = ref<HTMLElement | null>(null);

const grouped = computed(() => groupByDate(props.transactions));
const dayBalance = computed(() => dayBalanceOf(grouped.value));

/** 默认展开最近 30 天（数据每次变化都重算，与原实现一致） */
watch(
  () => props.transactions,
  () => {
    activeDates.value = recentDatesOf(grouped.value);
  },
  { immediate: true, flush: "post" }
);

/** 触底 100px 内加载下一页 */
function onScroll() {
  const el = scrollEl.value;
  if (!el || props.loadingMore || !props.hasMore) return;
  if (el.scrollTop + el.clientHeight + 100 >= el.scrollHeight) {
    emit("load-more");
  }
}
</script>

<template>
  <el-card shadow="never" class="overflow-hidden">
    <div
      ref="scrollEl"
      v-loading="loading"
      class="timeline-container"
      @scroll="onScroll"
    >
      <!-- 空状态 -->
      <div
        v-if="transactions.length === 0 && !loading"
        class="text-center py-12 text-gray-400"
      >
        <IconifyIconOffline icon="ep:folder-opened" class="text-4xl mb-2" />
        <p>暂无交易记录</p>
      </div>

      <!-- 按日期分组的时间线 -->
      <el-collapse v-else v-model="activeDates" class="border-none">
        <el-collapse-item
          v-for="(group, date) in grouped"
          :key="date"
          :title="`${date}`"
          class="border-b border-gray-100"
        >
          <!-- 当日汇总 -->
          <div class="day-summary text-xs text-gray-500 mb-3 flex gap-3">
            <span>笔数：{{ group.length }} 笔</span>
            <span>收支：</span>
            <MoneyDisplay :value="dayBalance[date] || 0" size="sm" />
          </div>

          <!-- 时间线 -->
          <el-timeline class="ml-1">
            <el-timeline-item v-for="txn in group" :key="txn.id" class="mb-3">
              <!-- 自定义时间节点：Iconify 图标 -->
              <template #dot>
                <div
                  class="custom-timeline-dot"
                  :class="timelineDotClass(txn.type)"
                >
                  <IconifyIconOffline
                    :icon="timelineIcon(txn.type)"
                    width="12"
                  />
                </div>
              </template>

              <!-- 交易卡片 -->
              <el-card class="transaction-card" shadow="hover">
                <div class="card-header">
                  <div class="left">
                    <span
                      class="font-medium"
                      :class="{
                        'opacity-50 grayscale': txn.position_id === null
                      }"
                    >
                      {{ txn.position_name }}
                    </span>
                    <el-tag :type="typeTag(txn.type)" size="small" class="ml-2">
                      {{ txnTypeLabel(txn.type) }}
                    </el-tag>
                    <el-tag
                      :type="statusTag(txn.status)"
                      size="small"
                      effect="plain"
                      class="ml-1"
                    >
                      {{ statusLabel(txn.status) }}
                    </el-tag>
                  </div>
                  <div class="right flex items-center">
                    <MoneyDisplay :value="signedAmount(txn)" size="sm" />
                    <el-button
                      size="small"
                      text
                      type="primary"
                      class="ml-2"
                      @click="emit('edit', txn)"
                    >
                      编辑
                    </el-button>
                  </div>
                </div>

                <div
                  class="card-body text-xs text-gray-500 mt-2 flex flex-wrap gap-x-4 gap-y-1"
                >
                  <span>账户：{{ txn.account_name }}</span>
                  <span
                    >手续费：
                    <MoneyDisplay
                      :value="txn.fee"
                      :show-sign="false"
                      size="xs"
                    />
                  </span>
                </div>

                <div
                  v-if="txn.notes"
                  class="card-footer text-xs text-gray-400 mt-2"
                >
                  备注：{{ txn.notes }}
                </div>
              </el-card>
            </el-timeline-item>
          </el-timeline>
        </el-collapse-item>
      </el-collapse>

      <!-- 加载更多提示 -->
      <div v-if="hasMore" class="text-center py-4 text-gray-400 text-sm">
        <span>下滑加载更多数据</span>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.timeline-container {
  max-width: 800px;
  max-height: 75vh;
  padding: 16px 0;
  margin: 0 auto;
  overflow-y: auto;
}

/* 自定义时间线节点 */
:deep(.el-timeline-item__dot) {
  display: none;
}

.custom-timeline-dot {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  color: var(--text-inverse);
  border-radius: 50%;
  box-shadow: 0 2px 4px rgb(0 0 0 / 10%);
}

.dot-buy {
  background: #00b42a;
}

.dot-sell {
  background: #f53f3f;
}

.dot-dividend {
  background: #ff7d00;
}

.dot-deposit {
  background: #4080ff;
}

.dot-withdraw {
  background: #86909c;
}

.dot-default {
  background: #ccc;
}

/* 卡片样式 */
.transaction-card {
  border: 1px solid #f0f0f0;
  transition: all 0.2s ease;
}

.transaction-card:hover {
  border-color: #e5e6eb;
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.left {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

/* 折叠面板 */
:deep(.el-collapse-item__header) {
  font-weight: 500;
  color: #333;
  background: #fafafa;
  border-radius: 4px;
}

:deep(.el-collapse-item__content) {
  padding: 12px 0 0 !important;
  background: var(--bg-card);
}
</style>
