<template>
  <div class="conversion-form flex flex-col gap-6">
    <!-- 四步步骤条（视觉与导入页一致：el-steps align-center + finish-status success） -->
    <el-steps
      :active="step"
      finish-status="success"
      align-center
      class="conversion-steps"
    >
      <el-step
        v-for="(title, index) in stepTitles"
        :key="index"
        :title="title"
      />
    </el-steps>

    <!-- ===== 第 1 步：选择转出 ===== -->
    <div v-if="step === 0" class="flex flex-col gap-5">
      <el-form label-width="90px" size="large" class="flex flex-col gap-5">
        <el-form-item label="转出基金">
          <el-select
            v-model="form.positionId"
            class="w-full"
            filterable
            placeholder="选择要转出的持仓"
            @change="onOutPositionChange"
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
                  :style="{ color: 'var(--text-tertiary-ink)' }"
                >
                  可用 {{ Number(pos.quantity).toFixed(2) }} 份
                </span>
              </div>
            </el-option>
          </el-select>
          <div
            v-if="!loadingPositions && accountPositions.length === 0"
            class="text-xs mt-1"
            style="color: var(--text-tertiary-ink)"
          >
            当前账户暂无基金持仓，无法转换。请先切换账户或记一笔申购。
          </div>
        </el-form-item>

        <template v-if="form.positionId">
          <el-form-item label="交易日期">
            <div class="flex items-center gap-3 w-full">
              <el-date-picker
                v-model="form.trade_date"
                type="date"
                class="flex-1"
                style="width: 100%"
                value-format="YYYY-MM-DD"
                :clearable="false"
                :disabled-date="disabledTradeDate"
              />
              <el-radio-group v-model="form.isAfter15" size="small">
                <el-radio-button :value="false">15:00前</el-radio-button>
                <el-radio-button :value="true">15:00后</el-radio-button>
              </el-radio-group>
            </div>
            <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
              15:00 后提交按下一交易日（T+1）净值计算
            </div>
          </el-form-item>

          <el-form-item label="转出份额">
            <div class="flex flex-col gap-2 w-full">
              <el-input-number
                v-model="form.quantity"
                class="w-full"
                :controls="false"
                :min="0"
                :max="maxQuantity"
                :step="0.01"
                :precision="2"
                placeholder="输入转出份额"
                @change="onQuantityInput"
              />
              <div class="flex items-center justify-between w-full">
                <el-button
                  v-for="ratio in TRANSFER_QUICK_RATIOS"
                  :key="ratio.label"
                  size="small"
                  plain
                  round
                  @click="applyQuickRatio(ratio.value)"
                >
                  {{ ratio.label }}
                </el-button>
              </div>
              <div class="text-xs" style="color: var(--text-tertiary-ink)">
                持有 {{ maxQuantity.toFixed(4) }} 份；「全部」按持仓精确值转出
              </div>
            </div>
          </el-form-item>
        </template>
      </el-form>
      <div class="flex justify-end">
        <el-button type="primary" :disabled="!step1Valid" @click="step = 1">
          下一步
        </el-button>
      </div>
    </div>

    <!-- ===== 第 2 步：选择转入 ===== -->
    <div v-else-if="step === 1" class="flex flex-col gap-5">
      <el-form label-width="90px" size="large" class="flex flex-col gap-5">
        <!-- 当前账户已持有的置顶快选（与 BuyForm 同一搜索源；不做两套搜索框） -->
        <el-form-item v-if="inFundCandidates.length" label="当前持有">
          <div class="flex flex-wrap gap-2">
            <el-button
              v-for="pos in inFundCandidates"
              :key="pos.id"
              size="small"
              :type="form.inSymbol === pos.symbol ? 'primary' : 'default'"
              round
              @click="pickInFund(pos.symbol, pos.name || pos.symbol)"
            >
              {{ pos.name || pos.symbol }}
            </el-button>
          </div>
        </el-form-item>

        <el-form-item label="转入基金">
          <el-select
            v-model="form.inSymbol"
            class="w-full"
            filterable
            remote
            :remote-method="remoteSearchFunds"
            :loading="searchLoading"
            placeholder="搜索基金代码或名称"
            @change="onInFundChange"
          >
            <el-option
              v-for="f in inFundOptions"
              :key="f.code"
              :value="f.code"
              :label="`${f.name}（${f.code}）`"
            >
              <div class="flex justify-between items-center w-full">
                <span class="truncate">{{ f.name }}</span>
                <span
                  class="text-xs"
                  :style="{ color: 'var(--text-tertiary-ink)' }"
                  >{{ f.code }}</span
                >
              </div>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="转入金额">
          <el-input-number
            v-model="form.inAmount"
            class="w-full"
            :controls="false"
            :min="0"
            :step="0.01"
            :precision="2"
            placeholder="留空 = 净额全部转入"
          />
          <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
            留空表示净额（转出金额 −
            费用）全部买入转入基金；指定更小金额时，差额需选退款去向
          </div>
        </el-form-item>
      </el-form>
      <div class="flex justify-between">
        <el-button @click="step = 0">上一步</el-button>
        <el-button type="primary" :disabled="!step2Valid" @click="gotoStep3">
          下一步
        </el-button>
      </div>
    </div>

    <!-- ===== 第 3 步：费用与确认 ===== -->
    <div v-else-if="step === 2" class="flex flex-col gap-4">
      <div
        v-if="estimating"
        class="p-6 text-center text-sm"
        :style="{ color: 'var(--text-secondary)' }"
      >
        正在试算费用与份额…
      </div>
      <template v-else-if="estimate">
        <!-- 摘要两列键值对齐（design.md：左标签 secondary、右数值 tabular-nums） -->
        <div class="estimate-panel flex flex-col gap-3">
          <div class="panel-row">
            <span class="panel-label">转出</span>
            <span class="panel-value">
              {{ estimate.out.name || estimate.out.symbol }} ·
              {{ estimate.out.quantity.toFixed(2) }} 份 ×
              {{ estimate.out.nav.toFixed(4) }}
            </span>
          </div>
          <div class="panel-row">
            <span class="panel-label">转出金额</span>
            <span class="panel-value"
              >¥{{ estimate.out.amount.toFixed(2) }}</span
            >
          </div>
          <div class="panel-row">
            <span class="panel-label">赎回费</span>
            <span class="panel-value">
              −¥{{ estimate.out.fee_breakdown.redeem.toFixed(2) }}
            </span>
          </div>
          <div class="panel-row">
            <span class="panel-label">补差费</span>
            <span class="panel-value">
              −¥{{ estimate.out.fee_breakdown.compensate.toFixed(2) }}
            </span>
          </div>
          <div class="panel-row panel-row-total">
            <span class="panel-label">费用合计</span>
            <span class="panel-value">−¥{{ estimate.out.fee.toFixed(2) }}</span>
          </div>
          <div class="panel-row">
            <span class="panel-label">净转入金额</span>
            <span class="panel-value"
              >¥{{ estimate.net_amount.toFixed(2) }}</span
            >
          </div>
          <div class="panel-row">
            <span class="panel-label">
              预估份额
              <el-tag size="small" type="info" effect="plain">预估</el-tag>
            </span>
            <span class="panel-value">
              {{ estimate.in.symbol }} ·
              {{ estimate.in.quantity.toFixed(2) }} 份（净值
              {{ estimate.in.nav.toFixed(4) }}）
            </span>
          </div>
          <div class="panel-row">
            <span class="panel-label">预计确认日</span>
            <span class="panel-value"
              >{{ estimate.trade_date }} 提交 · T+1 确认</span
            >
          </div>
        </div>

        <!-- 退款去向（有差额时必选；默认取账户绑定的类现金产品） -->
        <el-form
          v-if="estimate.refund.amount > 0"
          label-width="90px"
          size="large"
        >
          <el-form-item label="退款去向" required>
            <el-radio-group v-model="form.refundMode">
              <el-radio-button
                v-for="opt in estimate.refund.options"
                :key="opt.type"
                :value="opt.type"
              >
                {{ opt.name }}
              </el-radio-button>
            </el-radio-group>
            <div class="text-xs mt-1" style="color: var(--text-tertiary-ink)">
              指定转入金额小于净额，差额 ¥{{
                estimate.refund.amount.toFixed(2)
              }}
              需退回到以下位置，不允许凭空消失
            </div>
          </el-form-item>
        </el-form>

        <!-- 费率缺失等非阻断告警（D9：显式提示，不静默） -->
        <div
          v-for="w in estimate.warnings"
          :key="w"
          class="p-3 rounded-lg text-xs flex items-start gap-2"
          :style="{
            color: 'var(--color-warning-ink)',
            backgroundColor: 'var(--bg-soft)'
          }"
        >
          <IconifyIconOffline icon="ep:warning-filled" class="mt-0.5" />
          <span>{{ w }}</span>
        </div>

        <!-- 固定说明：预估口径 -->
        <div
          class="p-3 rounded-lg text-xs"
          :style="{
            color: 'var(--text-secondary)',
            backgroundColor: 'var(--bg-soft)'
          }"
        >
          以上金额按 {{ estimate.trade_date }} 净值预估，实际以 T
          日净值确认结果为准，T+1 确认、T+2 可赎回。
        </div>
      </template>
      <div
        v-else
        class="p-6 text-center text-sm flex flex-col items-center gap-3"
        :style="{ color: 'var(--color-danger)' }"
      >
        <span>{{ estimateError || "试算失败" }}</span>
        <el-button size="small" @click="runEstimate">重试</el-button>
      </div>

      <div class="flex justify-between">
        <el-button :disabled="submitting" @click="step = 1">上一步</el-button>
        <el-button
          type="primary"
          :loading="submitting"
          :disabled="!submitValid"
          @click="submit"
        >
          确认转换
        </el-button>
      </div>
    </div>

    <!-- ===== 第 4 步：结果 ===== -->
    <div v-else class="flex flex-col items-center gap-4 py-4">
      <IconifyIconOffline
        icon="ep:success-filled"
        class="text-5xl"
        :style="{ color: 'var(--color-success)' }"
      />
      <div
        class="text-base font-medium"
        :style="{ color: 'var(--text-primary)' }"
      >
        转换已提交
      </div>
      <div class="text-sm" :style="{ color: 'var(--text-secondary)' }">
        申请单号 {{ result?.group_no || "--" }} · 待确认（T+1）
      </div>
      <div v-if="result" class="estimate-panel w-full flex flex-col gap-3">
        <div class="panel-row">
          <span class="panel-label">转出</span>
          <span class="panel-value">
            {{ result.out.name || result.out.symbol }} ·
            {{ result.out.quantity.toFixed(2) }} 份
          </span>
        </div>
        <div class="panel-row">
          <span class="panel-label">费用合计</span>
          <span class="panel-value">−¥{{ result.out.fee.toFixed(2) }}</span>
        </div>
        <div class="panel-row">
          <span class="panel-label">转入</span>
          <span class="panel-value">
            {{ result.in.name || result.in.symbol }} ·
            {{ result.in.quantity.toFixed(2) }} 份（预估）
          </span>
        </div>
        <div v-if="result.refund.amount > 0" class="panel-row">
          <span class="panel-label">退款</span>
          <span class="panel-value">
            ¥{{ result.refund.amount.toFixed(2) }} ·
            {{
              result.refund.mode === "money_fund" ? "类现金产品" : "账户现金"
            }}
          </span>
        </div>
      </div>
      <div class="text-xs" style="color: var(--text-tertiary-ink)">
        确认后份额以 T 日净值清算结果为准，可在交易记录中查看本组流水。
      </div>
      <el-button type="primary" @click="finish">完成</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from "vue";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  estimateConversion,
  submitConversion,
  getPositionsGroupedByAccount,
  type ConversionEstimateResult,
  type ConversionSubmitResult
} from "@/api/positions";
import { searchFunds, type FundSearchItem } from "@/api/funds";
import type { Position } from "@/api/types";
import { disabledTradeDate } from "@/utils/date";
import { calcSellQuantityByRatio } from "@/utils/trading";

