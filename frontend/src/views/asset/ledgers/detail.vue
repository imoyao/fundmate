<template>
  <div
    class="account-detail p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 顶部操作栏 -->
    <div class="mb-4 flex justify-between items-center">
      <el-button text @click="$router.back()">
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
        <LedgerDetailOverview :page="page" />
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
              placeholder="搜索产品名称 / 代码"
              clearable
              class="tab-search-input"
              :prefix-icon="Search"
              @input="onSearchInput"
            />
          </div>
        </el-card>
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
import { Search } from "@element-plus/icons-vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import DeleteLedgerDialog from "./components/DeleteLedgerDialog.vue";
import PositionTransactionsDrawer from "./components/PositionTransactionsDrawer.vue";
import TransactionEditDialog from "./components/TransactionEditDialog.vue";
import EditAccountDialog from "./components/EditAccountDialog.vue";
import MigrateDialog from "./components/MigrateDialog.vue";
import MigrationResolvePanel from "./components/MigrationResolvePanel.vue";
import LedgerDetailOverview from "./components/LedgerDetailOverview.vue";
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
</script>

<style scoped>
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
