<template>
  <div
    class="ledger-list p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 页面标题 & 操作栏 -->
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2
          class="text-2xl font-bold"
          :style="{ color: 'var(--text-primary)' }"
        >
          账户管理
        </h2>
        <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary)' }">
          管理您的银行账户、证券账户、基金平台和实物资产
        </p>
      </div>
      <div class="flex gap-2">
        <el-button
          class="btn-ghost-text"
          @click="$router.push('/asset/portfolios')"
        >
          <IconifyIconOffline icon="ep:collection" class="mr-1" /> 投资组合
        </el-button>
        <el-button
          class="btn-ghost-text"
          @click="$router.push('/asset/strategies')"
        >
          <IconifyIconOffline icon="ep:data-analysis" class="mr-1" /> 策略分析
        </el-button>
        <el-button type="primary" @click="openCreateDialog">
          <IconifyIconOffline icon="ep:plus" class="mr-1" /> 新增账户
        </el-button>
        <el-button
          class="btn-ghost-text"
          :type="showArchived ? 'primary' : 'default'"
          :plain="!showArchived"
          @click="
            showArchived = !showArchived;
            fetchData();
          "
        >
          <IconifyIconOffline icon="ep:box" class="mr-1" />
          {{ showArchived ? "隐藏已归档" : "显示已归档" }}
          <span v-if="archivedCount > 0" class="ml-1 opacity-70"
            >({{ archivedCount }})</span
          >
        </el-button>
      </div>
    </div>

    <!-- 加载 / 空状态 -->
    <div
      v-if="loading"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary)' }"
    >
      <p class="mt-2">加载中...</p>
    </div>

    <div
      v-else-if="allLedgers.length === 0"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary)' }"
    >
      <IconifyIconOffline icon="ep:wallet" class="text-5xl mb-3 opacity-30" />
      <p class="text-lg">暂无账户，点击上方按钮新增</p>
    </div>

    <template v-else>
      <!-- 顶部双卡：净资产卡 + 资产配置环形图（md 两列并排，等高） -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <!-- 净资产卡：左侧大数字锚点，右侧指标区竖排（总资产/负债/负债率） -->
        <div class="overview-card net-worth-card">
          <div class="flex justify-between gap-6 flex-1 items-center">
            <div class="min-w-0">
              <p class="text-sm" :style="{ color: 'var(--text-tertiary)' }">
                净资产
              </p>
              <p class="mt-1">
                <MoneyDisplay :value="overviewData.net_worth" size="xl" />
              </p>
              <!-- 负债率偏高：警示态才用系统危险色（非涨跌色），放在大数字下方 -->
              <div
                v-if="showHighLiabilityWarning"
                class="liability-warning-badge mt-3"
              >
                负债率偏高
              </div>
            </div>
            <!-- 右侧指标区：三指标竖排，label 上数值下，--border-subtle 细分隔 -->
            <div class="overview-metrics">
              <div class="metric-item">
                <span class="metric-label">总资产</span>
                <MoneyDisplay
                  :value="totalAssets"
                  :show-sign="false"
                  :auto-color="false"
                  size="sm"
                />
              </div>
              <!-- 负债为 0 时不渲染负债信息位，保持摘要干净；
                   负债金额属中性财务信息，用 text-secondary，不用涨跌色误导 -->
              <div v-if="overviewData.liability_total > 0" class="metric-item">
                <span class="metric-label">负债</span>
                <MoneyDisplay
                  :value="overviewData.liability_total"
                  :show-sign="false"
                  :auto-color="false"
                  size="sm"
                />
              </div>
              <div class="metric-item">
                <span class="metric-label">负债率</span>
                <!-- 可计算时显示百分比，无负债或不可计算显示 --；浅灰胶囊弱化中性信息 -->
                <span class="liability-rate-pill">{{ liabilityRate }}</span>
              </div>
            </div>
          </div>
          <!-- 更新时间：右上角 -->
          <div class="hidden md:block text-right mt-4">
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              更新于 {{ lastUpdate }}
            </p>
          </div>
        </div>
        <!-- 资产配置环形图卡（#984 拆分至 components/LedgerAllocationCard.vue） -->
        <LedgerAllocationCard
          :groups="overviewData?.groups ?? []"
          :total-assets="totalAssets"
        />
      </div>

      <!-- 未归置持仓清理套件（#984 拆分至 components/OrphanCleanupDialogs.vue）：
           banner + 归入对话框 + 明细对话框 -->
      <OrphanCleanupDialogs
        :orphan-group="orphanGroup"
        :all-ledgers="allLedgers"
        @refresh="fetchData"
      />

      <!-- 按类型分组的账户卡片列表 -->
      <div v-for="group in groupedLedgers" :key="group.type" class="mb-8">
        <div class="flex items-center justify-between mb-3">
          <h3
            class="font-semibold text-base"
            :style="{ color: 'var(--text-primary)' }"
          >
            {{ group.label }}
            <span
              class="text-sm font-normal ml-2"
              :style="{ color: 'var(--text-tertiary)' }"
            >
              (
              {{ group.count }} 个账户 ·
              <MoneyDisplay
                :value="group.total"
                :show-sign="false"
                :auto-color="false"
                size="xs"
              />)
            </span>
          </h3>
        </div>

        <!-- 账户卡片：auto-fit 网格自动折叠空轨道，孤点分类不会产生右侧大片空白。
             卡片展示细节已拆分至 components/LedgerCard.vue（#984） -->
        <div class="ledger-grid">
          <LedgerCard
            v-for="ledger in group.ledgers"
            :key="ledger.id"
            :ledger="ledger"
            @open="goToDetail"
            @delete="openDeleteDialog"
            @toggle-archive="onToggleArchive"
          />
        </div>

        <!-- 幽灵态新增占位符：胶囊小按钮，高度恒定 44px，不撑满网格行 -->
        <button
          type="button"
          class="ghost-add"
          :aria-label="`新增${getLedgerTypeLabel(group.type)}`"
          @click="openCreateDialog"
        >
          <IconifyIconOffline icon="ep:plus" class="ghost-add__icon" />
          <span>新增{{ getLedgerTypeLabel(group.type) }}</span>
        </button>
      </div>
    </template>

    <!-- 新增账户对话框（#984 拆分至 components/CreateAccountDialog.vue） -->
    <CreateAccountDialog
      v-model:visible="showCreateDialog"
      :cash-ledgers="cashLedgers"
      :portfolio-list="portfolioList"
      :sales-institutions="salesInstitutions"
      @created="fetchData"
    />

    <!-- 删除确认对话框 -->
    <DeleteLedgerDialog
      v-model:visible="deleteDialogVisible"
      :ledger-id="deletingAccount?.id ?? 0"
      :ledger-name="deletingAccount?.name ?? ''"
      :position-count="deletingAccount?.position_count ?? 0"
      @deleted="fetchData"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { usePageRefresh } from "@/composables/usePageRefresh";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  getLedgers,
  getLedgersOverview,
  getSalesInstitutions,
  archiveLedger,
  unarchiveLedger,
  type SalesInstitution
} from "@/api/ledger";
import { getPortfolios } from "@/api/portfolio";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { getLedgerTypeLabel } from "@/constants";
import { formatDateTime } from "@/utils/date";
import DeleteLedgerDialog from "./components/DeleteLedgerDialog.vue";
import CreateAccountDialog from "./components/CreateAccountDialog.vue";
import OrphanCleanupDialogs from "./components/OrphanCleanupDialogs.vue";
import LedgerAllocationCard from "./components/LedgerAllocationCard.vue";
import LedgerCard from "./components/LedgerCard.vue";

