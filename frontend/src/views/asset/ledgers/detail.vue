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
      <!-- 加载状态 -->
      <div
        v-if="loading"
        class="text-center py-20"
        :style="{ color: 'var(--text-tertiary)' }"
      >
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <p class="mt-2">加载中...</p>
      </div>

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
          <!-- 1. 总资产（采用主色，大号加粗） -->
          <div
            class="bg-white p-4 md:p-5 rounded-xl shadow-sm border border-gray-100 flex flex-col justify-between"
          >
            <div
              class="flex items-center gap-2 text-xs font-medium"
              :style="{ color: 'var(--text-secondary)' }"
            >
              <IconifyIconOffline icon="ep:money" class="text-base" /> 总资产
            </div>
            <div
              class="text-2xl font-bold mt-2"
              :style="{ color: 'var(--color-primary)' }"
            >
              ¥{{ (summaryData?.total_market_value || 0).toLocaleString() }}
            </div>
          </div>

          <!-- 2. 持有盈亏（严格涨红跌绿） -->
          <div
            class="bg-white p-4 md:p-5 rounded-xl shadow-sm border border-gray-100 flex flex-col justify-between"
          >
            <div
              class="flex items-center gap-2 text-xs font-medium"
              :style="{ color: 'var(--text-secondary)' }"
            >
              <IconifyIconOffline icon="ep:trend-charts" class="text-base" />
              持仓盈亏
            </div>
            <div class="mt-2 flex items-baseline gap-2">
              <span
                class="text-xl font-bold"
                :style="{
                  color:
                    (summaryData?.position_pnl || 0) >= 0
                      ? 'var(--color-danger)'
                      : 'var(--color-success)'
                }"
              >
                {{ (summaryData?.position_pnl || 0) >= 0 ? "+" : ""
                }}{{
                  Math.abs(summaryData?.position_pnl || 0).toLocaleString()
                }}
              </span>
            </div>
          </div>

          <!-- 3. 持仓数量 + 资金余额（合并为一个卡片，类似同花顺的“仓位”卡片） -->
          <!-- 3. 持仓数量 + 资金余额（合并为一个卡片，类似同花顺的“仓位”卡片） -->
          <div
            class="bg-white p-4 md:p-5 rounded-xl shadow-sm border border-gray-100 flex flex-col justify-between"
          >
            <div
              class="flex items-center gap-2 text-xs font-medium"
              :style="{ color: 'var(--text-secondary)' }"
            >
              <IconifyIconOffline icon="ep:box" class="text-base" /> 持仓与余额
            </div>
            <div class="mt-2 flex gap-6">
              <div>
                <div class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
                  持仓数量
                </div>
                <div class="text-lg font-bold mt-1">
                  {{ summaryData?.position_count || 0 }} 项
                </div>
              </div>
              <div>
                <div class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
                  资金余额
                </div>
                <div class="text-lg font-bold mt-1">
                  {{
                    summaryData?.cash_balance != null
                      ? "¥" + summaryData.cash_balance.toLocaleString()
                      : "--"
                  }}
                </div>
              </div>
            </div>

            <!-- 🔥 修复：将负债写在这个卡片 div 里面，而不是外面！ -->
            <div
              v-if="
                summaryData?.ledger_type === 'bank' &&
                summaryData?.linked_liability > 0
              "
              class="mt-3 pt-2 border-t border-gray-50 flex justify-between"
            >
              <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }"
                >关联负债</span
              >
              <span
                class="text-xs font-semibold"
                :style="{ color: 'var(--color-danger)' }"
              >
                -¥{{ summaryData.linked_liability.toLocaleString() }}
              </span>
            </div>
          </div>
        </div>

        <!-- 资产配置与盈亏走势双列布局 -->
        <div
          class="grid grid-cols-2 gap-4 mb-6 bg-white p-4 rounded-xl shadow-sm border border-gray-100"
        >
          <!-- 左列：盈亏走势（flex 自动居中，避免大留白） -->
          <div
            class="flex flex-col justify-center border-r border-gray-100 pr-4"
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
              ref="lineChartRef"
              class="flex-1 min-h-[200px] w-full flex items-center justify-center"
            >
              <div class="text-xs text-gray-400 text-center leading-relaxed">
                暂无历史盈亏曲线<br />
                <span class="text-[10px]">(数据依赖 P1-20 定时任务同步)</span>
              </div>
            </div>
          </div>

          <!-- 右列：环形图（强制撑满，让饼图变大） -->
          <div class="flex flex-col justify-center pl-2">
            <div
              class="flex items-center gap-2 mb-3 text-sm font-medium"
              :style="{ color: 'var(--text-secondary)' }"
            >
              <IconifyIconOffline icon="ep:pie-chart" class="text-lg" />
              资产配置分布
            </div>
            <!-- 核心修复：强制高度 100% 或 min-h-[200px]，确保饼图有足够空间展现 -->
            <div
              ref="chartRef"
              class="flex-1 min-h-[200px] w-full overflow-hidden"
            />
            <div
              v-if="holdingsList.length === 0"
              class="text-xs text-center"
              :style="{ color: 'var(--text-tertiary)' }"
            >
              暂无持仓数据
            </div>
          </div>
        </div>
        <!-- Tab 切换 -->
        <el-card shadow="never">
          <el-tabs v-model="activeTab" @tab-change="onTabChange">
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
                  <template #default="{ row }"
                    >¥{{ (row.market_value || 0).toLocaleString() }}</template
                  >
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
                    <span
                      :style="{
                        color:
                          (row.pnl || 0) >= 0
                            ? 'var(--color-danger)'
                            : 'var(--color-success)'
                      }"
                    >
                      {{ (row.pnl || 0) >= 0 ? "+" : "" }}¥{{
                        Math.abs(row.pnl || 0).toLocaleString()
                      }}
                    </span>
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
                    <span
                      :style="{
                        color:
                          (row.pnl_rate || 0) >= 0
                            ? 'var(--color-danger)'
                            : 'var(--color-success)'
                      }"
                    >
                      {{ (row.pnl_rate || 0) >= 0 ? "+" : ""
                      }}{{ (row.pnl_rate || 0).toFixed(2) }}%
                    </span>
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
                        @click.stop="openMigrateDialog(row)"
                        >迁移</el-button
                      >
                      <el-button
                        text
                        size="small"
                        type="danger"
                        @click.stop="confirmDeletePosition(row)"
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
                    row.confirm_date?.slice(0, 10)
                  }}</template>
                </el-table-column>
                <el-table-column
                  prop="position_name"
                  label="资产名称"
                  min-width="140"
                />
                <el-table-column label="类型" width="80">
                  <template #default="{ row }">
                    <span :class="getTxnTypeClass(row.txn_type)">{{
                      txnTypeLabel(row.txn_type)
                    }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="价格" width="100" align="right">
                  <template #default="{ row }"
                    >¥{{ (row.price || 0).toLocaleString() }}</template
                  >
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
                  <template #default="{ row }"
                    >¥{{ (row.amount || 0).toLocaleString() }}</template
                  >
                </el-table-column>
                <el-table-column
                  label="手续费"
                  width="80"
                  align="right"
                  prop="fee"
                >
                  <template #default="{ row }"
                    >¥{{ (row.fee || 0).toLocaleString() }}</template
                  >
                </el-table-column>
                <el-table-column
                  v-if="!isUnclassified"
                  label="操作"
                  width="100"
                  fixed="right"
                >
                  <template #default="{ row }">
                    <div class="flex items-center gap-1">
                      <el-button
                        text
                        size="small"
                        @click.stop="openEditTxnDialog(row)"
                        >编辑</el-button
                      >
                      <el-button
                        text
                        size="small"
                        type="danger"
                        @click.stop="confirmDeleteTxn(row)"
                        >删除</el-button
                      >
                    </div>
                  </template>
                </el-table-column>
              </el-table>
              <div
                v-if="transactionsTotal === 0"
                class="text-center py-8 text-gray-400"
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
            :cash-ledgers="cashLedgers"
            :portfolio-list="portfolioList"
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
import {
  ref,
  computed,
  onMounted,
  nextTick,
  watch,
  onBeforeUnmount
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { Loading } from "@element-plus/icons-vue";
// 新增 ECharts 图表
import echarts from "@/plugins/echarts";
import { IconifyIconOffline } from "@/components/ReIcon";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
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
  deleteLedgerTransaction
} from "@/api/ledger";
import { getPortfolios } from "@/api/portfolio";
import { updateAsset } from "@/api/assets";
import AccountFormFields from "./components/AccountFormFields.vue";
import DeleteLedgerDialog from "./components/DeleteLedgerDialog.vue";
import { getLedgerTypeLabel, ALLOCATION_OPTIONS } from "@/constants";
import PositionTransactionsDrawer from "./components/PositionTransactionsDrawer.vue";
import { usePageRefresh } from "@/composables/usePageRefresh";

defineOptions({ name: "LedgerDetail" });

const route = useRoute();
const router = useRouter();

let resizeTimer: number | null = null;
const ledgerId = computed(() => route.params.id as string);
const isUnclassified = computed(
  () => ledgerId.value === "unclassified" || !!route.query.name
);
const targetAccountName = computed(
  () => route.query.name as string | undefined
);

const loading = ref(true);
const ledgers = ref<any[]>([]);
const portfolioList = ref<any[]>([]);
const assignMap = ref<Record<number, number>>({});
const deleteDialogVisible = ref(false);
const deletingAccount = ref<any>(null);
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
  fee_config: null as any
});

