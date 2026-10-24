<template>
  <el-form
    ref="formRef"
    :model="form"
    :rules="rules"
    label-width="90px"
    size="large"
    class="flex flex-col gap-5"
  >
    <!-- 账户 + 持仓 -->
    <SellPositionField
      v-model:ledger-id="form.ledger_id"
      v-model:position-id="form.positionId"
      :accounts="availableAccounts"
      :positions="accountPositions"
      :hide-account-select="hideAccountSelect"
      :show-position-select="showPositionSelect"
      :select-key="positionSelectKey"
      @account-change="onAccountChange"
      @position-change="onPositionSelect"
      @go-to-inventory="emit('go-to-inventory')"
    />

    <template v-if="form.positionId">
      <!-- 1. 交易日期 -->
      <el-form-item label="交易日期" prop="trade_date">
        <div class="flex items-center gap-3 w-full">
          <!-- 日期框外层自带弹性：DatePicker 是 inheritAttrs:false，写它身上的
               `:class` 落不到 DOM（曾用 `showIsAfter15 ? 'flex-1' : 'w-full'`）。 -->
          <div class="min-w-0 flex-1">
            <el-date-picker
              v-model="form.trade_date"
              type="date"
              style="width: 100%"
              value-format="YYYY-MM-DD"
              :clearable="false"
              :disabled-date="disabledDate"
            />
          </div>
          <TradeSlotSwitch v-if="showIsAfter15" v-model="form.isAfter15" />
        </div>
        <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
          <span v-if="form.isAfter15 && selectedPosition?.type === 'fund'">
            15:00后赎回，按下一交易日（T+1）净值计算
          </span>
          <span v-if="selectedPosition?.type === 'fund' && confirmDate">
            · 预计确认日：{{ confirmDate }}
          </span>
        </div>
      </el-form-item>

      <!-- 2. 卖出份额 / 数量 -->
      <SellQuantityField
        v-model:quantity="form.quantity"
        :max="maxQuantity"
        :min="sellMin"
        :type="form.type"
        :step="stepForSecurity"
        :show-qty-hint="showQtyHint"
        :is-odd-lot="isOddLot"
        :placeholder="placeholderText"
        @touched="qtyTouched = true"
      />

      <!-- 3. 卖出价格（仅股票显示） -->
      <el-form-item v-if="form.type !== 'fund'" label="卖出价格" prop="price">
        <el-input-number
          v-model="form.price"
          style="width: 100%"
          :controls="false"
          :min="0"
          :step="0.01"
          :precision="2"
          placeholder="卖出价格"
        />
        <span class="text-xs text-gray-500 mt-1"
          >默认为成本价，可按实际成交价修改</span
        >
      </el-form-item>

      <!-- 4. 卖出费用（纯金额模式） -->
      <template v-if="form.type === 'fund'">
        <el-form-item label="卖出费用" prop="fee">
          <div class="flex flex-col gap-2 w-full">
            <div class="flex items-center gap-3 w-full">
              <el-input-number
                v-model="form.fee"
                class="flex-1"
                :controls="false"
                :precision="2"
                :min="0"
                placeholder="输入手续费金额"
                @change="onFeeManualChange"
              />
              <el-button @click="openFeeRateDialog">查询费率</el-button>
            </div>
          </div>
          <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
            按持仓天数自动匹配费率，可手动修改
          </div>
        </el-form-item>
      </template>

      <!-- 5. 对应净值（提升视觉层级：净值是基金买入/赎回到账的核心依据，信息层级应与重要性匹配） -->
      <TradeNavPriceRow
        v-if="form.type === 'fund'"
        :price="form.price"
        :nav-date="actualNavDate"
        :fallback-date="form.trade_date"
      />

      <!-- 6. 预估金额 -->
      <el-form-item label="预估金额">
        <el-input :model-value="sellEstimate" class="w-full" readonly disabled>
          <template #append>元</template>
        </el-input>
      </el-form-item>
    </template>

    <!-- 备注 -->
    <el-form-item label="备注">
      <el-input
        v-model="form.notes"
        type="textarea"
        :rows="2"
        placeholder="补充交易理由（选填）"
      />
    </el-form-item>

    <!-- 资金流向提示 -->
    <div
      class="mt-2 mb-4 p-3 bg-gray-50 rounded-lg text-sm flex items-center gap-2"
      style="color: var(--text-secondary)"
    >
      <IconifyIconOffline icon="ep:info-filled" class="text-gray-400" />
      <span
        >卖出资金将留存在当前账户余额，可用于再投资；如需转出到银行卡，请单独登记银证转账</span
      >
    </div>

    <!-- 费率查询弹窗（根据是否有输入份额动态显示列） -->
    <SellFeeRateDialog
      v-model="feeRateDialogVisible"
      :has-position="!!selectedPosition"
      :max-quantity="maxQuantity"
      :entered-shares="enteredShares"
      :merged-fee-data="mergedFeeData"
      :total-calculated-hold="totalCalculatedHold"
    />
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from "vue";
import { ElMessage } from "element-plus";
import type { FormInstance } from "element-plus";
import { validateTradeOrder } from "@/api/positions";
import { usePositionSubmit } from "@/composables/usePositionSubmit";
import { useFormDirtySnapshot } from "@/composables/useFormDirtySnapshot";
import {
  useSecurityPriceRange,
  checkPriceInRange
} from "@/composables/useSecurityPrice";
import { disabledTradeDate } from "@/utils/date";
import { IconifyIconOffline } from "@/components/ReIcon";
import TradeSlotSwitch from "@/components/TradeSlotSwitch/index.vue";
import SellPositionField from "./components/SellPositionField.vue";
import SellQuantityField from "./components/SellQuantityField.vue";
import SellFeeRateDialog from "./components/SellFeeRateDialog.vue";
import TradeNavPriceRow from "./components/TradeNavPriceRow.vue";
import { defaultSellForm } from "./sellFormModel";
import { buildSellPayload } from "./sellFormPayload";
import { createSellRules } from "./sellFormRules";
import { useSellPositions } from "./composables/useSellPositions";
import { useSellFee } from "./composables/useSellFee";
import { useSellNavSync } from "./composables/useSellNavSync";
import { useSellFormActions } from "./composables/useSellFormActions";

