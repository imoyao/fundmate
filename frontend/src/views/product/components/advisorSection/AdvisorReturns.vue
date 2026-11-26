<script setup lang="ts">
import { computed } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type { AdvisorProfileResult } from "@/api/products";
import {
  buildReturnMetrics,
  buildRiskMetrics,
  fmtPct,
  riseFallClass
} from "./advisorModel";

/**
 * 投顾组合 · 收益与风险（重设计 §02）。
 *
 * ## 为什么收益改成条形
 *
 * 旧版是把六个区间铺成一排同权重的数字（近 1 月 / 3 月 / 6 月 / 1 年 / 成立以来 / 年化）。
 * 六个并排时「−7.67%」与「+175.50%」占同样大的位置，用户得逐个读数字才能比较。
 *
 * 现在近端四档（1M / 3M / 6M / 1Y）放进**同一 ±20% 刻度**做双向条、零轴居中：
 * 长度直接可比，正负在轴的两侧、颜色再标一次（颜色不是唯一载体）。
 * 成立以来与年化单独做大数字——它们的量级与四个近端档不在一个尺度上，
 * 塞进同一条刻度只会把近端压成看不见的小段。
 *
 * ## 口径
 *
 * - 数值来自后端 `advisor-profile` 的 `return_*` 字段（平台披露口径），
 *   前端**不自己按净值序列现算**——两套算法给出的数会在同页出现 0.2~2.8pp 的分歧，
 *   而用户无法判断该信哪一个；
 * - 条超 ±20% 时截断到端点（刻度是「看得见的范围」，不是无穷）；
 * - 风险三项一律中性色：回撤是负数，套「跌」的绿会被读成「亏得少」。
 */
const props = defineProps<{
  profile: AdvisorProfileResult | null;
}>();

/** ±20% 的固定刻度：近端四档都落得进去，且两端留白让「接近 20%」有预警感 */
const SCALE = 20;

/**
 * 近端四档的标签（与 `advisorModel.buildReturnMetrics` 的 label 逐字对应）。
 * 区间定义只在那一处，这里只挑选用哪几档做条形——不另写一份区间表。
 */
const NEAR_LABELS = ["近 1 月", "近 3 月", "近 6 月", "近 1 年"];
const LONG_LABELS = ["成立以来", "年化"];

interface ReturnRow {
  label: string;
  text: string;
  /** 涨跌色 class */
  class: string;
  /** 条形左端与宽度（%，相对整条轨道） */
  left: number;
  width: number;
}

const nearRows = computed<ReturnRow[]>(() =>
  buildReturnMetrics(props.profile)
    .filter(m => NEAR_LABELS.includes(m.label) && m.value != null)
    .map(item => {
      const value = item.value as number;
      const width = Math.min(Math.abs(value) / SCALE, 1) * 50;
      return {
        label: item.label,
        text: fmtPct(value),
        class: riseFallClass(value),
        left: value >= 0 ? 50 : 50 - width,
        width
      };
    })
);

/** 长期两档：与近端四档不同尺度，单独做大数字 */
const longTerm = computed(() => {
  const subFor: Record<string, string> = {
    成立以来: props.profile?.estab_date
      ? `自 ${props.profile.estab_date} 起`
      : "",
    年化: "按运作时长折算"
  };
  return buildReturnMetrics(props.profile)
    .filter(m => LONG_LABELS.includes(m.label) && m.value != null)
    .map(item => ({
      label: item.label,
      text: fmtPct(item.value),
      class: riseFallClass(item.value),
      sub: subFor[item.label] ?? ""
    }));
});

const risks = computed(() => buildRiskMetrics(props.profile));

/** 风险项的解释：指标名对新手不自明，一句话说清「越大越好还是越小越好」 */
const RISK_HINTS: Record<string, string> = {
  最大回撤: "历史峰值到谷底的最大跌幅",
  年化波动率: "日收益标准差年化，越低越平稳",
  夏普比率: "每承担 1 单位波动换来的超额收益"
};

function hintOf(label: string): string {
  return RISK_HINTS[label] ?? "";
}
</script>

