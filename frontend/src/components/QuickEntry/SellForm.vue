<!-- src/components/QuickEntry/SellForm.vue -->
<template>
  <el-form
    ref="formRef"
    :model="form"
    :rules="rules"
    label-width="90px"
    size="large"
  >
    <!-- 账户选择 -->
    <el-form-item label="选择账户" prop="ledger_id">
      <el-select
        v-model="form.ledger_id"
        class="w-full"
        style="width: 100%"
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
        <a class="text-[var(--color-primary)] cursor-pointer" @click="goToInventory">全面盘点</a>
        导入或录入持仓。
      </div>
    </el-form-item>

    <!-- 选择持仓 -->
    <template v-if="form.ledger_id">
      <el-form-item label="选择持仓" prop="positionId">
        <el-select
          v-model="form.positionId"
          class="w-full"
          style="width: 100%"
          filterable
          placeholder="选择资产"
          @change="onPositionSelect"
        >
          <el-option
            v-for="pos in accountPositions"
            :key="pos.id"
            :label="`${pos.name || pos.symbol} (可用 ${pos.quantity})`"
            :value="pos.id"
          />
        </el-select>
      </el-form-item>

      <template v-if="form.positionId">
        <!-- 卖出数量 -->
        <el-form-item
          :label="form.type === 'fund' ? '卖出份额' : '卖出数量'"
          prop="quantity"
        >
          <el-input-number
            v-model="form.quantity"
            :min="sellMin"
            class="w-full"
            style="width: 100%"
            :controls="false"
            :max="maxQuantity"
            :step="form.type === 'fund' ? 0.0001 : stepForSecurity"
            :precision="form.type === 'fund' ? 4 : 0"
            :placeholder="placeholderText"
          />
          <!-- 快捷比例 -->
          <div class="flex items-center gap-2 mt-2">
            <template v-for="ratio in SELL_QUICK_RATIOS" :key="ratio.label">
              <el-button size="small" plain @click="applySellQuickRatio(ratio.value)">
                {{ ratio.label }}
              </el-button>
            </template>
          </div>
          <div class="text-xs mt-2" style="color: var(--text-tertiary)">
            <template v-if="form.type === 'fund'"> 每笔最少 0.0001 份 </template>
            <template v-else>
              每笔最少卖出 {{ sellMin }} 股/张
              <span
                v-if="isOddLot && form.type !== 'fund'"
                style="color: var(--color-warning)"
              >
                （含碎股，可全部卖出）
              </span>
            </template>
          </div>
        </el-form-item>

        <!-- 卖出价格 -->
        <el-form-item label="卖出价格" prop="price">
          <el-input-number
            v-model="form.price"
            class="w-full"
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

        <!-- 预估金额 -->
        <el-form-item label="预估金额">
          <el-input :model-value="sellEstimate" class="w-full" style="width: 100%" readonly disabled>
            <template #append>元</template>
          </el-input>
        </el-form-item>
      </template>
    </template>

    <!-- 交易日期与下单时间 -->
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
        <!-- 🔥 修复6：卖出时，根据账户类型提前判断 15:00 开关显示 -->
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
        <!-- 👇 修改这里：改成和 BuyForm 一致的确认日提示 -->
        <span v-if="form.isAfter15 && selectedPosition?.type === 'fund'">
          15:00后赎回，按下一交易日（T+1）净值计算 · 预计确认日：{{ confirmDate || '计算中...' }}
        </span>
        <span v-else-if="!form.isAfter15 && selectedPosition?.type === 'fund'">
          预计确认日：{{ confirmDate || '计算中...' }}
        </span>
      </div>
    </el-form-item>

    <!-- 备注 -->
    <el-form-item label="备注">
      <el-input
        v-model="form.notes"
        type="textarea"
        :rows="2"
        placeholder="补充交易理由（选填）"
        style="width: 100%"
      />
    </el-form-item>

    <!-- 资金流向提示 -->
    <div
      class="mt-2 mb-4 p-3 bg-gray-50 rounded-lg text-sm flex items-center gap-2"
      style="color: var(--text-secondary)"
    >
      <IconifyIconOffline icon="ep:info-filled" class="text-gray-400" />
      <span v-if="linkedCashAccountName">
        卖出资金将划转至：<span class="font-medium text-gray-700">{{
          linkedCashAccountName
        }}</span>
      </span>
      <span v-else>未关联现金账户，资金将计入当前账户余额</span>
    </div>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch} from "vue";
import { ElMessage } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { createPosition, getPositions } from "@/api/positions";
import { IconifyIconOffline } from "@/components/ReIcon";
import { LEDGER_TYPE_SHORT } from "@/constants";
import { getLedgerColor, bgFromColor } from "@/utils/ledger";
import { calcFundConfirmDate } from "@/api/utils";
import {
  getStep,
  supportsOneShare,
  SELL_QUICK_RATIOS,
} from "@/utils/trading";

const props = defineProps<{ ledgers: any[] }>();
const emit = defineEmits<{
  (e: "submit-success"): void;
  (e: "close"): void;
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
});

const form = reactive(defaultForm());
const formRef = ref<FormInstance>();
// ── 确认日计算 ──
const confirmDate = ref("");