const props = defineProps<{
  ledgers: any[];
  hideAccountSelect?: boolean;
  defaultLedgerId?: number | null;
}>();
const emit = defineEmits<{
  (e: "submit-success"): void;
  (e: "close"): void;
  (e: "go-to-inventory"): void;
  (e: "positions-loaded", ledgerIds: number[]): void;
  (e: "go-sync"): void;
}>();

const positionSelectKey = ref(0);
const showPositionSelect = ref(true);
const form = reactive(defaultSellForm());
const formRef = ref<FormInstance>();
const selectedPosition = ref<any>(null);

// 交易日期禁用规则收敛到 utils/date（#1835）
const disabledDate = disabledTradeDate;

// 账户 → 持仓 → 可卖量 / 步长 / 快捷档位
const {
  qtyTouched,
  availableAccounts,
  currentLedger,
  accountPositions,
  maxQuantity,
  stepForSecurity,
  sellMin,
  placeholderText,
  isOddLot,
  showQtyHint,
  sellEstimate,
  showIsAfter15,
  fetchPositionsByAccount,
  resetPositions
} = useSellPositions({
  getLedgers: () => props.ledgers,
  form,
  selectedPosition,
  onLoaded: ids => emit("positions-loaded", ids)
});

// 股票价格区间（#948）：卖出价校验用，随持仓选择与交易日刷新（统一走 useSecurityPriceRange）
const { priceRange: stockPriceRange } = useSecurityPriceRange(
  computed(() => selectedPosition.value?.symbol),
  computed(() => form.trade_date),
  computed(() => form.type === "stock")
);

const { confirmDate, actualNavDate, resetTradeDate } = useSellNavSync({
  form,
  selectedPosition
});

// 赎回费用与费率分布
const {
  feeRateDialogVisible,
  totalCalculatedHold,
  enteredShares,
  mergedFeeData,
  calculateFeeAndRate,
  onFeeManualChange,
  openFeeRateDialog,
  resetFeeState,
  resetFeeManualFlag
} = useSellFee({ form, selectedPosition });

