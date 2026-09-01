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
              <AssetTypeBadge :type="acc.ledger_type" variant="tag" />
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
              <span
                class="truncate"
                :style="{ color: 'var(--text-primary)' }"
                >{{ pos.name || pos.symbol }}</span
              >
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
            <el-input-number
              v-model="form.quantity"
              :min="sellMin"
              style="width: 100%"
              :controls="false"
              :max="maxQuantity"
              :step="form.type === 'fund' ? 0.0001 : stepForSecurity"
              :precision="form.type === 'fund' ? 4 : 0"
              :placeholder="placeholderText"
              @blur="qtyTouched = true"
            />
            <div class="flex items-center justify-between w-full">
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
            <div
              v-if="showQtyHint"
              class="text-xs"
              style="color: var(--color-danger-system)"
            >
              <template v-if="form.type === 'fund'"
                >每笔最少 0.0001 份</template
              >
              <template v-else>每笔最少卖出 {{ sellMin }} 股/张</template>
            </div>
            <div
              v-else-if="isOddLot && form.type !== 'fund'"
              class="text-xs"
              style="color: var(--color-warning)"
            >
              （含碎股，可全部卖出）
            </div>
          </div>
        </el-form-item>

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
      <span
        >卖出资金将留存在当前账户余额，可用于再投资；如需转出到银行卡，请单独登记银证转账</span
      >
    </div>

    <!-- 费率查询弹窗（根据是否有输入份额动态显示列） -->
    <el-dialog
      v-model="feeRateDialogVisible"
      title="赎回费率分布"
      width="600px"
      destroy-on-close
    >
      <div v-if="!selectedPosition" class="text-center py-8 text-secondary">
        请先选择持仓
      </div>
      <template v-else>
        <div class="text-sm mb-3" style="color: var(--text-secondary)">
          当前持有 {{ maxQuantity.toFixed(4) }} 份
          <template v-if="enteredShares > 0">
            ，拟赎回 {{ enteredShares.toFixed(4) }} 份
          </template>
        </div>
        <el-table :data="mergedFeeData" stripe style="width: 100%">
          <el-table-column prop="range" label="持有天数" min-width="100" />
          <el-table-column prop="rate" label="费率" align="right" width="80">
            <template #default="{ row }">
              {{ (row.rate * 100).toFixed(2) }}%
            </template>
          </el-table-column>
          <el-table-column
            prop="holdShares"
            label="持有份额"
            align="right"
            width="110"
          />
          <el-table-column
            v-if="enteredShares > 0"
            prop="sellShares"
            label="卖出份额"
            align="right"
            width="110"
          >
            <template #default="{ row }">
              {{ row.sellShares !== null ? row.sellShares : "--" }}
            </template>
          </el-table-column>
        </el-table>
        <div
          v-if="maxQuantity > totalCalculatedHold"
          class="text-xs mt-2"
          style="color: var(--color-warning)"
        >
          注：当前持有 {{ maxQuantity.toFixed(4) }} 份，其中
          {{ totalCalculatedHold.toFixed(4) }}
          份有买入记录，可用于费率计算，其余份额未纳入分布。
        </div>
        <div class="mt-4 text-xs" style="color: var(--text-tertiary)">
          注：卖出份额按先进先出（FIFO）规则，从最早买入份额开始扣减。
        </div>
      </template>
      <template #footer>
        <el-button type="primary" @click="feeRateDialogVisible = false"
          >确定</el-button
        >
      </template>
    </el-dialog>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch, nextTick } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { getPositionsGroupedByAccount } from "@/api/positions";
