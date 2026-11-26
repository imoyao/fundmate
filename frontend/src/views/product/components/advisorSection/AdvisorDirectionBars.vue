<script setup lang="ts">
import { computed } from "vue";
import type { AdvisorStyleCompareResult } from "@/api/funds";
import {
  BIG_DIFF_PP,
  barScaleOf,
  barWidthPct,
  diffText,
  divergenceText,
  type DirectionRow
} from "./advisorDirectionModel";

/**
 * 投顾组合 · 方向对照的**图**（§05 上半：图例 + 五档双条 + 差值 + 提示条 + 覆盖缺口）。
 *
 * 纯展示：行数据、差值阈值判定、刻度归一全在 `advisorDirectionModel` 里（有单测），
 * 本组件只把数字摆上去。宿主 `AdvisorDirectionCompare` 负责取数与降级判断。
 *
 * ## 为什么刻度是「两侧最大值」而不是 100%
 *
 * 五方向的实测最大值在 35% 上下（真实库 ZH012926：中盘 34.58%）。按 100% 画，
 * 每一档都只有三分之一长度，用户看不出「哪一档更重」。
 *
 * ## 提示条只点最不一致的两档
 *
 * 三档以上等于没有提示（「五档里四档都不同」是废话）。判据是**差值绝对值**
 * 排序，不是行序——实测最大档常常不是第一行（固收 +18.9pp vs 大盘 +0.9pp）。
 */
const props = defineProps<{
  rows: DirectionRow[];
  /** 差值最大的两档（宿主算好，保证与提示条文案同源） */
  top2: DirectionRow[];
  /** 组合侧覆盖率（%）；null = 未知，不写成 100% */
  coveragePct: number | null;
  /** 缺风格箱的成分基金（覆盖率 <100 时说明缺在哪） */
  missing: AdvisorStyleCompareResult["advisor"]["missing"];
  /** 组合快照日 */
  asOfDate: string | null;
}>();

const scale = computed(() => barScaleOf(props.rows));

function widthOf(value: number): string {
  return barWidthPct(value, scale.value);
}
</script>

<template>
  <div class="dir__legend">
    <span class="legend__item">
      <i class="legend__dot legend__dot--adv" aria-hidden="true" />
      组合
    </span>
    <span class="legend__item">
      <i class="legend__dot legend__dot--mine" aria-hidden="true" />
      我的持仓
    </span>
    <span class="dir__note">
      <template v-if="asOfDate"> 组合快照 {{ asOfDate }} </template>
      <template v-if="coveragePct != null">
        · 覆盖 {{ coveragePct.toFixed(1) }}%
      </template>
      · 差 = 我 − 组合
    </span>
  </div>

  <div class="dir__head" aria-hidden="true">
    <span>方向</span>
    <span>占比</span>
    <span>组合</span>
    <span>我</span>
    <span>差</span>
  </div>

  <div
    v-for="row in rows"
    :key="row.key"
    class="dir"
    role="group"
    :aria-label="`${row.key}：组合 ${row.adv.toFixed(2)}%，我 ${row.mine.toFixed(2)}%`"
  >
    <span class="dir__k">{{ row.key }}</span>
    <span class="dir__bars">
      <span class="dir__track">
        <span
          class="dir__fill dir__fill--adv"
          :style="{ width: widthOf(row.adv) }"
        />
      </span>
      <span class="dir__track">
        <span
          class="dir__fill dir__fill--mine"
          :style="{ width: widthOf(row.mine) }"
        />
      </span>
    </span>
    <span class="dir__v">{{ row.adv.toFixed(2) }}</span>
    <span class="dir__v">{{ row.mine.toFixed(2) }}</span>
    <span class="dir__d" :class="{ 'dir__d--big': row.big }">
      {{ diffText(row.diff) }}
    </span>
  </div>

  <!-- 提示条：只点最不一致的两档，三档以上等于没有提示 -->
  <div v-if="top2.length" class="callout">
    <span class="callout__icon" aria-hidden="true">!</span>
    <p class="callout__text">
      <span class="callout__lead">方向差异 ≥ {{ BIG_DIFF_PP }}pp：</span>
      <span v-for="(row, i) in top2" :key="row.key">
        <b>{{ row.key }}</b> {{ divergenceText(row)
        }}<template v-if="i < top2.length - 1">；</template>
      </span>
    </p>
  </div>

  <!-- 覆盖缺口：只声明、不猜（缺箱体的权重不进加权） -->
  <p v-if="missing.length" class="advisor-compare__coverage">
    组合有 {{ missing.length }} 只成分基金没有风格箱（合计
    {{ missing[0].weight_pct.toFixed(2) }}%{{
      missing.length > 1 ? " 等" : ""
    }}权重）， 未计入方向占比。
  </p>
