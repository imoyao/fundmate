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
    <el-form-item label="交易日期" prop="trade_date">
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

    <!-- ===== 核心三兄弟 ===== -->

    <!-- 1. 买入金额 -->
    <el-form-item label="买入金额" prop="buyAmount">
      <div class="flex flex-col w-full">
        <el-input-number
          v-model="form.buyAmount"
          style="width: 100%"
          class="w-full"
          :controls="false"
          :precision="2"
          :min="0"
          placeholder="输入买入金额"
        />
        <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
          买入金额将包含手续费，系统自动计算份额
        </div>
      </div>
    </el-form-item>

    <!-- 2. 手续费（带有金额/费率切换） -->
    <BuyFeeField
      v-if="selectedSecurityOption?.type === 'fund'"
      v-model:fee="form.fee"
      v-model:fee-mode="feeMode"
      v-model:discount="fundFeeDiscount"
      @fee-mode-change="onFeeModeChange"
      @discount-change="onFundFeeDiscountChange"
    />

    <!-- 3. 确认份额（字号放大，用户可编辑微调） -->
    <el-form-item label="确认份额" prop="shares">
      <el-input-number
        v-model="form.shares"
        style="width: 100%"
        class="w-full font-bold text-lg"
        :controls="false"
        :precision="selectedSecurityOption?.type === 'fund' ? 2 : 0"
        :min="0"
        :placeholder="
          selectedSecurityOption?.type === 'fund'
            ? '自动计算或手动微调份额'
            : '买入数量'
        "
      />
      <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
        买入金额扣除手续费后的确认份额，可手动微调
      </div>
    </el-form-item>

    <!-- 4. 确认净值（提升视觉层级：净值是基金买入/赎回到账的核心依据，信息层级应与重要性匹配） -->
    <TradeNavPriceRow
      v-if="selectedSecurityOption?.type === 'fund'"
      :price="form.price"
      :nav-date="actualNavDate"
      :fallback-date="form.trade_date"
    />

    <!-- 净值缺失先记账：放行提交的提示（份额可留空，官方净值到位后自动回填） -->
    <div v-if="navMissing" class="nav-pending-hint text-xs mt-1">
      当日净值暂不可用，仍可先记账：份额可留空（或按估算填写），官方净值发布后将自动回填份额与成本。
    </div>

    <!-- 配置目标 -->
    <el-form-item label="配置目标" prop="allocation">
      <el-select
        v-model="form.allocation"
        class="w-full"
        style="display: block; width: 100%"
        placeholder="选择配置目标"
      >
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
      <el-input
        v-model="form.notes"
        type="textarea"
        :rows="2"
        placeholder="补充交易理由（选填）"
        style="width: 100%"
      />
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick, onMounted } from "vue";
import type { FormInstance } from "element-plus";
import { useFormDirtySnapshot } from "@/composables/useFormDirtySnapshot";
import type { LedgerItem } from "@/api/ledger";
import { useSecurityPriceRange } from "@/composables/useSecurityPrice";
import TradeSlotSwitch from "@/components/TradeSlotSwitch/index.vue";
import { ALLOCATION_OPTIONS } from "@/constants";
import { disabledTradeDate } from "@/utils/date";
import BuyAccountField from "./components/BuyAccountField.vue";
import BuySecuritySearchField from "./components/BuySecuritySearchField.vue";
import BuyFeeField from "./components/BuyFeeField.vue";
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

const defaultForm = () => ({
  ledger_id: null as number | null,
  symbol: "",
  name: "",
  market: "CN_A",
  type: "stock",
  price: undefined as number | undefined,
  trade_date: new Date().toISOString().slice(0, 10),
  confirm_date: "",
  fee: 0 as number | undefined,
  allocation: "longterm",
  notes: "",
  isAfter15: false,
  currency: "CNY",
  buyAmount: undefined as number | undefined,
  shares: undefined as number | undefined
});

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

// ── 金额 ⇄ 份额联动（三条 watch 的注册顺序由 composable 固定，勿随意挪调用位置）──
useBuySharesLinkage({ form, navMissing });

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
