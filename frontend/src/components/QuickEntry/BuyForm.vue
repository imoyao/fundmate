<!-- src/components/QuickEntry/BuyForm.vue -->
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
      <div class="flex gap-2 w-full">
        <el-select
          v-model="form.ledger_id"
          class="flex-1"
          style="width: 100%"
          placeholder="选择交易账户"
          filterable
          :disabled="showQuickAdd"
          @change="onAccountSelected"
        >
          <el-option
            v-for="ledger in selectableLedgers"
            :key="ledger.id"
            :label="ledger.name"
            :value="ledger.id"
          >
            <div class="flex items-center justify-between w-full">
              <span>{{ ledger.name }}</span>
              <el-tag
                class="px-1.5 py-0.5 rounded text-xs font-medium shrink-0"
                :style="{ backgroundColor: bgFromColor(getLedgerColor(ledger.ledger_type)), color: getLedgerColor(ledger.ledger_type) }"
              >
                {{ LEDGER_TYPE_SHORT[ledger.ledger_type] || ledger.ledger_type }}
              </el-tag>
            </div>
          </el-option>
        </el-select>
        <el-button
          v-if="!showQuickAdd"
          type="primary"
          text
          @click="showQuickAdd = true"
        >
          <IconifyIconOffline icon="ep:plus" />
        </el-button>
      </div>

      <div v-if="selectableLedgers.length === 0 && !showQuickAdd" class="text-xs mt-1" style="color: var(--text-tertiary)">
        暂无账户，点击右侧 + 按钮快速创建
      </div>

      <!-- 极简创建账户 -->
      <div v-if="showQuickAdd" class="quick-add-account mt-3 p-3 border rounded-lg bg-gray-50">
        <el-input
          v-model="newAccountName"
          placeholder="输入账户名称"
          size="small"
          @keyup.enter="quickCreateAccount"
        />
        <el-select v-model="newAccountType" class="w-full mt-2" size="small" placeholder="选择账户类型">
          <el-option
            v-for="opt in quickAddTypeOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <div class="flex justify-end gap-2 mt-2">
          <el-button size="small" @click="resetQuickAdd">取消</el-button>
          <el-button
            size="small"
            type="primary"
            :loading="creatingAccount"
            :disabled="!newAccountName.trim() || !newAccountType"
            @click="quickCreateAccount"
          >
            创建并选择
          </el-button>
        </div>
      </div>
    </el-form-item>

    <!-- 证券搜索 -->
    <el-form-item :label="searchLabel" prop="symbol">
      <el-select
        v-model="selectedSecurityOption"
        value-key="symbol"
        remote
        filterable
        reserve-keyword
        :placeholder="searchPlaceholder"
        :remote-method="remoteSearch"
        :loading="searchLoading"
        @change="onSecuritySelected"
        clearable
        class="w-full"
        style="width: 100%"
      >
        <el-option
          v-for="item in securityOptions"
          :key="item.symbol"
          :label="`${item.symbol} ${item.name} (${item.type_label || item.type})`"
          :value="item"
        />
        <template #empty>
          <div class="text-center py-4 text-sm" style="color: var(--text-tertiary)">
            <template v-if="!searchLoading">
              {{ emptyHint }}
            </template>
          </div>
        </template>
      </el-select>
    </el-form-item>

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
        <!-- 🔥 修复3：根据账户类型或当前选择的产品动态显示 -->
        <el-radio-group v-if="showIsAfter15" v-model="form.isAfter15" size="small">
          <el-radio-button :value="false">15:00前</el-radio-button>
          <el-radio-button :value="true">15:00后</el-radio-button>
        </el-radio-group>
      </div>
      <div class="text-xs mt-1" style="color: var(--text-tertiary)">
        <span v-if="isTradingDay === false" style="color: var(--color-warning)">所选日期非交易日，请确认 · </span>
        <span v-if="form.isAfter15 && selectedSecurityOption?.type === 'fund'">
          预计确认日：{{ confirmDate || '计算中...' }}
        </span>
      </div>
    </el-form-item>

    <!-- 成交价格 -->
    <el-form-item
      :label="selectedSecurityOption?.type === 'fund' ? '单位净值' : '成交价格'"
      prop="price"
    >
      <el-input-number
        v-model="form.price"
        class="w-full"
        style="width: 100%"
        :controls="false"
        :min="0"
        :step="0.01"
        :precision="selectedSecurityOption?.type === 'fund' ? 4 : 2"
        :placeholder="selectedSecurityOption?.type === 'fund' ? '基金单位净值' : '每股/张成交价'"
      />
      <div class="text-xs mt-1" style="color: var(--text-tertiary)">
        <template v-if="selectedSecurityOption?.type === 'fund'">
          后期将自动获取基金净值，当前请手动输入
        </template>
        <template v-else>
          输入实际成交价，系统将根据金额自动计算份额（已扣除手续费）
        </template>
      </div>
    </el-form-item>

    <!-- 买入方式：金额/份额切换 -->
    <el-form-item label="买入方式" prop="amountOrQuantity">
      <el-input v-model="amountOrQuantity" placeholder="输入金额或份额" class="w-full" style="width: 100%">
        <template #prepend>
          <el-select v-model="amountMode" style="width: 110px" @change="onAmountModeChange">
            <el-option label="金额" value="amount" />
            <el-option label="份额" value="quantity" />
          </el-select>
        </template>
        <template #append>
          <el-tooltip
            :content="amountMode === 'amount' ? '输入金额，自动计算份额' : '输入份额，自动计算金额'"
            placement="top"
          >
            <IconifyIconOffline icon="ep:info-filled" class="text-gray-500" />
          </el-tooltip>
        </template>
      </el-input>
      <div v-if="form.price > 0" class="text-xs mt-1" style="color: var(--text-secondary)">
        {{ amountMode === 'amount' ? `预估份额：约 ${computedQuantity.toFixed(2)} 份` : `预估金额：¥${computedAmount.toFixed(2)}` }}
      </div>
    </el-form-item>

    <!-- 手续费 -->
    <el-form-item v-if="selectedSecurityOption?.type === 'fund'" label="手续费" prop="fee">
      <el-input v-model="form.fee" placeholder="0.00" class="w-full" style="width: 100%">
        <template #prepend>
          <el-select v-model="fundFeeDiscount" style="width: 110px" @change="onFundFeeDiscountChange">
            <el-option label="原价" :value="1.0" />
            <el-option label="1折" :value="0.1" />
            <el-option label="0.1折" :value="0.01" />
            <el-option label="免申购费" :value="0" />
          </el-select>
        </template>
        <template #append>元</template>
      </el-input>
      <span class="text-xs text-gray-500 mt-1">费率已根据账户预设填充，可手动修改</span>
    </el-form-item>
    <el-form-item v-else label="手续费" prop="fee">
      <el-input-number
        v-model="form.fee"
        class="w-full"
        style="width: 100%"
        :controls="false"
        :min="0"
        :precision="2"
        placeholder="0.00"
      />
      <span class="text-xs text-gray-500 mt-1">按账户默认费率预填，可手动修改</span>
    </el-form-item>

    <!-- 配置目标 -->
    <el-form-item label="配置目标" prop="allocation">
      <el-select v-model="form.allocation" class="w-full" style="width: 100%" placeholder="选择配置目标">
        <el-option
          v-for="opt in ALLOCATION_OPTIONS"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
    </el-form-item>

    <!-- 备注 -->
    <el-form-item label="备注">
      <el-input v-model="form.notes" type="textarea" :rows="2" placeholder="补充交易理由（选填）" style="width: 100%" />
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from "vue";
import { ElMessage } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { createPosition } from "@/api/positions";
import { createLedger as createLedgerApi } from "@/api/ledger";
import { searchSecurities } from "@/api/securities";
import { searchFunds } from "@/api/funds";
import { checkTradingDay, calcFundConfirmDate } from "@/api/utils";
import { IconifyIconOffline } from "@/components/ReIcon";
import { ALLOCATION_OPTIONS, LEDGER_TYPE_SHORT, LEDGER_TYPE_OPTIONS } from "@/constants";
import { getLedgerColor, bgFromColor } from "@/utils/ledger";
import { getStep, supportsOneShare, getPrecision, DEFAULT_SUB_RATE } from "@/utils/trading";

