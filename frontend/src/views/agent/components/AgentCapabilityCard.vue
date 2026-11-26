<!--
  能力卡（单个）。从 AgentHero 拆出——同一个 button 结构在「主入口 / 常用 / 更多」
  三处各写一遍，拆掉重复后 AgentHero 才回到 400 行门禁以内（418 → ~230）。

  两种形态共用一套内部结构，只有主入口多一个方向箭头、图标与标题各大一档：
  分成两个组件会让「主卡只是更大一点的卡」这件事变成两处维护。
-->
<template>
  <button
    type="button"
    class="chat-cap"
    :class="{ 'chat-cap--primary': primary }"
    :data-cap="cap.key"
    data-action="ask-capability"
    @click="emit('ask', cap)"
  >
    <el-icon
      class="chat-cap__icon"
      :class="{ 'chat-cap__icon--primary': primary }"
    >
      <component :is="cap.icon" />
    </el-icon>

    <span class="chat-cap__body">
      <span
        class="chat-cap__label"
        :class="{ 'chat-cap__label--primary': primary }"
      >
        {{ cap.label }}
      </span>
      <span class="chat-cap__hint">{{ cap.hint }}</span>
    </span>

    <!-- 箭头只给主入口：它表示「这是本页的默认下一步」，
         普通卡右侧再挂箭头会变成 10 个指向同一个方向的符号，没有信息 -->
    <el-icon v-if="primary" class="chat-cap__go" aria-hidden="true">
      <ArrowRight />
    </el-icon>
  </button>
</template>

<script setup lang="ts">
import { ArrowRight } from "@element-plus/icons-vue";
import type { AgentCapability } from "../agentQuickActions";

defineOptions({ name: "AgentCapabilityCard" });

defineProps<{
  cap: AgentCapability;
  /** 主入口形态：整行、更大的图标与标题、右侧带箭头 */
  primary?: boolean;
}>();

const emit = defineEmits<{
  (e: "ask", cap: AgentCapability): void;
}>();
</script>

<style lang="scss" scoped>
.chat-cap {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  padding: 12px 14px;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  background-color: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease;

  /* hover 必须真的改点什么。上一版这里写的是 `border-color: var(--border-default)`
     —— 与默认值同一个令牌，等于一条无效声明，可点性只靠底色那一档变化。
     改用 --text-tertiary：它的定义就是「辅助描边/图形级」，暖灰加深一档刚好够看。 */
  &:hover {
    background-color: var(--bg-soft);
    border-color: var(--text-tertiary);
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
  }
}

/* 主入口：整行、纯卡底（透明底在白卡网格里反而最轻）、更大的图标与标题 */
.chat-cap--primary {
  align-items: center;
  padding: var(--space-3) var(--space-4);
  background-color: var(--bg-card);

  /* 主卡 hover 用 brand-700 而不是 brand-500：后者在白底只有 2.1:1，
     达不到非文本对比度 3:1，hover 时几乎看不出边框变了。700 亮 3.9 / 暗 3.5。 */
  &:hover {
    background-color: var(--bg-card);
    border-color: var(--brand-700);
  }
}

.chat-cap__icon {
  flex: 0 0 auto;
  margin-top: 2px;
  font-size: var(--text-body);
  color: var(--brand-700);
}

.chat-cap__icon--primary {
  margin-top: 0;
  font-size: var(--text-heading);
}

.chat-cap__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.chat-cap__label {
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.chat-cap__label--primary {
  font-size: var(--text-body);
}

/* 说明文字：--text-tertiary-ink 而不是 --text-tertiary。
   后者的定义写在 colors.css 里——「辅助底色/描边/图形级，作正文不足 4.5:1」；
   13px 的说明文字属于正文，实测 3.43:1 不到 AA。ink 版亮色 4.96:1、暗色 5.40:1。 */
.chat-cap__hint {
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}

.chat-cap__go {
  flex: 0 0 auto;
  margin-left: auto;
  font-size: var(--text-small);
  color: var(--text-tertiary);
}
</style>
