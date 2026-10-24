<script setup lang="ts">
/**
 * 对账明细表 + 客户端分页（#980 拆分）。
 *
 * 视觉基线走 `src/style/el-table.css`，本组件不覆盖表格外观——只补单元格内部的
 * 排版（基金名 + 代码两行、数字等宽、差异涨跌色）。
 *
 * 分页是**客户端**的：在页面已经筛好的结果上切片，不回后端。页码与每页条数用
 * `defineModel` 双向绑回页面，页面还要在「切筛选 / 重载数据」时把页码拍回 1。
 */
import { IconifyIconOffline } from "@/components/ReIcon";
import { formatQuantity } from "@/utils/format";
import type { ReconciliationItem } from "@/api/eaccount";

import ReconcileEmpty from "./ReconcileEmpty.vue";
import ReconcileRowActions from "./ReconcileRowActions.vue";
import {
  STATUS_META,
  diffClass,
  isActingOf,
  type Acting
} from "./reconcileModel";

defineProps<{
  /** 当前页要渲染的行（页面已按筛选 + 分页切好） */
  items: ReconciliationItem[];
  loading: boolean;
  /** 筛选后的总条数（分页器的 total，与顶部「共 N 条」同一口径） */
  total: number;
  /** 给空状态判断「全量无记录」还是「当前筛选无记录」 */
  statusFilter: string;
  acting: Acting;
}>();

const page = defineModel<number>("page", { required: true });
const pageSize = defineModel<number>("pageSize", { required: true });

const emit = defineEmits<{
  (e: "cover", row: ReconciliationItem): void;
  (e: "ignore", row: ReconciliationItem): void;
}>();
</script>

<template>
  <div v-loading="loading" class="table-card">
    <el-table :data="items" stripe>
      <el-table-column label="基金" fixed="left" width="200">
        <template #default="{ row }">
          <div class="fund-cell">
            <span class="fund-cell__name">{{ row.name || "--" }}</span>
            <span class="fund-cell__symbol">{{ row.symbol }}</span>
          </div>
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
      <el-table-column label="系统份额" width="110" align="right">
        <template #default="{ row }">
          <span class="num-cell">{{
            row.system_quantity != null
              ? formatQuantity(row.system_quantity)
              : "--"
          }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差异" width="120" align="right">
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
            :class="STATUS_META[row.status].className"
            size="small"
          >
            {{ STATUS_META[row.status].label }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <ReconcileRowActions
            :row="row as ReconciliationItem"
            :cover-loading="isActingOf(acting, row.record_id, 'cover')"
            :ignore-loading="isActingOf(acting, row.record_id, 'ignore')"
            @cover="emit('cover', row as ReconciliationItem)"
            @ignore="emit('ignore', row as ReconciliationItem)"
          />
        </template>
      </el-table-column>
      <template #empty>
        <ReconcileEmpty :status-filter="statusFilter" />
      </template>
    </el-table>

    <!-- 客户端分页：在筛选结果上切片，只翻页不改过滤口径 -->
    <el-pagination
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[50, 100, 200]"
      layout="total, prev, pager, next, sizes"
      class="table-pagination"
    />
  </div>
</template>

<style scoped>
/* ===== 表格卡片 ===== */
.table-card {
  padding: var(--space-compact);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

/* 分页条：卡片内表格底部右对齐，Element Plus 默认视觉 */
.table-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--space-compact);
}

/* 基金列：名称 + 代码上下两行（冻结列锚点，design.md 冻结列规范） */
.fund-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.fund-cell__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-small);
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

.fund-cell__symbol {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

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
