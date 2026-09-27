<script setup lang="ts" generic="T extends string | number">
/**
 * SegmentedControl · 轨道式胶囊分段控制器（设计语言强制复用，见 docs/design/components.md）。
 *
 * 用于「多选一、选项少（2–6）」的视图 / 维度 / 档位切换：轨道内平铺胶囊项，
 * 选中态为软按钮（`--brand-100` 底 + `--brand-700` 字）。两档尺寸：
 * `default`＝主视图 / 主维度切换（32px 轨道），`small`＝工具型选项（24px 轨道）。
 *
 * ## 为什么不用 `el-segmented`（#1717）
 *
 * `el-segmented` 的选中滑块是 Element Plus **JS 绝对定位**的独立子元素
 * `.el-segmented__item-selected`，它带来两个只有真机才看得见的缺陷：
 *
 * 1. **几何自相矛盾**：滑块圆角取自 `calc(var(--el-border-radius-base) - 2px)`，
 *    与轨道 / 选项项的 `border-radius` **各算各的**。使用方若只覆盖其中一两个选择器，
 *    就会出现「选中态方块 + hover 胶囊」这种自相矛盾的形态——#1717 在资产总览页实测到。
 * 2. **点击闪一下**：该滑块的初始几何是硬编码的 `left: 0; width: 10px`，真实位置 / 宽度
 *    由 JS 在挂载后与 `modelValue` 变化时（`flush: 'post'`）测量写回，而 EP 给它挂了
 *    `transition: all .3s`。于是**每次点击**滑块都会「从上一项的几何滑到并缩放到本项」，
 *    轨道内出现一段 300ms 的移动 / 伸缩动画——这正是 #1717 报的「点按钮组页面闪一下」。
 *
 * 本仓在 #1717 前有 10 处各写各的分段控制器（5 处直接挂 `el-segmented` 实例 + 5 处手写分段分组，
 * 分布在 8 个文件里），语言漂移出 6 种形态；本组件是收敛后的**唯一**实现，
 * 静态守卫 `scripts/guard_segmented.py` 拦截回潮（新增 `el-segmented` 或页面级手写样式块即 CI 变红）。
 * 例外：eaccount-import 页的实心圆角变体（`import-mode-switch` / `EaccountAiPanel`）是另一套
 * 设计语言，已在守卫白名单登记并另立跟进卡 #1731，不在本次收敛范围。
 *
 * 实现刻意为**纯 DOM + CSS**：没有 JS 定位、没有绝对定位滑块，选中态就是选项项自身的底色，
 * 因此几何永远自洽，点击时只做 `background-color` / `color` 过渡，不会位移或缩放。
 */

interface SegmentedOption<V extends string | number = string> {
  label: string;
  /** 选项值；调用方保证同一组内唯一（字符串维度名或数字档位） */
  value: V;
}

defineOptions({ name: "SegmentedControl" });

const props = withDefaults(
  defineProps<{
    modelValue: T;
    /** 选项；允许 `as const` 的只读数组（调用方常把选项表声明为常量） */
    options: readonly SegmentedOption<T>[];
    /**
     * `default`＝主视图 / 主维度切换（轨道 32px，选项 26px，字号 `--text-label`）；
     * `small`＝工具型选项（如刷新频率 / 展示口径，轨道 24px，选项 20px，字号 12px）。
     */
    size?: "default" | "small";
    /** 铺满父容器宽度，选项等分（如设置抽屉里的 4 档刷新频率） */
    block?: boolean;
    /** 整组禁用（如识别进行中冻结场景切换） */
    disabled?: boolean;
    /** 无障碍标签：读屏播报与 E2E 定位用（同页多组时必须区分） */
    ariaLabel?: string;
  }>(),
  { size: "default", block: false, disabled: false, ariaLabel: "" }
);

const emit = defineEmits<{
  (e: "update:modelValue", value: T): void;
  (e: "change", value: T): void;
}>();

function select(value: T) {
  if (value === props.modelValue) return;
  emit("update:modelValue", value);
  emit("change", value);
}
</script>

<template>
  <div
    class="segmented-control"
    :class="[`segmented-control--${size}`, { 'is-block': block }]"
    role="tablist"
    :aria-label="ariaLabel || undefined"
  >
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      role="tab"
      class="segmented-control__item"
      :class="{ 'is-active': modelValue === opt.value }"
      :aria-selected="modelValue === opt.value"
      :disabled="disabled"
      @click="select(opt.value)"
    >
      {{ opt.label }}
    </button>
  </div>
</template>

<style scoped>
.segmented-control {
  display: inline-flex;
  gap: 2px;
  align-items: center;
  height: 32px;
  padding: 3px;

  /* 轨道补 1px 描边：与筛选入口按钮、面板内胶囊统一「构件边界」语言，
     避免一整条筛选带里只有分段控制器没有边界、显得糊在卡片底色上（2026-09-11）。
     注意：只在**轨道**上加描边；选中项仍保持「浅红软底 + 深红字、无边框」不变。 */
  background-color: var(--bg-soft);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
}

.segmented-control__item {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 26px;
  padding: 0 14px;
  font-family: var(--font-ui);
  font-size: var(--text-label);
  line-height: 1;
  color: var(--text-secondary);
  cursor: pointer;
  background-color: transparent;
  border: none;
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease;
}

/* 原生 button 点击后收掉浏览器默认 focus 外框；键盘导航保留细描边兜底 */
.segmented-control__item:focus {
  outline: none;
}

.segmented-control__item:focus-visible {
  outline: 1px solid var(--brand-400);
  outline-offset: 1px;
}

/* hover 与选中同一几何尺寸、同一层级：仅底色深浅递进（透明 → --bg-hover → --brand-100） */
.segmented-control__item:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}

/* 选中态＝软按钮：浅品牌底 + 深品牌字，无边框（与轨道描边区分开） */
.segmented-control__item.is-active {
  font-weight: 600;
  color: var(--brand-700);
  background-color: var(--brand-100);
}

/* 禁用：整组只读（hover / 选中都退化为中性色，不再给点击暗示） */
.segmented-control__item:disabled {
  color: var(--text-disabled);
  cursor: not-allowed;
}

.segmented-control__item:disabled:hover {
  color: var(--text-disabled);
  background-color: transparent;
}

.segmented-control__item.is-active:disabled,
.segmented-control__item.is-active:disabled:hover {
  color: var(--text-disabled);
  background-color: var(--brand-100);
}

/* 铺满父容器：轨道撑满 + 选项等分（设置抽屉等窄容器场景） */
.segmented-control.is-block {
  display: flex;
  width: 100%;
}

.segmented-control.is-block .segmented-control__item {
  flex: 1;
  min-width: 0;
}

/* ===== small 档：工具型选项（design.md「Segmented（分段控制器）」） =====
   小档不加轨道描边：它常与状态文字 / 图标按钮挤在同一行，
   再补 1px 会让这一行出现第二条「构件边界」而与相邻元素打架 */
.segmented-control--small {
  height: 24px;
  padding: 2px;
  border: none;
}

.segmented-control--small .segmented-control__item {
  height: 20px;
  padding: 0 10px;
  font-size: 12px;
}
</style>
