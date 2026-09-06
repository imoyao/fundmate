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
            :style="{ color: 'var(--text-tertiary)' }"
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
        <!-- 账户信息头部 -->
        <div class="mb-6 flex items-center justify-between">
          <div>
            <h2
              class="text-2xl font-bold"
              :style="{ color: 'var(--text-primary)' }"
            >
              {{ accountName }}
            </h2>
            <div class="flex items-center gap-2 mt-1">
              <el-tag size="small" type="info" round>{{ subTitle }}</el-tag>
              <template v-if="summaryData?.portfolio_name">
                <span
                  class="text-xs"
                  :style="{ color: 'var(--text-tertiary)' }"
                >
                  · 组合: {{ summaryData.portfolio_name }}</span
                >
              </template>
            </div>
          </div>
        </div>

        <!-- 温柔提醒（#1133 §4）：中性信息色、拟人化、非阻断；可选「去对账/忽略」，绝不强制 -->
        <transition name="el-fade-in">
          <div
            v-if="visibleConsistencyItems.length > 0"
            class="soft-reconcile-banner"
            role="note"
          >
            <IconifyIconOffline
              icon="ep:info-filled"
              class="soft-reconcile-banner__icon"
            />
            <div class="soft-reconcile-banner__body">
              <p class="soft-reconcile-banner__title">
                这本账本的持仓快照截至
                {{
                  visibleConsistencyItems[0].snapshot_date
                }}，快照日之后仍有交易记录；如与流水对不上，请去对账工作台核对是否需要补录。
              </p>
              <p class="soft-reconcile-banner__detail">
                共
                {{ visibleConsistencyItems.length }}
                笔持仓可能滞后，去对账工作台可统一核对。
              </p>
            </div>
            <div class="soft-reconcile-banner__actions">
              <el-button size="small" type="primary" plain @click="goReconcile">
                去对账
              </el-button>
              <el-button size="small" text @click="dismissAllConsistency">
                忽略
              </el-button>
            </div>
          </div>
        </transition>

        <!-- 账本概览（对齐「家庭资产看板」范式：SectionHeader + CardBlock，左指标 / 右资产构成） -->
        <SectionHeader title="账本概览" />
        <CardBlock class="mb-6">
          <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
            <!-- 左栏：核心指标（总资产 + 持仓盈亏 / 持仓与余额） -->
            <div
              :class="isCompositionLedger ? 'lg:col-span-7' : 'lg:col-span-12'"
              class="flex flex-col gap-5"
            >
              <!-- 总资产 -->
              <div>
                <p
                  class="text-sm mb-2"
                  :style="{ color: 'var(--text-tertiary)' }"
                >
                  总资产
                </p>
                <div class="flex items-baseline gap-2">
                  <MoneyDisplay
                    :value="summaryData?.total_market_value || 0"
                    size="hero"
                    :show-sign="false"
                  />
                  <span
                    class="text-xl font-medium"
                    :style="{ color: 'var(--text-secondary)' }"
                    >元</span
                  >
                </div>
              </div>

              <!-- 持仓盈亏 + 持仓与余额 指标网格（分隔线对齐看板） -->
              <div
                class="grid grid-cols-2 gap-x-4 gap-y-5 pt-5"
                :style="{ borderTop: '1px solid var(--border-light)' }"
              >
                <!-- 持仓盈亏（涨红跌绿） -->
                <div class="flex flex-col">
                  <span
                    class="text-xs mb-1"
                    :style="{ color: 'var(--text-tertiary)' }"
                    >持仓盈亏</span
                  >
                  <MoneyDisplay
                    :value="summaryData?.position_pnl || 0"
                    size="lg"
                  />
                </div>
                <!-- 持仓数量 -->
                <div class="flex flex-col">
                  <span
                    class="text-xs mb-1"
                    :style="{ color: 'var(--text-tertiary)' }"
                    >持仓数量</span
                  >
                  <span
                    class="text-lg font-semibold"
                    :style="{ color: 'var(--text-primary)' }"
                    >{{ summaryData?.position_count || 0 }} 项</span
                  >
                </div>
                <!-- 资金余额（中性余额，不随涨跌着色） -->
                <div class="flex flex-col">
                  <span
                    class="text-xs mb-1"
                    :style="{ color: 'var(--text-tertiary)' }"
                    >资金余额</span
                  >
                  <MoneyDisplay
                    v-if="summaryData?.cash_balance != null"
                    :value="summaryData.cash_balance"
                    size="md"
                    :show-sign="false"
                    :auto-color="false"
                  />
                  <span
                    v-else
                    class="text-sm"
                    :style="{ color: 'var(--text-tertiary)' }"
                    >--</span
                  >
                </div>
                <!-- 关联负债（仅银行账户且有负债时展示） -->
                <div
                  v-if="
                    summaryData?.ledger_type === 'bank' &&
                    summaryData?.linked_liability > 0
                  "
                  class="flex flex-col"
                >
                  <span
                    class="text-xs mb-1"
                    :style="{ color: 'var(--text-tertiary)' }"
                    >关联负债</span
                  >
                  <MoneyDisplay
                    :value="-summaryData.linked_liability"
                    size="md"
                    :auto-color="false"
                    custom-color="var(--color-danger-system)"
                  />
                </div>
                <!-- 货基收益（仅基金账户展示） -->
                <div
                  v-if="summaryData?.ledger_type === 'fund'"
                  class="flex flex-col"
                >
                  <span
                    class="text-xs mb-1"
                    :style="{ color: 'var(--text-tertiary)' }"
                    >货基今日收益</span
                  >
                  <MoneyDisplay
                    v-if="moneyFundData"
                    :value="moneyFundData.today_income"
                    size="md"
                  />
                  <span
                    v-else
                    class="text-sm"
                    :style="{ color: 'var(--text-tertiary)' }"
                    >--</span
                  >
                </div>
              </div>
            </div>

            <!-- 右栏：资产构成分布（仅股票 / 基金 / 信用账户，对齐看板饼图） -->
            <div
              v-if="isCompositionLedger"
              class="lg:col-span-5 flex flex-col items-center justify-center h-full"
              :style="{ borderLeft: '1px solid var(--border-light)' }"
            >
              <div class="w-full flex justify-between items-center mb-4">
                <span
                  class="font-bold text-sm"
                  :style="{ color: 'var(--text-secondary)' }"
                  >资产构成分布</span
                >
              </div>
              <AssetAllocationDonut
                :data="compositionData"
                :color-map="compositionColorMap"
                :show-legend="true"
              />
            </div>
          </div>
        </CardBlock>

        <!-- 账户深度分析（规划中，敬请期待，详见内部工作记录 ledger-detail-info-redesign-plan-2026-08-27） -->
        <CardBlock class="mb-6">
          <div
            class="flex min-h-[160px] flex-1 items-center justify-center rounded-lg border border-dashed text-sm"
            :style="{
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-tertiary)'
            }"
          >
            账户深度分析（持仓集中度 / 行业分布 / 收益日历等）规划中，敬请期待
          </div>
        </CardBlock>
        <!-- Tab 切换 + 搜索同行（#982）：左 Tab 右搜索，共用一个输入框按当前 Tab 绑定 -->
        <el-card shadow="never">
          <div class="tabs-toolbar">
            <el-tabs
              v-model="activeTab"
              class="ledger-tabs"
              @tab-change="onTabChange"
            >
              <!-- 持仓明细 Tab -->
              <el-tab-pane label="持仓明细" name="holdings">
                <el-table
                  :data="holdingsList"
                  stripe
                  size="default"
                  :default-sort="{ prop: 'market_value', order: 'descending' }"
                  @row-click="openPositionDrawer"
                >
                  <el-table-column
                    label="产品信息"
                    min-width="150"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <ProductDisplay
                        :name="row.name"
                        :symbol="row.symbol"
                        :type-label="row.type_label"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="市值"
                    width="110"
                    align="right"
                    sortable
                    prop="market_value"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <MoneyDisplay
                        :value="row.market_value || 0"
                        :show-sign="false"
                        :auto-color="false"
                        size="sm"
                      />
                    </template>
                  </el-table-column>

                  <!-- 持仓成本（#862）：接口已返回 avg_price，仅补展示列 -->
                  <el-table-column
                    label="持仓成本"
                    width="120"
                    align="right"
                    sortable
                    prop="avg_price"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <MoneyDisplay
                        :value="row.avg_price || 0"
                        :precision="pricePrecision(row.asset_type)"
                        :show-sign="false"
                        :auto-color="false"
                        size="sm"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="盈亏"
                    width="110"
                    align="right"
                    sortable
                    prop="pnl"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <MoneyDisplay :value="row.pnl || 0" size="sm" />
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="盈亏率"
                    width="100"
                    align="right"
                    sortable
                    prop="pnl_rate"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <MoneyDisplay
                        :value="row.pnl_rate || 0"
                        :precision="2"
                        :show-currency="false"
                        suffix="%"
                        size="sm"
                      />
                    </template>
                  </el-table-column>

                  <!-- 持有时长（#862）：后端按 confirm_date 计算返回 holding_days；无确认日显示 -- ；
                       口径为「本轮」：自本轮建仓日起算，清仓后重新计起，不累计历史（见 docs/working-notes/holding-days-semantics-2026-09-02.md） -->
                  <el-table-column
                    label="持有时长"
                    width="110"
                    align="right"
                    sortable
                    prop="holding_days"
                    show-overflow-tooltip
                  >
                    <template #header>
                      <el-tooltip
                        content="自本轮建仓日起算；清仓后重新计起，不累计历史持仓"
                        placement="top"
                      >
                        <span>持有时长(本轮)</span>
                      </el-tooltip>
                    </template>
                    <template #default="{ row }">
                      <span v-if="row.holding_days != null"
                        >{{ row.holding_days }} 天</span
                      >
                      <span v-else>--</span>
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="配置目标"
                    width="90"
                    align="right"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <span
                        class="px-2 py-0.5 rounded-full text-xs"
                        :style="{ color: getAllocColor(row.allocation) }"
                      >
                        {{ row.allocation_label }}
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column
                    v-if="!isUnclassified"
                    label="操作"
                    width="130"
                    fixed="right"
                  >
                    <template #default="{ row }">
                      <div
                        class="flex items-center gap-1"
                        style="white-space: nowrap"
                      >
                        <el-button
                          text
                          size="small"
                          @click.stop="
                            migrateDialogRef?.openMigrateDialog(
                              row as LedgerHoldingRow
                            )
                          "
                          >迁移</el-button
                        >
                        <el-button
                          text
                          size="small"
                          type="danger"
                          @click.stop="
                            confirmDeletePosition(row as LedgerHoldingRow)
                          "
                          >删除</el-button
                        >
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column
                    v-if="isUnclassified"
                    label="归入账户"
                    width="160"
                  >
                    <template #default="{ row }">
                      <el-select
                        v-model="assignMap[row.id]"
                        placeholder="选择账户"
                        size="small"
                        @change="handleAssign(row.id)"
                      >
                        <el-option
                          v-for="ledger in ledgers"
                          :key="ledger.id"
                          :label="ledger.name"
                          :value="ledger.id"
                        />
                      </el-select>
                    </template>
                  </el-table-column>
                </el-table>

                <div class="flex justify-end mt-4">
                  <el-pagination
                    v-model:current-page="holdingsPage"
                    :page-size="holdingsPageSize"
                    layout="prev, pager, next"
                    :total="holdingsTotal"
                    small
                    @current-change="loadHoldings"
                  />
                </div>
              </el-tab-pane>

              <!-- 交易记录 Tab -->
              <el-tab-pane label="交易记录" name="transactions">
                <el-table
                  :data="transactionsList"
                  stripe
                  size="default"
                  :default-sort="{ prop: 'confirm_date', order: 'descending' }"
                >
                  <el-table-column
                    prop="confirm_date"
                    label="日期"
                    width="110"
                    sortable
                  >
                    <template #default="{ row }">{{
                      formatDate(row.confirm_date)
                    }}</template>
                  </el-table-column>
                  <!-- 资产列宽统一 160（产品信息列宽度规范，见 docs/design/components.md） -->
                  <el-table-column
                    label="资产名称"
                    min-width="160"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <span class="txn-asset-name">{{
                        row.position_name
                      }}</span>
                      <span v-if="row.symbol" class="txn-asset-code">{{
                        row.symbol
                      }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="类型" width="80">
                    <template #default="{ row }">
                      <span :class="getTxnTypeClass(row.txn_type)">{{
                        txnTypeLabel(row.txn_type)
                      }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="价格" width="100" align="right">
                    <template #default="{ row }">
                      <MoneyDisplay
                        :value="row.price || 0"
                        :precision="pricePrecision(row.asset_type)"
                        :show-sign="false"
                        :show-currency="false"
                        size="sm"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column label="数量" width="80" align="right">
                    <template #default="{ row }">{{ row.quantity }}</template>
                  </el-table-column>
                  <el-table-column
                    label="金额"
                    width="120"
                    align="right"
                    sortable
                    prop="amount"
                  >
                    <template #default="{ row }">
                      <MoneyDisplay
                        :value="row.amount || 0"
                        :show-sign="false"
                        :auto-color="false"
                        size="sm"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column
                    label="手续费"
                    width="80"
                    align="right"
                    prop="fee"
                  >
                    <template #default="{ row }">
                      <MoneyDisplay
                        :value="row.fee || 0"
                        :show-sign="false"
                        :auto-color="false"
                        size="sm"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column
                    v-if="!isUnclassified"
                    label="操作"
                    width="140"
                    fixed="right"
                  >
                    <template #default="{ row }">
                      <div
                        class="flex items-center gap-1"
                        style="white-space: nowrap"
                      >
                        <el-button
                          text
                          size="small"
                          @click.stop="openEditTxnDialog(row as LedgerTxnRow)"
                          >编辑</el-button
                        >
                        <el-button
                          text
                          size="small"
                          type="danger"
                          @click.stop="confirmDeleteTxn(row as LedgerTxnRow)"
                          >删除</el-button
                        >
                      </div>
                    </template>
                  </el-table-column>
                </el-table>
                <div
                  v-if="transactionsTotal === 0"
                  class="text-center py-8"
                  :style="{ color: 'var(--text-tertiary)' }"
                >
                  暂无交易记录
                </div>
                <div v-if="transactionsTotal > 0" class="flex justify-end mt-4">
                  <el-pagination
                    v-model:current-page="transactionsPage"
                    :page-size="transactionsPageSize"
                    layout="prev, pager, next"
                    :total="transactionsTotal"
                    small
                    @current-change="loadTransactions"
                  />
                </div>
              </el-tab-pane>
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
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { Search } from "@element-plus/icons-vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import AssetAllocationDonut from "@/components/Charts/AssetAllocationDonut.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import DeleteLedgerDialog from "./components/DeleteLedgerDialog.vue";
import { txnTypeLabel } from "@/constants";
import PositionTransactionsDrawer from "./components/PositionTransactionsDrawer.vue";
import TransactionEditDialog from "./components/TransactionEditDialog.vue";
import EditAccountDialog from "./components/EditAccountDialog.vue";
import MigrateDialog from "./components/MigrateDialog.vue";
import MigrationResolvePanel from "./components/MigrationResolvePanel.vue";
import { formatDate } from "@/utils/date";
import { pricePrecision } from "@/utils/pricePrecision";
import { useLedgerDetail } from "@/composables/useLedgerDetail";
import {
  getLedgerConsistency,
  type LedgerConsistencyItem
} from "@/api/reconciliation";
import { useLedgerTransactions } from "@/composables/useLedgerTransactions";
import { usePositionMigration } from "@/composables/usePositionMigration";
import type { LedgerHoldingRow } from "@/composables/useLedgerDetail";
import type { LedgerTxnRow } from "@/composables/useLedgerTransactions";

defineOptions({ name: "LedgerDetail" });

const router = useRouter();

const detail = useLedgerDetail();
const txns = useLedgerTransactions(detail);
const migration = usePositionMigration(detail);

const {
  ledgerId,
  isUnclassified,
  loading,
  showSkeleton,
  ledgers,
  portfolioList,
  salesInstitutions,
  assignMap,
  deleteDialogVisible,
  deletingAccount,
  showEditDialog,
  drawerVisible,
  selectedPosition,
  summaryData,
  moneyFundData,
  isCompositionLedger,
  compositionData,
  compositionColorMap,
  accountInfo,
  accountName,
  subTitle,
  getAllocColor,
  cashLedgers,
  sameTypeLedgers,
  activeTab,
  activeSearch,
  onSearchInput,
  holdingsPage,
  holdingsPageSize,
  holdingsList,
  holdingsTotal,
  loadHoldings,
  openPositionDrawer,
  openEditDialog,
  toggleArchiveDetail,
  confirmDeletePosition,
  openDeleteDialog,
  onAccountUpdated,
  onMigrationCommitted,
  onTabChange,
  migrateDialogRef,
  migrationPanelRef
} = detail;

const {
  transactionsList,
  transactionsTotal,
  transactionsPage,
  transactionsPageSize,
  loadTransactions,
  editTxnDialogVisible,
  editingTxn,
  onTxnSaved,
  openEditTxnDialog,
  confirmDeleteTxn,
  getTxnTypeClass
} = txns;

const { handleAssign } = migration;

// ── 温柔提醒（#1133 §4）：账户持仓快照一致性，中性、非阻断 ──
const consistencyItems = ref<LedgerConsistencyItem[]>([]);
const DISMISS_KEY = "fundmate:soft-recon-dismiss";
function loadDismissed(): Set<string> {
  try {
    const raw = localStorage.getItem(DISMISS_KEY);
    if (raw) {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr)) return new Set(arr as string[]);
    }
  } catch {
    /* 忽略损坏的本地存储 */
  }
  return new Set();
}
function saveDismissed(set: Set<string>) {
  try {
    localStorage.setItem(DISMISS_KEY, JSON.stringify([...set]));
  } catch {
    /* 忽略写入失败（隐私模式等） */
  }
}
const dismissedKeys = ref<Set<string>>(loadDismissed());

