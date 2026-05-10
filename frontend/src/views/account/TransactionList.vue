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
        <span class="text-gray-400 text-sm">共 {{ totalCount }} 条记录</span>
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
            @click="fetchData"
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
              {{ opLabel(row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" width="120" align="right">
          <template #default="{ row }">
            ¥{{ Number(row.amount).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column prop="fee" label="手续费" width="90" align="right">
          <template #default="{ row }">
            ¥{{ Number(row.fee).toFixed(2) }}
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

    <!-- 时间线视图 -->
    <el-card v-if="viewMode === 'timeline'" shadow="never">
      <div v-loading="loading" class="timeline-container">
        <el-timeline v-if="transactions.length">
          <el-timeline-item
            v-for="txn in transactions"
            :key="txn.id"
            :timestamp="txn.trade_date"
            :type="timelineType(txn.type)"
            :hollow="txn.status !== 'success'"
          >
            <div class="flex items-start justify-between">
              <div>
                <span :class="{ 'opacity-50': txn.position_id === null }">
                  {{ txn.position_name }}
                </span>
                <span class="text-xs text-gray-400 ml-2"
                  >({{ txn.account_name }})</span
                >
              </div>
              <div class="text-right">
                <span :class="amountClass(txn)">
                  {{ txn.type === "buy" || txn.type === "deposit" ? "+" : "-" }}
                  ¥{{ Number(txn.amount).toLocaleString() }}
                </span>
              </div>
            </div>
            <p v-if="txn.notes" class="text-gray-400 text-xs mt-1">
              {{ txn.notes }}
            </p>
          </el-timeline-item>
        </el-timeline>
        <div v-else class="text-center py-12 text-gray-400">
          <IconifyIconOffline icon="ep:folder-opened" class="text-4xl mb-2" />
          <p>暂无交易记录</p>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getTransactions } from "@/api/transactions";
import type { TransactionRecord } from "@/api/transactions";
import { ElMessage } from "element-plus";

defineOptions({ name: "TransactionList" });

const viewMode = ref("table");
const viewOptions = [
  { label: "📋 表格", value: "table" },
  { label: "⏳ 时间线", value: "timeline" }
];

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
const pageSize = ref(10); // 默认每页10条
const total = ref(0);

async function fetchData() {
  loading.value = true;
  try {
    const params: any = {
      page: currentPage.value,
      per_page: pageSize.value
    };
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
    // res 已经是后端返回的完整对象 { data: [...], total: 9, page: 1, ... }
    transactions.value = res?.data ?? [];
    total.value = res?.total ?? 0;
  } catch (e: any) {
    ElMessage.error(e?.message || "加载流水失败");
  } finally {
    loading.value = false;
  }
}
const fetchTransactions = fetchData;

function onPageChange(page: number) {
  currentPage.value = page;
  fetchData();
}

function onSizeChange(size: number) {
  pageSize.value = size;
  currentPage.value = 1;
  fetchData();
}

// ── 辅助函数 ──
function typeTag(type: string): string {
  const map: Record<string, string> = {
    buy: "success",
    sell: "danger",
    dividend: "warning",
    deposit: "",
    withdraw: "info"
  };
  return map[type] || "";
}
function opLabel(type: string): string {
  const map: Record<string, string> = {
    buy: "买入",
    sell: "卖出",
    dividend: "分红",
    deposit: "存入",
    withdraw: "取出"
  };
  return map[type] || type;
}
function statusTag(status: string): string {
  const map: Record<string, string> = {
    success: "success",
    failed: "danger",
    cancelled: "info",
    pending: "warning"
  };
  return map[status] || "";
}
function statusLabel(status: string): string {
  const map: Record<string, string> = {
    success: "成功",
    failed: "失败",
    cancelled: "已撤单",
    pending: "可撤单"
  };
  return map[status] || status;
}
function timelineType(
  type: string
): "primary" | "success" | "warning" | "danger" | "info" {
  const map: Record<string, string> = {
    buy: "success",
    sell: "danger",
    dividend: "warning",
    deposit: "",
    withdraw: ""
  };
  return (map[type] || "primary") as any;
}
function amountClass(txn: TransactionRecord): string {
  if (txn.type === "buy" || txn.type === "deposit")
    return "text-green-500 font-medium";
  return "text-red-500 font-medium";
}

onMounted(() => fetchData());
</script>

<style scoped>
.timeline-container {
  max-width: 700px;
  padding: 20px 0;
  margin: 0 auto;
}
</style>
