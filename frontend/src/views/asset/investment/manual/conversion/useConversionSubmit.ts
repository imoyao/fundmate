// frontend/src/views/asset/investment/manual/conversion/useConversionSubmit.ts
// 转换提交编排（#980 拆分自 ConversionForm.vue）。
//
// 幂等约定与 `usePositionSubmit` 相同，但这里**不复用那个 composable**：
// 它绑定的是记账表单的收尾（成功提示 + 广播刷新），转换页走的是「结果页回执」，
// 两者只在「一个提交意图一个 UUID」这一点上重合，所以只共用
// `@/utils/idempotency` 的键生成，编排各自保留。

import { ref, type ComputedRef, type Ref } from "vue";
import { ElMessage } from "element-plus";
import {
  submitConversion,
  type ConversionEstimateResult,
  type ConversionSubmitResult
} from "@/api/positions";
import type { Position } from "@/api/types";
import { genIdempotencyKey } from "@/utils/idempotency";
import type { ConversionFormModel } from "./conversionFormModel";
import { buildConversionSubmitParams } from "./conversionPayload";
import { buildDuplicateConversionResult } from "./conversionDuplicateResult";

export function useConversionSubmit(options: {
  form: ConversionFormModel;
  ledgerId: ComputedRef<number | null>;
  transferAll: Ref<boolean>;
  /** 人工修正后的费用；未修正为 null */
  feeOverride: ComputedRef<{
    redeem: number;
    compensate: number;
  } | null>;
  estimate: Ref<ConversionEstimateResult | null>;
  selectedPosition: ComputedRef<Position | null>;
  /** 提交成功 / 幂等命中都进第 3 步（索引 3，展示时夹到「结果」） */
  step: Ref<number>;
}) {
  const {
    form,
    ledgerId,
    transferAll,
    feeOverride,
    estimate,
    selectedPosition,
    step
  } = options;

  const submitting = ref(false);
  const result = ref<ConversionSubmitResult | null>(null);
  /** 每次「提交意图」一个 UUID；失败重试沿用同键（与 usePositionSubmit 同约定） */
  let idempotencyKey = "";

  async function submit() {
    if (submitting.value || !form.positionId) return;
    if (!idempotencyKey) idempotencyKey = genIdempotencyKey();
    submitting.value = true;
    try {
      const res = await submitConversion(
        buildConversionSubmitParams(
          form,
          {
            ledgerId: ledgerId.value,
            transferAll: transferAll.value,
            feeOverride: feeOverride.value
          },
          idempotencyKey
        )
      );
      result.value = (res?.data ?? null) as ConversionSubmitResult | null;
      step.value = 3;
    } catch (e: any) {
      if (e?.response?.status === 409) {
        // 幂等命中（重复点击 / 网络重发）：已在库，直接进结果步展示原组号
        const dup = e?.response?.data?.data;
        ElMessage.info(
          e?.response?.data?.message || "该笔转换已记录，请勿重复提交"
        );
        result.value = buildDuplicateConversionResult({
          dup,
          form,
          estimate: estimate.value,
          position: selectedPosition.value
        });
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

  /** 复位表单：清结果与幂等键（下一次提交视为新意图） */
  function resetSubmit() {
    result.value = null;
    idempotencyKey = "";
  }

  return { submitting, result, submit, resetSubmit };
}