const visibleConsistencyItems = computed(() =>
  consistencyItems.value
    .filter(
      it => it.ledger_id != null && String(it.ledger_id) === ledgerId.value
    )
    .filter(
      it =>
        !dismissedKeys.value.has(
          `${it.ledger_id}:${it.symbol}:${it.snapshot_date}`
        )
    )
);

async function loadConsistency() {
  try {
    const res = await getLedgerConsistency(
      ledgerId.value ? Number(ledgerId.value) : undefined
    );
    consistencyItems.value = res.data?.items ?? [];
  } catch {
    consistencyItems.value = [];
  }
}
function dismissAllConsistency() {
  const next = new Set(dismissedKeys.value);
  for (const it of visibleConsistencyItems.value) {
    next.add(`${it.ledger_id}:${it.symbol}:${it.snapshot_date}`);
  }
  dismissedKeys.value = next;
  saveDismissed(next);
}
function goReconcile() {
  router.push({ name: "ReconcileWorkbench" });
}

onMounted(() => {
  loadConsistency();
});
</script>

<style scoped>
/* 交易表资产名称列：名称 + 代码 */
.txn-asset-name {
  color: var(--text-primary);
}

.txn-asset-code {
  margin-left: 6px;
  font-size: 12px;
  color: var(--text-tertiary);
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

/* ===== 批量迁移决议面板（§7）：三区呈现 + conflict 行内联决议 ===== */

/* 概要：来源 → 目标 路由与总数 */
.mig-summary {
  margin-bottom: var(--space-3);
}

.mig-route {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.mig-route__name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.mig-route__arrow {
  font-size: 14px;
  color: var(--text-tertiary);
}

/* 总数右对齐：等宽数字保证跳动时不抖 */
.mig-route__total {
  margin-left: auto;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.mig-note {
  margin-top: var(--space-1);
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 长列表限高滚动：底栏（状态 + 确认按钮）始终可见 */
.mig-body {
  max-height: 56vh;
  padding-right: 2px;
  overflow-y: auto;
}

.mig-section {
  margin-bottom: var(--space-3);
}

.mig-section__head {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--border-subtle);
}

.mig-section__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.mig-section__count {
  padding: 0 8px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  line-height: 20px;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.mig-section__hint {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* keep / duplicate 行：名称居左、数值摘要居右 */
.mig-rows {
  padding: 0;
  margin: var(--space-2) 0 0;
  list-style: none;
}

.mig-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  min-height: 32px;
}

.mig-row + .mig-row {
  border-top: 1px dashed var(--border-light);
}

.mig-row__name {
  font-size: 13px;
  color: var(--text-primary);
}

.mig-row__symbol,
.mig-conflict__symbol {
  margin-left: 6px;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: normal;
  color: var(--text-tertiary);
}

.mig-row__values {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  text-align: right;
}

/* conflict 卡片：头部 + 对比表 + 内联决议 */
.mig-conflict {
  padding: var(--space-3);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.mig-conflict + .mig-conflict {
  margin-top: var(--space-2);
}

.mig-conflict__head {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}

.mig-conflict__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.mig-conflict__fields {
  font-size: 12px;
  color: var(--text-secondary);
}

/* 温柔提醒 banner（#1133 §4）：中性信息色，非涨跌色 / 非危险红；轻量、不制造心理压力 */
.soft-reconcile-banner {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-4);
  background: var(--bg-soft);
  border: 1px solid var(--border-subtle);
  border-left: 3px solid var(--el-color-info);
  border-radius: var(--radius-md);
}
.soft-reconcile-banner__icon {
  color: var(--el-color-info);
  font-size: 18px;
  margin-top: 2px;
  flex: none;
}
.soft-reconcile-banner__body {
  flex: 1;
  min-width: 0;
}
.soft-reconcile-banner__title {
  margin: 0;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-primary);
}
.soft-reconcile-banner__detail {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}
.soft-reconcile-banner__actions {
  display: flex;
  gap: 8px;
  flex: none;
  align-items: center;
}

/* 源/目标并排对比：标签列 + 双值列；警示底色只落在数值单元格上，
   文字保持 --text-primary 保证 WCAG 对比度（--color-warning 直接做小字文字色不达标） */
.mig-compare {
  display: grid;
  grid-template-columns: 72px 1fr 1fr;
  overflow: hidden;
  background: var(--bg-warm);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
}

.mig-compare > span {
  padding: 6px 10px;
  font-size: 13px;
  line-height: 20px;
  border-top: 1px solid var(--border-subtle);
}

.mig-compare > span:nth-child(-n + 3) {
  border-top: none;
}

.mig-compare__tag {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-soft);
}

.mig-compare__label {
  font-size: 12px;
  color: var(--text-tertiary);
  background: var(--bg-soft);
}

.mig-compare__value {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 差异字段高亮：警示色 20% 底 + 左侧警示色细条，亮暗色均由语义变量驱动 */
.mig-compare__value.is-diff {
  font-weight: 600;
  background: var(--color-warning-20);
  box-shadow: inset 2px 0 0 var(--color-warning);
}

/* 决议区：单选 + 当前选中态说明文案 */
.mig-decide {
  margin-top: var(--space-2);
}

.mig-action-note {
  margin: 4px 0 0;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
}

.mig-empty {
  padding: var(--space-loose) 0;
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: center;
}

/* 底栏：左侧状态文案 + 右侧操作按钮 */
.mig-footer {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.mig-footer__status {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ===== 目标账户选择器：机构标注与未绑定提示 ===== */

/* 下拉选项：名称居左、销售机构标注居右 */
.mig-option {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
}

.mig-option__name {
  color: var(--text-primary);
}

.mig-option__inst {
  flex-shrink: 0;
  padding: 0 8px;
  font-size: 12px;
  line-height: 20px;
  color: var(--text-secondary);
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

/* 同机构候选高亮为品牌软色（「优先候补」软按钮语义，允许引用 --brand-*） */
.mig-option__inst.is-same {
  color: var(--brand-700);
  background: var(--brand-100);
}

/* 未绑定销售机构的提示文案 */
.mig-bind-hint {
  margin: var(--space-1) 0 0;
  font-size: 12px;
}
</style>