const props = defineProps<{
  ledgers: any[];
  defaultLedgerId?: number | null;
}>();
const emit = defineEmits<{
  (e: "submit-success"): void;
  (e: "positions-loaded", ledgerIds: number[]): void;
}>();

const stepTitles = ["选择转出", "选择转入", "费用与确认", "结果"];
const step = ref(0);

// 25/50/75/100% 快捷比例（与 SellForm 同一工具；100% 走后端「全部转出」精确值语义）
const TRANSFER_QUICK_RATIOS = [
  { label: "25%", value: 0.25 },
  { label: "50%", value: 0.5 },
  { label: "75%", value: 0.75 },
  { label: "全部", value: 1 }
];

// ── 持仓（按账户分组拉取，与 SellForm 同源） ──
const positionsByAccount = ref<Record<string, Position[]>>({});
const loadingPositions = ref(false);

const ledgerId = computed(() => props.defaultLedgerId ?? null);

/** 当前账户的**基金**持仓（货基/逆回购不参与转换：转出无费率阶梯语义） */
const accountPositions = computed<Position[]>(() => {
  const all: Position[] = [];
  for (const list of Object.values(positionsByAccount.value)) all.push(...list);
  return all.filter(p => p.ledger_id === ledgerId.value && p.type === "fund");
});

