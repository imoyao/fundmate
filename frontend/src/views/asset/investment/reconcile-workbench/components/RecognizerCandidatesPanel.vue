<template>
  <div v-if="rows.length" class="recognizer-candidate-panel">
    <div class="recognizer-candidate-panel__head">
      <span class="recognizer-candidate-panel__title">
        AI 识别候选（{{ kindLabel }}）· {{ rows.length }} 条
      </span>
      <div class="recognizer-candidate-panel__actions">
        <el-button size="small" text @click="emit('discard')">丢弃</el-button>
        <el-button
          size="small"
          type="primary"
          :loading="committing"
          @click="emit('commit', props.kind)"
          >确认入库</el-button
        >
      </div>
    </div>

    <!-- 持仓候选（→ 域 A，#1252） -->
    <el-table
      v-if="props.kind === 'holding'"
      :data="rows"
      size="small"
      stripe
      class="disc-table"
    >
      <el-table-column label="代码" prop="symbol" width="110" />
      <el-table-column label="名称" prop="name" min-width="120" />
      <el-table-column label="份额" prop="quantity" width="110" align="right" />
      <el-table-column label="成本" prop="price" width="100" align="right" />
      <el-table-column label="快照日" prop="snapshot_date" width="120" />
    </el-table>

    <!-- 交易候选（→ 域 C，#1251） -->
    <el-table v-else :data="rows" size="small" stripe class="disc-table">
      <el-table-column label="代码" prop="symbol" width="110" />
      <el-table-column label="名称" prop="name" min-width="120" />
      <el-table-column label="操作" width="90">
        <template #default="{ row }">
          {{ (row as any).op_type_label || row.op_type }}
        </template>
      </el-table-column>
      <el-table-column label="数量" prop="quantity" width="100" align="right" />
      <el-table-column label="金额" prop="amount" width="110" align="right" />
      <el-table-column label="日期" prop="trade_date" width="120" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { RecognizerCandidate } from "@/composables/useReconDraft";

/** AI 识别候选面板（#980 拆分自 index.vue，零行为变更；#1250 / P3-1）：
 *  AI 识别结果落草稿后在三域 Tab 顶部展示，确认后入库并触发对应域对账。
 *  持仓候选（域 A）与交易候选（域 C）结构同构，仅标题与列定义不同，合并为单组件按 kind 渲染。 */
const props = defineProps<{
  kind: "txn" | "holding";
  candidates: RecognizerCandidate[];
  committing: boolean;
}>();

const emit = defineEmits<{
  discard: [];
  commit: [kind: "txn" | "holding"];
}>();

/** 按 kind 过滤候选行（原 index.vue 的 txnCandidates / holdingCandidates） */
const rows = computed(() =>
  props.candidates.filter(c => c.kind === props.kind)
);

const kindLabel = computed(() => (props.kind === "holding" ? "持仓" : "交易"));
</script>

<style scoped>
/* 识别候选面板（样式随模板一并迁入，保持 scoped 作用域不变，零视觉变更） */
.recognizer-candidate-panel {
  padding: 12px 16px;
  margin-bottom: 16px;
  background: color-mix(in srgb, var(--brand-100) 35%, var(--bg-card));
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
}

.recognizer-candidate-panel__head {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.recognizer-candidate-panel__title {
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
}

.recognizer-candidate-panel__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.disc-table {
  width: 100%;
}
</style>
