<script setup lang="ts">
import { ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getFundPerformance, type FundPerformanceResult } from "@/api/products";
import PerfFundBlock from "./perfSection/PerfFundBlock.vue";
import PerfMoneyBlock from "./perfSection/PerfMoneyBlock.vue";

/**
 * 详情页「业绩与风险」区块（#2029 卡 B · 设计卡 §4.1 #3）。
 *
 * 取数一次到位：`GET /api/products/fund-performance/` 把区间收益切面、最大回撤、年化波动率
 * 打包返回（后端基于 daily_worth.acc_nav 现算，与自选域同源）。
 *
 * 口径与降级（设计 §6 诚实降级，不编造占位值）：
 * - `fund_kind: "money"`：货币基金没有日涨跌 / 回撤口径，后端改返万份收益 + 七日年化，
 *   本区块只显这两项，不显净值型指标（避免误读「货币也跌了」）；
 * - `applicable: false` / 字段 null：逐项降级为「—」；
 * - 区间收益是**涨跌**，走 RiseFallText（涨红跌绿，与全站一致）；最大回撤 / 波动率
 *   是风险幅度而非方向性涨跌，用中性色，不把「绿」误读成「好」。
 *
 * #167 追加：
 * - **本轮回撤**（`current_drawdown`）是「现在疼不疼」，**最大回撤**是「最疼过多少」——
 *   两个都要显。只显最大值会把「跌 30% 但已修复」与「跌 30% 且仍在水下」显示成一个数，
 *   而后一种正是要警惕的「跌起来比涨得还猛」（#167 用户原话）。
 * - 风险比（夏普 / 索提诺 / 卡玛 / UI / UPI / 波回比）**只在同类内可比**：债基波动天生小、
 *   夏普系统性偏高。故本区块不画排行榜、不给「好/差」色，只把数字与口径摆出来。
 * - rf（无风险利率）与窗口随值下发并展示在脚注——不告诉用户 rf 取多少的夏普不可复核。
 *
 * ## 结构（#980 拆分）
 *
 * 主文件只留取数与三态分派；两个分支各自成件：
 * - `perfSection/PerfMoneyBlock.vue` —— 货基（七日年化 / 万份收益 / 同类分位 / 基准）
 * - `perfSection/PerfFundBlock.vue` —— 场外基金（区间收益 / 回撤 / 风险比 / 脚注）
 * - `perfSection/perfRows.ts` —— 指标行的构造与「全空不画」判定（纯函数，可单测）
 * - `perfSection/PerfFactGrid.vue` —— 「标签 / 数值 / 副行」这套同构排版的展示件
 */
const props = defineProps<{
  symbol: string;
}>();

const loading = ref(false);
const perf = ref<FundPerformanceResult | null>(null);
const failed = ref(false);

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  try {
    const res = await getFundPerformance(props.symbol);
    perf.value = res.data;
  } catch {
    // 非基金代码 / 未收录 / 网络异常：统一降级为空态，不影响详情页其余区块
    perf.value = null;
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <CardBlock class="performance-section">
    <SectionHeader title="业绩与风险" />

    <p v-if="loading" class="section-footnote">正在读取业绩与风险…</p>

    <p v-else-if="failed || !perf || !perf.applicable" class="section-footnote">
      暂无可展示的业绩数据
    </p>

    <!-- 货币基金：万份收益 + 七日年化（无回撤口径） -->
    <PerfMoneyBlock v-else-if="perf.fund_kind === 'money'" :perf="perf" />

    <!-- 场外基金：区间收益 + 风险指标 -->
    <PerfFundBlock v-else :perf="perf" />
  </CardBlock>
</template>

<style scoped>
/*
 * 样式留在父页，子件不各带一份（#980）。
 *
 * 原因：这些 `performance-section__*` 类被「指标网格 / 货基分支 / 基金分支」三处共用，
 * 而 scoped 样式只作用于本组件模板里的元素——子组件内部元素拿不到父的 scopeId。
 * 常见解法是每个子件各抄一份 partial，代价是**同一份声明出现多次**：将来改一个字号要
 * 改 3 处，漏一处就是局部视觉漂移，而这种漂移 review 时看不见。
 *
 * 这里改用 `:deep()` 从父页穿透：声明只有一份、口径只有一处，拆组件不产生视觉变化。
 * 类名带 `performance-section__` 前缀且全站唯一，穿透不会误伤别处。
 */
.performance-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* 令牌口径：`--text-secondary` 在 colors.css:33 有定义（`--text-secondary-ink` 未定义，
   写了会让整条 color 声明静默失效 → 回落浏览器默认色，暗色端直接失控）。 */
:deep(.performance-section__block-label) {
  margin: var(--space-3) 0 var(--space-1);
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-secondary);
}

:deep(.performance-section__label) {
  /* Tailwind v4 preflight 把全站 <svg> 置为 display:block，而
     IconifyIconOffline 渲染的图标是 <svg>——在普通 block 容器里「标签+图标」
     会被挤成上下两行（#2283 回归）。inline-flex 与排行榜表头 .th-with-tip
     同款修法：图标作为 flex item 跟随标签同行。 */
  display: inline-flex;
  align-items: center;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 指标名 + 解释图标（el-tooltip 锚点）：图标跟随标签色，cursor-help 提示可悬停 */
:deep(.performance-section__label-text) {
  margin-right: 4px;
}

:deep(.performance-section__tip-icon) {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  cursor: help;
}

:deep(.performance-section__value) {
  margin: 0;
  font-size: var(--text-mono-small);
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 区间收益 / 风险：与基金资料卡同款 facts 网格（#1969 P0，严禁 minmax(0,1fr) 塌轨） */
:deep(.performance-section__facts) {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--space-3) var(--space-6);
  margin: 0;
}

:deep(.performance-section__fact) {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

/* 标签旁的次要说明（「已 3 个月」「近3年 · 同类内可比」）：12px 三级色，不抢主信息 */
:deep(.performance-section__aside) {
  margin-left: var(--space-1);
  font-size: var(--text-label);
  font-weight: 400;
  color: var(--text-tertiary-ink);
}

/* 口径副行（高点/低点日期）：比正文再小一档 */
:deep(.performance-section__sub) {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 口径告警：暖沙金文字级（--color-warning 只许作底/边，禁作前景，见 #1545） */
:deep(.performance-section__caveat) {
  margin: 0;
  font-size: var(--text-label);
  color: var(--color-warning-ink);
}

/* 货基 KPI：两枚大数字横排 */
:deep(.performance-section__kpi) {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  margin: 0;
}

:deep(.performance-section__kpi-item) {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
</style>
