<template>
  <div
    class="account-detail p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 顶部操作栏 -->
    <div class="mb-4 flex justify-between items-center">
      <el-button text @click="goBack">
        <IconifyIconOffline icon="ep:arrow-left" class="mr-1" /> 返回
      </el-button>
      <div v-if="!isUnclassified && accountInfo" class="flex gap-2">
        <el-button @click="router.push({ name: 'InvestmentReconcile' })">
          <IconifyIconOffline icon="ep:data-analysis" class="mr-1" /> 对账
        </el-button>
        <el-button @click="openEditDialog">
          <IconifyIconOffline icon="ep:edit" class="mr-1" /> 编辑
        </el-button>
        <el-button v-if="accountInfo" @click="toggleArchiveDetail(accountInfo)">
          <IconifyIconOffline
            :icon="
              accountInfo.is_active === false ? 'ep:refresh-left' : 'ep:box'
            "
            class="mr-1"
          />
          {{ accountInfo.is_active === false ? "激活" : "归档" }}
        </el-button>
        <el-button
          v-if="!isUnclassified && holdingsTotal > 0"
          @click="migrationPanelRef?.openBatchMigrateDialog()"
        >
          <IconifyIconOffline icon="ep:share" class="mr-1" /> 批量迁移
        </el-button>
        <div class="flex items-center gap-1">
          <el-button
            v-if="!isUnclassified && accountInfo"
            type="danger"
            text
            @click="openDeleteDialog(accountInfo)"
          >
            <IconifyIconOffline icon="ep:delete" class="mr-1" /> 删除
          </el-button>
          <IconifyIconOffline
            icon="ep:arrow-right"
            :style="{ color: 'var(--text-tertiary-ink)' }"
          />
        </div>
      </div>
    </div>

    <!-- ✅ 核心修复：在外层增加一个 div，保证 <Transition> 动画时只有一个根节点 -->
    <div class="w-full">
      <!-- 加载状态：结构匹配的骨架屏。阈值控制（200ms）在 script 侧：请求太快则不显示，避免闪屏 -->
      <PageSkeleton
        v-if="loading && showSkeleton"
        :cards="3"
        :chart-cols="2"
        :table-rows="6"
      />

      <template v-else>
        <!-- 页内导航（#2739）：<xl 顶部锚点胶囊；xl+ 由正文右侧的目录 rail
             （PageToc）接管。两级互斥，条目由 usePageNav 按 DOM 里真实渲染的
             nav-* 锚点动态生成——整块不渲染的区块（类现金为 0、未归置持仓页）
             自动不留死链。 -->
        <PageNav
          v-if="navItems.length > 1"
          :items="navItems"
          :active-id="navActiveId"
          @navigate="goToNavSection"
        />

        <div class="account-detail__body">
          <div ref="pageMain" class="account-detail__main">
            <LedgerDetailOverview :page="page" />
            <!-- #2616 资金流动：入金/出金/净投入/期末资产（未分类账户没有真实归属，不展示）。
                 组件已上移 components/CashFlowPanel（#2681：账户级 / 组合级共享同一份口径）。
                 #2739：id 经 fallthrough 落在卡片根（单根元素）＝ 锚点即标题行顶边。 -->
            <CashFlowPanel
              v-if="!isUnclassified && ledgerIdNum"
              id="nav-cash-flow"
              :ledger-id="ledgerIdNum"
              class="mt-4"
            />
            <!-- Tab 切换 + 搜索同行（#982）：左 Tab 右搜索，共用一个输入框按当前 Tab 绑定 -->
            <el-card shadow="never">
              <div class="tabs-toolbar">
                <el-tabs
                  v-model="activeTab"
                  class="ledger-tabs"
                  @tab-change="onTabChange"
                >
                  <LedgerDetailHoldingsPane :page="page" />

                  <LedgerDetailTransactionsPane :page="page" />
                </el-tabs>
                <!-- 搜索框与 Tab 同行：按当前 Tab 绑定各自搜索词（#982） -->
                <el-input
                  v-model="activeSearch"
                  aria-label="搜索产品名称或代码"
                  placeholder="搜索产品名称 / 代码"
                  clearable
                  class="tab-search-input"
                  :prefix-icon="Search"
                  @input="onSearchInput"
                />
              </div>
            </el-card>
          </div>

          <!-- xl+ 右目录 rail：与顶部胶囊共用 items/activeId（usePageNav 下发） -->
          <PageToc
            v-if="navItems.length > 1"
            :items="navItems"
            :active-id="navActiveId"
            @navigate="goToNavSection"
          />
        </div>
      </template>

      <EditAccountDialog
        v-model:visible="showEditDialog"
        :ledger-id="ledgerId"
        :account-info="accountInfo"
        :ledgers="ledgers"
        :portfolio-list="portfolioList"
        :sales-institutions="salesInstitutions"
        :cash-ledgers="cashLedgers"
        @saved="onAccountUpdated"
      />

      <MigrateDialog
        ref="migrateDialogRef"
        :ledger-id="ledgerId"
        :same-type-ledgers="sameTypeLedgers"
        @migrated="loadHoldings"
      />

      <MigrationResolvePanel
        ref="migrationPanelRef"
        :ledgers="ledgers"
        :account-info="accountInfo"
        :sales-institutions="salesInstitutions"
        :ledger-id="ledgerId"
        :account-name="accountName"
        :same-type-ledgers="sameTypeLedgers"
        @committed="onMigrationCommitted"
      />

      <!-- 复用持仓明细抽屉同款的「编辑交易」弹窗，保证两处编辑字段一致（#982 体验统一） -->
      <TransactionEditDialog
        v-model="editTxnDialogVisible"
        :transaction="editingTxn"
        :asset-type="editingTxn?.asset_type"
        :symbol="editingTxn?.symbol"
        @saved="onTxnSaved"
      />

      <DeleteLedgerDialog
        v-model:visible="deleteDialogVisible"
        :ledger-id="deletingAccount?.id ?? 0"
        :ledger-name="deletingAccount?.name ?? ''"
        :position-count="holdingsTotal"
        @deleted="router.push({ name: 'AssetLedgers' })"
      />
    </div>
    <!-- 持仓明细抽屉 -->
    <PositionTransactionsDrawer
      v-model:visible="drawerVisible"
      :position-data="selectedPosition"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { Search } from "@element-plus/icons-vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import PageNav from "@/components/PageNav/index.vue";
