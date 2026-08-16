<template>
  <div class="reconcile-page">
    <!-- 页头：标题 + 数据日期胶囊 + 刷新（对齐 ledgers 页头模式） -->
    <header class="reconcile-head">
      <div class="reconcile-head__text">
        <h1 class="reconcile-head__title">E账户对账</h1>
        <p class="reconcile-head__subtitle">
          核对 E账户快照与各销售渠道的持仓差异，将快照归因到对应账户
        </p>
      </div>
      <div class="reconcile-head__actions">
        <el-tooltip
          content="E账户数据为最近一次导入的快照，如需更新请重新导入"
          placement="top"
        >
          <span class="data-date-capsule">
            <IconifyIconOffline
              icon="ep:calendar"
              class="data-date-capsule__icon"
            />
            <span>数据日期 {{ dataDate ? formatDate(dataDate) : "--" }}</span>
          </span>
        </el-tooltip>
        <el-button :loading="refreshing" @click="handleRefresh">
          <IconifyIconOffline icon="ep:refresh" class="mr-1" />
          刷新
        </el-button>
      </div>
    </header>

    <!-- 四态计数指标卡（MetricGrid 均分，待处理 featured 放大锚点） -->
    <MetricGrid class="summary-grid">
      <MetricCard
        title="待处理"
        :value="summary?.pending_count ?? null"
        featured
        caption="需要归因覆盖或忽略，优先处理"
      />
      <MetricCard
        title="已归因"
        :value="summary?.attributed_count ?? null"
        caption="快照已覆盖至对应渠道"
      />
      <MetricCard
        title="已忽略"
        :value="summary?.ignored_count ?? null"
        caption="导入时自动跳过，可重新对账恢复"
      />
      <MetricCard
        title="已核对"
        :value="summary?.verified_count ?? null"
        caption="与系统份额一致，无需处理"
      />
    </MetricGrid>

    <!-- 状态筛选：一级胶囊分段（design.md「Filter & Selection」，
         胶囊语言与 watchlist view-segmented 一致，选中态软按钮） -->
    <div class="filter-bar">
      <el-segmented
        v-model="statusFilter"
        :options="STATUS_OPTIONS"
        class="status-segmented"
      />
      <span class="filter-bar__count">共 {{ filteredItems.length }} 条</span>
    </div>

    <!-- 对账明细表：视觉基线走 src/style/el-table.css，页面不覆盖 -->
    <div v-loading="loading" class="table-card">
      <el-table :data="filteredItems" stripe>
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
            <div class="row-actions">
              <!-- 待处理：核心操作常显（本页操作即页面主题，不做 hover 隐藏） -->
              <template v-if="row.status === 'pending'">
                <el-button
                  link
                  size="small"
                  class="btn-cover-danger"
                  :loading="
                    actingRecordId === row.record_id && actingAction === 'cover'
                  "
                  @click="handleCover(row as ReconciliationItem)"
                >
                  归因覆盖
                </el-button>
                <el-button
                  link
                  size="small"
                  :loading="
                    actingRecordId === row.record_id &&
                    actingAction === 'ignore'
                  "
                  @click="handleIgnore(row as ReconciliationItem)"
                >
                  忽略
                </el-button>
              </template>
              <!-- 已归因：展示去向，操作禁用 -->
              <span
                v-else-if="row.status === 'attributed'"
                class="row-actions__readonly"
              >
                已归因至 {{ row.attributed_to || "对应渠道" }}
              </span>
              <span
                v-else-if="row.status === 'verified'"
                class="row-actions__readonly"
              >
                已核对一致
              </span>
              <span v-else class="row-actions__readonly">已忽略</span>
            </div>
          </template>
        </el-table-column>
        <!-- 空状态：鹦鹉螺插画资产未入库前先用文案版 + 品牌收尾文案
             （与 watchlist 空状态同一策略，插画到位后替换） -->
        <template #empty>
          <div class="reconcile-empty">
            <IconifyIconOffline icon="ep:files" class="reconcile-empty__icon" />
            <p class="reconcile-empty__title">
              {{
                statusFilter === "all" ? "暂无对账记录" : "当前筛选下没有记录"
              }}
            </p>
            <p class="reconcile-empty__copy">
              潮有涨落，壳有深浅。算得清，才无患。
            </p>
            <p v-if="statusFilter !== 'all'" class="reconcile-empty__hint">
              试试切换其他状态，或点击右上角「刷新」
            </p>
          </div>
        </template>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  getEaccountReconciliation,
  attributeEaccount,
  type ReconciliationItem,
  type ReconciliationData,
  type AttributionResult
} from "@/api/eaccount";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import { formatDate } from "@/utils/date";

defineOptions({ name: "InvestmentReconcile" });

/** 兼容「信封 {data}」与「直接返回」两种响应形态（并行 lane 契约以直接返回为准） */
function unwrap<T>(res: unknown): T {
  const r = res as { data?: T } | null;
  if (r && typeof r === "object" && "data" in r && r.data != null)
    return r.data;
  return res as T;
}