async function loadPositions() {
  loadingPositions.value = true;
  try {
    const res = await getPositionsGroupedByAccount();
    const data = (res?.data ?? {}) as Record<string, Position[]>;
    positionsByAccount.value = data;
    // 有基金持仓的账户才允许选「转换」（父页据此过滤账户下拉）
    const ledgerIds = new Set<number>();
    for (const list of Object.values(data)) {
      for (const p of list) {
        if (p.type === "fund" && p.ledger_id != null)
          ledgerIds.add(p.ledger_id);
      }
    }
    emit("positions-loaded", [...ledgerIds]);
  } catch {
    positionsByAccount.value = {};
  } finally {
    loadingPositions.value = false;
  }
}

// ── 表单状态 ──
const defaultForm = () => ({
  positionId: null as number | null,
  quantity: undefined as number | undefined,
  trade_date: new Date().toISOString().slice(0, 10),
  isAfter15: false,
  inSymbol: "",
  inName: "",
  inAmount: undefined as number | undefined,
  refundMode: "" as "" | "money_fund" | "account_cash"
});
const form = reactive(defaultForm());

/** 「全部」转出：不传 out_quantity，后端按持仓 4 位精确值处理（D8/§5.2） */
const transferAll = ref(false);

const selectedPosition = computed(
  () => accountPositions.value.find(p => p.id === form.positionId) || null
);
const maxQuantity = computed(() =>
  Number(selectedPosition.value?.quantity ?? 0)
);