import PageToc from "@/components/PageToc/index.vue";
import { usePageNav } from "@/composables/usePageNav";
import DeleteLedgerDialog from "./components/DeleteLedgerDialog.vue";
import PositionTransactionsDrawer from "./components/PositionTransactionsDrawer.vue";
import TransactionEditDialog from "./components/TransactionEditDialog.vue";
import EditAccountDialog from "./components/EditAccountDialog.vue";
import MigrateDialog from "./components/MigrateDialog.vue";
import MigrationResolvePanel from "./components/MigrationResolvePanel.vue";
import LedgerDetailOverview from "./components/LedgerDetailOverview.vue";
import CashFlowPanel from "@/components/CashFlowPanel/index.vue";
import LedgerDetailHoldingsPane from "./components/LedgerDetailHoldingsPane.vue";
import LedgerDetailTransactionsPane from "./components/LedgerDetailTransactionsPane.vue";
import { useLedgerDetailPage } from "./composables/useLedgerDetailPage";

defineOptions({ name: "LedgerDetail" });

// #980 P1-C 纯结构拆分：状态与动作收敛进 composables/useLedgerDetailPage.ts
// （组合既有三个领域 composable + 温柔提醒状态），三个子组件经 page prop 注入
// 同一实例。本文件只保留页面壳编排；解构后模板内自动解包 ref，绑定表达式与
// 拆分前逐字一致。
const page = useLedgerDetailPage();
const {
  router,
  isUnclassified,
  accountInfo,
  openEditDialog,
  toggleArchiveDetail,
  holdingsTotal,
  migrationPanelRef,
  openDeleteDialog,
  loading,
  showSkeleton,
  activeTab,
  onTabChange,
  activeSearch,
  onSearchInput,
  showEditDialog,
  ledgerId,
  ledgerIdNum,
  ledgers,
  portfolioList,
  salesInstitutions,
  cashLedgers,
  onAccountUpdated,
  sameTypeLedgers,
  loadHoldings,
  accountName,
  onMigrationCommitted,
  editTxnDialogVisible,
  editingTxn,
  onTxnSaved,
  deleteDialogVisible,
  deletingAccount,
  drawerVisible,
  selectedPosition,
  migrateDialogRef
} = page;

