<template>
  <div class="portfolio-detail p-4 md:p-6 min-h-full">
    <!-- 返回按钮 -->
    <div class="mb-4">
      <el-button text @click="router.push('/asset/portfolios')">
        <IconifyIconOffline icon="ep:arrow-left" class="mr-1" /> 返回组合列表
      </el-button>
    </div>

    <div
      v-if="loading"
      class="text-center py-20"
      style="color: var(--text-tertiary)"
    >
      <p>加载中...</p>
    </div>

    <template v-else-if="portfolio">
      <!-- 标题与操作 -->
      <div class="flex justify-between items-start mb-6">
        <div>
          <h2 class="text-2xl font-bold" style="color: var(--text-primary)">
            {{ portfolio.name }}
          </h2>
          <p class="text-sm mt-1" style="color: var(--text-tertiary)">
            {{ portfolio.purpose || "未设定投资目的" }}
          </p>
        </div>
        <div class="flex gap-2">
          <el-button @click="editVisible = true">编辑</el-button>
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

      <!-- 基础信息指标卡 -->
      <MetricGrid class="mb-6">
        <MetricCard title="关联账户" :value="linkedLedgers.length" unit="个" />
        <MetricCard
          title="目标收益率"
          :value="portfolio.target_return ?? null"
          unit="%"
        />
        <MetricCard title="基准指数" :value="portfolio.benchmark || '--'" />
      </MetricGrid>

      <!-- 组合收益 (XIRR) -->
      <CardBlock class="mb-6">
        <SectionHeader title="组合收益 (XIRR)">
          <template #action>
            <el-button size="small" :loading="xirrLoading" @click="fetchXirr">
              <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 刷新
            </el-button>
          </template>
        </SectionHeader>
        <div v-if="xirrData" class="xirr-grid">
          <div class="xirr-item">
            <span class="xirr-label">年化收益率</span>
            <div class="xirr-value--lg">
              <RiseFallText :value="xirrData.xirr * 100" />
            </div>
          </div>
          <div class="xirr-item xirr-item--ml">
            <span class="xirr-label">当前市值</span>
            <div class="xirr-value">
              <MoneyDisplay
                :value="xirrData.current_value"
                :show-sign="false"
              />
            </div>
          </div>
          <div class="xirr-item">
            <span class="xirr-label">总投入</span>
            <div class="xirr-value">
              <MoneyDisplay
                :value="xirrData.total_invested"
                :show-sign="false"
              />
            </div>
          </div>
          <div class="xirr-item">
            <span class="xirr-label">总收益</span>
            <div class="xirr-value">
              <MoneyDisplay :value="xirrData.total_return" />
            </div>
          </div>
        </div>
        <div v-else-if="!xirrLoading" class="xirr-empty">
          点击刷新获取收益数据
        </div>
        <div v-else class="xirr-empty">计算中...</div>
      </CardBlock>

      <!-- 持仓明细 -->
      <CardBlock class="mb-6">
        <SectionHeader title="持仓明细" />
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
              <ProductDisplay
                :name="row.name || ''"
                :symbol="row.symbol || ''"
                :type-label="row.type_label || ''"
              />
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
          <el-table-column label="来源" width="110">
            <template #default="{ row }">
              <el-tag
                v-if="positionSourceLabel(row.source)"
                size="small"
                type="info"
              >
                {{ positionSourceLabel(row.source) }}
              </el-tag>
              <span v-else style="color: var(--text-tertiary)">—</span>
            </template>
          </el-table-column>
          <el-table-column label="所属账户" width="120">
            <template #default="{ row }">{{
              row.account_name || "未归档"
            }}</template>
          </el-table-column>
        </el-table>
        <div v-else class="table-empty">
          暂无持仓数据，可先在各账户新建持仓后再关联到此组合。
        </div>
        <div v-if="holdings.length > 0" class="flex justify-end mt-4">
          <el-pagination
            v-model:current-page="holdingsPage"
            :page-size="holdingsPageSize"
            layout="prev, pager, next"
            :total="holdings.length"
            small
          />
        </div>
      </CardBlock>

      <!-- 未归档持仓（ledger_id=null，如探市录入）：就地归档到本组合账户 -->
      <CardBlock class="mb-6">
        <SectionHeader title="未归档持仓">
          <template #action>
            <el-button size="small" :loading="false" @click="fetchUnarchived">
              <IconifyIconOffline icon="ep:refresh" class="mr-1" /> 刷新
            </el-button>
          </template>
        </SectionHeader>
        <el-table v-if="unarchived.length > 0" :data="unarchived" border>
          <el-table-column label="产品信息" min-width="180">
            <template #default="{ row }">
              <ProductDisplay
                :name="row.name || ''"
                :symbol="row.symbol || ''"
                :type-label="row.type_label || ''"
              />
            </template>
          </el-table-column>
          <el-table-column label="来源" width="110">
            <template #default="{ row }">
              <el-tag
                v-if="positionSourceLabel(row.source)"
                size="small"
                type="info"
              >
                {{ positionSourceLabel(row.source) }}
              </el-tag>
              <span v-else style="color: var(--text-tertiary)">—</span>
            </template>
          </el-table-column>
          <el-table-column label="市值" width="130" align="right">
            <template #default="{ row }">
              <MoneyDisplay
                :value="row.market_value || 0"
                :show-sign="false"
                :auto-color="false"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="center">
            <template #default="{ row }">
              <el-button
                size="small"
                type="primary"
                @click="openArchive(row.id)"
              >
                归档
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-else class="table-empty">
          暂无未归档持仓。探市录入或导入未绑定账户的持仓会出现在这里。
        </div>
      </CardBlock>

      <!-- 关联账户 -->
      <CardBlock>
        <SectionHeader title="关联账户" />
        <el-table
          v-if="linkedLedgers.length"
          :data="linkedLedgers"
          stripe
          size="default"
        >
          <el-table-column prop="name" label="账户名称" min-width="150" />
          <el-table-column label="账户类型" width="120">
            <template #default="{ row }">
              {{ ledgerTypeLabel(row.ledger_type) }}
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
        <div v-else class="table-empty">
          暂无账户关联此组合，请在账户编辑中选择关联。
        </div>
      </CardBlock>
    </template>

    <!-- 编辑对话框（拆出的共有组件） -->
    <PortfolioEditDialog
      v-model="editVisible"
      :portfolio="portfolio"
      :linked-ledger-ids="linkedLedgers.map(l => l.id)"
      @saved="fetchDetail"
    />

    <!-- 归档对话框：将未归档持仓绑定到本组合下某账户 -->
    <el-dialog v-model="archiveVisible" title="归档到账户" width="420px">
      <el-form label-width="80px">
        <el-form-item label="目标账户">
          <el-select
            v-model="archiveLedgerId"
            placeholder="选择账户"
            style="width: 100%"
          >
            <el-option
              v-for="l in linkedLedgers"
              :key="l.id"
              :label="l.name"
              :value="l.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="archiveVisible = false">取消</el-button>
        <el-button type="primary" :loading="archiving" @click="confirmArchive">
          确定归档
        </el-button>
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
  deletePortfolio,
  getPortfolioHoldings,
  type PortfolioDetail
} from "@/api/portfolio";
import { getPortfolioXirr, type XirrData } from "@/api/performance";
import { getLedgers, type LedgerItem } from "@/api/ledger";
import { getPositions, updatePosition } from "@/api/positions";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import PortfolioEditDialog from "@/components/PortfolioEditDialog/index.vue";
import { useEnumLabels } from "@/composables/useEnumLabels";

