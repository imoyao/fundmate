// frontend/src/views/asset/investment/manual/conversion/useConversionEstimate.ts
// 转换试算编排 + 费用人工修正（#980 拆分自 ConversionForm.vue）。
//
// 三件容易写错、必须原样搬过来的事：
//
// 1. **防倒序覆盖**：`estimateSeq` 自增序号，过期响应整包丢弃（§6.3.5）。
//    只靠 debounce 不够——400ms 内连改两位会并发两次请求，回来顺序不定。
// 2. **费用不被回填**：`feeDirty` 一旦为真就**不再**用试算结果覆盖输入框，
//    否则用户每敲一位就被回填一次，永远改不完。
// 3. **试算只在确认页跑**：`scheduleEstimate` 的 watch 里 `step !== 1` 直接 return，
//    第 1 步填表时不发请求（填表阶段没有任何数字要展示）。

import {
  computed,
  reactive,
  ref,
  watch,
  type ComputedRef,
  type Ref
} from "vue";
import {
  estimateConversion,
  type ConversionEstimateResult
} from "@/api/positions";
import type { ConversionFormModel } from "./conversionFormModel";
import {
  buildConversionBaseParams,
  type ConversionPayloadCtx
} from "./conversionPayload";

/** 试算防抖窗口：确认页改一下费用就重算，间隔太短会连发 */
const ESTIMATE_DEBOUNCE_MS = 400;

export function useConversionEstimate(options: {
  form: ConversionFormModel;
  ledgerId: ComputedRef<number | null>;
  transferAll: Ref<boolean>;
  /** 当前步骤；只有确认页（1）才自动重算 */
  step: Ref<number>;
  /** 两腿是否都填完；未填完不发试算 */
  inputValid: ComputedRef<boolean>;
}) {
  const { form, ledgerId, transferAll, step, inputValid } = options;

  /**
   * 费用人工修正（#2348）。
   *
   * 真实确认单的费用常与费率先算值不一致（基金公司活动免赎回费、钱包垫资口径），
   * 所以确认页的两个费用行是可编辑的。`feeDirty` 用来判「用户是否动过」：
   * 没动过就跟着试算结果刷新，动过就不再覆盖用户输入。
   */
  const feeInputs = reactive({ redeem: 0, compensate: 0 });
  const feeDirty = ref(false);

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

  /** 请求体的非 form 部分（提交侧复用同一份口径） */
  const feeOverride = computed(() =>
    feeDirty.value
      ? { redeem: feeInputs.redeem, compensate: feeInputs.compensate }
      : null
  );

  function payloadCtx(): ConversionPayloadCtx {
    return {
      ledgerId: ledgerId.value,
      transferAll: transferAll.value,
      feeOverride: feeOverride.value
    };
  }

  async function runEstimate() {
    if (!form.positionId || !form.inSymbol) return;
    const my = ++estimateSeq;
    estimating.value = true;
    estimateError.value = "";
    try {
      const res = await estimateConversion(
        buildConversionBaseParams(form, payloadCtx())
      );
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
    estimateTimer = setTimeout(runEstimate, ESTIMATE_DEBOUNCE_MS);
  }

  /** 作废旧试算（进确认页 / 复位表单）：连防抖计时器一起清，避免旧参数漏跑一次 */
  function resetEstimate() {
    if (estimateTimer) clearTimeout(estimateTimer);
    estimate.value = null;
    estimateError.value = "";
  }

  // 进入确认页（第 2 步）：清掉旧试算并立即重算（避免展示上一批参数的数字）
  function gotoConfirm() {
    if (!inputValid.value) return;
    resetEstimate();
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

  /** 换转出基金 = 换一套费用，人工修正不再适用（连带清掉 dirty 标记） */
  function resetFeeOverrideState() {
    feeDirty.value = false;
    feeInputs.redeem = 0;
    feeInputs.compensate = 0;
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

  return {
    feeInputs,
    feeDirty,
    feeOverride,
    estimating,
    estimate,
    estimateError,
    refundOptions,
    runEstimate,
    scheduleEstimate,
    resetEstimate,
    gotoConfirm,
    onFeeEdit,
    resetFeeOverride,
    resetFeeOverrideState,
    submitValid
  };
}