const drawerVisible = ref(false);
const selectedPosition = ref<any>(null);

const migrateDialogVisible = ref(false);
const migratingItem = ref<any>(null);
const migrateTargetLedgerId = ref<number | null>(null);

// 概览数据
const summaryData = ref<any>(null);

// 持仓 Tab 数据
const holdingsPage = ref(1);
const holdingsPageSize = 20;
const holdingsList = ref<any[]>([]);
const holdingsTotal = ref(0);

// 交易 Tab 数据
const transactionsPage = ref(1);
const transactionsPageSize = 20;
const transactionsList = ref<any[]>([]);
const transactionsTotal = ref(0);

const activeTab = ref("holdings");

// 交易编辑
const editTxnDialogVisible = ref(false);
const editTxnForm = ref({ id: 0, fee: 0, notes: "" });

// 图表容器
const chartRef = ref<HTMLElement>();
let chartInstance: echarts.ECharts | null = null;

// 账户信息
const accountInfo = computed(
  () => ledgers.value.find((l: any) => String(l.id) === ledgerId.value) || null
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
  ledgers.value.filter((l: any) => l.ledger_type === "bank")
);
const sameTypeLedgers = computed(() =>
  accountInfo.value
    ? ledgers.value.filter(
        (l: any) =>
          l.ledger_type === accountInfo.value!.ledger_type &&
          l.id !== Number(ledgerId.value)
      )
    : []
);

