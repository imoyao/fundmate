<script setup lang="ts">
/**
 * E账户对账明细表（迁移自 reconcile/reconcileView/ReconcileTable.vue，2026-10-28）。
 *
 * 视觉基线走 `src/style/el-table.css`，本组件不覆盖表格外观——只补单元格内部的
 * 排版（产品复合列、数字等宽、差异涨跌色）。
 *
 * 分页**不在这里**：切页与筛选同属「这一屏看哪一段」的口径，放在面板层
 * （`index.vue`）与筛选器并排，避免表格既管数据又管页码。
 *
 * 列口径与老对账中心一致，2026-10-28 修正三处工作台手抄错误：
 * 1. 系统份额绑 `system_quantity`（原绑 `current_quantity` → 整列恒空）；
 * 2. 补回「差异」列（`diff`，E账户合计 − 记账合计）；
 * 3. 产品信息用 `ProductDisplay` 复合列（SPEC 3.8 红线：禁止手写「代码」「名称」两列）。
 */
import { IconifyIconOffline } from "@/components/ReIcon";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import { formatQuantity } from "@/utils/format";
import type { ReconciliationItem } from "@/api/eaccount";

import RowActions from "./RowActions.vue";
import EmptyState from "./EmptyState.vue";
import { STATUS_META, diffClass, isActingOf, type Acting } from "./model";

defineProps<{
  /** 当前页要渲染的行（面板已按筛选 + 分页切好） */
  items: ReconciliationItem[];
  loading: boolean;
  /** 给空状态判断「全量无记录」还是「当前筛选无记录」 */
  statusFilter: string;
  acting: Acting;
}>();

const emit = defineEmits<{
  (e: "cover", row: ReconciliationItem): void;
  (e: "ignore", row: ReconciliationItem): void;
}>();
</script>

<template>
  <!-- 类名 table-card 是 e2e 锚点（frontend/e2e/reconcile.spec.ts），改名须同步 spec -->
  <el-table v-loading="loading" :data="items" stripe class="table-card">
    <!-- 产品信息复合列（SPEC 3.8）：名称 + 「# 代码」，与自选/持仓表同一语言。
         类型段刻意留空——本表全部是基金，重复写「基金」只占宽度不提供信息。 -->
    <el-table-column label="基金" fixed="left" width="220">
      <template #default="{ row }">
        <ProductDisplay
          compact
          :name="row.name || row.symbol"
          :symbol="row.symbol"
        />
      </template>
    </el-table-column>

    <el-table-column label="销售机构" min-width="150">
      <template #default="{ row }">
        <span class="ellipsis-text" :title="row.source_broker || ''">
          {{ row.source_broker || "--" }}
        </span>
      </template>
    </el-table-column>

    <el-table-column label="E账户份额" width="160" align="right">
      <template #header>
        <el-tooltip
          content="基金 E 账户官方快照里，本渠道下的持有份额"
          placement="top"
        >
          <span class="th-hint">
            E账户份额
            <IconifyIconOffline
              icon="ep:question-filled"
              class="th-hint__icon"
            />
          </span>
        </el-tooltip>
      </template>
      <template #default="{ row }">
        <div class="qty-cell">
          <span class="num-cell">{{
            formatQuantity(row.eaccount_quantity)
          }}</span>
          <!-- 多渠道（eaccount_total ≠ 单条份额）时以角标 + tooltip 展示合计 -->
          <el-tooltip
            v-if="
              row.eaccount_total != null &&
              row.eaccount_total !== row.eaccount_quantity
            "
            :content="`该基金经多个销售机构持有，E账户合计 ${formatQuantity(row.eaccount_total)} 份`"
            placement="top"
          >
            <span class="qty-cell__total"
              >合计 {{ formatQuantity(row.eaccount_total) }}</span
            >
          </el-tooltip>
        </div>
      </template>
    </el-table-column>

    <el-table-column label="记账份额" width="110" align="right">
      <template #header>
        <el-tooltip
          content="你自己记账侧按基金代码汇总的份额（多个账户持同一只基金会合并计算）"
          placement="top"
        >
          <span class="th-hint">
            记账份额
            <IconifyIconOffline
              icon="ep:question-filled"
              class="th-hint__icon"
            />
          </span>
        </el-tooltip>
      </template>
      <template #default="{ row }">
        <span class="num-cell">{{
          row.system_quantity != null
            ? formatQuantity(row.system_quantity)
            : "--"
        }}</span>
      </template>
    </el-table-column>

    <el-table-column label="差异" width="120" align="right">
      <template #header>
        <el-tooltip
          content="E账户合计 − 记账合计。正数说明 E 账户比你账上多，负数说明少"
          placement="top"
        >
          <span class="th-hint">
            差异
            <IconifyIconOffline
              icon="ep:question-filled"
              class="th-hint__icon"
            />
          </span>
        </el-tooltip>
      </template>
      <template #default="{ row }">
        <!-- 差异 = E账户合计 - 系统合计（symbol 级汇总，正涨红负跌绿，
             符号与数字同色：design.md「正负符号强制约束」） -->
        <span class="diff-cell" :class="diffClass(row.diff)">
          <span v-if="row.diff > 0">+</span>
          <span v-if="row.diff < 0">-</span>
          {{ formatQuantity(Math.abs(row.diff)) }}
        </span>
      </template>
    </el-table-column>

    <el-table-column label="状态" width="96" align="center">
      <template #default="{ row }">
        <el-tag
          class="status-tag"
          :class="STATUS_META[(row as ReconciliationItem).status].className"
          size="small"
        >
          {{ STATUS_META[(row as ReconciliationItem).status].label }}
        </el-tag>
      </template>
    </el-table-column>

    <el-table-column label="操作" width="200" fixed="right">
      <template #default="{ row }">
        <RowActions
          :row="row as ReconciliationItem"
          :cover-loading="isActingOf(acting, row.record_id, 'cover')"
          :ignore-loading="isActingOf(acting, row.record_id, 'ignore')"
          @cover="emit('cover', $event)"
          @ignore="emit('ignore', $event)"
        />
      </template>
    </el-table-column>

    <template #empty>
      <EmptyState :status-filter="statusFilter" />
    </template>
  </el-table>
