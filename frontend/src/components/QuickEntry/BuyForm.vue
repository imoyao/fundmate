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
      <BuyAccountField
        v-model="form.ledger_id"
        :ledgers="ledgers"
        @change="onAccountSelected"
        @accounts-changed="emit('accounts-changed')"
      />
    </template>

    <!-- 证券/基金搜索 -->
    <BuySecuritySearchField
      ref="searchFieldRef"
      v-model="selectedSecurityOption"
      :ledger-type="currentLedger?.ledger_type"
      @select="onSecuritySelected"
    />

    <!-- 交易日期与下单时间 -->
    <el-form-item :label="TRADE_FIELD_LABELS.tradeDate" prop="trade_date">
      <div class="flex items-center gap-3 w-full">
        <!-- 日期框外层必须自带弹性：DatePicker 是 inheritAttrs:false，写它身上的
             class（曾用 `:class="showIsAfter15 ? 'flex-1' : 'w-full'"`）根本落不到
             DOM 上；宽度只能靠内联 width:100% + 外层的 flex-1/min-w-0 给。 -->
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
        <span
          v-if="isTradingDay === false"
          style="color: var(--color-warning-ink)"
          >所选日期非交易日，请确认 ·
        </span>
        <span v-if="form.isAfter15 && selectedSecurityOption?.type === 'fund'">
          预计确认日：{{ confirmDate || "计算中..." }}
        </span>
      </div>
    </el-form-item>

    <!-- ===== 核心字段 ===== -->

    <!-- 0. 买入价格（股票/ETF/可转债）：与买入金额拆在同一层，见组件内注释 -->
    <BuyPriceField
      v-model:price="form.price"
      :security-type="selectedSecurityOption?.type"
    />

    <BuyBankWealthNameField
      v-if="selectedSecurityOption?.is_manual && form.type === 'bank_wealth'"
      v-model:name="form.name"
    />

    <!-- 1a. 成交数量（股票/ETF/可转债）：先有成交数量与成交价，金额是派生量。
         与基金相反 —— 基金申购时净值未知，只能按金额算份额（见 3.） -->
    <BuyQuantityField
      v-if="quantityMeta.mode === 'trade'"
      v-model:shares="form.shares"
      :type="selectedSecurityOption?.type"
      :ledger-type="currentLedger?.ledger_type"
      :market="form.market"
      :symbol="form.symbol"
    />

    <!-- 1b. 买入金额（只记金额的品类文案在组件内部分叉；非基金为只读派生量） -->
    <BuyAmountField
      v-model:amount="form.buyAmount"
      :balance-kind="balanceKind"
      :derived="quantityMeta.amountDerived"
    />

    <!-- 2. 手续费（基金：金额/费率双模式 + 申购折扣；股票/ETF：实收金额直填） -->
    <BuyFeeField
      v-if="showFeeField"
      v-model:fee="form.fee"
      v-model:fee-mode="feeMode"
      v-model:discount="fundFeeDiscount"
      :simple="!isFundSecurity"
      @fee-mode-change="onFeeModeChange"
      @discount-change="onFundFeeDiscountChange"
    />

    <!-- 3. 确认份额（基金按净值算份额，可微调）；投顾组合 / 银行理财无份额，整块隐藏（D70 / D121） -->
    <BuyQuantityField
      v-if="quantityMeta.mode === 'fund'"
      v-model:shares="form.shares"
      :type="selectedSecurityOption?.type"
      :ledger-type="currentLedger?.ledger_type"
      :market="form.market"
      :symbol="form.symbol"
    />

    <!-- 4. 确认净值（提升视觉层级：净值是基金买入/赎回到账的核心依据，信息层级应与重要性匹配） -->
    <TradeNavPriceRow
      v-if="selectedSecurityOption?.type === 'fund' && balanceKind === null"
      :price="form.price"
      :nav-date="actualNavDate"
      :fallback-date="form.trade_date"
    />

    <!-- 净值缺失先记账：放行提交的提示（份额可留空，官方净值到位后自动回填） -->
    <div v-if="navMissing" class="nav-pending-hint text-xs mt-1">
      当日净值暂不可用，仍可先记账：份额可留空（或按估算填写），官方净值发布后将自动回填份额与成本。
    </div>

    <!-- 配置目标 / 备注（#980：整体拆到 BuyExtraFields，本文件守 400 行门禁） -->
    <BuyExtraFields
      v-model:allocation="form.allocation"
      v-model:notes="form.notes"
    />
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick, onMounted } from "vue";
import type { FormInstance } from "element-plus";
import { useFormDirtySnapshot } from "@/composables/useFormDirtySnapshot";
import type { LedgerItem } from "@/api/ledger";
import { useSecurityPriceRange } from "@/composables/useSecurityPrice";
import TradeSlotSwitch from "@/components/TradeSlotSwitch/index.vue";
import { TRADE_FIELD_LABELS } from "@/constants";
import { disabledTradeDate } from "@/utils/date";
import BuyAccountField from "./components/BuyAccountField.vue";
import BuyAmountField from "./components/BuyAmountField.vue";
import BuyBankWealthNameField from "./components/BuyBankWealthNameField.vue";
import BuySecuritySearchField from "./components/BuySecuritySearchField.vue";
import BuyExtraFields from "./components/BuyExtraFields.vue";
import BuyFeeField from "./components/BuyFeeField.vue";
import BuyPriceField from "./components/BuyPriceField.vue";
import BuyQuantityField from "./components/BuyQuantityField.vue";
import TradeNavPriceRow from "./components/TradeNavPriceRow.vue";
import { useBuyFee } from "./composables/useBuyFee";
import { useBuySharesLinkage } from "./composables/useBuySharesLinkage";
import { useBuyNavSync } from "./composables/useBuyNavSync";
import { useBuySecuritySelection } from "./composables/useBuySecuritySelection";
import { useBuySubmit } from "./composables/useBuySubmit";
import type { SecurityOption } from "./composables/useSecuritySearch";
import {
  loadBuyLastSubmitted,
  snapshotToFormPatch,
  snapshotToSecurityOption
} from "./buyLastSubmitted";
import { buyQuantityMeta } from "./buyQuantityMeta";
import { createBuyFormDefaults } from "./buyFormModel";