// ── Props & Emits ──
const props = defineProps<{ ledgers: any[] }>();
const emit = defineEmits<{
  (e: "submit-success"): void;
  (e: "accounts-changed"): void;
}>();

// ── 表单默认值 ──
const defaultForm = () => ({
  ledger_id: null as number | null,
  symbol: "",
  name: "",
  market: "CN_A",
  type: "stock",
  quantity: 0,
  price: undefined as number | undefined,
  trade_date: new Date().toISOString().slice(0, 10),
  confirm_date: "",
  fee: undefined as number | undefined,
  allocation: "longterm",
  notes: "",
  isAfter15: false,
  currency: "CNY",
});

const form = reactive(defaultForm());
const formRef = ref<FormInstance>();

// 极简账户创建
const showQuickAdd = ref(false);
const newAccountName = ref("");
const newAccountType = ref("");
const creatingAccount = ref(false);

const quickAddTypeOptions = LEDGER_TYPE_OPTIONS.filter(
  (opt) => opt.value !== "property"
);

// 搜索状态
const searchLoading = ref(false);
const securityOptions = ref<any[]>([]);
const selectedSecurityOption = ref<any>(null);

// 金额/份额模式
const amountMode = ref<"amount" | "quantity">("amount");
const amountOrQuantity = ref<string | number>("");

