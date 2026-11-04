import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  attributeEaccount,
  type ReconciliationItem,
  type AttributionResult
} from "@/api/eaccount";

import {
  ACTION_META,
  attributionPayload,
  attributionResultMessage,
  confirmMessageOf,
  errMsg,
  isActingOf,
  unwrap,
  type Acting,
  type AttributionAction
} from "./model";

/**
 * 行内归因 / 忽略（迁移自 reconcile/reconcileView/useReconcileActions.ts）。
 *
 * 两条操作此前是两段几乎相同的 `handleCover` / `handleIgnore`：确认框 → 置 loading →
 * 发请求 → 按 failed 数给文案 → 重载 → 清 loading。唯一区别是 action 与措辞，
 * 所以这里合成一条，差异全部走 `ACTION_META` / `attributionResultMessage`。
 *
 * `actingRecordId` + `actingAction` 只服务于「哪一行的哪个按钮在转圈」，
 * 属于本 composable 的私有状态，不回传页面；页面把 `acting` 快照传给表格。
 *
 * ⚠️ 工作台域 A 曾自己手写这两个函数，**漏掉了确认框**——「归因覆盖」会删除渠道
 * 原记录且不可撤销，不确认等于把不可逆操作做成了单击即执行。收敛到本 composable 后
 * 两处共用同一条确认链路，这类「抄漏一步」不会再发生。
 */
export function useEaccountActions(reload: () => Promise<void>) {
  const actingRecordId = ref<number | null>(null);
  const actingAction = ref<AttributionAction | null>(null);

  /** 判断某个按钮是否处于 loading（表格行用它决定转哪个圈） */
  function isActing(recordId: number, action: AttributionAction): boolean {
    return isActingOf(
      { recordId: actingRecordId.value, action: actingAction.value },
      recordId,
      action
    );
  }

  async function runAttribution(
    row: ReconciliationItem,
    action: AttributionAction
  ) {
    const meta = ACTION_META[action];

    try {
      await ElMessageBox.confirm(confirmMessageOf(action, row), meta.title, {
        type: meta.type,
        confirmButtonText: meta.confirmText,
        cancelButtonText: "取消",
        ...(meta.confirmClass ? { confirmButtonClass: meta.confirmClass } : {})
      });
    } catch {
      return; // 用户取消
    }

    actingRecordId.value = row.record_id;
    actingAction.value = action;
    try {
      const res = await attributeEaccount([attributionPayload(row, action)]);
      const result = unwrap<AttributionResult>(res);
      const { type, message } = attributionResultMessage(
        action,
        result.failed ?? 0
      );
      if (type === "warning") ElMessage.warning(message);
      else ElMessage.success(message);
      await reload();
    } catch (e) {
      ElMessage.error(
        errMsg(e, action === "cover" ? "归因覆盖失败" : "忽略失败")
      );
    } finally {
      actingRecordId.value = null;
      actingAction.value = null;
    }
  }

  return { actingRecordId, actingAction, isActing, runAttribution };
}

/** 传给表格的「哪个按钮在转圈」快照类型（表格 props 用它，避免携带 ref） */
export type ActingSnapshot = Acting;
