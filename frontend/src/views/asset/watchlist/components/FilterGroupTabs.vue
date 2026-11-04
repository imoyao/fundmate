<template>
  <!-- 左段（弹性）：分组胶囊 Tab（design.md「分组胶囊 Tab · 方案 B」，水平滑动、数量徽章 tabular-nums）。
       自定义分组多时会横向滚动，右缘用渐变遮罩暗示「右侧还有」（2026-09-05）。
       注意：此处不要套裸 <template>（无 v-if/v-for/v-slot 指令），否则会被渲染成原生
       <template> 元素，其 children 进入惰性 .content 片段而不显示到页面（已踩坑）。 -->
  <div class="group-tabs-wrap">
    <div
      ref="groupScrollEl"
      class="group-tabs-scroll"
      :class="{ 'is-overflowing': groupOverflow }"
      @wheel="handleGroupWheel"
      @scroll.passive="updateGroupFade"
    >
      <button
        v-for="g in allGroups"
        :key="g.key"
        type="button"
        class="group-tab"
        :class="{ 'is-active': g.key === activeGroupModel }"
        :title="g.label"
        @click="activeGroupModel = g.key"
      >
        <!-- 分组色点：用户数据色（非设计令牌），缺失回退中性 token（数据色例外） -->
        <span
          v-if="g.color"
          class="group-tab-dot"
          :style="{ backgroundColor: g.color }"
        />
        <span class="group-tab-label">{{ g.label }}</span>
        <span
          v-if="g.count > 0"
          class="group-tab-count"
          :style="{
            /* 分组/标签色为用户数据（非设计令牌），缺失回退中性 token（数据色例外） */
            color: g.color ? g.color : undefined
          }"
        >
          {{ g.count }}
        </span>
      </button>
    </div>
    <!-- 右缘渐变遮罩：分组溢出时暗示可横向滑动（纯装饰，不拦截指针事件）。
         ⚠️ 必须绑 showGroupFade：此前 `showGroupFade` 只被赋值、模板从未消费，
         遮罩**永远常亮**——分组根本放得下时也压住最后一个组名（2026-11-02 用户报障：
         「最后一个组名外显太短」）。判据见 updateGroupFade。 -->
    <span
      class="group-tabs-fade"
      :class="{ 'is-visible': showGroupFade }"
      aria-hidden="true"
    />
  </div>
</template>

<script setup lang="ts">
/* eslint-disable vue/no-mutating-props -- 状态注入模式：groups 为 composable 实例 prop，
   经 computed get/set 桥接修改其内部 ref 属有意设计（与 WatchlistFilterBar 同模式） */
import {
  computed,
  ref,
  watch,
  onMounted,
  onBeforeUnmount,
  nextTick
} from "vue";
import type { useWatchlistGroups } from "@/composables/useWatchlistGroups";

/**
 * 分组胶囊 Tab 滚动区（#980 P0-b 拆分自 WatchlistFilterBar，零行为变更）：
 * 左段弹性的分组 tab 横滑容器 + 右缘渐变遮罩 + 滚轮横滑手势。
 * 分组状态经 groups（composable 实例 prop）状态注入，不在本组件持有业务状态。
 */
const props = defineProps<{
  groups: ReturnType<typeof useWatchlistGroups>;
}>();

// 状态注入模式：activeGroup 为 composable 内部 ref，
// 双向绑定经 computed get/set 桥接（避免 vue/no-mutating-props）
const activeGroupModel = computed({
  get: () => props.groups.activeGroup.value,
  set: (value: string) => {
    props.groups.activeGroup.value = value;
  }
});
const allGroups = computed(() => props.groups.allGroups.value);

// ── 分组区横向滚动手势（2026-09-05）──
// 分组多时滚动条若常驻占位，会把分组区撑得比右侧操作区高几像素，造成两侧中心错位
// （用户反馈：滚动条出现时两边对不上）。故隐藏原生滚动条、改用「滚轮/触控板横滑」，
// 右缘渐变遮罩（.group-tabs-fade）负责提示还有更多，行高恒定、与右侧恒对齐。
const groupScrollEl = ref<HTMLElement>();
/**
 * 右缘渐变遮罩宽度（px），必须与 CSS `.group-tabs-fade` 的 `width` 一致：
 * 溢出时滚动容器会补同样宽度的 `padding-right`，让最后一个 tab 滚到底时
 * 完全落在遮罩左侧（否则它永远被压掉一截，正是用户报障的现象）。
 */
const FADE_WIDTH = 16;

/** 分组区是否横向溢出：控制滚动容器的尾部留白（.is-overflowing） */
const groupOverflow = ref(false);
/** 右缘渐变遮罩是否显示：仅当「单行 + 横向溢出 + 未滚到底」时显示 */
const showGroupFade = ref(false);

