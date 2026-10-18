<template>
  <!-- 类型快捷胶囊栏（#2199 胶囊化，替代原 SegmentedControl）：
       design.md「Filter & Selection」分水岭裁决——选项由用户偏好外显（#1449），
       自定义后可达 11 项（全部 + 10 类型），超出分段器「选项少（2–6）、平铺」
       的适用域，切换为「水平滑动胶囊栏」语言，视觉与 FilterGroupTabs 同一套
       （32px 胶囊 + 软按钮选中态）。溢出时隐滚动条 + 滚轮横滑 + 右缘渐变遮罩。
       注意：不要套裸 <template>（无指令时会被渲染成原生 <template> 元素，分组 Tab
       处已踩坑，见 FilterGroupTabs 模板注释）。 -->
  <div class="quick-pills-wrap">
    <div
      ref="pillScrollEl"
      class="quick-pills-scroll"
      role="group"
      aria-label="类型快捷筛选"
      @wheel="handlePillWheel"
    >
      <!-- 单选覆盖式按钮组：aria-pressed 表达激活态。
           不采用 tablist 角色——此处是筛选维度快速切换而非视图切换容器，
           普通按钮组 + aria-label 语义已足够（design.md 语言边界） -->
      <button
        v-for="opt in options"
        :key="opt.value"
        type="button"
        class="quick-pill"
        :class="{ 'is-active': opt.value === activeValue }"
        :aria-pressed="opt.value === activeValue"
        :title="opt.label"
        @click="emit('select', opt.value)"
      >
        {{ opt.label }}
      </button>
    </div>
    <!-- 右缘渐变遮罩：溢出时暗示可横向滑动（纯装饰，不拦截指针事件）；
         v-show 控制「仅溢出才出现」，未溢出时不留渐变误导 -->
    <span v-show="showPillFade" class="quick-pills-fade" aria-hidden="true" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from "vue";

/** 快捷胶囊项：label 已由调用方经 assetTypeLabel 映射，本组件不碰业务语义 */
export interface QuickTypePillOption {
  label: string;
  value: string;
}

const props = defineProps<{
  /** 胶囊项（首项由调用方拼「全部」，组件只负责渲染与滚动） */
  options: QuickTypePillOption[];
  /** 当前激活值（'' 表示组合态 / 无高亮，由调用方派生） */
  activeValue: string;
}>();

const emit = defineEmits<{
  /** 点击某项（单选覆盖式语义由调用方实现：再点当前项 → 取消回「全部」） */
  (e: "select", value: string): void;
}>();

// ── 横向滚动手势（照搬 FilterGroupTabs 成熟模式，#2199）──
// 原生滚动条常驻会占约 4px 把胶囊区撑高、与相邻分区中心错位；
// 故隐藏滚动条，横滑由滚轮手势承担，右缘渐变遮罩提示还有更多。
const pillScrollEl = ref<HTMLElement>();
/** 右缘渐变遮罩是否显示：仅当「单行且横向溢出」时显示；两行拆行时隐藏（#2213） */
const showPillFade = ref(false);
function updatePillFade() {
  const el = pillScrollEl.value;
  if (!el) {
    showPillFade.value = false;
    return;
  }
  const overflow = el.scrollWidth > el.clientWidth + 1;
  if (!overflow) {
    showPillFade.value = false;
    return;
  }
  // 单行检测：与相邻分组 Tab 容器比较垂直中心，若差值 > 2px 即视为已拆行（两行布局）。
  // #2329：① 选择器由 `.filter-bar__center` 更正为真实存在的 `.filter-row`——该 class
  //   早已改名为 .filter-row，此前 closest() 恒为 null、一直在走 parentElement 兜底
  //   （碰巧等价于 .filter-row，故从不出错，也因此从未被发现）；
  // ② 比较量由 offsetTop 改为**垂直中心**：`align-items: center` 会让不同高度的子项
  //   （32px 胶囊 vs 20px 分区分割线）即使在同一行也有不同 top，用 offsetTop 判同线
  //   会在单行时误判成拆行、把渐隐遮罩错误地关掉。
  const parent = el.closest(".filter-row");
  if (parent) {
    const groupTabs = parent.querySelector(".group-tabs-wrap");
    if (groupTabs && Math.abs(centerY(el) - centerY(groupTabs)) > 2) {
      showPillFade.value = false; // 已拆行，隐藏遮罩
      return;
    }
  }
  showPillFade.value = true;
}

