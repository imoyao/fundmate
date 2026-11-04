<script setup lang="ts">
import { useImportWizardContext } from "../composables/useImportWizardContext";

const { formatGuides, selectedMode } = useImportWizardContext();
</script>

<template>
  <div v-if="formatGuides[selectedMode]" class="format-guide">
    <div class="format-guide-header">
      <IconifyIconOffline icon="ep:info-filled" class="format-guide-icon" />
      <span>{{ formatGuides[selectedMode].title }}</span>
    </div>
    <ol class="format-guide-list">
      <li v-for="(tip, index) in formatGuides[selectedMode].tips" :key="index">
        {{ tip }}
      </li>
    </ol>
  </div>
</template>

<style scoped>
.format-guide {
  display: flex;
  flex-direction: column;
  padding: 18px 20px;
  margin-top: 0;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: 0 1px 4px rgb(0 0 0 / 4%);
}

.format-guide-header {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 14px;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.format-guide-icon {
  font-size: var(--text-num-strong);
  color: var(--color-primary-ink);
}

/* 横向自动分栏（#2836）：容器通栏后按可用宽度切成 2~4 栏，每条提示从
   窄栏里的 3~4 行降到 1~2 行。minmax 下限 250px 是实测值——再窄则最长那条
   （「下载 CSV 模板填写数据，或直接上传同花顺等券商导出的 Excel/CSV 文件」）
   又要折到第 3 行，与原来的窄栏没区别。 */
.format-guide-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 10px 28px;
  padding-left: 0;
  margin: 0;
  list-style: none;
  counter-reset: step-counter;
}

.format-guide-list li {
  display: flex;
  align-items: baseline;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
  counter-increment: step-counter;
}

.format-guide-list li::before {
  flex-shrink: 0;
  min-width: 18px;
  margin-right: 8px;
  font-weight: 600;
  color: var(--color-primary-ink);
  content: counter(step-counter) ".";
}
</style>
