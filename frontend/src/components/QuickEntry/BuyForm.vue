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
                <AssetTypeBadge :type="ledger.ledger_type" variant="tag" />
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

        <div
          v-if="selectableLedgers.length === 0 && !showQuickAdd"
          class="text-xs mt-1"
          style="color: var(--text-tertiary)"
        >
          暂无账户，点击右侧 + 按钮快速创建
        </div>

        <!-- 极简创建账户 -->
        <div
          v-if="showQuickAdd"
          class="quick-add-account mt-3 p-3 border rounded-lg bg-gray-50"
          style="border-color: var(--border-default)"
        >
          <el-input
            v-model="newAccountName"
            placeholder="输入账户名称"
            size="small"
            @keyup.enter="quickCreateAccount"
          />
          <el-select
            v-model="newAccountType"
            class="w-full mt-2"
            size="small"
            placeholder="选择账户类型"
          >
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
    </template>

    <!-- 证券/基金搜索 -->
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
        clearable
        class="w-full"
        style="display: block; width: 100%"
        @change="onSecuritySelected"
      >
        <el-option
          v-for="item in securityOptions"
          :key="item.symbol"
          :label="`${item.symbol} ${item.name} (${item.type_label || item.type})`"
          :value="item"
        />
        <template #empty>
          <div
            class="text-center py-4 text-sm"
            style="color: var(--text-tertiary)"
          >
            <template v-if="!searchLoading">{{ emptyHint }}</template>
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
        <span v-if="isTradingDay === false" style="color: var(--color-warning)"
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
        <div class="text-xs mt-1" style="color: var(--text-tertiary)">
          买入金额将包含手续费，系统自动计算份额
        </div>
      </div>
    </el-form-item>

    <!-- 2. 手续费（带有金额/费率切换） -->
    <el-form-item
      v-if="selectedSecurityOption?.type === 'fund'"
      label="手续费"
      prop="fee"
    >
      <div class="flex flex-col gap-2 w-full">
        <!-- 第一行：模式切换 + 数值输入 -->
        <div class="flex items-center gap-3 w-full">
          <el-select
            v-model="feeMode"
            style="width: 100px"
            @change="onFeeModeChange"
          >
            <el-option label="金额" value="amount" />
            <el-option label="费率" value="rate" />
          </el-select>

          <!-- 🔥 修复1：直接用 form.fee 接管所有输入，确保核心 watch 能监听到 -->
          <el-input-number
            v-model="form.fee"
            class="flex-1"
            :controls="false"
            :precision="feeMode === 'amount' ? 2 : 4"
            :min="0"
            :placeholder="feeMode === 'amount' ? '输入手续费金额' : '0.0000'"
          />
          <span class="text-sm shrink-0" style="color: var(--text-tertiary)">
            {{ feeMode === "amount" ? "元" : "%" }}
          </span>
        </div>

        <!-- 第二行：快捷折扣按钮（仅在费率模式下独立一行展示，间距宽松） -->
        <div
          v-if="feeMode === 'rate'"
          class="flex flex-wrap items-center gap-2 mt-1"
        >
          <el-button
            size="small"
            plain
            round
            class="quick-ratio-btn"
            :class="{ active: fundFeeDiscount === 1.0 }"
            @click="
              fundFeeDiscount = 1.0;
              onFundFeeDiscountChange();
            "
            >原价</el-button
          >
          <el-button
            size="small"
            plain
            round
            class="quick-ratio-btn"
            :class="{ active: fundFeeDiscount === 0.1 }"
            @click="
              fundFeeDiscount = 0.1;
              onFundFeeDiscountChange();
            "
            >1折</el-button
          >
          <el-button
            size="small"
            plain
            round
            class="quick-ratio-btn"
            :class="{ active: fundFeeDiscount === 0.01 }"
            @click="
              fundFeeDiscount = 0.01;
              onFundFeeDiscountChange();
            "
            >0.1折</el-button
          >
          <el-button
            size="small"
            plain
            round
            class="quick-ratio-btn"
            :class="{ active: fundFeeDiscount === 0 }"
            @click="
              fundFeeDiscount = 0;
              onFundFeeDiscountChange();
            "
            >免申购费</el-button
          >
        </div>
      </div>

      <div class="text-xs mt-1" style="color: var(--text-tertiary)">
        费率已根据账户预设填充，可手动修改
      </div>
    </el-form-item>

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
      <div class="text-xs mt-1" style="color: var(--text-tertiary)">
        买入金额扣除手续费后的确认份额，可手动微调
      </div>
    </el-form-item>

    <!-- 🔥 修改：显示“对应净值”，并用 actualNavDate 替代 form.trade_date -->
    <!-- 4. 确认净值（弱化展示：只读、小字、带日期） -->
    <div
      v-if="selectedSecurityOption?.type === 'fund'"
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
import { ref, reactive, computed, watch, nextTick } from "vue";
import { ElMessage } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { createPosition } from "@/api/positions";
import { createLedger as createLedgerApi } from "@/api/ledger";
import { searchSecurities } from "@/api/securities";
import { searchFunds, calcFundNav, getFundFeeRates } from "@/api/funds";
import type { FundSearchItem } from "@/api/funds";
import { checkTradingDay, calcFundConfirmDate } from "@/api/utils";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  ALLOCATION_OPTIONS,
  LEDGER_TYPE_SHORT,
  LEDGER_TYPE_OPTIONS
} from "@/constants";
import { getLedgerColor, bgFromColor } from "@/utils/ledger";
import { DEFAULT_SUB_RATE } from "@/utils/trading";

