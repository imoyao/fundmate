<template>
  <div
    class="ledger-list p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 页面标题 & 操作栏 -->
    <div class="mb-6 flex justify-between items-center">
      <div>
        <h2
          class="text-2xl font-bold"
          :style="{ color: 'var(--text-primary)' }"
        >
          账户管理
        </h2>
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
    <div
      v-if="loading"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary)' }"
    >
      <p class="mt-2">加载中...</p>
    </div>

    <div
      v-else-if="allLedgers.length === 0"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary)' }"
    >
      <IconifyIconOffline icon="ep:wallet" class="text-5xl mb-3 opacity-30" />
      <p class="text-lg">暂无账户，点击上方按钮新增</p>
    </div>

    <template v-else>
      <!-- 全局汇总卡片（三层结构） -->
      <div
        class="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 mb-4"
      >
        <div class="flex items-baseline justify-between">
          <div>
            <p class="text-sm" :style="{ color: 'var(--text-tertiary)' }">
              净资产
            </p>
            <p class="text-4xl font-bold tracking-tight mt-1">
              <MoneyDisplay :value="overviewData.net_worth" size="xl" />
            </p>
            <div class="flex gap-6 mt-2 text-sm">
              <span :style="{ color: 'var(--text-secondary)' }">
                总资产
                <MoneyDisplay
                  :value="totalAssets"
                  :show-sign="false"
                  :auto-color="false"
                  size="sm"
                />
              </span>
              <span :style="{ color: 'var(--color-success)' }">
                负债
                <MoneyDisplay
                  :value="overviewData.liability_total || 0"
                  :show-sign="false"
                  :auto-color="false"
                  size="sm"
                />
              </span>
              <span
                v-if="overviewData.liability_total > totalAssets * 0.5"
                class="text-[var(--color-danger)] text-xs"
              >
                负债率偏高
              </span>
            </div>
          </div>
          <div class="hidden md:block text-right">
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              更新于
            </p>
            <p
              class="text-sm font-medium"
              :style="{ color: 'var(--text-primary)' }"
            >
              {{ lastUpdate }}
            </p>
          </div>
        </div>
      </div>

      <!-- 第二层：分类汇总卡片 -->
      <div
        v-if="overviewData?.groups?.length"
        class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4"
      >
        <div
          v-for="group in overviewData.groups.filter(
            (g: any) => g.type !== 'deleted'
          )"
          :key="group.type"
          class="bg-white rounded-xl p-4 shadow-sm border border-gray-100"
        >
          <p class="text-xs mb-1" :style="{ color: 'var(--text-tertiary)' }">
            {{ group.label }}
          </p>
          <p
            class="text-xl font-bold"
            :style="{ color: 'var(--color-primary)' }"
          >
            <MoneyDisplay
              :value="group.total"
              :show-sign="false"
              :auto-color="false"
            />
          </p>
          <p class="text-xs mt-1" :style="{ color: 'var(--text-tertiary)' }">
            {{ group.count }} 个账户
          </p>
        </div>
      </div>

      <!-- 已删除账户持仓提示 -->
      <div
        v-if="orphanGroup?.count > 0"
        class="bg-orange-50 border border-orange-200 rounded-xl p-4 mb-4 text-sm flex items-center justify-between gap-3"
        :style="{ color: 'var(--text-secondary)' }"
      >
        <div class="flex items-center gap-2 min-w-0">
          <IconifyIconOffline
            icon="ep:warning-filled"
            class="text-orange-400 shrink-0"
          />
          <span>
            存在 {{ orphanGroup.count }} 个已删除账户的持仓，合计
            <MoneyDisplay
              :value="orphanGroup.total || 0"
              :show-sign="false"
              :auto-color="false"
              size="sm"
            />。 建议将这些持仓归入现有账户或手动清理。
          </span>
        </div>
        <div class="flex gap-2 shrink-0">
          <el-button size="small" type="primary" @click="openMigrateDialog">
            归入现有账户
          </el-button>
          <el-button
            size="small"
            type="danger"
            plain
            :loading="cleaning"
            @click="handleOrphanCleanup"
          >
            清理
          </el-button>
        </div>
      </div>

      <!-- 按类型分组的账户卡片列表 -->
      <div v-for="group in groupedLedgers" :key="group.type" class="mb-8">
        <div class="flex items-center justify-between mb-3">
          <h3
            class="font-semibold text-base"
            :style="{ color: 'var(--text-primary)' }"
          >
            {{ group.label }}
            <span
              class="text-sm font-normal ml-2"
              :style="{ color: 'var(--text-tertiary)' }"
            >
              (
              {{ group.count }} 个账户 ·
              <MoneyDisplay
                :value="group.total"
                :show-sign="false"
                :auto-color="false"
                size="xs"
              />)
            </span>
          </h3>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          <div
            v-for="ledger in group.ledgers"
            :key="ledger.id"
            class="ledger-card bg-white rounded-2xl p-5 border border-gray-100 shadow-sm cursor-pointer transition-all hover:shadow-md hover:-translate-y-1"
            @click="goToDetail(ledger)"
          >
            <!-- 标题行：名称 + 类型标签（支持 LEDGER_TYPE_SHORT） -->
            <div class="flex items-center justify-between mb-4">
              <div class="flex items-center gap-2 min-w-0">
                <span
                  class="font-semibold text-base truncate"
                  :style="{ color: 'var(--text-primary)' }"
                >
                  {{ ledger.name }}
                </span>
                <AssetTypeBadge :type="ledger.ledger_type" />
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
              <!-- 未归置持仓：归入按钮 -->
              <el-button
                v-if="ledger.id === 'orphan'"
                type="primary"
                size="small"
                plain
                @click.stop="openMigrateDialog"
              >
                归入
              </el-button>
            </div>

            <!-- 核心指标（三行） -->
            <div class="space-y-2">
              <!-- 1. 总资产 -->
              <div class="flex justify-between items-center">
                <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }"
                  >总资产</span
                >
                <span
                  class="text-lg font-bold"
                  :style="{ color: 'var(--color-primary)' }"
                >
                  <MoneyDisplay
                    :value="ledger.total_market_value || 0"
                    :show-sign="false"
                    :auto-color="false"
                  />
                </span>
              </div>
              <!-- 2. 当日盈亏 -->
              <div class="flex justify-between items-center">
                <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }"
                  >当日盈亏</span
                >
                <span class="text-sm" :style="{ color: 'var(--text-tertiary)' }"
                  >--</span
                >
              </div>
              <!-- 3. 活期/盈亏 -->
              <div class="flex justify-between items-center">
                <span
                  class="text-xs"
                  :style="{ color: 'var(--text-tertiary)' }"
                >
                  {{
                    ledger.ledger_type === "bank"
                      ? "活期余额"
                      : ledger.ledger_type === "property"
                        ? "估值"
                        : "持仓盈亏"
                  }}
                </span>
                <span
                  v-if="
                    ledger.ledger_type === 'bank' &&
                    ledger.cash_balance !== undefined &&
                    ledger.cash_balance !== null
                  "
                  class="text-sm font-medium"
                  :style="{ color: 'var(--text-secondary)' }"
                >
                  <MoneyDisplay
                    :value="ledger.cash_balance"
                    :show-sign="false"
                    :auto-color="false"
                    size="sm"
                  />
                </span>
                <span
                  v-else-if="ledger.ledger_type === 'property'"
                  class="text-sm font-medium"
                  :style="{ color: 'var(--text-secondary)' }"
                >
                  {{ ledger.position_count || 0 }} 项
                </span>
                <span v-else class="text-sm font-semibold">
                  <MoneyDisplay :value="ledger.pnl || 0" size="sm" />
                </span>
              </div>

              <!-- 🔥 新增：银行账户的关联负债（房贷） -->
              <div
                v-if="
                  ledger.ledger_type === 'bank' && ledger.linked_liability > 0
                "
                class="flex justify-between items-center pt-1 border-t border-gray-50"
              >
                <span class="text-xs" :style="{ color: 'var(--text-tertiary)' }"
                  >关联负债</span
                >
                <span
                  class="text-xs font-semibold"
                  :style="{ color: 'var(--color-danger)' }"
                >
                  <MoneyDisplay
                    :value="-ledger.linked_liability"
                    :auto-color="false"
                    size="xs"
                  />
                </span>
              </div>
            </div>
          </div>

          <!-- 末尾占位卡片：新建账户 -->
          <div
            class="ledger-card bg-white rounded-2xl p-5 border border-dashed border-gray-300 flex flex-col items-center justify-center text-center cursor-pointer hover:border-[var(--color-primary)] transition-all"
            @click="openCreateDialog"
          >
            <IconifyIconOffline
              icon="ep:plus"
              class="text-2xl mb-2"
              :style="{ color: 'var(--text-tertiary)' }"
            />
            <span class="text-sm" :style="{ color: 'var(--text-secondary)' }"
              >新增账户</span
            >
          </div>
        </div>
      </div>
    </template>

    <!-- 新增账户对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      title="创建账户"
      width="420px"
      destroy-on-close
    >
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="账户名称" required>
          <el-input
            v-model="createForm.name"
            placeholder="如：华泰证券、招商银行"
          />
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
        <el-button type="primary" :loading="creating" @click="handleCreate"
          >确认创建</el-button
        >
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

    <!-- 归入未归置持仓对话框 -->
    <el-dialog
      v-model="showMigrateDialog"
      title="归入未归置持仓"
      width="420px"
      destroy-on-close
    >
      <p class="mb-4 text-sm" :style="{ color: 'var(--text-secondary)' }">
        当前有 {{ orphanGroup?.count || 0 }} 个已删除账户的持仓，合计
        <MoneyDisplay
          :value="orphanGroup?.total || 0"
          :show-sign="false"
          :auto-color="false"
          size="sm"
        />。请选择要归入的目标账户：
      </p>
      <el-select
        v-model="migrateTargetId"
        placeholder="请选择目标账户"
        filterable
        class="w-full"
      >
        <el-option
          v-for="ledger in allLedgers"
          :key="ledger.id"
          :label="ledger.name"
          :value="ledger.id"
          :disabled="ledger.id === 'orphan'"
        >
          <span>{{ ledger.name }}</span>
          <span class="ml-1 text-xs" :style="{ color: 'var(--text-tertiary)' }">
            {{ LEDGER_TYPE_SHORT[ledger.ledger_type] || ledger.ledger_type }}
          </span>
        </el-option>
      </el-select>
      <template #footer>
        <el-button @click="showMigrateDialog = false">取消</el-button>
        <el-button
          type="primary"
          :loading="migrating"
          :disabled="!migrateTargetId"
          @click="handleMigrate"
        >
          确认归入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { usePageRefresh } from "@/composables/usePageRefresh";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  getLedgers,
  getLedgersOverview,
  createLedger,
  migrateOrphanPositions,
  deleteOrphanPositions
} from "@/api/ledger";
import { getPortfolios } from "@/api/portfolio";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { getLedgerTypeLabel, LEDGER_TYPE_SHORT } from "@/constants";
import AccountFormFields from "./components/AccountFormFields.vue";
import DeleteLedgerDialog from "./components/DeleteLedgerDialog.vue";

