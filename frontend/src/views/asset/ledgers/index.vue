<template>
  <div class="ledger-list p-4 md:p-6 min-h-full" :style="{ backgroundColor: 'var(--bg-page)' }">
    <!-- 页面标题 & 操作栏 -->
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">账户管理</h2>
        <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary)' }">
          管理您的银行账户、证券账户、基金平台和实物资产
        </p>
      </div>
      <div class="flex gap-2">
        <el-button @click="$router.push('/asset/portfolios')">
          <IconifyIconOffline icon="ep:collection" class="mr-1" /> 投资组合
        </el-button>
        <el-button @click="$router.push('/asset/strategies')">
          <IconifyIconOffline icon="ep:data-analysis" class="mr-1" /> 策略分析
        </el-button>
        <el-button type="primary" @click="openCreateDialog">
          <IconifyIconOffline icon="ep:plus" class="mr-1" /> 新增账户
        </el-button>
      </div>
    </div>

    <!-- 加载 / 空状态 -->
    <div v-if="loading" class="text-center py-20" :style="{ color: 'var(--text-tertiary)' }">
      <p class="mt-2">加载中...</p>
    </div>

    <div v-else-if="allLedgers.length === 0 && !hasOrphanAssets" class="text-center py-20" :style="{ color: 'var(--text-tertiary)' }">
      <IconifyIconOffline icon="ep:wallet" class="text-5xl mb-3 opacity-30" />
      <p class="text-lg">暂无账户，点击上方按钮新增</p>
    </div>

    <template v-else>
      <!-- 全局汇总卡片 -->
      <div class="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 mb-4">
        <div class="flex items-baseline justify-between">
          <div>
            <p class="text-sm" :style="{ color: 'var(--text-tertiary)' }">净资产</p>
            <p
              class="text-4xl font-bold tracking-tight mt-1"
              :class="overviewData.net_worth >= 0 ? 'text-[var(--color-danger)]' : 'text-[var(--color-success)]'"
            >
              {{ overviewData.net_worth >= 0 ? '+' : '' }}{{ Math.abs(overviewData.net_worth).toLocaleString() }}
            </p>
            <div class="flex gap-6 mt-2 text-sm">
              <span :style="{ color: 'var(--text-secondary)' }">
                总资产 ¥{{ totalAssets.toLocaleString() }}
              </span>
              <span :style="{ color: 'var(--color-success)' }">
                负债 ¥{{ (overviewData.liability_total || 0).toLocaleString() }}
              </span>
              <span v-if="overviewData.liability_total > totalAssets * 0.5" class="text-[var(--color-danger)] text-xs">
                负债率偏高
              </span>
            </div>
          </div>
          <div class="hidden md:block text-right">
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">更新于</p>
            <p class="text-sm font-medium" :style="{ color: 'var(--text-primary)' }">{{ lastUpdate }}</p>
          </div>
        </div>
      </div>

      <!-- 分类汇总卡片（保留 overview 的 group 信息） -->
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

      <!-- 已删除账户的持仓警告 -->
      <div
        v-if="orphanGroup"
        class="bg-orange-50 border border-orange-200 rounded-xl p-4 mb-4 text-sm flex items-center gap-2"
        :style="{ color: 'var(--text-secondary)' }"
      >
        <IconifyIconOffline icon="ep:warning-filled" class="text-orange-400 shrink-0" />
        <span>
          存在 {{ orphanGroup.count }} 个已删除账户的持仓，
          合计 ¥{{ orphanGroup.total.toLocaleString() }}。
          建议将这些持仓归入现有账户或手动清理。
        </span>
      </div>

      <!-- 按类型分组的账户卡片 -->
      <div v-for="group in groupedLedgers" :key="group.type" class="mb-8">
        <!-- 分组标题（含汇总） -->
        <div class="flex items-center justify-between mb-3">
          <h3 class="font-semibold text-base" :style="{ color: 'var(--text-primary)' }">
            {{ group.label }}
            <span class="text-sm font-normal ml-2" :style="{ color: 'var(--text-tertiary)' }">
              ({{ group.count }} 个账户 · ¥{{ group.total.toLocaleString() }})
            </span>
          </h3>
        </div>

        <!-- 卡片行 -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          <div
            v-for="ledger in group.ledgers"
            :key="ledger.id"
            class="ledger-card bg-white rounded-2xl p-5 border border-gray-100 shadow-sm cursor-pointer transition-all hover:shadow-md hover:-translate-y-1"
            @click="goToDetail(ledger)"
          >
            <!-- 标题行：名称 + 类型缩写 Badge -->
            <div class="flex items-center justify-between mb-4">
              <div class="flex items-center gap-2 min-w-0">
                <span class="font-semibold text-base truncate" :style="{ color: 'var(--text-primary)' }">
                  {{ ledger.name }}
                </span>
                <span
                  class="px-1.5 py-0.5 rounded text-xs font-medium shrink-0"
                  :style="{ backgroundColor: getTypeColor(ledger.ledger_type) + '20', color: getTypeColor(ledger.ledger_type) }"
                >
                  {{ getLedgerTypeShort(ledger.ledger_type) }}
                </span>
              </div>
              <!-- 删除按钮 -->
              <el-button
                v-if="typeof ledger.id === 'number'"
                type="danger"
                size="small"
                circle
                @click.stop="openDeleteDialog(ledger)"
              >
                <IconifyIconOffline icon="ep:delete" />
              </el-button>
            </div>

            <!-- 核心指标（三行） -->
            <div class="space-y-2">
              <!-- 总资产 -->
              <div class="flex justify-between items-center">
                <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }">总资产</span>
                <span class="text-lg font-bold" :style="{ color: 'var(--color-primary)' }">
                  ¥{{ (ledger.total_market_value || 0).toLocaleString() }}
                </span>
              </div>

              <!-- 当日盈亏（占位） -->
              <div class="flex justify-between items-center">
                <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }">当日盈亏</span>
                <span class="text-sm" :style="{ color: 'var(--text-tertiary)' }">--</span>
              </div>

              <!-- 持仓盈亏（仅 stock/fund）或资产分布提示（bank/property） -->
              <div class="flex justify-between items-center">
                <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
                  {{ ledger.ledger_type === 'bank' ? '活期余额' : ledger.ledger_type === 'property' ? '估值' : '持仓盈亏' }}
                </span>
                <span
                  v-if="ledger.ledger_type === 'bank' && ledger.cash_balance !== undefined && ledger.cash_balance !== null"
                  class="text-sm font-medium"
                  :style="{ color: 'var(--text-secondary)' }"
                >
                  ¥{{ ledger.cash_balance.toLocaleString() }}
                </span>
                <span
                  v-else-if="ledger.ledger_type === 'property'"
                  class="text-sm font-medium"
                  :style="{ color: 'var(--text-secondary)' }"
                >
                  {{ ledger.position_count || 0 }} 项
                </span>
                <span
                  v-else
                  class="text-sm font-semibold"
                  :class="(ledger.pnl || 0) >= 0 ? 'text-[var(--color-danger)]' : 'text-[var(--color-success)]'"
                >
                  {{ (ledger.pnl || 0) >= 0 ? '+' : '' }}¥{{ Math.abs(ledger.pnl || 0).toLocaleString() }}
                </span>
              </div>
            </div>
          </div>

          <!-- 末尾占位卡片：新建账户 -->
          <div
            class="ledger-card bg-white rounded-2xl p-5 border border-dashed border-gray-300 flex flex-col items-center justify-center text-center cursor-pointer hover:border-[var(--color-primary)] transition-all"
            @click="openCreateDialog"
          >
            <IconifyIconOffline icon="ep:plus" class="text-2xl mb-2" :style="{ color: 'var(--text-tertiary)' }" />
            <span class="text-sm" :style="{ color: 'var(--text-secondary)' }">新增账户</span>
          </div>
        </div>
      </div>
    </template>

    <!-- 新增账户对话框 -->
    <el-dialog v-model="showCreateDialog" title="创建账户" width="420px" destroy-on-close>
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
      :position-count="deletingAccount?.position_count ?? 0"
      @deleted="fetchData"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Loading } from "@element-plus/icons-vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { getLedgers, getLedgersOverview, createLedger } from "@/api/ledger";
