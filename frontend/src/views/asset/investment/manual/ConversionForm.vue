<template>
  <div class="conversion-form flex flex-col gap-5">
    <!-- 进度改成卡头一行文字（#2348 第三轮）。原先是 `el-steps` 三圆点轨道：
         它和上面那排 D13 果冻胶囊长得都是「横向导航」，两排叠在一起互相抢位；
         而且给最不可交互的信息单独一条轨道，权重与功能是反的。
         步骤语义只留「第几步 / 共几步」一句话，推进交给按钮。 -->
    <div class="conversion-head">
      <span class="conversion-head__where">
        {{ stepTitles[currentStep] }}
        <span class="conversion-head__count">
          · 第 {{ currentStep + 1 }} 步 / 共 {{ stepTitles.length }} 步
        </span>
      </span>
      <button
        v-if="step === 1"
        type="button"
        class="conversion-head__back"
        :disabled="submitting"
        @click="step = 0"
      >
        上一步
      </button>
    </div>

    <!-- ===== 第 1 步：填写转出与转入（两栏并置，#2348） ===== -->
    <div v-if="step === 0" class="flex flex-col gap-5">
      <!-- 转换是 1→1 的双腿操作：拆成两步问会让用户来回翻页核对「卖的和买的是不是同一笔」，
           券商确认页也都是同屏左右对照。栏间分割线走全局工具类 `.soft-col-divider`
           （lg 及以上才出现 24px 内距 + 1px 线，lg 以下两栏堆叠不画孤线，
           见 design.md §栏间竖向分割线），不手写 border。 -->
      <div class="convert-grid grid grid-cols-1 gap-6 lg:grid-cols-12">
        <ConversionOutLeg
          :positions="accountPositions"
          :loading="loadingPositions"
          :max-quantity="maxQuantity"
          :transfer-all="transferAll"
          :position-id="form.positionId"
          :trade-date="form.trade_date"
          :after15="form.isAfter15"
          :quantity="form.quantity"
          @update:position-id="v => (form.positionId = v)"
          @update:trade-date="v => (form.trade_date = v)"
          @update:after15="v => (form.isAfter15 = v)"
          @update:quantity="v => (form.quantity = v)"
          @position-change="onOutPositionChange"
          @quantity-input="onQuantityInput"
          @quick-ratio-select="onQuickRatioSelect"
        />
        <ConversionInLeg
          :candidates="inFundCandidates"
          :options="inFundOptions"
          :search-loading="searchLoading"
          :picked-option="pickedInOption"
          :in-symbol="form.inSymbol"
          :in-mode="form.inMode"
          :in-value="inValue"
          @pick="pickInFund"
          @search="remoteSearchFunds"
          @update:in-symbol="v => (form.inSymbol = v)"
          @in-fund-change="onInFundChange"
          @update:in-mode="v => (form.inMode = v)"
          @update:in-value="v => (inValue = v)"
        />
      </div>

      <div class="flex justify-end">
        <el-button type="primary" :disabled="!inputValid" @click="gotoConfirm">
          下一步
        </el-button>
      </div>
    </div>

    <!-- ===== 第 2 步：费用与确认 ===== -->
    <ConversionStepConfirm
      v-else-if="step === 1"
      :estimating="estimating"
      :estimate="estimate"
      :estimate-error="estimateError"
      :submit-valid="submitValid"
      :submitting="submitting"
      :refund-options="refundOptions"
      :refund-mode="form.refundMode"
      :show-fee-detail="showFeeDetail"
      :fee-dirty="feeDirty"
      :redeem="feeInputs.redeem"
      :compensate="feeInputs.compensate"
      @retry="runEstimate"
      @submit="submit"
      @update:refund-mode="v => (form.refundMode = v)"
      @update:show-fee-detail="v => (showFeeDetail = v)"
      @update:redeem="v => (feeInputs.redeem = v ?? 0)"
      @update:compensate="v => (feeInputs.compensate = v ?? 0)"
      @fee-edit="onFeeEdit"
      @fee-reset="resetFeeOverride"
    />

    <!-- ===== 第 3 步：结果 ===== -->
    <ConversionStepResult
      v-else
      :result="result"
      @again="finish"
      @list="viewLedger"
    />
  </div>
</template>
<script setup lang="ts">
/**
 * 基金转换表单（三步向导：填写 → 确认 → 结果）。
 *
 * ## 本文件的职责（#980 拆分后）
 *
 * **只做编排**：持有 `form` 这一份表单真相源、三个「这一步能不能往下走」的
 * 判定、以及复位入口（`resetForm` / `isDirty` 供父页未保存守卫使用）。
 * 模板、样式、纯函数与 API 编排按「一条腿 / 一个步骤 / 一件事」分到
 * `./conversion/` 下，1702 行 → 约 290 行。
 *
 * 拆分的判据是**可独立修改**：改转出栏的字段不会碰到确认页的版式，
 * 改请求体不会碰到模板。行为零变更——三条链路的等价性有单测与 e2e 兜底
 * （`conversion/__tests__` 钉 payload 与幂等回执，`e2e/trade-forms.spec.ts` 走界面）。
 *
 * ## 三步从哪来
 *
 * 原为四步（选出 / 选入分开），合并成两栏并置后少一步（#2348）——
 * 转出与转入是同一笔双腿操作，分两屏问会让用户来回翻页核对。
 * 「结果」步的索引是 3（走完全程），`currentStep` 负责夹回 2。
 */
