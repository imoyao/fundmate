<script setup>
/**
 * 更新日志时间线。数据在**构建期**由 docs/.vitepress/theme/index.ts 的
 * data loader 注入（构建时于 Node 中 fetch，不受浏览器 CORS 限制）。
 *
 * 单一真值源是 FeedLog；本页不维护第二份内容。
 * 降级（外部 API 不可达）时显示提示而非空白——构建不该被外部站点抖动打断。
 */
import { onMounted, ref } from 'vue'

const props = defineProps({
  entries: { type: Array, default: () => [] },
  degraded: { type: Boolean, default: false },
  sourceError: { type: String, default: '' },
})

// 折叠状态按 index 记；与FeedLog 的交互一致：前两条展开，其余折叠。
const expanded = ref(new Set([0, 1]))

function toggle(i) {
  const next = new Set(expanded.value)
  next.has(i) ? next.delete(i) : next.add(i)
  expanded.value = next
}

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
</script>

<template>
  <div class="changelog-timeline">
    <div v-if="props.degraded" class="changelog-degraded">
      <p><strong>更新日志暂时无法加载。</strong></p>
      <p>
        数据源（feedback.duoduobei.com）本次构建时不可达
        <code v-if="props.sourceError">{{ props.sourceError }}</code>。
        请直接访问
        <a href="https://feedback.duoduobei.com/changelog" target="_blank" rel="noopener">FeedLog 更新日志</a>。
      </p>
    </div>

    <p v-else-if="!props.entries.length" class="changelog-empty">
      暂无已发布的版本记录。
    </p>

    <template v-else>
      <article v-for="(e, i) in props.entries" :key="e.id" class="changelog-entry">
        <header class="changelog-entry__head">
          <h3 class="changelog-entry__title">{{ e.title }}</h3>
          <time class="changelog-entry__date" :datetime="e.publishedAt">{{ fmtDate(e.publishedAt) }}</time>
        </header>

        <div
          class="changelog-entry__body"
          :class="{ 'is-collapsed': !expanded.has(i) }"
          v-html="e.content"
        />

        <button class="changelog-entry__toggle" @click="toggle(i)">
          {{ expanded.has(i) ? '收起' : '展开' }}
        </button>

        <p v-if="e.url" class="changelog-entry__more">
          <a :href="e.url" target="_blank" rel="noopener">查看完整页面 →</a>
        </p>
      </article>
    </template>
  </div>
</template>

<style scoped>
.changelog-timeline { margin-top: 1.5rem; }

.changelog-entry {
  padding: 1.25rem 0;
  border-bottom: 1px solid var(--vp-c-divider);
}
.changelog-entry:first-child { padding-top: 0.5rem; }

.changelog-entry__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}
.changelog-entry__title {
  font-size: 1.15rem;
  font-weight: 600;
  margin: 0;
  line-height: 1.4;
}
.changelog-entry__date {
  font-size: 0.85rem;
  color: var(--vp-c-text-2);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.changelog-entry__body {
  margin-top: 0.75rem;
  line-height: 1.75;
  overflow-wrap: break-word;
}
.changelog-entry__body.is-collapsed {
  display: -webkit-box;
  -webkit-line-clamp: 4;
  line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.changelog-entry__toggle {
  margin-top: 0.6rem;
  background: none;
  border: 1px solid var(--vp-c-divider);
  border-radius: 6px;
  padding: 0.25rem 0.7rem;
  font-size: 0.85rem;
  color: var(--vp-c-text-2);
  cursor: pointer;
}
.changelog-entry__toggle:hover {
  color: var(--vp-c-text-1);
  border-color: var(--vp-c-divider-2);
}

.changelog-entry__more {
  margin: 0.6rem 0 0;
  font-size: 0.9rem;
}

.changelog-degraded {
  padding: 1rem 1.25rem;
  border-left: 3px solid var(--vp-c-warning-2);
  background: var(--vp-c-bg-soft);
  border-radius: 6px;
}
.changelog-degraded p { margin: 0.35rem 0; }

.changelog-empty { color: var(--vp-c-text-2); }
</style>