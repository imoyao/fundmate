<template>
  <div class="account-page p-4 md:p-6 min-h-full" :style="{ backgroundColor: 'var(--bg-page)' }" :key="$route.fullPath">
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">账户管理</h2>
        <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary)' }">按资金账户查看持仓明细，管理账户信息</p>
      </div>
      <el-button type="primary" @click="showCreateDialog = true">
        <IconifyIconOffline icon="ep:plus" class="mr-1" /> 新增账户
      </el-button>
    </div>

    <div v-if="loading" class="text-center py-20" :style="{ color: 'var(--text-tertiary)' }">
<!--      <el-icon class="is-loading" :size="32"><Loading /></el-icon>-->
      <p class="mt-2">加载中...</p>
    </div>

    <div v-else-if="allAccounts.length === 0" class="text-center py-20" :style="{ color: 'var(--text-tertiary)' }">
      <IconifyIconOffline icon="ep:wallet" class="text-5xl mb-3 opacity-30" />
      <p class="text-lg">暂无账户，点击上方按钮新增</p>
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      <div
        v-for="account in allAccounts"
        :key="account.id"
        class="account-card"
        :class="{ unlinked: !account.hasLedger }"
        @click="goToDetail(account)"
      >
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center gap-3">
            <div
              class="w-11 h-11 rounded-xl flex items-center justify-center"
              :style="{ backgroundColor: getAccountColor(account) + '20' }"
            >
              <IconifyIconOffline
                :icon="getAccountIcon(account)"
                class="text-xl"
                :style="{ color: getAccountColor(account) }"
              />
            </div>
            <div>
              <div class="flex items-center gap-2">
                <h3 class="font-semibold text-base" :style="{ color: 'var(--text-primary)' }">{{ account.name }}</h3>
                <span
                  v-if="!account.hasLedger"
                  class="px-2 py-0.5 text-xs rounded-full"
                  :style="{ backgroundColor: 'var(--color-warning)', color: '#fff' }"
                >未关联</span>
              </div>
              <p class="text-xs mt-0.5" :style="{ color: 'var(--text-tertiary)' }">
                {{ account.hasLedger ? (account.ledger_type === 'cash' ? '现金账户' : account.ledger_type === 'family' ? '家庭账户' : '通用账户') : '待归类' }}
                <template v-if="account.hasLedger && account.default_allocation">
                  · {{ getAllocLabel(account.default_allocation) }}
                </template>
              </p>
            </div>
          </div>
          <div class="flex items-center gap-1">
            <el-popconfirm
              v-if="account.hasLedger && typeof account.id === 'number'"
              title="确定删除此账户？"
              @confirm="handleDeleteLedger(account.id)"
              @click.stop
            >
              <template #reference>
                <el-button type="danger" size="small" circle @click.stop>
                  <IconifyIconOffline icon="ep:delete" />
                </el-button>
              </template>
            </el-popconfirm>
            <IconifyIconOffline icon="ep:arrow-right" :style="{ color: 'var(--text-tertiary)' }" />
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              {{ account.hasLedger ? (account.ledger_type === 'liability' ? '总负债' : '总市值') : '总市值' }}
            </p>
            <p class="text-lg font-bold" :style="{ color: 'var(--color-primary)' }">¥{{ account.total.toLocaleString() }}</p>
          </div>
          <div>
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">持仓数量</p>
            <p class="text-lg font-bold" :style="{ color: 'var(--text-primary)' }">{{ account.count }} 项</p>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="showCreateDialog" title="新增账户" width="420px" destroy-on-close>
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="账户名称" required>
          <el-input v-model="createForm.name" placeholder="如：华泰证券、招商银行" />
        </el-form-item>
        <el-form-item label="账户类型">
          <el-select v-model="createForm.ledger_type" class="w-full">
            <el-option label="通用账户" value="general" />
            <el-option label="现金账户" value="cash" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="createForm.notes" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">确认创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onActivated,watchEffect  } from "vue";
