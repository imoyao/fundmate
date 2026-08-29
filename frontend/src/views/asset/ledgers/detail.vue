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
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { Search } from "@element-plus/icons-vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import AssetAllocationDonut from "@/components/Charts/AssetAllocationDonut.vue";

import PageSkeleton from "@/components/PageSkeleton/index.vue";
import {
  getLedgers,
  getLedgerSummary,
  getLedgerPositions,
  getLedgerTransactions,
  updateLedgerPosition,
  deleteLedgerPosition,
  archiveLedger,
  unarchiveLedger,
  getSalesInstitutions,
  type LedgerItem,
  type SalesInstitution
} from "@/api/ledger";
import { deleteTransaction } from "@/api/transaction";
import { getPortfolios, type PortfolioItem } from "@/api/portfolio";
import { updateAsset } from "@/api/assets";
import {
  getMoneyFundIncome,
  type MoneyFundIncomeData
} from "@/api/performance";
import DeleteLedgerDialog from "./components/DeleteLedgerDialog.vue";
import { getLedgerTypeLabel, txnTypeLabel } from "@/constants";
import PositionTransactionsDrawer from "./components/PositionTransactionsDrawer.vue";
import TransactionEditDialog from "./components/TransactionEditDialog.vue";
import EditAccountDialog from "./components/EditAccountDialog.vue";
import MigrateDialog from "./components/MigrateDialog.vue";
import MigrationResolvePanel from "./components/MigrationResolvePanel.vue";
import { usePageRefresh } from "@/composables/usePageRefresh";
import { formatDate } from "@/utils/date";
import { pricePrecision } from "@/utils/pricePrecision";

defineOptions({ name: "LedgerDetail" });

// ---- 类型定义（以接口实际返回为准） ----

/** 账户概览（GET /api/ledgers/{id}/summary/） */
interface LedgerSummaryData {
  ledger_id?: number;
  ledger_name?: string;
  ledger_type?: string;
  portfolio_name?: string | null;
  total_market_value?: number;
  position_pnl?: number;
  position_count?: number;
  cash_balance?: number | null;
  /** 类现金合计（#1137）：货基 + 逆回购 + 账户现金，口径同 XIRR EXCLUDED_ASSET_TYPES */
  cash_like_amount?: number;
  /** 中高风险投资资产 = 总市值 - 类现金（#1137） */
  investment_amount?: number;
  /** 类现金明细：货基市值 */
  money_fund_amount?: number;
  /** 类现金明细：账户现金 */
  cash_amount?: number;
  linked_liability?: number;
  type_distribution?: Record<string, number>;
}

/** 持仓行（GET /api/ledgers/{id}/positions/ 分页 items） */
interface LedgerHoldingRow {
  id: number;
  symbol?: string;
  name?: string | null;
  asset_type?: string;
  type_label?: string;
  market_value?: number;
  pnl?: number;
  pnl_rate?: number;
  avg_price?: number;
  current_price?: number;
  allocation?: string | null;
  allocation_label?: string;
  quantity?: number;
  account_name?: string;
}

/** 交易行（GET /api/ledgers/{id}/transactions/ 分页 items） */
interface LedgerTxnRow {
  id: number;
  confirm_date?: string | null;
  trade_date?: string | null;
  asset_type?: string | null;
  ledger_id?: number;
  position_name?: string;
  symbol?: string;
  txn_type: string;
  price?: number;
  quantity?: number;
  amount?: number;
  fee?: number;
  notes?: string | null;
}

const route = useRoute();
const router = useRouter();

const ledgerId = computed(() => route.params.id as string);
const isUnclassified = computed(
  () => ledgerId.value === "unclassified" || !!route.query.name
);
const targetAccountName = computed(
  () => route.query.name as string | undefined
);

const loading = ref(true);
// 骨架屏阈值控制：请求 ≤200ms 返回时直接渲染内容、跳过骨架屏，避免"闪屏"（骨架刚出现就消失）
const showSkeleton = ref(false);
let skeletonTimer: ReturnType<typeof setTimeout> | null = null;
const ledgers = ref<LedgerItem[]>([]);
const portfolioList = ref<PortfolioItem[]>([]);
/** 基金销售机构候选（AMAC 名录，编辑账户可选关联） */
const salesInstitutions = ref<SalesInstitution[]>([]);
const assignMap = ref<Record<number, number>>({});
const deleteDialogVisible = ref(false);
const deletingAccount = ref<LedgerItem | null>(null);

