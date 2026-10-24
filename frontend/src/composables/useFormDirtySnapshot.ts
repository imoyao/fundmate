import { computed, ref } from "vue";

/**
 * 表单「未保存离开保护」的脏基线（#1853 / #980）。
 *
 * 买入 / 卖出 / 分红三个表单原先各抄一份同样的实现（`markFormClean` + `isDirty`），
 * 且都踩过同一个坑：基线快照必须在**全部重置动作之后**再记。记在前面会把「本轮刚填
 * 的值」当成基线，紧接着重置成默认值 —— 基线 ≠ 当前，`isDirty` 立刻为 true，
 * 提交成功后关闭抽屉时被问「交易表单已填写，确定放弃吗？」。
 *
 * 收敛到一处后这个顺序只讲一遍；调用方只需保证 `markClean()` 落在重置动作之后。
 */
export function useFormDirtySnapshot<T>(readSnapshot: () => T) {
  const initialSnapshot = ref("");

  function markClean() {
    initialSnapshot.value = JSON.stringify(readSnapshot());
  }

  const isDirty = computed(
    () => JSON.stringify(readSnapshot()) !== initialSnapshot.value
  );

  // 初次挂载即视为干净（父组件可能用 v-if 只挂其中一个 tab）
  markClean();

  return { markClean, isDirty };
}