</template>

<style scoped lang="scss">
@use "@/style/breakpoints" as bp;

.advisor-compare__coverage {
  margin: var(--space-2) 0 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.dir__legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
  align-items: center;
  margin-bottom: var(--space-3);
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.legend__item {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.legend__dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;

  &--adv {
    background: var(--color-primary);
  }

  &--mine {
    background: var(--palette-caramel);
  }
}

.dir__note {
  margin-left: auto;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);

  /* 窄屏不再靠 margin-left 挤到右侧：它比图例长，挤在同一行会把两行文字压成
     各占一半宽度的小字块，读起来断断续续 */
  @include bp.below("md") {
    flex-basis: 100%;
    margin-left: 0;
  }
}

/* 五列：方向 / 双条 / 组合值 / 我值 / 差值。
   行铺满卡片宽度：此前写死 max-width: 880px，而卡片实测 1174px，
   右侧 290px 变成一块没有分隔线的空白 —— 看起来像「表格少画了一截」。
   数字列本来就紧跟在条形右端（不是被 1fr 推到天边），拉满不会破坏对照关系。 */
.dir__head,
.dir {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) 60px 60px 60px;
  gap: var(--space-3);
  align-items: center;

  @include bp.below("md") {
    grid-template-columns: 48px minmax(0, 1fr) 48px 48px 44px;
    gap: var(--space-2);
  }
}

.dir__head {
  padding-bottom: 6px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  border-bottom: 1px solid var(--border-light);

  span:nth-child(n + 3) {
    text-align: right;
  }
}

.dir {
  padding: 11px 0;
  border-bottom: 1px solid var(--border-light);

  &:last-of-type {
    border-bottom: none;
  }
}

.dir__k {
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.dir__bars {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.dir__track {
  height: 6px;
  overflow: hidden;
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.dir__fill {
  display: block;
  height: 100%;
  border-radius: inherit;

  &--adv {
    background: var(--color-primary);
  }

  &--mine {
    background: var(--palette-caramel);
  }
}

.dir__v {
  font-family: var(--font-number);
  font-size: var(--text-label);
  color: var(--text-secondary);
  text-align: right;
  white-space: nowrap;
}

.dir__d {
  font-family: var(--font-number);
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-align: right;
  white-space: nowrap;

  /* 差值点色是「这两档方向不一样」的唯一另色提示，不是排名 */
  &--big {
    font-weight: 600;
    color: var(--color-warning-ink);
  }
}

.callout {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  padding: var(--space-3) var(--space-compact);
  margin-top: var(--space-4);
  font-size: var(--text-label);
  color: var(--text-primary);
  background: color-mix(in srgb, var(--color-warning) 14%, var(--bg-card));
  border-left: 3px solid var(--color-warning-fill);
  border-radius: var(--radius-sm);
}

.callout__icon {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  margin-top: 2px;
  font-family: var(--font-number);
  font-size: var(--text-label);
  font-weight: 700;
  color: var(--color-warning-ink);
  border: 1.3px solid currentColor;
  border-radius: 50%;
}

.callout__text {
  margin: 0;
  line-height: 1.6;
}

.callout__lead {
  color: var(--color-warning-ink);
}

.callout b {
  font-weight: 600;
  color: var(--color-warning-ink);
}
</style>
