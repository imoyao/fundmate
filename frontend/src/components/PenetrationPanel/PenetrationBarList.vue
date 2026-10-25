<template>
  <ul class="bar-list">
    <li v-for="row in rows" :key="row.key" class="bar-row">
      <span class="bar-name" :title="row.title">{{ row.name }}</span>
      <span class="bar-track">
        <span
          class="bar-fill"
          :class="{ 'bar-fill--alt': row.alt }"
          :style="{ width: row.width }"
        />
      </span>
      <span class="bar-value">{{ row.value }}</span>
    </li>
  </ul>
</template>

<script setup lang="ts">
/**
 * 穿透面板的横向条形列表（行业分布 / 个股层共用一个渲染器）。
 *
 * 只做「渲染」：宽度百分比与右侧数值都由父组件按各自口径算好再传进来
 * （行业行以「已穿透」为分母，个股行以「总市值」为分母）——分母口径属于
 * 业务语义，不能在一份共享渲染器里猜。
 */
defineProps<{
  rows: {
    key: string;
    name: string;
    /** 悬浮提示：持有基金数 / 口径说明等 */
    title: string;
    /** 条形宽度（0~100% 的 CSS 宽度字符串） */
    width: string;
    /** 右侧数值文案（已格式化） */
    value: string;
    /** 是否用第二色（个股层与行业层区分） */
    alt?: boolean;
  }[];
}>();
</script>

<style scoped lang="scss">
.bar-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
  padding: 0;
  margin: 0;
  list-style: none;
}

.bar-row {
  display: grid;
  grid-template-columns: minmax(96px, 168px) 1fr 56px;
  gap: var(--space-compact);
  align-items: center;
  font-size: var(--text-small);
  color: var(--text-secondary);
}

.bar-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar-track {
  height: 8px;
  overflow: hidden;
  background: var(--bg-muted);
  border-radius: 4px;
}

.bar-fill {
  display: block;
  height: 100%;
  background: var(--color-primary);
  border-radius: 4px;
}

.bar-fill--alt {
  background: var(--color-info);
}

.bar-value {
  font-variant-numeric: tabular-nums;
  text-align: right;
}
</style>
