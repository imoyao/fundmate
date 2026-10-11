import { watch, onBeforeUnmount, type ComputedRef } from "vue";
import { ElMessage } from "element-plus";

/**
 * 「记一笔」全局快捷键（N 单键）+ 受影响页面的首次提示（2026-10-10）。
 *
 * 背景：右下角 FAB（QuickFab）是布局级浮标，会压住自选页等高密度页面右下角的
 * 操作列（置顶/关注/移除按钮）；`hideQuickEntry` 可以把 FAB 隐藏，但入口就没了。
 * 本 composable 补上替代入口：**任意页面按 N 直接打开记账抽屉**，隐藏 FAB 的
 * 页面不再需要预留 `--layout-fab-safe`（与 constants/fab.ts 的配对约定一致）。
 *
 * 三道防误触守卫（缺一则打字场景会误开抽屉）：
 * 1. 输入焦点：input / textarea / select / contenteditable 一律忽略；
 * 2. 中文输入法：`e.isComposing`（组字中的 keydown，key 常为 "Process"）；
 * 3. 弹层互斥：EP 的 dialog / drawer 遮罩 `.el-overlay` 打开时不抢键。
 *    ⚠️ EP 遮罩是 **vShow 常驻 DOM**（关闭后留 `display:none` 节点），
 *    不能只判断元素存在，必须判断 `style.display !== "none"`。
 *
 * @param open 打开记账抽屉的动作（layout 注入 showTransactionDrawer = true）
 * @param fabHidden 当前路由是否隐藏 FAB（决定是否发「首次提示」）
 */
const HINT_STORAGE_KEY = "quick-entry-n-hint-shown";
/** sessionStorage 不可用（隐私模式等）时的页内兜底去重，避免每次进页都提示 */
let hintedThisPageLoad = false;

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT" ||
    target.isContentEditable ||
    target.closest("[contenteditable]") != null
  );
}

/** 是否有可见的 EP 弹层（dialog / drawer 遮罩）打开 */
function hasOpenOverlay(): boolean {
  // DOM lib 未开 DOM iterable，NodeListOf 不能直接 for...of，走 Array.from
  const overlays = Array.from(
    document.querySelectorAll<HTMLElement>(".el-overlay")
  );
  return overlays.some(el => el.style.display !== "none");
}

export function useQuickEntryHotkey(
  open: () => void,
  fabHidden: ComputedRef<boolean>
): void {
  function onKeydown(e: KeyboardEvent) {
    if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.repeat) return;
    if (e.key.toLowerCase() !== "n") return;
    if (e.isComposing) return; // 中文输入法组字中
    if (isEditableTarget(e.target)) return; // 正在输入框打字
    if (hasOpenOverlay()) return; // 弹窗/抽屉打开时不抢键
    e.preventDefault();
    open();
  }
  window.addEventListener("keydown", onKeydown);

  // 首次进入「FAB 已隐藏」页面时提示一次快捷键（sessionStorage 去重，会话内只提示一次）：
  // 隐藏后入口不可见，不提示则用户永远不知道有 N。
  const stopHint = watch(
    fabHidden,
    hidden => {
      if (!hidden) return;
      if (hintedThisPageLoad) return;
      try {
        if (sessionStorage.getItem(HINT_STORAGE_KEY)) return;
        sessionStorage.setItem(HINT_STORAGE_KEY, "1");
      } catch {
        /* 存储不可用：落到页内兜底标记，本页生命周期内仍只提示一次 */
      }
      hintedThisPageLoad = true;
      ElMessage.info("记一笔：按 N 键随时呼出");
    },
    { immediate: true }
  );

  onBeforeUnmount(() => {
    window.removeEventListener("keydown", onKeydown);
    stopHint();
  });
}
