<template>
  <div class="domain-placeholder">
    <div class="domain-placeholder__status">
      <span
        class="domain-status-tag"
        :class="`domain-status-tag--${tab.status}`"
      >
        {{ tab.statusLabel }}
      </span>
      <span class="domain-placeholder__hint">{{ tab.placeholderHint }}</span>
    </div>
    <div class="domain-placeholder__body">
      <p class="domain-placeholder__desc">{{ tab.desc }}</p>
      <div v-if="tab.links.length" class="domain-placeholder__links">
        <el-button
          v-for="(link, i) in tab.links"
          :key="i"
          size="small"
          text
          @click="emit('go', link.to)"
        >
          {{ link.label }}
          <IconifyIconOffline icon="ep:arrow-right" class="ml-1" />
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { IconifyIconOffline } from "@/components/ReIcon";
import type { WorkbenchDomainTab } from "../constants/domainTabs";

/** 域占位内容（#980 拆分自 index.vue，零行为变更）：
 *  未接入实体列表的域（如域 C）展示状态标签 + 说明 + 跳转链接，导航经 emit 上抛。 */
defineProps<{
  tab: WorkbenchDomainTab;
}>();

const emit = defineEmits<{
  go: [to: string | { name: string }];
}>();
</script>

<style scoped>
/* 域占位（样式随模板一并迁入，保持 scoped 作用域不变，零视觉变更） */
.domain-placeholder {
  padding: 8px 4px;
}

.domain-placeholder__status {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
}

.domain-status-tag {
  padding: 2px 10px;
  font-size: 12px;
  line-height: 1.6;
  border-radius: 999px;
}

.domain-status-tag--ready {
  color: var(--color-success-ink);
  background: color-mix(in srgb, var(--color-success) 12%, transparent);
}

.domain-status-tag--planned {
  color: var(--text-tertiary-ink);
  background: var(--bg-soft);
}

.domain-placeholder__hint {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.domain-placeholder__desc {
  margin: 0 0 12px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.domain-placeholder__links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