const showEditDialog = ref(false);

const drawerVisible = ref(false);
const selectedPosition = ref<LedgerHoldingRow | null>(null);

// 概览数据
const summaryData = ref<LedgerSummaryData | null>(null);

// 货币基金收益（仅基金账户拉取）
const moneyFundData = ref<MoneyFundIncomeData | null>(null);

// 是否展示资产构成（仅股票 / 基金 / 信用账户有投资资产与现金类资产之分）
const isCompositionLedger = computed(() =>
  ["stock", "fund", "e_account"].includes(summaryData.value?.ledger_type ?? "")
);

// 环形图数据：投资资产 vs 现金类资产
const compositionData = computed(() => [
  { name: "投资资产", value: summaryData.value?.investment_amount ?? 0 },
  { name: "现金类资产", value: summaryData.value?.cash_like_amount ?? 0 }
]);

// 环形图配色：走 design.md 图表语义变量（禁止硬编码 hex），对齐家庭资产看板饼图取色（chart-01 起）
const compositionColorMap = {
  投资资产: "--chart-01",
  现金类资产: "--chart-06"
};

async function loadMoneyFundIncome() {
  if (isUnclassified.value) return;
  moneyFundData.value = null;
  try {
    const res = await getMoneyFundIncome({
      scope: "ledger",
      ledger_id: Number(ledgerId.value)
    });
    moneyFundData.value = res.data;
  } catch (e) {
    // 禁止静默吞错：失败保留占位 "--"，仅记日志不打断页面
    console.error("货基收益加载失败", e);
  }
}

// 持仓 Tab 数据
const holdingsPage = ref(1);
const holdingsPageSize = 20;
const holdingsList = ref<LedgerHoldingRow[]>([]);
const holdingsTotal = ref(0);
// 名称/代码搜索（#982）：后端 LIKE 过滤，防抖后重置回第一页
const holdingsSearch = ref("");

// 交易 Tab 数据
const transactionsPage = ref(1);
const transactionsPageSize = 20;
const transactionsList = ref<LedgerTxnRow[]>([]);
const transactionsTotal = ref(0);
const transactionsSearch = ref("");

/** 搜索防抖（300ms）：变更即重置回第一页；输入框按当前 Tab 经 activeSearch 绑定 */
const searchTimers: Record<"holdings" | "transactions", number | undefined> = {
  holdings: undefined,
  transactions: undefined
};

/** 当前激活 Tab 的搜索词代理：一个输入框服务两个列表 */
const activeSearch = computed({
  get: () =>
    activeTab.value === "holdings"
      ? holdingsSearch.value
      : transactionsSearch.value,
  set: (v: string) => {
    if (activeTab.value === "holdings") holdingsSearch.value = v;
    else transactionsSearch.value = v;
  }
});

function onSearchInput() {
  const tab = activeTab.value === "holdings" ? "holdings" : "transactions";
  if (searchTimers[tab]) window.clearTimeout(searchTimers[tab]);
  searchTimers[tab] = window.setTimeout(() => {
    if (tab === "holdings") void loadHoldings(1);
    else void loadTransactions(1);
  }, 300);
}

const activeTab = ref("holdings");

// 交易编辑（复用持仓明细抽屉同款弹窗）
const editTxnDialogVisible = ref(false);
const editingTxn = ref<LedgerTxnRow | null>(null);

// 账户信息
const accountInfo = computed(
  () => ledgers.value.find(l => String(l.id) === ledgerId.value) || null
);
const accountName = computed(() => {
  if (targetAccountName.value) return targetAccountName.value;
  if (isUnclassified.value) return "未归置持仓";
  return (
    accountInfo.value?.name || summaryData.value?.ledger_name || "账户详情"
  );
});

const subTitle = computed(() => {
  if (isUnclassified.value) return "将以下资产关联到已有账户";
  const type = summaryData.value?.ledger_type || accountInfo.value?.ledger_type;
  return getLedgerTypeLabel(type) || "其他";
});

