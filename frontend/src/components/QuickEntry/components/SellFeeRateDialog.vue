<template>
  <!-- 赎回费率分布弹窗（根据是否有输入份额动态显示列）：#980 拆分自 SellForm.vue -->
  <el-dialog
    v-model="visibleModel"
    title="赎回费率分布"
    width="600px"
    destroy-on-close
  >
    <div v-if="!hasPosition" class="text-center py-8 text-secondary">
      请先选择持仓
    </div>
    <template v-else>
      <div class="text-sm mb-3" style="color: var(--text-secondary)">
        当前持有 {{ maxQuantity.toFixed(4) }} 份
        <template v-if="enteredShares > 0">
          ，拟赎回 {{ enteredShares.toFixed(4) }} 份
        </template>
      </div>
      <el-table :data="mergedFeeData" stripe style="width: 100%">
        <el-table-column prop="range" label="持有天数" min-width="100" />
        <el-table-column prop="rate" label="费率" align="right" width="80">
          <template #default="{ row }">
            {{ (row.rate * 100).toFixed(2) }}%
          </template>
        </el-table-column>
        <el-table-column
          prop="holdShares"
          label="持有份额"
          align="right"
          width="110"
        />
        <el-table-column
          v-if="enteredShares > 0"
          prop="sellShares"
          label="卖出份额"
          align="right"
          width="110"
        >
          <template #default="{ row }">
            {{ row.sellShares !== null ? row.sellShares : "--" }}
          </template>
        </el-table-column>
      </el-table>
      <div
        v-if="maxQuantity > totalCalculatedHold"
        class="text-xs mt-2"
        style="color: var(--color-warning-ink)"
      >
        注：当前持有 {{ maxQuantity.toFixed(4) }} 份，其中
        {{ totalCalculatedHold.toFixed(4) }}
        份有买入记录，可用于费率计算，其余份额未纳入分布。
      </div>
      <div class="mt-4 text-xs" style="color: var(--text-tertiary-ink)">
        注：卖出份额按先进先出（FIFO）规则，从最早买入份额开始扣减。
      </div>
    </template>
    <template #footer>
      <el-button type="primary" @click="visibleModel = false">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  modelValue: boolean;
  /** 是否已选持仓（未选时只显示空态，不渲染表格） */
  hasPosition: boolean;
  /** 当前持仓可卖总量 */
  maxQuantity: number;
  /** 用户已输入的赎回份额（>0 才显示「卖出份额」列） */
  enteredShares: number;
  /** 全仓分布与本次份额分布的合并行 */
  mergedFeeData: any[];
  /** 有买入记录、可参与费率计算的份额合计 */
  totalCalculatedHold: number;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();

const visibleModel = computed({
  get: () => props.modelValue,
  set: val => emit("update:modelValue", val)
});
</script>