const step1Valid = computed(() => {
  if (!form.positionId || !form.trade_date) return false;
  if (transferAll.value) return true;
  return (
    !!form.quantity &&
    form.quantity > 0 &&
    form.quantity <= maxQuantity.value + 1e-9
  );
});

const step2Valid = computed(() => {
  if (!form.inSymbol) return false;
  return form.inSymbol !== (selectedPosition.value?.symbol ?? "");
});

function onOutPositionChange() {
  transferAll.value = false;
  form.quantity = undefined;
}

function onQuantityInput() {
  transferAll.value = false;
}

function applyQuickRatio(ratio: number) {
  if (!selectedPosition.value) return;
  if (ratio >= 1) {
    transferAll.value = true;
    form.quantity = maxQuantity.value;
    return;
  }
  transferAll.value = false;
  // 基金份额步长 1（份），向下取整到 2 位由输入框精度约束
  form.quantity = calcSellQuantityByRatio(ratio, maxQuantity.value, "fund", 1);
}

// ── 转入基金搜索（与 BuyForm 同源：基金账户走 searchFunds） ──
const searchLoading = ref(false);
const inFundOptions = ref<FundSearchItem[]>([]);

async function remoteSearchFunds(query: string) {
  if (!query) {
    inFundOptions.value = [];
    return;
  }
  searchLoading.value = true;
  try {
    const res = await searchFunds(query);
    const arr = Array.isArray(res) ? res : (res?.data ?? []);
    // 货基不作为转换转入（后端亦拦截；前端先滤避免无效试算）
    inFundOptions.value = arr.filter(
      (f: FundSearchItem) => f.is_money_fund !== true
    );
  } catch {
    inFundOptions.value = [];
    ElMessage.warning("搜索服务暂不可用，请稍后重试");
  } finally {
    searchLoading.value = false;
  }
}

