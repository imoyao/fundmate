<template>
  <div class="domain-b-body">
    <el-empty
      v-if="!loading && items.length === 0"
      description="暂无待处理差异"
      :image-size="80"
    />
    <div v-else class="disc-table-wrap">
      <el-table :data="items" stripe size="small" class="disc-table">
        <el-table-column label="代码" prop="symbol" width="110" />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <span class="disc-type">{{ typeLabel(row.discrepancy_type) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          label="理论"
          prop="expected_value"
          width="100"
          align="right"
        />
        <el-table-column
          label="实际"
          prop="actual_value"
          width="100"
          align="right"
        />
        <el-table-column label="差异" width="100" align="right">
          <template #default="{ row }">
            <span :class="diffClass(row.diff)">{{ formatDiff(row.diff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <span class="disc-status" :class="`disc-status--${row.status}`">
              {{ statusLabel(row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <!-- 就地补充（§6.4）：工作台内直接补录，绝不跳「记一笔」 -->
              <el-button
                size="small"
                text
                type="primary"
                @click="emit('supplement', row as DiscrepancyItem)"
              >
                补充
              </el-button>
              <el-button
                size="small"
                text
                @click="emit('ignore', row as DiscrepancyItem)"
              >
                忽略
              </el-button>
            </template>
            <span v-else class="disc-muted">已处理</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DiscrepancyItem } from "@/api/reconciliation";
import {
  typeLabel,
  statusLabel,
  formatDiff,
  diffClass
} from "../utils/discFormat";

/** 域 B 持仓快照差异表（#980 拆分自 index.vue，零行为变更）：
 *  理论持仓 vs 实际持仓的待处理差异列表，补充 / 忽略操作经 emit 上抛由父级编排。 */
defineProps<{
  items: DiscrepancyItem[];
  loading: boolean;
}>();

const emit = defineEmits<{
  supplement: [row: DiscrepancyItem];
  ignore: [row: DiscrepancyItem];
}>();
</script>

<style scoped>
/* 域 B 差异表（样式随模板一并迁入，保持 scoped 作用域不变，零视觉变更） */
.domain-b-body {
  padding: 4px 0;
}

.disc-table-wrap {
  overflow-x: auto;
}

.disc-table {
  width: 100%;
}

.disc-type {
  padding: 1px 8px;
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: 4px;
}

.disc-diff-zero {
  color: var(--text-tertiary-ink);
}

.disc-diff-pos {
  color: var(--color-success-ink);
}

.disc-diff-neg {
  color: var(--color-danger);
}

.disc-status {
  padding: 1px 8px;
  font-size: 12px;
  border-radius: 999px;
}

.disc-status--pending {
  color: var(--color-warning-ink);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
}

.disc-status--cleared {
  color: var(--color-success-ink);
  background: color-mix(in srgb, var(--color-success) 12%, transparent);
}

.disc-status--ignored {
  color: var(--text-tertiary-ink);
  background: var(--bg-soft);
}

.disc-muted {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}
</style>
