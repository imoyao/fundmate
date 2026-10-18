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

    <!-- ===== 第 1 步：填写转出与转入（两栏并置，#2348） ===== -->
    <div v-if="step === 0" class="flex flex-col gap-5">
      <!-- 转换是 1→1 的双腿操作：拆成两步问会让用户来回翻页核对「卖的和买的是不是同一笔」，
           券商确认页也都是同屏左右对照。栏间分割线走全局工具类 `.soft-col-divider`
           （lg 及以上才出现 24px 内距 + 1px 线，lg 以下两栏堆叠不画孤线，
           见 design.md §栏间竖向分割线），不手写 border。 -->
      <div class="convert-grid grid grid-cols-1 gap-6 lg:grid-cols-12">
        <section class="lg:col-span-7">
          <!-- 栏头不重复标签里的「转出基金」，而是交代这条腿在后台是什么动作：
               转换 = 赎回 + 申购，这一点用户从界面上看不出来 -->
          <h3 class="convert-col__title">转出（赎回）</h3>
          <!-- 半屏列宽放不下 90px 横排标签（输入框会被压成一条缝），故标签在上 -->
          <el-form
            label-position="top"
            size="large"
            class="flex flex-col gap-4"
          >
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
                <!-- 日期框吃满剩余宽度，右端与上方「转出基金」右边缘对齐；
                 时点切换按 design.md「Segmented」走软按钮，不用实底 radio-button
                 （实底品牌色会与主按钮撞脸、抢走页面唯一供能焦点，#1731）。 -->
                <div class="field-row">
                  <!-- 外层 div 才是 flex item：EP 的 DatePicker 是 inheritAttrs:false，
                   直接写在它上面的 class 不会落到渲染出来的 `.el-input.el-date-editor` 上
                   （实测宽度仍是写死的 220px）。宽度走内联 100%，与外层 flex 配合。 -->
                  <div class="field-row__grow">
                    <el-date-picker
                      v-model="form.trade_date"
                      type="date"
                      style="width: 100%"
                      value-format="YYYY-MM-DD"
                      :clearable="false"
                      :disabled-date="disabledTradeDate"
                    />
                  </div>
                  <TradeSlotSwitch v-model="form.isAfter15" />
                </div>
                <div class="helper">
                  15:00 后提交按下一交易日（T+1）净值计算
                </div>
              </el-form-item>

              <el-form-item label="转出份额">
                <div class="quantity-field">
                  <!-- 宽度必须内联：EP 给 .el-input-number 写死 width:150px，
                   且其样式在运行时注入、晚于构建产物里的 w-full，类名会被压掉。 -->
                  <el-input-number
                    v-model="form.quantity"
                    style="width: 100%"
                    :controls="false"
                    :min="0"
                    :max="maxQuantity"
                    :step="0.01"
                    :precision="2"
                    placeholder="输入转出份额"
                    @change="onQuantityInput"
                  />
                  <!-- 比例档位：与卖出表单同一组件（档位表 / 取整 / 选中态唯一实现）；
                   选中态由 quantity 反算，手改数值自动掉高亮 -->
                  <div class="quick-ratio-row">
                    <QuickRatioPicker
                      v-model="form.quantity"
                      :total="maxQuantity"
                      type="fund"
                      aria-label="转出份额比例"
                      @select="onQuickRatioSelect"
                    />
                    <span class="hold-hint">
                      持有 {{ maxQuantity.toFixed(4) }} 份
                    </span>
                  </div>
                  <div class="helper">
                    {{
                      transferAll
                        ? "当前为全部转出：按持仓精确值清算，不抹零"
                        : "份额最多 2 位小数；「全部」按持仓精确值转出"
                    }}
                  </div>
                </div>
              </el-form-item>
            </template>
          </el-form>
        </section>

        <!-- 右栏：转入 -->
        <section class="lg:col-span-5 soft-col-divider">
          <h3 class="convert-col__title">转入（申购）</h3>
          <el-form
            label-position="top"
            size="large"
            class="flex flex-col gap-4"
          >
            <!-- 当前账户已持有的置顶快选（与 BuyForm 同一搜索源；不做两套搜索框） -->
            <el-form-item v-if="inFundCandidates.length" label="当前持有">
              <div class="flex flex-wrap gap-2">
                <el-button
                  v-for="pos in inFundCandidates"
                  :key="pos.id"
                  size="small"
                  round
                  :class="{ 'is-picked': form.inSymbol === pos.symbol }"
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
                <!-- 「当前持有」快选不经过搜索结果，选项里没有它 ⇒ el-select 会把
                     绑定的代码原样显示成「002340」。补一个只含标签的选项把它接住，
                     不伪造 `FundSearchItem` 的 type / subscription_rate 字段。 -->
                <el-option
                  v-if="
                    pickedInOption &&
                    !inFundOptions.some(f => f.code === pickedInOption?.value)
                  "
                  :key="pickedInOption.value"
                  :value="pickedInOption.value"
                  :label="pickedInOption.label"
                />
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

            <el-form-item label="转入">
              <!-- 口径切换独占一行：半屏列宽下与输入框并排会把数字框压到 190px 以内 -->
              <div class="in-amount-field">
                <SegmentedControl
                  v-model="form.inMode"
                  :options="inModeOptions"
                  class="in-amount-field__switch"
                  aria-label="转入口径"
                />
                <el-input-number
                  v-if="form.inMode === 'amount'"
                  v-model="form.inAmount"
                  style="width: 100%"
                  :controls="false"
                  :min="0"
                  :step="0.01"
                  :precision="2"
                  placeholder="留空 = 净额全部转入"
                />
                <!-- 份额口径：确认单上写的是份额，按金额反算会差 0.0001（#2348） -->
                <el-input-number
                  v-else
                  v-model="form.inQuantity"
                  style="width: 100%"
                  :controls="false"
                  :min="0"
                  :step="0.01"
                  :precision="2"
                  placeholder="留空 = 净额全部转入"
                />
                <div class="helper">
                  {{
                    form.inMode === "amount"
                      ? "留空表示净额（转出金额 − 费用）全部买入转入基金；指定更小金额时，差额需选去向"
                      : "按份额转入：金额由「份额 × 转入净值」派生，差额同样需选去向"
                  }}
                </div>
              </div>
            </el-form-item>
          </el-form>
        </section>
      </div>

      <!-- 差额去向：金额要试算后才知道，所以「选哪一档」放在下一步；
           但「差额不会凭空消失」这条规则必须在填写时就看得见（#2348 用户提问）。 -->
      <div class="convert-note">
        <IconifyIconOffline icon="ep:info-filled" class="convert-note__icon" />
        <span>
          转入金额小于「转出金额 −
          费用」时会产生差额，差额退回账户绑定的货币基金
          （账户未绑定则退回账户现金），下一步可改——不会凭空消失。
        </span>
      </div>

      <div class="flex justify-end">
        <el-button type="primary" :disabled="!inputValid" @click="gotoConfirm">
          下一步
        </el-button>
      </div>
    </div>

    <!-- ===== 第 2 步：费用与确认 ===== -->
    <div v-else-if="step === 1" class="flex flex-col gap-4">
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
          <!-- 费用行可编辑（#2348）：确认单上的费用常与费率表算出值不一致，
               只读会让账实永远差几分钱。改后由服务端重算净额/份额/差额。 -->
          <div class="panel-row">
            <span class="panel-label">赎回费</span>
            <div class="fee-cell">
              <span class="fee-sign">−¥</span>
              <el-input-number
                v-model="feeInputs.redeem"
                class="fee-input"
                aria-label="赎回费（可修正）"
                :controls="false"
                :min="0"
                :step="0.01"
                :precision="2"
                @change="onFeeEdit"
              />
            </div>
          </div>
          <div class="panel-row">
            <span class="panel-label">补差费</span>
            <div class="fee-cell">
              <span class="fee-sign">−¥</span>
              <el-input-number
                v-model="feeInputs.compensate"
                class="fee-input"
                aria-label="补差费（可修正）"
                :controls="false"
                :min="0"
                :step="0.01"
                :precision="2"
                @change="onFeeEdit"
              />
            </div>
          </div>
          <!-- 已手工修正时给出原估算值 + 一键还原，避免「改过但忘了改成多少」 -->
          <div v-if="feeDirty" class="panel-row fee-hint-row">
            <span class="fee-hint">
              已手工修正 · 原估算 赎回
              {{ (estimate.out.fee_estimated?.redeem ?? 0).toFixed(2) }}
              / 补差
              {{ (estimate.out.fee_estimated?.compensate ?? 0).toFixed(2) }}
            </span>
            <el-button
              link
              type="primary"
              size="small"
              @click="resetFeeOverride"
            >
              还原
            </el-button>
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
              {{ estimate.in.name || estimate.in.symbol }} ·
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

        <!-- 差额去向（有差额时必选；默认取账户绑定的类现金产品）
             命名与右栏提示保持一致：这里选的是「差额」去哪儿，不是「退多少钱」 -->
        <el-form
          v-if="estimate.refund.amount > 0"
          label-width="90px"
          size="large"
        >
          <el-form-item label="差额去向" required>
            <SegmentedControl
              v-model="form.refundMode"
              :options="refundOptions"
              aria-label="差额去向"
            />
            <div class="helper">
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
        <el-button :disabled="submitting" @click="step = 0">上一步</el-button>
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

    <!-- ===== 第 3 步：结果 ===== -->
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
import SegmentedControl from "@/components/SegmentedControl/index.vue";
import TradeSlotSwitch from "@/components/TradeSlotSwitch/index.vue";
import QuickRatioPicker from "@/components/QuickRatioPicker/index.vue";
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

