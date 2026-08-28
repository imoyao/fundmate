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
        <el-button type="primary" @click="openCreateDialog()">
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

      <!-- 场外基金（含E账户）聚合汇总卡：整卡可点下钻至聚合视图 -->
      <div
        class="overview-card fund-summary-card mb-6"
        role="button"
        tabindex="0"
        @click="goToFundAggregation"
        @keydown.enter="goToFundAggregation"
      >
        <div class="flex justify-between items-center gap-4 flex-wrap">
          <div class="min-w-0">
            <p class="text-sm" :style="{ color: 'var(--text-tertiary)' }">
              场外基金（含E账户）
            </p>
            <div class="mt-1">
              <MoneyDisplay
                :value="fundTotalYuan"
                size="lg"
                :show-sign="false"
                :auto-color="false"
              />
            </div>
          </div>
          <el-button type="primary" plain @click.stop="goToFundAggregation">
            <IconifyIconOffline icon="ep:right" class="mr-1" /> 查看明细
          </el-button>
        </div>
      </div>

      <!-- 未归置持仓清理套件（#984 拆分至 components/OrphanCleanupDialogs.vue）：
           banner + 归入对话框 + 明细对话框 -->
      <OrphanCleanupDialogs
        :orphan-group="orphanGroup"
        :all-ledgers="allLedgers"
        @refresh="fetchData"
      />

      <!-- 按类型分组的账户卡片列表；外层 ledger-groups 供「分组顺序拖拽」，与卡片拖拽互相独立 -->
      <div ref="groupsContainer" class="ledger-groups">
        <div
          v-for="group in displayedGroups"
          :key="group.type"
          class="mb-8 ledger-group"
          :class="{
            'ledger-group--dragging': group.type === draggingGroupType
          }"
        >
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-1 min-w-0">
              <!-- 分组拖拽抓手：与卡片抓手视觉/作用域分离，hover/focus 显示，拖拽整个分组（分组顺序存 localStorage） -->
              <span
                class="group-drag-handle"
                role="button"
                tabindex="-1"
                :title="`拖动调整分组顺序：${group.label}`"
                @click.stop
                @keydown.enter.stop
              >
                <!-- 分组拖拽：纵向三横线「块」抓手，暗示整段分组重排，与卡片四向箭头明确区分 -->
                <svg
                  class="drag-grip drag-grip--group"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  aria-hidden="true"
                >
                  <line x1="6" y1="6" x2="18" y2="6" />
                  <line x1="6" y1="12" x2="18" y2="12" />
                  <line x1="6" y1="18" x2="18" y2="18" />
                </svg>
              </span>
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
          </div>

          <!-- 账户卡片：auto-fit 网格自动折叠空轨道，孤点分类不会产生右侧大片空白。
             卡片展示细节已拆分至 components/LedgerCard.vue（#984）。
             网格绑定 data-ledger-type 供 sortablejs 按类型初始化拖拽（仅同组内可拖）。 -->
          <div class="ledger-grid" :data-ledger-type="group.type">
            <LedgerCard
              v-for="ledger in group.ledgers"
              :key="ledger.id"
              :ledger="ledger"
              @open="goToDetail"
              @delete="openDeleteDialog"
              @toggle-archive="onToggleArchive"
            />
          </div>

          <!-- 幽灵态新增占位符：胶囊小按钮，高度恒定 44px，不撑满网格行。
             携带分组类型打开弹窗，预置账户类型（#1082 入口预填） -->
          <button
            type="button"
            class="ghost-add"
            :aria-label="`新增${getChannelCategoryLabel(group.type)}`"
            @click="openCreateDialog(group.type)"
          >
            <IconifyIconOffline icon="ep:plus" class="ghost-add__icon" />
            <span>新增{{ getChannelCategoryLabel(group.type) }}</span>
          </button>
        </div>
      </div>
    </template>

    <!-- 新增账户对话框（#984 拆分至 components/CreateAccountDialog.vue）；
         initial-ledger-type：分组幽灵按钮入口预置账户类型（#1082） -->
    <CreateAccountDialog
      v-model:visible="showCreateDialog"
      :cash-ledgers="cashLedgers"
      :portfolio-list="portfolioList"
      :sales-institutions="salesInstitutions"
      :initial-ledger-type="initialCreateType"
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
import { ref, computed, onMounted, nextTick } from "vue";
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
  reorderLedgers,
  getFundAggregation,
  type SalesInstitution
} from "@/api/ledger";
import Sortable from "sortablejs";
import { getPortfolios } from "@/api/portfolio";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { getChannelCategoryLabel } from "@/constants";
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

/** 场外基金（含E账户）聚合总市值（分，整数）；独立获取，失败不影响主账户列表 */
const fundTotalCents = ref(0);
const fundTotalYuan = computed(() => fundTotalCents.value / 100);

