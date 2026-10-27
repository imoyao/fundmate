<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getAdvisorProfile, type AdvisorProfileResult } from "@/api/products";
import { getAdvisorHoldings, type AdvisorHoldingsResult } from "@/api/funds";
import { getAdvisorPlatformLabel } from "@/constants/advisorPlatform";
import AdvisorFacts from "./advisorSection/AdvisorFacts.vue";
import AdvisorFootnote from "./advisorSection/AdvisorFootnote.vue";
import AdvisorHoldings from "./advisorSection/AdvisorHoldings.vue";
import AdvisorMetrics from "./advisorSection/AdvisorMetrics.vue";
import {
  buildReturnMetrics,
  buildRiskMetrics,
  strategyText
} from "./advisorSection/advisorModel";

/**
 * 详情页「投顾组合」区块（#1975 · 设计 §6 三期货品）。
 *
 * ## 取数
 *
 * - `GET /api/products/advisor-profile/`（本卡新增）：组合档案 + 可得指标。
 *   此前 `advisor_portfolios` 的档案字段**没有任何端点返回** —— funds 域只有
 *   `advisors/<code>/holdings/` 与 `/adjusts/`，它们回答「持什么、调过什么」，
 *   回答不了「这是个什么组合」，而详情页首屏要的正是后者；
 * - 成分基金复用**已上线**的 `getAdvisorHoldings`，不重写取数链路。
 *
 * ## 内容边界（本次刻意不做调仓记录）
 *
 * 调仓明细（`getAdvisorAdjusts`）**不在本区块渲染**：设计 §7 已把「投顾成分与调仓」
 * 登记为「抽屉既有 + 详情页复用同一组件」，而那需要先把速览抽屉里那段渲染提取成
 * 共用组件（属 B6「速览抽屉是否瘦身」的复评范围）。此处先给**档案 + 指标 + 成分**，
 * 避免同一份渲染逻辑写两遍（§2.1「强制复用」）。
 *
 * ## 降级（设计 §6 诚实降级，不用 mock）
 *
 * 本机真实库 105 个组合实测：`org_name` / `risk_level` / 区间收益 / 回撤 / 波动率 /
 * 夏普填充率 91~100%，这些是区块主体；而 `strategy_type` / `cum_return` /
 * `running_days` / `benchmark` / `excess_return` 为 **0%**、`host` **1.9%**、
 * `return_ytd` **2.9%** —— 一律显示「—」；指标区**只渲染有值的项**，不让一排
 * 「—」占满版面（那是「没数据」的另一种噪声）。
 *
 * ## 不展示代码（设计 §2.6）
 *
 * 组合类标的靠「名称 + 平台 + 机构」识别。⚠️ 注意：设计要求写的是「平台/主理人」，
 * 但主理人实测填充率只有 1.9%，故实际锚点落在**机构**（100%）上 —— 不为凑条文编造。
 *
 * ## 结构（#980 拆分）
 *
 * - `advisorSection/advisorModel.ts` —— 指标筛选、涨跌色、策略文案（纯函数）
 * - `advisorSection/AdvisorFacts.vue` —— 识别信息（名称 / 平台 / 机构 / 净值…）
 * - `advisorSection/AdvisorMetrics.vue` —— 收益表现 + 风险指标
 * - `advisorSection/AdvisorHoldings.vue` —— 成分基金
 * - `advisorSection/AdvisorFootnote.vue` —— 来源与外链、披露声明
 */
const props = defineProps<{
  /** 平台组合码（`advisor_portfolios.code`，如 ZH012926 / XCOVSEX） */
  code: string;
}>();

const loading = ref(false);
const failed = ref(false);
const profile = ref<AdvisorProfileResult | null>(null);
const holdings = ref<AdvisorHoldingsResult | null>(null);

const platformLabel = computed(() =>
  profile.value ? getAdvisorPlatformLabel(profile.value.platform) : ""
);

const returnMetrics = computed(() => buildReturnMetrics(profile.value));
const riskMetrics = computed(() => buildRiskMetrics(profile.value));
const strategy = computed(() => strategyText(profile.value));

async function load() {
  if (!props.code) return;
  loading.value = true;
  failed.value = false;
  profile.value = null;
  holdings.value = null;
  try {
    const res = await getAdvisorProfile({ code: props.code });
    profile.value = res.data;
  } catch {
    // 未收录 / 网络异常：整块降级为空态，不影响详情页其余区块
    profile.value = null;
    failed.value = true;
    loading.value = false;
    return;
  }

  // 成分基金只在后端报了条数时才取：多数组合有持仓（103/105），但空组合不该白发请求
  if (profile.value && profile.value.holding_count > 0) {
    try {
      const res = await getAdvisorHoldings(props.code);
      holdings.value = res.data;
    } catch {
      // 成分取不到只影响这一块，上面的档案照常展示
      holdings.value = null;
    }
  }
  loading.value = false;
}

watch(() => props.code, load, { immediate: true });
</script>

<template>
  <CardBlock class="advisor-section">
    <SectionHeader title="投顾组合" />

    <p v-if="loading" class="section-footnote">正在读取投顾组合资料…</p>

    <p v-else-if="failed || !profile" class="section-footnote">
      暂无可展示的投顾组合资料
    </p>

    <template v-else>
      <!-- 识别信息：不展示代码（设计 §2.6），靠名称 + 平台 + 机构 -->
      <AdvisorFacts :profile="profile" :platform-label="platformLabel" />

      <!-- 指标区只渲染有值的项：一排「—」是「没数据」的另一种噪声 -->
      <AdvisorMetrics :returns="returnMetrics" :risks="riskMetrics" />

      <p v-if="strategy" class="advisor-section__desc">
        {{ strategy }}
      </p>

      <!-- 成分基金：复用已上线的 holdings 端点；已收录本地名录的才给跳转 -->
      <AdvisorHoldings
        v-if="holdings && holdings.holdings.length"
        :holdings="holdings"
      />

      <!-- 脚注：来源给平台名（用户看得懂），并附官方页面外链（新窗口打开） -->
      <AdvisorFootnote :profile="profile" :platform-label="platformLabel" />
    </template>
  </CardBlock>
</template>

<style scoped>
/* 策略说明：唯一留在父页的 advisor-section 样式，其余随子件走 */
.advisor-section__desc {
  margin: var(--space-3) 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}
</style>