const props = defineProps<{
  ledgers: any[];
  defaultLedgerId?: number | null;
}>();
const emit = defineEmits<{
  (e: "submit-success"): void;
  (e: "positions-loaded", ledgerIds: number[]): void;
}>();

/**
 * 三步：填写 → 确认 → 结果。
 *
 * 原为四步（选出/选入分开），合并成两栏并置后少一步（#2348）——
 * 转出与转入是同一笔双腿操作，分两屏问会让用户来回翻页核对。
 */
const stepTitles = ["填写转换", "费用与确认", "结果"];
const step = ref(0);

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
  /** 转入口径：金额 or 份额（二选一，后端 `in_amount` / `in_quantity` 互斥） */
  inMode: "amount" as "amount" | "quantity",
  inQuantity: undefined as number | undefined,
  refundMode: "" as "" | "money_fund" | "account_cash"
});
const form = reactive(defaultForm());

/**
 * 费用人工修正（#2348）。
 *
 * 真实确认单的费用常与费率先算值不一致（基金公司活动免赎回费、钱包垫资口径），
 * 所以确认页的两个费用行是可编辑的。`feeDirty` 用来判「用户是否动过」：
 * 没动过就跟着试算结果刷新，动过就**不再覆盖**用户输入（否则每敲一位就被回填）。
 */
