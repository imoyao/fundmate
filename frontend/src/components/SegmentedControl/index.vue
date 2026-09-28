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
 *
 * ## 语言边界（#1731 收编后定稿）
 *
 * `role="tablist"` 的「多选一、选项少」控件**一律**走本组件——筛选（`全部/股票/基金`）、
 * 档位（`市值/份额/收益率`）、视图（`资产端/负债端`）、维度（`按产品/按渠道`）、排序皆然。
 * #1731 把剩余 8 处手写按钮组收编进来，含此前登记在白名单里的 eaccount-import 实心变体。
 *
 * **不属本组件**的两类（各有独立登记语言，勿混）：
 *
 * - **分组胶囊 Tab**（`design.md` 专节）：带数量徽章 + 横向滚动的**分组导航**，选中态多一道
 *   `--brand-400` 边框、hover 加深到 `--brand-200`，与 `--border-subtle` 分割线配套
 *   （参考 `views/explore/index.vue` 的 `.panel-switch`）。
 * - **水平滑动胶囊栏**（`design.md`「Filter & Selection」的二级筛选）：一级筛选下方的
 *   **状态 / 子维度**筛选，`overflow-x: auto` 严禁换行（参考 `RoadFilterBar.vue` 的 `.road-pills--scroll`）。
 *
 * ## 为什么选中态是软按钮而不是实心品牌底（#1731 裁决）
 *
 * 实心选中态（`--brand-600` 底 + `--text-inverse` 白字）在本仓实测仅 **3.02:1**，连 WCAG AA 的
 * 大字档（3:1）都不到；且 `--brand-600` 在 `design.md` 里是「激活边框」而非填充色。
 * 改用合规的 `--brand-solid`（=`--brand-800`，白字 4.92:1）同样不行——那会让选中项与同页的
 * 真实主按钮（同为 `--brand-solid`）**外观撞脸**，同屏出现两个「主按钮」= 供能歧义。
 * 故裁决：**不加 `variant="solid"`**，全站统一软按钮。
 *
 * 实现刻意为**纯 DOM + CSS**：没有 JS 定位、没有绝对定位滑块，选中态就是选项项自身的底色，
 * 因此几何永远自洽，点击时只做 `background-color` / `color` 过渡，不会位移或缩放。
 */

interface SegmentedOption<V extends string | number = string> {
  label: string;
  /** 选项值；调用方保证同一组内唯一（字符串维度名或数字档位） */
  value: V;
  /**
   * 可选数量徽章（#1731）。用于「带计数的一级筛选」（如自选页 `全部 12 / 股票 5 / 基金 7`）。
   * 传 `undefined` 即不渲染徽章；传 `0` 会渲染 `0`（不做 falsy 吞并——计数为 0 是有信息量的）。
   * 与「分组胶囊 Tab」的数量徽章同语言：`tabular-nums` + 未选中 `--text-tertiary-ink` /
   * 选中 `--brand-700`。**唯一的语义差异**：分组胶囊 Tab 用 `v-if="count > 0"` 隐藏 0
   * （用户自建分组为空时不值得占位），而筛选场景下「某类别 0 条」本身就是结论，故此处照渲染。
   */
  count?: number;
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
      <!-- 数量徽章（#1731）：只在传了 count 时渲染。注意判 `!== undefined`——
           计数为 0 是有信息量的，用 `v-if="opt.count"` 会把 0 静默吞掉。 -->
      <span v-if="opt.count !== undefined" class="segmented-control__count">{{
        opt.count
      }}</span>
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
  gap: 5px;
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

/* 数量徽章（#1731）：与「分组胶囊 Tab」的数量徽章同语言（`design.md`「分组胶囊 Tab」）——
   继承正文字族 + `tabular-nums`（**不**切 `--font-mono`：那里「等宽」指的是数字对齐，
   参考实现 `FilterGroupTabs.vue` 的 `.group-tab-count` 也是继承字族），
   未选中 `--text-tertiary-ink`、选中 `--brand-700`。
   字号取「同级标签 −1px」：`default` 档标签 13px → 徽章 12px（与分组胶囊 Tab 的 12px 对齐），
   `small` 档标签 12px → 徽章 11px。 */
.segmented-control__count {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

.segmented-control__item.is-active .segmented-control__count {
  color: var(--brand-700);
}

/* 禁用时徽章同步退化为中性色（否则选中项整体变灰、徽章仍是品牌红） */
.segmented-control__item:disabled .segmented-control__count {
  color: var(--text-disabled);
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

/* small 档标签降到 12px，徽章同步降一档（见上方 `.segmented-control__count` 字号规则） */
.segmented-control--small .segmented-control__count {
  font-size: 11px;
}
</style>
