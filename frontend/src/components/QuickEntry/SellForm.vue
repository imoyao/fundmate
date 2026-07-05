<template>
  <el-form
    ref="formRef"
    :model="form"
    :rules="rules"
    label-width="90px"
    size="large"
    class="flex flex-col gap-5"
  >
    <!-- 账户选择（可被外部隐藏） -->
    <template v-if="!hideAccountSelect">
      <el-form-item label="选择账户" prop="ledger_id">
        <el-select
          v-model="form.ledger_id"
          class="w-full"
          placeholder="选择交易账户"
          filterable
          @change="onAccountChange"
        >
          <el-option
            v-for="acc in availableAccounts"
            :key="acc.id"
            :label="acc.name"
            :value="acc.id"
          >
            <div class="flex items-center justify-between w-full">
              <span>{{ acc.name }}</span>
              <el-tag
                class="px-1.5 py-0.5 rounded text-xs font-medium shrink-0"
                :style="{
                  backgroundColor: bgFromColor(getLedgerColor(acc.ledger_type)),
                  color: getLedgerColor(acc.ledger_type)
                }"
              >
                {{ LEDGER_TYPE_SHORT[acc.ledger_type] || acc.ledger_type }}
              </el-tag>
            </div>
          </el-option>
        </el-select>
        <div
          v-if="availableAccounts.length === 0"
          class="mt-2 p-3 bg-gray-50 rounded-lg text-xs"
          style="color: var(--text-secondary)"
        >
          暂无拥有持仓的账户。如需卖出，请先前往
          <a
            class="text-[var(--color-primary)] cursor-pointer"
            @click="$emit('go-to-inventory')"
            >全面盘点</a
          >
          导入或录入持仓。
        </div>
      </el-form-item>
    </template>

    <!-- 选择持仓 -->
    <template v-if="form.ledger_id">
      <el-form-item label="选择持仓" prop="positionId">
        <el-select
          v-model="form.positionId"
          class="w-full"
          filterable
          placeholder="选择持仓"
          @change="onPositionSelect"
        >
          <el-option
            v-for="pos in accountPositions"
            :key="pos.id"
            :value="pos.id"
            :label="pos.name || pos.symbol"
          >
            <div class="flex justify-between items-center w-full">
              <span
                class="truncate"
                :style="{ color: 'var(--text-primary)' }"
                >{{ pos.name || pos.symbol }}</span
              >
              <span
                class="text-xs whitespace-nowrap"
                :style="{ color: 'var(--text-tertiary)' }"
              >
                可用 {{ Number(pos.quantity).toFixed(2) }}
              </span>
            </div>
          </el-option>
        </el-select>
        <div
          v-if="accountPositions.length === 0"
          class="text-xs mt-1"
          style="color: var(--text-tertiary)"
        >
          当前账户无可用持仓，无法执行卖出/赎回操作。
        </div>
      </el-form-item>

      <template v-if="form.positionId">
        <!-- 1. 交易日期 -->
        <el-form-item label="交易日期" prop="trade_date">
          <div class="flex items-center gap-3 w-full">
            <el-date-picker
              v-model="form.trade_date"
              type="date"
              :class="showIsAfter15 ? 'flex-1' : 'w-full'"
              style="width: 100%"
              value-format="YYYY-MM-DD"
              :clearable="false"
              :disabled-date="disabledDate"
            />
            <el-radio-group
              v-if="showIsAfter15"
              v-model="form.isAfter15"
              size="small"
            >
              <el-radio-button :value="false">15:00前</el-radio-button>
              <el-radio-button :value="true">15:00后</el-radio-button>
            </el-radio-group>
          </div>
          <div class="text-xs mt-1" style="color: var(--text-tertiary)">
            <span v-if="form.isAfter15 && selectedPosition?.type === 'fund'">
              15:00后赎回，按下一交易日（T+1）净值计算
            </span>
            <span v-if="selectedPosition?.type === 'fund' && confirmDate">
              · 预计确认日：{{ confirmDate }}
            </span>
          </div>
        </el-form-item>

        <!-- 2. 卖出份额 / 数量 -->
        <el-form-item
          :label="form.type === 'fund' ? '卖出份额' : '卖出数量'"
          prop="quantity"
        >
          <div class="flex flex-col gap-2 w-full">
            <div class="flex items-center gap-3 w-full">
              <el-input-number
                v-model="form.quantity"
                :min="sellMin"
                class="flex-1"
                :controls="false"
                :max="maxQuantity"
                :step="form.type === 'fund' ? 0.0001 : stepForSecurity"
                :precision="form.type === 'fund' ? 4 : 0"
                :placeholder="placeholderText"
              />
              <div class="flex items-center gap-1 shrink-0">
                <template v-for="ratio in SELL_QUICK_RATIOS" :key="ratio.label">
                  <el-button
                    size="small"
                    plain
                    round
                    class="quick-ratio-btn"
                    @click="applySellQuickRatio(ratio.value)"
                  >
                    {{ ratio.label }}
                  </el-button>
                </template>
              </div>
            </div>
            <div class="text-xs" style="color: var(--text-tertiary)">
              <template v-if="form.type === 'fund'"
                >每笔最少 0.0001 份</template
              >
              <template v-else>
                每笔最少卖出 {{ sellMin }} 股/张
                <span
                  v-if="isOddLot && form.type !== 'fund'"
                  style="color: var(--color-warning)"
                  >（含碎股，可全部卖出）</span
                >
              </template>
            </div>
          </div>
        </el-form-item>

        <!-- 3. 卖出价格（仅股票显示） -->
        <el-form-item v-if="form.type !== 'fund'" label="卖出价格" prop="price">
          <el-input-number
            v-model="form.price"
            class="w-full"
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
            <div class="text-xs mt-1" style="color: var(--text-tertiary)">
              按持仓天数自动匹配费率，可手动修改
            </div>
          </el-form-item>
        </template>

        <!-- 5. 对应净值（弱化展示） -->
        <div
          v-if="form.type === 'fund'"
          class="text-xs flex items-center gap-1 mt-1 pl-[90px]"
          style="color: var(--text-tertiary)"
        >
          <span>对应净值：</span>
          <span class="font-medium" style="color: var(--text-secondary)">
            {{
              form.price !== undefined && form.price > 0
                ? form.price.toFixed(4)
                : "--"
            }}
          </span>
          <span>[{{ actualNavDate || form.trade_date || "--" }}]</span>
        </div>

        <!-- 6. 预估金额 -->
        <el-form-item label="预估金额">
          <el-input
            :model-value="sellEstimate"
            class="w-full"
            readonly
            disabled
          >
            <template #append>元</template>
          </el-input>
        </el-form-item>
      </template>
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
      <span v-if="linkedCashAccountName"
        >卖出资金将划转至：<span class="font-medium text-gray-700">{{
          linkedCashAccountName
        }}</span></span
      >
      <span v-else>未关联现金账户，资金将计入当前账户余额</span>
    </div>

    <!-- 费率查询弹窗 -->
    <el-dialog
      v-model="feeRateDialogVisible"
      title="卖出费率分布"
      width="500px"
      destroy-on-close
    >
      <el-table :data="feeRateTableData" stripe style="width: 100%">
        <el-table-column prop="range" label="持有天数" />
        <el-table-column prop="shares" label="区间份额" align="right" />
        <el-table-column prop="rate" label="卖出费率" align="right">
          <template #default="{ row }">
            {{ (row.rate * 100).toFixed(2) }}%
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button type="primary" @click="feeRateDialogVisible = false"
          >确定</el-button
        >
      </template>
    </el-dialog>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from "vue";
