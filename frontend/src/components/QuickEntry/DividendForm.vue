<template>
  <el-form
    ref="formRef"
    :model="form"
    :rules="rules"
    label-width="90px"
    size="large"
    class="flex flex-col gap-5"
  >
    <!-- 选择持仓（分红/送股必须落到已有持仓，不能新建） -->
    <el-form-item label="选择持仓" prop="positionId">
      <el-select
        v-if="showPositionSelect"
        :key="positionSelectKey"
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
            <span class="truncate" :style="{ color: 'var(--text-primary)' }">{{
              pos.name || pos.symbol
            }}</span>
            <span
              class="text-xs whitespace-nowrap"
              :style="{ color: 'var(--text-tertiary)' }"
            >
              可用 {{ Number(pos.quantity).toFixed(2) }} 份
            </span>
          </div>
        </el-option>
      </el-select>
      <div
        v-if="accountPositions.length === 0"
        class="text-xs mt-1"
        style="color: var(--text-tertiary)"
      >
        当前账户无可用持仓，无法登记。
      </div>
    </el-form-item>

    <template v-if="form.positionId">
      <!-- 交易日期 -->
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
          <span
            v-if="
              showIsAfter15 && selectedPosition?.type === 'fund' && confirmDate
            "
            >15:00后红利再投按下一交易日（T+1）净值申购 · 预计确认日：{{
              confirmDate
            }}</span
          >
        </div>
      </el-form-item>

      <!-- 现金分红：分红金额 -->
      <el-form-item
        v-if="mode === 'dividend'"
        label="分红金额"
        prop="dividendAmount"
      >
        <el-input-number
          v-model="form.dividendAmount"
          style="width: 100%"
          :controls="false"
          :precision="2"
          :min="0"
          placeholder="输入分红到账金额"
        />
        <div class="text-xs mt-1" style="color: var(--text-tertiary)">
          现金分红直接入账，不改变持仓份额
        </div>
      </el-form-item>

      <!-- 红利再投：红利金额 + 净值 + 自动申购份额 -->
      <template v-else-if="mode === 'dividend_reinvest'">
        <el-form-item label="红利金额" prop="dividendAmount">
          <el-input-number
            v-model="form.dividendAmount"
            style="width: 100%"
            :controls="false"
            :precision="2"
            :min="0"
            placeholder="输入红利再投金额"
          />
        </el-form-item>
        <el-form-item label="净值" prop="nav">
          <el-input-number
            v-model="form.nav"
            style="width: 100%"
            :controls="false"
            :precision="4"
            :min="0"
            placeholder="输入申购净值"
          />
        </el-form-item>
        <el-form-item label="申购份额">
          <el-input
            :model-value="computedShares"
            class="w-full"
            readonly
            disabled
          >
            <template #append>份</template>
          </el-input>
          <div class="text-xs mt-1" style="color: var(--text-tertiary)">
            按「红利金额 ÷ 净值」自动计算
          </div>
        </el-form-item>
      </template>

      <!-- 送股/拆分：增加的份额（零成本，仅稀释均价） -->
      <template v-else>
        <el-form-item label="送股/拆分份额" prop="splitQuantity">
          <el-input-number
            v-model="form.splitQuantity"
            style="width: 100%"
            :controls="false"
            :precision="4"
            :min="0"
            placeholder="输入送股/拆分增加的份额"
          />
          <div class="text-xs mt-1" style="color: var(--text-tertiary)">
            送股/拆分直接增加持仓份额，成本不变，持仓均价被自动稀释
          </div>
        </el-form-item>
      </template>

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
    </template>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, nextTick } from "vue";
import { ElMessage } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { getPositionsGroupedByAccount } from "@/api/positions";
import { usePositionSubmit } from "@/composables/usePositionSubmit";
import { useFundTradeDate } from "@/composables/useFundTradeDate";
import type { Position } from "@/api/types";

const props = defineProps<{
  ledgers: any[];
  hideAccountSelect?: boolean;
  defaultLedgerId?: number | null;
  mode: "dividend" | "dividend_reinvest" | "split";
}>();
const emit = defineEmits<{
  (e: "submit-success"): void;
}>();

const defaultForm = () => ({
  positionId: null as number | null,
  dividendAmount: undefined as number | undefined,
  nav: undefined as number | undefined,
  splitQuantity: undefined as number | undefined,
  trade_date: new Date().toISOString().slice(0, 10),
  isAfter15: false,
  notes: ""
});

const positionSelectKey = ref(0);
const showPositionSelect = ref(true);
const form = reactive(defaultForm());
const formRef = ref<FormInstance>();
const positionsByAccount = ref<Record<string, Position[]>>({});
const selectedPosition = ref<any>(null);

const {
  confirmDate,
  calcConfirmAndNav,
  reset: resetTradeDate
} = useFundTradeDate();