/** 第 2 步「当前持有」快选：排除转出基金本身 */
const inFundCandidates = computed(() =>
  accountPositions.value.filter(
    p => p.symbol !== selectedPosition.value?.symbol
  )
);

function pickInFund(symbol: string, name: string) {
  form.inSymbol = symbol;
  form.inName = name;
}

function onInFundChange(code: string) {
  const hit = inFundOptions.value.find(f => f.code === code);
  form.inName = hit?.name ?? code;
}

// ── 试算（debounce 400ms + 请求序号防倒序覆盖，§6.3.5） ──
const estimating = ref(false);
const estimate = ref<ConversionEstimateResult | null>(null);
const estimateError = ref("");
let estimateSeq = 0;
let estimateTimer: ReturnType<typeof setTimeout> | null = null;

async function runEstimate() {
  if (!form.positionId || !form.inSymbol) return;
  const my = ++estimateSeq;
  estimating.value = true;
  estimateError.value = "";
  try {
    const res = await estimateConversion({
      ledger_id: ledgerId.value,
      out_position_id: form.positionId,
      out_quantity: transferAll.value ? null : (form.quantity ?? null),
      in_symbol: form.inSymbol,
      in_amount: form.inAmount ?? null,
      trade_date: form.trade_date
    });
    if (my !== estimateSeq) return; // 过期响应丢弃
    estimate.value = (res?.data ?? null) as ConversionEstimateResult | null;
    // 退款去向默认值：优先账户绑定的类现金产品（D7）
    if (
      estimate.value &&
      estimate.value.refund.amount > 0 &&
      !form.refundMode
    ) {
      const first = estimate.value.refund.options[0];
      if (first) form.refundMode = first.type;
    }
  } catch (e: any) {
    if (my !== estimateSeq) return;
    estimate.value = null;
    estimateError.value =
      e?.response?.data?.message || e?.message || "试算失败";
  } finally {
    if (my === estimateSeq) estimating.value = false;
  }
}

function scheduleEstimate() {
  if (estimateTimer) clearTimeout(estimateTimer);
  estimateTimer = setTimeout(runEstimate, 400);
}

// 进入第 3 步：清掉旧试算并立即重算（避免展示上一批参数的数字）
function gotoStep3() {
  if (!step2Valid.value) return;
  if (estimateTimer) clearTimeout(estimateTimer);
  estimate.value = null;
  estimateError.value = "";
  step.value = 2;
  void runEstimate();
}

// 第 3 步内任何参数变化 → 防抖重算
watch(
  [
    () => form.positionId,
    () => form.quantity,
    () => form.trade_date,
    () => form.isAfter15,
    () => form.inSymbol,
    () => form.inAmount,
    transferAll
  ],
  () => {
    if (step.value !== 2) return;
    if (!step2Valid.value) return;
    scheduleEstimate();
  }
);