import { usePositionSubmit } from "@/composables/usePositionSubmit";
import {
  useSecurityPriceRange,
  createStockPriceValidator,
  checkPriceInRange
} from "@/composables/useSecurityPrice";
import { validateTradeOrder } from "@/api/positions";
import type { Position } from "@/api/types";
import { IconifyIconOffline } from "@/components/ReIcon";
import { LEDGER_TYPE_SHORT } from "@/constants";
import { getLedgerColor, bgFromColor } from "@/utils/ledger";
import {
  getStep,
  SELL_QUICK_RATIOS,
  calcSellQuantityByRatio
} from "@/utils/trading";
import { estimateRedeemFee, syncFundFees } from "@/api/funds";
import { useFundTradeDate } from "@/composables/useFundTradeDate";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";

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

const feeError = ref("");

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

const positionSelectKey = ref(0);
const showPositionSelect = ref(true);
const form = reactive(defaultForm());
const formRef = ref<FormInstance>();
const positionsByAccount = ref<Record<string, Position[]>>({});
const selectedPosition = ref<any>(null);
// 股票价格区间（#948）：卖出价校验用，随持仓选择与交易日刷新（统一走 useSecurityPriceRange）
const { priceRange: stockPriceRange } = useSecurityPriceRange(
  computed(() => selectedPosition.value?.symbol),
  computed(() => form.trade_date),
  computed(() => form.type === "stock")
);
const feeRateDialogVisible = ref(false);
const feeRateTableData = ref<any[]>([]); // 保留用于兼容，但主要使用 holdFeeDetails
const holdFeeDetails = ref<any[]>([]); // 全仓持有分布
const sellFeeData = ref<any[]>([]); // 指定份额分布
const feeManuallyChanged = ref(false);
const qtyTouched = ref(false);