const feeInputs = reactive({ redeem: 0, compensate: 0 });
const feeDirty = ref(false);

/** 转入口径切换选项（2 档「多选一」→ SegmentedControl） */
const inModeOptions = [
  { label: "按金额", value: "amount" },
  { label: "按份额", value: "quantity" }
] as const;

/** 「全部」转出：不传 out_quantity，后端按持仓 4 位精确值处理（D8/§5.2） */
const transferAll = ref(false);

const selectedPosition = computed(
  () => accountPositions.value.find(p => p.id === form.positionId) || null
);
const maxQuantity = computed(() =>
  Number(selectedPosition.value?.quantity ?? 0)
);

/** 转出腿是否填完（原 step1Valid） */
const outLegValid = computed(() => {
  if (!form.positionId || !form.trade_date) return false;
  if (transferAll.value) return true;
  return (
    !!form.quantity &&
    form.quantity > 0 &&
    form.quantity <= maxQuantity.value + 1e-9
  );
});

/** 转入腿是否填完（原 step2Valid）；转入基金不得等于转出基金 */
const inLegValid = computed(() => {
  if (!form.inSymbol) return false;
  return form.inSymbol !== (selectedPosition.value?.symbol ?? "");
});

/** 两栏并置后的单一进入条件：任一腿没填完都不让进确认页 */
const inputValid = computed(() => outLegValid.value && inLegValid.value);

function onOutPositionChange() {
  transferAll.value = false;
  form.quantity = undefined;
  // 换转出基金 = 换一套费用，人工修正不再适用
  feeDirty.value = false;
  feeInputs.redeem = 0;
  feeInputs.compensate = 0;
}

function onQuantityInput() {
  transferAll.value = false;
}