// ── Props & Emits ──
const props = defineProps<{
  ledgers: LedgerItem[];
  hideAccountSelect?: boolean;
  defaultLedgerId?: number | null;
}>();
const emit = defineEmits<{
  (e: "submit-success"): void;
  (e: "accounts-changed"): void;
}>();

const defaultForm = createBuyFormDefaults;

const form = reactive(defaultForm());
const formRef = ref<FormInstance>();
const searchFieldRef = ref<{ reset: () => void } | null>(null);
const selectedSecurityOption = ref<SecurityOption | null>(null);
// 净值缺失先记账标记（联动与提交都要读，故由本层持有）
const navMissing = ref(false);

// ── 派生值 ──
const currentLedger = computed(
  () => props.ledgers.find(l => l.id === form.ledger_id) ?? null
);
const accountName = computed(() => currentLedger.value?.name ?? "");
const isFundSecurity = computed(
  () => selectedSecurityOption.value?.type === "fund"
);
// 数量字段口径（品种×账户）：基金「确认份额 / 金额为主量」，股票等「成交数量 / 金额派生」。
// 标签、精度、一手、提示语与提交校验全从 buyQuantityMeta 取，别在模板里另写一套。
const quantityMeta = computed(() =>
  buyQuantityMeta({
    type: selectedSecurityOption.value?.type,
    ledgerType: currentLedger.value?.ledger_type,
    market: form.market,
    symbol: form.symbol
  })
);
// 投顾组合 / 银行理财：只记金额（balance），没有份额、净值与价格（D70 / D121）。
// 传取值而不是布尔，因为金额提示语两者不同（见 BuyAmountField.hint）。
const balanceKind = computed<"portfolio" | "bank_wealth" | null>(() =>
  form.type === "portfolio" || form.type === "bank_wealth" ? form.type : null
);
// 两类都不收申购费，不显示输入框；未选标的也不显示（与价格行同一模式）
const showFeeField = computed(
  () => Boolean(selectedSecurityOption.value?.type) && !balanceKind.value
);
// 买入价格可手填的品种判定已随表单项下沉到 BuyPriceField（含口径说明）
const showIsAfter15 = computed(() => {
  const type = currentLedger.value?.ledger_type;
  if (type === "fund" || type === "bank") return true;
  if (type === "stock" && selectedSecurityOption.value?.type === "fund")
    return true;
  return false;
});

// 交易日期禁用规则收敛到 utils/date（#1835：同一规则曾散落三处、编辑弹窗漏了第四处）
const disabledDate = disabledTradeDate;

// ── 手续费 / 价格区间 / 脏基线 ──
const {
  feeMode,
  fundFeeDiscount,
  applyFeePreset,
  onFeeModeChange,
  onFundFeeDiscountChange
} = useBuyFee({ form, currentLedger, selectedSecurityOption });

// 股票价格区间（#948）：随标的/交易日自动刷新，统一走 useSecurityPriceRange
const { priceRange: stockPriceRange, refresh: refreshStockRange } =
  useSecurityPriceRange(
    computed(() => selectedSecurityOption.value?.symbol),
    computed(() => form.trade_date),
    computed(() => selectedSecurityOption.value?.type === "stock")
  );

// 未保存离开保护（#1853）：脏状态住在本子组件里（父组件 TransactionDrawer 拿不到），
// 故 expose 出去。快照声明必须在 resetForm 之前——它被 resetForm 调用。
const { markFormClean, isDirty } = useFormDirtySnapshot(() => form);

