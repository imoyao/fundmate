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
        <el-button
          v-if="!isUnclassified && holdingsTotal > 0"
          @click="openBatchMigrateDialog"
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

        <!-- 核心概览卡片矩阵（2行 × 3列，或自适应） -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <!-- 1. 总资产 -->
          <div class="summary-card">
            <div class="summary-card__label">
              <IconifyIconOffline icon="ep:money" class="text-base" /> 总资产
            </div>
            <div class="summary-card__value">
              <MoneyDisplay
                :value="summaryData?.total_market_value || 0"
                :show-sign="false"
                :auto-color="false"
                size="lg"
              />
            </div>
          </div>

          <!-- 2. 持有盈亏（严格涨红跌绿） -->
          <div class="summary-card">
            <div class="summary-card__label">
              <IconifyIconOffline icon="ep:trend-charts" class="text-base" />
              持仓盈亏
            </div>
            <div class="summary-card__value">
              <MoneyDisplay :value="summaryData?.position_pnl || 0" size="lg" />
            </div>
          </div>

          <!-- 3. 持仓数量 + 资金余额（合并为一个卡片） -->
          <div class="summary-card">
            <div class="summary-card__label">
              <IconifyIconOffline icon="ep:box" class="text-base" /> 持仓与余额
            </div>
            <div class="mt-2 flex gap-6">
              <div>
                <div class="summary-card__sub-label">持仓数量</div>
                <div class="summary-card__sub-value">
                  {{ summaryData?.position_count || 0 }} 项
                </div>
              </div>
              <div>
                <div class="summary-card__sub-label">资金余额</div>
                <div class="summary-card__sub-value">
                  <MoneyDisplay
                    v-if="summaryData?.cash_balance != null"
                    :value="summaryData.cash_balance"
                    :show-sign="false"
                    :auto-color="false"
                  />
                  <template v-else>--</template>
                </div>
              </div>
            </div>

            <!-- 关联负债（仅银行账户且有负债时展示） -->
            <div
              v-if="
                summaryData?.ledger_type === 'bank' &&
                summaryData?.linked_liability > 0
              "
              class="summary-card__divider flex justify-between"
            >
              <span class="summary-card__sub-label">关联负债</span>
              <span
                class="text-xs font-semibold"
                :style="{ color: 'var(--color-danger-system)' }"
              >
                <MoneyDisplay
                  :value="-summaryData.linked_liability"
                  :auto-color="false"
                  size="xs"
                />
              </span>
            </div>

            <!-- 货币基金收益（仅基金账户展示，后端 summary 对该类型输出 money_fund_stats） -->
            <div
              v-if="summaryData?.ledger_type === 'fund'"
              class="summary-card__divider"
            >
              <div class="flex justify-between items-center">
                <span class="summary-card__sub-label">货基今日收益</span>
                <MoneyDisplay
                  v-if="moneyFundData"
                  :value="moneyFundData.today_income"
                  size="sm"
                />
                <span v-else class="summary-card__sub-label">--</span>
              </div>
              <div class="flex justify-between items-center mt-1">
                <span class="summary-card__sub-label">货基累计收益</span>
                <MoneyDisplay
                  v-if="moneyFundData"
                  :value="moneyFundData.total_income"
                  size="sm"
                />
                <span v-else class="summary-card__sub-label">--</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 资产配置与盈亏走势双列布局 -->
        <CardBlock class="mb-6">
          <div class="grid grid-cols-2 gap-4">
            <!-- 左列：盈亏走势（flex 自动居中，避免大留白） -->
            <div
              class="flex flex-col justify-center border-r pr-4"
              :style="{ borderColor: 'var(--border-subtle)' }"
            >
              <div class="flex justify-between items-center mb-3">
                <div
                  class="flex items-center gap-2 text-sm font-medium"
                  :style="{ color: 'var(--text-secondary)' }"
                >
                  <IconifyIconOffline icon="ep:trend-charts" class="text-lg" />
                  盈亏走势
                </div>
                <el-radio-group
                  v-model="trendPeriod"
                  size="small"
                  @change="initLineChart"
                >
                  <el-radio-button label="day">当日</el-radio-button>
                  <el-radio-button label="month">本月</el-radio-button>
                  <el-radio-button label="year">今年</el-radio-button>
                </el-radio-group>
              </div>
              <!-- 折线图容器：设置 min-height 让占位文字自然居中 -->
              <div
                class="flex-1 min-h-[200px] w-full flex items-center justify-center"
              >
                <div
                  class="text-xs text-center leading-relaxed"
                  :style="{ color: 'var(--text-tertiary)' }"
                >
                  暂无历史盈亏曲线<br />
                  <span class="text-[10px]">(数据依赖 P1-20 定时任务同步)</span>
                </div>
              </div>
            </div>

            <!-- 右列：资产配置分布环形图（共有组件：环形 + 底部图例 + 空态） -->
            <div class="flex flex-col justify-center pl-2">
              <div
                class="flex items-center gap-2 mb-3 text-sm font-medium"
                :style="{ color: 'var(--text-secondary)' }"
              >
                <IconifyIconOffline icon="ep:pie-chart" class="text-lg" />
                资产配置分布
              </div>
              <AssetAllocationDonut
                :data="allocationData"
                :color-map="typeColorMap"
                class="flex-1"
                empty-text="暂无持仓数据"
              />
            </div>
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
                            openMigrateDialog(row as LedgerHoldingRow)
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

      <!-- 弹窗部分保持不变（略去重复代码，保留原有全部Dialog功能） -->
      <el-dialog
        v-model="showEditDialog"
        title="编辑账户"
        width="420px"
        destroy-on-close
      >
        <el-form :model="editForm" label-width="100px">
          <el-form-item label="账户名称" required>
            <el-input v-model="editForm.name" />
          </el-form-item>
          <el-form-item label="配置目标">
            <el-select
              v-model="editForm.default_allocation"
              class="w-full"
              clearable
            >
              <el-option
                v-for="opt in ALLOCATION_OPTIONS"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </el-form-item>
          <AccountFormFields
            v-model:ledger-type="editForm.ledger_type"
            v-model:linked-cash-id="editForm.linked_cash_ledger_id"
            v-model:portfolio-id="editForm.portfolio_id"
            v-model:fee-config="editForm.fee_config"
            v-model:sales-institution-id="editForm.sales_institution_id"
            :cash-ledgers="cashLedgers"
            :portfolio-list="portfolioList"
            :sales-institutions="salesInstitutions"
          />
          <el-form-item label="备注">
            <el-input v-model="editForm.notes" type="textarea" :rows="2" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showEditDialog = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="handleUpdate"
            >保存</el-button
          >
        </template>
      </el-dialog>

      <el-dialog
        v-model="migrateDialogVisible"
        title="迁移资产到其他账户"
        width="400px"
        destroy-on-close
      >
        <el-form label-width="80px">
          <el-form-item label="资产名称"
            ><span>{{
              migratingItem?.name || migratingItem?.symbol
            }}</span></el-form-item
          >
          <el-form-item label="目标账户">
            <el-select
              v-model="migrateTargetLedgerId"
              placeholder="选择同类型账户"
              class="w-full"
            >
              <el-option
                v-for="ledger in sameTypeLedgers"
                :key="ledger.id"
                :label="ledger.name"
                :value="ledger.id"
              />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="migrateDialogVisible = false">取消</el-button>
          <el-button
            type="primary"
            :disabled="!migrateTargetLedgerId"
            @click="handleMigrate"
            >确认迁移</el-button
          >
        </template>
      </el-dialog>

      <el-dialog
        v-model="batchMigrateVisible"
        title="批量迁移持仓"
        width="400px"
        destroy-on-close
      >
        <p class="mb-4" :style="{ color: 'var(--text-secondary)' }">
          将账户「{{ accountName }}」下的所有持仓迁移到目标账户。
        </p>
        <el-form label-width="80px">
          <el-form-item label="目标账户">
            <el-select
              v-model="batchTargetLedgerId"
              class="w-full"
              placeholder="选择同类型账户"
            >
              <el-option
                v-for="ledger in sameTypeLedgers"
                :key="ledger.id"
                :label="ledger.name"
                :value="ledger.id"
                :disabled="ledger.id === Number(ledgerId)"
              />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="batchMigrateVisible = false">取消</el-button>
          <el-button
            type="primary"
            :disabled="!batchTargetLedgerId"
            :loading="batchMigrating"
            @click="handleBatchMigrate"
          >
            确认迁移（{{ holdingsTotal }} 项）
          </el-button>
        </template>
      </el-dialog>

      <el-dialog
        v-model="editTxnDialogVisible"
        title="编辑交易"
        width="380px"
        destroy-on-close
      >
        <el-form :model="editTxnForm" label-width="80px">
          <el-form-item label="手续费"
            ><el-input-number
              v-model="editTxnForm.fee"
              :precision="2"
              :min="0"
              class="w-full"
          /></el-form-item>
          <el-form-item label="备注"
            ><el-input v-model="editTxnForm.notes" type="textarea" :rows="2"
          /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="editTxnDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleUpdateTransaction"
            >保存</el-button
          >
        </template>
      </el-dialog>

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
import { IconifyIconOffline } from "@/components/ReIcon";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import AssetAllocationDonut from "@/components/Charts/AssetAllocationDonut.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import {
  getLedgers,
  updateLedger,
  migrateLedgerPositions,
  getLedgerSummary,
  getLedgerPositions,
  getLedgerTransactions,
  updateLedgerPosition,
  deleteLedgerPosition,
  updateLedgerTransaction,
  deleteLedgerTransaction,
  getSalesInstitutions,
  type LedgerItem,
  type SalesInstitution
} from "@/api/ledger";
import { getPortfolios, type PortfolioItem } from "@/api/portfolio";
import { updateAsset } from "@/api/assets";
import {
  getMoneyFundIncome,
  type MoneyFundIncomeData
} from "@/api/performance";
import AccountFormFields from "./components/AccountFormFields.vue";
import DeleteLedgerDialog from "./components/DeleteLedgerDialog.vue";
import {
  getLedgerTypeLabel,
  ALLOCATION_OPTIONS,
  txnTypeLabel
} from "@/constants";
import PositionTransactionsDrawer from "./components/PositionTransactionsDrawer.vue";
import { usePageRefresh } from "@/composables/usePageRefresh";
import { formatDate } from "@/utils/date";

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
  linked_liability?: number;
  type_distribution?: Record<string, number>;
}