function updateGroupFade() {
  const el = groupScrollEl.value;
  if (!el) {
    showGroupFade.value = false;
    groupOverflow.value = false;
    return;
  }
  // 尾部留白会让 scrollWidth 虚增同样宽度 ⇒ 判定前先扣回去，
  // 否则「内容刚好铺满」会被算成溢出，遮罩在放得下时也亮着（正是本次要修的病）。
  const pad = groupOverflow.value ? FADE_WIDTH : 0;
  const overflow = el.scrollWidth - pad > el.clientWidth + 1;
  groupOverflow.value = overflow;
  if (!overflow) {
    showGroupFade.value = false;
    return;
  }
  // 已滚到最右：右侧没有更多内容可提示，遮罩必须消失 —— 这是「最后一个组名
  // 完全显示」的最终保证（配合尾部留白，滑到底时覆盖量为 0）。
  if (el.scrollLeft >= el.scrollWidth - el.clientWidth - 1) {
    showGroupFade.value = false;
    return;
  }
  // 单行检测：与相邻类型胶囊容器比较垂直中心，若差值 > 2px 即视为已拆行（两行布局）。
  // #2329：① 选择器由 `.filter-bar__center` 更正为真实存在的 `.filter-row`——该 class
  //   早已改名为 .filter-row，此前 closest() 恒为 null、一直在走 parentElement 兜底；
  // ② 比较量由 offsetTop 改为**垂直中心**：`align-items: center` 下不同高度子项即使
  //   同行也有不同 top，用 offsetTop 判同线会在单行时误判成拆行、错误关掉渐隐遮罩。
  const parent = el.closest(".filter-row");
  if (parent) {
    const quickPills = parent.querySelector(".quick-pills-wrap");
    if (quickPills && Math.abs(centerY(el) - centerY(quickPills)) > 2) {
      showGroupFade.value = false; // 已拆行，隐藏遮罩
      return;
    }
  }
  showGroupFade.value = true;
}

/** 元素垂直中心（判「是否同一条 flex 线」用，勿用 offsetTop——见 updateGroupFade 注释）
 *  参数收 Element 而非 HTMLElement：querySelector 的返回类型是 Element | null */
function centerY(el: Element): number {
  const r = el.getBoundingClientRect();
  return r.top + r.height / 2;
}

/** 滚轮横滑：仅当分组区确有溢出时拦截纵向滚轮转为横向，避免干扰行内其它滚动。
 *  绑定在模板 @wheel 上（Vue 自动随 batchMode v-if 切换挂载/解绑）。 */
function handleGroupWheel(e: WheelEvent) {
  const el = groupScrollEl.value;
  if (!el || el.scrollWidth <= el.clientWidth + 1) return;
  const delta = e.deltaY || e.deltaX;
  const next = el.scrollLeft + delta;
  // 仅在滚动位置确实会变化时才拦截纵向滚轮，避免到达边缘时阻止页面竖向滚动
  if (next < 0 || next > el.scrollWidth - el.clientWidth) return;
  e.preventDefault();
  el.scrollLeft = next;
}

// 渐变遮罩按需显示：分组 tab 溢出时才出现，否则隐藏（#ai-review-inline）。
// ResizeObserver 覆盖窗口/容器尺寸变化；watch 分组内容变化覆盖增删/改名导致的溢出变化。
let groupFadeObserver: ResizeObserver | undefined;
onMounted(() => {
  const el = groupScrollEl.value;
  if (!el) return;
  updateGroupFade();
  groupFadeObserver = new ResizeObserver(updateGroupFade);
  groupFadeObserver.observe(el);
  // 字体就绪后重算：组名走 webfont，首帧可能按回退字体量过宽度，
  // 之后又不变（ResizeObserver 只看容器自身尺寸，内容宽度变化它不感知）。
  void document.fonts?.ready.then(() => nextTick(updateGroupFade));
});
onBeforeUnmount(() => groupFadeObserver?.disconnect());
// deep 而非只看 length：分组**改名**同样会改 tab 宽度（旧实现只 watch length，
// 改名引起的溢出状态变化因此一直被漏掉）。
watch(allGroups, () => nextTick(updateGroupFade), { deep: true });
</script>

<style scoped>
/* ===== 分组胶囊 Tab（design.md「分组胶囊 Tab · 方案 B」2026-08-14，数值与 index.vue 原实现逐值对齐） =====
   （样式随模板自 WatchlistFilterBar 原样迁入，保持 scoped 作用域不变，零视觉变更） */

