<template>
  <!-- 账户信息头部 -->
  <div class="mb-6 flex items-center justify-between">
    <div>
      <h2 class="text-2xl font-bold" :style="{ color: 'var(--text-primary)' }">
        {{ p.accountName }}
      </h2>
      <div class="flex items-center gap-2 mt-1">
        <el-tag size="small" type="info" round>{{ p.subTitle }}</el-tag>
        <template v-if="p.summaryData?.portfolio_name">
          <span class="text-xs" :style="{ color: 'var(--text-tertiary-ink)' }">
            · 组合: {{ p.summaryData.portfolio_name }}</span
          >
        </template>
      </div>
    </div>
  </div>

  <!-- 温柔提醒（#1133 §4）：中性信息色、拟人化、非阻断；可选「去对账/忽略」，绝不强制。
       #2730 起壳由 SoftBanner 的 info 档承担；`role="note"` **显式传入** —— 组件默认按色族
       推导（info→status 礼貌播报 / warning·danger→alert 打断播报），而这里原文就是
       `role="note"` 的静态注记（不排队播报），迁入时不能被无意识升格成 live region。 -->
  <transition name="el-fade-in">
    <SoftBanner
      v-if="p.visibleConsistencyItems.length > 0"
      class="soft-reconcile-banner"
      variant="info"
      role="note"
      icon="ep:info-filled"
    >
      <p class="soft-reconcile-banner__title">
        这本账本的持仓快照截至
        {{
          p.visibleConsistencyItems[0].snapshot_date
        }}，快照日之后仍有交易记录；如与流水对不上，请去对账工作台核对是否需要补录。
      </p>
      <p class="soft-reconcile-banner__detail">
        共
        {{ p.visibleConsistencyItems.length }}
        笔持仓可能滞后，去对账工作台可统一核对。
      </p>
      <template #actions>
        <el-button size="small" type="primary" plain @click="p.goReconcile">
          去对账
        </el-button>
        <el-button size="small" text @click="p.dismissAllConsistency">
          忽略
        </el-button>
      </template>
    </SoftBanner>
  </transition>

  <!-- 账本概览（对齐「家庭资产看板」范式：SectionHeader + CardBlock，左指标 / 右资产构成）。
       #2739：锚点挂在标题行上（SectionHeader 单根 ⇒ id 经 fallthrough 落下），
       与本页其余锚点同一手法——锚点 = 区块标题行的顶边。 -->
  <SectionHeader id="nav-overview" title="账本概览" />
  <CardBlock class="mb-6">
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
      <!-- 左栏：核心指标（总资产 + 持仓盈亏 / 持仓与余额） -->
      <div
        :class="p.isCompositionLedger ? 'lg:col-span-7' : 'lg:col-span-12'"
        class="flex flex-col gap-5"
      >
        <!-- 总资产 -->
        <div>
          <p
            class="text-sm mb-2"
            :style="{ color: 'var(--text-tertiary-ink)' }"
          >
            总资产
          </p>
          <div class="flex items-baseline gap-2">
            <MoneyDisplay
              :value="p.summaryData?.total_market_value || 0"
              size="hero"
              :show-sign="false"
            />
            <span
              class="text-xl font-medium"
              :style="{ color: 'var(--text-secondary)' }"
              >元</span
            >
          </div>
        </div>

        <!-- 持仓盈亏 + 持仓与余额 指标网格（分隔线对齐看板） -->
        <div
          class="grid grid-cols-2 gap-x-4 gap-y-5 pt-5"
          :style="{ borderTop: '1px solid var(--border-light)' }"
        >
          <!-- 持仓盈亏（涨红跌绿） -->
          <div class="flex flex-col">
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >持仓盈亏</span
            >
            <MoneyDisplay :value="p.summaryData?.position_pnl || 0" size="lg" />
          </div>
          <!-- 持仓数量 -->
          <div class="flex flex-col">
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >持仓数量</span
            >
            <span
              class="text-lg font-semibold"
              :style="{ color: 'var(--text-primary)' }"
              >{{ p.summaryData?.position_count || 0 }} 项</span
            >
          </div>
          <!-- 资金余额（中性余额，不随涨跌着色） -->
          <div class="flex flex-col">
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >资金余额</span
            >
            <MoneyDisplay
              v-if="p.summaryData?.cash_balance != null"
              :value="p.summaryData.cash_balance"
              size="md"
              :show-sign="false"
              :auto-color="false"
            />
            <span
              v-else
              class="text-sm"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >--</span
            >
          </div>
          <!-- 关联负债（仅银行账户且有负债时展示） -->
          <div
            v-if="
              p.summaryData?.ledger_type === 'bank' &&
              p.summaryData?.linked_liability > 0
            "
            class="flex flex-col"
          >
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >关联负债</span
            >
            <MoneyDisplay
              :value="-p.summaryData.linked_liability"
              size="md"
              :auto-color="false"
              custom-color="var(--color-danger)"
            />
          </div>
          <!-- 货基收益（仅基金账户展示） -->
          <div
            v-if="p.summaryData?.ledger_type === 'fund'"
            class="flex flex-col"
          >
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >货基今日收益</span
            >
            <MoneyDisplay
              v-if="p.moneyFundData"
              :value="p.moneyFundData.today_income"
              size="md"
            />
            <span
              v-else
              class="text-sm"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >--</span
            >
          </div>
          <!-- #2134：近 90 天区间收益 vs 基准同期 vs 超额。
               三值全部来自 /summary/benchmark-excess/，缺数据一律「--」（不造 0）；
               区间由首格 label 点明，后两格与之同区间（同期口径见后端 docstring）。 -->
          <div class="flex flex-col">
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >近 90 天收益</span
            >
            <span
              class="text-lg font-semibold"
              :style="{ color: 'var(--text-primary)' }"
            >
              <RiseFallText
                v-if="rangeRate != null"
                :value="rangeRate"
                size="lg"
              />
              <template v-else>--</template>
            </span>
          </div>
          <div class="flex flex-col">
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              >基准同期</span
            >
            <span
              class="text-lg font-semibold"
              :style="{ color: 'var(--text-primary)' }"
            >
              <RiseFallText
                v-if="benchReturn != null"
                :value="benchReturn"
                size="lg"
              />
              <template v-else>--</template>
            </span>
          </div>
          <div class="flex flex-col">
            <span
              class="text-xs mb-1"
              :style="{ color: 'var(--text-tertiary-ink)' }"
              :title="excessHint || undefined"
              >超额收益</span
            >
            <span
              class="text-lg font-semibold"
              :style="{ color: 'var(--text-primary)' }"
            >
              <RiseFallText
                v-if="excessReturn != null"
                :value="excessReturn"
                size="lg"
              />
              <template v-else>--</template>
            </span>
          </div>
        </div>
      </div>

      <!-- 右栏：资产构成分布（仅股票 / 基金 / 信用账户，对齐看板饼图） -->
      <!-- 栏间分割线走全局工具类 `.soft-col-divider`（style/index.scss）：
           自带 24px 内边距、且仅在 lg 及以上出现——原先内联 borderLeft 既贴文字，
           又在 lg 以下两栏堆叠时留一条孤零零的竖线。 -->
      <div
        v-if="p.isCompositionLedger"
        class="lg:col-span-5 flex flex-col items-center justify-center h-full soft-col-divider"
      >
        <div class="w-full flex justify-between items-center mb-4">
          <span
            class="font-bold text-sm"
            :style="{ color: 'var(--text-secondary)' }"
            >资产构成分布</span
          >
        </div>
        <AssetAllocationDonut
          :data="p.compositionData"
          :color-map="p.compositionColorMap"
          :show-legend="true"
        />
      </div>
    </div>
  </CardBlock>

  <!-- #2155 / CNB #479：账外类现金出口。
       它必须**独立成块、并列展示**，不能并进上面的环形图：环形图两片是
       「持仓市值的划分」（合计 = 总资产），账外类现金不建持仓、不在其中
       （并进去会重演 #1606 的「投资资产 -63.2%」负数 bug，口径解耦见 D59）。
       #2739：anchor-id 让本块在有内容时挂上页内导航锚点（整块不渲染时
       锚点随之消失，导航项不留死链）。 -->
  <LedgerCashLikeCard anchor-id="nav-cash-like" :summary="p.summaryData" />

  <!-- #1812：收益日历已落地（账户级，传 ledgerId 走该账户的 as-of 派生序列）。
       与 welcome 第三排 / panorama「资产大类 ⇄ 收益日历」原地切换是**同一组件的三处容器**，
       口径唯一；#1925 起三处都带日 / 月 / 年粒度切换。
       #2739：id 经 fallthrough 落在面板根（单根元素）＝ 锚点即标题行顶边。 -->
  <div class="mb-6">
    <PnlCalendar id="nav-calendar" :ledger-id="p.ledgerIdNum" />
  </div>

  <!-- #2135：收益归因（区间逐品种 / 大类贡献）——复用 pnl 引擎唯一盈亏口径，
       Σ品种 ≡ 同窗收益日历月合计由后端构造保证，前端只展示。
       #2739：PnlAttribution 是多根组件（吃不到父级 fallthrough），故由调用方
       包一层 div 承接锚点（与组合详情页同一手法）。 -->
  <div id="nav-attribution">
    <PnlAttribution :ledger-id="p.ledgerIdNum" />
  </div>

  <!-- #2739：账户深度分析（持仓结构 / 集中度 + 持仓穿透 / 行业分布）。
       这两项能力早已上线（#2617 / #870 + #2595），原先此处是一块写着
       「规划中，敬请期待」的占位卡——那是在把**已存在**的功能说成不存在。
       组件与端点现成、口径与组合详情页 / 持仓分析页同源，本页只补它独缺
       的这两块，不搬聚合页其余块（详见 docs/spec/account-detail-depth-analysis.md）。
       **必须显式传账户口径**：不传 = 全家庭档，会显示别的账户的数据；
       未归置持仓伪账户没有数字账户 id，整块不展示（与资金流动同一处置）。 -->
  <LedgerDepthAnalysis v-if="showDepthAnalysis" :ledger-id="p.ledgerIdNum" />
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import SoftBanner from "@/components/SoftBanner/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import PnlCalendar from "@/components/PnlCalendar/index.vue";
import PnlAttribution from "@/components/PnlAttribution/index.vue";
import AssetAllocationDonut from "@/components/Charts/AssetAllocationDonut.vue";
import LedgerCashLikeCard from "./LedgerCashLikeCard.vue";
import LedgerDepthAnalysis from "./LedgerDepthAnalysis.vue";
import { getBenchmarkExcess, type BenchmarkExcessResult } from "@/api/summary";
import { excessDateRange, excessDegradHint } from "@/utils/benchmarkExcess";
import type { useLedgerDetailPage } from "../composables/useLedgerDetailPage";