const {
  confirmDate,
  actualNavDate,
  calcConfirmAndNav,
  reset: resetTradeDate
} = useFundTradeDate();

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
const showQtyHint = computed(() => {
  if (!qtyTouched.value) return false;
  const q = form.quantity;
  if (q == null) return true;
  return q < sellMin.value;
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
const showIsAfter15 = computed(() => {
  const type = currentLedger.value?.ledger_type;
  if (type === "fund" || type === "bank") return true;
  if (type === "stock" && selectedPosition.value?.type === "fund") return true;
  return false;
});

// 计算实际可用于费率计算的买入总份额
const totalCalculatedHold = computed(() => {
  return holdFeeDetails.value.reduce((sum, item) => sum + item.shares, 0);
});

// 当前输入的份额（>0 时有效）
const enteredShares = computed(() => {
  const q = form.quantity;
  return q !== undefined && q !== null && q > 0 ? q : 0;
});

// 合并全仓和指定份额数据，用于弹窗表格
const mergedFeeData = computed(() => {
  const holdData = holdFeeDetails.value;
  const sellData = sellFeeData.value;
  if (holdData.length === 0) return [];
  const sellMap: Record<number, number> = {};
  sellData.forEach((item: any) => {
    sellMap[item.rate] = (sellMap[item.rate] || 0) + item.shares;
  });
  return holdData.map((h: any) => ({
    range: h.range,
    rate: h.rate,
    holdShares: h.shares,
    sellShares: sellMap[h.rate] ?? 0
  }));
});

const validateQuantity = (_rule: any, value: any, callback: any) => {
  if (value === undefined || value === null || value === "") {
    callback(
      new Error(form.type === "fund" ? "请输入卖出份额" : "请输入卖出数量")
    );
  } else {
    callback();
  }
};

// 股票成交价区间校验已统一到 useSecurityPrice.createStockPriceValidator（#948 统一约束）

const rules: FormRules = {
  ledger_id: [{ required: true, message: "请选择账户", trigger: "change" }],
  positionId: [
    { required: true, message: "请选择持仓产品", trigger: "change" }
  ],
  quantity: [{ validator: validateQuantity, trigger: "blur" }],
  price: [
    {
      validator: createStockPriceValidator(
        () => stockPriceRange.value,
        () => form.type === "stock"
      ),
      trigger: "blur"
    }
  ],
  trade_date: [{ required: true, message: "请选择日期", trigger: "change" }]
};

// ---------- 数据获取 ----------
async function fetchPositionsByAccount() {
  try {
    const res = await getPositionsGroupedByAccount();
    positionsByAccount.value = res?.data ?? {};
    const ids = new Set<number>();
    for (const accountName in positionsByAccount.value) {
      const positions = positionsByAccount.value[accountName];
      positions.forEach(p => {
        if (p.ledger_id) ids.add(p.ledger_id);
      });
    }
    emit("positions-loaded", Array.from(ids));
  } catch {
    positionsByAccount.value = {};
    emit("positions-loaded", []);
  }
}

// ---------- 交互方法 ----------
function applySellQuickRatio(ratio: number) {
  form.quantity = calcSellQuantityByRatio(
    ratio,
    maxQuantity.value,
    form.type,
    stepForSecurity.value
  );
}

function clearFormData() {
  qtyTouched.value = false;
  showPositionSelect.value = false;
  nextTick(() => {
    const currentLedgerId = form.ledger_id;
    const defaults = defaultForm();
    Object.keys(defaults).forEach(key => {
      (form as any)[key] = defaults[key];
    });
    form.ledger_id = currentLedgerId;
    form.positionId = null;

    selectedPosition.value = null;
    feeManuallyChanged.value = false;
    resetTradeDate();
    holdFeeDetails.value = [];
    sellFeeData.value = [];
    feeRateDialogVisible.value = false;

    +positionSelectKey.value++;
    formRef.value?.clearValidate();
    showPositionSelect.value = true;
  });
}

function onAccountChange(_ledgerId: number) {
  // 直接调用 clearFormData，它内部会保存并恢复 ledger_id
  clearFormData();
}

function onPositionSelect(positionId: number) {
  const pos = accountPositions.value.find(p => p.id === positionId);
  if (!pos) return;
  selectedPosition.value = pos;
  form.symbol = pos.symbol;
  form.name = pos.name;
  form.market = pos.market;
  form.type = pos.type;
  form.currency = pos.currency;
  form.price = pos.current_price ?? pos.avg_price;
  form.quantity = undefined;
  qtyTouched.value = false;
  form.fee = 0;
  feeManuallyChanged.value = false;
  resetTradeDate();
  calculateFeeAndRate();
  // 股票价格区间由 useSecurityPriceRange 随持仓/交易日自动刷新（#948 统一约束）
}

// fetchConfirmAndNavDate 已移至 useFundTradeDate composable，与其他组件共用

// ---------- 费率请求（改造为使用新后端接口） ----------
const fetchFundFeeRules = async (
  positionId: number,
  tradeDate: string,
  shares?: number
) => {
  const payload: any = {
    position_id: positionId,
    sell_date: tradeDate
  };
  if (shares !== undefined && shares !== null && shares > 0) {
    payload.shares = shares;
  }
  const res: any = await estimateRedeemFee(payload);
  const data = res.data;
  return {
    total_fee: data?.total_fee || 0,
    holdings: (data?.holdings || []).map((r: any) => ({
      range: r.range,
      shares: r.shares,
      rate: r.rate
    })),
    sell: (data?.sell || []).map((r: any) => ({
      range: r.range,
      shares: r.shares,
      rate: r.rate
    }))
  };
};

const calculateFeeAndRate = async () => {
  if (!selectedPosition.value || form.type !== "fund" || !form.trade_date) {
    form.fee = 0;
    holdFeeDetails.value = [];
    sellFeeData.value = [];
    feeError.value = "";
    return;
  }
  const buyDate = selectedPosition.value.confirm_date;
  if (!buyDate) {
    holdFeeDetails.value = [];
    sellFeeData.value = [];
    feeError.value = "";
    return;
  }

  try {
    const { total_fee, holdings, sell } = await fetchFundFeeRules(
      selectedPosition.value.id,
      form.trade_date,
      form.quantity || 0
    );
    if (!feeManuallyChanged.value) {
      form.fee = total_fee;
    }
    holdFeeDetails.value = holdings;
    sellFeeData.value = sell.length > 0 ? sell : [];
    feeRateTableData.value = holdings;
    feeError.value = "";
  } catch (e: any) {
    // 从 Axios 错误中提取后端返回的 message
    let msg = "暂时无法获取费率分布";
    if (e?.response?.data?.message) {
      msg = e.response.data.message; // 后端返回的业务错误消息
    } else if (e?.message) {
      msg = e.message;
    }
    console.warn("费率查询失败", msg, e);
    holdFeeDetails.value = [];
    sellFeeData.value = [];
    feeError.value = msg;
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
  await calculateFeeAndRate();

  if (holdFeeDetails.value.length === 0) {
    if (feeError.value.includes("暂无赎回费率规则")) {
      // 自定义弹窗：提供“更新费率”按钮
      ElMessageBox.confirm(
        "该基金尚未收录费率信息，是否立即更新？",
        "费率数据缺失",
        {
          confirmButtonText: "立即更新",
          cancelButtonText: "我知道了",
          type: "warning",
          beforeClose: async (action, instance, done) => {
            if (action === "confirm") {
              instance.confirmButtonLoading = true;
              try {
                await syncFundFees(selectedPosition.value.symbol);
                ElMessage.success("费率更新成功");
                // 重新计算费率（此时应该能获取到数据）
                await calculateFeeAndRate();
                if (holdFeeDetails.value.length > 0) {
                  feeRateDialogVisible.value = true; // 打开费率分布弹窗
                } else {
                  ElMessage.info("费率已更新但仍无法计算，请手动输入费用");
                }
              } catch (e: any) {
                ElMessage.error("更新失败，请稍后重试或手动输入费用");
              } finally {
                instance.confirmButtonLoading = false;
                done();
              }
            } else {
              done();
            }
          }
        }
      );
    } else {
      ElMessage.error(feeError.value || "暂时无法获取费率分布");
    }
    return;
  }
  // 正常打开费率分布
  feeRateDialogVisible.value = true;
};

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

  // 统一提交层（#933）：修复原空 catch 吞错——失败提示由本层统一弹出
  const { submitPosition } = usePositionSubmit();
  const ok = await submitPosition(body);
  if (ok) {
    emit("submit-success");
  }
}

function resetForm() {
  Object.assign(form, defaultForm());
  selectedPosition.value = null;
  positionsByAccount.value = {};
  feeManuallyChanged.value = false;
  formRef.value?.resetFields();
  positionSelectKey.value++;

  if (props.hideAccountSelect && props.defaultLedgerId) {
    form.ledger_id = props.defaultLedgerId;
  }
}

// ---------- 监听 ----------
// 交易日期/15点后/标的 变化：基金拉取当日净值回填，股票刷新价格区间。
// 不依赖 form.price，避免回填净值时触发自身监听造成循环或覆盖用户手动改价。
watch(
  [() => form.trade_date, () => form.isAfter15, () => selectedPosition.value],
  async () => {
    if (!selectedPosition.value) return;
    if (form.type === "fund" && form.trade_date) {
      const pos = selectedPosition.value;
      const result = await calcConfirmAndNav({
        tradeDate: form.trade_date,
        symbol: pos.symbol,
        isAfter15: form.isAfter15
      });
      if (result?.nav != null) {
        form.price = result.nav;
      }
    }
    // 股票价格区间由 useSecurityPriceRange 随持仓/交易日自动刷新（#948 统一约束）
  }
);

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

defineExpose({ handleSubmit, resetForm });
</script>

<style scoped>
.text-xs {
  font-size: 0.75rem;
}

.quick-ratio-btn {
  height: 28px;
  padding: 0 8px;
  font-size: 0.75rem;
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

/* 输入框通用 */
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

/* 避免校验错误过渡闪烁 */
:deep(.el-form-item__error) {
  transition: none;
}
</style>