/** 持仓行（GET /api/ledgers/{id}/positions/ 分页 items） */
interface LedgerHoldingRow {
  id: number;
  symbol?: string;
  name?: string | null;
  type_label?: string;
  market_value?: number;
  pnl?: number;
  pnl_rate?: number;
  allocation?: string | null;
  allocation_label?: string;
  quantity?: number;
  account_name?: string;
}

/** 交易行（GET /api/ledgers/{id}/transactions/ 分页 items） */
interface LedgerTxnRow {
  id: number;
  confirm_date?: string | null;
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
const batchMigrateVisible = ref(false);
const batchMigrating = ref(false);
const batchTargetLedgerId = ref<number | null>(null);

const showEditDialog = ref(false);
const saving = ref(false);
const editForm = ref({
  name: "",
  ledger_type: "bank",
  default_allocation: null as string | null,
  notes: "",
  portfolio_id: null as number | null,
  linked_cash_ledger_id: null as number | null,
  fee_config: null as Record<string, unknown> | null,
  sales_institution_id: null as number | null
});

const drawerVisible = ref(false);
const selectedPosition = ref<LedgerHoldingRow | null>(null);

const migrateDialogVisible = ref(false);
const migratingItem = ref<LedgerHoldingRow | null>(null);
const migrateTargetLedgerId = ref<number | null>(null);

// 概览数据
const summaryData = ref<LedgerSummaryData | null>(null);

// 货币基金收益（仅基金账户拉取）
const moneyFundData = ref<MoneyFundIncomeData | null>(null);

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

// 交易编辑
const editTxnDialogVisible = ref(false);
const editTxnForm = ref({ id: 0, fee: 0, notes: "" });

// 折线图周期切换（P1-20 数据就绪前仅占位）
const trendPeriod = ref("day");

// ---------- 资产配置分布（共有组件 AssetAllocationDonut 数据源） ----------
// 类型分类色（CSS 语义变量名，组件内部经 getCssVar 读取）
const typeColorMap: Record<string, string> = {
  股票: "--invest-stock",
  基金: "--invest-fund",
  ETF: "--invest-etf",
  债券: "--invest-bond",
  加密货币: "--invest-crypto",
  其他: "--color-neutral"
};

// 由后端 type_distribution（分类名 -> 金额）转为组件数据（name -> value）
const allocationData = computed(() =>
  Object.entries(summaryData.value?.type_distribution ?? {}).map(
    ([name, value]) => ({ name, value })
  )
);

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
  // 环形图由 AssetAllocationDonut 组件 watch allocationData 自动重绘，无需手动触发
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

/** 折线图占位（待 P1-20 数据就绪后换成真实折线图渲染） */
function initLineChart() {
  // P1-20 未实现前保持占位，空函数防止控制台报错
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

async function handleMigrate() {
  if (!migrateTargetLedgerId.value || !migratingItem.value) return;
  const ledger = ledgers.value.find(l => l.id === migrateTargetLedgerId.value);
  if (!ledger) return;
  try {
    if (migratingItem.value.id > 100000) {
      await updateAsset(migratingItem.value.id - 100000, {
        account_name: ledger.name
      });
    } else {
      await updateLedgerPosition(
        Number(ledgerId.value),
        migratingItem.value.id,
        { account_name: ledger.name }
      );
    }
    ElMessage.success(`已迁移至「${ledger.name}」`);
    migrateDialogVisible.value = false;
    loadHoldings();
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "迁移失败");
  }
}

function openMigrateDialog(row: LedgerHoldingRow) {
  migratingItem.value = row;
  migrateTargetLedgerId.value = null;
  migrateDialogVisible.value = true;
}

function openBatchMigrateDialog() {
  batchTargetLedgerId.value = null;
  batchMigrateVisible.value = true;
}

async function handleBatchMigrate() {
  if (!batchTargetLedgerId.value) return;
  batchMigrating.value = true;
  try {
    await migrateLedgerPositions(
      Number(ledgerId.value),
      batchTargetLedgerId.value
    );
    ElMessage.success("迁移成功");
    batchMigrateVisible.value = false;
    loadHoldings();
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "迁移失败");
  } finally {
    batchMigrating.value = false;
  }
}

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
    ledgers.value = (ledgerRes as { data?: LedgerItem[] })?.data ?? [];
    portfolioList.value =
      (portfolioRes as { data?: PortfolioItem[] })?.data ?? [];
  } catch (e) {
    ElMessage.error("加载关联账户或组合列表失败");
    return; // 加载失败不打开弹窗
  }

  // 构建编辑表单
  editForm.value = {
    name: accountInfo.value.name,
    ledger_type: accountInfo.value.ledger_type || "bank",
    default_allocation: accountInfo.value.default_allocation || null,
    notes: accountInfo.value.notes || "",
    portfolio_id: accountInfo.value.portfolio_id || null,
    linked_cash_ledger_id: accountInfo.value.linked_cash_ledger_id || null,
    fee_config: accountInfo.value.fee_config,
    sales_institution_id: accountInfo.value.sales_institution_id ?? null
  };
  showEditDialog.value = true;
}