defineOptions({ name: "PortfolioDetail" });

/** 组合持仓（后端 /api/portfolios/{id}/holdings/ 返回，字段按现有代码使用为准） */
interface PortfolioHolding {
  symbol?: string;
  name?: string | null;
  type_label?: string;
  market_value?: number;
  pnl?: number;
  pnl_rate?: number;
  account_name?: string;
  source?: string | null;
}

/** 关联账户：账户 + 组合关联字段 */
interface LinkedLedger extends LedgerItem {
  portfolio_id?: number | null;
}

const route = useRoute();
const router = useRouter();

const portfolioId = computed(() => Number(route.params.id));

const loading = ref(true);
const portfolio = ref<PortfolioDetail | null>(null);
const linkedLedgers = ref<LinkedLedger[]>([]);
const xirrData = ref<XirrData | null>(null);
const xirrLoading = ref(false);
const sortProp = ref<string | null>(null);
const sortOrder = ref<"ascending" | "descending" | null>(null);

// 枚举中文标签（来源等），从后端 /api/utils/enums 单一真相源获取
const { ensure: ensureEnums, positionSourceLabel } = useEnumLabels();

// 持仓相关
const holdings = ref<PortfolioHolding[]>([]);
const holdingsPage = ref(1);
const holdingsPageSize = 20;

// 未归档持仓（ledger_id=null，如探市录入）：就地归档到本组合下某账户
const unarchived = ref<PortfolioHolding[]>([]);
const archiveVisible = ref(false);
const archiveTargetId = ref<number | null>(null);
const archiveLedgerId = ref<number | null>(null);
const archiving = ref(false);

