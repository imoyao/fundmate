<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type { AdvisorProfileResult } from "@/api/products";
import { getAdvisorPlatformLabel } from "@/constants/advisorPlatform";
import { DASH, fmtPct, riseFallClass, strategyText } from "./advisorModel";
import { fetchAdvisorProfile } from "./advisorProfileCache";

/**
 * 投顾组合 · 概览（重设计 §01）。
 *
 * ## 为什么把净值与指标提到这里
 *
 * 旧版 `AdvisorFacts` 八格里混着三类信息：身份（平台 / 机构）、属性（风险等级 /
 * 产品类型 / 成立日期）、行情（最新净值 / 日涨跌）。用户要在同一张网格里找
 * 「它现在怎么样」，而那一格排在第 7、8 位、字号与「平台」一样大。
 *
 * 现在分三处：身份压成一行 meta、属性下沉到「组合档案」、行情与四个关键指标
 * 成为首屏主数字（净值）+ KPI 网格。一句话：**概览答「它是什么、现在怎么样、
 * 代价多大」，其余细节各有归处**。
 *
 * ## 口径
 *
 * - 只渲染有值的项（105 个组合实测：`return_ytd` 2.9%、`running_days` 0%），
 *   一排「—」是「没数据」的另一种噪声；
 * - 收益走文字级涨跌色 + ↑↓ 双编码（颜色不是唯一载体）；回撤与夏普是中性量，
 *   套涨跌色会把「回撤大」读成「涨得多」；
 * - 净值保留 4 位（与库内 `advisor_portfolio_navs.nav` 精度一致），百分比 2 位。
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

/** 身份行：缺项跳过（不写「—」占位——一行里连着的破折号比信息还长） */
const metaLine = computed(() => {
  const p = profile.value;
  if (!p) return [];
  return [
    platformLabel.value,
    p.org_name,
    p.host ? `主理人 ${p.host}` : null,
    p.risk_level,
    p.product_type,
    p.estab_date ? `成立 ${p.estab_date}` : null
  ].filter((item): item is string => Boolean(item));
});

interface Kpi {
  label: string;
  text: string;
  class: string;
  sub: string;
}

/** 主数字下的 KPI：收益类带涨跌色，回撤 / 夏普为中性（见文件头口径） */
const kpis = computed<Kpi[]>(() => {
  const p = profile.value;
  if (!p) return [];
  const items: Kpi[] = [];

  if (p.return_since_incep != null) {
    items.push({
      label: "成立以来",
      text: fmtPct(p.return_since_incep),
      class: riseFallClass(p.return_since_incep),
      sub: p.estab_date ? `${p.estab_date} 起` : ""
    });
  }
  if (p.return_1y != null) {
    items.push({
      label: "近一年",
      text: fmtPct(p.return_1y),
      class: riseFallClass(p.return_1y),
      // 只写月日：完整日期在主数字下方与页头右侧各有一次，KPI 格里再写全年份
      // 会在窄屏（两列网格 138px 宽）被折成「截至 2026-11-」+「17」两行
      sub: p.nav_date ? `截至 ${p.nav_date.slice(5)}` : ""
    });
  }
  if (p.max_drawdown != null) {
    items.push({
      label: "最大回撤",
      // 回撤是「峰值到谷底的跌幅」，用绝对值 + 百分号，符号由标签表达
      text: `${Math.abs(p.max_drawdown).toFixed(2)}%`,
      class: "",
      sub: "历史峰值到谷底"
    });
  }
  if (p.sharpe_ratio != null) {
    items.push({
      label: "夏普比率",
      text: p.sharpe_ratio.toFixed(3),
      class: "",
      sub: "每单位波动的超额"
    });
  }
  return items;
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
    <SectionHeader title="概览">
      <template #action>
        <span v-if="profile?.nav_date" class="advisor-overview__stamp">
          净值日 {{ profile.nav_date }}
        </span>
      </template>
    </SectionHeader>

    <p v-if="loading" class="advisor-overview__hint">正在读取投顾组合资料…</p>
    <p v-else-if="failed || !profile" class="advisor-overview__hint">
      暂无可展示的投顾组合资料
    </p>

    <template v-else>
      <p v-if="metaLine.length" class="advisor-overview__meta">
        {{ metaLine.join(" · ") }}
      </p>

      <div class="advisor-overview__grid">
        <div class="navnow">
          <p class="navnow__label">最新净值</p>
          <p class="navnow__value">
            {{ profile.nav != null ? profile.nav.toFixed(4) : DASH }}
          </p>
          <p v-if="dayChange" class="navnow__delta" :class="dayChange.class">
            {{ dayChange.text }}
            <span class="navnow__delta-note">较前一交易日</span>
          </p>
          <p class="navnow__date">
            {{ profile.nav_date ? `净值日期 ${profile.nav_date}` : "" }}
          </p>
        </div>

        <dl v-if="kpis.length" class="kpis">
          <div v-for="k in kpis" :key="k.label" class="kpi">
            <dt class="kpi__label">{{ k.label }}</dt>
            <dd class="kpi__value" :class="k.class">{{ k.text }}</dd>
            <dd class="kpi__sub">{{ k.sub }}</dd>
          </div>
        </dl>
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
@use "@/style/breakpoints" as bp;

.advisor-overview__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 页头右侧的状态戳：日期是事实，不抢标题 */
.advisor-overview__stamp {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

/* 身份行：一行读完「谁在管、什么风险、什么时候成立」。
   用 --text-secondary 而不是 tertiary-ink——它是事实信息，不是注释。 */
.advisor-overview__meta {
  margin: var(--space-2) 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}

.advisor-overview__grid {
  display: grid;
  grid-template-columns: minmax(180px, 248px) minmax(0, 1fr);
  gap: var(--space-5);
  align-items: end;
  padding-top: var(--space-4);
  margin-top: var(--space-4);
  border-top: 1px solid var(--border-light);

  @include bp.below("md") {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-4);
  }
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
.kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  padding: 0;
  margin: 0;
  overflow: hidden;
  background: var(--border-light);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);

  @include bp.below("lg") {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.kpi {
  padding: var(--space-3) var(--space-compact);
  background: var(--bg-card);
}

.kpi__label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.kpi__value {
  margin: 2px 0 0;
  font-family: var(--font-number);
  font-size: var(--text-num-strong);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;

  &.is-rise {
    color: var(--color-rise-ink);
  }

  &.is-fall {
    color: var(--color-fall-ink);
  }
}

.kpi__sub {
  margin: 1px 0 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

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
