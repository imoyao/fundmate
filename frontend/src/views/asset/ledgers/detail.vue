<template>
  <div>
    <div class="account-detail p-4 md:p-6 min-h-full" :style="{ backgroundColor: 'var(--bg-page)' }">
      <!-- 顶部操作栏 -->
      <div class="mb-4 flex justify-between items-center">
        <el-button text @click="$router.back()">
          <IconifyIconOffline icon="ep:arrow-left" class="mr-1" /> 返回
        </el-button>
        <div v-if="!isUnclassified && accountInfo" class="flex gap-2">
          <el-button @click="openEditDialog">
            <IconifyIconOffline icon="ep:edit" class="mr-1" /> 编辑
          </el-button>

          <el-button @click="openBatchMigrateDialog" v-if="!isUnclassified && holdings.length > 0">
            <IconifyIconOffline icon="ep:share" class="mr-1" /> 批量迁移持仓
          </el-button>

          <div class="flex items-center gap-1">
            <!-- 删除按钮改为打开对话框 -->
            <el-button
              v-if="!isUnclassified && accountInfo"
              type="danger"
              text
              @click="openDeleteDialog(accountInfo)"
            >
              <IconifyIconOffline icon="ep:delete" class="mr-1" /> 删除
            </el-button>
            <IconifyIconOffline icon="ep:arrow-right" :style="{ color: 'var(--text-tertiary)' }" />
          </div>
        </div>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="text-center py-20" :style="{ color: 'var(--text-tertiary)' }">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <p class="mt-2">加载中...</p>
      </div>

      <template v-else>
        <!-- 账户信息头部 -->
        <div class="mb-6">
          <h2 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">{{ accountName }}</h2>
          <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary)' }">
            {{ subTitle }}
            <template v-if="accountInfo?.default_allocation"> · {{ accountInfo.default_allocation_label || '未配置'}}</template>
            <template v-if="accountInfo?.portfolio_name"> · 组合: {{ accountInfo.portfolio_name }}</template>
          </p>
        </div>

        <!-- 汇总卡片 -->
        <el-row :gutter="16" class="mb-6">
          <el-col :span="8">
            <el-card shadow="never">
              <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">{{ totalLabel }}</p>
              <p class="text-xl font-bold" :style="{ color: 'var(--color-primary)' }">¥{{ Math.abs(totalMarketValue).toLocaleString() }}</p>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never">
              <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">持仓数量</p>
              <p class="text-xl font-bold" :style="{ color: 'var(--text-primary)' }">{{ holdings.length }} 项</p>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never">
              <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">五笔钱分布</p>
              <p class="text-xl font-bold" :style="{ color: 'var(--text-primary)' }">{{ allocationSummary }}</p>
            </el-card>
          </el-col>
        </el-row>

        <!-- Tab 切换 -->
        <el-card shadow="never">
          <el-tabs v-model="activeTab">
            <el-tab-pane label="持仓明细" name="holdings">
              <el-table :data="pagedHoldings"
                        stripe
                        @row-click="expandPosition"
                        size="default"
                        :default-sort="{ prop: 'marketValue', order: 'descending' }">
                <el-table-column label="名称 / 代码" min-width="180">
                  <template #default="{ row }">
                    <div class="product-cell">
                      <span class="product-name">{{ row.name || row.symbol || '--' }}</span>
                      <div class="product-code-row">
                        <span class="product-code"># {{ row.symbol || '--' }}</span>
                        <span
                          v-if="row.type_label"
                          class="type-tag-inline ml-2 px-2 py-0.5 rounded-full text-xs"
                          :style="{ backgroundColor: 'var(--bg-page)', color: 'var(--text-secondary)' }"
                        >{{ row.type_label }}</span>
                      </div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="市值" width="130" align="right" sortable prop="marketValue">
                  <template #default="{ row }">¥{{ (row.marketValue || 0).toLocaleString() }}</template>
                </el-table-column>
                <el-table-column label="盈亏" width="120" align="right" sortable prop="pnl">
                  <template #default="{ row }">
                    <span :class="(row.pnl || 0) >= 0 ? 'text-[var(--color-danger)]' : 'text-[var(--color-success)]'">
                      {{ (row.pnl || 0) >= 0 ? '+' : '' }}¥{{ Math.abs(row.pnl || 0).toLocaleString() }}
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="盈亏率" width="90" align="right" sortable prop="pnlRate">
                  <template #default="{ row }">
                    <span :class="(row.pnlRate || 0) >= 0 ? 'text-[var(--color-danger)]' : 'text-[var(--color-success)]'">
                      {{ (row.pnlRate || 0) >= 0 ? '+' : '' }}{{ (row.pnlRate || 0).toFixed(2) }}%
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="配置目标" width="110" align="right">
                  <template #default="{ row }">
                    <span class="px-2 py-0.5 rounded-full text-xs" :style="{ color: getAllocColor(row.allocation) }">
                      {{ row.allocation_label }}
                    </span>
                  </template>
                </el-table-column>

                <el-table-column label="操作" width="80" fixed="right" v-if="!isUnclassified">
                  <template #default="{ row }">
                    <el-button text size="small" @click="openMigrateDialog(row)">迁移</el-button>
                    <el-button text size="small" type="danger" @click="confirmDeletePosition(row)">删除</el-button>
                  </template>
                </el-table-column>

                <el-table-column v-if="isUnclassified" label="归入账户" width="160">
                  <template #default="{ row }">
                    <el-select v-model="assignMap[row.id]" placeholder="选择账户" size="small" @change="handleAssign(row.id)">
                      <el-option v-for="ledger in ledgers" :key="ledger.id" :label="ledger.name" :value="ledger.id" />
                    </el-select>
                  </template>
                </el-table-column>
              </el-table>

              <div v-if="expandedPositionId" class="mt-4 p-4 bg-gray-50 rounded-xl">
                <h4 class="text-sm font-semibold mb-2" :style="{ color: 'var(--text-primary)' }">交易明细</h4>
                <el-table :data="expandedTransactions" stripe size="small">
                  <el-table-column prop="trade_date" label="日期" width="100" />
                  <el-table-column label="类型" width="60">
                    <template #default="{ row }">{{ txnTypeLabel(row.txn_type) }}</template>
                  </el-table-column>
                  <el-table-column label="数量" width="80" align="right">
                    <template #default="{ row }">{{ row.quantity }}</template>
                  </el-table-column>
                  <el-table-column label="价格" width="100" align="right">
                    <template #default="{ row }">¥{{ (row.price || 0).toLocaleString() }}</template>
                  </el-table-column>
                  <el-table-column label="金额" width="100" align="right">
                    <template #default="{ row }">¥{{ (row.amount || 0).toLocaleString() }}</template>
                  </el-table-column>
                </el-table>
              </div>
              <div class="flex justify-end mt-4">
                <el-pagination v-model:current-page="holdingsPage" :page-size="holdingsPageSize" layout="prev, pager, next" :total="holdings.length" small />
              </div>
            </el-tab-pane>

            <el-tab-pane label="交易记录" name="transactions">
              <el-table :data="pagedTransactions" stripe size="default" :default-sort="{ prop: 'trade_date', order: 'descending' }">
                <el-table-column prop="trade_date" label="日期" width="110" sortable>
                  <template #default="{ row }">{{ row.trade_date?.slice(0, 10) }}</template>
                </el-table-column>
                <el-table-column prop="position_name" label="资产名称" min-width="140" />
                <el-table-column label="类型" width="80">
                  <template #default="{ row }">
                    <span :class="getTxnTypeClass(row.txn_type)">{{ txnTypeLabel(row.txn_type) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="价格" width="100" align="right">
                  <template #default="{ row }">¥{{ (row.price || 0).toLocaleString() }}</template>
                </el-table-column>
                <el-table-column label="数量" width="80" align="right">
                  <template #default="{ row }">{{ row.quantity }}</template>
                </el-table-column>
                <el-table-column label="金额" width="120" align="right" sortable prop="amount">
                  <template #default="{ row }">¥{{ (row.amount || 0).toLocaleString() }}</template>
                </el-table-column>
              </el-table>
              <div v-if="filteredTransactions.length === 0" class="text-center py-8 text-gray-400">暂无交易记录</div>
              <div v-if="filteredTransactions.length > 0" class="flex justify-end mt-4">
                <el-pagination v-model:current-page="transactionsPage" :page-size="transactionsPageSize" layout="prev, pager, next" :total="filteredTransactions.length" small />
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-card>

        <!-- 走势图预留区域 -->
        <div class="mt-6 p-4 border border-dashed rounded-xl text-center" :style="{ borderColor: 'var(--border-default)', color: 'var(--text-tertiary)' }">
          <IconifyIconOffline icon="ep:trend-charts" class="text-3xl mb-1" />
          <p>资产走势与分布图即将推出</p>
        </div>
      </template>
    </div>

    <!-- 编辑账户弹窗 -->
    <el-dialog v-model="showEditDialog" title="编辑账户" width="420px" destroy-on-close>
      <el-form :model="editForm" label-width="100px">
        <el-form-item label="账户名称" required>
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="配置目标">
          <el-select v-model="editForm.default_allocation" class="w-full" clearable>
            <el-option label="活钱" value="liquid" />
            <el-option label="稳健底仓" value="stable" />
            <el-option label="长期增值" value="longterm" />
            <el-option label="高风险博弈" value="speculative" />
            <el-option label="保险保障" value="security" />
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
        <el-button type="primary" :loading="saving" @click="handleUpdate">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="migrateDialogVisible" title="迁移资产到其他账户" width="400px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="资产名称">
          <span>{{ migratingItem?.name || migratingItem?.symbol }}</span>
        </el-form-item>
        <el-form-item label="目标账户">
          <el-select v-model="migrateTargetLedgerId" placeholder="选择账户" class="w-full">
            <el-option
              v-for="ledger in ledgers"
              :key="ledger.id"
              :label="ledger.name"
              :value="ledger.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="migrateDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleMigrate" :disabled="!migrateTargetLedgerId">
          确认迁移
        </el-button>
      </template>
    </el-dialog>


    <el-dialog v-model="batchMigrateVisible" title="批量迁移持仓" width="400px" destroy-on-close>
      <p class="mb-4" :style="{ color: 'var(--text-secondary)' }">
        将账户「{{ accountName }}」下的所有持仓迁移到目标账户。
      </p>
      <el-form label-width="80px">
        <el-form-item label="目标账户">
          <el-select v-model="batchTargetLedgerId" class="w-full" placeholder="选择同类型账户">
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
        <el-button type="primary" :disabled="!batchTargetLedgerId" :loading="batchMigrating" @click="handleBatchMigrate">
          确认迁移（{{ holdings.length }} 项）
        </el-button>
      </template>
    </el-dialog>

    <!-- 删除确认对话框 -->
    <DeleteLedgerDialog
      v-model:visible="deleteDialogVisible"
      :ledger-id="deletingAccount?.id ?? 0"
      :ledger-name="deletingAccount?.name ?? ''"
      :position-count="holdings.length"
      @deleted="router.push({ name: 'AssetLedgers' })"
    />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import {ElMessage, ElMessageBox} from "element-plus";
import { Loading } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getLedgers, updateLedger, migrateLedgerPositions  } from "@/api/ledger";
import { getPortfolios } from "@/api/portfolio";  // 新增导入
import { getPositions, updatePosition, deletePosition, getPositionTransactions } from "@/api/positions";
import { getAssets, updateAsset } from "@/api/assets";
import { getTransactions } from "@/api/transactions";
import AccountFormFields from "./components/AccountFormFields.vue";
import DeleteLedgerDialog from "./components/DeleteLedgerDialog.vue";

defineOptions({ name: "LedgerDetail" });

const route = useRoute();
const router = useRouter();

const ledgerId = computed(() => route.params.id as string);
const isUnclassified = computed(() => ledgerId.value === "unclassified" || !!route.query.name);
const targetAccountName = computed(() => route.query.name as string | undefined);

const loading = ref(true);
const ledgers = ref<any[]>([]);
const allPositions = ref<any[]>([]);
const allAssets = ref<any[]>([]);
const allTransactions = ref<any[]>([]);
const assignMap = ref<Record<number, number>>({});
const deleteDialogVisible = ref(false);
const deletingAccount = ref<any>(null);

const batchMigrateVisible = ref(false);
const batchMigrating = ref(false);
const batchTargetLedgerId = ref<number | null>(null);
const expandedPositionId = ref<number | null>(null);
const expandedTransactions = ref<any[]>([]);

const cashLedgers = computed(() => ledgers.value.filter((l: any) => l.ledger_type === 'cash'));

// 同类型账户列表（排除自身）
const sameTypeLedgers = computed(() =>
  accountInfo.value
    ? ledgers.value.filter(
        (l: any) =>
          l.ledger_type === accountInfo.value!.ledger_type &&
          l.id !== Number(ledgerId.value)
      )
    : []
);

const showEditDialog = ref(false);
const saving = ref(false);
const editForm = ref({
  name: "",
  ledger_type: "stock",
  default_allocation: null as string | null,
  notes: "",
  portfolio_id: null as number | null,  // 新增
  linked_cash_ledger_id: null as number | null,
  fee_config: null,
});

const holdingsPage = ref(1);
const holdingsPageSize = 20;
const transactionsPage = ref(1);
const transactionsPageSize = 20;
const activeTab = ref("holdings");

// 迁移相关状态
const migrateDialogVisible = ref(false);
const migratingItem = ref<any>(null);
const migrateTargetLedgerId = ref<number | null>(null);

// 组合列表（新增）
const portfolioList = ref<any[]>([]);

async function expandPosition(row: any) {
  if (expandedPositionId.value === row.id) {
    expandedPositionId.value = null;
    expandedTransactions.value = [];
    return;
  }
  expandedPositionId.value = row.id;
  try {
    const res = await getPositionTransactions(row.id);
    expandedTransactions.value = (res as any)?.data ?? [];
  } catch (e) {
    ElMessage.error("获取交易明细失败");
    expandedTransactions.value = [];
  }
}

function openBatchMigrateDialog() {
  batchTargetLedgerId.value = null;
  batchMigrateVisible.value = true;
}

async function handleBatchMigrate() {
  if (!batchTargetLedgerId.value) return;
  batchMigrating.value = true;
  try {
    const res = await migrateLedgerPositions(Number(ledgerId.value), batchTargetLedgerId.value);
    const result = (res as any)?.data;
    ElMessage.success(result?.message || `迁移成功`);
    batchMigrateVisible.value = false;
    await fetchData();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "迁移失败");
  } finally {
    batchMigrating.value = false;
  }
}