const currentLedger = computed(
  () => props.ledgers.find(l => l.id === props.defaultLedgerId) ?? null
);
const accountPositions = computed(() => {
  if (!currentLedger.value) return [];
  return positionsByAccount.value[currentLedger.value.name] || [];
});
const showIsAfter15 = computed(() => selectedPosition.value?.type === "fund");
const computedShares = computed(() => {
  const amt = form.dividendAmount || 0;
  const nav = form.nav || 0;
  return amt > 0 && nav > 0 ? (amt / nav).toFixed(4) : "--";
});

const disabledDate = (time: Date) =>
  time.getTime() > new Date().setHours(0, 0, 0, 0);

const rules = computed<FormRules>(() => {
  const base: FormRules = {
    positionId: [{ required: true, message: "请选择持仓", trigger: "change" }],
    trade_date: [{ required: true, message: "请选择日期", trigger: "change" }]
  };
  if (props.mode === "split") {
    base.splitQuantity = [
      { required: true, message: "请输入送股/拆分份额", trigger: "blur" }
    ];
  } else {
    base.dividendAmount = [
      { required: true, message: "请输入金额", trigger: "blur" }
    ];
    if (props.mode === "dividend_reinvest") {
      base.nav = [{ required: true, message: "请输入净值", trigger: "blur" }];
    }
  }
  return base;
});

async function fetchPositionsByAccount() {
  try {
    const res = await getPositionsGroupedByAccount();
    positionsByAccount.value = res?.data ?? {};
  } catch {
    positionsByAccount.value = {};
  }
}

function onPositionSelect(positionId: number) {
  const pos = accountPositions.value.find(p => p.id === positionId);
  if (!pos) return;
  selectedPosition.value = pos;
  // 切换持仓后清空金额/净值，避免串用
  form.dividendAmount = undefined;
  form.nav = undefined;
  form.splitQuantity = undefined;
  resetTradeDate();
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  if (!selectedPosition.value) {
    ElMessage.error("请先选择持仓");
    return;
  }

  const isFund = selectedPosition.value.type === "fund";
  const finalConfirmDate =
    isFund && confirmDate.value && confirmDate.value.trim() !== ""
      ? confirmDate.value
      : form.trade_date;

  const body: any = {
    symbol: selectedPosition.value.symbol,
    name: selectedPosition.value.name,
    op_type: props.mode,
    position_id: form.positionId,
    market: selectedPosition.value.market || "CN_A",
    type: selectedPosition.value.type,
    ledger_id: props.defaultLedgerId,
    account_name: currentLedger.value?.name || "",
    trade_date: form.trade_date,
    confirm_date: finalConfirmDate,
    currency: selectedPosition.value.currency || "CNY",
    fee: 0,
    notes: form.notes,
    allocation: null,
    isAfter15: form.isAfter15
  };

  if (props.mode === "split") {
    body.quantity = form.splitQuantity || 0;
  } else if (props.mode === "dividend") {
    body.dividend_amount = form.dividendAmount || 0;
  } else {
    body.dividend_amount = form.dividendAmount || 0;
    body.nav = form.nav || 0;
    body.quantity =
      form.dividendAmount && form.nav ? form.dividendAmount / form.nav : 0;
  }

  const { submitPosition } = usePositionSubmit();
  const ok = await submitPosition(body);
  if (ok) emit("submit-success");
}

function resetForm() {
  Object.assign(form, defaultForm());
  selectedPosition.value = null;
  positionsByAccount.value = {};
  resetTradeDate();
  formRef.value?.resetFields();
  positionSelectKey.value++;
}

watch(
  [() => form.trade_date, () => form.isAfter15, selectedPosition],
  async () => {
    if (selectedPosition.value?.type === "fund" && form.trade_date) {
      await calcConfirmAndNav({
        tradeDate: form.trade_date,
        symbol: selectedPosition.value.symbol,
        isAfter15: form.isAfter15
      });
    }
  }
);

onMounted(fetchPositionsByAccount);

defineExpose({ handleSubmit, resetForm });
</script>

<style scoped>
.text-xs {
  font-size: 0.75rem;
}

/* 输入框通用样式（与 BuyForm/SellForm 保持一致） */
:deep(.el-input__wrapper) {
  --el-input-border-color: var(--border-default);
  --el-input-hover-border-color: var(--brand-500);
  --el-input-focus-border-color: var(--brand-700);
  --el-input-focus-shadow:
    inset 0 0 0 1px var(--brand-700), 0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);

  height: 40px;
  border-radius: var(--radius-sm);
}

:deep(.el-select .el-input__wrapper) {
  --el-input-border-color: var(--border-default);
  --el-input-hover-border-color: var(--brand-500);
  --el-input-focus-border-color: var(--brand-700);
  --el-input-focus-shadow:
    inset 0 0 0 1px var(--brand-700), 0 0 0 2px var(--bg-card),
    0 0 0 4px var(--brand-700);

  height: 40px;
  border-radius: var(--radius-sm);
}
</style>