defineOptions({ name: "AssetLedgers" });

const router = useRouter();

const loading = ref(true);
const allLedgers = ref<any[]>([]);
const overviewData = ref<{
  net_worth: number;
  liability_total: number;
  groups: any[];
}>({
  net_worth: 0,
  liability_total: 0,
  groups: []
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
  fee_config: null as any
});

const cashLedgers = computed(() =>
  allLedgers.value.filter((l: any) => l.ledger_type === "bank")
);
const portfolioList = ref<any[]>([]);
const deleteDialogVisible = ref(false);
const deletingAccount = ref<any>(null);

// 未归置持仓：归入 / 清理
const showMigrateDialog = ref(false);
const migrateTargetId = ref<number | null>(null);
const migrating = ref(false);
const cleaning = ref(false);

// 总资产（从 overview groups 汇总）
const totalAssets = computed(
  () =>
    overviewData.value?.groups?.reduce(
      (sum: number, g: any) => sum + (g.total || 0),
      0
    ) ?? 0
);

// 已删除账户的持仓信息（来自 overview）
const orphanGroup = computed(() =>
  overviewData.value?.groups?.find((g: any) => g.type === "deleted")
);

// 分组展示（按类型分组，并排序，追加未归置持仓）
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
        ledgers: []
      };
    }
    groups[type].count++;
    groups[type].total += ledger.total_market_value || 0;
    groups[type].ledgers.push(ledger);
  }

  const order = ["bank", "stock", "fund", "property"];
  const result = order.map(type => groups[type]).filter(Boolean);

  // 追加未归置分组（防止孤立资产出现缺漏）
  if (orphanGroup.value && orphanGroup.value.count > 0) {
    result.push({
      type: "deleted",
      label: "未归置持仓",
      total: orphanGroup.value.total,
      count: orphanGroup.value.count,
      ledgers: [
        {
          id: "orphan",
          name: "已删除账户的持仓",
          total_market_value: orphanGroup.value.total,
          position_count: orphanGroup.value.count,
          pnl: 0,
          ledger_type: "deleted",
          cash_balance: null
        }
      ]
    });
  }

  return result;
});