import { ElMessage } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { createPosition, getPositions } from "@/api/positions";
import { IconifyIconOffline } from "@/components/ReIcon";
import { LEDGER_TYPE_SHORT } from "@/constants";
import { getLedgerColor, bgFromColor } from "@/utils/ledger";
import { validateTradeOrder } from "@/api/positions";
import { getStep, SELL_QUICK_RATIOS } from "@/utils/trading";
import { estimateRedeemFee } from "@/api/funds";
import { calcFundConfirmDate } from "@/api/utils";

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
}>();

const defaultForm = () => ({
  ledger_id: null as number | null,
  positionId: null as number | null,
  symbol: "",
  name: "",
  market: "CN_A",
  type: "stock",
  quantity: undefined as number | undefined,
  price: undefined as number | undefined,
  trade_date: new Date().toISOString().slice(0, 10),
  isAfter15: false,
  notes: "",
  currency: "CNY",
  fee: 0 as number | undefined
});

const form = reactive(defaultForm());
const formRef = ref<FormInstance>();
const positionsByAccount = ref<Record<string, any[]>>({});
const selectedPosition = ref<any>(null);
const feeRateDialogVisible = ref(false);
const feeRateTableData = ref<any[]>([]);
const feeManuallyChanged = ref(false);

const confirmDate = ref("");
const actualNavDate = ref("");

