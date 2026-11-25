/**
 * 响应式断点订阅（按需渲染用）。
 *
 * 为什么不是纯 CSS：CSS 只能隐藏元素，组件照样 mount——`v-if` 才是「不发请求、
 * 不建状态」的那一层。账本精灵的历史左栏就是例子：窄屏隐藏后若仍挂载，
 * 首屏会白拉一次会话列表（`GET /api/agent/sessions/`）。
 *
 * 断点取值必须与 `src/style/_breakpoints.scss` 的 `$breakpoints` 一致
 * （那边是 Tailwind v4 对齐后的唯一来源）。这里写 rem 而非 px：
 * `guard_breakpoints.py` 拦的是 CSS 里的裸 `@media (width <= Npx)`，
 * 而 rem 写法同时跟随浏览器字号，与 SCSS 侧语义一致。
 */

import { onBeforeUnmount, onMounted, ref } from "vue";

function canMatch(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function";
}

export function useMediaQuery(query: string) {
  /* 首帧就取真实值，**不**用 `ref(false)` 占位：初始 false 等于「先按窄屏渲染」，
     mounted 后才纠正 ⇒ 宽屏会闪一次错位。两个真实受害者：
     ① 账本精灵左栏 `v-if="isWide"`（宽屏首帧缺栏、mounted 后闪入，与「不白拉
        会话列表」的初衷相反地多了一次渲染）；
     ② 成分基金折叠（初始按 1 列算行数 ⇒ 13 只首帧误判溢出，闪一下
        「展开全部」再消失）。 */
  const mql = canMatch() ? window.matchMedia(query) : null;
  const matches = ref(mql?.matches ?? false);

  const apply = (e: MediaQueryList | MediaQueryListEvent) => {
    matches.value = e.matches;
  };

  onMounted(() => {
    if (!mql) return;
    /* 首帧已同步取值；这里补订阅，顺便纠正 setup→mounted 之间跨断点的情况 */
    apply(mql);
    mql.addEventListener("change", apply);
  });

  onBeforeUnmount(() => {
    mql?.removeEventListener("change", apply);
  });

  return matches;
}