const showCreateDialog = ref(false);
/** 创建弹窗初始渠道分组：顶部「新增账户」默认 bank；分组幽灵按钮预置对应渠道分组 */
const initialCreateType = ref("bank");
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

// 分组展示（按渠道分组 channel_category，组内排序）：手动排序序号优先，回退按持仓金额降序（#1083）
// 旧数据可能无 channel_category，按 legacy ledger_type 映射兜底到对应渠道分组。
const LEGACY_TYPE_TO_CHANNEL: Record<string, string> = {
  bank: "bank",
  stock: "securities",
  fund: "fund_platform",
  property: "other"
};
function channelOf(ledger: any): string {
  if (ledger.channel_category) return ledger.channel_category;
  return LEGACY_TYPE_TO_CHANNEL[ledger.ledger_type] || "other";
}

function buildGroups(ledgers: any[]) {
  const groups: Record<string, any> = {};
  for (const ledger of ledgers) {
    const type = channelOf(ledger);
    if (!groups[type]) {
      groups[type] = {
        type,
        label: getChannelCategoryLabel(type),
        total: 0,
        count: 0,
        ledgers: [] as any[]
      };
    }
    groups[type].count++;
    groups[type].total += ledger.total_market_value || 0;
    groups[type].ledgers.push(ledger);
  }

  // 分组顺序来自本地偏好（groupOrder），默认 银行/证券/基金平台/保险/期货/其他；
  // 仅保留实际有账户的分组（空分组不渲染）
  const result = groupOrder.value.filter(type => groups[type]) as any[];

  // 未归置持仓不再作为分组卡片进入网格（2026-08 改版），统一由顶部警示 banner 承接
  // 组内排序：已手动排序（display_order 非 null）的卡片按 display_order 升序排在前面，
  // 其余（null）回退到「按持仓金额降序」，默认即金额大的靠前。
  for (const g of result) {
    g.ledgers.sort((a: any, b: any) => {
      const da = a.display_order ?? Infinity;
      const db = b.display_order ?? Infinity;
      if (da !== db) return da - db;
      return (b.total_market_value || 0) - (a.total_market_value || 0);
    });
  }
  return result;
}

// 实际渲染用的分组（可被拖拽直接重排：拖拽时修改该分组 ledgers 数组并落库）
const displayedGroups = ref<any[]>([]);

// ── 分组顺序（纯视图偏好，存 localStorage，不落库；与组内卡片排序分层）──
const GROUP_ORDER_KEY = "fundmate:ledgerGroupOrder:v1";
const DEFAULT_GROUP_ORDER = [
  "bank",
  "securities",
  "fund_platform",
  "insurance",
  "futures",
  "other"
];
function loadGroupOrder(): string[] {
  try {
    const raw = localStorage.getItem(GROUP_ORDER_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.every(t => typeof t === "string")) {
        const stored = parsed.filter(t => DEFAULT_GROUP_ORDER.includes(t));
        const missing = DEFAULT_GROUP_ORDER.filter(t => !stored.includes(t));
        return [...stored, ...missing];
      }
    }
  } catch {
    /* 解析失败时回退默认顺序 */
  }
  return [...DEFAULT_GROUP_ORDER];
}
function saveGroupOrder(order: string[]) {
  try {
    localStorage.setItem(GROUP_ORDER_KEY, JSON.stringify(order));
  } catch {
    /* 隐私模式等场景忽略写入失败 */
  }
}
const groupOrder = ref<string[]>(loadGroupOrder());

// 分组整体拖拽（与卡片拖拽是两套独立 Sortable，handle 互不触发）
const groupsContainer = ref<HTMLElement | null>(null);
// 拖拽中的分组类型：用于高亮当前被拖的分组，强化「正在重排整段」的反馈
const draggingGroupType = ref<string | null>(null);
let groupSortable: any = null;
function destroyGroupSortable() {
  if (groupSortable) {
    groupSortable.destroy();
    groupSortable = null;
  }
}
function initGroupSortable() {
  destroyGroupSortable();
  if (!groupsContainer.value) return;
  groupSortable = Sortable.create(groupsContainer.value, {
    animation: 180,
    handle: ".group-drag-handle",
    ghostClass: "ledger-group--ghost",
    onStart: (evt: any) => {
      const moved = displayedGroups.value[evt.oldIndex];
      draggingGroupType.value = moved?.type ?? null;
    },
    onEnd: (evt: any) => {
      const { oldIndex, newIndex } = evt;
      draggingGroupType.value = null;
      if (oldIndex == null || newIndex == null || oldIndex === newIndex) return;
      const arr = displayedGroups.value;
      const [moved] = arr.splice(oldIndex, 1);
      if (!moved) return;
      arr.splice(newIndex, 0, moved);
      const order = arr.map(g => g.type);
      groupOrder.value = order;
      saveGroupOrder(order);
    }
  });
}

