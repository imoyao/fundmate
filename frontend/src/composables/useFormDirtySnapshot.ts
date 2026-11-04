import { computed, ref } from "vue";

/**
 * 内嵌表单「未保存离开保护」的脏基线（#1853 / #980）。
 *
 * 买入 / 卖出 / 分红三个表单原先各抄一份同样的实现（`markFormClean` + `isDirty`），
 * 且都踩过同一个坑：基线快照必须在**全部重置动作之后**再记。记在前面会把「本轮刚填
 * 的值」当成基线，紧接着重置成默认值 —— 基线 ≠ 当前，`isDirty` 立刻为 true，
 * 提交成功后关闭抽屉时被问「交易表单已填写，确定放弃吗？」。
 * 这条顺序由 `scripts/tests/unsaved_guard_baseline.test.js` 盯着，改之前先看它。
 *
 * ## 为什么不复用 `useUnsavedChangesGuard.ts` 里的 `useFormDirty`
 *
 * 两者的**初始语义不同**，不能合并：
 * - `useFormDirty` 的基线初始为 `null`，且 `null` 视为「不脏」——它面向**弹窗**：
 *   弹窗没打开过就不该拦导航，打开时由调用方 `markClean()` 起算；
 * - 本 composable 面向**常驻表单**：组件一挂载就要有基线（= 挂载时的值）。
 *   若用 `useFormDirty`，用户首次挂载后直接填金额、期间没有任何 `markClean()`，
 *   `isDirty` 会一直是 false —— #1853 的保护等于被静默关掉。
 *
 * 所以这里在构造时立刻记一次基线，之后只由 `markFormClean()` 手动复位。
 */
export function useFormDirtySnapshot<T>(readSnapshot: () => T) {
  const initialSnapshot = ref("");

  function markFormClean() {
    initialSnapshot.value = JSON.stringify(readSnapshot());
  }

  const isDirty = computed(
    () => JSON.stringify(readSnapshot()) !== initialSnapshot.value
  );

  // 初次挂载即视为干净（父组件可能用 v-if 只挂其中一个 tab）
  markFormClean();

  return { markFormClean, isDirty };
}