/** 统一错误文案提取：后端信封 message 优先，其次 Error.message */
function errMsg(e: unknown, fallback: string): string {
  const err = e as {
    response?: { data?: { message?: string } };
    message?: string;
  };
  return err?.response?.data?.message || err?.message || fallback;
}

const loading = ref(true);
const refreshing = ref(false);
const dataDate = ref("");
const items = ref<ReconciliationItem[]>([]);
const summary = ref<ReconciliationData["summary"] | null>(null);
const statusFilter = ref("all");
/** 当前正在执行归因/忽略的记录（行内按钮 loading 定位） */
const actingRecordId = ref<number | null>(null);
const actingAction = ref<"cover" | "ignore" | null>(null);

const STATUS_OPTIONS = [
  { label: "全部", value: "all" },
  { label: "待处理", value: "pending" },
  { label: "已归因", value: "attributed" },
  { label: "已忽略", value: "ignored" },
  { label: "已核对", value: "verified" }
];

/** 状态标签元信息：标签文字 + 自定义色类（四态语义区分） */
const STATUS_META: Record<
  ReconciliationItem["status"],
  { label: string; className: string }
> = {
  pending: { label: "待处理", className: "status-tag--pending" },
  attributed: { label: "已归因", className: "status-tag--attributed" },
  ignored: { label: "已忽略", className: "status-tag--ignored" },
  verified: { label: "已核对", className: "status-tag--verified" }
};

/** 一级状态筛选（客户端过滤：数据量小，切换即时，四态计数保持全量口径） */
const filteredItems = computed(() => {
  if (statusFilter.value === "all") return items.value;
  return items.value.filter(item => item.status === statusFilter.value);
});

/** 份额格式化：保留 2 位 + 千分位（design.md「份额/数量保留 2 位」） */
function formatQuantity(qty: number): string {
  return (qty || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

/** 差异涨跌语义：正=E账户多于系统（涨红）、负=少于系统（跌绿）、零=中性 */
function diffClass(diff: number): string {
  if (diff > 0) return "is-rise";
  if (diff < 0) return "is-fall";
  return "is-zero";
}

async function fetchData() {
  loading.value = true;
  try {
    const res = await getEaccountReconciliation();
    const data = unwrap<ReconciliationData>(res);
    dataDate.value = data.data_date ?? "";
    items.value = Array.isArray(data.items) ? data.items : [];
    summary.value = data.summary ?? null;
  } catch (e) {
    ElMessage.error(errMsg(e, "加载对账数据失败"));
  } finally {
    loading.value = false;
  }
}

async function handleRefresh() {
  refreshing.value = true;
  await fetchData();
  refreshing.value = false;
}

/** 归因覆盖：危险操作（删除渠道原记录），确认按钮走 --color-danger-system */
async function handleCover(row: ReconciliationItem) {
  try {
    await ElMessageBox.confirm(
      `将以 E账户快照覆盖「${row.name || row.symbol}」在对应销售渠道的旧持仓，删除渠道原记录。此操作不可撤销。`,
      "归因覆盖",
      {
        type: "warning",
        confirmButtonText: "确认覆盖",
        cancelButtonText: "取消",
        confirmButtonClass: "reconcile-confirm-danger"
      }
    );
  } catch {
    return; // 用户取消
  }
  actingRecordId.value = row.record_id;
  actingAction.value = "cover";
  try {
    const res = await attributeEaccount([
      {
        symbol: row.symbol,
        source_broker: row.source_broker || "",
        fund_manager: row.fund_manager || "",
        action: "cover"
      }
    ]);
    const result = unwrap<AttributionResult>(res);
    if (result.failed > 0) {
      ElMessage.warning(`归因覆盖完成，但有 ${result.failed} 条未成功`);
    } else {
      ElMessage.success("归因覆盖完成");
    }
    await fetchData();
  } catch (e) {
    ElMessage.error(errMsg(e, "归因覆盖失败"));
  } finally {
    actingRecordId.value = null;
    actingAction.value = null;
  }
}

/** 忽略：导入自动跳过，可稍后重新对账恢复（非破坏性，默认确认按钮） */
async function handleIgnore(row: ReconciliationItem) {
  try {
    await ElMessageBox.confirm(
      `忽略后「${row.name || row.symbol}」在后续 E账户导入中自动跳过，可稍后重新对账恢复。`,
      "忽略该记录",
      {
        type: "info",
        confirmButtonText: "确认忽略",
        cancelButtonText: "取消"
      }
    );
  } catch {
    return; // 用户取消
  }
  actingRecordId.value = row.record_id;
  actingAction.value = "ignore";
  try {
    const res = await attributeEaccount([
      {
        symbol: row.symbol,
        source_broker: row.source_broker || "",
        fund_manager: row.fund_manager || "",
        action: "ignore"
      }
    ]);
    const result = unwrap<AttributionResult>(res);
    if (result.failed > 0) {
      ElMessage.warning(`忽略完成，但有 ${result.failed} 条未成功`);
    } else {
      ElMessage.success("已忽略该记录");
    }
    await fetchData();
  } catch (e) {
    ElMessage.error(errMsg(e, "忽略失败"));
  } finally {
    actingRecordId.value = null;
    actingAction.value = null;
  }
}

onMounted(fetchData);
</script>

<style scoped>
/* 触屏设备无 hover 态：行内操作常显，避免入口不可达 */
@media (hover: none) {
  .row-actions {
    opacity: 1;
  }
}

.reconcile-page {
  font-family: var(--font-ui);
  font-variant-numeric: tabular-nums;
}

/* ===== 页头 ===== */
.reconcile-head {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-standard);
}

.reconcile-head__title {
  margin: 0;
  font-size: var(--text-display);
  font-weight: 300;
  line-height: 1.3;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

.reconcile-head__subtitle {
  margin: 6px 0 0;
  font-size: var(--text-small);
  line-height: 1.5;
  color: var(--text-secondary);
}

.reconcile-head__actions {
  display: inline-flex;
  flex-shrink: 0;
  gap: var(--space-2);
  align-items: center;
}

/* 数据日期胶囊：--bg-soft 底 + 胶囊圆角（PageHeaderBar 更新时间胶囊同语言） */
.data-date-capsule {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
  background: var(--bg-soft);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-pill);
}

.data-date-capsule__icon {
  font-size: 13px;
}

/* ===== 指标卡区 ===== */
.summary-grid {
  margin-bottom: var(--space-standard);
}

/* ===== 筛选栏 ===== */
.filter-bar {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-compact);
}

