<!--
  空态 hero（功能型空态，插画资产就绪前的过渡方案，已同步 design.md）：
  两行大标题 + 品牌渐变词 + 示例问题块。示例问题是**直达入口**——点一下直接发问，
  不是装饰文案，故每条都渲染成 button（键盘可达、有焦点态）。
-->
<template>
  <div class="chat-hero">
    <h2 class="chat-hero__title">
      你未曾留意的账<br />
      <span class="chat-hero__brand">账本精灵</span>全部记清
    </h2>
    <p class="chat-hero__label">试着问一句</p>
    <div class="chat-hero__questions">
      <button
        v-for="ex in examples"
        :key="ex"
        type="button"
        class="chat-hero__q"
        @click="emit('ask', ex)"
      >
        <el-icon class="chat-hero__q-icon"><MagicStick /></el-icon>
        <span>{{ ex }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { MagicStick } from "@element-plus/icons-vue";

defineOptions({ name: "AgentHero" });

defineProps<{
  /** 示例问题（与输入区 chips 同源，见 agentQuickActions.ts） */
  examples: readonly string[];
}>();

const emit = defineEmits<{
  (e: "ask", question: string): void;
}>();
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

// —— 空态 hero（参考竞品：两行大标题 + 品牌渐变词 + 示例问题块）——
.chat-hero {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  align-items: flex-start;
  justify-content: center;

  /* 空态垂直居中：页面改为「外层滚动」后，这里没有可撑开的确定高度参照，
     故用一个视口高估算（顶栏 + 页头 + 输入 dock ≈ 260px）。
     它只影响空态留白，不参与滚动行为（真正的滚动在外层，见 index.vue 注释） */
  min-height: calc(100vh - var(--layout-topbar-height) - 260px);
  padding: var(--space-6) var(--space-2) var(--space-standard);
}

.chat-hero__title {
  margin: 0;
  font-size: var(--text-title);
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-primary);
}

// 品牌渐变词：@supports 条件与块内声明**同写法**，只用不带前缀的
// background-clip:text——stylelint 的 property-no-vendor-prefix（standard 预设）
// 会把 -webkit-background-clip 剥成 background-clip，既制造重复声明（CI 红灯），
// 又会让「条件认 -webkit-、声明只认标准属性」的老浏览器进块拿到
// transparent 却裁不了背景，文字直接消失。不支持的浏览器整块不生效，
// 落回上面的 --brand-700 实色。
.chat-hero__brand {
  color: var(--brand-700);
}

@supports (background-clip: text) {
  .chat-hero__brand {
    color: transparent;
    background: linear-gradient(135deg, var(--brand-700), var(--brand-900));
    background-clip: text;
  }
}

.chat-hero__label {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

.chat-hero__questions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 100%;
  max-width: 640px;
}

.chat-hero__q {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  padding: 14px 18px;
  font-size: var(--text-body);
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  background-color: var(--bg-soft);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease;

  &:hover {
    background-color: var(--bg-hover);
    border-color: var(--border-default);
  }
}

.chat-hero__q-icon {
  flex: 0 0 auto;
  font-size: var(--text-body);
  color: var(--brand-700);
}

@include bp.below("md") {
  .chat-hero {
    padding-top: var(--space-standard);
  }

  .chat-hero__title {
    font-size: var(--text-heading);
  }
}
</style>
