<script setup lang="ts">
// 交易流水·列表卡头（视图切换 + 计数 + 一级/二级筛选 + symbol 回显）。
//
// 设计 §六：页头只留「我是谁」（标题 / 副标题 / 导出），这一层是列表自己的头——
// 此前页面先是 h2 页头、又起一张筛选卡，等于同一屏两个头顶。
//
// `filters` 用 defineModel 而不是「每个筛选项一个 emit」：父层持有同一个响应式对象，
// 子层改的是对象属性（不是替换整个对象），所以本地改动直接落到父层状态上，
// 只有父层需要重置（清 symbol）时才由父层自己改。
import { Refresh } from "@element-plus/icons-vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import {
  TXN_TYPE_OPTIONS,
  TXN_VIEW_OPTIONS,
  type TransactionFilters
} from "./transactionListModel";

const viewMode = defineModel<string>("viewMode", { required: true });
const filters = defineModel<TransactionFilters>("filters", { required: true });

defineProps<{
  totalCount: number;
  loading: boolean;
}>();

const emit = defineEmits<{
  change: [];
  reset: [];
  "clear-symbol": [];
}>();
</script>

<template>
  <div class="txn-toolbar">
    <div class="txn-toolbar__head">
      <SegmentedControl
        v-model="viewMode"
        :options="TXN_VIEW_OPTIONS"
        size="small"
        aria-label="流水视图切换"
      />
      <!-- 计数 + 两句口径说明放在同一行：用户核对金额前先要知道「这数是怎么数的」 -->
      <span class="txn-toolbar__count">
        共 {{ totalCount }} 条 · 按交易日倒序 · 金额不含手续费
      </span>
    </div>

    <div class="txn-toolbar__filters">
      <!-- 一级：交易类型（高频、互斥 → 分段控制器一步到位） -->
      <SegmentedControl
        v-model="filters.type"
        :options="TXN_TYPE_OPTIONS"
        size="small"
        aria-label="按交易类型筛选"
        @change="emit('change')"
      />
      <!-- 二级：资产 / 状态 / 时间（低频条件 → 下拉，不抢一级的位置） -->
      <div class="txn-toolbar__selects">
        <el-select
          v-model="filters.assetType"
          placeholder="全部资产"
          clearable
          class="txn-toolbar__select"
          aria-label="按资产类型筛选"
          @change="emit('change')"
        >
          <el-option label="全部资产" value="" />
          <el-option label="股票" value="stock" />
          <el-option label="基金" value="fund" />
          <el-option label="可转债" value="bond" />
          <el-option label="虚拟货币" value="crypto" />
          <el-option label="银行存款" value="saving" />
          <el-option label="现金" value="cash" />
        </el-select>
        <el-select
          v-model="filters.status"
          placeholder="全部状态"
          clearable
          class="txn-toolbar__select"
          aria-label="按交易状态筛选"
          @change="emit('change')"
        >
          <el-option label="全部状态" value="" />
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
          <el-option label="已撤单" value="cancelled" />
          <el-option label="可撤单" value="pending" />
        </el-select>
        <el-select
          v-model="filters.timeRange"
          placeholder="全部时间"
          class="txn-toolbar__select"
          aria-label="按时间范围筛选"
          @change="emit('change')"
        >
          <el-option label="全部时间" value="" />
          <el-option label="近一个月" value="1m" />
          <el-option label="近三个月" value="3m" />
          <el-option label="近半年" value="6m" />
          <el-option label="近一年" value="1y" />
          <el-option label="自定义" value="custom" />
        </el-select>
        <el-date-picker
          v-if="filters.timeRange === 'custom'"
          v-model="filters.customDate"
          type="daterange"
          range-separator="至"
          start-placeholder="开始"
          end-placeholder="结束"
          class="txn-toolbar__range"
          aria-label="自定义时间范围"
          @change="emit('change')"
        />
        <el-button
          :icon="Refresh"
          circle
          :loading="loading"
          aria-label="刷新流水"
          @click="emit('reset')"
        />
      </div>
    </div>

    <!-- #2160：symbol 预筛的回显。它多半不是用户自己设的（详情页「查看全部流水」
         带过来的），所以必须显式可见 + 可清除：否则「共 3 条」会被读成全站只有 3 条。 -->
    <div v-if="filters.symbol" class="txn-toolbar__symbol">
      <span>已按产品代码筛选：</span>
      <el-tag closable size="small" type="info" @close="emit('clear-symbol')">
        {{ filters.symbol }}
      </el-tag>
    </div>
  </div>
</template>

<style scoped>
.txn-toolbar {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-compact) var(--space-standard);
  border-bottom: 1px solid var(--border-light);
}

.txn-toolbar__head {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-3);
  align-items: center;
  justify-content: space-between;
}

.txn-toolbar__count {
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}

.txn-toolbar__filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  justify-content: space-between;
}

.txn-toolbar__selects {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.txn-toolbar__select {
  width: 132px;
}

.txn-toolbar__range {
  width: 240px;
}

.txn-toolbar__symbol {
  display: flex;
  gap: var(--space-1);
  align-items: center;
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}

@media (width <= 768px) /* breakpoint-allow: 含 768 本身（iPad 竖屏即 768 宽）；bp.below("md") 不含断点本身，会把 iPad 竖屏判进桌面档，三个下拉 + 日期区间在 768 上横排挤爆 */ {
  .txn-toolbar__filters {
    flex-direction: column;
    align-items: stretch;
  }

  .txn-toolbar__select {
    width: 100%;
  }
}
</style>
