<template>
  <div class="account-page p-4 md:p-6 min-h-full" :style="{ backgroundColor: 'var(--bg-page)' }" :key="$route.fullPath">
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">账户管理</h2>
        <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary)' }">按资金账户查看持仓明细，管理账户信息</p>
      </div>
      <div class="flex gap-2">
        <el-button @click="$router.push('/asset/portfolios')">
          <IconifyIconOffline icon="ep:collection" class="mr-1" /> 投资组合
        </el-button>
        <el-button @click="$router.push('/asset/strategies')">
          <IconifyIconOffline icon="ep:data-analysis" class="mr-1" /> 策略分析
        </el-button>
        <el-button type="primary" @click="showCreateDialog = true">
          <IconifyIconOffline icon="ep:plus" class="mr-1" /> 新增账户
        </el-button>
      </div>
    </div>

    <!-- 加载 / 空状态 -->
    <div v-if="loading" class="text-center py-20" :style="{ color: 'var(--text-tertiary)' }">
      <p class="mt-2">加载中...</p>
    </div>

    <div v-else-if="allAccounts.length === 0" class="text-center py-20" :style="{ color: 'var(--text-tertiary)' }">
      <IconifyIconOffline icon="ep:wallet" class="text-5xl mb-3 opacity-30" />
      <p class="text-lg">暂无账户，点击上方按钮新增</p>
    </div>

    <template v-else>
      <!-- ========== 汇总区域（三层结构） ========== -->
      <!-- 第一层：净资产（核心数字） -->
      <div class="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 mb-4">
        <div class="flex items-baseline justify-between">
          <div>
            <p class="text-sm" :style="{ color: 'var(--text-tertiary)' }">净资产</p>
            <p
              class="text-4xl font-bold tracking-tight mt-1"
              :class="overviewData?.net_worth >= 0 ? 'text-[var(--color-danger)]' : 'text-[var(--color-success)]'"
            >
              {{ overviewData?.net_worth >= 0 ? '+' : '' }}{{ Math.abs(overviewData?.net_worth).toLocaleString() }}
            </p>
            <div class="flex gap-6 mt-2 text-sm">
              <span :style="{ color: 'var(--text-secondary)' }">
                总资产 ¥{{ totalAssets.toLocaleString() }}
              </span>
              <span :style="{ color: 'var(--color-success)' }">
                负债 ¥{{ overviewData?.liability_total?.toLocaleString() ?? '0' }}
              </span>
            </div>
          </div>
          <div class="hidden md:block text-right">
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">更新于</p>
            <p class="text-sm font-medium" :style="{ color: 'var(--text-primary)' }">{{ lastUpdate }}</p>
          </div>
        </div>
      </div>

      <!-- 第二层：分类汇总卡片 -->
      <div v-if="overviewData?.groups?.length" class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <div
          v-for="group in overviewData.groups.filter((g: any) => g.type !== 'deleted')"
          :key="group.type"
          class="bg-white rounded-xl p-4 shadow-sm border border-gray-100"
        >
          <p class="text-xs mb-1" :style="{ color: 'var(--text-tertiary)' }">{{ group.label }}</p>
          <p class="text-xl font-bold" :style="{ color: 'var(--color-primary)' }">
            ¥{{ group.total.toLocaleString() }}
          </p>
          <p class="text-xs mt-1" :style="{ color: 'var(--text-tertiary)' }">{{ group.count }} 个账户</p>
        </div>
      </div>

      <!-- 第三层：已删除/游离账户 -->
      <div
        v-if="overviewData?.groups?.some((g: any) => g.type === 'deleted' && g.count > 0)"
        class="bg-orange-50 border border-orange-200 rounded-xl p-4 mb-4 text-sm flex items-center gap-2"
        :style="{ color: 'var(--text-secondary)' }"
      >
        <IconifyIconOffline icon="ep:warning-filled" class="text-orange-400 shrink-0" />
        <span>
          存在 {{ overviewData.groups.find((g: any) => g.type === 'deleted')?.count ?? 0 }} 个已删除账户的持仓，
          合计 ¥{{ overviewData.groups.find((g: any) => g.type === 'deleted')?.total?.toLocaleString() ?? '0' }}。
          建议将这些持仓归入现有账户或手动清理。
        </span>
      </div>

      <!-- ========== 账户列表（按类型分组） ========== -->
      <div v-for="group in accountGroups" :key="group.label" class="mb-8">
        <div class="flex items-center justify-between mb-3">
          <h3 class="font-semibold text-base" :style="{ color: 'var(--text-primary)' }">
            {{ group.label }}
            <span class="text-sm font-normal ml-2" :style="{ color: 'var(--text-tertiary)' }">
              {{ group.accounts.length }} 个账户
            </span>
          </h3>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          <div
            v-for="account in group.accounts"
            :key="account.id"
            class="account-card"
            :class="{
              unlinked: !account.hasLedger,
              'account-card--large': account.isLarge && account.hasLedger
            }"
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
                    <template v-if="account.hasLedger && account.default_allocation">
                      {{ account.default_allocation_label || account.default_allocation || '未配置' }}
                    </template>
                    <template v-if="!account.hasLedger">待归类</template>
                  </p>
                </div>
              </div>
              <div class="flex items-center gap-1">
                <!-- 删除按钮改为打开对话框 -->
                <el-button
                  v-if="account.hasLedger && typeof account.id === 'number'"
                  type="danger"
                  size="small"
                  circle
                  @click.stop="openDeleteDialog(account)"
                >
                  <IconifyIconOffline icon="ep:delete" />
                </el-button>
                <IconifyIconOffline icon="ep:arrow-right" :style="{ color: 'var(--text-tertiary)' }" />
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">总市值</p>
                <p class="text-lg font-bold" :style="{ color: 'var(--color-primary)' }">¥{{ Math.abs(account.total).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</p>
              </div>
              <div>
                <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">持仓数量</p>
                <p class="text-lg font-bold" :style="{ color: 'var(--text-primary)' }">{{ account.count }} 项</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 新增账户对话框（不变） -->
    <el-dialog v-model="showCreateDialog" title="新增账户" width="420px" destroy-on-close>
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="账户名称" required>
          <el-input v-model="createForm.name" placeholder="如：华泰证券、招商银行" />
        </el-form-item>

        <AccountFormFields
          v-model:ledger-type="createForm.ledger_type"
          v-model:linked-cash-id="createForm.linked_cash_ledger_id"
          v-model:portfolio-id="createForm.portfolio_id"
          v-model:fee-config="createForm.fee_config"
          :cash-ledgers="cashLedgers"
          :portfolio-list="portfolioList"
        />

        <el-form-item label="备注">
          <el-input v-model="createForm.notes" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">确认创建</el-button>
      </template>
    </el-dialog>

    <!-- 删除确认对话框 -->
    <DeleteLedgerDialog
      v-model:visible="deleteDialogVisible"
      :ledger-id="deletingAccount?.id ?? 0"
      :ledger-name="deletingAccount?.name ?? ''"
      :position-count="deletingAccount?.count ?? 0"
      @deleted="fetchData"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getLedgers, createLedger, getLedgersOverview } from "@/api/ledger";
import { getPositions } from "@/api/positions";
import { getPortfolios } from "@/api/portfolio";
import { getAssets } from "@/api/assets";
import AccountFormFields from "./components/AccountFormFields.vue";
import DeleteLedgerDialog from "./components/DeleteLedgerDialog.vue";

// 组件名与路由配置中的 name 保持一致，确保 Keep-Alive 正常工作
defineOptions({ name: "AssetLedgers" });

// TODO: 后续可提取到全局常量文件 @/core/constants 中统一管理
const EXCHANGE_RATES: Record<string, number> = { CNY: 1, USD: 7.25, HKD: 0.92 };

const router = useRouter();
const route = useRoute();
const loading = ref(true);
const ledgers = ref<any[]>([]);
const allPositions = ref<any[]>([]);
const allAssets = ref<any[]>([]);
const overviewData = ref<any>(null);
const lastUpdate = ref("");
const deleting = ref(false);

const showCreateDialog = ref(false);
const creating = ref(false);
const createForm = ref({
  name: "",
  ledger_type: "stock",
  notes: "",
  linked_cash_ledger_id: null as number | null,
  portfolio_id: null as number | null,
  fee_config: null,
});
const cashLedgers = computed(() => ledgers.value.filter((l: any) => l.ledger_type === 'cash'));
const portfolioList = ref<any[]>([]);  // 从 API 获取，类似编辑页面

// 计算总资产（用于净资产卡片）
const totalAssets = computed(() => {
  return overviewData.value?.groups?.reduce((sum: number, g: any) => sum + (g.total || 0), 0) ?? 0;
});

// 按类型分组账户（用于列表展示）
const accountGroups = computed(() => {
  const order = ['stock', 'fund', 'cash', 'general', 'family'];
  const labels: Record<string, string> = {
    stock: '证券账户',
    fund: '基金平台',
    cash: '现金/活钱',
    general: '通用账户',
    family: '家庭账户',
  };

  const groups: Record<string, any[]> = {};

  // 有 Ledger 的账户按类型分组
  allAccounts.value
    .filter(acc => acc.hasLedger)
    .forEach(acc => {
      const type = acc.ledger_type || 'general';
      if (!groups[type]) groups[type] = [];
      groups[type].push(acc);
    });

  // 计算平均值用于高亮标记
  const allTotals = allAccounts.value
    .filter(a => a.hasLedger)
    .map(a => Math.abs(a.total));
  const avg = allTotals.length
    ? allTotals.reduce((s, v) => s + v, 0) / allTotals.length
    : 0;

  const result = order
    .filter(type => groups[type]?.length)
    .map(type => ({
      label: labels[type] || type,
      accounts: groups[type].map(acc => ({
        ...acc,
        isLarge: Math.abs(acc.total) > avg * 2 && avg > 0,
      })),
    }));

  // 未关联账户（游离/已删除）单独展示
  const unlinked = allAccounts.value.filter(acc => !acc.hasLedger);
  if (unlinked.length > 0) {
    result.push({
      label: '未关联账户',
      accounts: unlinked.map(acc => ({ ...acc, isLarge: false })),
    });
  }

  return result;
});

const accountHoldingsCache = ref<Map<string, any[]>>(new Map());
const accountTotalCache = ref<Map<string, number>>(new Map());

const deleteDialogVisible = ref(false);
const deletingAccount = ref<any>(null);

const allAccounts = computed(() => {
  const map = new Map<string, any>();

  // 1. Ledger 账户
  ledgers.value.forEach((l: any) => {
    const holdings = accountHoldingsCache.value.get(l.name) || [];
    const total = accountTotalCache.value.get(l.name) || 0;
    map.set(`ledger-${l.id}`, {
      id: l.id,
      name: l.name,
      hasLedger: true,
      ledger_type: l.ledger_type || "general",
      default_allocation: l.default_allocation,
      default_allocation_label: l.default_allocation_label || '',
      total,
      count: holdings.length,
    });
  });

  // 2. 游离账户（排除与 Ledger 同名的）
  const ledgerNameSet = new Set(ledgers.value.map(l => l.name));
  accountHoldingsCache.value.forEach((holdings, accountName) => {
    const key = accountName || "未指定账户";
    // 如果 Ledger 中已存在同名账户，则这些资产不应视为游离
    if (ledgerNameSet.has(key)) return;
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

function openDeleteDialog(account: any) {
  deletingAccount.value = account;
  deleteDialogVisible.value = true;
}

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
    createForm.value = {
      name: "",
      ledger_type: "stock",
      notes: "",
      linked_cash_ledger_id: null,
      portfolio_id: null,
    };
    await fetchData();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "创建失败");
  } finally {
    creating.value = false;
  }
}

async function fetchData() {
  loading.value = true;
  try {
    const [ledgerRes, posRes, assetsRes, overviewRes, portfolioRes] = await Promise.all([
      getLedgers(),
      getPositions({ per_page: 500 }),
      getAssets({ per_page: 500 }),
      getLedgersOverview(),
      getPortfolios(),
    ]);

    // 1. 解析 Ledger
    const newLedgers = (ledgerRes as any)?.data?.data ?? (ledgerRes as any)?.data ?? [];

    // 2. 解析持仓
    let posRaw: any[] = [];
    const posData = (posRes as any)?.data ?? posRes;
    posRaw = Array.isArray(posData) ? posData : posData?.data ?? [];
    const newPositions = posRaw.map((p: any) => ({
      ...p,
      marketValue: (p.quantity || 0) * (p.current_price || 0) * (EXCHANGE_RATES[p.currency || "CNY"] || 1),
    }));

    // 3. 解析资产
    let assetRaw: any[] = [];
    const assetData = (assetsRes as any)?.data ?? assetsRes;
    assetRaw = Array.isArray(assetData) ? assetData : assetData?.data ?? [];
    const newAssets = assetRaw.map((a: any) => ({
      ...a,
      marketValue: a.signed_amount ?? (a.amount || 0),
    }));

    // 4. 构建本地缓存
    const newHoldingsMap = new Map<string, any[]>();
    const newTotalMap = new Map<string, number>();

    newPositions.forEach((p: any) => {
      const acc = p.account_name || "未指定账户";
      if (!newHoldingsMap.has(acc)) newHoldingsMap.set(acc, []);
      newHoldingsMap.get(acc)!.push({
        ...p,
        type_label: p.type_label || p.type,
        allocation_label: p.allocation_label || p.allocation|| "未配置",
      });
    });

    newAssets.forEach((a: any) => {
      const acc = a.account_name || "未指定账户";
      if (!newHoldingsMap.has(acc)) newHoldingsMap.set(acc, []);
      newHoldingsMap.get(acc)!.push({
        ...a,
        id: a.id + 100000,
        type_label: a.minor_category || a.major_category,
        allocation_label: a.allocation_label || a.allocation || "未配置",
        marketValue: a.marketValue || a.amount || 0,
        asset_type: a.major_category,
      });
    });

    newHoldingsMap.forEach((items, acc) => {
      newTotalMap.set(acc, items.reduce((s, i) => s + (i.marketValue || 0), 0));
    });

    // 3. 一次性更新所有响应式变量，避免中间状态渲染
    ledgers.value = newLedgers;
    allPositions.value = newPositions;
    allAssets.value = newAssets;
    accountHoldingsCache.value = newHoldingsMap;
    accountTotalCache.value = newTotalMap;

    // 6. 汇总数据
    overviewData.value = (overviewRes as any)?.data ?? null;

    // 7. 组合列表
    const newPortfolios = (portfolioRes as any)?.data?.data ?? (portfolioRes as any)?.data ?? [];
    portfolioList.value = newPortfolios;

    // 8. 时间戳
    lastUpdate.value = new Date().toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

// 根元素已添加 :key="$route.fullPath"，每次进入都会重新挂载
// 仅保留 onMounted 即可保证数据加载
onMounted(() => {
  fetchData();
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
.account-card--large {
  border-left: 4px solid var(--tag-muted-blue);
}
</style>
