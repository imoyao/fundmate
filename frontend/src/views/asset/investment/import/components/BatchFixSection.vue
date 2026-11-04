<script setup lang="ts">
// 批量修正面板的一个分区（「代码未匹配 / 单价数量缺失 / 数据不一致 / 逆回购识别」共用）。
//
// 四个分区的头部结构逐字相同（标签 + 说明 + 条数 tag），差异只在 actions：
// 代码分区要「匹配基金代码 / 输入框 / 应用到全部」，数量分区要「自动填充 / 查看已填充 /
// 撤销 / 逐条修正」，不一致分区要「自动修正金额 / 逐条修正」，逆回购是没有点击的信息区。
// 故把外壳收在这里，actions 走默认插槽。
import type { FixSectionKey } from "../composables/batchFixLogic";

const props = defineProps<{
  /** 渲染成 `data-section`，e2e 靠它定位（`section(page, "mismatch")`） */
  sectionKey: FixSectionKey | "reverse_repo";
  label: string;
  desc: string;
  count: number;
  /** 条数 tag 的颜色档，沿用 `getCategoryTagType` 的四档 */
  tagType: "danger" | "warning" | "success" | "info";
  /** 当前是否被表格筛选选中 */
  active?: boolean;
  /** 信息型分区：不可点击筛选，光标也不该变成手型（逆回购识别） */
  info?: boolean;
  /** 计数提示行（仅「单价/数量缺失」用），null 不渲染 */
  metaText?: string | null;
  metaSub?: string | null;
}>();

const emit = defineEmits<{ select: [] }>();

function onSelect() {
  if (!props.info) emit("select");
}
</script>

<template>
  <section
    class="bf-section"
    :class="{ 'bf-section--active': active, 'bf-section--info': info }"
    :data-section="sectionKey"
    @click="onSelect"
  >
    <div class="bf-section-header">
      <span class="bf-section-label">{{ label }}</span>
      <span class="bf-section-desc">{{ desc }}</span>
      <el-tag size="small" effect="dark" :type="tagType">
        {{ count }} 条
      </el-tag>
    </div>
    <p v-if="metaText" class="bf-section-meta">
      {{ metaText }}
      <span v-if="metaSub" class="bf-section-meta-sub">{{ metaSub }}</span>
    </p>
    <div class="bf-section-actions" @click.stop>
      <slot />
    </div>
  </section>
</template>

<style scoped>
.bf-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  transition: border-color 0.2s;
}

.bf-section:hover,
.bf-section--active {
  border-color: var(--color-primary);
}

.bf-section--info {
  cursor: default;
}

.bf-section-header {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.bf-section-label {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
}

.bf-section-desc {
  flex: 1;
  min-width: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.bf-section-meta {
  margin: 0;
  font-size: var(--text-label);
  color: var(--color-warning-ink);
}

.bf-section-meta-sub {
  color: var(--text-tertiary-ink);
}

.bf-section-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

/* 注意：actions 里的按钮是**父层插槽内容**，带的是父组件 scopeId，子组件的
   `.el-button[data-v-子]` 命中不了它们。`.bf-section-actions .el-button + .el-button`
   与 `.bf-btn-right` / `.bf-input` 同理，都放在 BatchFixPanel.vue 的样式里。 */
</style>
