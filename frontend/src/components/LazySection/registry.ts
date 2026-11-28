/**
 * `LazySection` 的激活注册表（页内导航跳转用）。
 *
 * ## 为什么需要它
 *
 * 内容懒挂之后，「跳转到某个区块」会在目标还没挂载时发生——`usePageNav.goTo`
 * 能把占位块顶边送到定位线（顶边只受**上方**内容影响，占位不影响），但用户看到
 * 的会是一块空白，内容在滚动动画结束后才长出来。
 *
 * 所以跳转前先按 anchorId 找到对应区块、把它激活，再让 `usePageNav` 去滚。
 * 注册表就是这张「anchorId → activate」的查找表，由页面 `provide`、区块 `inject`。
 *
 * ## 为什么不用 DOM 事件 / 全局单例
 *
 * - 事件（`el.dispatchEvent(new CustomEvent(...))`）跨组件通信隐晦，读代码的人
 *   看不出「谁在监听、谁在发」，还会在 SSR / 测试里静默失效；
 * - 全局单例在多页并存（keep-alive 缓存）时互相覆盖，且卸载时机不可控。
 *
 * 注入让作用域跟随组件树：同一页内只有一份，页面卸载即随 provide 一起消失。
 */
import type { InjectionKey } from "vue";

/** anchorId → 强制挂载该区块内容。Map 而非对象：key 是 DOM id，可能含连字符。 */
export type LazySectionRegistry = Map<string, () => void>;

export const LAZY_SECTION_REGISTRY: InjectionKey<LazySectionRegistry> = Symbol(
  "lazy-section-registry"
);