// ── 拖拽排序（仅限同类型组内，#1083）──
const sortables: Record<string, any> = {};
function destroySortables() {
  Object.values(sortables).forEach((s: any) => s.destroy());
  for (const k of Object.keys(sortables)) delete sortables[k];
}
function initSortables() {
  destroySortables();
  for (const g of displayedGroups.value) {
    const el = document.querySelector(
      `.ledger-grid[data-ledger-type="${g.type}"]`
    ) as HTMLElement | null;
    if (!el) continue;
    sortables[g.type] = Sortable.create(el, {
      animation: 180,
      handle: ".drag-handle",
      ghostClass: "ledger-card--ghost",
      chosenClass: "ledger-card--chosen",
      onEnd: (evt: any) => onLedgerDragEnd(g.type, evt)
    });
  }
}
function onLedgerDragEnd(type: string, evt: any) {
  const group = displayedGroups.value.find(g => g.type === type);
  if (!group) return;
  const { oldIndex, newIndex } = evt;
  if (oldIndex == null || newIndex == null || oldIndex === newIndex) return;
  const arr = group.ledgers;
  const [moved] = arr.splice(oldIndex, 1);
  if (!moved) return;
  arr.splice(newIndex, 0, moved);
  const orderedIds = arr.map((l: any) => l.id);
  // 落库按真实 ledger_type 排序（channel_category 由 ledger_type 派生，组内 ledger_type 一致）
  const ledgerType = group.ledgers[0]?.ledger_type ?? type;
  // 乐观更新已在 UI 生效；落库失败则回填并重拉，保证最终一致
  reorderLedgers(ledgerType, orderedIds).catch(() => {
    ElMessage.error("排序保存失败，已恢复");
    fetchData();
  });
}

function openCreateDialog(channelCategory?: string) {
  // 显式传 undefined 时回退默认 bank，避免点击事件对象被误当类型参数
  initialCreateType.value =
    channelCategory && typeof channelCategory === "string"
      ? channelCategory
      : "bank";
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

/** 下钻到场外基金（含E账户）聚合视图 */
function goToFundAggregation() {
  router.push({ name: "fund-aggregation" });
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
    // 重新分组并构建可拖拽的展示结构（含「金额降序 / 手动序号」排序规则）
    displayedGroups.value = buildGroups(allLedgers.value);
    // 统一走公共格式化：YYYY-MM-DD HH:mm（不带秒），避免斜线/时分秒混用
    lastUpdate.value = formatDateTime(new Date());
    nextTick(() => {
      initSortables();
      initGroupSortable();
    });
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
  }
  // 独立获取场外基金（含E账户）聚合总市值：与账户列表解耦，失败静默兜底不阻塞主列表
  fetchFundTotal();
}

/** 独立获取场外基金聚合总市值（GET /api/ledgers/fund-aggregation/）。
 *  汇总值与维度无关（始终为全量场外基金市值），故用默认 product 维度取一次即可。 */
async function fetchFundTotal() {
  try {
    const res = await getFundAggregation("product");
    fundTotalCents.value = res.data?.total_market_value_cents ?? 0;
  } catch {
    fundTotalCents.value = 0;
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

/* 分组拖拽抓手：常驻低透明，hover/focus 高亮，与卡片抓手区分（分组顺序本地存储） */
.group-drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  flex: none;
  color: var(--text-tertiary);
  cursor: grab;
  border-radius: var(--radius-sm);
  opacity: 0.5;
  touch-action: none;
  transition:
    opacity 0.15s ease,
    color 0.15s ease,
    background-color 0.15s ease;
}

.group-drag-handle:active {
  cursor: grabbing;
}

.ledger-group:hover .group-drag-handle,
.group-drag-handle:hover {
  opacity: 1;
  color: var(--brand-600);
  background: var(--bg-page);
}

/* 分组抓手：纵向三横线「块」抓手，描边风格 */
.drag-grip--group {
  padding: 2px;
}

/* 分组拖拽中的占位「幽灵」态 */
.ledger-group--ghost {
  opacity: 0.4;
}

/* 分组拖拽中：整段高亮，强化「正在重排整段分组」的反馈（与卡片拖拽态分层） */
.ledger-group--dragging {
  border-radius: var(--radius-xl);
  box-shadow: 0 0 0 2px var(--brand-300);
  background: var(--brand-50);
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

/* 场外基金（含E账户）汇总卡：整卡可点下钻，复用 overview-card 视觉语言 */
.fund-summary-card {
  cursor: pointer;
  transition:
    box-shadow 0.15s ease,
    border-color 0.15s ease;
}

.fund-summary-card:hover {
  box-shadow: var(--shadow-float);
  border-color: var(--border-strong);
}

.fund-summary-card:focus-visible {
  box-shadow: var(--focus-ring);
  outline: none;
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
