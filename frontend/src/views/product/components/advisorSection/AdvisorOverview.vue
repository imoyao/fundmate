<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type { AdvisorProfileResult } from "@/api/products";
import { getAdvisorPlatformLabel } from "@/constants/advisorPlatform";
import { formatPrice } from "@/utils/pricePrecision";
import { fmtPct, riseFallClass, strategyText } from "./advisorModel";
import { fetchAdvisorProfile } from "./advisorProfileCache";

/**
 * 投顾组合 · 概览（重设计 §01）。
 *
 * ## 这一块只回答「它是什么、现在什么价」
 *
 * 2026-11-26 用户实测：「最大年化、回撤这些数据同一个页面出现一次就够了。」
 * 此前这里还排着四个 KPI（成立以来 / 近一年 / 最大回撤 / 夏普比率），而 §02
 * 「收益与风险」逐个都有 —— 同一屏里每个数字出现两次，读者反而不确定该信哪个。
 *
 * 现在按**指标唯一归属**划分：
 *
 * | 内容 | 归属 |
 * |---|---|
 * | 净值 / 当日涨跌 / 净值日 | 这里（「现在什么价」只有一处） |
 * | 区间收益、回撤、波动率、夏普、成立以来、年化 | §02 收益与风险 |
 * | 平台 / 机构 / 主理人 / 风险等级 / 产品类型 / 成立日期 | §06 组合档案 |
 *
 * 保留的身份行只做「一行读人」的摘要——完整属性在档案里，两处措辞刻意不同
 * （这里不写成立日期，因为它是档案属性，不是行情）。
 *
 * ## 口径
 *
 * - 净值保留 4 位（与库内 `advisor_portfolio_navs.nav` 精度一致）；
 * - 日涨跌走文字级涨跌色 + ↑↓ 双编码（颜色不是唯一载体）。
 */
const props = defineProps<{
  /** 平台组合码（`advisor_portfolios.code`） */
  code: string;
}>();

const loading = ref(false);
const failed = ref(false);
const profile = ref<AdvisorProfileResult | null>(null);
const strategyOpen = ref(false);

watch(
  () => props.code,
  async code => {
    if (!code) return;
    loading.value = true;
    failed.value = false;
    try {
      profile.value = await fetchAdvisorProfile(code);
    } catch {
      // 未收录 / 网络异常：整卡为空态，不影响其余区块
      profile.value = null;
      failed.value = true;
    } finally {
      loading.value = false;
    }
  },
  { immediate: true }
);

const platformLabel = computed(() =>
  profile.value ? getAdvisorPlatformLabel(profile.value.platform) : ""
);

/** 身份行：缺项跳过（不写「—」占位——一行里连着的破折号比信息还长）。
 *  **不写成立日期**：它是档案属性（§06 有），概览只回答「谁在管、什么风险」。 */
const metaLine = computed(() => {
  const p = profile.value;
  if (!p) return [];
  return [
    platformLabel.value,
    p.org_name,
    p.host ? `主理人 ${p.host}` : null,
    p.risk_level,
    p.product_type
  ].filter((item): item is string => Boolean(item));
});

const strategy = computed(() => strategyText(profile.value));

/** 日涨跌：正数显式带「+」+ 上箭头，负数自带负号 + 下箭头 */
const dayChange = computed(() => {
  const value = profile.value?.return_1d;
  if (value == null) return null;
  return {
    text: `${fmtPct(value)} ${value > 0 ? "↑" : value < 0 ? "↓" : ""}`.trim(),
    class: riseFallClass(value)
  };
});
</script>

<template>
  <CardBlock class="advisor-overview">
    <SectionHeader title="概览" />

    <p v-if="loading" class="advisor-overview__hint">正在读取投顾组合资料…</p>
    <p v-else-if="failed || !profile" class="advisor-overview__hint">
      暂无可展示的投顾组合资料
    </p>

    <template v-else>
      <p v-if="metaLine.length" class="advisor-overview__meta">
        {{ metaLine.join(" · ") }}
      </p>

      <!-- 净值块：净值日紧贴数字（全页只在这里出现一次） -->
      <div class="navnow">
        <p class="navnow__label">最新净值</p>
        <p class="navnow__value">
          {{ formatPrice(profile.nav, "fund") }}
        </p>
        <p v-if="dayChange" class="navnow__delta" :class="dayChange.class">
          {{ dayChange.text }}
          <span class="navnow__delta-note">较前一交易日</span>
        </p>
        <p class="navnow__date">
          {{ profile.nav_date ? `净值日期 ${profile.nav_date}` : "" }}
        </p>
      </div>

      <div v-if="strategy" class="strategy" :data-open="strategyOpen">
        <p class="strategy__text">{{ strategy }}</p>
        <button
          type="button"
          class="strategy__toggle"
          :aria-expanded="strategyOpen"
          @click="strategyOpen = !strategyOpen"
        >
          {{ strategyOpen ? "收起" : "展开" }}
        </button>
      </div>
    </template>
  </CardBlock>
</template>

<style lang="scss" scoped>
.advisor-overview__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 身份行：一行读完「谁在管、什么风险」。
   用 --text-secondary 而不是 tertiary-ink——它是事实信息，不是注释。 */
.advisor-overview__meta {
  margin: var(--space-2) 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}

/* 净值块：与身份行之间一条细线分开。全宽左对齐——右侧不再放 KPI（那些指标
   归 §02，见文件头「指标唯一归属」），所以不需要网格分栏 */
.navnow {
  padding-top: var(--space-4);
  margin-top: var(--space-4);
  border-top: 1px solid var(--border-light);
}

.navnow__label {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.navnow__value {
  margin: 2px 0 0;
  font-family: var(--font-number);
  font-size: var(--text-display);
  font-weight: 600;
  line-height: 1.1;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.navnow__delta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
  margin: 6px 0 0;
  font-size: var(--text-small);
  font-weight: 600;

  /* 涨跌色只在数字上，不再涂「较前一交易日」这行说明 */
  &.is-rise {
    color: var(--color-rise-ink);
  }

  &.is-fall {
    color: var(--color-fall-ink);
  }
}

.navnow__delta-note {
  font-size: var(--text-label);
  font-weight: 400;
  color: var(--text-tertiary-ink);
}

.navnow__date {
  margin: 2px 0 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* KPI：1px 分隔用网格背景露出来（比给每格加边框少一圈重叠的 2px） */

/* 策略说明：两行截断，避免长文把首屏推下去 */
.strategy {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  padding: var(--space-3) 0 0;
}

.strategy__text {
  display: -webkit-box;
  flex: 1;
  min-width: 0;
  margin: 0;
  overflow: hidden;
  -webkit-line-clamp: 2;
  font-size: var(--text-label);
  line-height: 1.75;
  color: var(--text-secondary);
  -webkit-box-orient: vertical;
}

.strategy[data-open="true"] .strategy__text {
  -webkit-line-clamp: unset;
}

.strategy__toggle {
  flex: 0 0 auto;
  padding: 0;
  font-size: var(--text-label);
  color: var(--color-primary-ink);
  white-space: nowrap;
  cursor: pointer;
  background: none;
  border: none;

  &:hover {
    text-decoration: underline;
  }
}
</style>