function openDeleteDialog(account: any) {
  deletingAccount.value = account;
  deleteDialogVisible.value = true;
}

function openMigrateDialog(row: any) {
  migratingItem.value = row;
  migrateTargetLedgerId.value = null;
  migrateDialogVisible.value = true;
}

async function handleMigrate() {
  if (!migrateTargetLedgerId.value || !migratingItem.value) return;
  const ledger = ledgers.value.find((l: any) => l.id === migrateTargetLedgerId.value);
  if (!ledger) return;

  try {
    if (migratingItem.value.id > 100000) {
      await updateAsset(migratingItem.value.id - 100000, { account_name: ledger.name });
    } else {
      await updatePosition(migratingItem.value.id, { account_name: ledger.name });
    }
    ElMessage.success(`已迁移至「${ledger.name}」`);
    migrateDialogVisible.value = false;
    await fetchData(); // 刷新列表，该资产将从当前页面消失（如果迁移到其他账户）
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "迁移失败");
  }
}

function getTypeColor(type: string) {
  const map: Record<string, string> = {
    stock: "var(--asset-stock)", fund: "var(--asset-fund)", bond: "var(--asset-bond)",
    etf: "var(--asset-etf)", crypto: "var(--asset-crypto)", saving: "var(--asset-saving)",
  };
  return map[type] || "var(--color-neutral)";
}
function getAllocColor(alloc: string | null) {
  const map: Record<string, string> = {
    liquid: "var(--tag-muted-blue)", stable: "var(--tag-thistle)",
    longterm: "var(--color-primary)", speculative: "var(--color-danger)",
    security: "var(--color-accent)",
  };
  return map[alloc || ""] || "var(--color-neutral)";
}