// 五笔钱颜色映射
function getAllocColor(alloc: string | null): string {
  const colorMap: Record<string, string> = {
    liquid: "var(--sankey-liquid)",
    stable: "var(--sankey-stable)",
    longterm: "var(--sankey-longterm)",
    speculative: "var(--sankey-speculative)",
    security: "var(--sankey-security)"
  };
  return colorMap[alloc || ""] || "var(--text-tertiary)";
}

// 关联现金账户列表
const cashLedgers = computed(() =>
  ledgers.value.filter(l => l.ledger_type === "bank")
);
const sameTypeLedgers = computed(() =>
  accountInfo.value
    ? ledgers.value.filter(
        l =>
          l.ledger_type === accountInfo.value!.ledger_type &&
          l.id !== Number(ledgerId.value)
      )
    : []
);

function openPositionDrawer(row: LedgerHoldingRow) {
  selectedPosition.value = row; // 把当前点击的持仓数据传进去
  drawerVisible.value = true; // 打开抽屉
}

async function handleGlobalRefresh() {
  console.log("收到全局记账完成信号，刷新当前页面数据...");
  if (!isUnclassified.value) {
    await loadSummary();
  }
  await loadHoldings();
  // 如果当前用户正在看的是交易记录 Tab，顺便刷新交易记录
  if (activeTab.value === "transactions") {
    await loadTransactions();
  }
}

async function loadSummary() {
  try {
    const res = await getLedgerSummary(Number(ledgerId.value));
    summaryData.value = (res as { data?: LedgerSummaryData })?.data ?? {};
  } catch (e) {
    ElMessage.error("概览加载失败");
  }
}

/** 销售机构候选加载：失败仅记日志，编辑弹窗下拉留空（可选字段不阻塞页面） */
async function loadSalesInstitutions() {
  try {
    const res = await getSalesInstitutions();
    salesInstitutions.value = res?.data ?? [];
  } catch (e) {
    console.error("销售机构名录加载失败", e);
  }
}

// 持仓加载
async function loadHoldings(page = 1) {
  holdingsPage.value = page;
  try {
    const res = await getLedgerPositions(Number(ledgerId.value), {
      page,
      per_page: holdingsPageSize,
      search: holdingsSearch.value.trim() || undefined
    });
    const result = (
      res as { data?: { items?: LedgerHoldingRow[]; total?: number } }
    )?.data;
    holdingsList.value = result?.items ?? [];
    holdingsTotal.value = result?.total ?? 0;
  } catch (e) {
    ElMessage.error("持仓加载失败");
  }
}

// 交易记录加载
async function loadTransactions(page = 1) {
  transactionsPage.value = page;
  try {
    const res = await getLedgerTransactions(Number(ledgerId.value), {
      page,
      per_page: transactionsPageSize,
      search: transactionsSearch.value.trim() || undefined
    });
    const result = (
      res as { data?: { items?: LedgerTxnRow[]; total?: number } }
    )?.data;
    transactionsList.value = result?.items ?? [];
    transactionsTotal.value = result?.total ?? 0;
  } catch (e) {
    ElMessage.error("交易记录加载失败");
  }
}

function onTabChange(tabName: string) {
  if (tabName === "holdings" && holdingsList.value.length === 0) {
    loadHoldings();
  } else if (
    tabName === "transactions" &&
    transactionsList.value.length === 0
  ) {
    loadTransactions();
  }
}

function getTxnTypeClass(type: string) {
  // 涨红跌绿：买入/存入=红（rise），卖出/取出=绿（fall），分红等中性=info
  if (type === "buy" || type === "deposit") return "text-[var(--color-rise)]";
  if (type === "sell" || type === "withdraw") return "text-[var(--color-fall)]";
  return "text-[var(--color-info)]";
}

/** 第一步：调 preview 拉取迁移方案（只读不写库），成功后进入决议面板 */

/** 由决议表组装 commit 入参：持仓按 symbol 三选一，资产按三级分类键二选一 */

/** 第二步：全部 conflict 决议完成后提交（单事务，失败整体回滚） */

async function handleAssign(itemId: number) {
  const targetLedgerId = assignMap.value[itemId];
  if (!targetLedgerId) return;
  const ledger = ledgers.value.find(l => l.id === targetLedgerId);
  if (!ledger) return;
  try {
    if (itemId > 100000) {
      await updateAsset(itemId - 100000, { account_name: ledger.name });
    } else {
      await updateLedgerPosition(Number(ledgerId.value), itemId, {
        account_name: ledger.name
      });
    }
    ElMessage.success(`已归入「${ledger.name}」`);
    loadHoldings();
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "归入失败");
  }
}

