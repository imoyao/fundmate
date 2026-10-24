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
      style="color: var(--text-tertiary-ink)"
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
          <p class="text-sm mt-1" style="color: var(--text-tertiary-ink)">
            {{ portfolio.purpose || "未设定投资目的" }}
          </p>
        </div>
        <div class="flex gap-2">
          <el-button @click="editVisible = true">编辑</el-button>
          <el-popconfirm
            title="确定删除此组合？关联账户将自动解绑。"
            confirm-button-text="删除"
            cancel-button-text="取消"
            popper-class="danger-popconfirm"
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
        <MetricCard
          title="基准指数"
          :value="benchmarkLabel"
          :caption="benchmarkCaption"
        />
        <!-- #2134：区间超额（近 90 天 vs 基准同期）；缺数据由 MetricCard 显示「--」，不造 0 -->
        <MetricCard
          title="超额收益"
          :value="excessValue"
          unit="%"
          :caption="excessCaption"
          :value-color="excessColor"
        />
      </MetricGrid>

      <!-- 组合收益（#871 三口径卡，#980 拆出）；v-if=portfolio 复刻拆出前「组合存在才拉」 -->
      <PortfolioReturnCard v-if="portfolio" :portfolio-id="portfolioId" />

      <!-- 货基收益（组合维度：按 ledger_id 聚合关联账户；与 XIRR 并列，不与 XIRR 相加） -->
      <PortfolioMoneyFundCard :portfolio-id="portfolioId" />

      <!-- 持仓穿透（#870 B2：钱最终压在哪些行业/个股；#2595 组合级口径） -->
      <div class="mb-6">
        <PenetrationPanel :portfolio-id="portfolioId" />
      </div>

      <!-- #2135：收益归因（组合口径 = 成员账本继承 + 持仓显式归属） -->
      <PnlAttribution :portfolio-id="portfolioId" />

      <!-- 持仓明细（#1104：盈亏双线 —— 已确认 / 当日预估） -->
      <PortfolioHoldingsCard :holdings="holdings" />

      <!-- 未归档持仓（ledger_id=null，如探市录入）：就地归档到本组合账户 -->
      <PortfolioUnarchivedCard
        :ledgers="linkedLedgers"
        @archived="fetchHoldings"
      />

      <!-- 关联账户 -->
      <PortfolioLinkedLedgersCard :ledgers="linkedLedgers" />
    </template>

    <!-- 编辑对话框（拆出的共有组件） -->
    <PortfolioEditDialog
      v-model="editVisible"
      :portfolio="portfolio"
      :linked-ledger-ids="linkedLedgers.map(l => l.id)"
      @saved="fetchDetail"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { IconifyIconOffline } from "@/components/ReIcon";
import {
  getPortfolio,
  deletePortfolio,
  getPortfolioHoldings,
  type PortfolioDetail
} from "@/api/portfolio";
import { getLedgers } from "@/api/ledger";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import PnlAttribution from "@/components/PnlAttribution/index.vue";
import PortfolioEditDialog from "@/components/PortfolioEditDialog/index.vue";
import PenetrationPanel from "@/components/PenetrationPanel/index.vue";
import PortfolioReturnCard from "./PortfolioReturnCard.vue";
import PortfolioMoneyFundCard from "./portfolioDetail/PortfolioMoneyFundCard.vue";
import PortfolioHoldingsCard from "./portfolioDetail/PortfolioHoldingsCard.vue";
import PortfolioUnarchivedCard from "./portfolioDetail/PortfolioUnarchivedCard.vue";
import PortfolioLinkedLedgersCard from "./portfolioDetail/PortfolioLinkedLedgersCard.vue";
import { usePortfolioExcess } from "./portfolioDetail/usePortfolioExcess";
import {
  type LinkedLedger,
  type PortfolioHolding,
  unwrapList
} from "./portfolioDetail/portfolioDetailModel";

/**
 * 组合详情页（/asset/portfolios/:id）。
 *
 * #980 拆分后只留「页面骨架」：标题与操作、四张指标卡、两个自有子页面区块
 * （收益卡 / 穿透）、收益归因、编辑对话框。四张表与两块取数各自成组件：
 *
 * - `PortfolioHoldingsCard`：持仓明细（排序 + 前端分页 + 盈亏双线估值接线）
 * - `PortfolioUnarchivedCard`：未归档持仓 + 归档对话框（自含取数）
 * - `PortfolioLinkedLedgersCard`：关联账户
 * - `PortfolioMoneyFundCard`：货基收益（自含取数）
 *
 * 区间超额（#2134）的五段派生文案进 `usePortfolioExcess`，接口信封解包、
 * 排序分页、账户类型文案进 `portfolioDetailModel.ts`（纯函数）。
 */
defineOptions({ name: "PortfolioDetail" });

const route = useRoute();
const router = useRouter();

const portfolioId = computed(() => Number(route.params.id));

const loading = ref(true);
const portfolio = ref<PortfolioDetail | null>(null);
const linkedLedgers = ref<LinkedLedger[]>([]);

// 持仓相关
const holdings = ref<PortfolioHolding[]>([]);

// 编辑相关
const editVisible = ref(false);

// #871：组合收益（三口径）已拆为 PortfolioReturnCard——自含取数与口径切换，
// 父页只传 portfolioId（#980 上帝页面拆分）。

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

// ---------- 区间收益 vs 基准（#2134）----------
const {
  fetchExcess,
  benchmarkLabel,
  benchmarkCaption,
  excessValue,
  excessColor,
  excessCaption
} = usePortfolioExcess(portfolioId, portfolio);

// ---------- 删除 ----------
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

// ---------- 生命周期 ----------
onMounted(async () => {
  await fetchDetail();
  if (portfolio.value) {
    void fetchExcess(); // #2134 区间收益 vs 基准（近 90 天）
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

/* XIRR 指标区：组合收益卡与组合货基卡共用——两张卡都已拆为子组件（#980），
   跨子组件的规则统一用 :deep() 包裹（作用域仍限定在本页树内，
   welcome/index.vue 同款约定）。注意：搬进任一张卡都会让另一张失去样式。 */
:deep(.xirr-grid) {
  display: flex;
  gap: var(--space-5);
  align-items: center;
}

:deep(.xirr-item) {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

:deep(.xirr-item--ml) {
  margin-left: auto;
}

:deep(.xirr-label) {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

:deep(.xirr-value) {
  font-size: var(--text-body);
  font-weight: 700;
  color: var(--text-primary);
}

:deep(.xirr-value--lg) {
  font-size: var(--text-display);
  font-weight: 700;
  line-height: 1.1;
}

:deep(.xirr-empty) {
  padding: var(--space-compact);
  color: var(--text-tertiary-ink);
  text-align: center;
}
</style>
