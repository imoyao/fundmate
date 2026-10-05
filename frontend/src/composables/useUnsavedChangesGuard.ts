import { ElMessageBox } from "element-plus";
import { onBeforeRouteLeave } from "vue-router";
import { onBeforeUnmount } from "vue";

/**
 * 未保存离开保护（#1853 / #1835）。
 *
 * 抽出来是因为同一段逻辑要在多处复用，而**每处都手写一遍必然漏一路**：
 * `el-dialog` 的 `before-close` 只拦关闭按钮 / ESC / 点遮罩，**底部「取消」是
 * 程序化 `close`，走不到它**——#1835 已在 `TransactionEditDialog` 上踩过这个坑，
 * 当时是手动补的 `requestClose`。这里把四条路一次收齐：
 *
 *   1. 关闭按钮 / ESC / 点遮罩 → `onBeforeClose`（挂 `:before-close`）
 *   2. 底部「取消」等程序化 close → `requestClose(close)`
 *   3. 路由离开 → 本 composable 内的 `onBeforeRouteLeave`（**无需调用方接线**）
 *   4. 浏览器刷新 / 关闭标签页 → `beforeunload`（可选，`useBeforeUnload` 传 true 开）
 *
 * ## 脏状态怎么给
 *
 * 传**函数**而不是 `Ref`，因为脏状态的来源分两种：父组件自己是表单
 * （`isDirty = computed(...)`），或脏状态住在子组件里（`TransactionDrawer`
 * 包着 `BuyForm`/`SellForm`，需子组件 `defineExpose({ isDirty })`，
 * 父组件用 `buyForm.value?.isDirty` 这种间接读法）。
 *
 * @param isDirty 返回当前是否有未保存改动
 */
export function useUnsavedChangesGuard(
  isDirty: () => boolean,
  opts?: {
    /** 提示正文；不传用通用文案 */
    message?: string;
    /** 弹窗标题 */
    title?: string;
    confirmButtonText?: string;
    cancelButtonText?: string;
    /** 是否额外拦浏览器刷新 / 关闭标签页（beforeunload） */
    useBeforeUnload?: boolean;
  }
) {
  /** 有未保存修改时问一次；resolve(true) 表示可以离开 */
  async function confirmDiscard(): Promise<boolean> {
    if (!isDirty()) return true;
    try {
      await ElMessageBox.confirm(
        opts?.message ?? "当前修改尚未保存，确定放弃吗？",
        opts?.title ?? "未保存的修改",
        {
          confirmButtonText: opts?.confirmButtonText ?? "放弃修改",
          cancelButtonText: opts?.cancelButtonText ?? "继续编辑",
          type: "warning"
        }
      );
      return true;
    } catch {
      return false; // 点「继续编辑」或关闭弹窗 → 留下
    }
  }

  /** el-dialog 的 `:before-close`——拦关闭按钮 / ESC / 点遮罩 */
  function onBeforeClose(done: () => void): void {
    void confirmDiscard().then(ok => {
      if (ok) done();
    });
  }

  /**
   * 底部「取消」等程序化 close 走这条路。
   * @param close 真正的关闭动作（通常是 emit('update:modelValue', false)）
   */
  async function requestClose(close: () => void): Promise<void> {
    if (await confirmDiscard()) close();
  }

  // 路由离开：第 4 路。注册在 composable 内，调用方无需接线。
  // vue-router 要求守卫在 setup 同步阶段注册，因此本 composable 只能在 setup 顶层调用。
  onBeforeRouteLeave(async () => confirmDiscard());

  if (opts?.useBeforeUnload) {
    const handler = (e: BeforeUnloadEvent) => {
      if (!isDirty()) return undefined;
      e.preventDefault();
      // 浏览器要求赋值一个非空字符串才会弹确认框
      e.returnValue = "";
      return "";
    };
    window.addEventListener("beforeunload", handler);
    // 组件卸载时移除，避免在对话框关闭后仍拦刷新
    onBeforeUnmount(() => window.removeEventListener("beforeunload", handler));
  }

  return { confirmDiscard, onBeforeClose, requestClose };
}