// 基金手续费折扣
const fundFeeDiscount = ref(0.1);

// 交易日与确认日
const isTradingDay = ref<boolean | null>(null);
const confirmDate = ref("");

// ── 计算属性 ──
const selectableLedgers = computed(() =>
  props.ledgers.filter((l) => l.ledger_type !== "property")
);

const currentLedger = computed(() =>
  props.ledgers.find((l) => l.id === form.ledger_id) ?? null
);

// 完全替代手动同步 account_name
const accountName = computed(() => currentLedger.value?.name ?? "");

const searchLabel = computed(() => {
  const t = currentLedger.value?.ledger_type;
  return t === "fund" || t === "bank" ? "基金" : "证券";
});

const searchPlaceholder = computed(() => {
  const t = currentLedger.value?.ledger_type;
  return t === "fund" || t === "bank"
    ? "输入基金代码或名称"
    : "输入股票/ETF代码或名称";
});

const emptyHint = computed(() => {
  return `还没有${searchLabel.value}持仓？去「全面盘点」导入交割单吧 >`;
});

// 🔥 修复3：15:00显示逻辑（无需依赖选择证券，根据账户类型提前判定）
const showIsAfter15 = computed(() => {
  const type = currentLedger.value?.ledger_type;
  // 银行/基金账户天然买基金，直接显示。证券账户只有在搜到了基金后才显示。
  if (type === 'fund' || type === 'bank') return true;
  if (type === 'stock' && selectedSecurityOption.value?.type === 'fund') return true;
  return false;
});

const computedQuantity = computed(() => {
  if (!form.price || form.price <= 0) return 0;
  if (amountMode.value === "amount") {
    const net = Math.max(0, Number(amountOrQuantity.value || 0) - (form.fee || 0));
    return net / form.price;
  }
  return Number(amountOrQuantity.value || 0);
});

const computedAmount = computed(() => {
  if (amountMode.value === "quantity") {
    const q = Number(amountOrQuantity.value || 0);
    return q * (form.price || 0) + (form.fee || 0);
  }
  return Number(amountOrQuantity.value || 0);
});

// ── 规则 ──
const rules: FormRules = {
  ledger_id: [{ required: true, message: "请选择账户", trigger: "change" }],
  symbol: [{ required: true, message: "请选择买入产品", trigger: "change" }],
  trade_date: [{ required: true, message: "请选择日期", trigger: "change" }],
  price: [{ required: true, message: "请输入成交价格", trigger: "blur" }],
  allocation: [{ required: true, message: "请选择配置目标", trigger: "change" }],
};

