<template>
  <!-- 卖出数量 + 快捷档位 + 最小单位提示（#980 拆分自 SellForm.vue）。
       标签走 TRADE_FIELD_LABELS.quantity（成交数量）：基金叫份额、股票叫股/张
       的区分保留在辅助文案里（「每笔最少 0.0001 份 / {{ min }} 股/张」），
       输入框本身同一件事只允许一个叫法（2026-11-12 全站标签统一）。 -->
  <el-form-item :label="TRADE_FIELD_LABELS.quantity" prop="quantity">
    <div class="flex flex-col gap-2 w-full">
      <el-input-number
        v-model="qtyModel"
        :min="min"
        style="width: 100%"
        :controls="false"
        :max="max"
        :step="type === 'fund' ? 0.0001 : step"
        :precision="type === 'fund' ? 4 : 0"
        :placeholder="placeholder"
        @blur="emit('touched')"
      />
      <!-- 快捷档位：与转换表单同一组件（档位表 / 取整 / 选中态唯一实现） -->
      <div class="flex items-center justify-between w-full">
        <QuickRatioPicker
          v-model="qtyModel"
          :total="max"
          :type="type"
          :step="step"
          aria-label="卖出份额比例"
        />
      </div>
      <div
        v-if="showQtyHint"
        class="text-xs"
        style="color: var(--color-danger)"
      >
        <template v-if="type === 'fund'">每笔最少 0.0001 份</template>
        <template v-else>每笔最少卖出 {{ min }} 股/张</template>
      </div>
      <div
        v-else-if="isOddLot && type !== 'fund'"
        class="text-xs"
        style="color: var(--color-warning-ink)"
      >
        （含碎股，可全部卖出）
      </div>
    </div>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from "vue";
import QuickRatioPicker from "@/components/QuickRatioPicker/index.vue";
import { TRADE_FIELD_LABELS } from "@/constants";

const props = defineProps<{
  quantity: number | undefined;
  /** 最多可卖（持仓数量） */
  max: number;
  /** 最小可卖（基金 0.0001 份 / 股票一手，碎股取持仓本身） */
  min: number;
  type: string;
  /** 一手股数 */
  step: number;
  showQtyHint: boolean;
  isOddLot: boolean;
  placeholder: string;
}>();
const emit = defineEmits<{
  "update:quantity": [value: number | undefined];
  /** 失焦：父层据此开始提示「低于最小单位」 */
  touched: [];
}>();

const qtyModel = computed({
  get: () => props.quantity,
  set: val => emit("update:quantity", val)
});
</script>
