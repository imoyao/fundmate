import { ElMessageBox } from "element-plus";
import { onBeforeRouteLeave } from "vue-router";
import { computed, onBeforeUnmount, ref } from "vue";
import type { Ref } from "vue";

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
/**
 * 表单脏状态：拿「打开时的快照」和「当前值」比。
 *
 * ## 为什么不各写各的
 *
 * 三个弹窗（TransactionEditDialog / AssetEditDialog / CreateAccountDialog）原本各自
 * 写了一份 `initialSnapshot = ref("")` + `JSON.stringify(form.value) !== initialSnapshot`，
 * **三处同一个 bug**：初值是 `""` 而表单初值是 `{}`，于是 `JSON.stringify({})`（`"{}"`）
 * 永远不等于 `""` —— **弹窗还没打开就被判定为「有未保存修改」**。
 * 叠上 `onBeforeRouteLeave` 后后果是：用户什么都没填，只要离开这个页面
 * （例如在账户列表点一张卡片进详情）就被问「当前修改尚未保存，确定放弃吗？」。
 *
 * ## 用法
 *
 *     const { isDirty, markClean } = useFormDirty(() => form.value);
 *     // 打开 / 保存成功后：markClean();
 *     const { onBeforeClose, requestClose } = useUnsavedChangesGuard(() => isDirty.value);
 *
 * `baseline` 为 null 表示「还没打开过」→ 不算脏。这比拿空串当基线稳：
 * 空串基线要求「初值必须恰好是空串」，而表单初值是对象。
 */
export function isFormDirtyJson(
  baseline: string | null,
  currentJson: string
): boolean {
  // baseline 为 null = 弹窗没打开过 → 不算脏。
  // 这一条是 #1845 回归的全部根因：原实现拿空串当基线，而表单初值是对象，
  // `JSON.stringify({})`（"{}"）永不等于 ""，于是「未打开」被判定成「有未保存修改」，
  // 叠上 onBeforeRouteLeave 后用户离开页面就被问「确定放弃吗？」。
  if (baseline === null) return false;
  return currentJson !== baseline;
}

export function useFormDirty<T>(getValue: () => T) {
  const baseline = ref<string | null>(null);

  const isDirty = computed(() =>
    isFormDirtyJson(baseline.value, JSON.stringify(getValue()))
  );

  /** 记下「当前值即干净」——打开弹窗时与保存成功后各调一次 */
  function markClean() {
    baseline.value = JSON.stringify(getValue());
  }

  return { isDirty, markClean };
}

/**
 * 弹窗表单的「打开时重填 + 脏基线同步」两件事绑在一起（#1880）。
 *
 * ## 为什么要绑
 *
 * 关闭态复位若只做一半，就会复现 #1845 那个 bug 的**变种**：
 * - 只 `markClean()` → 基线清了，但表单里还留着改后的值；下次打开时 `markClean()`
 *   把这个残留值记成基线，用户看到的是「上次的输入」，且一旦有 watcher 改写表单
 *   就又变脏；
 * - 只重置表单不碰基线 → 基线还是打开时的值，`isDirty` 立刻为 true：
 *   **保存成功后点侧边栏仍弹「未保存的修改」，导航被拦死**（本卡实测复现）。
 *
 * 两件事必须同一个入口，否则调用方总会只写一半。
 *
 * ## 用法
 *
 *     const { isDirty, fillOnOpen } = useDialogForm(form, () => ({ id: null, amount: 0 }));
 *     watch(() => props.modelValue, open => fillOnOpen(open, () => ({
 *       id: props.row?.id ?? null,
 *       amount: props.row?.amount || 0
 *     })));
 *     // save() 成功后：markClean()  或  markSaved()
 */
export function useDialogForm<S extends object>(
  form: Ref<S>,
  emptyValue: () => S
) {
  const { isDirty, markClean } = useFormDirty(() => form.value);

  /**
   * @param open  弹窗是否打开
   * @param fill  打开时的填充值；不传则用 `emptyValue()`
   */
  function fillOnOpen(open: boolean, fill?: () => S) {
    const next = open ? (fill ? fill() : emptyValue()) : emptyValue();
    form.value = next;
    // 基线同步：打开时 = 刚填的值（不脏），关闭时 = 空表单（不脏）
    markClean();
  }

  /** 保存成功：当前值即新基线 */
  function markSaved() {
    markClean();
  }

  return { isDirty, fillOnOpen, markSaved, markClean };
}
