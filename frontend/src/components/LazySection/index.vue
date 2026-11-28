<!--
  LazySection · 长页区块的「锚点常驻、内容懒挂」

  ## 解决什么问题

  复盘页一个页面挂 10 个区块，每个都在 `onMounted` 里自己取数、其中 4 个还会建
  echarts 实例。首屏实际只看得到前三块，但后七块的请求与图表初始化全都挤在同一帧
  发出——后端是单 worker，10 个并发排队，首屏最后一个请求要等前面全部完成。

  ## 为什么锚点（`<section id>`）必须常驻，只懒挂内容

  页内导航的条目来自 `usePageNav` **扫 DOM 里真实存在的 `nav-` 锚点**（见
  `composables/usePageNav.ts` 文件头）。如果懒加载连锚点一起省掉，未挂载的区块
  就没有锚点，右侧目录 rail 直接少几项、scroll-spy 也认不出它们——导航退化，
  比性能问题严重得多。

  反方向的诱惑是「给 usePageNav 传一份静态锚点清单」。那是**错误解法**：清单与
  真实渲染脱钩后必然长死链——本页的「浮亏回本」「货币基金收益」是 `v-if` 数据
  驱动（无浮亏 / 无货基时整块不渲染），静态清单会把它们钉在导航里，点一下原地
  不动。所以这里选择：**锚点由「这块该不该有」决定，内容由「看不看得见」决定**，
  两件事分开。DOM 扫描因此仍是唯一真相源，`usePageNav` 一行不用改。

  ## 为什么不用 `content-visibility: auto`

  `content-visibility` 只跳过**渲染**，组件照样挂载、`onMounted` 照样跑、请求
  照样发出——省的是绘制，不是首屏并发。而这个页面的瓶颈恰恰是后者。

  ## 挂载时机

  - `eager`：首屏区块，首帧就挂（IO 首次回调要等一帧，首屏用它避开闪一下）；
  - 其余：`IntersectionObserver` 提前 `PRELOAD_MARGIN` 激活，滚到时内容已经在了；
  - **激活后不回收**：回收会让用户往回滚时内容消失、整页高度变化，scroll-spy
    与滚动位置同时错乱，比一直挂着更糟。

  ## 占位高度

  占位只给 `min-height`，不给视觉（不加骨架/边框）：提前量足够时占位几乎不可见，
  画出来的「加载框」反而比空白更像故障。高度必须传接近真实值——占位太矮会让下方
  锚点全部上移，rail 的高亮跟着错位，直到区块被激活为止。页面按实测值传。
-->
<template>
  <section :id="anchorId" ref="root" class="lazy-section">
    <slot v-if="activated" />
    <div
      v-else
      class="lazy-section__placeholder"
      :style="{ minHeight: `${minHeight}px` }"
      aria-hidden="true"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, ref } from "vue";
import { LAZY_SECTION_REGISTRY, type LazySectionRegistry } from "./registry";

defineOptions({ name: "LazySection" });

const props = withDefaults(
  defineProps<{
    /** 锚点 id（`nav-` 前缀）：必须挂在**外层 section** 上，内容组件里不能再挂同一个
     *  id——重复 id 会让 `querySelectorAll` 扫到两次，导航里这一项出现两遍。 */
    anchorId: string;
    /** 首屏区块：首帧即挂载，不等 IO 回调（避免先闪一帧占位再长出来） */
    eager?: boolean;
    /** 占位高度（px）：按该块真实高度传，偏差越大下方锚点错位越明显 */
    minHeight?: number;
    /** 提前量（px）：距视口还有这么远就激活。默认一屏高度以内，滚到时已挂好 */
    preloadMargin?: number;
  }>(),
  { eager: false, minHeight: 420, preloadMargin: 300 }
);

const root = ref<HTMLElement>();
const selfActivated = ref(props.eager);
/** props.eager 之后可能被父级改（如切档重取），故用 computed 而不是初始值一拍定死 */
const activated = computed(() => props.eager || selfActivated.value);

const registry = inject<LazySectionRegistry | null>(
  LAZY_SECTION_REGISTRY,
  null
);
const activate = () => {
  selfActivated.value = true;
};

let observer: IntersectionObserver | null = null;
const stopObserving = () => {
  observer?.disconnect();
  observer = null;
};

onMounted(() => {
  // 注册在挂载时、注销在卸载时：页内导航的跳转要能在这里按 anchorId 找到我
  registry?.set(props.anchorId, activate);
  if (activated.value || !root.value) return;
  observer = new IntersectionObserver(
    entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        activate();
        stopObserving();
      }
    },
    { rootMargin: `${props.preloadMargin}px 0px` }
  );
  observer.observe(root.value);
});

onBeforeUnmount(() => {
  stopObserving();
  // 只删自己这一条：同一 anchorId 若换了实例（热更新 / 条件重建），
  // 删之前确认注册的仍是自己，别把新实例的入口删掉
  if (registry?.get(props.anchorId) === activate) {
    registry.delete(props.anchorId);
  }
});

defineExpose({ activate });
</script>

<style lang="scss" scoped>
/* section 本身不加样式：它只是锚点载体，纵向间距由父级 flex gap 负责。
   占位块同理——高度是唯一职责，任何底色/边框都会让「还没加载」看起来像故障。 */
.lazy-section__placeholder {
  width: 100%;
}
</style>
