<!--
  PnlCalendarCaliberIcon · 收益日历口径 ⓘ 图标（#2050）

  从 PnlCalendar 的 SectionHeader `#info` 插槽上提为独立组件，供「宿主自画标题」
  的场景复用。视觉契约与 `SectionHeader` 的 `.section-header__info` 完全一致：
  同一枚 ep:info-filled 图标、同一份 hover/focus 配色、同一个 `rich-tip` 气泡 class、
  同一份 `PnlCalendarCaliberTip` 富内容。

  ## 为什么需要它

  `PnlCalendar` 在 `hostHeader` 模式下不再渲染自己的 `SectionHeader`（标题 + ⓘ
  一并交给宿主）。但口径说明是 PnlCalendar 自己的信息，宿主不承载——所以把 ⓘ
  抽成组件，宿主在自画 `<h3>` 旁边 `<PnlCalendarCaliberIcon />` 即可，不必
  复制 tooltip 内容与样式。
-->

<template>
  <el-tooltip placement="top" popper-class="rich-tip">
    <span
      class="pnl-calendar-caliber-icon"
      tabindex="0"
      role="img"
      aria-label="收益日历的口径与图例说明"
    >
      <IconifyIconOffline icon="ep:info-filled" />
    </span>
    <template #content>
      <PnlCalendarCaliberTip />
    </template>
  </el-tooltip>
</template>

<script setup lang="ts">
import { Icon as IconifyIconOffline } from "@iconify/vue";
import PnlCalendarCaliberTip from "./PnlCalendarCaliberTip.vue";

defineOptions({ name: "PnlCalendarCaliberIcon" });
</script>

<style scoped>
/* 与 SectionHeader 的 .section-header__info 视觉契约完全一致（同一枚图标、
   同一份配色），确保宿主标题行里的 ⓘ 与满宽容器里 SectionHeader 自画的 ⓘ
   看不出区别。 */
.pnl-calendar-caliber-icon {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  font-size: var(--text-body);
  color: var(--text-tertiary-ink);
  cursor: help;
  transition: color 0.15s ease;

  &:hover,
  &:focus-visible {
    color: var(--brand-700);
    outline: none;
  }
}
</style>
