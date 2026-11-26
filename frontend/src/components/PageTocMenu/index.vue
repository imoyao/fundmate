<!--
  PageTocMenu · 页内导航的**页头右上角下拉**形态（2026-11 投顾组合详情重设计）

  ## 为什么不是胶囊、也不是右栏
  `<xl` 的顶部胶囊要占掉正文上方一整行（本页 6 个区块，胶囊会挤成两行横滑）；
  `xl+` 的右侧 rail 固定吃掉 160px 内容宽——组合详情页的「方向对照」是五列网格 +
  双条形，宽度直接决定它能不能读。把入口收到页头右上角后，正文拿到完整内容宽，
  而「现在在哪一节」由按钮上的当前项名称持续回答，不需要一整列常驻。

  ## 与 PageNav / PageToc 的关系
  三者消费**同一份** `usePageNav` 状态（items / activeId / goTo），只是投影不同形态。
  本组件不自己算 scroll-spy，也不自己滚动页面——`@navigate` 交给调用方。

  ## 无障碍
  - 触发按钮 `aria-expanded` + `aria-haspopup`，面板内为 `<button>` 列表（跳转不是
    切换视图，不挂 tablist/menu 角色——与本仓 `guard_segmented` 的既有取舍一致）；
  - 当前项用 `aria-current="location"`（读屏读到「当前所在位置」，不是「选中」）；
  - Esc 关闭并把焦点还给触发按钮；点击面板外部关闭。
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { PageNavItem } from "@/composables/usePageNav";

const props = defineProps<{
  items: PageNavItem[];
  activeId: string;
}>();

const emit = defineEmits<{
  (e: "navigate", id: string): void;
}>();

const open = ref(false);
const root = ref<HTMLElement>();
const trigger = ref<HTMLButtonElement>();

/** 按钮上显示的「当前在哪」；还没算出来时退回第一项 */
const currentLabel = computed(() => {
  const hit = props.items.find(item => item.id === props.activeId);
  return hit?.label ?? props.items[0]?.label ?? "目录";
});

function toggle() {
  open.value = !open.value;
}

function close(returnFocus = false) {
  if (!open.value) return;
  open.value = false;
  if (returnFocus) trigger.value?.focus();
}

function go(item: PageNavItem) {
  emit("navigate", item.id);
  close(true);
}

function onDocumentPointerDown(event: MouseEvent) {
  if (!open.value) return;
  const target = event.target as Node | null;
  if (target && root.value?.contains(target)) return;
  close();
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") close(true);
}

// 锚点集合变化（品类切换 / 区块降级卸载）时，面板里的旧项已失效，直接收起
watch(
  () => props.items,
  () => close()
);

/**
 * 页头被吸顶工具栏「吃掉」之后，按钮转为**视口右上角悬浮**。
 *
 * ## 为什么必须这样（2026-11-26 实测）
 *
 * 页头（`PageHeaderBar`）不是 sticky。把目录放进页头后，滚到 §05 时按钮的
 * `getBoundingClientRect().top` 实测是 **−2988**（视口上方 3000px 外）：
 * 用户既看不到也点不到。
 *
 * 而页内导航的**唯一使用场景**恰恰是「已经滚到深处，想跳回/跳到别处」——
 * 入口只在顶部可用、其余 99% 的滚动位置不可用，等于没有导航。
 *
 * ## 为什么不用 IntersectionObserver（曾经的实现，有洞）
 *
 * 旧判据是 `!entry.isIntersecting && entry.boundingClientRect.bottom < 0`。
 * 但页头是被**滚动容器**裁掉的（容器上沿 = 吸顶工具栏下沿 81px），不是被视口
 * 裁掉的；而 `boundingClientRect` 给的是**视口坐标**。实测滚到 200px 时
 * `isIntersecting` 已经是 false 而 `bottom` 还是 **+43**，判据不成立；此后
 * `isIntersecting` 不再变化，**不会再有新回调** ⇒ `floating` 永久为 false。
 *
 * 后果是渐进滚动（用户真实操作）下按钮先钻进吸顶栏、再滚出视口，全程点不到；
 * 只有「一次跳过整屏」才会在穿越瞬间拿到足够负的 bottom 而碰巧生效——
 * 这也是之前 e2e 全绿却没发现的原因（用例一次跳 400~1400px）。
 *
 * 改为监听滚动、每帧重量一次：判据是「页头顶沿是否越过滚动区上沿」，
 * 连续且与裁剪方向一致，不存在「只在穿越时判一次」的窗口。
 */
const floating = ref(false);
/**
 * 悬浮态顶边。
 *
 * 不能写死 `top: 12px`：本仓 `fixedHeader` 模式下顶部栏（面包屑 + 工具按钮）是
 * **吸顶**的，写死 12px 会让悬浮按钮正压在它下面 —— 实测 `elementFromPoint`
 * 命中的是顶栏按钮而不是目录按钮，Playwright 真实点击 5s 超时（人点也一样点不到）。
 * `.app-main` 的滚动区上沿就是顶栏下沿，据此让开即可；非 fixedHeader 模式下
 * 滚动区从 0 起，退化为 12px，行为等价。
 */
const floatTop = ref("12px");

function scrollerOf(): HTMLElement | null {
  return document.querySelector<HTMLElement>(".app-main .el-scrollbar__wrap");
}

function measureFloatTop() {
  const wrap = scrollerOf();
  const top = wrap ? Math.max(wrap.getBoundingClientRect().top, 0) : 0;
  floatTop.value = `${Math.round(top) + 12}px`;
}