const availableAccounts = computed(() =>
  props.ledgers.filter(l => positionsByAccount.value[l.name]?.length > 0)
);
const currentLedger = computed(
  () => props.ledgers.find(l => l.id === form.ledger_id) ?? null
);
const accountPositions = computed(() => {
  if (!currentLedger.value) return [];
  return positionsByAccount.value[currentLedger.value.name] || [];
});
const maxQuantity = computed(() => selectedPosition.value?.quantity ?? 1);
const stepForSecurity = computed(() => {
  if (!selectedPosition.value) return 1;
  return getStep({ type: form.type, market: form.market, symbol: form.symbol });
});
const sellMin = computed(() => {
  const total = maxQuantity.value;
  if (form.type === "fund") return total > 0 ? 0.0001 : 0;
  return total < stepForSecurity.value ? total : stepForSecurity.value;
});
const placeholderText = computed(() => {
  const total = maxQuantity.value;
  const unit =
    form.type === "fund" ? " 份" : form.type === "bond" ? " 张" : " 股/张";
  return `最多可卖出 ${total}${unit}`;
});
const isOddLot = computed(() => {
  const total = maxQuantity.value;
  return total > 0 && total < stepForSecurity.value;
});
const sellEstimate = computed(() => {
  const q = form.quantity || 0;
  const p = form.price || 0;
  const f = form.fee || 0;
  const amount = q * p - f;
  return amount > 0 ? amount.toFixed(2) : "-";
});
const disabledDate = (time: Date) =>
  time.getTime() > new Date().setHours(0, 0, 0, 0);
const linkedCashAccountName = computed(() => {
  if (!currentLedger.value?.linked_cash_ledger_id) return "";
  const cashLedger = props.ledgers.find(
    l => l.id === currentLedger.value.linked_cash_ledger_id
  );
  return cashLedger?.name || "";
});
const showIsAfter15 = computed(() => {
  const type = currentLedger.value?.ledger_type;
  if (type === "fund" || type === "bank") return true;
  if (type === "stock" && selectedPosition.value?.type === "fund") return true;
  return false;
});

// 自定义验证器：根据 form.type 动态返回错误消息
const validateQuantity = (_rule: any, value: any, callback: any) => {
  if (value === undefined || value === null || value === "") {
    callback(
      new Error(form.type === "fund" ? "请输入卖出份额" : "请输入卖出数量")
    );
  } else {
    callback();
  }
};

const rules: FormRules = {
  ledger_id: [{ required: true, message: "请选择账户", trigger: "change" }],
  positionId: [
    { required: true, message: "请选择持仓产品", trigger: "change" }
  ],
  quantity: [{ validator: validateQuantity, trigger: "blur" }],
  trade_date: [{ required: true, message: "请选择日期", trigger: "change" }]
};

// emits 定义中增加


async function fetchPositionsByAccount() {
  try {
    const res = await getPositions({ group_by: "account" });
    positionsByAccount.value = (res as any)?.data ?? {};
    // 提取有持仓的 ledger_id
    const ids = new Set<number>();
    for (const accountName in positionsByAccount.value) {
      const positions = positionsByAccount.value[accountName];
      positions.forEach((p: any) => {
        if (p.ledger_id) ids.add(p.ledger_id);
      });
    }
    emit('positions-loaded', Array.from(ids));
  } catch {
    positionsByAccount.value = {};
    emit('positions-loaded', []);
  }
}

function applySellQuickRatio(ratio: number) {
  const total = maxQuantity.value;
  if (ratio === 1) {
    form.quantity = total;
    return;
  }
  if (form.type === "fund") {
    form.quantity = parseFloat((total * ratio).toFixed(4));
    return;
  }
  const step = stepForSecurity.value;
  let target = Math.floor((total * ratio) / step) * step;
  if (target < step && total >= step) target = step;
  form.quantity = Math.min(target, total);
}

function onAccountChange(_ledgerId: number) {
  form.positionId = null;
  selectedPosition.value = null;
}

function onPositionSelect(positionId: number) {
  const pos = accountPositions.value.find((p: any) => p.id === positionId);
  if (!pos) return;
  selectedPosition.value = pos;
  form.symbol = pos.symbol;
  form.name = pos.name;
  form.market = pos.market;
  form.type = pos.type;
  form.currency = pos.currency;
  form.price = pos.current_price ?? pos.avg_price;
  form.quantity = undefined;
  form.fee = 0;
  feeManuallyChanged.value = false;
  confirmDate.value = "";
  actualNavDate.value = "";
  calculateFeeAndRate();
}

