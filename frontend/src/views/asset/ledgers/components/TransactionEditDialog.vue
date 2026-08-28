<template>
  <el-dialog
    :model-value="modelValue"
    title="编辑交易"
    width="520px"
    @update:model-value="val => emit('update:modelValue', val)"
    @open="initForm"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="90px"
      size="large"
      class="flex flex-col gap-4"
      :disabled="saving"
    >
      <!-- 手工编辑提示：作为弹窗内常驻提示，避免保存后弹出警告框干扰用户 -->
      <el-alert
        v-if="isManual"
        type="info"
        :closable="false"
        show-icon
        class="mb-1"
        title="该记录为手工编辑，重新导入时需按新内容对账"
      />
      <!-- 数量/份额：基金按份额(支持小数)，股票/可转债按股|张(整数) -->
      <el-form-item :label="isFund ? '份额' : '数量'" prop="quantity">
        <el-input-number
          v-model="form.quantity"
          style="width: 100%"
          class="w-full"
          :controls="false"
          :min="0"
          :precision="quantityPrecision"
          :step="quantityStep"
        />
        <div class="text-xs mt-1" style="color: var(--text-tertiary)">
          <template v-if="isFund">基金份额，根据金额自动反算</template>
          <template v-else>数量为整数（股 / 张）</template>
        </div>
      </el-form-item>

      <!-- 单价/净值：基金净值只读(4位)，股票价格可编辑(2位) -->
      <el-form-item :label="isFund ? '净值(元)' : '单价(元)'">
        <!-- 基金：净值不可编辑，只读展示 -->
        <el-input
          v-if="isFund"
          :model-value="
            navLoading
              ? '加载中...'
              : form.price != null
                ? Number(form.price).toFixed(4)
                : ''
          "
          readonly
          disabled
          :placeholder="navLoading ? '加载中...' : '--'"
        >
          <template #append>元/份</template>
        </el-input>
        <!-- 股票：价格可编辑，2位小数 -->
        <el-input-number
          v-else
          v-model="form.price"
          style="width: 100%"
          class="w-full"
          :controls="false"
          :min="0"
          :precision="2"
          :step="0.01"
          placeholder="0.00"
        />
      </el-form-item>

      <!-- 金额：自动计算 = 数量 * 单价 + 手续费，可手动覆盖 -->
      <el-form-item label="金额(元)">
        <el-input-number
          v-model="form.amount"
          style="width: 100%"
          class="w-full"
          :controls="false"
          :min="0"
          :precision="2"
          :step="0.01"
          placeholder="0.00"
        />
        <div class="text-xs mt-1" style="color: var(--text-tertiary)">
          <span v-if="isFund">金额为权威数据，份额自动反算，可手动修改</span>
          <span v-else>自动计算：数量 × 单价 + 手续费，可手动修改</span>
        </div>
      </el-form-item>

      <!-- 手续费：2 位小数 -->
      <el-form-item label="手续费(元)">
        <el-input-number
          v-model="form.fee"
          style="width: 100%"
          class="w-full"
          :controls="false"
          :min="0"
          :precision="2"
          :step="0.01"
          placeholder="0.00"
        />
      </el-form-item>

      <!-- 交易日期 + 15:00前/后（基金） -->
      <el-form-item label="交易日期" prop="trade_date">
        <div class="flex items-center gap-3 w-full">
          <el-date-picker
            v-model="form.trade_date"
            type="date"
            class="flex-1"
            style="width: 100%"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            clearable
          />
          <el-radio-group v-if="isFund" v-model="isAfter15" size="small">
            <el-radio-button :value="false">15:00前</el-radio-button>
            <el-radio-button :value="true">15:00后</el-radio-button>
          </el-radio-group>
        </div>
        <div
          v-if="isFund"
          class="text-xs mt-1"
          style="color: var(--text-tertiary)"
        >
          预计确认日：{{ confirmDateDisplay || "计算中..." }}
        </div>
      </el-form-item>

      <!-- 备注 -->
      <el-form-item label="备注">
        <el-input
          v-model="form.notes"
          type="textarea"
          :rows="2"
          placeholder="选填"
          style="width: 100%"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button :disabled="saving" @click="emit('update:modelValue', false)"
        >取消</el-button
      >
      <el-button type="primary" :loading="saving" @click="handleSave"
        >保存</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from "vue";
