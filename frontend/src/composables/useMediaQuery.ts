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

export function useMediaQuery(query: string) {
  const matches = ref(false);
  let mql: MediaQueryList | null = null;

  const apply = (e: MediaQueryList | MediaQueryListEvent) => {
    matches.value = e.matches;
  };

  onMounted(() => {
    mql = window.matchMedia(query);
    apply(mql);
    mql.addEventListener("change", apply);
  });

  onBeforeUnmount(() => {
    mql?.removeEventListener("change", apply);
    mql = null;
  });

  return matches;
}
