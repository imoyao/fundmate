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
 * 页头滚出视口后，按钮转为**视口右上角悬浮**。
 *
 * ## 为什么必须这样（2026-11-26 实测）
 *
 * 页头（`PageHeaderBar`）不是 sticky。把目录放进页头后，滚到 §05 时按钮的
 * `getBoundingClientRect().top` 实测是 **−2988**（视口上方 3000px 外）：
 * 用户既看不到也点不到。
 *
 * 而页内导航的**唯一使用场景**恰恰是「已经滚到深处，想跳回/跳到别处」——
 * 入口在顶部可用、其余 99% 的滚动位置不可用，等于没有导航。这是把导航
 * 收进页头换来的空间收益所必须偿还的成本，不是可选项。
 *
 * ## 为什么观察页头而不是观察自己
 *
 * 观察自身会形成振荡：一旦自身改为 fixed 就落回视口内 → 观察器判定可见 →
 * 取消 fixed → 又滚出视口 → 再 fixed……页头本身不动，用它做判据是单调的。
 * 只在页头**整体位于视口上方**（bottom < 0）时悬浮；首屏阶段不动。
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

function measureFloatTop() {
  const wrap = document.querySelector<HTMLElement>(
    ".app-main .el-scrollbar__wrap"
  );
  const top = wrap ? Math.max(wrap.getBoundingClientRect().top, 0) : 0;
  floatTop.value = `${Math.round(top) + 12}px`;
}

let headerObserver: IntersectionObserver | null = null;

onMounted(() => {
  document.addEventListener("mousedown", onDocumentPointerDown, true);
  document.addEventListener("keydown", onKeydown);

  // 页头随内容滚动，不在滚动宿主上做阈值判断——IntersectionObserver 用视口
  // 作 root 即可，滚动容器变化时会自然重算，不必知道页面把滚动放在哪一层
  const header = root.value?.closest(".page-header");
  if (!header) return;
  headerObserver = new IntersectionObserver(
    entries => {
      const entry = entries[0];
      floating.value =
        !entry.isIntersecting && entry.boundingClientRect.bottom < 0;
    },
    { threshold: 0 }
  );
  headerObserver.observe(header);

  // 首屏就可能在深处（刷新后恢复滚动位置 / 从锚点链接进来）
  measureFloatTop();
});

// 浮起来之前先量一次：等真的浮动再量会让按钮有一帧压在顶栏上
watch(floating, value => {
  if (value) measureFloatTop();
});

onBeforeUnmount(() => {
  headerObserver?.disconnect();
  headerObserver = null;
  document.removeEventListener("mousedown", onDocumentPointerDown, true);
  document.removeEventListener("keydown", onKeydown);
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