const accountInfo = computed(() => {
  if (isUnclassified.value) return null;
  return ledgers.value.find((l: any) => String(l.id) === ledgerId.value) || null;
});

const accountName = computed(() => {
  if (targetAccountName.value) return targetAccountName.value;
  if (isUnclassified.value) return "未归置持仓";
  return accountInfo.value?.name || "账户详情";
});

const subTitle = computed(() => {
  if (isUnclassified.value) return "将以下资产关联到已有账户";
  const type = accountInfo.value?.ledger_type;
  if (type === "stock") return "证券账户";
  if (type === "fund") return "基金平台";
  if (type === "cash") return "现金/活钱";
  if (type === "family") return "家庭账户";
  return "其他";
});

const totalLabel = computed(() => {
  return isUnclassified.value ? "待归置市值" : (accountInfo.value?.ledger_type === 'liability' ? "总负债" : "总市值");
});

// 所有已知 Ledger 名称的集合，用于过滤已归入同名账户的资产
const ledgerNames = computed(() => new Set(ledgers.value.map(l => l.name)));

const holdings = computed(() => {
  const posList = allPositions.value
    .filter((p: any) => {
      const acc = p.account_name || "未指定账户";
      if (isUnclassified.value) {
        // 游离资产：账户名为 "未指定账户" 或不在任何已知 Ledger 中
        if (acc === "未指定账户") return true;
        if (ledgerNames.value.has(acc)) return false; // 已有同名 Ledger，视为已归入
        if (targetAccountName.value) {
          return acc === targetAccountName.value;
        }
        return true;
      }
      return accountInfo.value && acc === accountInfo.value.name;
    })
    .map((p: any) => ({
      ...p,
      type_label: p.type_label || p.type || '其他',
      allocation_label: p.allocation_label || p.allocation || '未配置',
      pnlRate: p.avg_price ? ((p.current_price - p.avg_price) / p.avg_price * 100) : 0,
    }))

  const assetList = allAssets.value
    .filter((a: any) => {
      const acc = a.account_name || "未指定账户";
      if (isUnclassified.value) {
        if (acc === "未指定账户") return true;
        if (ledgerNames.value.has(acc)) return false;
        if (targetAccountName.value) {
          return acc === targetAccountName.value;
        }
        return true;
      }
      return accountInfo.value && acc === accountInfo.value.name;
    })
    .map((a: any) => ({
      ...a,
      id: a.id + 100000,
      type_label: a.type_label || a.major_category || '其他',
      allocation_label: a.allocation_label || a.allocation || '未配置',
      marketValue: a.marketValue || a.amount || 0,
      asset_type: a.major_category,
      pnl: 0,
      pnlRate: 0,
    }));

  return [...posList, ...assetList];
});