/* 分组区外框：持有 flex 弹性与最小宽度，承载内层滚动区与右缘遮罩。
   min-width 保证分组区不被右侧操作区挤没（#1281 第四轮：本行多了搜索框与按钮组，
   极端窄屏下宁可让整行换行，也要给分组 tab 留 120px 可见区）。

   #2329 换行根修：flex-basis 由 auto 改 0（此前 `flex: 1 1 auto` + `max-width: 50%`）。
   - 原因：`flex-wrap: wrap` 的换行判定发生在**收缩之前**——flexbox 先按每个 item 的
     hypothetical size（= flex-basis 按 min/max 夹紧后的值）决定放哪一行，放不下就换行，
     压根不会先尝试收缩。而 `flex-basis: auto` ⇒ hypothetical size = **内容宽**，
     于是判定条件成了「两区内容宽 + 右段 > 容器宽」。加上两区各 `max-width: 50%`
     把它们钉成各占一半，合计 100% 再加右段 206px ⇒ **必然溢出、必然换行**
     （实测容器 1568→528px 全宽度区间稳定两行，与用户截图一致）。
   - 改法：basis 归零 ⇒ hypothetical 恒为 0，换行判定永不成立；剩余空间由
     flex-grow 按 3:2 分给分组区与品类区（本区 3 份：分组是主导航、项更宽），
     内容超出交给内层 `overflow-x: auto` 横滑兜底（滚轮手势 + 右缘渐隐已具备）。
   - `min-width: 120px` 保底**保留**：容器窄到连两个 120px 保底 + 右段都放不下时
     （实测 < 约 470px），flex-wrap 仍会换行——#1281「宁可换行也不挤没分组」的兜底不受影响。
   - 不可改回 `max-width` 上限：两区同为一个上限时，合计必然占满 100%，
     这正是换行的直接成因。 */
.group-tabs-wrap {
  position: relative;
  display: flex;
  flex: 3 1 0%;
  min-width: 120px;
}

/* 分组区横滑容器。
   原生滚动条必须隐藏（而非常驻）：WebKit 横向滚动条会在容器底部占约 4px，
   把分组区撑得比右侧操作区高、两侧中心错位（#1281 对齐回归，2026-09-05）。
   横滑能力由模板 @wheel 滚轮手势承担，右缘渐变遮罩提示还有更多。 */
.group-tabs-scroll {
  display: flex;
  flex: 1;
  gap: 4px;
  align-items: center;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none; /* Firefox */
  -ms-overflow-style: none; /* 旧 Edge/IE */
}

.group-tabs-scroll::-webkit-scrollbar {
  display: none; /* Chrome / Edge（Chromium） */
}

/* 溢出时给滚动内容补一段与遮罩等宽的尾部留白：
   遮罩是绝对定位、盖在内容之上，不留白的话最后一个 tab 永远被压掉一截
   （滚到底也压着）。留白后滑到最右，最后一项的右缘恰好落在遮罩左边界。
   只在溢出时加——不溢出时加会白占 16px，也会让 scrollWidth 虚增、误判成溢出。 */
.group-tabs-scroll.is-overflowing {
  padding-right: 16px;
}

/* 右缘渐变遮罩：自定义分组多、横向可滑动时，用「渐隐到卡片底色」暗示右侧还有内容。
   遮罩固定在可视区右缘（absolute 于 wrap），不随内容滚动；pointer-events:none 不挡点击。
   默认透明，仅 .is-visible 时显现——**可见性必须由 JS 判定驱动**，因为
   「是否还有内容可滑」不是 CSS 能表达的条件（见 updateGroupFade）。 */
.group-tabs-fade {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 16px;
  pointer-events: none;
  background: linear-gradient(to right, transparent, var(--bg-card));
  opacity: 0;
  transition: opacity 150ms ease;
}

.group-tabs-fade.is-visible {
  opacity: 1;
}

/* tab 项：32px 胶囊；选中态软按钮（--brand-100/--brand-700/--brand-400），未选中 --text-secondary + hover --bg-hover */
.group-tab {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 32px;
  padding: 0 12px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  white-space: nowrap;
  cursor: pointer;
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease,
    border-color 150ms ease;
}

.group-tab:hover {
  background-color: var(--bg-hover);
}

.group-tab.is-active {
  color: var(--brand-700);
  background-color: var(--brand-100);
  border-color: var(--brand-400);
}

.group-tab.is-active:hover {
  background-color: var(--brand-200);
}

/* 分组色点：用户数据色常驻可见（数据色例外），选中态软按钮品牌色不受影响 */
.group-tab-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* 分组名：展示截断 10 汉字（10em），全名由 title 提示。
   2026-11-02：8em → 10em。8em 下 12 字组名只剩 66% 可见，低于「不少于八成」的
   可读底线；10em 让常见组名（≤10 字）完全显示，超长组名也保住 80% 以上。
   代价是单个 tab 最宽多约 2 个字宽——分组区本来就靠横滚 + 右缘遮罩兜底，
   宽度不够时滑一下即可，比「名字永远看不全」划算。 */
.group-tab-label {
  max-width: 10em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-tab-count {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

.group-tab.is-active .group-tab-count {
  color: var(--brand-700);
}
</style>
