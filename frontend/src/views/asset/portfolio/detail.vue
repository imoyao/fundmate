<template>
  <div
    class="portfolio-detail p-4 md:p-6 min-h-full"
    :style="{ backgroundColor: 'var(--bg-page)' }"
  >
    <!-- 返回按钮 -->
    <div class="mb-4">
      <el-button text @click="$router.push('/asset/portfolios')">
        <IconifyIconOffline icon="ep:arrow-left" class="mr-1" /> 返回组合列表
      </el-button>
    </div>

    <div
      v-if="loading"
      class="text-center py-20"
      :style="{ color: 'var(--text-tertiary)' }"
    >
      <p>加载中...</p>
    </div>

    <template v-else-if="portfolio">
      <!-- 标题与操作 -->
      <div class="flex justify-between items-start mb-6">
        <div>
          <h2
            class="text-2xl font-bold"
            :style="{ color: 'var(--text-primary)' }"
          >
            {{ portfolio.name }}
          </h2>
          <p class="text-sm mt-1" :style="{ color: 'var(--text-tertiary)' }">
            {{ portfolio.purpose || "未设定投资目的" }}
          </p>
        </div>
        <div class="flex gap-2">
          <el-button @click="openEditDialog">编辑</el-button>
          <el-popconfirm
            title="确定删除此组合？关联账户将自动解绑。"
            @confirm="handleDelete"
          >
            <template #reference>
              <el-button type="danger" text>删除</el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>

      <!-- 组合基本信息卡片 -->
      <el-row :gutter="16" class="mb-6">
        <el-col :span="8">
          <el-card shadow="never">
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              关联账户
            </p>
            <p
              class="text-xl font-bold"
              :style="{ color: 'var(--color-primary)' }"
            >
              {{ linkedLedgers.length }} 个
            </p>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="never">
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              目标收益率
            </p>
            <p
              class="text-xl font-bold"
              :style="{ color: 'var(--text-primary)' }"
            >
              {{
                portfolio.target_return != null
                  ? portfolio.target_return + "%"
                  : "--"
              }}
            </p>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="never">
            <p class="text-xs" :style="{ color: 'var(--text-tertiary)' }">
              基准指数
            </p>
            <p
              class="text-xl font-bold"
              :style="{ color: 'var(--text-primary)' }"
            >
              {{ portfolio.benchmark || "无" }}
            </p>
          </el-card>
        </el-col>
      </el-row>

      <!-- 组合收益率卡片 -->
      <div
        class="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 mb-6"
      >
        <div class="flex items-center justify-between mb-4">
          <h3 class="font-bold" :style="{ color: 'var(--text-primary)' }">
            组合收益 (XIRR)
          </h3>
          <el-button size="small" :loading="xirrLoading" @click="fetchXirr">
            <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 刷新
          </el-button>
        </div>
        <div v-if="xirrData" class="flex items-center gap-8">
          <div class="flex flex-col">
            <span class="text-gray-400 text-xs mb-1">年化收益率</span>
            <div class="text-3xl font-bold">
              <RiseFallText :value="(xirrData?.xirr ?? 0) * 100" />
            </div>
          </div>
          <div class="flex gap-6 ml-auto">
            <div class="flex flex-col">
              <span class="text-gray-400 text-xs mb-1">当前市值</span>
              <span class="text-lg font-bold">
                <MoneyDisplay
                  :value="xirrData?.current_value ?? 0"
                  :show-sign="false"
                />
              </span>
            </div>
            <div class="flex flex-col">
              <span class="text-gray-400 text-xs mb-1">总投入</span>
              <span class="text-lg font-bold">
                <MoneyDisplay
                  :value="xirrData?.total_invested ?? 0"
                  :show-sign="false"
                />
              </span>
            </div>
            <div class="flex flex-col">
              <span class="text-gray-400 text-xs mb-1">总收益</span>
              <span class="text-lg font-bold">
                <MoneyDisplay :value="xirrData?.total_return ?? 0" />
              </span>
            </div>
          </div>
        </div>
        <div v-else-if="!xirrLoading" class="text-center py-4 text-gray-400">
          点击刷新获取收益数据
        </div>
        <div v-else class="text-center py-4 text-gray-400">计算中...</div>
      </div>

      <!-- 持仓明细卡片 -->
      <div
        class="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 mb-6"
      >
        <h3 class="font-bold mb-4" :style="{ color: 'var(--text-primary)' }">
          持仓明细
        </h3>
        <el-table
          v-if="holdings.length"
          :data="pagedHoldings"
          stripe
          size="default"
          :default-sort="{ prop: 'market_value', order: 'descending' }"
          @sort-change="handleSortChange"
        >
          <el-table-column label="产品信息" min-width="180">
            <template #default="{ row }">
              <div class="product-cell">
                <span class="product-name">{{
                  row.name || row.symbol || "--"
                }}</span>
                <div class="product-code-row">
                  <span class="product-code"># {{ row.symbol || "--" }}</span>
                  <span
                    v-if="row.type_label"
                    class="ml-2 px-2 py-0.5 rounded-full text-xs type-tag-inline"
                    :style="{
                      backgroundColor: 'var(--bg-page)',
                      color: 'var(--text-secondary)'
                    }"
                    >{{ row.type_label }}</span
                  >
                </div>
              </div>
            </template>
          </el-table-column>

          <el-table-column
            label="市值"
            width="130"
            align="right"
            sortable
            prop="market_value"
          >
            <template #default="{ row }">
              <MoneyDisplay
                :value="row.market_value || 0"
                :show-sign="false"
                :auto-color="false"
              />
            </template>
          </el-table-column>
          <el-table-column
            label="盈亏"
            width="120"
            align="right"
            sortable
            prop="pnl"
          >
            <template #default="{ row }">
              <MoneyDisplay :value="row.pnl || 0" />
            </template>
          </el-table-column>
          <el-table-column
            label="盈亏率"
            width="90"
            align="right"
            sortable
            prop="pnl_rate"
          >
            <template #default="{ row }">
              <RiseFallText :value="row.pnl_rate || 0" />
            </template>
          </el-table-column>
          <el-table-column label="所属账户" width="120">
            <template #default="{ row }">{{ row.account_name }}</template>
          </el-table-column>
        </el-table>
        <div v-else class="text-center py-8 text-gray-400">暂无持仓数据</div>
        <div v-if="holdings.length > 0" class="flex justify-end mt-4">
          <el-pagination
            v-model:current-page="holdingsPage"
            :page-size="holdingsPageSize"
            layout="prev, pager, next"
            :total="holdings.length"
            small
          />
        </div>
      </div>

      <!-- 关联账户列表 -->
      <div class="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
        <h3 class="font-bold mb-4" :style="{ color: 'var(--text-primary)' }">
          关联账户
        </h3>
        <el-table
          v-if="linkedLedgers.length"
          :data="linkedLedgers"
          stripe
          size="default"
        >
          <el-table-column prop="name" label="账户名称" min-width="150" />
          <el-table-column label="账户类型" width="120">
            <template #default="{ row }">
              {{
                row.ledger_type === "cash"
                  ? "现金账户"
                  : row.ledger_type === "family"
                    ? "家庭账户"
                    : "通用账户"
              }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button text size="small" @click="goToLedger(row.id)"
                >查看</el-button
              >
            </template>
          </el-table-column>
        </el-table>
        <div v-else class="text-center py-8 text-gray-400">
          暂无账户关联此组合，请在账户编辑中选择关联。
        </div>
      </div>
    </template>

    <!-- 编辑对话框 -->
    <el-dialog
      v-model="editVisible"
      title="编辑组合"
      width="500px"
      destroy-on-close
    >
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="组合名称" required>
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="投资目的">
          <el-input v-model="editForm.purpose" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="目标收益率">
          <el-input-number
            v-model="editForm.target_return"
            :min="0"
            :max="100"
            :precision="2"
            controls-position="right"
            class="w-full"
          />
        </el-form-item>
        <el-form-item label="目标金额">
          <el-input-number
            v-model="editForm.target_amount"
            :min="0"
            :precision="2"
            controls-position="right"
            class="w-full"
          />
        </el-form-item>
        <el-form-item label="目标日期">
          <el-date-picker
            v-model="editForm.target_date"
            type="date"
            placeholder="选择日期"
            class="w-full"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item label="基准指数">
          <el-select
            v-model="editForm.benchmark"
            class="w-full"
            clearable
            filterable
            allow-create
          >
            <el-option label="沪深300" value="CSI300" />
            <el-option label="中证500" value="CSI500" />
            <el-option label="标普500" value="SPX" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联账户">
          <el-select
            v-model="selectedLedgerIds"
            multiple
            placeholder="选择关联此组合的账户"
            class="w-full"
            clearable
          >
            <el-option
              v-for="ledger in allLedgers"
              :key="ledger.id"
              :label="ledger.name"
              :value="ledger.id"
            >
              <div class="flex items-center justify-between w-full">
                <span>{{ ledger.name }}</span>
                <el-tag
                  v-if="ledger.portfolioName"
                  size="small"
                  type="info"
                  class="ml-2"
                >
                  已关联：{{ ledger.portfolioName }}
                </el-tag>
                <span v-else class="text-xs text-green-500 ml-2">待关联</span>
              </div>
            </el-option>
          </el-select>
          <p class="text-xs mt-1" style="color: var(--text-tertiary)">
            一个账户只能归属一个组合，重新分配后原组合将自动解绑。优先显示未关联账户。
          </p>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleUpdate"
          >保存</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  getPortfolio,
  updatePortfolio,
  deletePortfolio,
  getPortfolioHoldings
} from "@/api/portfolio";
import { getLedgers, updateLedger } from "@/api/ledger";
import { getPortfolioXirr } from "@/api/performance";
import type { XirrData } from "@/api/performance";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";

