<template>
  <div class="domain-a-body">
    <el-empty
      v-if="!loading && items.length === 0"
      description="暂无 E账户对账记录"
      :image-size="80"
    />
    <div v-else class="disc-table-wrap">
      <el-table :data="items" stripe size="small" class="disc-table">
        <el-table-column label="代码" prop="symbol" width="110" />
        <el-table-column label="名称" prop="name" min-width="120" />
        <el-table-column label="渠道" width="120">
          <template #default="{ row }">
            {{ row.source_broker || "—" }}
          </template>
        </el-table-column>
        <el-table-column label="E账户份额" width="110" align="right">
          <template #default="{ row }">
            {{ row.eaccount_quantity ?? "—" }}
          </template>
        </el-table-column>
        <el-table-column label="系统份额" width="110" align="right">
          <template #default="{ row }">
            {{ row.current_quantity ?? "—" }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span class="disc-status">{{ eStatusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button
                size="small"
                text
                type="primary"
                @click="emit('cover', row as ReconciliationItem)"
              >
                归因覆盖
              </el-button>
              <el-button
                size="small"
                text
                @click="emit('ignore', row as ReconciliationItem)"
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
import type { ReconciliationItem } from "@/api/eaccount";
import { eStatusLabel } from "../utils/discFormat";

/** 域 A E账户对账表（#980 拆分自 index.vue，零行为变更）：
 *  E账户官方快照 vs 渠道持仓，归因覆盖 / 忽略操作经 emit 上抛由父级编排。 */
defineProps<{
  items: ReconciliationItem[];
  loading: boolean;
}>();

const emit = defineEmits<{
  cover: [row: ReconciliationItem];
  ignore: [row: ReconciliationItem];
}>();
</script>

<style scoped>
/* 域 A 对账表（样式随模板一并迁入；.disc-* 与域 B 同名但 scoped 作用域相互独立，
 * 按抽象克制原则保留局部副本，不为此上提公共样式） */
.disc-table-wrap {
  overflow-x: auto;
}

.disc-table {
  width: 100%;
}

.disc-status {
  padding: 1px 8px;
  font-size: 12px;
  border-radius: 999px;
}

.disc-muted {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}
</style>
