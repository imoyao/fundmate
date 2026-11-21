<template>
  <div
    class="ledger-list p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 页面标题 & 操作栏 -->
    <div class="page-head">
      <div class="page-head__text">
        <h2 class="page-head__title">账户管理</h2>
        <p class="page-head__sub">管理您的银行账户、证券账户、基金和实物资产</p>
      </div>
      <div class="page-head__actions">
        <!-- 次级导航（投资组合 / 策略分析）：文本按钮，与主操作之间用竖线分开。
             两者不是本页动作，而是「去别处看」，混在按钮组里会和「新增账户」抢注意力。 -->
        <nav class="page-head__links" aria-label="相关页面">
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
        </nav>
        <span class="page-head__divider" aria-hidden="true" />
        <div class="page-head__primary">
          <!-- 「显示已归档」是筛选开关，不是主操作：原先在激活态走 type=primary，
               整颗按钮会被刷成品牌实底，与「新增账户」并列时读成两个主按钮。
               改成独立胶囊开关（aria-pressed），激活态只染浅品牌底 + 品牌文字色。 -->
          <el-button
            class="archive-toggle"
            :class="{ 'is-active': showArchived }"
            :aria-pressed="showArchived"
            @click="toggleArchived"
          >
            <IconifyIconOffline icon="ep:box" class="mr-1" />
            {{ showArchived ? "隐藏已归档" : "显示已归档" }}
            <span v-if="archivedCount > 0" class="archive-toggle__count">
              {{ archivedCount }}
            </span>
          </el-button>
          <el-button type="primary" @click="openCreateDialog()">
            <IconifyIconOffline icon="ep:plus" class="mr-1" /> 新增账户
          </el-button>
        </div>
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

    <!-- 空态给出口而不是指路：原先写「点击上方按钮新增」，用户得回头找按钮；
         这里直接把「新增账户」放在空态里，一步到达。 -->
    <CardBlock v-else-if="allLedgers.length === 0" class="empty-state">
      <span class="empty-state__icon" aria-hidden="true">
        <IconifyIconOffline icon="ep:wallet" />
      </span>
      <p class="empty-state__title">还没有账户</p>
      <p class="empty-state__desc">建好账户后，导入的持仓与流水才有归属。</p>
      <el-button type="primary" @click="openCreateDialog()">
        <IconifyIconOffline icon="ep:plus" class="mr-1" /> 新增账户
      </el-button>
    </CardBlock>

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
import CardBlock from "@/components/CardBlock/index.vue";
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

/** 归档筛选开关：改状态后走同一取数入口（与原先模板内联写法等价） */
function toggleArchived() {
  showArchived.value = !showArchived.value;
  fetchData();
}
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

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

/* ===== 页头：标题 + 副标题（左），次级导航 | 主操作（右） =====
   与下方卡片区同为 24px 纵向间距（--space-standard），页头不再是「一块独立的
   标题区」而是卡片列表的第一层。 */
.page-head {
  display: flex;
  gap: var(--space-compact);
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-standard);
}

.page-head__title {
  margin: 0;
  font-size: var(--text-title);
  font-weight: 700;
  line-height: 1.25;
  color: var(--text-primary);
  white-space: nowrap;
}

.page-head__sub {
  margin: 4px 0 0;
  font-size: var(--text-small);
  line-height: 22px;
  color: var(--text-tertiary-ink);
}

.page-head__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  justify-content: flex-end;
}

.page-head__links {
  display: flex;
  gap: 2px;
  align-items: center;
}

/* 次级导航与主操作之间的竖线：两者语义不同（去别处看 / 在本页做），
   靠一条 --border-light 细线分组，比空 16px 更清楚地表达「不是一组」。 */
.page-head__divider {
  width: 1px;
  height: 16px;
  background: var(--border-light);
}

.page-head__primary {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

/* 窄屏（< xl）：页头改上下排。1280 是「标题块 + 操作组」刚好并得下的一档
   （实测 966 / 992px 内容宽）；再窄仍强行并排，副标题会被挤成两行、操作组折行。 */
@include bp.below("xl") {
  .page-head {
    flex-direction: column;
    align-items: stretch;
  }

  .page-head__actions {
    justify-content: flex-start;
  }
}

/* 手机：操作组再折一层——次级导航一行，主操作独占一行（与标题同宽），
   此时竖线已不在「两组之间」，隐藏。 */
@include bp.below("sm") {
  .page-head__divider {
    display: none;
  }

  .page-head__primary {
    flex: 1 1 100%;
  }
}

/* ===== 归档筛选开关：胶囊形态、浅品牌底表示「已开启」 =====
   它是筛选器不是主操作——激活态若用品牌实底，会与「新增账户」并排读成两个主按钮。 */
.archive-toggle {
  --el-button-text-color: var(--text-secondary);
  --el-button-bg-color: transparent;
  --el-button-border-color: var(--border-light);
  --el-button-hover-text-color: var(--text-primary);
  --el-button-hover-bg-color: var(--bg-hover);
  --el-button-hover-border-color: var(--border-light);
  --el-button-active-bg-color: var(--bg-hover);
  --el-button-active-border-color: var(--border-light);
}

.archive-toggle.is-active {
  --el-button-text-color: var(--brand-ink);
  --el-button-bg-color: var(--brand-100);
  --el-button-border-color: var(--brand-300);
  --el-button-hover-text-color: var(--brand-ink);
  --el-button-hover-bg-color: var(--brand-200);
  --el-button-hover-border-color: var(--brand-300);
  --el-button-active-bg-color: var(--brand-200);
  --el-button-active-border-color: var(--brand-300);
}

/* 计数徽标：与胶囊同色系但更浅，数字不参与按钮主文案的阅读顺序 */
.archive-toggle__count {
  display: inline-block;
  min-width: 18px;
  padding: 0 5px;
  margin-left: 4px;
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  line-height: 18px;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.archive-toggle.is-active .archive-toggle__count {
  color: var(--brand-ink);
  background: var(--bg-card);
}

/* ===== 空态：一句结论 + 一个出口，不做插画式堆叠 ===== */
.empty-state {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-12) var(--space-standard);
  text-align: center;
}

.empty-state__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  margin-bottom: var(--space-2);
  font-size: var(--text-title);
  color: var(--text-tertiary-ink);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.empty-state__title {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
  line-height: 24px;
  color: var(--text-primary);
}

.empty-state__desc {
  margin: 0 0 var(--space-3);
  font-size: var(--text-label);
  line-height: 20px;
  color: var(--text-tertiary-ink);
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
