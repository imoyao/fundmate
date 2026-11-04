// src/views/welcome/composables/useHouseholdLinks.ts
/**
 * 家庭口径三列的「点击语义」：短按跳页、长按余波吃掉、触屏长按不弹系统菜单。
 *
 * 为什么单独成文件而不是留在组件里：
 * 这套逻辑是**手势契约**，与「三列长什么样」无关。放在组件里时，任何一次
 * 视觉改版都会让人误以为可以顺手改它——而它每一条都对应一个真实故障：
 *
 *   1. 用 `<a href>` 让浏览器直跳 ⇒ history 模式下等于整页刷新，SPA 状态全丢；
 *      故 preventDefault 后自己 router.push。修饰键 / 中键仍放行，
 *      交给浏览器开新标签页——那是 `<a>` 的本分。
 *   2. 长按已被「窥视金额」占用 ⇒ 松手那一下的 click 必须被吃掉，
 *      否则用户「想看一眼数字」的结果是**被带走**（见 `peekGuard`）。
 *   3. 触屏长按链接会弹系统菜单（新标签打开 / 拷贝链接），菜单一弹窥视就断 ⇒
 *      只在**粗指针 + 遮罩中**拦；桌面右键照旧放行。
 */

import { useRouter } from "vue-router";
import { usePrivacyMode } from "@/composables/usePrivacyMode";

/**
 * @param peekGuard 返回 true 表示「这次点击是长按的余波，应被吃掉」，
 *   并且**由它自己复位**——若让调用方读原始标记，同一次长按会连累下一次点击。
 */
export function useHouseholdLinks(peekGuard: () => boolean) {
  const router = useRouter();
  const { masked } = usePrivacyMode();

  function onClick(e: MouseEvent, to: string) {
    if (peekGuard()) {
      e.preventDefault();
      return;
    }
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0)
      return;
    e.preventDefault();
    router.push(to);
  }

  function onContextMenu(e: MouseEvent) {
    if (masked.value && window.matchMedia("(hover: none)").matches) {
      e.preventDefault();
    }
  }

  return { onClick, onContextMenu };
}