let raf = 0;

function evaluate() {
  raf = 0;
  // 每次重新取节点：路由内重渲染会把页头换掉，缓存引用会让判据停在挂载那一刻
  const header = root.value?.closest<HTMLElement>(".page-header");
  if (!header) return;
  const wrap = scrollerOf();
  // 没有独立滚动容器时（整页 window 滚动）等价于视口上沿
  const boundary = wrap ? wrap.getBoundingClientRect().top : 0;
  const next = header.getBoundingClientRect().top <= boundary;
  if (next !== floating.value) floating.value = next;
  // 顶栏高度随布局/缩放变化，浮起来时每帧对一次，代价是两次 rect
  if (next) measureFloatTop();
}

function schedule() {
  if (raf) return;
  raf = requestAnimationFrame(evaluate);
}

onMounted(() => {
  document.addEventListener("mousedown", onDocumentPointerDown, true);
  document.addEventListener("keydown", onKeydown);
  // scroll 不冒泡，但捕获阶段会经过 window —— 这样不必知道页面把滚动放在哪一层
  window.addEventListener("scroll", schedule, { passive: true, capture: true });
  window.addEventListener("resize", schedule);
  // 首屏就可能在深处（刷新后恢复滚动位置 / 从锚点链接进来）
  evaluate();
});

onBeforeUnmount(() => {
  if (raf) cancelAnimationFrame(raf);
  raf = 0;
  document.removeEventListener("mousedown", onDocumentPointerDown, true);
  document.removeEventListener("keydown", onKeydown);
  window.removeEventListener("scroll", schedule, { capture: true });
  window.removeEventListener("resize", schedule);
});
</script>

<template>
  <div
    ref="root"
    class="toc-menu"
    :class="{ 'is-floating': floating }"
    :style="floating ? { '--toc-float-top': floatTop } : undefined"
  >
    <button
      ref="trigger"
      type="button"
      class="toc-menu__btn"
      :aria-expanded="open"
      aria-haspopup="true"
      :title="`本页目录：${currentLabel}`"
      @click="toggle"
    >
      <svg
        class="toc-menu__icon"
        width="13"
        height="13"
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M2 4h12M2 8h12M2 12h8"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
      </svg>
      <span class="toc-menu__label">{{ currentLabel }}</span>
      <svg
        class="toc-menu__chev"
        width="10"
        height="10"
        viewBox="0 0 12 12"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M3 4.5 6 7.5l3-3"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <div v-if="open" class="toc-menu__panel">
      <p class="toc-menu__title">本页目录</p>
      <ul class="toc-menu__list">
        <li v-for="item in items" :key="item.id">
          <button
            type="button"
            class="toc-menu__item"
            :class="{ 'is-active': item.id === activeId }"
            :aria-current="item.id === activeId ? 'location' : undefined"
            @click="go(item)"
          >
            {{ item.label }}
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped lang="scss">
.toc-menu {
  position: relative;
}

/* 页头滚出视口后：钉在右上角，与内容区右边缘对齐（宽屏取留白中点、窄屏贴边）。
   不占文档流，页头处不留空；滚回顶部时类名移除，自动归位。 */
.toc-menu.is-floating {
  position: fixed;

  /* 顶边由 `measureFloatTop()` 现算（避开吸顶工具栏），见脚本注释 */
  top: var(--toc-float-top, 12px);
  right: max(
    var(--space-3),
    calc((100vw - var(--layout-content-width)) / 2 + var(--space-standard))
  );
  z-index: 60;

  /* 脱离页头后下方是正文，透明底会与内容糊在一起 ⇒ 给实底 + 浮起阴影 */
  .toc-menu__btn {
    background: var(--bg-card);
    box-shadow: var(--shadow-float);
  }
}

.toc-menu__btn {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 30px;
  padding: 0 10px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  white-space: nowrap;
  cursor: pointer;
  background: none;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-pill);
  transition:
    background-color 0.15s ease,
    color 0.15s ease,
    border-color 0.15s ease;

  &:hover {
    color: var(--text-primary);
    background: var(--bg-hover);
  }

  &[aria-expanded="true"] {
    color: var(--text-primary);
    background: var(--bg-hover);
    border-color: var(--border-default);
  }
}

.toc-menu__icon {
  flex: 0 0 auto;
  opacity: 0.72;
}

.toc-menu__label {
  max-width: 9em;
  overflow: hidden;
  text-overflow: ellipsis;
}

.toc-menu__chev {
  flex: 0 0 auto;
  opacity: 0.72;
  transition: transform 0.15s ease;
}

.toc-menu__btn[aria-expanded="true"] .toc-menu__chev {
  transform: rotate(180deg);
}

/* 面板：右对齐到按钮，宽 240px（六个中文标签最长「与我账户的对照」7 字，不折行） */
.toc-menu__panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 40;
  width: 240px;
  padding: 6px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-float);
}

.toc-menu__title {
  padding: 6px 10px 4px;
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.toc-menu__list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.toc-menu__item {
  display: block;
  width: 100%;
  padding: 7px 8px 7px 10px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
  background: none;
  border: none;
  border-left: 2px solid transparent;
  border-radius: var(--radius-sm);
  transition:
    background-color 0.15s ease,
    color 0.15s ease,
    border-color 0.15s ease;

  &:hover {
    color: var(--text-primary);
    background: var(--bg-hover);
  }

  &.is-active {
    font-weight: 600;
    color: var(--brand-ink);
    background: var(--bg-hover);
    border-left-color: var(--brand-700);
  }
}
</style>