<template>
  <CardBlock class="advisor-returns">
    <SectionHeader
      title="收益与风险"
      info="收益按平台披露的区间口径；回撤、波动率、夏普为区间统计，不随走势区间切换。"
    />

    <p v-if="!profile" class="advisor-returns__hint">
      暂无可展示的收益与风险数据
    </p>

    <div v-else class="advisor-returns__grid">
      <section class="panel" aria-label="区间收益">
        <h3 class="panel__h">
          区间收益
          <small>近端四档同一刻度 ±{{ SCALE }}%</small>
        </h3>

        <div v-if="nearRows.length" class="ret">
          <div v-for="row in nearRows" :key="row.label" class="ret__row">
            <span class="ret__label">{{ row.label }}</span>
            <span class="ret__track">
              <span class="ret__axis" aria-hidden="true" />
              <span
                class="ret__bar"
                :class="row.class === 'is-rise' ? 'is-rise' : 'is-fall'"
                :style="{ left: `${row.left}%`, width: `${row.width}%` }"
              />
            </span>
            <span class="ret__val" :class="row.class">{{ row.text }}</span>
          </div>
        </div>
        <p v-else class="panel__empty">平台未披露区间收益</p>

        <div v-if="longTerm.length" class="longterm">
          <div v-for="item in longTerm" :key="item.label">
            <p class="longterm__label">{{ item.label }}</p>
            <p class="longterm__value" :class="item.class">{{ item.text }}</p>
            <p class="longterm__sub">{{ item.sub }}</p>
          </div>
        </div>
      </section>

      <section class="panel" aria-label="风险指标">
        <h3 class="panel__h">
          风险
          <small>中性色，不套涨跌色</small>
        </h3>

        <div v-if="risks.length" class="risklist">
          <div v-for="item in risks" :key="item.label" class="risk">
            <span class="risk__label">
              {{ item.label }}
              <span v-if="hintOf(item.label)" class="risk__hint">
                {{ hintOf(item.label) }}
              </span>
            </span>
            <span class="risk__value">{{ item.text }}</span>
          </div>
        </div>
        <p v-else class="panel__empty">平台未披露风险指标</p>

        <p class="panel__note">
          回撤与波动率越低越好，夏普越高越好；三项均为区间统计，与走势切换的区间无关。
        </p>
      </section>
    </div>
  </CardBlock>
</template>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.advisor-returns__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 左宽右窄：收益四行条需要横向空间，风险三行只需放得下数字 */
.advisor-returns__grid {
  display: grid;
  grid-template-columns: minmax(0, 1.32fr) minmax(0, 1fr);
  gap: var(--space-4);

  @include bp.below("lg") {
    grid-template-columns: minmax(0, 1fr);
  }
}

.panel {
  padding: var(--space-4);
  background: var(--bg-soft);
  border-radius: var(--radius-md);
}

.panel__h {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
  margin: 0 0 var(--space-3);
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-secondary);
}

.panel__h small {
  font-size: var(--text-label);
  font-weight: 400;
  color: var(--text-tertiary-ink);
}

.panel__empty {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.panel__note {
  padding-top: var(--space-3);
  margin: var(--space-3) 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
  border-top: 1px solid var(--border-light);
}

.ret {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ret__row {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) 76px;
  gap: var(--space-3);
  align-items: center;
  padding: 7px 0;

  & + & {
    border-top: 1px solid var(--border-light);
  }
}

.ret__label {
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.ret__track {
  position: relative;
  height: 6px;
}

/* 零轴：贯穿上下留白，让「正负」有一个明确的参照，而不只是两根不同色的条 */
.ret__axis {
  position: absolute;
  top: -7px;
  bottom: -7px;
  left: 50%;
  width: 1px;
  background: var(--border-default);
}

.ret__bar {
  position: absolute;
  top: 0;
  height: 6px;
  border-radius: 2px;

  &.is-rise {
    background: var(--color-rise);
  }

  &.is-fall {
    background: var(--color-fall);
  }
}

.ret__val {
  font-family: var(--font-number);
  font-size: var(--text-small);
  font-weight: 600;
  text-align: right;
  white-space: nowrap;

  &.is-rise {
    color: var(--color-rise-ink);
  }

  &.is-fall {
    color: var(--color-fall-ink);
  }
}

.longterm {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  margin-top: var(--space-4);
  overflow: hidden;
  background: var(--border-light);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);

  > div {
    padding: var(--space-3) var(--space-compact);
    background: var(--bg-card);
  }
}

.longterm__label {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.longterm__value {
  margin: 2px 0 0;
  font-family: var(--font-number);
  font-size: var(--text-num-hero);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;

  &.is-rise {
    color: var(--color-rise-ink);
  }

  &.is-fall {
    color: var(--color-fall-ink);
  }
}

.longterm__sub {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.risklist {
  display: flex;
  flex-direction: column;
}

.risk {
  display: flex;
  gap: var(--space-3);
  align-items: baseline;
  justify-content: space-between;
  padding: var(--space-3) 0;

  & + & {
    border-top: 1px solid var(--border-light);
  }
}

.risk__label {
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.risk__hint {
  display: block;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.risk__value {
  font-family: var(--font-number);
  font-size: var(--text-num-strong);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  white-space: nowrap;
}
</style>