// 未保存离开保护（#1853）：脏状态住在本子组件里（父组件 TransactionDrawer 拿不到），
// 故 expose 出去。快照声明必须在 resetForm 之前——它被 resetForm 调用。
const { markClean, isDirty } = useFormDirtySnapshot(() => form);

// 账户切换 / 选持仓
const { clearFormData, onAccountChange, onPositionSelect } = useSellFormActions(
  {
    form,
    formRef,
    selectedPosition,
    accountPositions,
    qtyTouched,
    showPositionSelect,
    positionSelectKey,
    resetTradeDate,
    resetFeeState,
    resetFeeManualFlag,
    calculateFeeAndRate
  }
);

// 校验规则：份额文案随品类变，价格区间只在股票生效（#948 统一约束）
const rules = createSellRules({
  getType: () => form.type,
  stockPriceRange
});

// ---------- 提交 ----------
async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  const quantity = form.quantity!;
  const currentHolding = maxQuantity.value;

  const validateRes = await validateTradeOrder({
    symbol: form.symbol,
    market: form.market,
    type: form.type,
    current_hold: currentHolding,
    order_qty: quantity,
    op_type: "sell"
  });
  if (!validateRes.valid) {
    ElMessage.error(validateRes.message);
    return;
  }

  // 股票价格区间校验（#948）：统一走 useSecurityPrice.checkPriceInRange
  const priceErr = checkPriceInRange(
    form.price ?? 0,
    stockPriceRange.value,
    form.type === "stock"
  );
  if (priceErr) {
    ElMessage.error(priceErr);
    return;
  }

  const body = buildSellPayload({
    form,
    accountName: currentLedger.value?.name || "",
    quantity
  });

  // 统一提交层（#933）：修复原空 catch 吞错——失败提示由本层统一弹出
  const { submitPosition } = usePositionSubmit();
  const ok = await submitPosition(body);
  if (ok) {
    emit("submit-success");
  }
}

function resetForm() {
  Object.assign(form, defaultSellForm());
  selectedPosition.value = null;
  resetPositions();
  resetFeeManualFlag();
  formRef.value?.resetFields();
  positionSelectKey.value++;

  if (props.hideAccountSelect && props.defaultLedgerId) {
    form.ledger_id = props.defaultLedgerId;
  }

  // 未保存离开保护的脏基线（#1853）：必须在**全部重置动作之后**再记快照。
  // 记在前面会把「本轮刚填的值」记成基线，紧接着 Object.assign 重置成默认值，
  // 于是 isDirty 为 true——提交成功后关闭抽屉时被问「确定放弃吗？」。
  markClean();
}

// ---------- 监听 ----------
// 价格/数量/交易日期变化：重算费用与费率（与净值回填解耦，避免循环）。
watch(
  [
    () => form.price,
    () => form.quantity,
    () => form.trade_date,
    () => form.isAfter15
  ],
  () => {
    if (!selectedPosition.value) return;
    calculateFeeAndRate();
  }
);

watch(
  () => props.defaultLedgerId,
  newVal => {
    if (props.hideAccountSelect && newVal) {
      form.ledger_id = newVal;
      clearFormData();
    }
  },
  { immediate: true }
);

onMounted(() => {
  fetchPositionsByAccount();
});

defineExpose({ handleSubmit, resetForm, isDirty });
</script>

<style scoped>
/* .text-xs 由全局原子类提供，不再本地重复声明 */
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

/* 输入框高度：走 #1772 输入基线的高度令牌（本表单是 40px 视觉高度，
   EP 默认 32px）。底色 / 边框 / hover / focus / 圆角已由基线统一，
   原先两条以 `.el-input__wrapper` 为目标的 :deep 块（含一条 `.el-select .el-input__wrapper`
   死规则 —— el-select 树里没有 .el-input__wrapper）即因此删除。 */
.el-form {
  --input-height: 40px;
}

/* 避免校验错误过渡闪烁 */
:deep(.el-form-item__error) {
  transition: none;
}
</style>