// ── Props & Emits ──
const props = defineProps<{
  ledgers: any[];
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

// 极简账户创建
const showQuickAdd = ref(false);
const newAccountName = ref("");
const newAccountType = ref("");
const creatingAccount = ref(false);
const quickAddTypeOptions = LEDGER_TYPE_OPTIONS.filter(
  opt => opt.value !== "property"
);

// 搜索状态
const searchLoading = ref(false);
const securityOptions = ref<any[]>([]);
const selectedSecurityOption = ref<any>(null);

// 🔥 修复2：移除 feeRateValue，直接用 form.fee 管理所有模式下的输入
const feeMode = ref<"amount" | "rate">("amount");

// 是否正在更新（防死循环锁）
const isUpdating = ref(false);

// 基金手续费折扣
const fundFeeDiscount = ref(0.1);

// 交易日与确认日
const isTradingDay = ref<boolean | null>(null);
const actualNavDate = ref(""); // 🔥 新增：用于储存后端返回的实际净值日
const confirmDate = ref("");

// ── 计算属性 ──
const selectableLedgers = computed(() =>
  props.ledgers.filter(l => l.ledger_type !== "property")
);
const currentLedger = computed(
  () => props.ledgers.find(l => l.id === form.ledger_id) ?? null
);
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
const emptyHint = computed(
  () => `还没有${searchLabel.value}持仓？去「全面盘点」导入交割单吧 >`
);
const showIsAfter15 = computed(() => {
  const type = currentLedger.value?.ledger_type;
  if (type === "fund" || type === "bank") return true;
  if (type === "stock" && selectedSecurityOption.value?.type === "fund")
    return true;
  return false;
});

const disabledDate = (time: Date) =>
  time.getTime() > new Date().setHours(0, 0, 0, 0);

const rules: FormRules = {
  ledger_id: [{ required: true, message: "请选择账户", trigger: "change" }],
  symbol: [{ required: true, message: "请选择买入产品", trigger: "change" }],
  trade_date: [{ required: true, message: "请选择日期", trigger: "change" }],
  buyAmount: [{ required: true, message: "请输入买入金额", trigger: "blur" }],
  shares: [{ required: true, message: "确认份额不能为空", trigger: "blur" }],
  allocation: [{ required: true, message: "请选择配置目标", trigger: "change" }]
};

// ── 核心联动逻辑 ──

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
      securityOptions.value = [];
    }
    applyFeePreset();
  }
);

// 金额变化，联动计算份额
watch(
  () => form.buyAmount,
  newVal => {
    if (isUpdating.value || newVal === undefined) return;
    if (!form.price || form.price <= 0) {
      form.shares = undefined;
      return;
    }
    isUpdating.value = true;
    const fee = form.fee || 0;
    form.shares = parseFloat(((newVal - fee) / form.price).toFixed(4));
    nextTick(() => {
      isUpdating.value = false;
    });
  }
);