// 禁用今天之后的日期
const disabledDate = (time: Date) => {
  // new Date().setHours(0,0,0,0) 确保今天这整一天都可以正常选择，只有明天及以后无法选择
  return time.getTime() > new Date().setHours(0,0,0,0);
};

// ── 方法 ──

function onAccountSelected() {
  applyFeePreset();
}

// 🔥 修复2：切换账户时清理产品逻辑
watch(() => form.ledger_id, (newVal, oldVal) => {
  if (!oldVal && !newVal) return;
  const oldLedger = props.ledgers.find(l => l.id === oldVal);
  const newLedger = props.ledgers.find(l => l.id === newVal);

  // 跨类型切换（股票↔基金/银行）时，强制清除已选产品
  if (oldLedger?.ledger_type !== newLedger?.ledger_type) {
    form.symbol = '';
    form.name = '';
    form.market = 'CN_A';
    form.type = 'stock';
    form.price = undefined;
    amountOrQuantity.value = '';
    selectedSecurityOption.value = null;
    securityOptions.value = [];
  }
  // 同类型切换时，仅更新费率，保留产品
  applyFeePreset();
});

async function remoteSearch(query: string) {
  if (!query) { securityOptions.value = []; return; }
  searchLoading.value = true;
  try {
    const type = currentLedger.value?.ledger_type ?? "";
    let opts: any[] = [];
    if (type === "fund" || type === "bank") {
      const res = await searchFunds(query);
      const arr = Array.isArray(res) ? res : (res as any)?.data ?? [];
      opts = arr.map((f: any) => ({
        symbol: f.code,
        name: f.name,
        market: "CN_A",
        type: "fund",
        type_label: "基金",
        subscription_rate: f.subscription_rate || DEFAULT_SUB_RATE,
      }));
    } else {
      const res = await searchSecurities(query);
      const arr = Array.isArray(res) ? res : (res as any)?.data ?? [];
      const typeLabels: Record<string, string> = { stock: "股票", bond: "可转债", etf: "ETF" };
      opts = arr.map((s: any) => ({
        symbol: s.symbol,
        name: s.name,
        market: s.market,
        type: s.type,
        type_label: typeLabels[s.type] || s.type,
      }));
    }

    if (opts.length === 0 && query.trim()) {
      const manualType = type === "fund" || type === "bank" ? "fund" : "stock";
      opts = [
        {
          symbol: query.trim().toUpperCase(),
          name: query.trim(),
          market: "CN_A",
          type: manualType,
          type_label: "手动输入",
          is_manual: true,
        },
      ];
    }
    securityOptions.value = opts;
  } catch {
    if (query.trim()) {
      const manualType = currentLedger.value?.ledger_type === "fund" ? "fund" : "stock";
      securityOptions.value = [
        {
          symbol: query.trim().toUpperCase(),
          name: query.trim(),
          market: "CN_A",
          type: manualType,
          type_label: "手动输入",
          is_manual: true,
        },
      ];
    }
    ElMessage.warning("搜索服务暂不可用，已提供手动输入选项");
  } finally {
    searchLoading.value = false;
  }
}

function onSecuritySelected(option: any) {
  if (!option) {
    form.symbol = "";
    form.name = "";
    form.market = "CN_A";
    form.type = "stock";
    selectedSecurityOption.value = null;
    return;
  }
  form.symbol = option.symbol;
  form.name = option.name;
  form.market = option.market || "CN_A";
  form.type = option.type;
  amountMode.value = option.type === "fund" ? "amount" : "quantity";
  selectedSecurityOption.value = option;
  applyFeePreset();
}

function applyFeePreset() {
  const ledger = currentLedger.value;
  if (!ledger) { form.fee = 0; return; }
  const config = parseFeeConfig(ledger.fee_config);
  const safeAmount = Number(amountOrQuantity.value || 0);
  const safePrice = form.price || 0;

  if (ledger.ledger_type === "stock") {
    const estAmount = amountMode.value === "amount" ? safeAmount : safeAmount * safePrice;
    form.fee = estAmount * (config?.commission?.rate ?? 0.00025);
  } else if (ledger.ledger_type === "fund" || ledger.ledger_type === "bank") {
    fundFeeDiscount.value = config?.subscription_discount ?? 0.1;
    const fundRate = selectedSecurityOption.value?.subscription_rate ?? DEFAULT_SUB_RATE;
    const estAmount = amountMode.value === "amount" ? safeAmount : safeAmount * safePrice;
    form.fee = estAmount * fundRate * fundFeeDiscount.value;
  } else {
    form.fee = 0;
  }
}