.filter-bar__count {
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

/* 一级筛选分段控制器：胶囊语言与 watchlist view-segmented 一致
   （design.md「Filter & Selection」一级胶囊分段，选中态软按钮） */
.status-segmented :deep(.el-segmented) {
  height: 32px;
  padding: 2px;
  background-color: var(--bg-muted);
  border-radius: var(--radius-pill);
  box-shadow: none;
}

.status-segmented :deep(.el-segmented__item) {
  height: 28px;
  padding: 0 14px;
  font-size: var(--text-label);
  line-height: 28px;
  color: var(--text-secondary);
  border-radius: var(--radius-pill);
  transition:
    background-color 150ms ease,
    color 150ms ease;
}

.status-segmented :deep(.el-segmented__item:hover) {
  color: var(--text-primary);
}

.status-segmented :deep(.el-segmented__item.is-selected) {
  color: var(--brand-700);
  background-color: var(--brand-100);
  box-shadow: none;
}

.status-segmented :deep(.el-segmented__item.is-selected:hover) {
  background-color: var(--brand-200);
}

.status-segmented :deep(.el-segmented__item-selected) {
  background-color: var(--brand-100);
  border-radius: var(--radius-pill);
  box-shadow: none;
}

.status-segmented
  :deep(.el-segmented__item.is-selected:hover .el-segmented__item-selected) {
  background-color: var(--brand-200);
}

/* ===== 表格卡片 ===== */
.table-card {
  padding: var(--space-compact);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
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
  font-size: 12px;
  color: var(--text-tertiary);
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
  font-size: 12px;
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
  color: var(--color-rise);
}

.diff-cell.is-fall {
  color: var(--color-fall);
}

.diff-cell.is-zero {
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
  color: var(--text-tertiary);
  background-color: transparent;
  border: 1px dashed var(--border-default);
}

.status-tag--verified {
  color: var(--text-secondary);
  background-color: var(--bg-card);
  border: 1px solid var(--border-default);
}

/* ===== 操作列 ===== */
.row-actions {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: center;
}

.row-actions__readonly {
  font-size: var(--text-label);
  color: var(--text-tertiary);
  white-space: nowrap;
}

/* 归因覆盖按钮：危险语义（覆盖 = 删除渠道原记录），危险色走
   --color-danger-system（design.md「危险按钮」幽灵态） */
.btn-cover-danger {
  --el-button-text-color: var(--color-danger-system);
  --el-button-hover-text-color: var(--color-danger-system);
  --el-button-hover-bg-color: var(--color-danger-20);
}

/* ===== 空状态（鹦鹉螺插画资产到位前文案版） ===== */
.reconcile-empty {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  padding: 40px 0;
}

.reconcile-empty__icon {
  margin-bottom: 6px;
  font-size: 40px;
  color: var(--text-tertiary);
  opacity: 0.4;
}

.reconcile-empty__title {
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-secondary);
}

.reconcile-empty__copy {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

.reconcile-empty__hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 页面根容器：字体继承全局 token + 全页数字等宽（design.md「数字等宽对齐落地规范」） */
</style>

<!-- 归因覆盖确认框按钮：ElMessageBox 渲染在 body 下，scoped 样式不可达，
     需全局样式将确认按钮染为危险色（--color-danger-system） -->
<style>
.el-message-box .reconcile-confirm-danger.el-button--primary {
  --el-button-bg-color: var(--color-danger-system);
  --el-button-border-color: var(--color-danger-system);
  --el-button-hover-bg-color: var(--color-danger-system);
  --el-button-hover-border-color: var(--color-danger-system);
  --el-button-active-bg-color: var(--color-danger-system);
  --el-button-active-border-color: var(--color-danger-system);
}
</style>
