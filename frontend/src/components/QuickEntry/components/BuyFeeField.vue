<template>
  <!-- 手续费（金额 / 费率双模式 + 折扣档位）。
       #980 拆分自 BuyForm.vue：状态仍住父层（提交时要换算，区块只负责呈现与透传）。 -->
  <el-form-item label="手续费" prop="fee">
    <div class="flex flex-col gap-2 w-full">
      <!-- 第一行：模式切换 + 数值输入 -->
      <div class="flex items-center gap-3 w-full">
        <el-select
          v-model="feeModeModel"
          style="width: 100px"
          @change="emit('fee-mode-change')"
        >
          <el-option label="金额" value="amount" />
          <el-option label="费率" value="rate" />
        </el-select>

        <!-- 直接用 form.fee 接管所有输入，确保核心 watch 能监听到 -->
        <el-input-number
          v-model="feeModel"
          class="flex-1"
          :controls="false"
          :precision="feeMode === 'amount' ? 2 : 4"
          :min="0"
          :placeholder="feeMode === 'amount' ? '输入手续费金额' : '0.0000'"
        />
        <span class="text-sm shrink-0" style="color: var(--text-tertiary-ink)">
          {{ feeMode === "amount" ? "元" : "%" }}
        </span>
      </div>

      <!-- 第二行：快捷折扣档位（仅费率模式）。
           「多选一、选项少」→ SegmentedControl（design.md 语言边界），
           与份额档位/交易时点同一套软按钮选中态，不再手写 el-button 组。 -->
      <div
        v-if="feeMode === 'rate'"
        class="flex flex-wrap items-center gap-2 mt-1"
      >
        <SegmentedControl
          v-model="discountModel"
          :options="FEE_DISCOUNT_OPTIONS"
          aria-label="申购费折扣"
          @change="emit('discount-change')"
        />
      </div>
    </div>

    <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
      费率已根据账户预设填充，可手动修改
    </div>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from "vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import {
  FEE_DISCOUNT_OPTIONS,
  type FeeMode
} from "@/components/QuickEntry/composables/useBuyFee";

const props = defineProps<{
  /** 手续费金额或费率百分比（随 feeMode 变义） */
  fee: number | undefined;
  feeMode: FeeMode;
  /** 申购费折扣系数（1 / 0.1 / 0.01 / 0） */
  discount: number;
}>();
const emit = defineEmits<{
  "update:fee": [value: number | undefined];
  "update:feeMode": [value: FeeMode];
  "update:discount": [value: number];
  /** 模式切换：父层按新模式换算 form.fee 的单位 */
  "fee-mode-change": [];
  /** 点折扣档位：父层按新折扣重算 form.fee */
  "discount-change": [];
}>();

const feeModel = computed({
  get: () => props.fee,
  set: val => emit("update:fee", val)
});
const feeModeModel = computed({
  get: () => props.feeMode,
  set: val => emit("update:feeMode", val)
});
const discountModel = computed({
  get: () => props.discount,
  set: val => emit("update:discount", val)
});
</script>
