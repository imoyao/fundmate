<template>
  <div v-if="ledgerType === 'securities' || ledgerType === 'fund_platform'">
    <template v-if="ledgerType === 'securities'">
      <el-form-item label="佣金率">
        <el-input-number
          :model-value="feeStock.commission_rate"
          :min="0"
          :max="1"
          :precision="4"
          :step="0.0001"
          controls-position="right"
          class="w-full"
          placeholder="如 0.00025 表示万2.5"
          @update:model-value="updateStockFee('commission_rate', $event)"
        />
        <p class="text-xs mt-1" :style="{ color: 'var(--text-tertiary)' }">
          如万2.5输入 0.00025
        </p>
      </el-form-item>
      <el-form-item label="最低佣金（元）">
        <el-input-number
          :model-value="feeStock.commission_min"
          :min="0"
          :precision="2"
          controls-position="right"
          class="w-full"
          placeholder="如 5 元"
          @update:model-value="updateStockFee('commission_min', $event)"
        />
      </el-form-item>
      <el-form-item label="印花税">
        <el-input-number
          :model-value="feeStock.stamp_duty"
          :min="0"
          :max="1"
          :precision="4"
          :step="0.0001"
          controls-position="right"
          class="w-full"
          placeholder="仅卖出收取，如 0.005"
          @update:model-value="updateStockFee('stamp_duty', $event)"
        />
      </el-form-item>
      <el-form-item label="过户费">
        <el-input-number
          :model-value="feeStock.transfer_fee"
          :min="0"
          :max="1"
          :precision="4"
          :step="0.0001"
          controls-position="right"
          class="w-full"
          placeholder="双边收取，如 0.0001"
          @update:model-value="updateStockFee('transfer_fee', $event)"
        />
      </el-form-item>
    </template>

    <template v-if="ledgerType === 'fund_platform'">
      <el-form-item label="申购费折扣">
        <el-input-number
          :model-value="feeFund.subscription_discount"
          :min="0"
          :max="1"
          :precision="2"
          :step="0.01"
          controls-position="right"
          class="w-full"
          placeholder="0.1 表示 1 折"
          @update:model-value="updateFundFee($event)"
        />
        <p class="text-xs mt-1" :style="{ color: 'var(--text-tertiary)' }">
          0.1 = 1折，0.01 = 0.1折，0 = 免申购费
        </p>
      </el-form-item>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";

const props = withDefaults(
  defineProps<{
    ledgerType: string;
    feeConfig?: any; // 初始费率对象
  }>(),
  { feeConfig: null }
);

const emit = defineEmits<{ "update:feeConfig": [value: any] }>();

const feeStock = ref({
  commission_rate: 0,
  commission_min: undefined as number | undefined,
  stamp_duty: 0,
  transfer_fee: 0
});

const feeFund = ref({
  subscription_discount: 0
});

watch(
  () => props.feeConfig,
  val => {
    if (val) {
      if (props.ledgerType === "securities") {
        feeStock.value = {
          commission_rate: val.commission?.rate || 0,
          commission_min: val.commission?.min,
          stamp_duty: val.stamp_duty?.rate || 0,
          transfer_fee: val.transfer_fee?.rate || 0
        };
      } else if (props.ledgerType === "fund_platform") {
        feeFund.value = {
          subscription_discount: val.subscription_discount || 0
        };
      }
    }
  },
  { immediate: true }
);

function buildFeeConfig(): any {
  if (props.ledgerType === "securities") {
    return {
      commission: {
        rate: feeStock.value.commission_rate,
        min: feeStock.value.commission_min
      },
      stamp_duty: { rate: feeStock.value.stamp_duty, scope: "sell_only" },
      transfer_fee: { rate: feeStock.value.transfer_fee, scope: "both" }
    };
  } else if (props.ledgerType === "fund_platform") {
    return { subscription_discount: feeFund.value.subscription_discount };
  }
  return null;
}

function emitFee() {
  emit("update:feeConfig", buildFeeConfig());
}

function updateStockFee(key: string, value: number | undefined) {
  if (typeof value === "number") {
    (feeStock.value as any)[key] = value;
  }
  emitFee();
}

function updateFundFee(value: number | undefined) {
  feeFund.value.subscription_discount = value ?? 0;
  emitFee();
}
</script>