import { updateLedgerTransaction } from "@/api/ledger";
import { useFundTradeDate } from "@/composables/useFundTradeDate";
import {
  useSecurityPriceRange,
  createStockPriceValidator
} from "@/composables/useSecurityPrice";
import { ElMessage } from "element-plus";

const props = defineProps<{
  modelValue: boolean;
  transaction: any;
  assetType?: string;
  /** 基金代码（用于自动拉取净值，可从 positionData 或交易记录获取） */
  symbol?: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  saved: [data: any];
}>();

const saving = ref(false);
const formRef = ref();
const form = ref<any>({});

// 初始化标记：防止 initForm 赋值时触发 watch 覆盖原始金额
const isInitializing = ref(false);

// 15:00 后下单（影响确认日计算）
const isAfter15 = ref(false);

// 基金交易日期联动 composable（calcFundConfirmDate + fetchFundNav）
const {
  navLoading,
  confirmDate: confirmDateDisplay,
  calcConfirmAndNav
} = useFundTradeDate();

// 证券（股票/可转债等）卖出价区间校验与日期联动，统一走 useSecurityPriceRange（#948 统一约束）
const isStock = computed(() =>
  ["stock", "etf", "bond", "convertible"].includes(assetType.value)
);
const { priceRange: stockPriceRange } = useSecurityPriceRange(
  computed(() =>
    isStock.value ? props.symbol || props.transaction?.symbol : undefined
  ),
  computed(() => form.value.trade_date),
  isStock
);

// 资产类型：多字段兜底检测
// 优先用传入的 assetType，否则从交易记录中尝试多个字段
const assetType = computed(() => {
  const t = props.transaction;
  return (
    props.assetType ||
    t?.asset_type ||
    t?.type ||
    t?.security_type ||
    t?.position_type ||
    ""
  );
});

// 基金类（含货币基金）按份额(小数)处理；其余按股/张(整数)
const isFund = computed(() => ["fund", "money_fund"].includes(assetType.value));

// 是否手工编辑记录（未导入，import_hash 为空）：弹窗内展示对账提示，无需保存后弹窗
const isManual = computed(() => props.transaction?.import_hash == null);

const quantityPrecision = computed(() => (isFund.value ? 4 : 0));
const quantityStep = computed(() => (isFund.value ? 0.0001 : 1));

// 交易日期必填（确认日期由系统自动计算，不需用户输入）
const rules = {
  trade_date: [
    {
      required: true,
      message: "请选择交易日期",
      trigger: ["blur", "change"]
    }
  ],
  price: [
    {
      validator: createStockPriceValidator(
        () => stockPriceRange.value,
        () => isStock.value
      ),
      trigger: ["blur", "change"]
    }
  ]
};

function initForm() {
  isInitializing.value = true;
  const t = props.transaction || {};
  isAfter15.value = false;
  form.value = {
    quantity: t.quantity,
    price: t.price,
    amount: t.amount,
    fee: t.fee,
    trade_date: t.trade_date || null,
    confirm_date: t.confirm_date || null,
    notes: t.notes ?? ""
  };
  // 展示已有确认日期（若交易记录里有）
  confirmDateDisplay.value = t.confirm_date || "";
  nextTick(() => {
    isInitializing.value = false;
  });
}

// 金额为权威数据：
// - 基金：amount 不可被覆盖，由 amount 反算 shares = (amount - fee) / nav
// - 股票/可转债：amount = quantity * price + fee（但初始化时不覆盖原始值）
// 两种模式都在初始化时跳过，防止 initForm 赋值触发 watch 覆盖记录中的原始金额

// 基金：amount / nav / fee 变化 → 反算 shares
watch(
  [() => form.value.amount, () => form.value.price, () => form.value.fee],
  ([amount, price, fee]) => {
    if (isInitializing.value || !isFund.value) return;
    if (amount != null && price != null && price > 0 && amount >= 0) {
      const calculated =
        Math.round(
          ((Number(amount) - Number(fee || 0)) / Number(price)) * 10000
        ) / 10000;
      form.value.quantity = calculated;
    }
  }
);

