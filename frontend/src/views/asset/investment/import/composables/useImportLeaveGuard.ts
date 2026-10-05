import { ref, onMounted, onUnmounted } from "vue";
import { onBeforeRouteLeave } from "vue-router";
import type { useImportWizard } from "./useImportWizard";

/**
 * 导入页离开守卫（#1789）。
 *
 * 形态决策（对齐 #1789「先定形态」）：
 * - 回站恢复维持 #1239 的非阻断 Banner（柔性原则 §2.5，不改回弹窗）；
 * - 仅在「离开路由 / 关闭标签页」且确有未保存修改（hasUnsavedDraftWork）时拦截。
 *
 * 三选用自定义对话框而非 ElMessageBox：需要「保存后离开 / 丢弃 / 取消」三个动作位，
 * ElMessageBox 只有确认/取消两个槽——把中止位借给某个分支正是 #1830 事故的成因，
 * 此处沿用该卡确立的对话框范式（DeletePositionDialog）。
 *
 * beforeunload 只能出浏览器原生确认框（按钮文案不可定制），三选语义仅适用站内路由离开。
 */

type LeaveDecision = "save" | "discard" | "cancel";

type ImportWizard = ReturnType<typeof useImportWizard>;

export function useImportLeaveGuard(wizard: ImportWizard) {
  const leaveDialogVisible = ref(false);
  let settleDecision: ((decision: LeaveDecision) => void) | null = null;

  /** 弹三选对话框并等待用户表态（路由离开的确认在这里挂起） */
  function requestDecision(): Promise<LeaveDecision> {
    leaveDialogVisible.value = true;
    return new Promise(resolve => {
      settleDecision = resolve;
    });
  }

  function settle(decision: LeaveDecision) {
    const resolve = settleDecision;
    settleDecision = null;
    leaveDialogVisible.value = false;
    resolve?.(decision);
  }

  onBeforeRouteLeave(async () => {
    if (!wizard.hasUnsavedDraftWork.value) return true;
    const decision = await requestDecision();
    if (decision === "cancel") return false;
    if (decision === "save") {
      // 保存失败也不锁死用户：盘上仍有上一轮快照（解析时落盘 + 30s 自动保存）兜底，
      // 且脏标未清、回站仍可恢复，不因一次写失败把人困在页内。
      await wizard.persistDraft();
      return true;
    }
    // 丢弃：删除整份草稿并清脏标——不保留本次未保存修改，回站也不再提示恢复
    await wizard.discardCurrentDraft();
    wizard.draftDirty.value = false;
    return true;
  });

  function handleBeforeUnload(e: BeforeUnloadEvent) {
    if (!wizard.hasUnsavedDraftWork.value) return;
    // 尽力落盘：IndexedDB 写入在卸载期间通常能完成，但浏览器不保证——
    // 30s 自动保存已兜底主要窗口，这里只是把残余窗口再压小
    void wizard.persistDraft();
    // 触发原生确认框（现代浏览器靠 preventDefault，旧引擎靠 returnValue 非空）
    e.preventDefault();
    e.returnValue = "";
  }

  onMounted(() => {
    window.addEventListener("beforeunload", handleBeforeUnload);
  });

  onUnmounted(() => {
    window.removeEventListener("beforeunload", handleBeforeUnload);
  });

  return {
    leaveDialogVisible,
    onLeaveSave: () => settle("save"),
    onLeaveDiscard: () => settle("discard"),
    onLeaveCancel: () => settle("cancel"),
    /** 对话框被 X / ESC 关闭时等价于「取消」（否则路由确认的 Promise 悬挂、导航卡死） */
    onLeaveDialogVisibleChange: (visible: boolean) => {
      if (!visible) settle("cancel");
    }
  };
}