defineOptions({ name: "PortfolioDetail" });

const route = useRoute();
const router = useRouter();

const portfolioId = computed(() => Number(route.params.id));

const loading = ref(true);
const portfolio = ref<any>(null);
const linkedLedgers = ref<any[]>([]);
const xirrData = ref<XirrData | null>(null);
const xirrLoading = ref(false);
const sortProp = ref<string | null>(null);
const sortOrder = ref<"ascending" | "descending" | null>(null);

// 持仓相关
const holdings = ref<any[]>([]);
const holdingsPage = ref(1);
const holdingsPageSize = 20;

// 编辑相关
const editVisible = ref(false);
const saving = ref(false);
const allLedgers = ref<any[]>([]);
const selectedLedgerIds = ref<number[]>([]);
const editForm = ref({
  name: "",
  purpose: "",
  description: "",
  target_return: undefined as number | undefined,
  target_amount: undefined as number | undefined,
  target_date: "",
  benchmark: ""
});

const sortedHoldings = computed(() => {
  if (!sortProp.value || !sortOrder.value) {
    return [...holdings.value]; // 默认不排序，保持原始顺序
  }
  const sorted = [...holdings.value];
  sorted.sort((a, b) => {
    const valA = a[sortProp.value!] ?? 0;
    const valB = b[sortProp.value!] ?? 0;
    return sortOrder.value === "ascending" ? valA - valB : valB - valA;
  });
  return sorted;
});