defineOptions({ name: "LedgerDetailOverview" });

// #980 P1-C 拆分自 detail.vue：账户信息头 + 温柔提醒横幅 + 账本概览区。
// 状态单体经 page prop 注入，p. 前缀替换与拆分前的绑定表达式一一对应。
const props = defineProps<{ page: ReturnType<typeof useLedgerDetailPage> }>();
const p = reactive(props.page);

/**
 * 是否展示账户深度分析（持仓结构 / 持仓穿透）。
 *
 * 未归置持仓页**不展示**：那个页面是「把散落资产关联到账户」的归置台，
 * 它没有数字账户 id，深度分析对它没有账户口径可言（传家庭级会展示别的
 * 账户的数据）。处置与同页的资金流动区块一致（`!isUnclassified && ledgerIdNum`）。
 */
const showDepthAnalysis = computed(
  () => !p.isUnclassified && p.ledgerIdNum != null
);

// ---------- #2134：近 90 天区间收益 vs 基准（缺数据诚实降级 null → 模板「--」）----------
const excess = ref<BenchmarkExcessResult | null>(null);
const rangeRate = computed(() => excess.value?.range_rate ?? null);
const benchReturn = computed(
  () => excess.value?.benchmark?.range_return ?? null
);
const excessReturn = computed(() => excess.value?.excess_return ?? null);
const excessHint = computed(() => excessDegradHint(excess.value));