const positionsByAccount = ref<Record<string, any[]>>({});
const selectedPosition = ref<any>(null);

// 可用账户列表
const availableAccounts = computed(() =>
  props.ledgers.filter(
    (l) => positionsByAccount.value[l.name]?.length > 0
  )
);

const currentLedger = computed(
  () => props.ledgers.find((l) => l.id === form.ledger_id) ?? null
);

const accountPositions = computed(() => {
  if (!currentLedger.value) return [];
  return positionsByAccount.value[currentLedger.value.name] || [];
});

const maxQuantity = computed(() => selectedPosition.value?.quantity ?? 1);

const stepForSecurity = computed(() => {
  if (!selectedPosition.value) return 1;
  return getStep({
    type: form.type,
    market: form.market,
    symbol: form.symbol,
  });
});

const sellMin = computed(() => {
  const total = maxQuantity.value;
  if (form.type === "fund") return total > 0 ? 0.0001 : 0;
  return total < stepForSecurity.value ? total : stepForSecurity.value;
});

const placeholderText = computed(() => {
  const total = maxQuantity.value;
  const unit =
    form.type === "fund"
      ? " 份"
      : form.type === "bond"
      ? " 张"
      : " 股/张";
  return `最多可卖出 ${total}${unit}`;
});

const isOddLot = computed(() => {
  const total = maxQuantity.value;
  return total > 0 && total < stepForSecurity.value;
});

const sellEstimate = computed(() => {
  const q = form.quantity || 0;
  const p = form.price || 0;
  return q * p > 0 ? (q * p).toFixed(2) : "-";
});

const disabledDate = (time: Date) => {
  return time.getTime() > new Date().setHours(0,0,0,0);
};

const linkedCashAccountName = computed(() => {
  if (!currentLedger.value?.linked_cash_ledger_id) return "";
  const cashLedger = props.ledgers.find(
    (l) => l.id === currentLedger.value.linked_cash_ledger_id
  );
  return cashLedger?.name || "";
});

// 🔥 修复6：卖出时提前判断 15:00 逻辑
const showIsAfter15 = computed(() => {
  const type = currentLedger.value?.ledger_type;
  // 银行/基金账户天然买基金，直接显示。证券账户只有在持仓是基金时显示。
  if (type === 'fund' || type === 'bank') return true;
  if (type === 'stock' && selectedPosition.value?.type === 'fund') return true;
  return false;
});

const rules: FormRules = {
  ledger_id: [{ required: true, message: "请选择账户", trigger: "change" }],
  quantity: [{ required: true, message: "请输入卖出数量", trigger: "blur" }],
  price: [{ required: true, message: "请输入卖出价格", trigger: "blur" }],
  trade_date: [{ required: true, message: "请选择日期", trigger: "change" }],
};

async function fetchPositionsByAccount() {
  try {
    const res = await getPositions({ group_by: "account" });
    positionsByAccount.value = (res as any)?.data ?? {};
  } catch {
    positionsByAccount.value = {};
  }
}

onMounted(() => {
  fetchPositionsByAccount();
});

function onAccountChange(ledgerId: number) {
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
  fetchConfirmDate();
}

async function fetchConfirmDate() {
  if (selectedPosition.value?.type !== "fund" || !form.trade_date) {
    confirmDate.value = "";
    return;
  }
  try {
    const res = await calcFundConfirmDate({
      trade_date: form.trade_date,
      fund_type: "domestic",
      is_after_15: form.isAfter15,
    });
    confirmDate.value = (res as any)?.data ?? "";
  } catch {
    confirmDate.value = "";
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

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  const quantity = form.quantity!;
  const price = form.price!;
  if (quantity <= 0) {
    ElMessage.error("请输入卖出数量");
    return;
  }
  if (price <= 0) {
    ElMessage.error("请输入卖出价格");
    return;
  }

  const body = {
    symbol: form.symbol,
    name: form.name,
    op_type: "sell",
    position_id: form.positionId,
    market: form.market,
    type: form.type,
    ledger_id: form.ledger_id,
    account_name: currentLedger.value?.name || "",
    quantity,
    avg_price: price,
    amount: quantity * price,
    currency: form.currency,
    confirm_date: form.type === "fund" ? confirmDate.value : form.trade_date,
    trade_date: form.trade_date,
    fee: 0,
    notes: form.notes,
    allocation: null,
    isAfter15: form.isAfter15,
  };

  try {
    await createPosition(body);
    ElMessage.success("记账成功");
    emit("submit-success");
  } catch (e: any) {
    ElMessage.error(e?.message || "记账失败");
  }
}

function resetForm() {
  Object.assign(form, defaultForm());
  selectedPosition.value = null;
  positionsByAccount.value = {};
  confirmDate.value = "";
  formRef.value?.resetFields();
}

function goToInventory() {
  emit("close");
}

// 监听日期和 15:00 切换，重新计算确认日
watch(
  [() => form.trade_date, () => form.isAfter15],
  () => {
    fetchConfirmDate();
  }
);

defineExpose({ handleSubmit, resetForm });
</script>

<style scoped>
.text-xs {
  font-size: 0.75rem;
}
</style>
