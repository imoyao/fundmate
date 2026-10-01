<template>
  <!-- 预览：只读展示，error 行标红禁提交。三种导入模式共用这一张表，
       标题 / 计数 / 按钮按模式措辞（解析=文件与 AI，录入=手动） -->
  <div class="preview-card">
    <SectionHeader
      :title="p.importMode === 'manual' ? '录入预览' : '解析预览'"
      :info="
        (p.importMode === 'manual' ? '共录入 ' : '共识别 ') +
        p.parseMeta.total +
        ' 条记录' +
        (p.errorCount > 0 ? '，其中 ' + p.errorCount + ' 条解析失败' : '')
      "
    >
      <template #action>
        <!-- 手动录入（#1788）没有「对账」语义：提交走 holdings/confirm 直接落持仓，
             按钮与计数文案随之切换，避免用户以为会进对账中心。 -->
        <el-button
          type="primary"
          :disabled="p.errorCount > 0 || p.previewRows.length === 0"
          :loading="p.reconciling"
          @click="p.handleReconcile"
        >
          <IconifyIconOffline
            :icon="p.importMode === 'manual' ? 'ep:download' : 'ep:connection'"
            class="mr-1"
          />
          {{ p.importMode === "manual" ? "确认导入" : "开始对账" }}
        </el-button>
      </template>
    </SectionHeader>

    <div v-if="p.errorCount > 0" class="parse-warning">
      <IconifyIconOffline icon="ep:warning-filled" class="mr-1" />
      <template v-if="p.importMode === 'manual'">
        存在 {{ p.errorCount }} 条无效记录（红底行），请修正后重试
      </template>
      <template v-else>
        存在 {{ p.errorCount }} 条解析失败记录（红底行），请更换文件后重试，
        有误数据不会参与对账
      </template>
    </div>

    <!-- 表格视觉基线走 src/style/el-table.css（row-blocked 为基线内置类） -->
    <el-table
      :data="p.pagedPreviewRows"
      stripe
      :row-class-name="p.getRowClassName"
      max-height="480"
    >
      <el-table-column label="基金" min-width="180">
        <template #default="{ row }">
          <div class="fund-cell">
            <span class="fund-cell__name">{{ row.name || "--" }}</span>
            <span class="fund-cell__symbol">{{ row.symbol || "--" }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="份额" width="110" align="right">
        <template #default="{ row }">
          <span class="num-cell">{{
            p.toNumber(row.quantity) != null
              ? formatQuantity(p.toNumber(row.quantity))
              : "--"
          }}</span>
        </template>
      </el-table-column>
      <el-table-column label="净值" width="100" align="right">
        <template #default="{ row }">
          <span class="num-cell">{{
            p.toNumber(row.price) != null ? Number(row.price).toFixed(4) : "--"
          }}</span>
        </template>
      </el-table-column>
      <el-table-column label="快照日期" width="110" align="right">
        <template #default="{ row }">
          <span class="num-cell">{{ formatDate(row.snapshot_date) }}</span>
        </template>
      </el-table-column>
      <!-- 销售机构 / 基金管理人是 E账户快照的溯源列（来自文件里的销售渠道与管理人字段）。
           手动录入没有这些来源，留着只会是两列恒为「--」，反而让人以为漏填，故按模式隐藏。 -->
      <el-table-column
        v-if="p.importMode !== 'manual'"
        label="销售机构"
        min-width="170"
      >
        <template #default="{ row }">
          <span class="ellipsis-text" :title="row.source_broker || ''">
            {{ row.source_broker || "--" }}
          </span>
        </template>
      </el-table-column>
      <el-table-column
        v-if="p.importMode !== 'manual'"
        label="基金管理人"
        min-width="170"
      >
        <template #default="{ row }">
          <span class="ellipsis-text" :title="row.fund_manager || ''">
            {{ row.fund_manager || "--" }}
          </span>
        </template>
      </el-table-column>
      <template #empty>
        <div class="preview-empty">暂无预览数据</div>
      </template>
    </el-table>

    <!-- 客户端分页：在全量解析行上切片，统计口径保持全量 -->
    <el-pagination
      v-model:current-page="p.previewPage"
      v-model:page-size="p.previewPageSize"
      :total="p.previewRows.length"
      :page-sizes="[50, 100, 200]"
      layout="total, prev, pager, next, sizes"
      class="table-pagination"
    />

    <div class="preview-footer">
      <span class="preview-footer__count">
        共 {{ p.parseMeta.total }} 条，{{
          p.importMode === "manual" ? "可导入" : "可对账"
        }}
        {{ p.previewRows.length - p.errorCount }} 条
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { formatDate } from "@/utils/date";
import { formatQuantity } from "@/utils/format";
import type { useEaccountImport } from "../composables/useEaccountImport";

defineOptions({ name: "EaccountParsePreview" });

const props = defineProps<{ page: ReturnType<typeof useEaccountImport> }>();

/**
 * 共享状态单体（useEaccountImport）的响应式视图（#980 P1-A 同款）。
 * 外层显隐（previewRows.length > 0）由 index.vue 编排，与拆分前一致。
 */
const p = reactive(props.page);
</script>

<style scoped>
/* ===== 预览区 ===== */
.preview-card {
  padding: var(--space-standard);
  margin-top: var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

/* 有解析失败行时提示（提示性信息用品牌色，危险色只留给破坏性操作） */
.parse-warning {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-3) var(--space-compact);
  margin-bottom: var(--space-compact);
  font-size: var(--text-small);
  color: var(--brand-700);
  background: var(--brand-100);
  border-radius: var(--radius-md);
}

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
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.ellipsis-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.num-cell {
  font-family: var(--font-mono);
  font-size: var(--text-small);
  color: var(--text-primary);
}

.preview-empty {
  padding: 24px 0;
  color: var(--text-tertiary-ink);
  text-align: center;
}

/* 分页条：表格底部右对齐，Element Plus 默认视觉 */
.table-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--space-compact);
}

.preview-footer {
  padding-top: var(--space-compact);
  margin-top: var(--space-compact);
  border-top: 1px solid var(--border-subtle);
}

.preview-footer__count {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