// 份额变化，联动计算金额
watch(
  () => form.shares,
  newVal => {
    if (isUpdating.value || newVal === undefined) return;
    if (!form.price || form.price <= 0) return;
    isUpdating.value = true;
    const fee = form.fee || 0;
    form.buyAmount = parseFloat((newVal * form.price + fee).toFixed(2));
    nextTick(() => {
      isUpdating.value = false;
    });
  }
);

// ── 手续费逻辑 ──

function applyFeePreset() {
  const ledger = currentLedger.value;
  if (!ledger) {
    form.fee = 0;
    return;
  }
  const config = parseFeeConfig(ledger.fee_config);
  const safeAmount = form.buyAmount || 0;
  if (ledger.ledger_type === "stock") {
    form.fee = safeAmount * (config?.commission?.rate ?? 0.00025);
  } else if (ledger.ledger_type === "fund" || ledger.ledger_type === "bank") {
    fundFeeDiscount.value = config?.subscription_discount ?? 0.1;
    const fundRate =
      selectedSecurityOption.value?.subscription_rate ?? DEFAULT_SUB_RATE;
    form.fee = safeAmount * fundRate * fundFeeDiscount.value;
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

// 🔥 修复3：统一金额/费率模式切换转换逻辑，直接操纵 form.fee
function onFeeModeChange() {
  const est = form.buyAmount || 0;
  if (feeMode.value === "rate") {
    // 从金额切换到费率
    if (est > 0 && form.fee && form.fee > 0) {
      form.fee = parseFloat(((form.fee / est) * 100).toFixed(4));
    } else {
      form.fee = undefined;
    }
  } else {
    // 从费率切换到金额
    if (est > 0 && form.fee && form.fee > 0) {
      form.fee = parseFloat((est * (form.fee / 100)).toFixed(2));
    } else {
      form.fee = undefined;
    }
  }
}

// 🔥 修复4：点击快捷折扣按钮时直接修改 form.fee，触发联动更新
function onFundFeeDiscountChange() {
  const fundRate =
    selectedSecurityOption.value?.subscription_rate ?? DEFAULT_SUB_RATE;
  const est = form.buyAmount || 0;
  const rate = fundRate * fundFeeDiscount.value;
  if (feeMode.value === "rate") {
    // 费率模式，存百分比
    form.fee = parseFloat((rate * 100).toFixed(4));
  } else {
    // 金额模式，存金额
    form.fee = parseFloat((est * rate).toFixed(2));
  }
}

// ── 搜索 ──

/**
 * 识别货币基金：字段优先、代码段兜底。
 * 1. 后端 /api/funds/search/ 输出 is_money_fund（fund_type_id === 6）时直接判定，
 *    可覆盖场外货基（如 000198 余额宝）；
 * 2. 字段缺失（后端尚未部署）时回退代码段规则，与后端 core/symbol_utils.py
 *    _get_asset_type 一致：SH 97 开头（沪市现金管理产品）、SZ 10/11 开头（深市货币基金）。
 * 命中后前端提交 type='money_fund'，后端 position_service 对现金管理类产品
 * 只记孤儿流水、不建持仓。
 */
function resolveFundAssetType(
  code: string,
  isMoneyFund?: boolean
): "money_fund" | "fund" {
  if (isMoneyFund === true) return "money_fund";
  return /^97\d{4}$/.test(code) || /^1[01]\d{4}$/.test(code)
    ? "money_fund"
    : "fund";
}

async function remoteSearch(query: string) {
  if (!query) {
    securityOptions.value = [];
    return;
  }
  searchLoading.value = true;
  try {
    const type = currentLedger.value?.ledger_type ?? "";
    let opts: any[] = [];
    if (type === "fund" || type === "bank") {
      const res = await searchFunds(query);
      const arr = Array.isArray(res) ? res : (res.data ?? []);
      opts = arr.map((f: FundSearchItem) => {
        const assetType = resolveFundAssetType(f.code, f.is_money_fund);
        return {
          symbol: f.code,
          name: f.name,
          market: "CN_A",
          type: assetType,
          type_label: assetType === "money_fund" ? "货币基金" : "基金",
          subscription_rate: f.subscription_rate || DEFAULT_SUB_RATE
        };
      });
    } else {
      const res = await searchSecurities(query);
      const arr = Array.isArray(res) ? res : ((res as any)?.data ?? []);
      const typeLabels: Record<string, string> = {
        stock: "股票",
        bond: "可转债",
        etf: "ETF"
      };
      opts = arr.map((s: any) => ({
        symbol: s.symbol,
        name: s.name,
        market: s.market,
        type: s.type,
        type_label: typeLabels[s.type] || s.type
      }));
    }
    if (opts.length === 0 && query.trim()) {
      const isFundLedger = type === "fund" || type === "bank";
      const manualType = isFundLedger
        ? resolveFundAssetType(query.trim())
        : "stock";
      opts = [
        {
          symbol: query.trim().toUpperCase(),
          name: query.trim(),
          market: "CN_A",
          type: manualType,
          type_label: manualType === "money_fund" ? "货币基金" : "手动输入",
          is_manual: true
        }
      ];
    }
    securityOptions.value = opts;
  } catch {
    if (query.trim()) {
      const manualType =
        currentLedger.value?.ledger_type === "fund" ||
        currentLedger.value?.ledger_type === "bank"
          ? resolveFundAssetType(query.trim())
          : "stock";
      securityOptions.value = [
        {
          symbol: query.trim().toUpperCase(),
          name: query.trim(),
          market: "CN_A",
          type: manualType,
          type_label: manualType === "money_fund" ? "货币基金" : "手动输入",
          is_manual: true
        }
      ];
    }
    ElMessage.warning("搜索服务暂不可用，已提供手动输入选项");
  } finally {
    searchLoading.value = false;
  }
}

// 替换 onSecuritySelected 为如下代码
async function onSecuritySelected(option: any) {
  if (!option) {
    form.symbol = "";
    form.name = "";
    form.market = "CN_A";
    form.type = "stock";
    selectedSecurityOption.value = null;
    form.buyAmount = undefined;
    form.shares = undefined;
    return;
  }
  form.symbol = option.symbol;
  form.name = option.name;
  form.market = option.market || "CN_A";
  form.type = option.type;
  selectedSecurityOption.value = option;

  // 🔥 新增：如果是基金，去拉取详细费率（用来更新 subscription_rate）
  if (option.type === "fund") {
    try {
      const res = await getFundFeeRates(option.symbol);
      const data = res.data;
      if (data && data.purchase && data.purchase.length > 0) {
        // 取第一条费率作为默认预设（通常是无门槛或最低门槛的费率）
        const defaultRate = data.purchase[0].rate;
        // 回填到 option 上，这样 applyFeePreset 在之后触发时能拿到正确的 0.0 或 0.15%
        selectedSecurityOption.value.subscription_rate = defaultRate;
      }
    } catch (e) {
      console.warn("拉取详细费率失败", e);
    }
  }

  applyFeePreset(); // 最终触发预设
}

// ── 快捷创建账户 ──

async function quickCreateAccount() {
  const name = newAccountName.value.trim();
  const type = newAccountType.value;
  if (!name || !type) return;
  creatingAccount.value = true;
  try {
    let feeConfig: any = undefined;
    if (type === "fund") feeConfig = { subscription_discount: 0.1 };
    else if (type === "stock")
      feeConfig = { commission: { rate: 0.00025, min: null } };
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

// ── 交易日、确认日、净值 ──

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

// 🔥 修复 1：正确接收后端返回的两个日期
async function fetchConfirmDate() {
  if (selectedSecurityOption.value?.type !== "fund" || !form.trade_date) {
    actualNavDate.value = "";
    confirmDate.value = "";
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
      actualNavDate.value = data.actual_trade_date; // 真实净值日
      confirmDate.value = data.confirm_date; // 确认日
    }
  } catch {
    actualNavDate.value = "";
    confirmDate.value = "";
  }
}

// ── 提交 ──

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  const quantity = form.shares!;
  if (quantity <= 0) {
    ElMessage.error("确认份额必须大于0");
    return;
  }

  let finalConfirmDate = null;
  if (form.type === "fund") {
    finalConfirmDate =
      confirmDate.value && confirmDate.value.trim() !== ""
        ? confirmDate.value
        : null;
  } else {
    finalConfirmDate = form.trade_date;
  }

  // 🔥 修复5：统一计算实际手续费，确保传给后端的是金额（元）
  let finalFee = form.fee || 0;
  // 如果在费率模式，用户填的是百分比，必须转成金额
  if (feeMode.value === "rate") {
    finalFee = (form.buyAmount || 0) * (form.fee / 100);
  }

  const body = {
    symbol: form.symbol,
    name: form.name,
    op_type: "buy",
    market: form.market || "CN_A",
    type: form.type,
    ledger_id: form.ledger_id,
    account_name: accountName.value,
    quantity,
    avg_price: form.price || 0,
    amount: form.buyAmount || 0,
    currency: form.currency,
    trade_date: form.trade_date,
    confirm_date: finalConfirmDate,
    fee: finalFee,
    notes: form.notes,
    allocation: form.allocation,
    isAfter15: form.isAfter15
  };

  try {
    await createPosition(body);
    ElMessage.success("记账成功");
    emit("submit-success");
  } catch (e: any) {
    let msg = e?.message || "记账失败，请重试";
    if (e?.response?.status === 422) {
      const detail = e?.response?.data?.message;
      if (detail) {
        if (typeof detail === "object") {
          const errors = Object.entries(detail)
            .map(([field, errs]) => `${field}: ${(errs as any).join(", ")}`)
            .join("; ");
          msg = `数据错误 (422): ${errors}`;
        } else if (typeof detail === "string") {
          msg = `数据错误 (422): ${detail}`;
        }
      }
    }
    ElMessage.error(msg);
  }
}

function resetForm() {
  Object.assign(form, defaultForm());
  selectedSecurityOption.value = null;
  securityOptions.value = [];
  actualNavDate.value = "";
  confirmDate.value = "";
  formRef.value?.resetFields();

  if (props.hideAccountSelect && props.defaultLedgerId) {
    form.ledger_id = props.defaultLedgerId;
  }
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

// 🔥 核心修复：监听日期和 15:00 切换，先算确认日，再用确认日拉净值
watch(
  [() => form.trade_date, () => form.isAfter15, selectedSecurityOption],
  async () => {
    fetchTradingDay();

    if (selectedSecurityOption.value?.type === "fund" && form.trade_date) {
      await fetchConfirmDate();

      if (actualNavDate.value) {
        try {
          const res = await calcFundNav(
            [selectedSecurityOption.value.symbol],
            actualNavDate.value
          );
          const navData = (res as any)?.data || [];
          if (navData.length > 0 && navData[0].unit_nav) {
            form.price = navData[0].unit_nav;
          }
        } catch (e) {
          console.warn("净值获取失败，需用户手动输入", e);
        }
      }
    }
  }
);

// 🔥 核心联动：统一监听【买入金额、手续费、基金净值】。
// 只要这三个值全了就立刻联动，绝不卡住！
watch(
  [() => form.buyAmount, () => form.fee, () => form.price],
  ([newBuy, newFee, newPrice]) => {
    if (isUpdating.value) return;
    if (newBuy === undefined || newBuy <= 0 || !newPrice || newPrice <= 0) {
      if (form.shares !== undefined) form.shares = undefined;
      return;
    }
    isUpdating.value = true;
    const fee = newFee || 0;
    const calculated = parseFloat(((newBuy - fee) / newPrice).toFixed(4));
    if (form.shares !== calculated) {
      form.shares = calculated;
    }
    nextTick(() => {
      isUpdating.value = false;
    });
  }
);

defineExpose({ handleSubmit, resetForm });
</script>

<style scoped>
.text-xs {
  font-size: 0.75rem;
}

.quick-ratio-btn {
  height: 40px;
  padding: 0 16px;
  font-weight: 500;
  color: var(--text-secondary);
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  transition:
    background-color 0.2s,
    border-color 0.2s,
    color 0.2s,
    transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.quick-ratio-btn:hover {
  color: var(--brand-700);
  background-color: var(--brand-100);
  border-color: var(--brand-700);
}

.quick-ratio-btn:active {
  color: var(--brand-700);
  background-color: var(--brand-200);
  border-color: var(--brand-700);
  transform: scale(0.92);
}

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

/* 输入框统一样式（高度、圆角、边框颜色、聚焦阴影） */
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

/* 下拉框复用同样变量 */
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
