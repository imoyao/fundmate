<template>
  <div class="account-overview p-4 md:p-6 bg-[#f5f7fa] min-h-full">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h2 class="text-2xl font-bold text-gray-800">账户总览</h2>
      <p class="text-gray-500 mt-1 text-sm">查看所有持仓与盈亏明细</p>
    </div>

    <!-- 概览卡片 -->
    <el-row :gutter="16" class="mb-6">
      <el-col :xs="24" :sm="8" class="mb-4 sm:mb-0">
        <el-card shadow="never" class="stat-card">
          <div class="flex items-center gap-3">
            <div
              class="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center"
            >
              <IconifyIconOffline
                icon="ep:wallet"
                class="text-blue-500 text-lg"
              />
            </div>
            <div>
              <p class="text-gray-400 text-xs">总资产 (人民币)</p>
              <p class="text-xl font-bold text-gray-800">
                ¥{{ totalAssets.toLocaleString() }}
              </p>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8" class="mb-4 sm:mb-0">
        <el-card shadow="never" class="stat-card">
          <div class="flex items-center gap-3">
            <div
              class="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center"
            >
              <IconifyIconOffline
                icon="ep:collection"
                class="text-green-500 text-lg"
              />
            </div>
            <div>
              <p class="text-gray-400 text-xs">持仓数量</p>
              <p class="text-xl font-bold text-gray-800">
                {{ positions.length }} 笔
              </p>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="never" class="stat-card">
          <div class="flex items-center gap-3">
            <div
              class="w-10 h-10 rounded-lg bg-orange-100 flex items-center justify-center"
            >
              <IconifyIconOffline
                icon="ep:trend-charts"
                class="text-orange-500 text-lg"
              />
            </div>
            <div>
              <p class="text-gray-400 text-xs">总盈亏 (人民币)</p>
              <p
                :class="[
                  'text-xl font-bold',
                  totalPnl >= 0 ? 'text-red-500' : 'text-green-500'
                ]"
              >
                {{ totalPnl >= 0 ? "+" : "" }}¥{{ totalPnl.toLocaleString() }}
              </p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="mb-4">
      <el-row :gutter="12" align="middle">
        <el-col :xs="24" :sm="6" class="mb-2 sm:mb-0">
          <el-input
            v-model="filters.keyword"
            placeholder="搜索名称/代码"
            clearable
            :prefix-icon="Search"
          />
        </el-col>
        <el-col :xs="12" :sm="4">
          <el-select
            v-model="filters.market"
            placeholder="市场"
            clearable
            class="w-full"
          >
            <el-option label="全部市场" value="" />
            <el-option label="A股" value="CN_A" />
            <el-option label="港股" value="CN_HK" />
            <el-option label="美股" value="US" />
            <el-option label="虚拟货币" value="CRYPTO" />
          </el-select>
        </el-col>
        <el-col :xs="12" :sm="4">
          <el-select
            v-model="filters.type"
            placeholder="类型"
            clearable
            class="w-full"
          >
            <el-option label="全部类型" value="" />
            <el-option label="股票" value="stock" />
            <el-option label="基金" value="fund" />
            <el-option label="可转债" value="bond" />
            <el-option label="虚拟货币" value="crypto" />
            <el-option label="银行存款" value="saving" />
            <el-option label="现金" value="cash" />
          </el-select>
        </el-col>
        <el-col :xs="12" :sm="4">
          <el-select
            v-model="filters.account"
            placeholder="账户"
            clearable
            class="w-full"
          >
            <el-option label="全部账户" value="" />
            <el-option
              v-for="acc in accountOptions"
              :key="acc"
              :label="acc"
              :value="acc"
            />
          </el-select>
        </el-col>
        <el-col :xs="12" :sm="4">
          <el-button
            :icon="Refresh"
            circle
            :loading="loading"
            @click="fetchPositions"
          />
        </el-col>
      </el-row>
    </el-card>

    <!-- 持仓表格 -->
    <el-card shadow="never">
      <el-table
        v-loading="loading"
        :data="filteredPositions"
        stripe
        style="width: 100%"
        :default-sort="{ prop: 'updated_at', order: 'descending' }"
        size="default"
      >
        <el-table-column prop="name" label="名称" min-width="140">
          <template #default="{ row }">
            <div>
              <p class="font-medium text-gray-800">
                {{ row.name || row.symbol }}
              </p>
              <p class="text-xs text-gray-400">{{ row.symbol }}</p>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="90">
          <template #default="{ row }">
            <el-tag :type="typeTagType(row.type)" size="small" effect="plain">
              {{ typeLabel(row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="market" label="市场" width="70">
          <template #default="{ row }">
            {{ marketLabel(row.market) }}
          </template>
        </el-table-column>
        <el-table-column prop="account_name" label="账户" width="110" />
        <el-table-column prop="quantity" label="数量" width="100" align="right">
          <template #default="{ row }">
            {{ row.quantity.toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column
          prop="avg_price"
          label="成本价"
          width="100"
          align="right"
        >
          <template #default="{ row }">
            ¥{{ row.avg_price.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column label="当前价" width="120" align="right">
          <template #default="{ row }">
            <div class="flex items-center justify-end gap-1">
              <span
                :class="[
                  'cursor-pointer hover:underline',
                  priceChangeClass(row)
                ]"
                @click="startEditPrice(row)"
              >
                ¥{{ row.current_price.toFixed(2) }}
              </span>
              <IconifyIconOffline
                icon="ep:edit"
                class="text-gray-300 text-xs cursor-pointer hover:text-blue-400"
                @click="startEditPrice(row)"
              />
            </div>
          </template>
        </el-table-column>

        <!-- 价格编辑中 -->
        <el-table-column
          v-if="editingPriceId !== null"
          label="编辑价格"
          width="160"
          fixed="right"
        >
          <template #default="{ row }">
            <div
              v-if="row.id === editingPriceId"
              class="flex items-center gap-1"
            >
              <el-input-number
                v-model="editingPriceValue"
                :min="0"
                :precision="2"
                size="small"
                controls-position="right"
                class="w-24"
              />
              <el-button
                type="primary"
                size="small"
                @click="confirmEditPrice(row)"
              >
                确认
              </el-button>
              <el-button size="small" @click="cancelEditPrice">
                取消
              </el-button>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="市值" width="120" align="right">
          <template #default="{ row }">
            ¥{{ (row.quantity * row.current_price).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="盈亏" width="130" align="right">
          <template #default="{ row }">
            <div>
              <p
                :class="[
                  'font-medium',
                  row.current_price >= row.avg_price
                    ? 'text-red-500'
                    : 'text-green-500'
                ]"
              >
                {{ row.current_price >= row.avg_price ? "+" : "" }}¥{{
                  (
                    (row.current_price - row.avg_price) *
                    row.quantity
                  ).toLocaleString()
                }}
              </p>
              <p
                :class="[
                  'text-xs',
                  row.current_price >= row.avg_price
                    ? 'text-red-400'
                    : 'text-green-400'
                ]"
              >
                {{ row.current_price >= row.avg_price ? "+" : ""
                }}{{
                  ((row.current_price / row.avg_price - 1) * 100).toFixed(2)
                }}%
              </p>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="purchase_date" label="买入日期" width="110" />
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-popconfirm
              title="确定删除该持仓？"
              @confirm="handleDelete(row.id)"
            >
              <template #reference>
                <el-button type="danger" size="small" link> 删除 </el-button>
              </template>
            </el-popconfirm>
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
          :page-sizes="[5, 10, 20, 50, 100]"
          @current-change="onPageChange"
          @size-change="onSizeChange"
        />
      </div>

      <div
        v-if="!loading && filteredPositions.length === 0"
        class="text-center py-12 text-gray-400"
      >
        <IconifyIconOffline icon="ep:folder-opened" class="text-4xl mb-2" />
        <p>暂无持仓数据</p>
        <p class="text-sm mt-1">点击右下角"+"按钮记录第一笔交易</p>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { Search, Refresh } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getPositions, deletePosition, updatePosition } from "@/api/positions";
import { getSummary } from "@/api/summary";
import type { Position, SummaryData } from "@/api/types";
import { ElMessage } from "element-plus";

defineOptions({
  name: "AccountOverview"
});

// 数据状态
const positions = ref<Position[]>([]);
const summaryData = ref<SummaryData | null>(null);
const loading = ref(false);

// 筛选
const filters = ref({
  keyword: "",
  market: "",
  type: "",
  account: ""
});

// 汇率换算（简化版，实际应从配置获取）
const EXCHANGE_RATES: Record<string, number> = {
  CNY: 1,
  USD: 7.25,
  HKD: 0.92
};

const currentPage = ref(1);
const pageSize = ref(5);
const total = ref(0);

// 计算总资产 (人民币)
const totalAssets = computed(() => {
  return summaryData.value?.total_assets_cny ?? 0;
});

// 计算总盈亏 (人民币)
const totalPnl = computed(() => {
  return summaryData.value?.total_pnl_cny ?? 0;
});

// 账户选项（从数据中提取）
const accountOptions = computed(() => {
  const accounts = new Set<string>();
  positions.value.forEach(p => accounts.add(p.account_name));
  return Array.from(accounts).sort();
});

// 筛选后的持仓
const filteredPositions = computed(() => {
  let list = positions.value;

  if (filters.value.keyword) {
    const kw = filters.value.keyword.toLowerCase();
    list = list.filter(
      p =>
        p.name?.toLowerCase().includes(kw) ||
        p.symbol?.toLowerCase().includes(kw)
    );
  }
  if (filters.value.market) {
    list = list.filter(p => p.market === filters.value.market);
  }
  if (filters.value.type) {
    list = list.filter(p => p.type === filters.value.type);
  }
  if (filters.value.account) {
    list = list.filter(p => p.account_name === filters.value.account);
  }

  return list;
});

function onSizeChange(size: number) {
  pageSize.value = size;
  currentPage.value = 1; // 切换每页数量时重置到第一页
  fetchPositions();
}

// 类型标签样式
function typeTagType(type: string) {
  const map: Record<string, string> = {
    stock: "",
    fund: "warning",
    bond: "info",
    crypto: "danger",
    saving: "success",
    cash: "success",
    static: ""
  };
  return map[type] || "";
}

function typeLabel(type: string) {
  const map: Record<string, string> = {
    stock: "股票",
    fund: "基金",
    bond: "可转债",
    crypto: "虚拟币",
    saving: "存款",
    cash: "现金",
    static: "其他"
  };
  return map[type] || type;
}

function marketLabel(market: string) {
  const map: Record<string, string> = {
    CN_A: "A股",
    CN_HK: "港股",
    US: "美股",
    CRYPTO: "虚拟币"
  };
  return map[market] || market;
}

function priceChangeClass(row: Position) {
  if (row.current_price > row.avg_price) return "text-red-500";
  if (row.current_price < row.avg_price) return "text-green-500";
  return "text-gray-500";
}

// 获取数据
async function fetchPositions() {
  loading.value = true;
  try {
    const [posRes, sumRes] = await Promise.all([
      getPositions({ page: currentPage.value, per_page: pageSize.value }),
      getSummary()
    ]);

    // 分页接口返回 { data: [...], total: n, page: n, per_page: n, message: 'ok' }
    positions.value = posRes?.data ?? [];
    total.value = posRes?.total ?? 0;

    summaryData.value = sumRes?.data ?? sumRes ?? null;
  } catch (e: any) {
    ElMessage.error(e?.message || "加载数据失败");
  } finally {
    loading.value = false;
  }
}

function onPageChange(page: number) {
  currentPage.value = page;
  fetchPositions();
}

// 删除持仓
async function handleDelete(id: number) {
  try {
    await deletePosition(id);
    ElMessage.success("删除成功");
    positions.value = positions.value.filter(p => p.id !== id);
  } catch (e: any) {
    ElMessage.error(e?.message || "删除失败");
  }
}

// 价格编辑
const editingPriceId = ref<number | null>(null);
const editingPriceValue = ref(0);

function startEditPrice(row: Position) {
  editingPriceId.value = row.id;
  editingPriceValue.value = row.current_price;
}

async function confirmEditPrice(row: Position) {
  try {
    await updatePosition(row.id, { current_price: editingPriceValue.value });
    row.current_price = editingPriceValue.value;
    editingPriceId.value = null;
    ElMessage.success("价格已更新");
    // 重新拉取汇总数据
    const sumRes = await getSummary();
    summaryData.value = (sumRes as any)?.data ?? sumRes ?? null;
  } catch (e: any) {
    ElMessage.error(e?.message || "更新失败");
  }
}

function cancelEditPrice() {
  editingPriceId.value = null;
}

onMounted(() => {
  fetchPositions();
});
</script>

<style scoped>
.stat-card {
  border: 1px solid #f0f0f0;
  border-radius: 12px;
  transition: box-shadow 0.2s;
}

.stat-card:hover {
  box-shadow: 0 2px 12px rgb(0 0 0 / 6%);
}

.stat-card :deep(.el-card__body) {
  padding: 18px 20px;
}
</style>
