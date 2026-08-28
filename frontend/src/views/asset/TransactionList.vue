<template>
  <div class="transaction-list p-4 md:p-6 bg-[#f5f7fa] min-h-full">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h2 class="text-2xl font-bold text-gray-800">交易流水</h2>
      <p class="text-gray-500 mt-1 text-sm">所有交易操作的历史记录</p>
    </div>

    <!-- 视图切换 + 筛选栏 -->
    <el-card shadow="never" class="mb-4">
      <div class="flex items-center justify-between mb-4">
        <el-segmented v-model="viewMode" :options="viewOptions" size="small" />
        <div class="flex items-center gap-3">
          <span class="text-gray-400 text-sm">共 {{ totalCount }} 条记录</span>
          <el-button
            :icon="Download"
            plain
            size="small"
            :loading="exporting"
            @click="handleExport"
          >
            导出
          </el-button>
        </div>
      </div>
      <el-row :gutter="8">
        <el-col :xs="24" :sm="4" class="mb-2 sm:mb-0">
          <el-select
            v-model="filters.type"
            placeholder="操作类型"
            clearable
            class="w-full"
            @change="fetchData"
          >
            <el-option label="全部类型" value="" />
            <el-option label="买入" value="buy" />
            <el-option label="卖出" value="sell" />
            <el-option label="分红" value="dividend" />
            <el-option label="存入" value="deposit" />
            <el-option label="取出" value="withdraw" />
          </el-select>
        </el-col>
        <el-col :xs="24" :sm="4" class="mb-2 sm:mb-0">
          <el-select
            v-model="filters.assetType"
            placeholder="资产类型"
            clearable
            class="w-full"
            @change="fetchData"
          >
            <el-option label="全部资产" value="" />
            <el-option label="股票" value="stock" />
            <el-option label="基金" value="fund" />
            <el-option label="可转债" value="bond" />
            <el-option label="虚拟货币" value="crypto" />
            <el-option label="银行存款" value="saving" />
            <el-option label="现金" value="cash" />
          </el-select>
        </el-col>
        <el-col :xs="24" :sm="4" class="mb-2 sm:mb-0">
          <el-select
            v-model="filters.status"
            placeholder="交易状态"
            clearable
            class="w-full"
            @change="fetchData"
          >
            <el-option label="全部状态" value="" />
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
            <el-option label="已撤单" value="cancelled" />
            <el-option label="可撤单" value="pending" />
          </el-select>
        </el-col>
        <el-col :xs="24" :sm="5" class="mb-2 sm:mb-0">
          <el-select
            v-model="filters.timeRange"
            placeholder="交易时间"
            class="w-full"
            @change="fetchData"
          >
            <el-option label="全部时间" value="" />
            <el-option label="近一个月" value="1m" />
            <el-option label="近三个月" value="3m" />
            <el-option label="近半年" value="6m" />
            <el-option label="近一年" value="1y" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-col>
        <el-col
          v-if="filters.timeRange === 'custom'"
          :xs="12"
          :sm="3"
          class="mb-2 sm:mb-0"
        >
          <el-date-picker
            v-model="filters.customDate"
            type="daterange"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            class="w-full"
            @change="fetchData"
          />
        </el-col>
        <el-col :xs="12" :sm="2">
          <el-button
            :icon="Refresh"
            circle
            :loading="loading"
            @click="resetAndFetch"
          />
        </el-col>
      </el-row>
    </el-card>

    <!-- 表格视图 -->
    <el-card v-if="viewMode === 'table'" shadow="never">
      <el-table
        v-loading="loading"
        :data="transactions"
        stripe
        size="default"
        :default-sort="{ prop: 'created_at', order: 'descending' }"
      >
        <el-table-column prop="position_name" label="资产名称" min-width="150">
          <template #default="{ row }">
            <div :class="{ 'opacity-50 grayscale': row.position_id === null }">
              <p class="font-medium text-gray-800">{{ row.position_name }}</p>
              <p v-if="row.position_id === null" class="text-xs text-gray-400">
                已删除
              </p>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="操作" width="90">
          <template #default="{ row }">
            <el-tag :type="typeTag(row.type)" size="small" effect="plain">
              {{ txnTypeLabel(row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" width="120" align="right">
          <template #default="{ row }">
            <MoneyDisplay :value="row.amount" :show-sign="false" size="sm" />
          </template>
        </el-table-column>
        <el-table-column prop="fee" label="手续费" width="90" align="right">
          <template #default="{ row }">
            <MoneyDisplay :value="row.fee" :show-sign="false" size="sm" />
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small" effect="plain">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trade_date" label="交易日期" width="110" />
        <el-table-column prop="account_name" label="账户/渠道" width="110" />
        <el-table-column prop="notes" label="备注" min-width="120">
          <template #default="{ row }">
            <span class="text-gray-400">{{ row.notes || "-" }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="64" align="center">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openEdit(row)">
              编辑
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div v-if="total > 0" class="flex justify-end mt-4">
        <el-pagination
          background
          layout="prev, pager, next, sizes, total"
          :total="total"
          :current-page="currentPage"
          :page-size="pageSize"
          :page-sizes="[5, 10, 20, 50]"
          @current-change="onPageChange"
          @size-change="onSizeChange"
        />
      </div>

      <div
        v-if="!loading && transactions.length === 0"
        class="text-center py-12 text-gray-400"
      >
        <IconifyIconOffline icon="ep:folder-opened" class="text-4xl mb-2" />
        <p>暂无交易记录</p>
        <p class="text-sm mt-1">记账后交易流水会出现在这里</p>
      </div>
    </el-card>

    <!-- 高级时间线视图 -->
    <el-card
      v-if="viewMode === 'timeline'"
      shadow="never"
      class="overflow-hidden"
    >
      <div
        ref="timelineScrollRef"
        v-loading="loading"
        class="timeline-container"
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
            v-for="(group, date) in groupedTransactions"
            :key="date"
            :title="`${date}`"
            class="border-b border-gray-100"
          >
            <!-- 当日汇总 -->
            <div class="day-summary text-xs text-gray-500 mb-3 flex gap-3">
              <span>笔数：{{ group.length }} 笔</span>
              <span>收支：</span>
              <MoneyDisplay :value="groupDayBalance[date] || 0" size="sm" />
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
                      <el-tag
                        :type="typeTag(txn.type)"
                        size="small"
                        class="ml-2"
                      >
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
                        @click="openEdit(txn)"
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
        <div
          v-if="hasMore && viewMode === 'timeline'"
          class="text-center py-4 text-gray-400 text-sm"
        >
          <span>下滑加载更多数据</span>
        </div>
      </div>
    </el-card>

    <!-- 行内编辑弹窗 -->
    <TransactionEditDialog
      v-model="editDialogVisible"
      :transaction="editingTxn"
      :asset-type="editingTxn?.asset_type"
      :symbol="editingTxn?.symbol"
      @saved="handleSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, onUnmounted } from "vue";
import { Refresh, Download } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getTransactions, exportTransactions } from "@/api/transactions";
import type { TransactionRecord } from "@/api/transactions";
import { ElMessage } from "element-plus";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import TransactionEditDialog from "./ledgers/components/TransactionEditDialog.vue";
import { txnTypeLabel } from "@/constants";

defineOptions({ name: "TransactionList" });

const viewMode = ref("table");
const viewOptions = [
  { label: "表格", value: "table" },
  { label: "时间线", value: "timeline" }
];

// 时间线配置
const activeDates = ref<string[]>([]);
const timelineScrollRef = ref(null);
const loadingMore = ref(false);
const hasMore = ref(true);

const transactions = ref<TransactionRecord[]>([]);
const loading = ref(false);
const totalCount = computed(() => total.value);

const filters = ref({
  type: "",
  assetType: "",
  status: "",
  timeRange: "",
  customDate: null as [Date, Date] | null
});

const currentPage = ref(1);
const pageSize = ref(10);
const total = ref(0);

// 按日期分组
const groupedTransactions = computed(() => {
  const group: Record<string, TransactionRecord[]> = {};
  transactions.value.forEach(item => {
    const date = item.trade_date;
    if (!group[date]) group[date] = [];
    group[date].push(item);
  });
  return group;
});

// 每日收支汇总
const groupDayBalance = computed(() => {
  const balance: Record<string, number> = {};
  Object.entries(groupedTransactions.value).forEach(([date, list]) => {
    let sum = 0;
    list.forEach(txn => {
      const val = Number(txn.amount);
      if (
        txn.type === "sell" ||
        txn.type === "dividend" ||
        txn.type === "deposit"
      )
        sum += val;
      else sum -= val;
    });
    balance[date] = sum;
  });
  return balance;
});

// 判断日期是否在30天内
const isDateInLast30Days = (dateStr: string) => {
  const target = new Date(dateStr);
  const now = new Date();
  const past = new Date(now.setDate(now.getDate() - 30));
  return target >= past;
};

// 默认展开最近30天
const setDefaultExpireDates = () => {
  const allDates = Object.keys(groupedTransactions.value);
  const recentDates = allDates.filter(date => isDateInLast30Days(date));
  activeDates.value = recentDates;
};

// 数据请求
const fetchData = async (isLoadMore = false) => {
  if (loading.value || loadingMore.value) return;
  isLoadMore ? (loadingMore.value = true) : (loading.value = true);

  try {
    const params: any = { page: currentPage.value, per_page: pageSize.value };
    if (filters.value.type) params.type = filters.value.type;
    if (filters.value.assetType) params.asset_type = filters.value.assetType;
    if (filters.value.status) params.status = filters.value.status;
    if (filters.value.timeRange) params.time_range = filters.value.timeRange;
    if (filters.value.customDate) {
      const [start, end] = filters.value.customDate;
      params.start_date = start.toISOString().slice(0, 10);
      params.end_date = end.toISOString().slice(0, 10);
    }

    const res = await getTransactions(params);
    const newData = res?.data ?? [];
    transactions.value = isLoadMore
      ? [...transactions.value, ...newData]
      : newData;
    total.value = res?.total ?? 0;
    hasMore.value = transactions.value.length < total.value;
    nextTick(() => setDefaultExpireDates());
  } catch (e: any) {
    ElMessage.error(e?.message || "加载流水失败");
  } finally {
    loading.value = false;
    loadingMore.value = false;
  }
};

// 重置刷新
const resetAndFetch = () => {
  currentPage.value = 1;
  hasMore.value = true;
  fetchData();
};

// 行内编辑
const editDialogVisible = ref(false);
const editingTxn = ref<any>(null);
function openEdit(row: any) {
  editingTxn.value = row;
  editDialogVisible.value = true;
}
function handleSaved(data: any) {
  const idx = transactions.value.findIndex(t => t.id === data?.id);
  if (idx !== -1) {
    Object.assign(transactions.value[idx], {
      quantity: data.quantity,
      price: data.price,
      amount: data.amount,
      fee: data.fee,
      trade_date: data.trade_date,
      confirm_date: data.confirm_date,
      notes: data.notes,
      import_hash: data.import_hash
    });
  }
}

// 导出全部交易流水
const exporting = ref(false);
const handleExport = async () => {
  if (exporting.value) return;
  exporting.value = true;
  try {
    await exportTransactions();
  } catch (e: any) {
    ElMessage.error(e?.message || "导出失败");
  } finally {
    exporting.value = false;
  }
};

// 分页
const onPageChange = (page: number) => {
  currentPage.value = page;
  fetchData();
};
const onSizeChange = (size: number) => {
  pageSize.value = size;
  currentPage.value = 1;
  fetchData();
};

// ==============================================
// 原生JS滚动懒加载（零依赖，无报错）
// ==============================================
const handleTimelineScroll = () => {
  const el = timelineScrollRef.value;
  if (!el || loadingMore.value || !hasMore.value) return;
  if (el.scrollTop + el.clientHeight + 100 >= el.scrollHeight) {
    currentPage.value++;
    fetchData(true);
  }
};

let scrollListener = null;
const bindScroll = () => {
  if (
    viewMode.value === "timeline" &&
    timelineScrollRef.value &&
    !scrollListener
  ) {
    scrollListener = handleTimelineScroll;
    timelineScrollRef.value.addEventListener("scroll", scrollListener);
  }
};
const unbindScroll = () => {
  if (timelineScrollRef.value && scrollListener) {
    timelineScrollRef.value.removeEventListener("scroll", scrollListener);
    scrollListener = null;
  }
};

watch(viewMode, val => {
  unbindScroll();
  nextTick(bindScroll);
});

// ==============================================
// 图标 & 样式工具函数
// ==============================================
const timelineIcon = (type: string) => {
  const map = {
    buy: "ep:arrow-down",
    sell: "ep:arrow-up",
    dividend: "ep:present",
    deposit: "ep:wallet",
    withdraw: "ep:money"
  };
  return map[type] || "ep:arrow-down";
};
const timelineDotClass = (type: string) => {
  const map = {
    buy: "dot-buy",
    sell: "dot-sell",
    dividend: "dot-dividend",
    deposit: "dot-deposit",
    withdraw: "dot-withdraw"
  };
  return map[type] || "dot-default";
};
const signedAmount = (txn: TransactionRecord) => {
  return txn.type === "sell" ||
    txn.type === "dividend" ||
    txn.type === "deposit"
    ? Number(txn.amount) || 0
    : -(Number(txn.amount) || 0);
};

// 原有工具函数
function typeTag(
  type: string
): "primary" | "success" | "warning" | "info" | "danger" {
  const map: Record<
    string,
    "primary" | "success" | "warning" | "info" | "danger"
  > = {
    buy: "success",
    sell: "danger",
    dividend: "warning",
    deposit: "primary",
    withdraw: "info"
  };
  return map[type] || "primary";
}
function statusTag(
  status: string
): "primary" | "success" | "warning" | "info" | "danger" {
  const map: Record<
    string,
    "primary" | "success" | "warning" | "info" | "danger"
  > = {
    success: "success",
    failed: "danger",
    cancelled: "info",
    pending: "warning"
  };
  return map[status] || "primary";
}
function statusLabel(status: string): string {
  const map = {
    success: "成功",
    failed: "失败",
    cancelled: "已撤单",
    pending: "可撤单"
  };
  return map[status] || status;
}

// 生命周期
onMounted(() => {
  fetchData();
  nextTick(bindScroll);
});
onUnmounted(unbindScroll);
</script>

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
  color: #fff;
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
  background: #fff;
}
</style>
