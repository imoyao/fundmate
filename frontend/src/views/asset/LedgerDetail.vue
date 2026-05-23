<template>
  <div> <!-- 新增根元素 -->
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
          <el-popconfirm title="确定删除此账户？账户下的持仓不会被删除，但会变为未关联状态。" @confirm="handleDelete">
            <template #reference>
              <el-button type="danger" text>
                <IconifyIconOffline icon="ep:delete" class="mr-1" /> 删除
              </el-button>
            </template>
          </el-popconfirm>
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
            <template v-if="accountInfo?.default_allocation"> · {{ allocLabel(accountInfo.default_allocation) }}</template>
          </p>
        </div>

        <!-- 汇总卡片 -->
        <el-row :gutter="16" class="mb-6">
          <el-col :span="8">
            <el-card shadow="never">
              <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">{{ totalLabel }}</p>
              <p class="text-xl font-bold" :style="{ color: 'var(--color-primary)' }">¥{{ totalMarketValue.toLocaleString() }}</p>
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
              <el-table :data="pagedHoldings" stripe size="default" :default-sort="{ prop: 'marketValue', order: 'descending' }">
                <el-table-column prop="name" label="名称" min-width="140">
                  <template #default="{ row }">{{ row.name || row.symbol }}</template>
                </el-table-column>
                <el-table-column label="类型" width="100">
                  <template #default="{ row }">
                    <span class="px-2 py-0.5 rounded-full text-xs" :style="{ color: getTypeColor(row.asset_type || row.type) }">
                      {{ row.type_label }}
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="代码" width="100" v-if="!isUnclassified">
                  <template #default="{ row }">
                    <span :style="{ color: 'var(--text-tertiary)' }">{{ row.symbol || '-' }}</span>
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
                <el-table-column v-if="isUnclassified" label="归入账户" width="160">
                  <template #default="{ row }">
                    <el-select v-model="assignMap[row.id]" placeholder="选择账户" size="small" @change="handleAssign(row.id)">
                      <el-option v-for="ledger in ledgers" :key="ledger.id" :label="ledger.name" :value="ledger.id" />
                    </el-select>
                  </template>
                </el-table-column>
              </el-table>
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
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="账户名称" required>
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="账户类型">
          <el-select v-model="editForm.ledger_type" class="w-full">
            <el-option label="通用账户" value="general" />
            <el-option label="现金账户" value="cash" />
          </el-select>
        </el-form-item>
        <el-form-item label="默认配置目标">
          <el-select v-model="editForm.default_allocation" class="w-full" clearable>
            <el-option label="活钱" value="liquid" />
            <el-option label="稳健底仓" value="stable" />
            <el-option label="长期增值" value="longterm" />
            <el-option label="高风险博弈" value="speculative" />
            <el-option label="保险保障" value="security" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleUpdate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onActivated, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Loading } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getLedgers, updateLedger, deleteLedger } from "@/api/ledger";
import { getPositions, updatePosition } from "@/api/positions";
import { getAssets, updateAsset } from "@/api/assets";
import { getTransactions } from "@/api/transactions";

defineOptions({ name: "LedgerDetail" });

const route = useRoute();
const router = useRouter();

// 路由参数可能变化，使用 computed 动态响应
const ledgerId = computed(() => route.params.id as string);
const isUnclassified = computed(() => ledgerId.value === "unclassified" || !!route.query.name);
const targetAccountName = computed(() => route.query.name as string | undefined);

const loading = ref(false);
const ledgers = ref<any[]>([]);
const allPositions = ref<any[]>([]);
const allAssets = ref<any[]>([]);
const allTransactions = ref<any[]>([]);
const assignMap = ref<Record<number, number>>({});

const showEditDialog = ref(false);
const saving = ref(false);
const editForm = ref({
  name: "",
  ledger_type: "general",
  default_allocation: null as string | null,
  notes: "",
});

const holdingsPage = ref(1);
const holdingsPageSize = 20;
const transactionsPage = ref(1);
const transactionsPageSize = 20;
const activeTab = ref("holdings");

const TYPE_LABELS: Record<string, string> = {
  stock: "股票", fund: "基金", bond: "可转债", etf: "ETF",
  crypto: "虚拟货币", saving: "银行存款", cash: "现金",
};
const ALLOC_LABELS: Record<string, string> = {
  liquid: "活钱", stable: "稳健底仓", longterm: "长期增值",
  speculative: "高风险博弈", security: "保险保障",
};

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
function allocLabel(key: string | null) {
  return ALLOC_LABELS[key || ""] || key || "未配置";
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
  if (type === "cash") return "现金账户";
  if (type === "family") return "家庭账户";
  return "通用账户";
});

const totalLabel = computed(() => {
  return isUnclassified.value ? "待归置市值" : (accountInfo.value?.ledger_type === 'liability' ? "总负债" : "总市值");
});

const holdings = computed(() => {
  const posList = allPositions.value
    .filter((p: any) => {
      const acc = p.account_name || "未指定账户";
      if (isUnclassified.value) return acc === "未指定账户" || acc === targetAccountName.value;
      return accountInfo.value && acc === accountInfo.value.name;
    })
    .map((p: any) => ({
      ...p,
      type_label: TYPE_LABELS[p.asset_type || p.type] || p.asset_type || p.type,
      allocation_label: ALLOC_LABELS[p.allocation] || p.allocation || "未配置",
      pnlRate: p.avg_price ? ((p.current_price - p.avg_price) / p.avg_price * 100) : 0,
    }));

  const assetList = allAssets.value
    .filter((a: any) => {
      const acc = a.account_name || "未指定账户";
      if (isUnclassified.value) return acc === "未指定账户" || acc === targetAccountName.value;
      return accountInfo.value && acc === accountInfo.value.name;
    })
    .map((a: any) => ({
      ...a,
      id: a.id + 100000,
      type_label: a.minor_category || a.major_category,
      allocation_label: ALLOC_LABELS[a.allocation] || a.allocation || "未配置",
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
    const alloc = h.allocation_label || "未配置";
    map[alloc] = (map[alloc] || 0) + (h.marketValue || 0);
  });
  const total = totalMarketValue.value || 1;
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
    ledger_type: accountInfo.value.ledger_type || "general",
    default_allocation: accountInfo.value.default_allocation || null,
    notes: accountInfo.value.notes || "",
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

async function handleDelete() {
  try {
    await deleteLedger(Number(ledgerId.value));
    ElMessage.success("账户已删除");
    router.push("/asset/ledgers");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "删除失败");
  }
}

async function fetchData() {
  console.log('[AccountDetail] fetchData 开始')
  loading.value = true;
  try {
    const [ledgerRes, posRes, assetsRes, txnRes] = await Promise.all([
      getLedgers(),
      getPositions({ per_page: 500 }),
      getAssets({ per_page: 500 }),
      getTransactions({ per_page: 1000 }),
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
      marketValue: a.amount || 0,
    }));

    let txnRaw: any[] = [];
    const txnData = (txnRes as any)?.data || txnRes;
    txnRaw = Array.isArray(txnData) ? txnData : txnData?.data || [];
    allTransactions.value = txnRaw;
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

// 组件首次挂载时加载数据
onMounted(() => {
  fetchData();
});

// 组件激活时也重新获取
onActivated(() => {
  fetchData();
});
</script>