async function handleUpdate() {
  if (!editForm.value.name.trim()) {
    ElMessage.warning("名称不能为空");
    return;
  }
  saving.value = true;
  try {
    await updateLedger(Number(ledgerId.value), editForm.value);
    ElMessage.success("账户已更新");
    showEditDialog.value = false;
    const ledgerRes = await getLedgers();
    ledgers.value = (ledgerRes as { data?: LedgerItem[] })?.data ?? [];
    await loadSummary();
    await loadHoldings();
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "更新失败");
  } finally {
    saving.value = false;
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
  editTxnForm.value = { id: row.id, fee: row.fee || 0, notes: row.notes || "" };
  editTxnDialogVisible.value = true;
}

async function handleUpdateTransaction() {
  try {
    await updateLedgerTransaction(
      Number(ledgerId.value),
      editTxnForm.value.id,
      {
        fee: editTxnForm.value.fee,
        notes: editTxnForm.value.notes
      }
    );
    ElMessage.success("交易已更新");
    editTxnDialogVisible.value = false;
    loadTransactions(transactionsPage.value);
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "更新失败");
  }
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
      await deleteLedgerTransaction(Number(ledgerId.value), row.id);
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
    await deleteLedgerTransaction(Number(ledgerId.value), row.id);
    ElMessage.success("孤立交易已删除");
    loadTransactions(transactionsPage.value);
    loadHoldings();
  }
}

function openDeleteDialog(account: LedgerItem) {
  deletingAccount.value = account;
  deleteDialogVisible.value = true;
}
</script>

<style scoped>
/* 概览卡片：token 化（与 CardBlock/MetricCard 同一套卡片语言，仅因需内嵌 MoneyDisplay 故用局部类） */
.summary-card {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: var(--space-compact) var(--space-standard);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
}

.summary-card__label {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.summary-card__value {
  margin-top: var(--space-2);
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
}

.summary-card__sub-label {
  font-size: 12px;
  color: var(--text-tertiary);
}

.summary-card__sub-value {
  margin-top: 4px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.summary-card__divider {
  padding-top: var(--space-2);
  margin-top: var(--space-3);
  border-top: 1px solid var(--border-subtle);
}

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
</style>