// 根据账户类型返回颜色
function getTypeColor(type: string): string {
  const map: Record<string, string> = {
    bank: "var(--tag-mint-green)",
    stock: "var(--color-danger)",
    fund: "var(--color-warning)",
    property: "var(--color-accent)",
    deleted: "var(--color-neutral)"
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
    fee_config: null
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
  if (ledger.id === "orphan") {
    // 未归置持仓是假卡片，无详情页，直接打开归入对话框
    openMigrateDialog();
    return;
  }
  router.push({ name: "LedgerDetail", params: { id: ledger.id } });
}

function openMigrateDialog() {
  migrateTargetId.value = null;
  showMigrateDialog.value = true;
}

async function handleMigrate() {
  if (!migrateTargetId.value) {
    ElMessage.warning("请选择目标账户");
    return;
  }
  migrating.value = true;
  try {
    const res = await migrateOrphanPositions(migrateTargetId.value);
    const total = (res as any)?.data?.total ?? 0;
    ElMessage.success(`已将 ${total} 项未归置数据归入目标账户`);
    showMigrateDialog.value = false;
    await fetchData();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "归入失败");
  } finally {
    migrating.value = false;
  }
}

async function handleOrphanCleanup() {
  try {
    await ElMessageBox.confirm(
      "确定清理全部未归置持仓吗？将同时删除关联的交易记录，此操作不可恢复。",
      "清理未归置持仓",
      {
        type: "warning",
        confirmButtonText: "确认清理",
        cancelButtonText: "取消"
      }
    );
  } catch {
    return; // 用户取消
  }
  cleaning.value = true;
  try {
    const res = await deleteOrphanPositions();
    const data = (res as any)?.data ?? {};
    ElMessage.success(
      `已清理 ${data.position_count ?? 0} 笔持仓、${data.asset_count ?? 0} 项资产、${data.transaction_count ?? 0} 笔交易`
    );
    await fetchData();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "清理失败");
  } finally {
    cleaning.value = false;
  }
}

async function fetchData() {
  loading.value = true;
  try {
    const [ledgersRes, overviewRes, portfolioRes] = await Promise.all([
      getLedgers(),
      getLedgersOverview(),
      getPortfolios()
    ]);
    allLedgers.value = (ledgersRes as any)?.data ?? [];
    overviewData.value = (overviewRes as any)?.data ?? {
      net_worth: 0,
      liability_total: 0,
      groups: []
    };
    portfolioList.value = (portfolioRes as any)?.data ?? [];
    lastUpdate.value = new Date().toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

// 只需一行，列表全自动刷新
usePageRefresh(() => {
  fetchData();
});

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
