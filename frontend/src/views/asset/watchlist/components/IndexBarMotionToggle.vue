<!--
  IndexBarMotionToggle · 「折叠时滚动展示」开关（#watchlist 指数个性化设置）

  即时生效、不参与弹窗的「保存」：这是纯视图偏好，没有草稿态。
  单独成组件的理由：弹窗已贴着页面规模门禁（400 行，#980），
  把说明文案 + 样式留在弹窗里会把它顶过阈值。
-->
<template>
  <label class="motion-row">
    <span class="motion-row__text">
      <span class="motion-row__title">折叠时滚动展示</span>
      <span class="motion-row__hint">
        关闭后折叠态改为静态（可横向拖动）。系统「减弱动效」开启时不滚动。
      </span>
    </span>
    <el-switch :model-value="enabled" @update:model-value="onToggle" />
  </label>
</template>

<script setup lang="ts">
import { useIndexBarMotionPref } from "@/views/asset/watchlist/composables/useIndexBarMotionPref";

const { enabled, setEnabled } = useIndexBarMotionPref();

/** el-switch 的 value 是 boolean | string | number，这里只接受布尔并显式落盘 */
function onToggle(next: string | number | boolean): void {
  setEnabled(next === true);
}
</script>

<style scoped lang="scss">
.motion-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  cursor: pointer;
  background: var(--bg-page, #fafafa);
  border: 1px solid var(--border-default, #eee);
  border-radius: 10px;

  &__text {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  &__title {
    font-size: var(--text-label);
    font-weight: 600;
    color: var(--text-primary);
  }

  &__hint {
    font-size: var(--text-label);
    line-height: 1.5;
    color: var(--text-secondary);
  }
}
</style>