defineOptions({ name: "AssetLedgers" });

const router = useRouter();

const loading = ref(true);
const allLedgers = ref<any[]>([]);
const overviewData = ref<{
  net_worth: number;
  liability_total: number;
  groups: any[];
}>({
  net_worth: 0,
  liability_total: 0,
  groups: []
});
const lastUpdate = ref("");

const showCreateDialog = ref(false);
/** 基金销售机构候选（AMAC 名录，创建账户可选关联） */
const salesInstitutions = ref<SalesInstitution[]>([]);

const cashLedgers = computed(() =>
  allLedgers.value.filter((l: any) => l.ledger_type === "bank")
);
/** 已归档账户数量（用于工具栏徽标），数据来自全量列表 */
const archivedCount = computed(
  () => allLedgersRaw.value.filter((l: any) => l.is_active === false).length
);
const portfolioList = ref<any[]>([]);
const deleteDialogVisible = ref(false);
const deletingAccount = ref<any>(null);
/** 是否在列表显示已归档账户（默认隐藏，归档数据仍计入顶部净资产/配置图） */
const showArchived = ref(false);
/** 全量账户（含已归档），用于按开关过滤展示 + 统计归档数 */
const allLedgersRaw = ref<any[]>([]);

// 总资产（从 overview groups 汇总）
const totalAssets = computed(
  () =>
    overviewData.value?.groups?.reduce(
      (sum: number, g: any) => sum + (g.total || 0),
      0
    ) ?? 0
);