function parseFeeConfig(raw: any): any {
  if (!raw) return null;
  try {
    return typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch {
    return null;
  }
}

function onAmountModeChange() {
  amountOrQuantity.value = 0;
}

function onFundFeeDiscountChange() {
  const fundRate = selectedSecurityOption.value?.subscription_rate ?? DEFAULT_SUB_RATE;
  form.fee = computedAmount.value * fundRate * fundFeeDiscount.value;
}

async function quickCreateAccount() {
  const name = newAccountName.value.trim();
  const type = newAccountType.value;
  if (!name || !type) return;
  creatingAccount.value = true;
  try {
    let feeConfig: any = undefined;
    if (type === "fund") feeConfig = { subscription_discount: 0.1 };
    else if (type === "stock") feeConfig = { commission: { rate: 0.00025, min: null } };

    const payload: any = { name, ledger_type: type };
    if (feeConfig) payload.fee_config = feeConfig;
    await createLedgerApi(payload);
    emit("accounts-changed");
    ElMessage.success(`已创建账户「${name}」`);
    resetQuickAdd();
  } catch (e: any) {
    ElMessage.error(e?.message || "创建账户失败");
  } finally {
    creatingAccount.value = false;
  }
}

function resetQuickAdd() {
  showQuickAdd.value = false;
  newAccountName.value = "";
  newAccountType.value = "";
}

// ── 交易日与确认日 ──
async function fetchTradingDay() {
  if (selectedSecurityOption.value?.type === "fund" || !form.trade_date) {
    isTradingDay.value = null;
    return;
  }
  try {
    const res = await checkTradingDay(form.trade_date);
    isTradingDay.value = (res as any)?.data?.is_trading_day ?? false;
  } catch {
    isTradingDay.value = null;
  }
}

async function fetchConfirmDate() {
  if (selectedSecurityOption.value?.type !== "fund" || !form.trade_date) {
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

watch([() => form.trade_date, () => form.isAfter15, selectedSecurityOption], () => {
  fetchTradingDay();
  fetchConfirmDate();
});

// ── 提交 ──
async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  const step = getStep({ type: form.type, market: form.market, symbol: form.symbol });
  const quantity = amountMode.value === "amount" ? computedQuantity.value : Number(amountOrQuantity.value);
  if (quantity < step) {
    ElMessage.error(`买入数量不能低于 ${step} 份`);
    return;
  }
  if (!supportsOneShare({ type: form.type, market: form.market, symbol: form.symbol }) && quantity % step !== 0) {
    ElMessage.error(`买入数量必须是 ${step} 的整数倍`);
    return;
  }

  const body = {
    symbol: form.symbol,
    name: form.name,
    op_type: "buy",
    market: form.market,
    type: form.type,
    ledger_id: form.ledger_id,
    account_name: accountName.value,
    quantity,
    avg_price: form.price,
    amount: computedAmount.value,
    currency: form.currency,
    trade_date: form.trade_date,
    confirm_date: form.type === "fund" ? confirmDate.value : null,
    fee: form.fee,
    notes: form.notes,
    allocation: form.allocation,
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
  selectedSecurityOption.value = null;
  securityOptions.value = [];
  amountOrQuantity.value = "";
  amountMode.value = "amount";
  fundFeeDiscount.value = 0.1;
  isTradingDay.value = null;
  confirmDate.value = "";
  formRef.value?.resetFields();
}

// 父组件通过 ref 调用
defineExpose({ handleSubmit, resetForm });
</script>

<style scoped>
/* 与原来一致，只保留买入需要的样式 */
.quick-add-account {
  border-color: var(--border-default);
}
.text-xs {
  font-size: 0.75rem;
}
</style>
