<template>
  <div class="domain-f-body">
    <!-- 汇总条：数字全部来自后端扫描结果，前端不做二次推导。
         只留用户会拿来决策的四个，删掉「导入批次」「待处理分组」这类工程指标。 -->
    <div class="df-summary">
      <div class="df-summary__item">
        <span class="df-summary__num">{{ data?.total ?? 0 }}</span>
        <span>受影响的交易</span>
      </div>
      <div class="df-summary__item">
        <span class="df-summary__num df-summary__num--ok">{{
          data?.fixable_count ?? 0
        }}</span>
        <span>已找到可挂回的持仓</span>
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

    <!-- 覆盖率如实告知，并给下一步：系统只在能确定归属时才允许写，其余不猜 -->
    <p v-if="data && data.total > data.fixable_count" class="df-hint">
      还有 {{ data.total - data.fixable_count }}
      条暂时不能自动处理：缺标的代码，或对应持仓已删除。先补全信息，再回来批量挂回。
    </p>

    <div v-if="batches.length" class="df-filter">
      <span class="df-filter__label">来自哪次导入</span>
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
        <el-empty description="暂无数据缺失" :image-size="80" />
      </template>
      <div class="df-groups">
        <DanglingRefGroupCard
          v-for="g in visibleGroups"
          :key="g.key"
          :group="g"
          @fix="emit('fix', $event)"
          @enrich="open('enrich', $event)"
          @remove="open('remove', $event)"
          @rebuild="openRebuild($event)"
        />
      </div>
    </ReconStatusState>

    <!-- 补全信息 / 删除 / 重建持仓的状态内聚在本域：页面层只加一行 @refresh -->
    <DanglingRefRemediationDialog
      v-model="dialogVisible"
      :group="activeGroup"
      :mode="activeMode ?? 'enrich'"
      @submitted="emit('refresh')"
      @update:model-value="onDialogVisibleChange"
    />
    <DanglingRefRebuildDialog
      v-model="rebuildVisible"
      :group="rebuildGroup"
      @rebuilt="emit('refresh')"
      @update:model-value="onRebuildVisibleChange"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { DanglingRefGroup, DanglingRefList } from "@/api/reconciliation";
import { reconBatchLabel } from "../utils/reconDisplay";
import DanglingRefGroupCard from "./DanglingRefGroupCard.vue";
import DanglingRefRemediationDialog from "./DanglingRefRemediationDialog.vue";
import DanglingRefRebuildDialog from "./DanglingRefRebuildDialog.vue";
import ReconStatusState from "./ReconStatusState.vue";

/**
 * 域 F 数据缺失主视图（#2866）：暴露 + 选组 + 四态。
 * `error` 由 useWorkbenchDomains 的 loadErrors 传入：加载失败不再伪装成「暂无数据缺失」。
 */
const props = withDefaults(
  defineProps<{
    data: DanglingRefList | null;
    loading: boolean;
    error?: string;
  }>(),
  { error: "" }
);
const emit = defineEmits<{
  fix: [group: DanglingRefGroup];
  enrich: [group: DanglingRefGroup];
  remove: [group: DanglingRefGroup];
  refresh: [];
  retry: [];
}>();

const batches = computed(() => props.data?.batches ?? []);
const selectedBatch = ref<number | "all">("all");
const visibleGroups = computed(() => {
  const all = props.data?.groups ?? [];
  return selectedBatch.value === "all"
    ? all
    : all.filter(g => g.batch_id === selectedBatch.value);
});

const activeMode = ref<"enrich" | "delete" | null>(null);
const activeGroup = ref<DanglingRefGroup | null>(null);
const dialogVisible = ref(false);

function batchLabel(label: string, count: number): string {
  return reconBatchLabel(label, count);
}

/** 「删除」按钮对应弹窗的 delete 模式（弹窗 mode 只有 enrich / delete 两态）。 */
function open(mode: "enrich" | "remove", group: DanglingRefGroup): void {
  activeMode.value = mode === "remove" ? "delete" : "enrich";
  activeGroup.value = group;
  dialogVisible.value = true;
}

/** 弹窗收起时清空选中组与模式，避免下次打开残留上一组。 */
function onDialogVisibleChange(visible: boolean): void {
  dialogVisible.value = visible;
  if (!visible) {
    activeGroup.value = null;
    activeMode.value = null;
  }
}

/** 「重建持仓」弹窗：与 enrich / remove 同样的内聚方式，单独一组状态。 */
const rebuildVisible = ref(false);
const rebuildGroup = ref<DanglingRefGroup | null>(null);

function openRebuild(group: DanglingRefGroup): void {
  rebuildGroup.value = group;
  rebuildVisible.value = true;
}

function onRebuildVisibleChange(visible: boolean): void {
  rebuildVisible.value = visible;
  if (!visible) rebuildGroup.value = null;
}
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
  min-width: 96px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.df-summary__num {
  font-family: var(--font-mono);
  font-size: var(--text-body);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.df-summary__num--ok {
  color: var(--color-success-ink);
}

.df-hint {
  padding: 0 2px;
  margin: -4px 0 12px;
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-secondary);
}

.df-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.df-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
