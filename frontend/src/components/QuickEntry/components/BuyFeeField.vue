<template>
  <!-- 手续费。
       基金：金额 / 费率双模式 + 申购折扣档位（#980 拆分自 BuyForm.vue）。
       股票 / ETF：`simple` 模式，只收一个实收金额 —— 佣金有「免五不免五」、
       各家费率不同，费率模式既算不准也多一层心智负担（与卖出侧对称）。
       状态仍住父层（提交时要换算），区块只负责呈现与透传。 -->
  <el-form-item :label="TRADE_FIELD_LABELS.fee" prop="fee">
    <div class="flex flex-col gap-2 w-full">
      <!-- 第一行：模式切换（仅基金）+ 数值输入 -->
      <div class="flex items-center gap-3 w-full">
        <el-select
          v-if="!simple"
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
          :precision="simple ? 2 : feeMode === 'amount' ? 2 : 4"
          :min="0"
          :placeholder="
            simple
              ? '券商实际收取的费用（不确定可留 0）'
              : feeMode === 'amount'
                ? '输入手续费金额'
                : '0.0000'
          "
        />
        <span class="text-sm shrink-0" style="color: var(--text-tertiary-ink)">
          {{ simple || feeMode === "amount" ? "元" : "%" }}
        </span>
      </div>

      <!-- 第二行：快捷折扣档位（仅基金 · 费率模式）。
           「多选一、选项少」→ SegmentedControl（design.md 语言边界），
           与份额档位/交易时点同一套软按钮选中态，不再手写 el-button 组。 -->
      <div
        v-if="!simple && feeMode === 'rate'"
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
      <span v-if="simple"
        >含佣金、过户费等，按交割单实收金额填写；不填则按 0
        计，持仓成本会偏低</span
      >
      <span v-else>费率已根据账户预设填充，可手动修改</span>
    </div>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from "vue";
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import { TRADE_FIELD_LABELS } from "@/constants";
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
  /** 简化模式（股票 / ETF）：只收实收金额，隐藏模式切换与折扣档位 */
  simple?: boolean;
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
