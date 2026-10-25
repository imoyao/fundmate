<template>
  <div class="portfolio-detail p-4 md:p-6 min-h-full">
    <!-- 返回按钮 -->
    <div class="mb-4">
      <el-button text @click="router.push('/asset/portfolios')">
        <IconifyIconOffline icon="ep:arrow-left" class="mr-1" /> 返回组合列表
      </el-button>
    </div>

    <PageSkeleton v-if="loading" :cards="3" :chart-cols="1" :table-rows="4" />

    <template v-else-if="portfolio">
      <!-- 页头统一走 PageHeaderBar（2026-10-25 前是手写 h2 + tailwind，
           与全站页头规格 --text-display/300 不一致） -->
      <PageHeaderBar
        :title="portfolio.name"
        :subtitle="portfolio.purpose || '未设定投资目的'"
      >
        <template #action>
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
        </template>
      </PageHeaderBar>

      <!-- 页内导航：<xl 顶部锚点胶囊；xl+ 由正文右侧的目录 rail（PageToc）接管。
           两级互斥，条目由 usePageNav 按 DOM 里真实渲染的 nav-* 锚点动态生成，
           v-if 整块消失的区块（如无货基数据）自动不留死链。 -->
      <PageNav
        v-if="navItems.length > 1"
        :items="navItems"
        :active-id="navActiveId"
        @navigate="goToNavSection"
      />

      <div class="portfolio-detail__body">
        <div ref="pageMain" class="portfolio-detail__main">
          <!-- 基础信息指标卡（hero 概览，不进目录） -->
          <MetricGrid class="mb-6">
            <MetricCard
              title="关联账户"
              :value="linkedLedgers.length"
              unit="个"
            />
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

          <!-- 组合收益（#871 三口径卡，#980 拆出） -->
          <PortfolioReturnCard id="nav-return" :portfolio-id="portfolioId" />

          <!-- 货币基金收益（组合维度：按 ledger_id 聚合关联账户；与 XIRR 并列，不与 XIRR 相加） -->
          <PortfolioMoneyFundCard
            id="nav-money-fund"
            :portfolio-id="portfolioId"
          />

          <!-- #2135 收益归因（组合口径 = 成员账本继承 + 持仓显式归属）。
               2026-10-25 自「持仓穿透」之后上移：动线收敛为「表现（收益 / 货基）
               → 归因（收益从哪来）→ 结构（穿透）→ 明细」，与产品详情页
               「表现 → 归因」的既有口径一致。根节点是 template 分片
               （SectionHeader + CardBlock），fallthrough 落不上 id，故包一层。 -->
          <div id="nav-attribution">
            <PnlAttribution :portfolio-id="portfolioId" />
          </div>

          <!-- 持仓穿透（#870 B2：钱最终压在哪些行业/个股） -->
          <div class="mb-6">
            <PenetrationPanel id="nav-penetration" />
          </div>

          <!-- 组合风格构成（#2603：按市值加权的 8 分类风格暴露）。
               与穿透同属「结构」段：穿透说钱压在哪些行业/个股，风格说这些持仓
               在风格维度上的偏斜。 -->
          <div class="mb-6">
            <PortfolioStylePanel id="nav-style" />
          </div>

          <!-- 持仓明细（#1104：盈亏双线 —— 已确认 / 当日预估） -->
          <PortfolioHoldingsCard id="nav-holdings" :holdings="holdings" />

          <!-- 持仓重叠度（#2604：组合内基金重仓股重合程度）。
               紧跟明细：先看买了什么，再看这些基金之间重不重。 -->
          <div class="mb-6">
            <HoldingOverlapPanel id="nav-overlap" />
          </div>

          <!-- 未归档持仓（ledger_id=null，如探市录入）：就地归档到本组合账户 -->
          <PortfolioUnarchivedCard
            id="nav-unarchived"
            :ledgers="linkedLedgers"
            @archived="fetchHoldings"
          />

          <!-- 关联账户 -->
          <PortfolioLinkedLedgersCard
            id="nav-ledgers"
            :ledgers="linkedLedgers"
          />
        </div>

        <!-- xl+ 右目录 rail：与顶部胶囊共用 items/activeId（usePageNav 下发） -->
        <PageToc
          v-if="navItems.length > 1"
          :items="navItems"
          :active-id="navActiveId"
          @navigate="goToNavSection"
        />
      </div>
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
import PageHeaderBar from "@/components/PageHeaderBar/index.vue";
import PageNav from "@/components/PageNav/index.vue";
import PageToc from "@/components/PageToc/index.vue";
import PageSkeleton from "@/components/PageSkeleton/index.vue";
import PnlAttribution from "@/components/PnlAttribution/index.vue";
import PortfolioEditDialog from "@/components/PortfolioEditDialog/index.vue";
import { usePageNav } from "@/composables/usePageNav";
import PenetrationPanel from "./PenetrationPanel.vue";
import PortfolioStylePanel from "./PortfolioStylePanel.vue";
import PortfolioReturnCard from "./PortfolioReturnCard.vue";
import PortfolioMoneyFundCard from "./portfolioDetail/PortfolioMoneyFundCard.vue";
import PortfolioHoldingsCard from "./portfolioDetail/PortfolioHoldingsCard.vue";
import PortfolioUnarchivedCard from "./portfolioDetail/PortfolioUnarchivedCard.vue";
import HoldingOverlapPanel from "./HoldingOverlapPanel.vue";
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
 * #980 拆分后只留「页面骨架」：PageHeaderBar 页头、四张指标卡、页内导航
 * （PageNav / PageToc，2026-10-25 接入）与九个纵向区块（收益 / 货基 / 归因 /
 * 穿透 / 风格 / 明细 / 重叠 / 未归档 / 关联账户）、编辑对话框。四张表与两块取数各自成组件：
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

// ---------- 页内导航（2026-10-25）----------
// 纵向区块 9 个、明显超一屏，符合 components.md 的 PageToc 接入判据。
// state / scroll-spy 全在共享 usePageNav 里，本文件只给锚点 → 标签映射。
const pageMain = ref<HTMLElement>();
const NAV_LABELS: Record<string, string> = {
  "nav-return": "组合收益",
  "nav-money-fund": "货币基金收益",
  "nav-attribution": "收益归因",
  "nav-penetration": "持仓穿透",
  "nav-style": "组合风格",
  "nav-holdings": "持仓明细",
  "nav-overlap": "持仓重叠度",
  "nav-unarchived": "未归档持仓",
  "nav-ledgers": "关联账户"
};
const {
  items: navItems,
  activeId: navActiveId,
  goTo: goToNavSection
} = usePageNav(pageMain, { labels: NAV_LABELS });

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

/* 页内导航两级布局（components.md PageToc）：<xl 单列（胶囊在正文上方整条横跨）；
   xl+ 主列 + 160px 右目录 rail，列间距 20px（产品详情页同款宽度账）。 */
.portfolio-detail__body {
  display: flex;
  gap: var(--space-5);
}

.portfolio-detail__main {
  flex: 1;
  min-width: 0;
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
