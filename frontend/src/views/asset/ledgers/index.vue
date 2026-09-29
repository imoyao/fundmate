<template>
  <div
    class="ledger-list p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 页面标题 & 操作栏 -->
    <div
      class="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between"
    >
      <div>
        <h2
          class="text-2xl font-bold whitespace-nowrap"
          :style="{ color: 'var(--text-primary)' }"
        >
          账户管理
        </h2>
        <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary-ink)' }">
          管理您的银行账户、证券账户、基金和实物资产
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
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
      :style="{ color: 'var(--text-tertiary-ink)' }"
    >
      <p class="mt-2">加载中...</p>
    </div>

    <div
      v-else-if="allLedgers.length === 0"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    >
      <IconifyIconOffline icon="ep:wallet" class="text-5xl mb-3 opacity-30" />
      <p class="text-lg">暂无账户，点击上方按钮新增</p>
    </div>

    <template v-else>
      <LedgerOverviewSection :page="page" />

      <!-- 未归置持仓清理套件（#984 拆分至 components/OrphanCleanupDialogs.vue）：
           banner + 归入对话框 + 明细对话框 -->
      <OrphanCleanupDialogs
        :orphan-group="orphanGroup"
        :all-ledgers="allLedgers"
        @refresh="fetchData"
      />

      <LedgerGroupsList :page="page" />
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
import { IconifyIconOffline } from "@/components/ReIcon";
import DeleteLedgerDialog from "./components/DeleteLedgerDialog.vue";
import CreateAccountDialog from "./components/CreateAccountDialog.vue";
import OrphanCleanupDialogs from "./components/OrphanCleanupDialogs.vue";
import LedgerOverviewSection from "./components/LedgerOverviewSection.vue";
import LedgerGroupsList from "./components/LedgerGroupsList.vue";
import { useLedgerList } from "./composables/useLedgerList";

defineOptions({ name: "AssetLedgers" });

// #980 P1-C 结构拆分：状态与动作收敛在 composables/useLedgerList.ts，
// 两个子组件经 page prop 注入同一实例；index 只保留页面壳编排
// （解构后在模板内自动解包 ref，绑定表达式与拆分前逐字一致）。
const page = useLedgerList();
const {
  loading,
  allLedgers,
  showArchived,
  archivedCount,
  openCreateDialog,
  fetchData,
  orphanGroup,
  showCreateDialog,
  cashLedgers,
  portfolioList,
  salesInstitutions,
  initialCreateType,
  deleteDialogVisible,
  deletingAccount
} = page;
</script>

<style scoped>
/* 触屏设备无 hover 态的删除按钮样式已随 LedgerCard 迁移 */

/* 尊重系统减弱动效偏好：本页 .ghost-add/.overview-card/.ledger-card 等规则已随
   两个子组件迁移（见各子组件 scoped 块）；.ledger-row-action/.orphan-banner 等
   子组件内部元素的对应规则同样见各组件 scoped 块 */

.ledger-list {
  /* 字体继承全局 token（--font-ui → Inter 优先），不再硬编码 PingFang 栈，
     避免与站内其它页面字体不一致（design-tokens.css --font-ui） */
  font-family: var(--font-ui);

  /* 全页数字等宽对齐：消除金额/统计数字宽度抖动（design.md「数字等宽对齐」） */
  font-variant-numeric: tabular-nums;
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