async function fetchExcess() {
  const ledgerId = p.ledgerIdNum;
  if (!ledgerId) {
    excess.value = null;
    return;
  }
  try {
    const res = await getBenchmarkExcess({
      ...excessDateRange(),
      ledger_id: ledgerId
    });
    excess.value = res.data;
  } catch {
    // 拿不到就整组降级「--」：概览区不因超额计算失败而打断
    excess.value = null;
  }
}

// ledgerId 随路由注入，切换账户时重取（与页内 PnlCalendar 同一数据源）
watch(
  () => p.ledgerId,
  () => void fetchExcess(),
  { immediate: true }
);
</script>

<style scoped>
/* 温柔提醒 banner（#1133 §4）：中性信息色，非涨跌色 / 非危险红；轻量、不制造心理压力。
   #2730 起壳由 SoftBanner info 档承担，此处只留两级正文排版。
   已删除的本地壳：display/gap/align-items/padding/margin/background/border/border-radius
   以及 `.soft-reconcile-banner__icon` / `__body` / `__actions`（图标位与动作区由组件提供）。
   随壳一起去掉的是 `border-left: 3px solid var(--el-color-info)` —— 判为**冗余装饰**：
   它的语义（中性信息）与 info 档图标 `--color-info-ink` 完全重合，且 `--el-color-info`
   是 Element Plus 直调（tech-debt 明令的颜色直调），链路里唯一用处就是这道 3px 条。
   不加 `accent` prop 的理由见 docs/spec/soft-banner.md §3（单消费方不值得把壳变成可拼装结构）。 */
.soft-reconcile-banner__title {
  margin: 0;
  font-size: var(--text-small);
  line-height: 22px;
  color: var(--text-primary);
}

.soft-reconcile-banner__detail {
  margin: 4px 0 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