function openPositionDrawer(row: any) {
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
    summaryData.value = (res as any)?.data ?? {};
  } catch (e: any) {
    ElMessage.error("概览加载失败");
  }
}

// 持仓加载
async function loadHoldings(page = 1) {
  holdingsPage.value = page;
  try {
    const res = await getLedgerPositions(Number(ledgerId.value), {
      page,
      per_page: holdingsPageSize
    });
    const result = (res as any)?.data;
    holdingsList.value = result?.items ?? [];
    holdingsTotal.value = result?.total ?? 0;
    // 🔥 移除原本的 nextTick，用 watch 替代
  } catch (e: any) {
    ElMessage.error("持仓加载失败");
  }
}

// 在 script setup 底部追加以下变量
const trendPeriod = ref("day");
const lineChartRef = ref<HTMLElement>();
let lineChartInstance: echarts.ECharts | null = null;

// 渲染 ECharts 环形图（基于当前持仓数据前端聚合）
// 极强诊断：读取 CSS 变量并打印到控制台
const getCSSColor = (varName: string, fallback: string) => {
  if (typeof window === "undefined") return fallback;
  const val = getComputedStyle(document.documentElement)
    .getPropertyValue(varName)
    .trim();
  console.log(
    `[ECharts颜色] 读取 ${varName}，结果：`,
    val || `❌ 没读到！使用后备色 ${fallback}`
  );
  return val || fallback;
};

