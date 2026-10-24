<script setup lang="ts">
// 逐条修正的一张卡片（#783 §4 第 1 条：≤10 条问题自动进入卡片形态）。
//
// 四种分区共用同一张卡片，差异在「正文 + 表单」：
// - error：只显示行内错误，没有可填项（面板内改不了解析结果）；
// - missingCode：一个代码输入框 + 应用；
// - missingQtyPrice：数量 / 单价两个输入框 + 应用；
// - mismatch：显示差额算式 + 「修正此条」。
//
// 草稿由父层持有（按 `_rowKey` 懒建），本组件只做受控输入：拆开写会让「撤销后
// 再回到这条时草稿还在」这个既有行为丢掉。
import type { FixSectionKey } from "../composables/batchFixLogic";
import type { CardDraft } from "./batchFixPanelModel";
import { SECTION_LABELS, mismatchDiffText } from "./batchFixPanelModel";

defineProps<{
  row: any;
  section: FixSectionKey;
  draft: CardDraft;
  tagType: "danger" | "warning" | "success" | "info";
}>();

const emit = defineEmits<{
  "update-draft": [payload: { field: keyof CardDraft; value: string }];
  "apply-code": [];
  "apply-fill": [];
  "fix-amount": [];
  skip: [];
}>();

function onDraft(field: keyof CardDraft, value: string) {
  emit("update-draft", { field, value });
}
</script>

<template>
  <article class="bf-card" data-fix-card :data-section="section">
    <div class="bf-card-header">
      <el-tag size="small" effect="plain" :type="tagType">
        {{ SECTION_LABELS[section] }}
      </el-tag>
      <span class="bf-card-name">
        {{ row.name || row.symbol || "未命名" }}
      </span>
      <span v-if="row.symbol" class="bf-card-meta">{{ row.symbol }}</span>
      <span v-if="row.trade_date" class="bf-card-meta">
        {{ row.trade_date }}
      </span>
    </div>

    <p v-if="section === 'error'" class="bf-card-error">
      {{ row.error }}
    </p>
    <p v-else-if="section === 'mismatch'" class="bf-card-diff">
      {{ mismatchDiffText(row) }}
    </p>

    <div v-if="section === 'missingCode'" class="bf-card-form">
      <el-input
        :model-value="draft.code"
        placeholder="输入证券代码"
        size="small"
        class="bf-input"
        @update:model-value="onDraft('code', $event)"
      />
      <el-button type="primary" size="small" @click="emit('apply-code')">
        应用
      </el-button>
    </div>

    <div v-if="section === 'missingQtyPrice'" class="bf-card-form">
      <el-input
        :model-value="draft.quantity"
        placeholder="数量"
        size="small"
        class="bf-input"
        @update:model-value="onDraft('quantity', $event)"
      />
      <el-input
        :model-value="draft.price"
        placeholder="单价"
        size="small"
        class="bf-input"
        @update:model-value="onDraft('price', $event)"
      />
      <el-button type="primary" size="small" @click="emit('apply-fill')">
        应用
      </el-button>
    </div>

    <div v-if="section === 'mismatch'" class="bf-card-form">
      <el-button type="primary" size="small" @click="emit('fix-amount')">
        修正此条
      </el-button>
    </div>

    <div class="bf-card-footer">
      <el-button size="small" @click="emit('skip')">跳过此条</el-button>
    </div>
  </article>
</template>

<style scoped>
.bf-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  border-left: 3px solid var(--color-warning);
  border-radius: 8px;
}

.bf-card-header {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.bf-card-name {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary);
}

.bf-card-meta {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.bf-card-error {
  margin: 0;
  font-size: var(--text-label);
  color: var(--color-danger-ink, var(--color-warning-ink));
}

.bf-card-diff {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.bf-card-form {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.bf-card-form .el-button + .el-button {
  margin-left: 0;
}

.bf-card-footer {
  display: flex;
  justify-content: flex-end;
}

/* 与 BatchFixSection 各持一份：scoped 样式不跨组件（同那里的注释） */
.bf-input {
  width: 132px;
}
</style>