/**
 * 快捷档位点击后的**附加语义**：`ratio >= 1` 即「全部转出」——
 * 后端按持仓 4 位精确值清算、不抹零（见 `ConversionBaseParams.out_quantity`）。
 *
 * 档位表、取整、选中态反算都在 `QuickRatioPicker` 内部（与卖出表单同一实现），
 * 这里只接「全部」这一个语义差异，不再重复算份额。
 */
function onQuickRatioSelect({ ratio }: { ratio: number; quantity: number }) {
  transferAll.value = ratio >= 1;
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

/** 第 1 步「当前持有」快选：排除转出基金本身 */
const inFundCandidates = computed(() =>
  accountPositions.value.filter(
    p => p.symbol !== selectedPosition.value?.symbol
  )
);

/**
 * 已选转入基金的「标签兜底」。
 *
 * 快选按钮把 `form.inSymbol` 直接写成持仓代码，而它不在 `inFundOptions`（搜索结果）里，
 * el-select 找不到同名选项就把值原样显示成「002340」。这里只造一个**纯标签**选项
 * 把它接住——不伪造 `FundSearchItem` 的 type / subscription_rate，避免编数据。
 */
const pickedInOption = computed(() => {
  const code = form.inSymbol;
  if (!code) return null;
  return { value: code, label: `${form.inName || code}（${code}）` };
});

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
/** 退款去向选项：2 档「多选一」→ SegmentedControl（design.md 语言边界） */
const refundOptions = computed(() =>
  (estimate.value?.refund.options ?? []).map(opt => ({
    label: opt.name,
    value: opt.type
  }))
);
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
      // 金额 / 份额二选一：只发当前口径的那个，后端对同时传两者直接拒绝
      in_amount: form.inMode === "amount" ? (form.inAmount ?? null) : null,
      in_quantity:
        form.inMode === "quantity" ? (form.inQuantity ?? null) : null,
      fee_override: feeDirty.value
        ? { redeem: feeInputs.redeem, compensate: feeInputs.compensate }
        : null,
      trade_date: form.trade_date
    });
    if (my !== estimateSeq) return; // 过期响应丢弃
    estimate.value = (res?.data ?? null) as ConversionEstimateResult | null;
    // 费用行未手工修正时跟随试算刷新；修正过就保留用户输入，不回填
    if (estimate.value && !feeDirty.value) {
      feeInputs.redeem = estimate.value.out.fee_breakdown.redeem;
      feeInputs.compensate = estimate.value.out.fee_breakdown.compensate;
    }
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

// 进入确认页（第 2 步）：清掉旧试算并立即重算（避免展示上一批参数的数字）
function gotoConfirm() {
  if (!inputValid.value) return;
  if (estimateTimer) clearTimeout(estimateTimer);
  estimate.value = null;
  estimateError.value = "";
  step.value = 1;
  void runEstimate();
}

/**
 * 手工修正费用：标记 dirty 并按新费用重算。
 *
 * 净额 = 转出金额 − 费用，所以改费用会连带改「净额 / 转入份额 / 差额」——
 * 这些都由服务端重算（前端不算账，§4.2 单一实现）。
 */
function onFeeEdit() {
  feeDirty.value = true;
  scheduleEstimate();
}

/** 还原为算法估算值（把人工修正撤回） */
function resetFeeOverride() {
  feeDirty.value = false;
  if (estimate.value) {
    feeInputs.redeem = estimate.value.out.fee_breakdown.redeem;
    feeInputs.compensate = estimate.value.out.fee_breakdown.compensate;
  }
  scheduleEstimate();
}

// 确认页内任何参数变化 → 防抖重算
watch(
  [
    () => form.positionId,
    () => form.quantity,
    () => form.trade_date,
    () => form.isAfter15,
    () => form.inSymbol,
    () => form.inAmount,
    () => form.inQuantity,
    () => form.inMode,
    transferAll
  ],
  () => {
    if (step.value !== 1) return;
    if (!inputValid.value) return;
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
      in_amount: form.inMode === "amount" ? (form.inAmount ?? null) : null,
      in_quantity:
        form.inMode === "quantity" ? (form.inQuantity ?? null) : null,
      fee_override: feeDirty.value
        ? { redeem: feeInputs.redeem, compensate: feeInputs.compensate }
        : null,
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
      !!form.inQuantity ||
      !!form.refundMode)
);