const totalMarketValue = computed(() => holdings.value.reduce((s, i) => s + (i.marketValue || 0), 0));

const allocationSummary = computed(() => {
  const map: Record<string, number> = {};
  holdings.value.forEach((h: any) => {
    // 排除负债及无效资产
    if (h.major_category === 'liability' || (h.marketValue || 0) <= 0) return;
    const alloc = h.allocation_label || "未配置";
    map[alloc] = (map[alloc] || 0) + (h.marketValue || 0);
  });
  const total = Object.values(map).reduce((s, v) => s + v, 0) || 1;
  return Object.entries(map)
    .map(([k, v]) => `${k} ${((v / total) * 100).toFixed(0)}%`)
    .join(" / ") || "暂无";
});

const filteredTransactions = computed(() => {
  if (isUnclassified.value) return [];
  const accName = accountInfo.value?.name;
  if (!accName) return [];
  return allTransactions.value.filter((t: any) => t.account_name === accName);
});

const pagedHoldings = computed(() => {
  const start = (holdingsPage.value - 1) * holdingsPageSize;
  return holdings.value.slice(start, start + holdingsPageSize);
});

const pagedTransactions = computed(() => {
  const start = (transactionsPage.value - 1) * transactionsPageSize;
  return filteredTransactions.value.slice(start, start + transactionsPageSize);
});

