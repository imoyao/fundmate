<script setup lang="ts">
/**
 * SearchInput · 全站唯一搜索输入框（设计语言强制复用，见 design.md「输入框基线契约」）。
 *
 * ## 为什么要有这个组件（问题驱动）
 *
 * 全站搜索框此前 8 处手写、7 种宽度（168 / 200 / 220 / 240 / 260 / 360 / 100%），
 * 且每个页面各自在 scoped 样式里写死 `width`——「搜名称或代码」这种工具条搜索框
 * 与相邻的下拉 / 按钮比例失衡（168px 窄条 vs 104px 排序下拉），观感粗糙。
 * 本组件收敛「宽度档位 + 前缀搜索图标 + clearable」为一处定义：
 * 视觉（底色 / 边框三态 / 圆角 / 高度 / 焦点单环）**全部**继承自
 * `element-plus.scss` 的输入基线，本组件**只做几何（宽度）**，不复制任何视觉覆盖。
 *
 * ## 宽度三档（唯一真相源）
 *
 * | size | 宽度 | 场景 |
 * |------|------|------|
 * | `sm` | 220px | 工具条 / 卡片内搜索（与相邻 small 控件同高、比例协调） |
 * | `md` | 360px | 页头主搜索（watchlist 头，长 placeholder 不截断，见 #2354） |
 * | `block` | 100% | 面板 / 抽屉内铺满（父容器控宽） |
 *
 * 需要第四种宽度？先回来改这里 + design.md 的档位表，**不要**在页面级再写 `width`。
 *
 * ## 使用方只做两件事
 *
 * - `v-model`（或 `:model-value` + `@update:model-value`）绑关键词；
 * - 传 `placeholder` / `aria-label`（同页多框必须区分 label，E2E 定位靠它）。
 *
 * 前缀 `Search` 图标与 `clearable` 由组件内置，页面不再各自拼 `:prefix-icon="Search"`。
 */
import { Search } from "@element-plus/icons-vue";

defineOptions({ name: "SearchInput" });

const props = withDefaults(
  defineProps<{
    modelValue: string;
    /** `sm` 工具型 / `md` 页头主搜索 / `block` 面板铺满（见上方宽度表） */
    size?: "sm" | "md" | "block";
    placeholder?: string;
    /** 无障碍标签：读屏播报与 E2E 定位用（同页多框必须区分） */
    ariaLabel?: string;
    /** 透传 clearable（默认开） */
    clearable?: boolean;
    /**
     * 软底变体：`--input-bg: var(--bg-soft)` + `--input-height: 32px`，
     * 与分段控制器 / 筛选胶囊对齐同一种「构件边界」语言（工具条场景）。
     * 仍是「覆盖令牌」而非 :deep 视觉覆盖——见 design.md「输入框基线契约」。
     */
    soft?: boolean;
  }>(),
  {
    size: "sm",
    placeholder: "搜索",
    ariaLabel: "搜索",
    clearable: true,
    soft: false
  }
);

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void;
  /** 透传原生 input 事件（供「输入即防抖搜索」类场景挂 debounce，如 watchlist 头） */
  (e: "input", value: string): void;
}>();
</script>

<template>
  <el-input
    :model-value="modelValue"
    :class="[
      'search-input',
      `search-input--${props.size}`,
      { 'search-input--soft': props.soft }
    ]"
    :placeholder="placeholder"
    :aria-label="ariaLabel"
    :clearable="clearable"
    :prefix-icon="Search"
    @update:model-value="emit('update:modelValue', String($event ?? ''))"
    @input="emit('input', String($event))"
  />
</template>

<style scoped>
/* 只做几何（宽度档位）+ 软底令牌覆盖，视觉其余全部继承输入基线。
   禁止在这里覆盖 wrapper / inner 的底色、圆角、焦点环。 */
.search-input--sm {
  width: 220px;
  max-width: 100%;
}

.search-input--md {
  width: 360px;
  max-width: 100%;
}

.search-input--block {
  width: 100%;
}

/* 软底变体：覆盖令牌（design.md 允许），不是 :deep 视觉覆盖 */
.search-input--soft {
  --input-bg: var(--bg-soft);
  --input-height: 32px;
}
</style>