function handleSortChange(sort: {
  prop: string;
  order: "ascending" | "descending" | null;
}) {
  sortProp.value = sort.order ? sort.prop : null;
  sortOrder.value = sort.order || null;
  holdingsPage.value = 1; // 排序后重置到第一页
}

// ---------- 数据加载 ----------
async function fetchDetail() {
  loading.value = true;
  try {
    const res = await getPortfolio(portfolioId.value);
    portfolio.value = res.data;
    await fetchLinkedLedgers();
  } catch (e) {
    ElMessage.error("加载组合信息失败");
    router.replace("/asset/portfolios");
  } finally {
    loading.value = false;
  }
}

async function fetchLinkedLedgers() {
  try {
    const res = await getLedgers();
    const all = (res as any)?.data?.data ?? (res as any)?.data ?? [];
    linkedLedgers.value = all.filter(
      (l: any) => l.portfolio_id === portfolioId.value
    );
  } catch (e) {
    linkedLedgers.value = [];
  }
  await fetchHoldings();
}

async function fetchHoldings() {
  if (linkedLedgers.value.length === 0) {
    holdings.value = [];
    return;
  }
  try {
    const res = await getPortfolioHoldings(portfolioId.value);
    holdings.value = (res as any)?.data ?? [];
  } catch (e) {
    holdings.value = [];
  }
}

async function fetchXirr() {
  xirrLoading.value = true;
  try {
    const res = await getPortfolioXirr("portfolio", portfolioId.value);
    xirrData.value = res.data;
  } catch (e) {
    ElMessage.error("获取收益率失败");
  } finally {
    xirrLoading.value = false;
  }
}