// 负债率偏高警示：仅当负债 > 0 且超过总资产一半时显示（负债为 0 时不渲染刺眼文案）
const showHighLiabilityWarning = computed(
  () =>
    overviewData.value.liability_total > 0 &&
    overviewData.value.liability_total > totalAssets.value * 0.5
);

// 负债率：可计算时显示百分比（负债/总资产），无负债或不可计算时显示 --
const liabilityRate = computed(() => {
  if (overviewData.value.liability_total <= 0 || totalAssets.value <= 0) {
    return "--";
  }
  return `${((overviewData.value.liability_total / totalAssets.value) * 100).toFixed(1)}%`;
});

// ── 资产配置环形图逻辑已拆分至 components/LedgerAllocationCard.vue（#984）──

// 已删除账户的持仓信息（来自 overview）
const orphanGroup = computed(() =>
  overviewData.value?.groups?.find((g: any) => g.type === "deleted")
);

// 分组展示（按类型分组，并排序，追加未归置持仓）
const groupedLedgers = computed(() => {
  const groups: Record<string, any> = {};
  for (const ledger of allLedgers.value) {
    const type = ledger.ledger_type || "bank";
    if (!groups[type]) {
      groups[type] = {
        type,
        label: getLedgerTypeLabel(type),
        total: 0,
        count: 0,
        ledgers: []
      };
    }
    groups[type].count++;
    groups[type].total += ledger.total_market_value || 0;
    groups[type].ledgers.push(ledger);
  }

  const order = ["bank", "stock", "fund", "property"];
  const result = order.map(type => groups[type]).filter(Boolean);

  // 未归置持仓不再作为分组卡片进入网格（2026-08 改版），统一由顶部警示 banner 承接
  return result;
});

function openCreateDialog() {
  showCreateDialog.value = true;
}

function openDeleteDialog(account: any) {
  deletingAccount.value = account;
  deleteDialogVisible.value = true;
}

/** 归档/激活切换。归档有数据账户是安全的（保留全部数据、仅隐藏），但给一次确认。 */
async function onToggleArchive(ledger: any) {
  const archiving = ledger.is_active !== false;
  try {
    if (archiving) {
      await ElMessageBox.confirm(
        `归档后「${ledger.name}」将从日常列表隐藏，但全部交易/持仓数据仍保留并计入收益。确定归档？`,
        "归档账户",
        { confirmButtonText: "归档", cancelButtonText: "取消", type: "warning" }
      );
    }
    if (archiving) {
      await archiveLedger(ledger.id);
      ElMessage.success(`已归档「${ledger.name}」`);
    } else {
      await unarchiveLedger(ledger.id);
      ElMessage.success(`已激活「${ledger.name}」`);
    }
    fetchData();
  } catch (e: any) {
    if (e !== "cancel" && e?.action !== "cancel") {
      ElMessage.error(e?.message || "操作失败");
    }
  }
}

function goToDetail(ledger: any) {
  router.push({ name: "LedgerDetail", params: { id: ledger.id } });
}