// 原有的 openEditDialog
async function openEditDialog() {
  if (!accountInfo.value) return;

  // 🔥 新增：点开编辑弹窗时，才去拉取关联的下拉列表数据
  try {
    // 为了不阻塞用户体验，可以加个 loading
    const [ledgerRes, portfolioRes] = await Promise.all([
      getLedgers(),
      getPortfolios()
    ]);
    ledgers.value = ledgerRes.data ?? [];
    portfolioList.value =
      (portfolioRes as { data?: PortfolioItem[] })?.data ?? [];
  } catch (e) {
    ElMessage.error("加载关联账户或组合列表失败");
    return; // 加载失败不打开弹窗
  }

  // 表单回填与快照由 EditAccountDialog 在 visible 变为 true 时自行处理
  showEditDialog.value = true;
}

/** 详情页归档/激活：归档给一次确认（保留全部数据、仅隐藏） */
async function toggleArchiveDetail(ledger: any) {
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
    // 刷新账户信息（accountInfo 由 ledgers 派生）+ 顶部统计
    const res = await getLedgers(true);
    ledgers.value = res.data ?? [];
    await loadSummary();
    await loadHoldings();
  } catch (e: any) {
    if (e !== "cancel" && e?.action !== "cancel") {
      ElMessage.error(e?.message || "操作失败");
    }
  }
}

async function confirmDeletePosition(row: LedgerHoldingRow) {
  const positionId = row.id;
  try {
    const action = await ElMessageBox.confirm(
      `确定删除持仓「${row.name || row.symbol}」吗？可选择同时删除关联交易记录。`,
      "删除持仓",
      {
        confirmButtonText: "删除持仓及交易",
        cancelButtonText: "仅删除持仓",
        distinguishCancelAndClose: true,
        type: "warning"
      }
    );

    // ✅ 用户点击了【删除持仓及交易】
    await deleteLedgerPosition(Number(ledgerId.value), positionId, true);
    ElMessage.success("持仓及关联交易已删除");

    // 刷新持仓列表
    loadHoldings();
    // 🔥 核心修复：清除交易列表缓存，保证用户切换 Tab 后会自动拉取最新数据
    transactionsList.value = [];
    transactionsTotal.value = 0;
  } catch (action: unknown) {
    // ✅ 用户点击了【仅删除持仓】（ElMessageBox 取消分支返回 "cancel"）
    if (action === "cancel") {
      try {
        await deleteLedgerPosition(Number(ledgerId.value), positionId, false);
        ElMessage.success("持仓已删除，交易记录保留");

        // 刷新持仓列表
        loadHoldings();
        // 🔥 核心修复：虽然保留了交易记录，但交易列表引用的是内存缓存，强制置空以触发刷新
        transactionsList.value = [];
        transactionsTotal.value = 0;
      } catch (e) {
        const err = e as { response?: { data?: { message?: string } } };
        ElMessage.error(err?.response?.data?.message || "删除失败");
      }
    }
  }
}

function openEditTxnDialog(row: LedgerTxnRow) {
  editingTxn.value = { ...row, ledger_id: Number(ledgerId.value) };
  editTxnDialogVisible.value = true;
}

function onTxnSaved() {
  editTxnDialogVisible.value = false;
  loadTransactions(transactionsPage.value);
}

// 只需一行，页面全自动刷新
usePageRefresh(async () => {
  if (!isUnclassified.value) {
    await loadSummary();
    if (summaryData.value?.ledger_type === "fund") await loadMoneyFundIncome();
  }
  await loadHoldings();
  if (activeTab.value === "transactions") await loadTransactions();
});