import { getPortfolios } from "@/api/portfolio";
import { getLedgerTypeLabel, LEDGER_TYPE_SHORT } from "@/constants";
import AccountFormFields from "./components/AccountFormFields.vue";
import DeleteLedgerDialog from "./components/DeleteLedgerDialog.vue";

// 组件名与路由配置中的 name 保持一致，确保 Keep-Alive 正常工作
defineOptions({ name: "AssetLedgers" });

const router = useRouter();

const loading = ref(true);
const allLedgers = ref<any[]>([]);
const overviewData = ref<{ net_worth: number; liability_total: number; groups: any[] }>({
  net_worth: 0,
  liability_total: 0,
  groups: [],
});
const lastUpdate = ref("");

const showCreateDialog = ref(false);
const creating = ref(false);
const createForm = ref({
  name: "",
  ledger_type: "stock",
  notes: "",
  linked_cash_ledger_id: null as number | null,
  portfolio_id: null as number | null,
  fee_config: null as any,
});

// 新增：关联现金账户列表
const cashLedgers = computed(() => allLedgers.value.filter((l: any) => l.ledger_type === 'bank'));

// 新增：组合列表
const portfolioList = ref<any[]>([]);

// 删除相关
const deleteDialogVisible = ref(false);
const deletingAccount = ref<any>(null);