// ---------- 页内导航（#2739）----------
// 纵向分析区块 7 个、页面明显超过一屏，符合 components.md「长页面页内导航」
// 的接入判据。state / scroll-spy / 跳转动画全在共享 usePageNav 里，
// 本文件只提供「锚点 → 标签」映射。
//
// 标签与各区块的 SectionHeader 标题**逐字一致**（读屏与视觉同一套词汇）。
// 锚点由 DOM 存在性过滤决定：整块不渲染的区块（类现金为 0 的普通基金账户、
// 未归置持仓页的深度分析）自动不留死链。
//
// 持仓明细 / 交易记录**不进目录**：它们是页面末端的 el-tabs（视图切换区），
// 一个锚点指不到两个 tab 中的哪一个，硬挂一个必然指错；它们也是页面最后一屏，
// 自然滚动即达。
const pageMain = ref<HTMLElement>();
const NAV_LABELS: Record<string, string> = {
  "nav-overview": "账本概览",
  "nav-cash-like": "类现金",
  "nav-calendar": "收益日历",
  "nav-attribution": "收益归因",
  "nav-structure": "持仓结构",
  "nav-penetration": "持仓穿透",
  "nav-cash-flow": "资金流动"
};
const {
  items: navItems,
  activeId: navActiveId,
  goTo: goToNavSection
} = usePageNav(pageMain, {
  labels: NAV_LABELS,
  // 换账户 = 换页内容：作废上一次跳转意图并重扫锚点
  rescanOn: () => ledgerId.value
});

/**
 * 返回（#1845 回归修复）。
 *
 * 原先直接 `@click="$router.back()"`。用 hash 路由 + **直接输 URL / 刷新进来**时，
 * 浏览器历史栈里没有上一条记录，`router.back()` 是**静默 no-op** ——
 * 按钮点了没反应，用户只会以为页面坏了。
 *
 * 现在：有历史就 back（保留「从哪来回哪去」），没有就回账户列表这个明确的去处。
 * 判空用 `history.state?.back`：vue-router 在历史记录里放 `{ back: <上一条> }`，
 * 直接打开页面时它是 null。
 */
function goBack() {
  if (window.history.state?.back) {
    router.back();
    return;
  }
  router.push({ name: "AssetLedgers" });
}
</script>

<style scoped>
/* 页内导航两级布局（components.md PageToc）：<xl 单列（胶囊在正文上方整条横跨）；
   xl+ 主列 + 160px 右目录 rail，列间距走 --space-5（与组合详情页同款宽度账）。 */
.account-detail__body {
  display: flex;
  gap: var(--space-5);
}

.account-detail__main {
  flex: 1;
  min-width: 0;
}

/* Tab 工具栏（#982）：搜索框绝对定位到 Tab 头右侧，与标签同一行。
   不能用 flex 横排——el-tabs 包含整个内容区，横排会把输入框挤到表格右侧 */
.tabs-toolbar {
  position: relative;
}

.tab-search-input {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 1;
  width: 220px;
}
</style>
