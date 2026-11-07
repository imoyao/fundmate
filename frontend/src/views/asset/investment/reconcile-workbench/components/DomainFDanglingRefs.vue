<template>
  <div class="domain-f-body">
    <!-- 汇总条：五个数字都来自后端扫描结果，前端不做二次推导 -->
    <div class="df-summary">
      <div class="df-summary__item">
        <span class="df-summary__num">{{ data?.total ?? 0 }}</span>
        <span>待处理记录</span>
      </div>
      <div class="df-summary__item">
        <span class="df-summary__num df-summary__num--ok">{{
          data?.fixable_count ?? 0
        }}</span>
        <span>可直接补上关联</span>
      </div>
      <div class="df-summary__item">
        <span class="df-summary__num">{{ data?.group_count ?? 0 }}</span>
        <span>待处理分组</span>
      </div>
      <div class="df-summary__item">
        <span class="df-summary__num">{{ data?.batch_count ?? 0 }}</span>
        <span>导入批次</span>
      </div>
      <div class="df-summary__item">
        <span class="df-summary__num">{{ data?.null_symbol ?? 0 }}</span>
        <span>缺标的代码</span>
      </div>
      <div class="df-summary__item">
        <span class="df-summary__num">{{ data?.null_trade_date ?? 0 }}</span>
        <span>缺交易日期</span>
      </div>
    </div>

    <!-- 覆盖率如实告知：系统只在能确定归属时才允许写，其余不猜 -->
    <p v-if="data && data.total > data.fixable_count" class="df-hint">
      其中
      {{ data.total - data.fixable_count }} 条暂时没法处理：有的没填标的代码，
      有的对应持仓记录已被删除。系统不会替你猜归属，补全信息后重新检查即可继续。
    </p>

    <!-- 批次筛选：只收窄当前可见分组，不改变后端数据 -->
    <div v-if="batches.length" class="df-filter">
      <span class="df-filter__label">按批次筛选</span>
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

    <div v-if="loading" v-loading="loading" class="df-state">正在检查数据…</div>
    <el-empty
      v-else-if="visibleGroups.length === 0"
      description="暂无数据缺失"
      :image-size="80"
    />
    <div v-else class="df-groups">
      <DanglingRefGroupCard
        v-for="g in visibleGroups"
        :key="g.key"
        :group="g"
        @fix="emit('fix', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { DanglingRefGroup, DanglingRefList } from "@/api/reconciliation";
import DanglingRefGroupCard from "./DanglingRefGroupCard.vue";

/**
 * 域 F 悬空引用主视图（#2866）。
 * 只做「暴露 + 选组」；预览 → 回补 → 撤销在 DanglingRefFixDialog 里完成。
 */
const props = defineProps<{
  data: DanglingRefList | null;
  loading: boolean;
}>();
const emit = defineEmits<{ fix: [group: DanglingRefGroup] }>();

const batches = computed(() => props.data?.batches ?? []);
const selectedBatch = ref<number | "all">("all");
const visibleGroups = computed(() => {
  const all = props.data?.groups ?? [];
  return selectedBatch.value === "all"
    ? all
    : all.filter(g => g.batch_id === selectedBatch.value);
});
</script>

<style scoped>
.domain-f-body {
  padding: 4px 0;
}

.df-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px 14px;
  margin-bottom: 12px;
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}

.df-summary__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 84px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.df-summary__num {
  font-size: var(--text-body);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--color-warning-ink);
}

.df-summary__num--ok {
  color: var(--color-primary-ink);
}

.df-hint {
  padding: 0 2px;
  margin: -4px 0 12px;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.df-filter {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.df-state {
  padding: 24px 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-align: center;
}

.df-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