// ── 账户切换 ──
function onAccountSelected() {
  applyFeePreset();
}

watch(
  () => form.ledger_id,
  (newVal, oldVal) => {
    if (!oldVal && !newVal) return;
    const oldLedger = props.ledgers.find(l => l.id === oldVal);
    const newLedger = props.ledgers.find(l => l.id === newVal);
    if (oldLedger?.ledger_type !== newLedger?.ledger_type) {
      form.symbol = "";
      form.name = "";
      form.market = "CN_A";
      form.type = "stock";
      form.price = undefined;
      form.buyAmount = undefined;
      form.shares = undefined;
      selectedSecurityOption.value = null;
      // 旧选项属于上一个账户的品类，留着会让人搜到不该出现的东西
      searchFieldRef.value?.reset();
    }
    applyFeePreset();
  }
);

// ── 金额 ⇄ 份额联动（watch 的注册顺序由 composable 固定，勿随意挪调用位置）──
// 基金：金额 → 份额；股票/ETF/可转债：数量 → 金额（金额只读，反算会得出碎股）
useBuySharesLinkage({
  form,
  navMissing,
  mode: () => (quantityMeta.value.amountDerived ? "trade" : "fund")
});

// ── 交易日 / 确认日 / 净值 ──
const {
  isTradingDay,
  actualNavDate,
  confirmDate,
  calcConfirmAndNav,
  resetTradeDate
} = useBuyNavSync({ form, selectedSecurityOption, navMissing, markFormClean });

// ── 选中标的：回填价格与费率 ──
const { onSecuritySelected } = useBuySecuritySelection({
  form,
  selectedSecurityOption,
  navMissing,
  applyFeePreset,
  refreshStockRange
});

// ── 校验规则 + 提交 ──
const { rules, handleSubmit } = useBuySubmit({
  form,
  formRef,
  selectedSecurityOption,
  stockPriceRange,
  navMissing,
  quantityMeta,
  getAccountName: () => accountName.value,
  confirmDate,
  actualNavDate,
  feeMode,
  onSuccess: () => emit("submit-success")
});

// ── 「重记一笔」预填（#2305）──
// 挂载时若有快照，预填产品+账户（金额/日期/份额留空，避免误提交上次金额）。
// 放在 onMounted 里，等 defaultLedgerId 的 immediate watcher 跑完再覆盖，避免被父组件默认值冲掉。
onMounted(() => {
  const last = loadBuyLastSubmitted();
  if (!last) return;
  Object.assign(form, snapshotToFormPatch(last));
  selectedSecurityOption.value = snapshotToSecurityOption(last);
  // 预填后触发一次费用预设与净值计算（watch 在模块加载期尚未挂载，需手动触发）
  nextTick(() => {
    applyFeePreset();
    if (last.type === "fund" && form.trade_date) {
      calcConfirmAndNav({
        tradeDate: form.trade_date,
        symbol: last.symbol,
        isAfter15: form.isAfter15
      });
    }
    // 「重记一笔」的预填是**程序化初始值**，不是用户编辑。不回写脏基线的话，
    // 页面一挂载 `isDirty` 就是 true —— 用户什么都不填、只切一下操作类型，
    // 就被弹「记账表单已填写，确定放弃吗？」（#2305 引入的回归）。
    markFormClean();
  });
});

function resetForm() {
  Object.assign(form, defaultForm());
  selectedSecurityOption.value = null;
  searchFieldRef.value?.reset();
  navMissing.value = false;
  resetTradeDate();
  formRef.value?.resetFields();

  if (props.hideAccountSelect && props.defaultLedgerId) {
    form.ledger_id = props.defaultLedgerId;
  }

  // 未保存离开保护的脏基线（#1853）：必须在**全部重置动作之后**再记快照。
  //
  // 记在前面（此前的写法）会把「本轮刚填的值」记成基线，紧接着 Object.assign 又把
  // 表单重置成默认值——基线≠当前，isDirty 于是为 true：提交成功后
  // TransactionDrawer 走 v-model setter 关闭时读到脏，弹出「交易表单已填写，确定
  // 放弃吗？」，且点「继续编辑」留下的是一个已被清空的表单。正确范式见
  // DividendForm.resetForm（先重置、后记快照）。
  markFormClean();
}

watch(
  () => props.defaultLedgerId,
  newVal => {
    if (props.hideAccountSelect && newVal) {
      form.ledger_id = newVal;
    }
  },
  { immediate: true }
);

defineExpose({ handleSubmit, resetForm, isDirty });
</script>

<style scoped>
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

/* 净值缺失先记账提示：走语义 warning 令牌（禁硬编码色值） */
.nav-pending-hint {
  padding: 6px 10px;
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
  border-radius: var(--radius-sm);
}
</style>