import { useRoute,useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Loading } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getLedgers, createLedger, deleteLedger } from "@/api/ledger";
import { getPositions } from "@/api/positions";
import { getAssets } from "@/api/assets";

defineOptions({ name: "AssetLedger" });

const EXCHANGE_RATES: Record<string, number> = { CNY: 1, USD: 7.25, HKD: 0.92 };

const router = useRouter();
const route = useRoute();
const loading = ref(true);
const ledgers = ref<any[]>([]);
const allPositions = ref<any[]>([]);
const allAssets = ref<any[]>([]);

const showCreateDialog = ref(false);
const creating = ref(false);
const createForm = ref({ name: "", ledger_type: "general", notes: "" });

const TYPE_LABELS: Record<string, string> = {
  stock: "股票", fund: "基金", bond: "可转债", etf: "ETF",
  crypto: "虚拟货币", saving: "银行存款", cash: "现金",
};
const ALLOC_LABELS: Record<string, string> = {
  liquid: "活钱", stable: "稳健底仓", longterm: "长期增值",
  speculative: "高风险博弈", security: "保险保障",
};

function getTypeColor(type: string): string {
  const map: Record<string, string> = {
    stock: "var(--asset-stock)", fund: "var(--asset-fund)", bond: "var(--asset-bond)",
    etf: "var(--asset-etf)", crypto: "var(--asset-crypto)", saving: "var(--asset-saving)",
  };
  return map[type] || "var(--color-neutral)";
}
function getAllocLabel(key: string | null): string {
  return ALLOC_LABELS[key || ""] || key || "未配置";
}

async function handleDeleteLedger(id: number) {
  try {
    await deleteLedger(id);
    ElMessage.success("账户已删除");
    fetchData();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "删除失败");
  }
}

const accountHoldingsCache = ref<Map<string, any[]>>(new Map());
const accountTotalCache = ref<Map<string, number>>(new Map());

const allAccounts = computed(() => {
  const map = new Map<string, any>();

  ledgers.value.forEach((l: any) => {
    const holdings = accountHoldingsCache.value.get(l.name) || [];
    const total = accountTotalCache.value.get(l.name) || 0;
    map.set(`ledger-${l.id}`, {
      id: l.id,
      name: l.name,
      hasLedger: true,
      ledger_type: l.ledger_type || "general",
      default_allocation: l.default_allocation,
      total,
      count: holdings.length,
    });
  });

  accountHoldingsCache.value.forEach((holdings, accountName) => {
    const key = accountName || "未指定账户";
    if (!map.has(key) && holdings.length > 0) {
      const total = accountTotalCache.value.get(accountName) || 0;
      map.set(key, {
        id: key === "未指定账户" ? "unclassified" : key,
        name: key,
        hasLedger: false,
        ledger_type: "general",
        default_allocation: null,
        total,
        count: holdings.length,
      });
    }
  });

  return Array.from(map.values());
});

function getAccountColor(account: any): string {
  if (!account.hasLedger) return "var(--color-warning)";
  const type = account.ledger_type;
  if (type === "cash") return "var(--tag-mint-green)";
  if (type === "family") return "var(--color-accent)";
  return "var(--tag-muted-blue)";
}

function getAccountIcon(account: any): string {
  if (!account.hasLedger) return "ep:warning";
  const type = account.ledger_type;
  if (type === "cash") return "ep:bank";
  if (type === "family") return "ep:share";
  return "ep:wallet";
}

function goToDetail(account: any) {
  if (account.id === "unclassified") {
    router.push("/asset/ledgers/unclassified");
  } else if (account.hasLedger && typeof account.id === "number") {
    router.push(`/asset/ledgers/${account.id}`);
  } else {
    router.push(`/asset/ledgers/unclassified?name=${encodeURIComponent(account.name)}`);
  }
}