// 股票/可转债：quantity / price / fee 变化 → 正算 amount
watch(
  [() => form.value.quantity, () => form.value.price, () => form.value.fee],
  ([qty, price, fee]) => {
    if (isInitializing.value || isFund.value) return;
    if (qty != null && price != null && qty >= 0 && price >= 0) {
      const calculated =
        Math.round((Number(qty) * Number(price) + Number(fee || 0)) * 100) /
        100;
      form.value.amount = calculated;
    }
  }
);

// 核心联动：交易日期变化 → 自动计算确认日期 → 自动拉取净值
// 统一走 useFundTradeDate composable，与 BuyForm / SellForm 共用同一套逻辑
watch(
  [() => form.value.trade_date, () => isAfter15.value],
  async ([newDate]) => {
    if (!newDate) {
      confirmDateDisplay.value = "";
      return;
    }

    if (!isFund.value) {
      // 股票/可转债：确认日 = 交易日
      form.value.confirm_date = newDate;
      confirmDateDisplay.value = "";
      return;
    }

    // 基金：调 composable 计算确认日 + 拉净值
    const code = props.symbol || props.transaction?.symbol;
    const result = await calcConfirmAndNav({
      tradeDate: newDate,
      symbol: code,
      isAfter15: isAfter15.value
    });
    if (result) {
      form.value.confirm_date = result.confirmDate;
      if (result.nav != null) {
        form.value.price = result.nav;
      }
    } else {
      confirmDateDisplay.value = "计算失败";
    }
  }
);

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  const t = props.transaction;
  if (!t?.ledger_id || !t?.id) {
    ElMessage.error("缺少账户或交易信息，无法保存");
    return;
  }
  saving.value = true;
  try {
    const payload: any = {
      quantity: form.value.quantity,
      price: form.value.price,
      amount: form.value.amount,
      fee: form.value.fee,
      trade_date: form.value.trade_date || null,
      confirm_date: form.value.confirm_date || null,
      notes: form.value.notes
    };
    const res: any = await updateLedgerTransaction(t.ledger_id, t.id, payload);
    const data = res?.data ?? res;
    emit("saved", data);
    emit("update:modelValue", false);
    ElMessage.success("保存成功");
  } catch (e: any) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.text-xs {
  font-size: 0.75rem;
}

/* 去掉 el-form-item 默认 margin-bottom，间距统一由 gap-4 控制 */
:deep(.el-form-item) {
  margin-bottom: 0;
}

/* 输入框统一样式 —— 对齐 design.md Input 规范 & BuyForm/SellForm */
:deep(.el-input__wrapper),
:deep(.el-textarea__inner) {
  --el-input-border-color: var(--border-default);
  --el-input-hover-border-color: var(--brand-500);
  --el-input-focus-border-color: var(--brand-700);
  --el-input-focus-shadow:
    inset 0 0 0 1px var(--brand-700), 0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);

  border-radius: var(--radius-sm);
}

:deep(.el-input-number .el-input__wrapper) {
  --el-input-border-color: var(--border-default);
  --el-input-hover-border-color: var(--brand-500);
  --el-input-focus-border-color: var(--brand-700);
  --el-input-focus-shadow:
    inset 0 0 0 1px var(--brand-700), 0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);

  height: 40px;
  border-radius: var(--radius-sm);
}

/* el-input-number controls=false 后文字默认居中，强制左对齐 */
:deep(.el-input-number .el-input__inner) {
  text-align: left;
}

/* 日期选择器：强制 100% 宽度，与数字输入框等宽 */
:deep(.el-date-editor.el-input),
:deep(.el-date-editor.el-input__wrapper) {
  --el-input-border-color: var(--border-default);
  --el-input-hover-border-color: var(--brand-500);
  --el-input-focus-border-color: var(--brand-700);
  --el-input-focus-shadow:
    inset 0 0 0 1px var(--brand-700), 0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);

  width: 100% !important;
  height: 40px;
  border-radius: var(--radius-sm);
}

/* 主按钮物理反馈 */
:deep(.el-button--primary) {
  height: 40px;
  transition:
    transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1),
    box-shadow 0.15s;
}

:deep(.el-button--primary:active) {
  box-shadow: none !important;
  transform: translateY(1px);
}

/* 校验错误样式 */
:deep(.el-form-item__error) {
  padding-top: 2px;
  font-size: 0.75rem;
  color: var(--el-color-danger, #f56c6c);
  transition: none;
}
</style>
