<template>
  <div class="domain-g-body">
    <!-- 四个数字都来自后端扫描结果，前端不做二次推导 -->
    <div class="olg-summary">
      <div class="olg-summary__item">
        <span class="olg-summary__num">{{ data?.total ?? 0 }}</span>
        <span>没有账本的流水</span>
      </div>
      <div class="olg-summary__item">
        <span class="olg-summary__num olg-summary__num--ok">{{
          data?.fixable_count ?? 0
        }}</span>
        <span>已确定归属</span>
      </div>
      <div class="olg-summary__item">
        <span class="olg-summary__num">{{ data?.blocked_count ?? 0 }}</span>
        <span>归属待核对</span>
      </div>
      <div class="olg-summary__item">
        <span class="olg-summary__num">{{ data?.batch_count ?? 0 }}</span>
        <span>来自几次导入</span>
      </div>
    </div>

    <!-- 覆盖率如实告知：不把用户导向「记一笔」，只说清原因和下一步 -->
    <p v-if="data && data.blocked_count > 0" class="olg-hint">
      有 {{ data.blocked_count }}
      笔找不到唯一对应的账本，系统不会猜测归属。常见原因：账户名与账本名不一致，
      或同名账本有多个。核对账户名后重新检查即可继续。
    </p>
    <p v-if="data && data.total === 0" class="olg-hint">
      当前没有缺账本流水。回填成功后这里会自然清空，不需要手工标记。
    </p>

    <div v-if="batches.length" class="olg-filter">
      <span class="olg-filter__label">来自哪次导入</span>
      <el-select v-model="selectedBatch" size="small" style="width: 260px">
        <el-option label="全部导入" value="all" />
        <el-option
          v-for="b in batches"
          :key="b.id"
          :label="batchLabel(b.label, b.txn_count)"
          :value="b.id"
        />
      </el-select>
    </div>

    <ReconStatusState
      :loading="loading"
      :error="error || null"
      :empty="!loading && !error && visibleGroups.length === 0"
      @retry="emit('retry')"
    >
      <template #empty>
        <el-empty description="没有缺账本的流水" :image-size="80" />
      </template>
      <div class="olg-groups">
        <OrphanLedgerGroupCard
          v-for="g in visibleGroups"
          :key="g.key"
          :group="g"
          @fix="openFix"
        />
      </div>
    </ReconStatusState>

    <!-- 回填与撤销内聚在域内；页面层只负责传数据与接收 submitted -->
    <OrphanLedgerFixDialog
      v-model="fixVisible"
      :group="fixGroup"
      @submitted="emit('submitted')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { OrphanLedgerGroup, OrphanLedgerList } from "@/api/reconciliation";
import { reconBatchLabel } from "../utils/reconDisplay";
import OrphanLedgerGroupCard from "./OrphanLedgerGroupCard.vue";
import OrphanLedgerFixDialog from "./OrphanLedgerFixDialog.vue";
import ReconStatusState from "./ReconStatusState.vue";

/**
 * 域 G 缺账本孤儿流水主视图（#2875）：暴露 + 选组 + 四态。
 * 加载失败与「真的没有待办」不再共用同一个空态。
 */
const props = withDefaults(
  defineProps<{
    data: OrphanLedgerList | null;
    loading: boolean;
    error?: string;
  }>(),
  { error: "" }
);
const emit = defineEmits<{ submitted: []; retry: [] }>();

const batches = computed(() => props.data?.batches ?? []);
const selectedBatch = ref<number | "all">("all");
const visibleGroups = computed(() => {
  const all = props.data?.groups ?? [];
  return selectedBatch.value === "all"
    ? all
    : all.filter(g => g.batch_id === selectedBatch.value);
});

const fixVisible = ref(false);
const fixGroup = ref<OrphanLedgerGroup | null>(null);

function batchLabel(label: string, count: number): string {
  return reconBatchLabel(label, count);
}

function openFix(group: OrphanLedgerGroup): void {
  fixGroup.value = group;
  fixVisible.value = true;
}
</script>

<style scoped>
.domain-g-body {
  padding: 4px 0;
}

.olg-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px 14px;
  margin-bottom: 12px;
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.olg-summary__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 96px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.olg-summary__num {
  font-family: var(--font-mono);
  font-size: var(--text-body);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.olg-summary__num--ok {
  color: var(--color-success-ink);
}

.olg-hint {
  padding: 0 2px;
  margin: -4px 0 12px;
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-secondary);
}

.olg-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.olg-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