function txnTypeLabel(type: string) {
  const map: Record<string, string> = {
    buy: "买入", sell: "卖出", dividend: "分红", deposit: "存入", withdraw: "取出",
  };
  return map[type] || type;
}
function getTxnTypeClass(type: string) {
  if (type === "buy" || type === "deposit") return "text-[var(--color-danger)]";
  if (type === "sell" || type === "withdraw") return "text-[var(--color-success)]";
  return "text-[var(--color-info)]";
}

async function confirmDeletePosition(row: any) {
  try {
    await ElMessageBox.confirm(
      `确定删除持仓「${row.name || row.symbol}」吗？可选择同时删除关联交易记录。`,
      '删除持仓',
      {
        confirmButtonText: '仅删除持仓',
        cancelButtonText: '删除持仓及交易',
        distinguishCancelAndClose: true,
        type: 'warning',
      }
    ).then(async () => {
      await deletePosition(row.id, false);
    }).catch(async (action: string) => {
      if (action === 'cancel') {
        await deletePosition(row.id, true);
      }
    });
    ElMessage.success('持仓已删除');
    await fetchData();
  } catch (e: any) {
    // 取消操作
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
      await updatePosition(itemId, { account_name: ledger.name });
    }
    ElMessage.success(`已归入「${ledger.name}」`);
    await fetchData();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "归入失败");
  }
}