async function handleCreate() {
  if (!createForm.value.name.trim()) {
    ElMessage.warning("请输入账户名称");
    return;
  }
  creating.value = true;
  try {
    await createLedger({ ...createForm.value, currency: "CNY" });
    ElMessage.success("账户已创建");
    showCreateDialog.value = false;
    createForm.value = { name: "", ledger_type: "general", notes: "" };
    await fetchData();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "创建失败");
  } finally {
    creating.value = false;
  }
}

async function fetchData() {
  console.log('--------111111111111111-----------')
  loading.value = true;
  try {
    const [ledgerRes, posRes, assetsRes] = await Promise.all([
      getLedgers(),
      getPositions({ per_page: 500 }),
      getAssets({ per_page: 500 }),
    ]);

    // 1. 先在本地处理所有数据，不更新任何响应式变量
    const newLedgers = Array.isArray((ledgerRes as any)?.data)
      ? (ledgerRes as any).data
      : (ledgerRes as any)?.data?.data || [];

    let posRaw: any[] = [];
    const posData = (posRes as any)?.data || posRes;
    posRaw = Array.isArray(posData) ? posData : posData?.data || [];
    const newPositions = posRaw.map((p: any) => ({
      ...p,
      marketValue: (p.quantity || 0) * (p.current_price || 0) * (EXCHANGE_RATES[p.currency || "CNY"] || 1),
    }));

    let assetRaw: any[] = [];
    const assetData = (assetsRes as any)?.data || assetsRes;
    assetRaw = Array.isArray(assetData) ? assetData : assetData?.data || [];
    const newAssets = assetRaw.map((a: any) => ({
      ...a,
      marketValue: a.amount || 0,
    }));

    // 2. 构建新的缓存
    const newHoldingsMap = new Map<string, any[]>();
    const newTotalMap = new Map<string, number>();

    newPositions.forEach((p: any) => {
      const acc = p.account_name || "未指定账户";
      if (!newHoldingsMap.has(acc)) newHoldingsMap.set(acc, []);
      newHoldingsMap.get(acc)!.push({
        ...p,
        type_label: TYPE_LABELS[p.asset_type || p.type] || p.asset_type || p.type,
        allocation_label: ALLOC_LABELS[p.allocation] || p.allocation || "未配置",
      });
    });

    newAssets.forEach((a: any) => {
      const acc = a.account_name || "未指定账户";
      if (!newHoldingsMap.has(acc)) newHoldingsMap.set(acc, []);
      newHoldingsMap.get(acc)!.push({
        ...a,
        id: a.id + 100000,
        type_label: a.minor_category || a.major_category,
        allocation_label: ALLOC_LABELS[a.allocation] || a.allocation || "未配置",
        marketValue: a.marketValue || a.amount || 0,
        asset_type: a.major_category,
      });
    });

    newHoldingsMap.forEach((items, acc) => {
      newTotalMap.set(acc, items.reduce((s, i) => s + (i.marketValue || 0), 0));
    });

    // 3. ✅ 一次性更新所有响应式变量，完全避免中间状态
    ledgers.value = newLedgers;
    allPositions.value = newPositions;
    allAssets.value = newAssets;
    accountHoldingsCache.value = newHoldingsMap;
    accountTotalCache.value = newTotalMap;

  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

// 生命周期：首次挂载和每次激活时都重新拉取数据
onMounted(() => {
  fetchData();  // ← 必须调用
});

onActivated(() => {
  fetchData();
});

// 强制监听当前路由，一旦匹配到列表页路径，立即重新加载数据
watchEffect(() => {
  if (route.path === '/asset/ledgers') {
    console.log('[AccountManagement] 强制激活，重新加载数据');
    loading.value = true;
    fetchData();
  }
});
</script>

<style scoped>
.account-page {
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}
.account-card {
  background: var(--bg-card);
  border-radius: 16px;
  padding: 20px;
  border: 1px solid var(--border-default);
  cursor: pointer;
  transition: all 0.2s;
}
.account-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  transform: translateY(-2px);
}
.account-card.unlinked {
  border-color: var(--color-warning);
}
</style>
