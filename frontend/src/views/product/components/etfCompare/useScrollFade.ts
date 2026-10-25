import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";

/**
 * 横向滚动容器的**右缘渐隐**（#980 拆分自 `ProductEtfCompare.vue`）。
 *
 * 为什么只在「真的可滚且未滚到尽头」时显示：常显的渐隐会让人以为表格被截断，
 * 滚到底还留着则等于撒谎（右边其实没有内容了）。
 *
 * `overflow > 2` 的容差：亚像素宽度差会让 `scrollWidth - clientWidth` 在 0 与 1
 * 之间抖动，不加容差会在窄屏边界反复闪。
 */
export function useScrollFade() {
  const scroller = ref<HTMLElement | null>(null);
  const scrollable = ref(false);
  const atEnd = ref(false);

  const showFade = computed(() => scrollable.value && !atEnd.value);

  function measure() {
    const el = scroller.value;
    if (!el) {
      scrollable.value = false;
      return;
    }
    const overflow = el.scrollWidth - el.clientWidth;
    scrollable.value = overflow > 2;
    atEnd.value = overflow > 2 && el.scrollLeft >= overflow - 2;
  }

  // 挂载后必须自己量一次。不能只靠调用方的 `watch(rows)`：本组件是**数据到位后**
  // 才被父层 `v-if` 挂上来的，挂载时 `rows` 已经是有值的，那个 watch 不会为它触发
  // 第一次（拆分前 watch 写在父层、父层从空数组变 N 行时必触发一次，等价性就断在这）。
  onMounted(() => {
    window.addEventListener("resize", measure);
    nextTick(measure);
  });

  onBeforeUnmount(() => {
    window.removeEventListener("resize", measure);
  });

  return { scroller, showFade, measure };
}