const submitValid = computed(() => {
  if (!estimate.value || estimating.value) return false;
  if (estimate.value.supplement.required) return false; // D6：垫资前端先拦
  if (estimate.value.refund.amount > 0 && !form.refundMode) return false;
  return true;
});

// ── 提交 ──
const submitting = ref(false);
const result = ref<ConversionSubmitResult | null>(null);
/** 幂等键：每次「提交意图」一个 UUID；失败重试沿用同键（与 usePositionSubmit 同约定） */
let idempotencyKey = "";

function genIdempotencyKey(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

async function submit() {
  if (submitting.value || !form.positionId) return;
  if (!idempotencyKey) idempotencyKey = genIdempotencyKey();
  submitting.value = true;
  try {
    const res = await submitConversion({
      ledger_id: ledgerId.value,
      out_position_id: form.positionId,
      out_quantity: transferAll.value ? null : (form.quantity ?? null),
      in_symbol: form.inSymbol,
      in_amount: form.inAmount ?? null,
      refund_mode: form.refundMode || null,
      trade_date: form.trade_date,
      idempotency_key: idempotencyKey
    });
    result.value = (res?.data ?? null) as ConversionSubmitResult | null;
    step.value = 3;
  } catch (e: any) {
    if (e?.response?.status === 409) {
      // 幂等命中（重复点击/网络重发）：已在库，直接进结果步展示原组号
      const dup = e?.response?.data?.data;
      ElMessage.info(
        e?.response?.data?.message || "该笔转换已记录，请勿重复提交"
      );
      result.value = dup?.link_group_id
        ? ({
            link_group_id: dup.link_group_id,
            group_no: dup.link_group_id,
            status: "pending",
            trade_date: form.trade_date,
            confirm_date: "",
            out: estimate.value?.out ?? {
              symbol: selectedPosition.value?.symbol ?? "",
              name: selectedPosition.value?.name ?? null,
              quantity: form.quantity ?? 0,
              nav: 0,
              amount: 0,
              fee: 0,
              fee_breakdown: { redeem: 0, compensate: 0 },
              realized_pnl_estimate: 0
            },
            in: {
              ...(estimate.value?.in ?? {
                symbol: form.inSymbol,
                name: form.inName || null,
                nav: 0,
                amount: 0,
                quantity: 0
              }),
              position_id: null
            },
            refund: {
              amount: estimate.value?.refund.amount ?? 0,
              mode: form.refundMode || null,
              txn_id: null
            },
            warnings: []
          } as ConversionSubmitResult)
        : null;
      step.value = 3;
    } else {
      ElMessage.error(
        e?.response?.data?.message || e?.message || "转换提交失败"
      );
    }
  } finally {
    submitting.value = false;
  }
}

function finish() {
  emit("submit-success");
}

// ── 未保存守卫（#1891）：第 1~3 步有已填内容即视为脏 ──
const isDirty = computed(
  () =>
    step.value < 3 &&
    (!!form.positionId ||
      !!form.quantity ||
      !!form.inSymbol ||
      !!form.inAmount ||
      !!form.refundMode)
);

function resetForm() {
  Object.assign(form, defaultForm());
  transferAll.value = false;
  estimate.value = null;
  estimateError.value = "";
  result.value = null;
  idempotencyKey = "";
  step.value = 0;
}

onMounted(loadPositions);

// 父页切换账户：重新拉持仓并复位步骤（旧账户的持仓/试算对新账户无意义）
watch(ledgerId, () => {
  resetForm();
  loadPositions();
});

defineExpose({ isDirty, resetForm });
</script>

<style scoped>
.conversion-steps {
  margin-bottom: 8px;
}

/* 试算面板：两列键值对齐（左标签 secondary、右数值 tabular-nums；净额加粗） */
.estimate-panel {
  padding: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.panel-row {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
}

.panel-label {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  color: var(--text-secondary);
  white-space: nowrap;
}

.panel-value {
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
  text-align: right;
}

.panel-row-total .panel-value {
  font-weight: 600;
}
</style>
