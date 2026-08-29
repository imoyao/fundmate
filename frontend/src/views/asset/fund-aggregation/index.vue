<template>
  <div
    class="fund-aggregation p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 标题 & 维度切换 -->
    <div class="mb-6 flex flex-wrap justify-between items-center gap-3">
      <div>
        <h2
          class="text-2xl font-bold"
          :style="{ color: 'var(--text-primary)' }"
        >
          基金
        </h2>
        <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary)' }">
          家族全部基金持仓
        </p>
      </div>
      <el-radio-group v-model="dimension" @change="onDimensionChange">
        <el-radio-button label="product">按基金</el-radio-button>
        <el-radio-button label="institution">按机构</el-radio-button>
        <el-radio-button label="app">按App</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 总市值卡 -->
    <div class="overview-card total-card mb-6">
      <p class="text-sm" :style="{ color: 'var(--text-tertiary)' }">
        总市值
      </p>
      <div class="mt-1">
        <MoneyDisplay
          :value="totalYuan"
          size="xl"
          :show-sign="false"
          :auto-color="false"
        />
      </div>
    </div>

    <!-- 加载 -->
    <div
      v-if="loading"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary)' }"
    >
      <p class="mt-2">加载中...</p>
    </div>

    <!-- 失败兜底 -->
    <div
      v-else-if="errorMsg"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary)' }"
    >
      <IconifyIconOffline icon="ep:warning" class="text-5xl mb-3 opacity-30" />
      <p class="text-lg">{{ errorMsg }}</p>
    </div>

    <!-- 空态 -->
    <div
      v-else-if="
        productGroups.length === 0 &&
        institutionGroups.length === 0 &&
        appGroups.length === 0
      "
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary)' }"
    >
      <IconifyIconOffline icon="ep:box" class="text-5xl mb-3 opacity-30" />
      <p class="text-lg">暂无基金持仓</p>
    </div>

    <!-- 表格区 -->
    <div v-else class="overview-card table-card">
      <!-- product 维度：按基金代码聚合 -->
      <el-table
        v-if="dimension === 'product'"
        :data="productGroups"
        :row-key="rowKey"
        default-expand-all
        style="width: 100%"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="px-4 py-2">
              <p
                class="text-xs mb-2"
                :style="{ color: 'var(--text-tertiary)' }"
              >
                来源账户（{{ row.sources.length }}）
              </p>
              <el-table :data="row.sources" size="small">
                <el-table-column label="账户" min-width="160">
                  <template #default="{ row: s }">
                    {{ s.ledger_name || "未命名账户" }}
                  </template>
                </el-table-column>
                <el-table-column label="市值" min-width="140" align="right">
                  <template #default="{ row: s }">
                    <MoneyDisplay
                      :value="mvYuan(s.market_value_cents)"
                      :show-sign="false"
                      :auto-color="false"
                      size="sm"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="份额(份)" min-width="140" align="right">
                  <template #default="{ row: s }">
                    {{ formatQuantity(toShares(s.quantity)) }}
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="基金代码" prop="symbol" min-width="120" />
        <el-table-column label="基金名称" prop="name" min-width="200" />
        <el-table-column label="市值" min-width="160" align="right">
          <template #default="{ row }">
            <MoneyDisplay
              :value="mvYuan(row.market_value_cents)"
              :show-sign="false"
              :auto-color="false"
            />
          </template>
        </el-table-column>
        <el-table-column label="份额(份)" min-width="160" align="right">
          <template #default="{ row }">
            {{ formatQuantity(toShares(row.quantity)) }}
          </template>
        </el-table-column>
      </el-table>

      <!-- institution 维度：按销售机构聚合 -->
      <el-table
        v-else-if="dimension === 'institution'"
        :data="institutionGroups"
        :row-key="rowKey"
        default-expand-all
        style="width: 100%"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="px-4 py-2">
              <el-table :data="row.items" size="small">
                <el-table-column
                  label="基金代码"
                  prop="symbol"
                  min-width="120"
                />
                <el-table-column label="基金名称" prop="name" min-width="200" />
                <el-table-column label="账户" min-width="160">
                  <template #default="{ row: it }">
                    {{ it.ledger_name || "未命名账户" }}
                  </template>
                </el-table-column>
                <el-table-column label="市值" min-width="140" align="right">
                  <template #default="{ row: it }">
                    <MoneyDisplay
                      :value="mvYuan(it.market_value_cents)"
                      :show-sign="false"
                      :auto-color="false"
                      size="sm"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="份额(份)" min-width="140" align="right">
                  <template #default="{ row: it }">
                    {{ formatQuantity(toShares(it.quantity)) }}
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="销售机构" min-width="200">
          <template #default="{ row }">
            {{ institutionLabel(row.key) }}
          </template>
        </el-table-column>
        <el-table-column label="基金数" min-width="100" align="right">
          <template #default="{ row }">{{ row.items.length }}</template>
        </el-table-column>
        <el-table-column label="市值" min-width="180" align="right">
          <template #default="{ row }">
            <MoneyDisplay
              :value="mvYuan(row.market_value_cents)"
              :show-sign="false"
              :auto-color="false"
            />
          </template>
        </el-table-column>
      </el-table>

      <!-- app 维度：按交易前端聚合 -->
      <el-table
        v-else
        :data="appGroups"
        :row-key="rowKey"
        default-expand-all
        style="width: 100%"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="px-4 py-2">
              <el-table :data="row.items" size="small">
                <el-table-column
                  label="基金代码"
                  prop="symbol"
                  min-width="120"
                />
                <el-table-column label="基金名称" prop="name" min-width="200" />
                <el-table-column label="账户" min-width="160">
                  <template #default="{ row: it }">
                    {{ it.ledger_name || "未命名账户" }}
                  </template>
                </el-table-column>
                <el-table-column label="市值" min-width="140" align="right">
                  <template #default="{ row: it }">
                    <MoneyDisplay
                      :value="mvYuan(it.market_value_cents)"
                      :show-sign="false"
                      :auto-color="false"
                      size="sm"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="份额(份)" min-width="140" align="right">
                  <template #default="{ row: it }">
                    {{ formatQuantity(toShares(it.quantity)) }}
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="交易前端" min-width="200">
          <template #default="{ row }">
            {{ appLabel(row.key) }}
          </template>
        </el-table-column>
        <el-table-column label="基金数" min-width="100" align="right">
          <template #default="{ row }">{{ row.items.length }}</template>
        </el-table-column>
        <el-table-column label="市值" min-width="180" align="right">
          <template #default="{ row }">
            <MoneyDisplay
              :value="mvYuan(row.market_value_cents)"
              :show-sign="false"
              :auto-color="false"
            />
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { formatQuantity } from "@/utils/format";
import {
  getFundAggregation,
  type FundAggregationDimension,
  type FundAggregationResult,
  type FundAggregationProductGroup,
  type FundAggregationInstitutionGroup,
  type FundAggregationAppGroup,
  type FundAggregationAppKey
} from "@/api/ledger";