// 总资产（从 overview groups 汇总）
const totalAssets = computed(() =>
  overviewData.value?.groups?.reduce((sum: number, g: any) => sum + (g.total || 0), 0) ?? 0
);

// 已删除账户的持仓信息（来自 overview）
const orphanGroup = computed(() =>
  overviewData.value?.groups?.find((g: any) => g.type === 'deleted')
);

const hasOrphanAssets = computed(() => orphanGroup.value?.count > 0);

// 辅助函数：获取类型缩写
function getLedgerTypeShort(type: string): string {
  return LEDGER_TYPE_SHORT[type] || type;
}

// 分组展示（正常账户 + 未归置）
const groupedLedgers = computed(() => {
  const groups: Record<string, any> = {};
  for (const ledger of allLedgers.value) {
    const type = ledger.ledger_type || "bank";
    if (!groups[type]) {
      groups[type] = {
        type,
        label: getLedgerTypeLabel(type),
        total: 0,
        count: 0,
        ledgers: [],
      };
    }
    groups[type].count++;
    groups[type].total += ledger.total_market_value || 0;
    groups[type].ledgers.push(ledger);
  }

  const order = ["bank", "stock", "fund", "property"];
  const result = order.map((type) => groups[type]).filter(Boolean);

  // 追加未归置分组
  if (orphanGroup.value && orphanGroup.value.count > 0) {
    result.push({
      type: 'deleted',
      label: '未归置持仓',
      total: orphanGroup.value.total,
      count: orphanGroup.value.count,
      ledgers: [{
        id: 'orphan',
        name: '已删除账户的持仓',
        total_market_value: orphanGroup.value.total,
        position_count: orphanGroup.value.count,
        pnl: 0,
        ledger_type: 'deleted',
        cash_balance: null,
      }],
    });
  }

  return result;
});

// 颜色映射（使用 CSS 变量）
function getTypeColor(type: string): string {
  const map: Record<string, string> = {
    bank: "var(--tag-mint-green)",
    stock: "var(--color-danger)",
    fund: "var(--color-warning)",
    property: "var(--color-accent)",
    deleted: "var(--color-neutral)",
  };
  return map[type] || "var(--color-neutral)";
}

function openCreateDialog() {
  createForm.value = {
    name: "",
    ledger_type: "stock",
    notes: "",
    linked_cash_ledger_id: null,
    portfolio_id: null,
    fee_config: null,
  };
  showCreateDialog.value = true;
}

async function handleCreate() {
  if (!createForm.value.name.trim()) {
    ElMessage.warning("名称不能为空");
    return;
  }
  creating.value = true;
  try {
    await createLedger(createForm.value);
    ElMessage.success("账户创建成功");
    showCreateDialog.value = false;
    await fetchData();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "创建失败");
  } finally {
    creating.value = false;
  }
}

function openDeleteDialog(account: any) {
  deletingAccount.value = account;
  deleteDialogVisible.value = true;
}

function goToDetail(ledger: any) {
  if (ledger.id === 'orphan') {
    router.push('/asset/ledgers/unclassified');
  } else {
    router.push({ name: "LedgerDetail", params: { id: ledger.id } });
  }
}

async function fetchData() {
  loading.value = true;
  try {
    const [ledgersRes, overviewRes, portfolioRes] = await Promise.all([
      getLedgers(),
      getLedgersOverview(),
      getPortfolios(),
    ]);
    allLedgers.value = (ledgersRes as any)?.data ?? [];
    overviewData.value = (overviewRes as any)?.data ?? { net_worth: 0, liability_total: 0, groups: [] };
    portfolioList.value = (portfolioRes as any)?.data ?? [];
    lastUpdate.value = new Date().toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
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
.ledger-list {
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}
.ledger-card {
  transition: all 0.2s ease;
}
.ledger-card:hover {
  box-shadow: var(--el-box-shadow-light);
}
</style>