function renderPieChart() {
  if (!chartRef.value) {
    setTimeout(() => renderPieChart(), 100);
    return;
  }
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value);
  }

  const dataMap = new Map<string, number>();
  holdingsList.value.forEach((item: any) => {
    const type = item.type_label || "其他";
    const val = item.market_value || 0;
    dataMap.set(type, (dataMap.get(type) || 0) + val);
  });
  const pieData = Array.from(dataMap.entries()).map(([name, value]) => ({
    name,
    value
  }));
  const isDataEmpty = pieData.length === 0;

  // 动态读取 CSS 变量，统一颜色来源
  const style = getComputedStyle(document.documentElement);
  const getColor = (varName: string, fallback: string) =>
    style.getPropertyValue(varName).trim() || fallback;

  const colorMap: Record<string, string> = {
    股票: getColor("--invest-stock", "#9D81A9"),
    基金: getColor("--invest-fund", "#A3B5C7"),
    ETF: getColor("--invest-etf", "#B5C4B1"),
    可转债: getColor("--invest-bond", "#8E8B82"),
    虚拟货币: getColor("--invest-crypto", "#C4A0A8"),
    其他: getColor("--color-neutral", "#8E8B82")
  };

  const option = {
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    legend: { show: false },
    series: [
      {
        type: "pie",
        radius: isDataEmpty ? "50%" : ["45%", "70%"],
        itemStyle: {
          color: (params: any) => colorMap[params.name] || "#8E8B82",
          borderRadius: 6,
          borderColor: "#fff",
          borderWidth: 2
        },
        label: isDataEmpty
          ? {
              show: true,
              position: "center",
              formatter: "暂无配置",
              color: "#999",
              fontSize: 12
            }
          : { show: false },
        labelLine: { show: !isDataEmpty },
        data: isDataEmpty ? [{ name: "无数据", value: 1 }] : pieData
      }
    ]
  };
  chartInstance.setOption(option, true);
  nextTick(() => chartInstance?.resize());
}

// 2. 初始化折线图占位（待 P1-20 数据就绪后换掉这个占位逻辑）
function initLineChart() {
  // P1-20 未实现前，暂时只渲染占位文字。如果 ECharts 此时没数据，直接取消渲染
  if (!lineChartRef.value) return;

  // 如果未来有了数据，改为 echarts.init(lineChartRef.value) 渲染真实的趋势线
  // 当前只是一个接收占位的空函数，防止控制台报错
}

// 交易记录加载
async function loadTransactions(page = 1) {
  transactionsPage.value = page;
  try {
    const res = await getLedgerTransactions(Number(ledgerId.value), {
      page,
      per_page: transactionsPageSize
    });
    const result = (res as any)?.data;
    transactionsList.value = result?.items ?? [];
    transactionsTotal.value = result?.total ?? 0;
  } catch (e: any) {
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

function txnTypeLabel(type: string) {
  const map: Record<string, string> = {
    buy: "买入",
    sell: "卖出",
    dividend: "分红",
    deposit: "存入",
    withdraw: "取出"
  };
  return map[type] || type;
}
function getTxnTypeClass(type: string) {
  if (type === "buy" || type === "deposit") return "text-[var(--color-danger)]";
  if (type === "sell" || type === "withdraw")
    return "text-[var(--color-success)]";
  return "text-[var(--color-info)]";
}

async function handleMigrate() {
  if (!migrateTargetLedgerId.value || !migratingItem.value) return;
  const ledger = ledgers.value.find(
    (l: any) => l.id === migrateTargetLedgerId.value
  );
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
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "迁移失败");
  }
}

function openMigrateDialog(row: any) {
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
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "迁移失败");
  } finally {
    batchMigrating.value = false;
  }
}