async function fetchData() {
  loading.value = true;
  try {
    const [ledgersRes, overviewRes, portfolioRes, instRes] = await Promise.all([
      getLedgers(true),
      getLedgersOverview(),
      getPortfolios(),
      getSalesInstitutions()
    ]);
    allLedgersRaw.value = (ledgersRes as any)?.data ?? [];
    // 按「显示已归档」开关过滤展示列表（归档数据始终计入顶部净资产/配置图）
    allLedgers.value = showArchived.value
      ? allLedgersRaw.value
      : allLedgersRaw.value.filter((l: any) => l.is_active !== false);
    overviewData.value = (overviewRes as any)?.data ?? {
      net_worth: 0,
      liability_total: 0,
      groups: []
    };
    portfolioList.value = (portfolioRes as any)?.data ?? [];
    salesInstitutions.value =
      (instRes as { data?: SalesInstitution[] })?.data ?? [];
    // 统一走公共格式化：YYYY-MM-DD HH:mm（不带秒），避免斜线/时分秒混用
    lastUpdate.value = formatDateTime(new Date());
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

// 只需一行，列表全自动刷新
usePageRefresh(() => {
  fetchData();
});

onMounted(() => {
  fetchData();
});
</script>

<style scoped>
/* 触屏设备无 hover 态的删除按钮样式已随 LedgerCard 迁移 */

/* 尊重系统减弱动效偏好（.ledger-row-action/.orphan-banner 等子组件内部
   元素的对应规则已随组件迁移，见各组件 scoped 块） */
@media (prefers-reduced-motion: reduce) {
  .ghost-add,
  .overview-card,
  .ledger-card {
    transition: none;
  }

  .ledger-card:hover {
    transform: none;
  }
}

.ledger-list {
  /* 字体继承全局 token（--font-ui → Inter 优先），不再硬编码 PingFang 栈，
     避免与站内其它页面字体不一致（design-tokens.css --font-ui） */
  font-family: var(--font-ui);

  /* 全页数字等宽对齐：消除金额/统计数字宽度抖动（design.md「数字等宽对齐」） */
  font-variant-numeric: tabular-nums;
}

/* ===== 全局汇总卡片（--space-standard 间距，净资产大数字锚点） ===== */
.overview-card {
  padding: var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

/* 净资产卡：纵向布局，更新时间贴底，与右侧图表卡等高对齐 */
.net-worth-card {
  display: flex;
  flex-direction: column;
}

/* 负债率偏高警示：负债属中性信息，警示态才用系统危险色（非涨跌色） */
.liability-warning-badge {
  display: inline-block;
  padding: 2px 8px;
  font-size: 12px;
  line-height: 18px;
  color: var(--color-danger);
  background: var(--color-danger-20);
  border-radius: var(--radius-pill);
}

/* ===== 净资产卡右侧指标区：三指标竖排，label 上数值下，--border-subtle 细分隔 ===== */
.overview-metrics {
  display: flex;
  flex-direction: column;

  /* 间距 12px -> 16px：--space-4 未定义（见 profile/index.vue 前车之鉴），用 --space-compact */
  gap: var(--space-compact);
  min-width: 160px;

  /* 数字等宽对齐：消除金额宽度抖动 */
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 2px;

  /* 子元素统一右对齐：label/数值/胶囊与整体 text-align 一致，消除「对齐奇怪」 */
  align-items: flex-end;
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-subtle);
}

.metric-item:first-child {
  padding-top: 0;
  border-top: none;
}

/* 指标区 label：限定在 overview-metrics 内，避免与账户卡片的 .metric-label 混淆 */
.overview-metrics .metric-label {
  font-size: var(--text-label, 13px);
  line-height: 18px;
  color: var(--text-tertiary);
}

/* 负债率胶囊：--bg-soft 底 + --radius-pill + --text-tertiary 字，弱化中性信息。
   右对齐由 .metric-item 的 align-items: flex-end 统一提供，不再单独 align-self */
.liability-rate-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 56px;
  padding: 1px 10px;
  font-size: var(--text-label, 13px);
  line-height: 20px;
  color: var(--text-tertiary);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

/* ===== 账户卡片网格：auto-fit 自动折叠空轨道，孤点分类不产生右侧大片空白 ===== */
.ledger-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr));
  gap: var(--space-compact);
}

/* ===== 幽灵态新增占位符：--bg-soft 底、胶囊圆角、高度恒定 44px ===== */
.ghost-add {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 44px;
  padding: 0 var(--space-compact);
  margin-top: var(--space-compact);
  font-family: inherit;
  font-size: var(--text-small, 14px);
  color: var(--text-secondary);
  cursor: pointer;
  background: var(--bg-soft);
  border: none;
  border-radius: var(--radius-pill);
  transition: background-color 0.15s ease;
}

.ghost-add:hover {
  background: var(--bg-hover);
}

.ghost-add:focus-visible {
  box-shadow: var(--focus-ring);
}

.ghost-add__icon {
  font-size: 14px;
}

/* ===== 次级导航按钮（投资组合/策略分析）：文本按钮风格 ===== */
.btn-ghost-text {
  --el-button-bg-color: transparent;
  --el-button-border-color: transparent;
  --el-button-text-color: var(--text-secondary);
  --el-button-hover-bg-color: var(--bg-hover);
  --el-button-hover-border-color: transparent;
  --el-button-hover-text-color: var(--text-primary);
  --el-button-active-bg-color: transparent;
  --el-button-active-border-color: transparent;
}
</style>
