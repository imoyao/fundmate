/**
 * 探市页的档位切换（#980 拆分自 views/explore/index.vue）。
 *
 * 三档（概览 / 深度 / 行业情绪）与 `?view=` 查询参数双向同步。这里的规则本身是
 * 纯映射，抽出来后可以逐条断言：未知 `?view=` 值要落回概览、←/→ 要循环、
 * Home/End 要跳首尾。
 */

import { computed, ref, watch } from "vue";

export type PanelKey = "overview" | "detail" | "emotion";

/** 档位顺序即 Tab 顺序，也决定 ←/→ 的循环方向 */
export const PANEL_TABS: Array<{ key: PanelKey; label: string }> = [
  { key: "overview", label: "概览" },
  { key: "detail", label: "深度" },
  { key: "emotion", label: "行业情绪" }
];

/** 每个档位给一句「这档在讲什么」，渲染在 Tab 右侧 */
export const PANEL_HINTS: Record<PanelKey, string> = {
  overview: "一屏看懂市场冷热，并建立自己的观察列表",
  detail: "行业维度、趋势与全部指标明细",
  emotion: "韭圈儿行业恐贪快照，辅助判断行业冷热（标注韭圈儿行业口径）"
};

/**
 * `?view=` → 档位。
 *
 * 任何不认识的值（含 `undefined` / 数组 / 空串）都落回概览：URL 是用户可改的，
 * 这里不做白屏式的报错，而是给一个确定可用的默认档。
 */
export function normalizePanel(raw: unknown): PanelKey {
  if (raw === "detail") return "detail";
  if (raw === "emotion") return "emotion";
  return "overview";
}

/**
 * 键盘事件 → 目标 Tab 下标；不处理的键返回 -1。
 *
 * ←/→ 循环（首项左键到末项、末项右键到首项），Home/End 直达首尾。
 * Enter / Space 刻意不处理：`<button>` 原生 click 已经触发切换，再绑会切两次。
 */
export function nextTabIndex(
  key: string,
  index: number,
  length: number
): number {
  const last = length - 1;
  switch (key) {
    case "ArrowRight":
      return index === last ? 0 : index + 1;
    case "ArrowLeft":
      return index === 0 ? last : index - 1;
    case "Home":
      return 0;
    case "End":
      return last;
    default:
      return -1;
  }
}

export function usePanelSwitch(options: { route: any; router: any }) {
  const { route, router } = options;

  const activePanel = ref<PanelKey>(normalizePanel(route.query.view));
  const activeHint = computed(() => PANEL_HINTS[activePanel.value]);

  // URL 变化（含 /temperature 重定向过来、浏览器前进后退）时同步档位
  watch(
    () => route.query.view,
    raw => {
      activePanel.value = normalizePanel(raw);
    }
  );

  const switchPanel = (key: PanelKey) => {
    activePanel.value = key;
    // replace 而非 push：切换档位不应污染历史栈，避免返回键在档位间循环
    router.replace({
      path: "/explore",
      query: key === "overview" ? {} : { view: key }
    });
  };

  return { activePanel, activeHint, switchPanel };
}
