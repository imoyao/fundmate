<template>
  <el-drawer
    v-model="drawerVisible"
    size="680px"
    direction="rtl"
    destroy-on-close
    title="持仓明细"
    @closed="resetState"
  >
    <!-- 1. 顶部：持仓名称与信息 -->
    <div class="position-header mb-5 flex items-center justify-between">
      <div>
        <h3 class="text-xl font-bold" :style="{ color: 'var(--text-primary)' }">
          {{ positionData?.name || "--" }}
        </h3>
        <div class="flex items-center gap-2 mt-1">
          <span class="text-sm" :style="{ color: 'var(--text-tertiary)' }"
            ># {{ positionData?.symbol || "--" }}</span
          >
          <el-tag size="small" type="info" round>{{
            positionData?.type_label || "--"
          }}</el-tag>
        </div>
      </div>
    </div>

    <!-- 2. 核心摘要卡片 -->
    <div class="grid grid-cols-3 gap-3 mb-5">
      <!-- 持有份额 / 持有数量 -->
      <div
        class="p-3 rounded-lg border"
        :style="{ borderColor: 'var(--border-default)' }"
      >
        <div class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
          {{ isFund ? "持有份额" : "持有数量" }}
        </div>
        <div
          class="text-lg font-bold mt-1"
          :style="{ color: 'var(--text-primary)' }"
        >
          {{ Number(positionData?.quantity ?? 0).toLocaleString() }}
          <span
            class="text-sm font-normal"
            :style="{ color: 'var(--text-tertiary)' }"
          >
            {{ isFund ? "份" : "股/张" }}
          </span>
        </div>
      </div>

      <!-- 成本净值 / 持仓成本 -->
      <div
        class="p-3 rounded-lg border"
        :style="{ borderColor: 'var(--border-default)' }"
      >
        <div class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
          {{ isFund ? "成本净值" : "持仓成本" }}
        </div>
        <div
          class="text-lg font-bold mt-1"
          :style="{ color: 'var(--text-primary)' }"
        >
          <MoneyDisplay
            :value="positionData?.avg_price || 0"
            :show-sign="false"
            :auto-color="false"
            size="lg"
          />
          <span
            class="text-sm font-normal"
            :style="{ color: 'var(--text-tertiary)' }"
          >
            {{ isFund ? "元/份" : "元" }}
          </span>
        </div>
      </div>

      <!-- 最新净值 / 现价 -->
      <div
        class="p-3 rounded-lg border"
        :style="{ borderColor: 'var(--border-default)' }"
      >
        <div class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
          {{ isFund ? "最新净值" : "现价" }}
        </div>
        <div
          class="text-lg font-bold mt-1"
          :style="{ color: 'var(--text-primary)' }"
        >
          <MoneyDisplay
            :value="positionData?.current_price || 0"
            :show-sign="false"
            :auto-color="false"
            size="lg"
          />
          <span
            class="text-sm font-normal"
            :style="{ color: 'var(--text-tertiary)' }"
          >
            {{ isFund ? "元/份" : "元" }}
          </span>
        </div>
      </div>

      <!-- 市值 -->
      <div
        class="p-3 rounded-lg border"
        :style="{ borderColor: 'var(--border-default)' }"
      >
        <div class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
          市值
        </div>
        <div
          class="text-lg font-bold mt-1"
          :style="{ color: 'var(--text-primary)' }"
        >
          <MoneyDisplay
            :value="positionData?.market_value || 0"
            :show-sign="false"
            :auto-color="false"
            size="lg"
          />
        </div>
      </div>

      <!-- 持仓盈亏 -->
      <div
        class="p-3 rounded-lg border"
        :style="{ borderColor: 'var(--border-default)' }"
      >
        <div class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
          持仓盈亏
        </div>
        <div class="text-lg font-bold mt-1">
          <MoneyDisplay :value="positionData?.pnl || 0" size="lg" />
        </div>
      </div>

      <!-- 盈亏率 -->
      <div
        class="p-3 rounded-lg border"
        :style="{ borderColor: 'var(--border-default)' }"
      >
        <div class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
          盈亏率
        </div>
        <div
          class="text-lg font-bold mt-1"
          :style="{
            color:
              (positionData?.pnl_rate ?? 0) >= 0
                ? 'var(--color-danger)'
                : 'var(--color-success)',
          }"
        >
          {{
            positionData?.pnl_rate != null
              ? (positionData.pnl_rate >= 0 ? "+" : "") +
                positionData.pnl_rate.toFixed(2) +
                "%"
              : "--"
          }}
        </div>
      </div>
    </div>

    <!-- 3. 走势图区 -->
    <div
      class="mb-5 p-4 bg-gray-50 rounded-lg border border-dashed flex items-center justify-center"
      :style="{ borderColor: 'var(--border-default)' }"
    >
      <div
        class="text-xs text-center leading-relaxed"
        :style="{ color: 'var(--text-tertiary)' }"
      >
        <IconifyIconOffline
          icon="ep:trend-charts"
          class="text-lg block mx-auto mb-1"
        />
        历史价格与成本曲线<br />
        <span class="text-[10px]">(数据依赖 P1-20 定时任务同步)</span>
      </div>
    </div>

    <!-- 4. 交易明细列表 -->
    <div class="flex-1 overflow-y-auto">
      <div class="flex justify-between items-center mb-3">
        <span
          class="text-sm font-medium"
          :style="{ color: 'var(--text-secondary)' }"
          >交易记录</span
        >
        <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }"
          >共 {{ transactionsTotal }} 条</span
        >
      </div>

      <!-- 加载状态 -->
      <div
        v-if="loadingTransactions"
        class="text-center py-8"
        :style="{ color: 'var(--text-tertiary)' }"
      >
        <el-icon class="is-loading" :size="20"><Loading /></el-icon>
        <p class="mt-2 text-xs">加载交易记录中...</p>
      </div>

      <template v-else>
        <!-- 🔥 修复1：将固定 width 改为 min-width，避免在 520px 抽屉中强制滚动 -->
        <el-table
          :data="transactionsList"
          stripe
          size="small"
          :header-cell-style="{ color: 'var(--text-tertiary)' }"
        >
          <el-table-column label="日期" min-width="100" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.trade_date || row.confirm_date || "--" }}
            </template>
          </el-table-column>
          <el-table-column label="类型" min-width="40">
            <template #default="{ row }">
              <span
                :class="
                  row.txn_type === 'buy' || row.txn_type === 'deposit'
                    ? 'text-[var(--color-danger)]'
                    : 'text-[var(--color-success)]'
                "
              >
                {{ txnTypeLabel(row.txn_type) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column
            :label="isFund ? '确认净值' : '单价'"
            min-width="90"
            align="right"
          >
            <template #default="{ row }">
              <MoneyDisplay
                :value="row.price || 0"
                :show-sign="false"
                :auto-color="false"
                size="sm"
              />
            </template>
          </el-table-column>
          <el-table-column
            :label="isFund ? '确认份额' : '数量'"
            min-width="80"
            align="right"
          >
            <template #default="{ row }">{{ row.quantity }}</template>
          </el-table-column>
          <el-table-column label="金额" min-width="90" align="right">
            <template #default="{ row }">
              <MoneyDisplay
                :value="row.amount || 0"
                :show-sign="false"
                :auto-color="false"
                size="sm"
              />
            </template>
          </el-table-column>
          <el-table-column label="手续费" min-width="70" align="right">
            <template #default="{ row }">
              <MoneyDisplay
                :value="row.fee || 0"
                :show-sign="false"
                :auto-color="false"
                size="sm"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="72" align="center">
            <template #default="{ row }">
              <el-button
                size="small"
                text
                type="primary"
                :icon="Edit"
                @click="openEdit(row)"
              >
                编辑
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 🔥 修复3：明确加载完成的提示 -->
        <div
          v-if="!loadingTransactions && transactionsList.length > 0"
          class="text-center text-xs mt-4 pb-2"
          :style="{ color: 'var(--text-tertiary)' }"
        >
          已加载全部交易记录
        </div>

        <div
          v-if="transactionsList.length === 0"
          class="text-center py-6 text-xs"
          :style="{ color: 'var(--text-tertiary)' }"
        >
          暂无交易记录
        </div>
      </template>
    </div>

    <!-- 行内编辑弹窗 -->
    <TransactionEditDialog
      v-model="editDialogVisible"
      :transaction="editingTxn"
      :asset-type="positionData?.asset_type"
      @saved="handleSaved"
    />
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from "vue";
import { Loading, Edit } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getPositionTransactions } from "@/api/positions";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import TransactionEditDialog from "./TransactionEditDialog.vue";
import { txnTypeLabel } from "@/constants";

const props = defineProps<{
  visible: boolean;
  positionData: any;
}>();

const emit = defineEmits<{
  "update:visible": [value: boolean];
}>();

// 基金类型判断（基金/货币基金）
const isFund = computed(() =>
  ["fund", "money_fund"].includes(props.positionData?.asset_type)
);

// 抽屉双向绑定
const drawerVisible = computed({
  get: () => props.visible,
  set: val => emit("update:visible", val)
});

// 交易记录状态
const loadingTransactions = ref(false);
const transactionsList = ref<any[]>([]);
const transactionsTotal = ref(0);

// 获取交易明细 API 调用
async function fetchTransactions() {
  if (!props.positionData?.id) return;

  loadingTransactions.value = true;
  try {
    const res = await getPositionTransactions(props.positionData.id);
    // 根据后端实际返回格式解析
    const data = (res as any)?.data;

    // 兼容处理
    if (data && typeof data === "object" && "items" in data) {
      transactionsList.value = data.items || [];
      transactionsTotal.value = data.total || 0;
    } else {
      transactionsList.value = Array.isArray(data) ? data : [];
      transactionsTotal.value = transactionsList.value.length;
    }
  } catch (e) {
    transactionsList.value = [];
    transactionsTotal.value = 0;
  } finally {
    loadingTransactions.value = false;
  }
}

// 监听抽屉打开事件，触发数据加载
watch(
  () => props.visible,
  newVal => {
    if (newVal) {
      // 打开时先清空之前的记录
      transactionsList.value = [];
      transactionsTotal.value = 0;
      // 等待 DOM 渲染完毕再拉取数据
      nextTick(() => fetchTransactions());
    }
  }
);

// 重置状态
function resetState() {
  transactionsList.value = [];
  transactionsTotal.value = 0;
  editDialogVisible.value = false;
  editingTxn.value = null;
}

// 行内编辑
const editDialogVisible = ref(false);
const editingTxn = ref<any>(null);
function openEdit(row: any) {
  editingTxn.value = row;
  editDialogVisible.value = true;
}
function handleSaved(data: any) {
  const idx = transactionsList.value.findIndex(t => t.id === data?.id);
  if (idx !== -1) {
    Object.assign(transactionsList.value[idx], {
      quantity: data.quantity,
      price: data.price,
      amount: data.amount,
      fee: data.fee,
      trade_date: data.trade_date || data.confirm_date || null,
      confirm_date: data.confirm_date,
      notes: data.notes,
      import_hash: data.import_hash
    });
  }
}
</script>

<style scoped>
/* 无需额外全局 CSS，完全依赖色彩规范变量 */
</style>