function resetForm() {
  Object.assign(form, defaultForm());
  transferAll.value = false;
  feeDirty.value = false;
  feeInputs.redeem = 0;
  feeInputs.compensate = 0;
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
/* 步骤条收窄：卡片内通栏 4 步连线过长会显得空旷（设计 §6.4 只统一视觉与语义）。
   ⚠️ `width:100%` 不能省：父级是 flex column，本元素的 `margin:0 auto` 会让交叉轴
   的 `align-self:stretch` 失效，宽度收缩到内容宽（实测 240px），四步标题被挤成两行。 */
.conversion-steps {
  width: 100%;
  max-width: 560px;
  margin: 0 auto 8px;
}

/* 当前步必须有"起点"：EP 默认 is-process 是深灰描边 + 深灰字，
   四步排开时没有任何一步像"正在进行"。改为品牌实底 + 反白数字。 */
.conversion-steps :deep(.el-step__head.is-process) {
  color: var(--brand-solid);
  border-color: var(--brand-solid);
}

.conversion-steps :deep(.el-step__head.is-process .el-step__icon) {
  color: var(--text-inverse);
  background-color: var(--brand-solid);
  border-color: var(--brand-solid);
}

.conversion-steps :deep(.el-step__title.is-process) {
  font-weight: 600;
  color: var(--text-primary);
}

.conversion-steps :deep(.el-step__title.is-wait) {
  color: var(--text-tertiary-ink);
}

/* ===== 两栏并置（第 1 步，#2348） ===== */

/* 栏头：比输入框标签更轻，只交代"这一栏在做什么"；
   h3 默认的 margin/字号必须清掉，否则两栏顶端会错开一行 */
.convert-col__title {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-secondary);
}

/* 转入金额区：口径切换独占一行右对齐，输入框整行吃满 */
.in-amount-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.in-amount-field__switch {
  align-self: flex-end;
}

/* 差额去向提示：与既有告警块同一视觉层级（bg-soft 底、无边框），
   只是常驻而不是出错才出现 */
.convert-note {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 12px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: var(--radius-md);
}

.convert-note__icon {
  flex: none;
  margin-top: 1px;
  color: var(--text-tertiary-ink);
}

/* ===== 表单栅格 ===== */

/* 一期一列的弹性行：右端控件贴住与其它输入框同一条垂直线 */
.field-row {
  display: flex;
  gap: 12px;
  align-items: center;
  width: 100%;
}

/* 日期框吃满剩余宽度。`flex-basis` 必须是 **0%**：EP 给 `.el-date-editor.el-input`
   写死 `width:220px`（(0,2,0) 压过本类的 (0,1,0)），而 `flex:1 1 auto` 会退回那个
   width 当基准——grow 分不到额外空间，实测仍是 220px；`1 1 0%` 才与 width 脱钩。 */
.field-row__grow {
  flex: 1 1 0%;
  min-width: 0;
}

.quantity-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

/* 快捷比例：紧凑贴左，右侧挂"持有"读数，不拉满整行 */
.quick-ratio-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.hold-hint {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

/* 辅助说明：与主文案拉开行高，避免贴脸；宽度 100% 保证在 form-item 内换行 */
.helper {
  width: 100%;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}

/* 「当前持有」快选：选中态走软按钮（浅红底 + 红字），不占实底主按钮的供能位 */
.is-picked.el-button {
  color: var(--brand-700);
  background-color: var(--brand-100);
  border-color: var(--brand-400);
}

.is-picked.el-button:hover {
  color: var(--brand-700);
  background-color: var(--brand-200);
  border-color: var(--brand-400);
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

/* ── 费用可编辑（#2348） ──
   输入框贴右、与上面的金额列右对齐；tab 数字等宽避免抖动。 */
.fee-cell {
  display: inline-flex;
  gap: 2px;
  align-items: center;
}

.fee-sign {
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.fee-input {
  width: 96px;
}

.fee-input :deep(.el-input__inner) {
  font-variant-numeric: tabular-nums;
  text-align: right;
}

/* 修正提示行：说明「已改过」并给出原估算值，不抢主信息的层级 */
.fee-hint-row {
  margin-top: -4px;
}

.fee-hint {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}
</style>
