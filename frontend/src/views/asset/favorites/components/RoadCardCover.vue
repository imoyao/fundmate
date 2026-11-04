<!--
  RoadCardCover · 未竟之蹊卡片封面（#980 批 B6 从 `RoadCard.vue` 抽出）

  封面本身是 `RoadSparkline`（走势曲线 + 类型色层），本组件负责画在它上面的
  四枚浮层：类型胶囊、状态胶囊、「示例」角标，以及右下角的编辑 / 勾选入口。

  为什么单独成组件：这四枚浮层全部是 `position: absolute`，坐标以 `.road-cover`
  为基准。留在 `RoadCard` 里时，卡片正文与底部的样式会和它们混在一个 scoped 块，
  改正文间距要担心碰到悬浮层的 top/right。

  ⚠️ 编辑入口的 `opacity: 0` 基态在这里，但**何时显示由父组件控制**——
  `.road-card:hover` / `:focus-within` 是跨组件的祖先选择器，只能写在 `RoadCard`
  里并用 `:deep()` 穿透。若哪天看到「悬停不显示编辑按钮」，先查父侧那条规则。
-->
<template>
  <RoadSparkline :series="series" :color="color" :metric-label="metricLabel">
    <span class="road-chip road-chip--type">{{ entityLabel }}</span>
    <span class="road-chip road-chip--state" :style="stateStyle">
      {{ stateLabel }}
    </span>
    <span v-if="isDemo" class="road-chip road-chip--demo">示例</span>

    <button
      v-if="manageMode"
      type="button"
      class="road-check"
      :class="{ 'is-on': selected }"
      :aria-label="selected ? '取消选择' : '选择该卡片'"
      @click.stop="$emit('toggle-select')"
    >
      <IconifyIconOffline v-if="selected" icon="ep:check" />
    </button>
    <button
      v-else
      type="button"
      class="road-edit-entry"
      aria-label="编辑这张卡片"
      @click.stop="$emit('start-edit')"
    >
      <IconifyIconOffline icon="ep:edit-pen" />
    </button>
  </RoadSparkline>
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";
import RoadSparkline from "./RoadSparkline.vue";

defineOptions({ name: "RoadCardCover" });

defineProps<{
  /** 收盘价序列（走势缩略图），不足两点时由 RoadSparkline 降级为占位文案 */
  series: number[];
  /** 实体主色（类型胶囊底 + 封面色层） */
  color: string;
  /** 封面口径标注：净值 / 点位 / 价格；空串不渲染 */
  metricLabel: string;
  entityLabel: string;
  stateLabel: string;
  /** 状态胶囊配色（语义色，非涨跌） */
  stateStyle: Record<string, string>;
  isDemo: boolean;
  /** 管理模式：右下角显示勾选圈而不是编辑笔 */
  manageMode: boolean;
  selected: boolean;
}>();

defineEmits<{
  (e: "toggle-select"): void;
  (e: "start-edit"): void;
}>();
</script>

<style scoped>
/* ── 封面胶囊 ── */
.road-chip {
  position: absolute;
  padding: 2px 8px;
  font-size: var(--text-label);
  line-height: 18px;
  white-space: nowrap;
  border-radius: var(--radius-pill);
}

.road-chip--type {
  top: 10px;
  left: 10px;
  color: var(--text-inverse);
  background: var(--card-color);
}

.road-chip--state {
  top: 10px;
  right: 10px;
}

.road-chip--demo {
  right: 10px;
  bottom: 10px;
  color: var(--text-secondary);
  background: var(--glass-bg);
  border: 1px solid var(--border-default);
}

.road-check {
  position: absolute;
  right: 10px;
  bottom: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  color: var(--text-tertiary-ink);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 50%;
}

.road-check.is-on {
  /* #1600：原 `--bg-card` 作文字（design.dark.md 明文红线），暗色下仅 3.43:1 → 改 --text-inverse */
  color: var(--text-inverse);
  background: var(--brand-solid);
  border-color: var(--brand-solid);
}

.road-edit-entry {
  position: absolute;
  right: 10px;
  bottom: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  background: var(--glass-bg);
  border-radius: 50%;
  opacity: 0;
  transition: opacity 0.15s ease;
}

/* 键盘直接聚焦到按钮本身时也要可见（不依赖祖先的 :focus-within） */
.road-edit-entry:focus-visible {
  opacity: 1;
}

@media (hover: none) {
  .road-edit-entry {
    opacity: 1;
  }
}
</style>
