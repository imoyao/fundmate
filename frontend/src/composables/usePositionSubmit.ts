import { ref } from "vue";
import { ElMessage } from "element-plus";
import { createPosition } from "@/api/positions";
import type { PositionCreate } from "@/api/types";
import { emitter } from "@/utils/mitt";

/**
 * 统一提交层（issue #933）：手动记账 / 资产简记等所有持仓写入口的唯一通道。
 *
 * 为什么收敛：此前 BuyForm / SellForm 各自直写 createPosition，错误信封解析、
 * 双击防抖、成功后刷新广播等业务规则散落两份且行为漂移（SellForm 的 catch
 * 是空的，错误被静默吞掉）。收敛后表单组件只负责校验与组装 body，
 * 写入规则单点维护；后续接入 ImportOrchestrator（#1020 去重作用域降级）
 * 也只需改本层。
 *
 * 职责：
 * - submitting 防抖：同一时刻只允许一个在途写入；
 * - 后端错误信封解析：422 字段级明细转可读文案（原 BuyForm 逻辑上移）；
 * - 成功提示 + refresh-ledger-data 广播（原各页面散落的刷新逻辑收口）。
 */
export function usePositionSubmit() {
  const submitting = ref(false);

  /** 后端错误 → 可读文案（422 携带字段级明细时逐项拼接） */
  function parseSubmitError(e: any): string {
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
    return msg;
  }

  /**
   * 提交持仓写操作（buy/sell/dividend/deposit/withdraw 统一入口）。
   * @returns 是否成功（失败已在本层完成错误提示，调用方无需重复弹错）
   */
  async function submitPosition(body: PositionCreate): Promise<boolean> {
    if (submitting.value) return false;
    submitting.value = true;
    try {
      await createPosition(body);
      ElMessage.success("记账成功");
      emitter.emit("refresh-ledger-data");
      return true;
    } catch (e: any) {
      ElMessage.error(parseSubmitError(e));
      return false;
    } finally {
      submitting.value = false;
    }
  }

  return { submitting, submitPosition };
}