// 加载优化：概览与持仓并行拉取，减少首屏等待（loading 期间显示骨架屏，见模板）
onMounted(async () => {
  loading.value = true;
  // 阈值控制：200ms 后仍未完成才显示骨架屏；快速请求（<200ms）不显示，避免闪屏
  skeletonTimer = setTimeout(() => {
    showSkeleton.value = true;
  }, 200);
  try {
    // 销售机构候选：编辑弹窗下拉数据源（内部兜底，失败不打断主流程）
    await loadSalesInstitutions();
    if (!isUnclassified.value) {
      await Promise.all([loadSummary(), loadHoldings()]);
      // 货基收益依赖 summary 判定账户类型，故在 summary 就绪后再拉
      if (summaryData.value?.ledger_type === "fund")
        await loadMoneyFundIncome();
      // 修复：首屏填充 ledgers，使 accountInfo 可解析，从而显示右上角操作栏
      // （编辑/归档/删除/对账/批量迁移）。此前仅在点击这些按钮时才拉取，
      // 而按钮本身又在 v-if="accountInfo" 内，形成死锁导致操作栏永不显示。
      // 拉取失败仅影响操作栏可用性，不阻断概览/持仓等主流程，故单独兜底。
      try {
        const ledgerRes = await getLedgers(true);
        ledgers.value = ledgerRes.data ?? [];
      } catch (error) {
        console.error(
          "获取账本列表失败，操作栏暂不可用（其余详情正常）",
          error
        );
      }
    } else {
      await loadHoldings();
    }
  } catch (e) {
    const err = e as { message?: string };
    ElMessage.error(err?.message || "加载失败");
  } finally {
    if (skeletonTimer) {
      clearTimeout(skeletonTimer);
      skeletonTimer = null;
    }
    showSkeleton.value = false;
    loading.value = false;
  }
});

// 🔥 修复：确认删除交易
async function confirmDeleteTxn(row: LedgerTxnRow) {
  // 1. 查找这笔交易对应的持仓对象
  const targetPos = holdingsList.value.find(p => p.symbol === row.symbol);

  // 2. 如果找到了关联持仓，做防呆处理
  if (targetPos) {
    try {
      await ElMessageBox.confirm(
        `确定要删除这笔交易记录吗？<br/><br/>
        <span style="color: var(--color-warning); font-weight: bold;">重要提示</span><br/>
        当前持仓「${targetPos.name || targetPos.symbol}」共持有 ${targetPos.quantity} 份/股。<br/>
        如果删除这笔历史交易，<b style="color: var(--color-danger-system);">该持仓将丢失成本来源，变成“幽灵持仓”</b>。<br/><br/>
        <b>推荐操作：前往「持仓明细」Tab，找到该持仓并点击“删除”，选择“删除持仓及交易”。</b>`,
        "删除交易风险确认",
        {
          confirmButtonText: "我理解风险，只删除交易",
          cancelButtonText: "取消，我去持仓页操作",
          dangerouslyUseHTMLString: true,
          type: "warning"
        }
      );
      // 用户执意只删交易
      await deleteTransaction(row.id);
      ElMessage.warning("交易记录已删除（持仓已变成幽灵数据）");
      loadTransactions(transactionsPage.value);
      loadHoldings(); // 更新持仓成本
    } catch (e: unknown) {
      if (e !== "cancel") {
        const err = e as { response?: { data?: { message?: string } } };
        ElMessage.error(err?.response?.data?.message || "删除失败");
      }
    }
  } else {
    // 3. 如果找不到对应的持仓（说明本来就是个幽灵交易），直接删
    await deleteTransaction(row.id);
    ElMessage.success("孤立交易已删除");
    loadTransactions(transactionsPage.value);
    loadHoldings();
  }
}

function openDeleteDialog(account: LedgerItem) {
  deletingAccount.value = account;
  deleteDialogVisible.value = true;
}

// 编辑账户弹窗（EditAccountDialog）保存成功后：刷新账户列表 / 概览 / 持仓
async function onAccountUpdated() {
  const ledgerRes = await getLedgers();
  ledgers.value = ledgerRes.data ?? [];
  await loadSummary();
  await loadHoldings();
}

// 迁移决议面板（MigrationResolvePanel）提交成功后：清空交易缓存并刷新概览 / 持仓
function onMigrationCommitted() {
  transactionsList.value = [];
  transactionsTotal.value = 0;
  loadSummary();
  loadHoldings();
}

// 子组件命令式打开入口（defineExpose）
const migrateDialogRef = ref<InstanceType<typeof MigrateDialog> | null>(null);
const migrationPanelRef = ref<InstanceType<
  typeof MigrationResolvePanel
> | null>(null);
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
