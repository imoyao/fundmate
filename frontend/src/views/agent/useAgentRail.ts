/**
 * 对话页左栏（会话导航）的收/展偏好（2026-11 反馈：常驻栏吃掉 232px，用户要能收起来）。
 *
 * 默认展开——保持既有「≥lg 常驻」的信息架构，不改默认契约；
 * 收起一次即记住，下次进来就是他要的形态。
 * 不落 store / cookie：这是纯本机展示偏好，跨端同步没有意义。
 *
 * 抽成模块而不是留在页面里：页面已有 400 行门禁，这段是「偏好读写 + 副作用」，
 * 与实际渲染无关，单测也不该为此拉起页面。
 */
import { ref, watch } from "vue";

const RAIL_COLLAPSED_KEY = "fm.agent.railCollapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(RAIL_COLLAPSED_KEY) === "1";
  } catch {
    return false; // 隐私模式 / 禁用存储：退回默认展开，不抛错
  }
}

export function useAgentRail() {
  const railCollapsed = ref(readCollapsed());

  watch(railCollapsed, collapsed => {
    try {
      localStorage.setItem(RAIL_COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
      // 写失败只影响「下次进来」的形态，不影响本次会话
    }
  });

  function toggle(): void {
    railCollapsed.value = !railCollapsed.value;
  }

  return { railCollapsed, toggle };
}
