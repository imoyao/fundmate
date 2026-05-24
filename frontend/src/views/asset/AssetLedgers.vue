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
      <!-- 注释原因：Element Plus is-loading 类在 Keep-Alive 缓存恢复时会导致 SVG 渲染崩溃 -->
      <!-- <el-icon class="is-loading" :size="32"><Loading /></el-icon> -->
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
                {{ account.hasLedger
                  ? (account.ledger_type === 'cash' ? '现金账户'
                    : account.ledger_type === 'family' ? '家庭账户'
                    : '通用账户')
                  : '待归类' }}
                <template v-if="account.hasLedger && account.default_allocation">
                  · {{ account.default_allocation_label || account.default_allocation || '未配置'  }}
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
              {{ account.hasLedger && account.ledger_type === 'liability' ? '总负债' : '总市值' }}
            </p>
            <p class="text-lg font-bold" :style="{ color: 'var(--color-primary)' }">¥{{ Math.abs(account.total).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })  }}</p>
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
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router"; // 修复：添加缺失的空格
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getLedgers, createLedger, deleteLedger } from "@/api/ledger";
import { getPositions } from "@/api/positions";
import { getAssets } from "@/api/assets";

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

const showCreateDialog = ref(false);
const creating = ref(false);
const createForm = ref({ name: "", ledger_type: "general", notes: "" });

async function handleDeleteLedger(id: number) {
  try {
    await deleteLedger(id);
    ElMessage.success("账户已删除");
    fetchData();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "删除失败");
  }
}

// 注意：此处使用 ref 是为了触发 allAccounts 计算属性更新
// 优化建议：后续可改为普通变量，在 fetchData 末尾手动触发计算
const accountHoldingsCache = ref<Map<string, any[]>>(new Map());
const accountTotalCache = ref<Map<string, number>>(new Map());

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
  loading.value = true;
  try {
    const [ledgerRes, posRes, assetsRes] = await Promise.all([
      getLedgers(),
      getPositions({ per_page: 500 }),
      getAssets({ per_page: 500 }),
    ]);

    // 1. 统一解析 API 响应格式（兼容后端不同的返回结构）
    const newLedgers = (ledgerRes as any)?.data?.data ?? (ledgerRes as any)?.data ?? [];

    let posRaw: any[] = [];
    const posData = (posRes as any)?.data ?? posRes;
    posRaw = Array.isArray(posData) ? posData : posData?.data ?? [];
    const newPositions = posRaw.map((p: any) => ({
      ...p,
      marketValue: (p.quantity || 0) * (p.current_price || 0) * (EXCHANGE_RATES[p.currency || "CNY"] || 1),
    }));

    let assetRaw: any[] = [];
    const assetData = (assetsRes as any)?.data ?? assetsRes;
    assetRaw = Array.isArray(assetData) ? assetData : assetData?.data ?? [];
    const newAssets = assetRaw.map((a: any) => ({
      ...a,
      marketValue: a.signed_amount ?? (a.amount || 0),
    }));

    // 2. 构建本地缓存
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
</style>