async function handleAssign(itemId: number) {
  const targetLedgerId = assignMap.value[itemId];
  if (!targetLedgerId) return;
  const ledger = ledgers.value.find((l: any) => l.id === targetLedgerId);
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
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "归入失败");
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
    ledgers.value = (ledgerRes as any)?.data ?? [];
    portfolioList.value = (portfolioRes as any)?.data ?? [];
  } catch (e: any) {
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
    fee_config: accountInfo.value.fee_config
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
    ledgers.value = (ledgerRes as any)?.data ?? [];
    await loadSummary();
    await loadHoldings();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "更新失败");
  } finally {
    saving.value = false;
  }
}

async function confirmDeletePosition(row: any) {
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
  } catch (action: any) {
    // ✅ 用户点击了【仅删除持仓】
    if (action === "cancel") {
      try {
        await deleteLedgerPosition(Number(ledgerId.value), positionId, false);
        ElMessage.success("持仓已删除，交易记录保留");

        // 刷新持仓列表
        loadHoldings();
        // 🔥 核心修复：虽然保留了交易记录，但交易列表引用的是内存缓存，强制置空以触发刷新
        transactionsList.value = [];
        transactionsTotal.value = 0;
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.message || "删除失败");
      }
    }
  }
}

function openEditTxnDialog(row: any) {
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
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "更新失败");
  }
}

// 窗口改变时重绘图表（防抖）
const handleWindowResize = () => {
  if (resizeTimer) clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(() => {
    chartInstance?.resize();
    lineChartInstance?.resize();
    resizeTimer = null;
  }, 200);
};

// 只需一行，页面全自动刷新
usePageRefresh(async () => {
  if (!isUnclassified.value) await loadSummary();
  await loadHoldings();
  if (activeTab.value === "transactions") await loadTransactions();
});

// 在 onMounted 中加入监听：
onMounted(async () => {
  window.addEventListener("resize", handleWindowResize);
  loading.value = true;
  try {
    if (!isUnclassified.value) {
      await loadSummary();
    }
    await loadHoldings();
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
  }
});

// 在 onBeforeUnmount 中移除监听
onBeforeUnmount(() => {
  window.removeEventListener("resize", handleWindowResize);
  chartInstance?.dispose();
  lineChartInstance?.dispose();
});

// 🔥 修复：确认删除交易
async function confirmDeleteTxn(row: any) {
  // 1. 查找这笔交易对应的持仓对象
  const targetPos = holdingsList.value.find(p => p.symbol === row.symbol);

  // 2. 如果找到了关联持仓，做防呆处理
  if (targetPos) {
    try {
      await ElMessageBox.confirm(
        `确定要删除这笔交易记录吗？<br/><br/>
        <span style="color: var(--color-warning); font-weight: bold;">⚠️ 重要提示</span><br/>
        当前持仓「${targetPos.name || targetPos.symbol}」共持有 ${targetPos.quantity} 份/股。<br/>
        如果删除这笔历史交易，<b style="color: var(--color-danger);">该持仓将丢失成本来源，变成“幽灵持仓”</b>。<br/><br/>
        <b>✅ 推荐操作：前往「持仓明细」Tab，找到该持仓并点击“删除”，选择“删除持仓及交易”。</b>`,
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
    } catch (e: any) {
      if (e !== "cancel") {
        ElMessage.error(e?.response?.data?.message || "删除失败");
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

function openDeleteDialog(account: any) {
  deletingAccount.value = account;
  deleteDialogVisible.value = true;
}

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleWindowResize);
  chartInstance?.dispose();
  lineChartInstance?.dispose();
});

// 替换为：
watch(chartRef, newVal => {
  if (newVal) {
    // DOM 挂载好了，渲染图表
    nextTick(() => renderPieChart());
  }
});

// 同时，当数据变化时，也要重新渲染
watch(holdingsList, () => {
  if (chartRef.value) {
    nextTick(() => renderPieChart());
  }
});
</script>

<style scoped>
.product-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.3;
}
.product-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}
.product-code-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.product-code {
  font-size: 12px;
  color: var(--text-tertiary);
}
.type-tag-inline {
  font-size: 11px;
  padding: 0 6px;
  height: 20px;
  line-height: 20px;
  border: none;
  color: #fff;
  background-color: var(--bg-page);
}
</style>