// ---------- 编辑功能 ----------
import { getPortfolios } from "@/api/portfolio"; // 确保导入

async function openEditDialog() {
  if (!portfolio.value) return;

  editForm.value = {
    name: portfolio.value.name,
    purpose: portfolio.value.purpose || "",
    description: portfolio.value.description || "",
    target_return: portfolio.value.target_return,
    target_amount: portfolio.value.target_amount,
    target_date: portfolio.value.target_date || "",
    benchmark: portfolio.value.benchmark || ""
  };

  try {
    // 并行加载所有账户和组合
    const [ledgerRes, portfolioRes] = await Promise.all([
      getLedgers(),
      getPortfolios()
    ]);

    const rawLedgers =
      (ledgerRes as any)?.data?.data ?? (ledgerRes as any)?.data ?? [];
    const allPortfolios =
      (portfolioRes as any)?.data?.data ?? (portfolioRes as any)?.data ?? [];

    // 构建组合 ID -> 名称映射（排除当前正在编辑的组合，因为它是自己）
    const portfolioNameMap: Record<number, string> = {};
    allPortfolios.forEach((p: any) => {
      if (p.id !== portfolioId.value) {
        portfolioNameMap[p.id] = p.name;
      }
    });

    // 给每个账户附加 portfolioName，并排序
    allLedgers.value = rawLedgers
      .map((l: any) => ({
        ...l,
        portfolioName: l.portfolio_id
          ? portfolioNameMap[l.portfolio_id] || "未知组合"
          : null
      }))
      .sort((a: any, b: any) => {
        // 未关联的排在前面
        if (a.portfolioName && !b.portfolioName) return 1;
        if (!a.portfolioName && b.portfolioName) return -1;
        // 同类型按名称排序
        return a.name.localeCompare(b.name, "zh-Hans");
      });
  } catch (e) {
    allLedgers.value = [];
  }

  selectedLedgerIds.value = linkedLedgers.value.map((l: any) => l.id);
  editVisible.value = true;
}

async function handleUpdate() {
  if (!editForm.value.name.trim()) {
    ElMessage.warning("名称不能为空");
    return;
  }
  saving.value = true;
  try {
    // 1. 更新组合基本信息
    await updatePortfolio(portfolioId.value, editForm.value);

    // 更新账户关联
    const previousIds = linkedLedgers.value.map((l: any) => l.id);
    const toUnlink = previousIds.filter(
      (id: number) => !selectedLedgerIds.value.includes(id)
    );
    const toLink = selectedLedgerIds.value.filter(
      (id: number) => !previousIds.includes(id)
    );

    for (const id of toUnlink) {
      await updateLedger(id, { portfolio_id: null });
    }
    for (const id of toLink) {
      await updateLedger(id, { portfolio_id: portfolioId.value });
    }

    ElMessage.success("组合已更新");
    editVisible.value = false;
    await fetchDetail();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "更新失败");
  } finally {
    saving.value = false;
  }
}

async function handleDelete() {
  try {
    await deletePortfolio(portfolioId.value);
    ElMessage.success("组合已删除");
    router.push("/asset/portfolios");
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || "删除失败");
  }
}

function goToLedger(id: number) {
  router.push(`/asset/ledgers/${id}`);
}

// ---------- 分页 ----------
const pagedHoldings = computed(() => {
  const start = (holdingsPage.value - 1) * holdingsPageSize;
  return sortedHoldings.value.slice(start, start + holdingsPageSize); // ← 这里
});

// ---------- 生命周期 ----------
onMounted(async () => {
  await fetchDetail();
  if (portfolio.value) {
    fetchXirr(); // 自动加载收益率
  }
});
</script>

<style scoped>
.portfolio-detail {
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}

/* 产品单元格样式（与导入预览页保持一致） */
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
  gap: 6px;
  align-items: center;
}

.product-code {
  font-size: 12px;
  color: var(--text-tertiary);
}

.type-tag-inline {
  height: 20px;
  padding: 0 6px;
  font-size: 11px;
  line-height: 20px;
  color: #fff;
  border: none;
}

.el-select-dropdown__item {
  height: auto;
  padding: 5px 12px;
}
</style>
