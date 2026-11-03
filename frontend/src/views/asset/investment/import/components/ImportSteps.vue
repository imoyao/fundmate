<script setup lang="ts">
/**
 * 导入向导的步骤条（2026-11-03 由 `el-steps :simple` 改为自绘）。
 *
 * 换掉 Element Plus simple 模式的原因：它给的是一条填色横条（padding 13px + 8% 左右留白 +
 * 浅底），贴在页头下面像一块「膏药」——条子自身有边界，却不属于任何一块内容；
 * 且 finish-status=success 会把已完成的标题整行染绿，四步条上同时出现绿、黑、灰三种文字色，
 * 看上去像三套不同的组件拼起来的。
 *
 * 自绘版只保留「点 + 连线 + 标题」三件事，三态用同一套中性色 + 主色：已完成＝主色淡底对勾、
 * 进行中＝主色描边实心点 + 加粗标题、未开始＝浅灰描边。没有背景块，所以放哪都贴合。
 */
import { computed } from "vue";

const props = defineProps<{
  steps: Array<{ title: string }>;
  /** 当前步下标（0 起）；等于 steps.length 表示全部完成 */
  current: number;
  /** 仅开发态可点击跳转 */
  clickable?: boolean;
}>();

const emit = defineEmits<{ jump: [index: number] }>();

/** 三态只在这里算一次，模板与样式都读它，避免两处各判一遍 */
const items = computed(() =>
  props.steps.map((step, i) => ({
    title: step.title,
    state: i < props.current ? "done" : i === props.current ? "current" : "todo"
  }))
);

function onClick(index: number) {
  if (props.clickable) emit("jump", index);
}
</script>

<template>
  <ol class="steps">
    <li
      v-for="(item, i) in items"
      :key="item.title"
      class="step"
      :class="`is-${item.state}`"
    >
      <!-- 用真 <button> 而不是给 <li> 挂 @click：后者需要 role/tabindex/@keydown 三件套
           才不违反交互可达性守卫，而按钮本来就自带这三件事。非开发态 disabled 掉，
           也就自然退出 Tab 序列（不给用户一个按了没反应的控件）。 -->
      <button
        type="button"
        class="step-main"
        :disabled="!clickable"
        :aria-current="item.state === 'current' ? 'step' : undefined"
        @click="onClick(i)"
      >
        <span class="step-dot">
          <IconifyIconOffline v-if="item.state === 'done'" icon="ep:check" />
        </span>
        <span class="step-label">{{ item.title }}</span>
      </button>
      <span v-if="i < items.length - 1" class="step-sep" aria-hidden="true">
        <IconifyIconOffline icon="ep:arrow-right" />
      </span>
    </li>
  </ol>
</template>

<style scoped>
.steps {
  display: flex;
  align-items: center;
  padding: 0;
  margin: 0;
  list-style: none;
}

.step {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}

/* 按钮化后要抹平 UA 默认外观，否则会多出一块可点的灰底 */
.step-main {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  padding: 0;
  font: inherit;
  color: inherit;
  cursor: pointer;
  background: none;
  border: 0;
}

.step-main:disabled {
  cursor: default;
  opacity: 1;
}

/* 键盘焦点用仓库统一的 --focus-ring，与输入类控件同一套环 */
.step-main:focus-visible {
  border-radius: var(--radius-sm);
  box-shadow: var(--focus-ring);
}

/* 16px 圆点位：三态共用尺寸，只换描边/填充，切换时不会有位置跳动 */
.step-dot {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;

  /* 对勾是圆点里的符号，不是正文：用相对字号把它压到圆点的 ~65%，
     硬写 px 字号会撞上仓库「字号一律走令牌」的 stylelint 规则 */
  font-size: 0.7em;
  border-radius: 50%;
}

.is-done .step-dot {
  color: var(--color-primary-ink);
  background: var(--color-primary-10);
  box-shadow: inset 0 0 0 1px var(--color-primary-20);
}

.is-current .step-dot {
  box-shadow: inset 0 0 0 2px var(--color-primary);
}

/* 进行中的实心内点：和完成态区分开，又不靠颜色抢注意力 */
.is-current .step-dot::after {
  width: 6px;
  height: 6px;
  content: "";
  background: var(--color-primary);
  border-radius: 50%;
}

.is-todo .step-dot {
  box-shadow: inset 0 0 0 1px var(--border-default);
}

.step-label {
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);

  /* 「选择导入账户」曾折成「选择导入账 / 户」：标题统共几个字，宽度够不够都该是一行 */
  white-space: nowrap;
}

.is-done .step-label {
  color: var(--text-secondary);
}

.is-current .step-label {
  font-weight: 600;
  color: var(--text-primary);
}

/* 连接线是标点，不是内容：只做视觉引导，颜色压到最低 */
.step-sep {
  display: inline-flex;
  align-items: center;
  margin: 0 4px;
  font-size: 0.65em;
  color: var(--text-tertiary);
  opacity: 0.6;
}
</style>