/** 元素垂直中心（判「是否同一条 flex 线」用，勿用 offsetTop——见 updatePillFade 注释）
 *  参数收 Element 而非 HTMLElement：querySelector 的返回类型是 Element | null */
function centerY(el: Element): number {
  const r = el.getBoundingClientRect();
  return r.top + r.height / 2;
}

/** 滚轮横滑：仅当胶囊区确有溢出时拦截纵向滚轮转为横向，避免干扰页面滚动 */
function handlePillWheel(e: WheelEvent) {
  const el = pillScrollEl.value;
  if (!el || el.scrollWidth <= el.clientWidth + 1) return;
  const delta = e.deltaY || e.deltaX;
  const next = el.scrollLeft + delta;
  // 仅在滚动位置确实会变化时才拦截纵向滚轮，避免到达边缘时阻止页面竖向滚动
  if (next < 0 || next > el.scrollWidth - el.clientWidth) return;
  e.preventDefault();
  el.scrollLeft = next;
}

// 渐变遮罩按需显示：ResizeObserver 覆盖窗口 / 容器尺寸变化（布局争夺区
// flex max-width 变化也在其内）；watch 选项数变化覆盖偏好增删导致的溢出变化。
let pillFadeObserver: ResizeObserver | undefined;
onMounted(() => {
  const el = pillScrollEl.value;
  if (!el) return;
  updatePillFade();
  pillFadeObserver = new ResizeObserver(updatePillFade);
  pillFadeObserver.observe(el);
});
onBeforeUnmount(() => pillFadeObserver?.disconnect());
watch(
  () => props.options.length,
  () => nextTick(updatePillFade)
);
</script>

<style scoped>
/* 胶囊区外框：#2199 布局争夺方案——与分组胶囊区（FilterGroupTabs）并列为
   两个弹性区。#2329 换行根修：flex-basis 由 auto 改 0，且**去掉 max-width 上限**。
   - 原因：`flex-basis: auto` 让 hypothetical size = 内容宽，而 flex-wrap 的换行判定
     发生在收缩之前 ⇒ 判定条件是「两区内容宽 + 右段 > 容器宽」；再叠加两区各
     `max-width: 50%`，合计恒为 100%，加右段必溢出 ⇒ 用户截图里右段被甩到第二行。
     推导与逐条实测见 FilterGroupTabs 的 .group-tabs-wrap 注释。
   - 改法：basis 0 ⇒ hypothetical 恒 0，换行判定永不成立；剩余空间按 2 份分给本区
     （分组区 3 份），超出交给内层 `overflow-x: auto` 横滑（滚轮手势 + 右缘渐隐已具备）。
   - `min-width: 120px` 保底保留，窄屏换行兜底不受影响。 */
.quick-pills-wrap {
  position: relative;
  display: flex;
  flex: 2 1 0%;
  min-width: 120px;
}

/* 横滑容器：滚动条隐藏（而非常驻），横滑由 @wheel 手势承担 */
.quick-pills-scroll {
  display: flex;
  flex: 1;
  gap: 4px;
  align-items: center;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none; /* Firefox */
  -ms-overflow-style: none; /* 旧 Edge/IE */
}

.quick-pills-scroll::-webkit-scrollbar {
  display: none; /* Chrome / Edge（Chromium） */
}

/* 右缘渐变遮罩：溢出时「渐隐到卡片底色」暗示右侧还有内容；
   固定在可视区右缘（absolute 于 wrap），不随内容滚动；pointer-events:none 不挡点击 */
.quick-pills-fade {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 28px;
  pointer-events: none;
  background: linear-gradient(to right, transparent, var(--bg-card));
}

/* 胶囊项：数值与 FilterGroupTabs 的 .group-tab 逐值对齐（32px 胶囊 / 软按钮选中态），
   同语言不同职责——此处是类型维度筛选，非分组导航 */
.quick-pill {
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

.quick-pill:hover {
  background-color: var(--bg-hover);
}

.quick-pill.is-active {
  color: var(--brand-700);
  background-color: var(--brand-100);
  border-color: var(--brand-400);
}

.quick-pill.is-active:hover {
  background-color: var(--brand-200);
}
</style>
