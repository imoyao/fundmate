<template>
  <div class="domain-b-body">
    <el-empty
      v-if="!loading && items.length === 0"
      :description="emptyText"
      :image-size="80"
    />
    <template v-else>
      <!-- 列名改成用户语言，并当场解释三个数是怎么来的（owner 第二轮：
           「类型列 / 数量 / 理论 / 实际 / 差异，我不知道系统在说什么」） -->
      <p class="disc-caliber">{{ DISC_CALIBER_HINT }}</p>
      <div class="disc-table-wrap">
        <el-table :data="pagedItems" stripe size="small" class="disc-table">
          <el-table-column :label="DISC_COLUMN_LABELS.product" min-width="180">
            <template #default="{ row }">
              <div class="disc-product">
                <span class="disc-product__name">{{
                  reconGroupTitle(row.symbol, row.display_name)
                }}</span>
                <span class="disc-product__code">{{
                  specialSymbolLabel(row.symbol)
                    ? CASH_SYMBOL_HINT
                    : `代码 ${reconSymbolCode(row.symbol)}`
                }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="DISC_COLUMN_LABELS.issue" width="130">
            <template #default="{ row }">
              <span class="disc-type">{{
                discrepancyIssue(row.discrepancy_type)
              }}</span>
            </template>
          </el-table-column>
          <el-table-column
            :label="DISC_COLUMN_LABELS.expected"
            width="120"
            align="right"
          >
            <template #default="{ row }">
              {{ reconQuantity(row.expected_value) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="DISC_COLUMN_LABELS.actual"
            width="120"
            align="right"
          >
            <template #default="{ row }">
              {{ reconQuantity(row.actual_value) }}
            </template>
          </el-table-column>
          <el-table-column
            :label="DISC_COLUMN_LABELS.diff"
            width="120"
            align="right"
          >
            <template #default="{ row }">
              <span :class="diffClass(row.diff)">{{
                reconQuantity(row.diff)
              }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="DISC_COLUMN_LABELS.status" width="90">
            <template #default="{ row }">
              <span class="disc-status" :class="`disc-status--${row.status}`">
                {{ statusLabel(row.status) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column :label="DISC_COLUMN_LABELS.action" width="200">
            <template #default="{ row }">
              <template v-if="row.status === 'pending'">
                <!-- 补录弹窗已带「补的是哪一条」上下文，标题不再叫「就地补充」 -->
                <el-button
                  size="small"
                  text
                  type="primary"
                  @click="emit('supplement', row as DiscrepancyItem)"
                >
                  补录这笔
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

      <!-- 客户端分页：域 B 实测 163 条待处理差异，全量堆在一页既翻不动也看不清 -->
      <el-pagination
        v-if="items.length > pageSize"
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="items.length"
        :page-sizes="[50, 100, 200]"
        layout="total, prev, pager, next, sizes"
        small
        background
        class="disc-pagination"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { DiscrepancyItem } from "@/api/reconciliation";
import { statusLabel, diffClass } from "../utils/discFormat";
import {
  reconGroupTitle,
  reconQuantity,
  reconSymbolCode
} from "../utils/reconDisplay";
import {
  CASH_SYMBOL_HINT,
  DISC_CALIBER_HINT,
  DISC_COLUMN_LABELS,
  discrepancyIssue,
  specialSymbolLabel
} from "../utils/reconLabels";

/** 域 B 持仓快照差异表（#980 拆分自 index.vue；2026-10-28 补客户端分页）。
 *  理论持仓 vs 实际持仓的待处理差异列表，补充 / 忽略操作经 emit 上抛由父级编排。
 *  域 C（对账单导入）复用同一张表：两域差异结构相同（`DiscrepancyItem`），
 *  差别只在空态文案，故不为 C 域再抄一份。 */
const props = withDefaults(
  defineProps<{
    items: DiscrepancyItem[];
    loading: boolean;
    /** 空态文案（域 B「暂无待处理差异」/ 域 C「暂无缺流水的持仓」） */
    emptyText?: string;
  }>(),
  { emptyText: "暂无待处理差异" }
);

const emit = defineEmits<{
  supplement: [row: DiscrepancyItem];
  ignore: [row: DiscrepancyItem];
}>();

/** 客户端分页（与域 A 面板口径一致：默认 50，可选 100 / 200） */
const page = ref(1);
const pageSize = ref(50);
const pagedItems = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return props.items.slice(start, start + pageSize.value);
});

/** 数据重载（运行对账 / 补充 / 忽略）后回到第一页，避免停在已不存在的页 */
watch(
  () => props.items,
  () => {
    page.value = 1;
  }
);
</script>

<style scoped>
/* 域 B 差异表（样式随模板一并迁入，保持 scoped 作用域不变） */
.domain-b-body {
  padding: 4px 0;
}

.disc-caliber {
  margin: 0 0 10px;
  font-size: var(--text-label);
  line-height: 1.7;
  color: var(--text-secondary);
}

.disc-table-wrap {
  overflow-x: auto;
}

.disc-product {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 0;
}

.disc-product__name {
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
}

.disc-product__code {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.disc-table {
  width: 100%;
}

/* 分页条：表格底部右对齐，与域 A 面板同一位置与粗细 */
.disc-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--space-compact);
}

.disc-type {
  padding: 1px 8px;
  font-size: var(--text-label);
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
  font-size: var(--text-label);
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
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