import { computed, onMounted, reactive, ref, watch } from "vue";
import ConversionOutLeg from "./conversion/components/ConversionOutLeg.vue";
import ConversionInLeg from "./conversion/components/ConversionInLeg.vue";
import ConversionStepConfirm from "./conversion/components/ConversionStepConfirm.vue";
import ConversionStepResult from "./conversion/components/ConversionStepResult.vue";
import { defaultConversionForm } from "./conversion/conversionFormModel";
import { useConversionPositions } from "./conversion/useConversionPositions";
import { useConversionInFund } from "./conversion/useConversionInFund";
import { useConversionEstimate } from "./conversion/useConversionEstimate";
import { useConversionSubmit } from "./conversion/useConversionSubmit";

const props = defineProps<{
  ledgers: any[];
  defaultLedgerId?: number | null;
}>();
const emit = defineEmits<{
  /** 结果页收尾：again=再记一笔、list=去交易流水（见 finish 的注释） */
  (e: "done", action: "again" | "list"): void;
  (e: "positions-loaded", ledgerIds: number[]): void;
}>();

const stepTitles = ["填写转换", "费用与确认", "结果"];
const step = ref(0);
/** 提交成功后 `step` 置 3（全流程走完），落在「结果」这一步 —— 索引要夹住 */
const currentStep = computed(() => Math.min(step.value, stepTitles.length - 1));
/** 费用明细默认收起：常驻两个可编辑输入框会把复核页读成编辑页 */
const showFeeDetail = ref(false);

const ledgerId = computed(() => props.defaultLedgerId ?? null);

// ── 表单状态 ──
const form = reactive(defaultConversionForm());
/** 「全部」转出：不传 out_quantity，后端按持仓 4 位精确值处理（D8/§5.2） */
const transferAll = ref(false);

// ── 持仓（按账户分组拉取，与 SellForm 同源） ──
const {
  loadingPositions,
  accountPositions,
  selectedPosition,
  maxQuantity,
  loadPositions
} = useConversionPositions(form, ledgerId, ledgerIds =>
  emit("positions-loaded", ledgerIds)
);

// ── 转入基金搜索（与 BuyForm 同源：基金账户走 searchFunds） ──
const {
  searchLoading,
  inFundOptions,
  remoteSearchFunds,
  inFundCandidates,
  pickedInOption,
  pickInFund,
  onInFundChange
} = useConversionInFund({ form, accountPositions, selectedPosition });

/**
 * 一个输入框承载两种口径（#2348 第二轮）。
 *
 * 改动前是两个互斥的 `el-input-number`（`v-if` / `v-else`）：切换口径等于换组件实例，
 * 光标丢失、输入框回到空态，而占位文案两边还都写着「留空 = 净额全部转入」——
 * 用户看不出自己现在填的是钱还是份。改成单框 + 读写映射后，切换只换
 * 「这个数字的含义」，两个口径各留各的值，切回来原数还在。
 */
const inValue = computed<number | undefined>({
  get: () => (form.inMode === "amount" ? form.inAmount : form.inQuantity),
  set: v => {
    if (form.inMode === "amount") form.inAmount = v;
    else form.inQuantity = v;
  }
});

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

// ── 试算 / 费用修正 / 提交 ──
const {
  feeInputs,
  feeDirty,
  feeOverride,
  estimating,
  estimate,
  estimateError,
  refundOptions,
  runEstimate,
  resetEstimate,
  gotoConfirm,
  onFeeEdit,
  resetFeeOverride,
  resetFeeOverrideState,
  submitValid
} = useConversionEstimate({ form, ledgerId, transferAll, step, inputValid });

const { submitting, result, submit, resetSubmit } = useConversionSubmit({
  form,
  ledgerId,
  transferAll,
  feeOverride,
  estimate,
  selectedPosition,
  step
});

function onOutPositionChange() {
  transferAll.value = false;
  form.quantity = undefined;
  // 换转出基金 = 换一套费用，人工修正不再适用
  resetFeeOverrideState();
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

/**
 * 结果页收尾走 `done` 而不是 `submit-success`（#2348 第四轮）。
 *
 * `submit-success` 在父页会弹一个「交易记录已成功保存！」的模态框，可那是
 * 无回执表单的收尾方式：转换页已经是一张回执（单号 + 三个数 + 后续时间），
 * 再弹一次「记账成功」等于把刚说过的话换个框再说一遍，还把用户的视线
 * 从结果页赶走。这里改成两个明确出口，由父页直接执行。
 */
function finish() {
  emit("done", "again");
}

function viewLedger() {
  emit("done", "list");
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
  Object.assign(form, defaultConversionForm());
  transferAll.value = false;
  resetFeeOverrideState();
  resetEstimate();
  resetSubmit();
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
/* 卡头进度行：一行 12px 文字代替三圆点轨道（#2348 第三轮）。
   它只承担「走到哪了」，不承担导航——所以不给描边、不给底色，
   让它读起来像卡片的一句附注，而不是又一条横条。 */
.conversion-head {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  min-height: 24px;
  margin-bottom: -4px;
}

.conversion-head__where {
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-secondary);
}

.conversion-head__count {
  color: var(--text-tertiary-ink);
}

/* 上一步改成卡头文字链：确认页只有一屏，「返回校对」离得近比离得远好；
   底部那排只留主按钮，避免两个「上一步」 */
.conversion-head__back {
  padding: 2px 4px;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-secondary);
  cursor: pointer;
  background: none;
  border: 0;
  border-radius: var(--radius-xs);
}

.conversion-head__back:hover:not(:disabled) {
  color: var(--brand-ink);
  text-decoration: underline;
}

.conversion-head__back:focus-visible {
  color: var(--brand-800);
  outline: none;
  box-shadow: inset 0 0 0 2px var(--brand-700);
}

.conversion-head__back:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