async function fetchConfirmAndNavDate() {
  if (!selectedPosition.value || form.type !== "fund" || !form.trade_date) {
    confirmDate.value = "";
    actualNavDate.value = "";
    return;
  }
  try {
    const res = await calcFundConfirmDate({
      trade_date: form.trade_date,
      fund_type: "domestic",
      is_after_15: form.isAfter15
    });
    const data = (res as any)?.data;
    if (data) {
      actualNavDate.value = data.actual_trade_date;
      confirmDate.value = data.confirm_date;
    }
  } catch (e) {
    confirmDate.value = "";
    actualNavDate.value = "";
  }
}

const fetchFundFeeRules = async (
  positionId: number,
  tradeDate: string,
  shares: number
) => {
  const res = await estimateRedeemFee({
    position_id: positionId,
    shares: shares,
    sell_date: tradeDate
  });
  return {
    total_fee: res.data?.total_fee || 0,
    details: (res.data?.details || []).map((r: any) => ({
      range: r.range,
      shares: (r.shares || 0).toFixed(2),
      rate: r.rate
    }))
  };
};

const calculateFeeAndRate = async () => {
  if (!selectedPosition.value || form.type !== "fund" || !form.trade_date) {
    form.fee = 0;
    feeRateTableData.value = [];
    return;
  }
  const buyDate = selectedPosition.value.confirm_date;
  if (!buyDate) {
    feeRateTableData.value = [];
    return;
  }

  try {
    const { total_fee, details } = await fetchFundFeeRules(
      selectedPosition.value.id,
      form.trade_date,
      form.quantity || 0
    );
    if (!feeManuallyChanged.value) {
      form.fee = total_fee;
    }
    feeRateTableData.value = details;
  } catch (e) {
    console.warn("费率查询失败", e);
    feeRateTableData.value = [];
  }
};

function onFeeManualChange() {
  feeManuallyChanged.value = true;
}

const openFeeRateDialog = async () => {
  if (!selectedPosition.value) {
    ElMessage.info("请先选择持仓");
    return;
  }
  if (!selectedPosition.value.confirm_date) {
    ElMessage.warning(
      "该持仓缺少买入确认日期，无法查询费率。请先在持仓详情中补充确认日期。"
    );
    return;
  }
  try {
    await calculateFeeAndRate();
    feeRateDialogVisible.value = true;
  } catch (e) {
    ElMessage.error("获取费率分布失败，请检查网络或稍后重试");
  }
};

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

  const body = {
    symbol: form.symbol,
    name: form.name,
    op_type: "sell",
    position_id: form.positionId,
    market: form.market || "CN_A",
    type: form.type,
    ledger_id: form.ledger_id,
    account_name: currentLedger.value?.name || "",
    quantity,
    avg_price: form.price,
    amount: quantity * form.price,
    currency: form.currency,
    trade_date: form.trade_date,
    confirm_date: form.type === "fund" ? null : form.trade_date,
    fee: form.fee || 0,
    notes: form.notes,
    allocation: null,
    isAfter15: form.isAfter15
  };

  try {
    await createPosition(body);
    ElMessage.success("记账成功");
    emit("submit-success");
  } catch (e: any) {
    // 保持原有错误处理
  }
}

function resetForm() {
  Object.assign(form, defaultForm());
  selectedPosition.value = null;
  positionsByAccount.value = {};
  feeManuallyChanged.value = false;
  formRef.value?.resetFields();

  if (props.hideAccountSelect && props.defaultLedgerId) {
    form.ledger_id = props.defaultLedgerId;
  }
}

watch(
  [
    () => form.trade_date,
    () => form.isAfter15,
    () => form.quantity,
    () => form.price
  ],
  () => {
    fetchConfirmAndNavDate();
    calculateFeeAndRate();
  }
);

watch(
  () => props.defaultLedgerId,
  newVal => {
    if (props.hideAccountSelect && newVal) {
      form.ledger_id = newVal;
    }
  },
  { immediate: true }
);

onMounted(() => {
  fetchPositionsByAccount();
});

defineExpose({ handleSubmit, resetForm });
</script>

<style scoped>
.text-xs {
  font-size: 0.75rem;
}
.quick-ratio-btn {
  transform-origin: center;
  transition:
    transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1),
    border-color 0.2s,
    color 0.2s;
  border-color: var(--border-default);
  color: var(--text-secondary);
}
.quick-ratio-btn:hover {
  border-color: var(--color-primary) !important;
  color: var(--color-primary) !important;
  background-color: var(--color-primary-10) !important;
}
.quick-ratio-btn:active {
  transform: scale(0.92) !important;
}
</style>
