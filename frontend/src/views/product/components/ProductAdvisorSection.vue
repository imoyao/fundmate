<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import type { AdvisorProfileResult } from "@/api/products";
import {
  getAdvisorComparison,
  getAdvisorHoldings,
  type AdvisorComparisonResult,
  type AdvisorHoldingsResult
} from "@/api/funds";
import { getAdvisorPlatformLabel } from "@/constants/advisorPlatform";
import AdvisorReturns from "./advisorSection/AdvisorReturns.vue";
import AdvisorHoldingsTable from "./advisorSection/AdvisorHoldingsTable.vue";
import AdvisorTimeline from "./advisorSection/AdvisorTimeline.vue";
import AdvisorDirectionCompare from "./advisorSection/AdvisorDirectionCompare.vue";
import AdvisorArchive from "./advisorSection/AdvisorArchive.vue";
import { fetchAdvisorProfile } from "./advisorSection/advisorProfileCache";

/**
 * 详情页「投顾组合」区块 —— 下部五块（收益与风险 / 成分基金 / 调仓 / 账户对照 / 档案）。
 *
 * ## 为什么拆成六个区块
 *
 * 旧版是**一张卡**里塞六个子块：身份网格、收益数字、风险数字、成分清单、调仓平铺、
 * 脚注。用户要在一张卡片里滚 5000px，页内导航只能给一个「投顾组合」入口。
 * 重设计（2026-11-25 原型）按「结论 → 归因 → 细节」拆成六块、各有锚点，
 * 页内导航才真正可用。
 *
 * 概览（§01）**不在这里**：它要提到走势之前（结论先行），单独挂在
 * `ProductAdvisorOverview.vue`；两处共用 `advisorProfileCache`，同一次浏览只发一次档案请求。
 *
 * ## 取数
 *
 * - `advisor-profile`：经缓存取（概览已取过一次，这里命中缓存）；
 * - `advisor-holdings`：仅当后端报 `holding_count > 0` 才发——空组合不该白发请求；
 * - `advisor-compare`：三集合 +「已持有」列的数据源，失败只影响对照块。
 *
 * ## 降级（设计 §6 诚实降级）
 *
 * 档案取不到 → 整块一个空态卡（不能拆成五张各报一次错）；成分 / 对比取不到 →
 * 只影响各自那一块，其余照常。
 */
const props = defineProps<{
  /** 平台组合码（`advisor_portfolios.code`） */
  code: string;
}>();

const loading = ref(false);
const failed = ref(false);
const profile = ref<AdvisorProfileResult | null>(null);
const holdings = ref<AdvisorHoldingsResult | null>(null);
const comparison = ref<AdvisorComparisonResult | null>(null);

const platformLabel = computed(() =>
  profile.value ? getAdvisorPlatformLabel(profile.value.platform) : ""
);

/**
 * 「已持有」列的真相源：对比端点的共同持有集合。
 * `null` 表示**未知**（对比取不到 / 未登录），与「都没持有」是两件事。
 */
const heldCodes = computed<string[] | null>(() => {
  if (!comparison.value) return null;
  return comparison.value.overlap.common.map(item => item.fund_code);
});

async function load() {
  const code = props.code;
  if (!code) return;
  loading.value = true;
  failed.value = false;
  profile.value = null;
  holdings.value = null;
  comparison.value = null;

  try {
    profile.value = await fetchAdvisorProfile(code);
  } catch {
    failed.value = true;
    loading.value = false;
    return;
  }

  // 以下两块互不影响：任一失败只降级自己
  if (profile.value.holding_count > 0) {
    try {
      const res = await getAdvisorHoldings(code);
      holdings.value = res.data;
    } catch {
      holdings.value = null;
    }
  }

  try {
    const res = await getAdvisorComparison(code);
    comparison.value = res.data;
  } catch {
    comparison.value = null;
  }

  loading.value = false;
}

watch(() => props.code, load, { immediate: true });
</script>

<template>
  <CardBlock v-if="loading" class="advisor-section-state">
    <p class="advisor-section-state__text">正在读取投顾组合资料…</p>
  </CardBlock>

  <CardBlock v-else-if="failed || !profile" class="advisor-section-state">
    <p class="advisor-section-state__text">暂无可展示的投顾组合资料</p>
  </CardBlock>

  <template v-else>
    <!-- 五块各自挂锚点：子件单根（CardBlock），id 经 attribute fallthrough 落到 section 上。
         本组件是多根，**不要**给本组件本身传 id —— Vue 会报 extraneous attribute。 -->
    <AdvisorReturns id="nav-advisor-returns" :profile="profile" />

    <AdvisorHoldingsTable
      id="nav-advisor-holdings"
      :holdings="holdings"
      :held-codes="heldCodes"
    />

    <AdvisorTimeline
      id="nav-advisor-adjusts"
      :code="code"
      :platform="profile.platform"
    />

    <AdvisorDirectionCompare
      id="nav-advisor-compare"
      :code="code"
      :comparison="comparison"
    />

    <AdvisorArchive
      id="nav-advisor-archive"
      :profile="profile"
      :platform-label="platformLabel"
      :holdings-as-of="holdings?.as_of_date ?? null"
    />
  </template>
</template>

<style scoped>
.advisor-section-state__text {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