function openEditDialog() {
  if (!accountInfo.value) return;
  editForm.value = {
    name: accountInfo.value.name,
    ledger_type: accountInfo.value.ledger_type || "stock",
    default_allocation: accountInfo.value.default_allocation || null,
    notes: accountInfo.value.notes || "",
    portfolio_id: accountInfo.value.portfolio_id || null,  // 回填
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
    await fetchData();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "更新失败");
  } finally {
    saving.value = false;
  }
}

let abortController: AbortController | null = null;

async function fetchData() {
  if (abortController) {
    abortController.abort();
  }
  abortController = new AbortController();
  loading.value = true;
  try {
    const [ledgerRes, posRes, assetsRes, txnRes, portfolioRes] = await Promise.all([
      getLedgers(),
      getPositions({ per_page: 500 }),
      getAssets({ per_page: 500 }),
      getTransactions({ per_page: 1000 }),
      getPortfolios(),  // 新增
  ]);

    ledgers.value = Array.isArray((ledgerRes as any)?.data)
      ? (ledgerRes as any).data
      : (ledgerRes as any)?.data?.data || [];

    let posRaw: any[] = [];
    const posData = (posRes as any)?.data || posRes;
    posRaw = Array.isArray(posData) ? posData : posData?.data || [];
    allPositions.value = posRaw.map((p: any) => ({
      ...p,
      marketValue: (p.quantity || 0) * (p.current_price || 0),
      pnl: ((p.current_price || 0) - (p.avg_price || 0)) * (p.quantity || 0),
    }));

    let assetRaw: any[] = [];
    const assetData = (assetsRes as any)?.data || assetsRes;
    assetRaw = Array.isArray(assetData) ? assetData : assetData?.data || [];
    allAssets.value = assetRaw.map((a: any) => ({
      ...a,
      marketValue: a.signed_amount ?? (a.amount || 0),
    }));

    let txnRaw: any[] = [];
    const txnData = (txnRes as any)?.data || txnRes;
    txnRaw = Array.isArray(txnData) ? txnData : txnData?.data || [];
    allTransactions.value = txnRaw;

    // 保存组合列表
    const newPortfolios = (portfolioRes as any)?.data?.data ?? (portfolioRes as any)?.data ?? [];
    portfolioList.value = newPortfolios;
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  fetchData();
});
</script>
<style scoped>
.product-cell { display: flex; flex-direction: column; gap: 2px; line-height: 1.3; }
.product-name { font-size: 14px; font-weight: 500; color: var(--text-primary); }
.product-code-row { display: flex; align-items: center; gap: 6px; }
.product-code { font-size: 12px; color: var(--text-tertiary); }
.type-tag-inline { font-size: 11px; padding: 0 6px; height: 20px; line-height: 20px; border: none; color: #fff; background-color: var(--bg-page); }
</style>
