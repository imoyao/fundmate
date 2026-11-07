<template>
  <div class="domain-g-body">
    <!-- 四个数字都来自后端扫描结果，前端不做二次推导 -->
    <div class="olg-summary">
      <div class="olg-summary__item">
        <span class="olg-summary__num">{{ data?.total ?? 0 }}</span>
        <span>缺账本流水</span>
      </div>
      <div class="olg-summary__item">
        <span class="olg-summary__num olg-summary__num--ok">{{
          data?.fixable_count ?? 0
        }}</span>
        <span>可精确归属</span>
      </div>
      <div class="olg-summary__item">
        <span class="olg-summary__num">{{ data?.blocked_count ?? 0 }}</span>
        <span>无法归属</span>
      </div>
      <div class="olg-summary__item">
        <span class="olg-summary__num">{{ data?.batch_count ?? 0 }}</span>
        <span>批次数</span>
      </div>
    </div>

    <!-- 覆盖率如实告知：无同名账本 / 同名歧义 / 空账户名的绝不猜 -->
    <p v-if="data && data.blocked_count > 0" class="olg-hint">
      其中 {{ data.blocked_count }}
      条按账户名找不到唯一同名账本，系统不会猜测归属；请到「记一笔」或账户页核对后重新扫描。
    </p>
    <p v-if="data && data.total === 0" class="olg-hint">
      当前没有缺账本流水。回填成功后本域会自然清空，不需要手工标记。
    </p>

    <div v-if="batches.length" class="olg-filter">
      <span class="olg-filter__label">按批次筛选</span>
      <el-select v-model="selectedBatch" size="small" style="width: 220px">
        <el-option label="全部批次" value="all" />
        <el-option
          v-for="b in batches"
          :key="b.id"
          :label="`${b.label}（${b.txn_count} 条）`"
          :value="b.id"
        />
      </el-select>
    </div>

    <div v-if="loading" v-loading="loading" class="olg-state">
      正在扫描缺账本流水…
    </div>
    <el-empty
      v-else-if="visibleGroups.length === 0"
      description="没有缺账本的流水"
      :image-size="80"
    />
    <div v-else class="olg-groups">
      <OrphanLedgerGroupCard
        v-for="g in visibleGroups"
        :key="g.key"
        :group="g"
        @fix="openFix"
      />
    </div>

    <!-- 状态内聚在域内：页面层只负责传数据，不增加 index.vue 的行数 -->
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
import OrphanLedgerGroupCard from "./OrphanLedgerGroupCard.vue";
import OrphanLedgerFixDialog from "./OrphanLedgerFixDialog.vue";

/** 域 G 缺账本孤儿流水主视图（#2875）：暴露 + 选组；回填与撤销在弹窗里完成。 */
const props = defineProps<{
  data: OrphanLedgerList | null;
  loading: boolean;
}>();
const emit = defineEmits<{ submitted: [] }>();

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
  min-width: 84px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.olg-summary__num {
  font-size: var(--text-body);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--color-warning-ink);
}

.olg-summary__num--ok {
  color: var(--color-primary-ink);
}

.olg-hint {
  padding: 0 2px;
  margin: -4px 0 12px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.olg-filter {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.olg-state {
  padding: 24px 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-align: center;
}

.olg-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