async function fetchUnarchived() {
  try {
    const res = await getPositions({ ledger_id: "null" });
    unarchived.value = unwrapList<PortfolioHolding>(res);
  } catch {
    unarchived.value = [];
  }
}

function openArchive(id: number) {
  archiveTargetId.value = id;
  archiveLedgerId.value = linkedLedgers.value[0]?.id ?? null;
  archiveVisible.value = true;
}

async function confirmArchive() {
  if (!archiveTargetId.value || !archiveLedgerId.value) {
    ElMessage.warning("请选择归档目标账户");
    return;
  }
  archiving.value = true;
  try {
    await updatePosition(archiveTargetId.value, {
      ledger_id: archiveLedgerId.value
    });
    ElMessage.success("已归档");
    archiveVisible.value = false;
    await fetchUnarchived();
    await fetchHoldings();
  } catch {
    ElMessage.error("归档失败");
  } finally {
    archiving.value = false;
  }
}

// 编辑相关
const editVisible = ref(false);

/** 从接口信封（{ data, message } 或 { data: { data, message } }）中安全取出列表 */
function unwrapList<T>(res: unknown): T[] {
  const d = (res as { data?: unknown })?.data;
  if (Array.isArray(d)) return d as T[];
  const nested = (d as { data?: unknown })?.data;
  return Array.isArray(nested) ? (nested as T[]) : [];
}

const sortedHoldings = computed(() => {
  if (!sortProp.value || !sortOrder.value) {
    return [...holdings.value]; // 默认保持原始顺序
  }
  const sorted = [...holdings.value];
  sorted.sort((a, b) => {
    const key = sortProp.value as keyof PortfolioHolding;
    const valA = Number(a[key] ?? 0);
    const valB = Number(b[key] ?? 0);
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
    portfolio.value = res.data as PortfolioDetail;
    await fetchLinkedLedgers();
  } catch {
    ElMessage.error("加载组合信息失败");
    router.replace("/asset/portfolios");
  } finally {
    loading.value = false;
  }
}

async function fetchLinkedLedgers() {
  try {
    const res = await getLedgers();
    linkedLedgers.value = unwrapList<LinkedLedger>(res).filter(
      l => l.portfolio_id === portfolioId.value
    );
  } catch {
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
    holdings.value = unwrapList<PortfolioHolding>(res);
  } catch {
    holdings.value = [];
  }
}

async function fetchXirr() {
  xirrLoading.value = true;
  try {
    const res = await getPortfolioXirr("portfolio", portfolioId.value);
    xirrData.value = res.data;
  } catch {
    ElMessage.error("获取收益率失败");
  } finally {
    xirrLoading.value = false;
  }
}

// ---------- 删除 / 跳转 ----------
async function handleDelete() {
  try {
    await deletePortfolio(portfolioId.value);
    ElMessage.success("组合已删除");
    router.push("/asset/portfolios");
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "删除失败");
  }
}

function goToLedger(id: number) {
  router.push(`/asset/ledgers/${id}`);
}

function ledgerTypeLabel(type: string): string {
  if (type === "cash") return "现金账户";
  if (type === "family") return "家庭账户";
  return "通用账户";
}

// ---------- 分页 ----------
const pagedHoldings = computed(() => {
  const start = (holdingsPage.value - 1) * holdingsPageSize;
  return sortedHoldings.value.slice(start, start + holdingsPageSize);
});

// ---------- 生命周期 ----------
onMounted(async () => {
  void ensureEnums(); // 预热枚举标签缓存（来源徽标）
  await fetchDetail();
  if (portfolio.value) {
    void fetchXirr(); // 自动加载收益率
    await fetchUnarchived(); // 加载未归档持仓（探市录入等）
  }
});
</script>

<style scoped>
.portfolio-detail {
  /* 继承全局字体 token，避免与站内其它页面字体不一致（design-tokens.css --font-ui） */
  font-family: var(--font-ui);

  /* 数字等宽对齐：消除金额/收益率宽度抖动（design.md「数字等宽对齐」） */
  font-variant-numeric: tabular-nums;
}

/* XIRR 指标区 */
.xirr-grid {
  display: flex;
  gap: var(--space-5);
  align-items: center;
}

.xirr-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.xirr-item--ml {
  margin-left: auto;
}

.xirr-label {
  font-size: 13px;
  color: var(--text-tertiary);
}

.xirr-value {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.xirr-value--lg {
  font-size: 32px;
  font-weight: 700;
  line-height: 1.1;
}

.xirr-empty {
  padding: var(--space-4);
  color: var(--text-tertiary);
  text-align: center;
}

/* 空状态 */
.table-empty {
  padding: var(--space-6);
  color: var(--text-tertiary);
  text-align: center;
}
</style>