// keep-alive 依赖：组件 name 须与路由 name 一致（见 src/router/modules/asset.ts）
defineOptions({ name: "fund-aggregation" });

const dimension = ref<FundAggregationDimension>("product");
const result = ref<FundAggregationResult | null>(null);
const loading = ref(false);
const errorMsg = ref("");

const totalYuan = computed(
  () => (result.value?.total_market_value_cents ?? 0) / 100
);

const productGroups = computed<FundAggregationProductGroup[]>(() =>
  dimension.value === "product"
    ? ((result.value?.groups as FundAggregationProductGroup[]) ?? [])
    : []
);
const institutionGroups = computed<FundAggregationInstitutionGroup[]>(() =>
  dimension.value === "institution"
    ? ((result.value?.groups as FundAggregationInstitutionGroup[]) ?? [])
    : []
);
const appGroups = computed<FundAggregationAppGroup[]>(() =>
  dimension.value === "app"
    ? ((result.value?.groups as FundAggregationAppGroup[]) ?? [])
    : []
);

const APP_LABELS: Record<FundAggregationAppKey, string> = {
  tonghuashun: "同花顺",
  eastmoney: "东方财富",
  self: "手动/其它",
  other: "其它"
};

function appLabel(key: FundAggregationAppKey | string): string {
  return APP_LABELS[key as FundAggregationAppKey] ?? String(key);
}

function institutionLabel(key: number | "unknown"): string {
  return key === "unknown" ? "未关联机构" : `销售机构 #${key}`;
}

/** 最小单位（份×10000）→ 可读份额（份）。后端聚合直接返回 Position.quantity 原始最小单位。 */
function toShares(minUnit: number): number {
  return (minUnit || 0) / 10000;
}

/** 分 → 元 */
function mvYuan(cents: number): number {
  return (cents || 0) / 100;
}

function rowKey(row: any): string {
  if (dimension.value === "product") {
    return (row as FundAggregationProductGroup).symbol;
  }
  return String((row as any).key);
}

async function load() {
  loading.value = true;
  errorMsg.value = "";
  try {
    const res = await getFundAggregation(dimension.value);
    result.value = res.data ?? null;
  } catch (e: any) {
    errorMsg.value = e?.message || "加载失败";
    ElMessage.error(errorMsg.value);
    result.value = null;
  } finally {
    loading.value = false;
  }
}

function onDimensionChange() {
  load();
}

onMounted(load);
</script>

<style scoped>
.fund-aggregation {
  font-family: var(--font-ui);
  /* 数字等宽对齐：消除金额/份额宽度抖动 */
  font-variant-numeric: tabular-nums;
}

/* 汇总/表格卡片复用 ledgers/index.vue 的 overview-card 视觉语言 */
.overview-card {
  padding: var(--space-standard);
  background: var(--bg-card);
  border: var(--card-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

.total-card {
  display: flex;
  flex-direction: column;
}

.table-card {
  padding: var(--space-standard);
}

@media (prefers-reduced-motion: reduce) {
  .overview-card {
    transition: none;
  }
}
</style>
