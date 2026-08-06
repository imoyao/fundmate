<template>
  <div>
    <el-form-item label="账户类型">
      <el-select
        :model-value="ledgerType"
        class="w-full"
        @update:model-value="onTypeChange"
      >
        <el-option
          v-for="opt in LEDGER_TYPE_OPTIONS"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
    </el-form-item>

    <el-form-item
      v-if="ledgerType === 'stock' || ledgerType === 'fund'"
      label="关联现金账户"
    >
      <el-select
        :model-value="linkedCashId"
        class="w-full"
        clearable
        placeholder="选择关联的现金/活钱账户"
        @update:model-value="onCashChange"
      >
        <el-option
          v-for="ledger in cashLedgers"
          :key="ledger.id"
          :label="ledger.name"
          :value="ledger.id"
        />
      </el-select>
    </el-form-item>

    <el-form-item label="关联投资组合">
      <el-select
        :model-value="portfolioId"
        class="w-full"
        clearable
        placeholder="不关联组合"
        @update:model-value="onPortfolioChange"
      >
        <el-option
          v-for="p in portfolioList"
          :key="p.id"
          :label="p.name"
          :value="p.id"
        />
      </el-select>
    </el-form-item>

    <!-- 高级设置：费率信息 -->
    <el-collapse
      v-if="ledgerType === 'stock' || ledgerType === 'fund'"
      class="mt-4"
    >
      <el-collapse-item title="高级设置（费率）" name="fee">
        <template v-if="ledgerType === 'stock'">
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

        <template v-if="ledgerType === 'fund'">
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
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { LEDGER_TYPE_OPTIONS } from "@/constants";

interface Props {
  ledgerType: string;
  linkedCashId: number | null;
  portfolioId: number | null;
  cashLedgers?: any[];
  portfolioList?: any[];
  feeConfig?: any; // 初始费率对象
}

const props = withDefaults(defineProps<Props>(), {
  cashLedgers: () => [],
  portfolioList: () => [],
  feeConfig: null
});

const emit = defineEmits<{
  "update:ledgerType": [value: string];
  "update:linkedCashId": [value: number | null];
  "update:portfolioId": [value: number | null];
  "update:feeConfig": [value: any];
}>();

// 证券费率结构
const feeStock = ref({
  commission_rate: 0,
  commission_min: undefined as number | undefined,
  stamp_duty: 0,
  transfer_fee: 0
});

// 基金费率结构
const feeFund = ref({
  subscription_discount: 0
});

// 初始化费率数据
watch(
  () => props.feeConfig,
  val => {
    if (val) {
      if (props.ledgerType === "stock") {
        feeStock.value = {
          commission_rate: val.commission?.rate || 0,
          commission_min: val.commission?.min,
          stamp_duty: val.stamp_duty?.rate || 0,
          transfer_fee: val.transfer_fee?.rate || 0
        };
      } else if (props.ledgerType === "fund") {
        feeFund.value = {
          subscription_discount: val.subscription_discount || 0
        };
      }
    }
  },
  { immediate: true }
);

// 构建完整的 fee_config 对象并发射
function buildFeeConfig(): any {
  if (props.ledgerType === "stock") {
    return {
      commission: {
        rate: feeStock.value.commission_rate,
        min: feeStock.value.commission_min
      },
      stamp_duty: {
        rate: feeStock.value.stamp_duty,
        scope: "sell_only"
      },
      transfer_fee: {
        rate: feeStock.value.transfer_fee,
        scope: "both"
      }
    };
  } else if (props.ledgerType === "fund") {
    return {
      subscription_discount: feeFund.value.subscription_discount
    };
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

function onTypeChange(val: string) {
  emit("update:ledgerType", val);
  // 如果切换到的类型不是 stock/fund，清空关联的现金账户
  if (val !== "stock" && val !== "fund") {
    emit("update:linkedCashId", null);
    emit("update:feeConfig", null);
  }
}

function onCashChange(val: number | null) {
  emit("update:linkedCashId", val);
}

function onPortfolioChange(val: number | null) {
  emit("update:portfolioId", val);
}
</script>