</template>

<style scoped>
/* 长文本省略（销售机构等） */
.ellipsis-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 数字单元格：等宽对齐由页面根容器 tabular-nums 兜底，此处补字体 */
.num-cell {
  font-family: var(--font-mono);
  font-size: var(--text-small);
  color: var(--text-primary);
}

/* E账户份额列：单条份额 + 多渠道合计角标（tooltip 承载完整说明） */
.qty-cell {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  justify-content: flex-end;
}

.qty-cell__total {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--brand-700);
  cursor: help;
  background: var(--brand-100);
  border-radius: var(--radius-pill);
}

/* 差异列：涨红跌绿 + 符号同色（design.md「正负符号强制约束」） */
.diff-cell {
  font-family: var(--font-mono);
  font-size: var(--text-small);
  font-weight: 500;
}

.diff-cell.is-rise {
  color: var(--color-rise-ink);
}

.diff-cell.is-fall {
  color: var(--color-fall-ink);
}

.diff-cell.is-zero {
  color: var(--text-tertiary-ink);
}

/* 表头问号：列名本身是行话（记账份额 / 差异方向），补一个可悬停的解释入口。
   图标用三级文字色，不抢列名权重。 */
.th-hint {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  cursor: help;
}

.th-hint__icon {
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

/* ===== 状态标签：四态语义（pending 行动品牌色 / attributed 中性软底 /
     ignored 虚线弱化 / verified 实心确认），区分靠「底色+边框+文字」组合，
     不引入系统外色值（design.md「禁止硬编码 hex」） ===== */
.status-tag {
  border: none;
}

.status-tag--pending {
  color: var(--brand-700);
  background-color: var(--brand-100);
}

.status-tag--attributed {
  color: var(--text-secondary);
  background-color: var(--bg-soft);
}

.status-tag--ignored {
  color: var(--text-tertiary-ink);
  background-color: transparent;
  border: 1px dashed var(--border-default);
}

.status-tag--verified {
  color: var(--text-secondary);
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
}
</style>
