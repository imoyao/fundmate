<script setup lang="ts">
// 交易流水·筛选工具条（视图切换 + 记录数 + 导出 + 五个筛选项 + symbol 回显）。
//
// `filters` 用 defineModel 而不是「每个筛选项一个 emit」：父层持有同一个响应式对象，
// 子层改的是对象属性（不是替换整个对象），所以本地改动直接落到父层状态上，
// 只有父层需要重置（清 symbol）时才由父层自己改。
import { Download, Refresh } from "@element-plus/icons-vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import {
  TXN_VIEW_OPTIONS,
  type TransactionFilters
} from "./transactionListModel";

const viewMode = defineModel<string>("viewMode", { required: true });
const filters = defineModel<TransactionFilters>("filters", { required: true });

defineProps<{
  totalCount: number;
  loading: boolean;
  exporting: boolean;
}>();

const emit = defineEmits<{
  change: [];
  reset: [];
  export: [];
  "clear-symbol": [];
}>();
</script>

<template>
  <el-card shadow="never" class="mb-4">
    <div class="flex items-center justify-between mb-4">
      <SegmentedControl
        v-model="viewMode"
        :options="TXN_VIEW_OPTIONS"
        size="small"
        aria-label="流水视图切换"
      />
      <div class="flex items-center gap-3">
        <span class="text-gray-400 text-sm">共 {{ totalCount }} 条记录</span>
        <el-button
          :icon="Download"
          plain
          size="small"
          :loading="exporting"
          @click="emit('export')"
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
          @change="emit('change')"
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
      </el-col>
      <el-col :xs="24" :sm="4" class="mb-2 sm:mb-0">
        <el-select
          v-model="filters.status"
          placeholder="交易状态"
          clearable
          class="w-full"
          @change="emit('change')"
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
          @change="emit('change')"
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
          @change="emit('change')"
        />
      </el-col>
      <el-col :xs="12" :sm="2">
        <el-button
          :icon="Refresh"
          circle
          :loading="loading"
          @click="emit('reset')"
        />
      </el-col>
    </el-row>

    <!-- #2160：symbol 预筛的回显。它多半不是用户自己设的（详情页「查看全部流水」
         带过来的），所以必须显式可见 + 可清除：否则「共 3 条」会被读成全站只有 3 条。 -->
    <div
      v-if="filters.symbol"
      class="mb-2 flex items-center gap-2 text-sm text-gray-500"
    >
      <span>已按产品代码筛选：</span>
      <el-tag closable size="small" type="info" @close="emit('clear-symbol')">
        {{ filters.symbol }}
      </el-tag>
    </div>
  </el-card>
</template>
