<!--
  ClearedRankList · 清仓周期的「最赚 / 最亏」两栏排行（#2774）

  为什么单独成文件：这段排行让 `ClearedCyclesSection.vue` 越过 400 行门槛
  （`scripts/check_vue_size.mjs`，issue #980 的「上帝页面拆分」），而它本身就是
  独立展示单元（只吃 `cycles`、只调 `pickTop`），拆出来比压缩代码更合理。

  两栏并置而非切换：桌面端宽度足够，「最赚」与「最亏」同时可见才能看出盈亏是否
  对称；点一下才看得到另一栏纯属白花一次操作。

  排序与过滤纪律全在 `helpers.pickTop`（只收 pnl_known 且非零、不改动入参顺序），
  本组件不重复实现。
-->
<template>
  <CardBlock>
    <div class="rank-grid">
      <section
        v-for="col in columns"
        :key="col.direction"
        class="rank-col"
        :aria-label="col.title"
      >
        <header class="rank-col__head">
          <h3 class="rank-col__title">{{ col.title }}</h3>
          <span class="rank-col__meta">按已实现盈亏</span>
        </header>

        <ol v-if="col.rows.length" class="rank-list">
          <li
            v-for="(row, i) in col.rows"
            :key="cycleRowKey(row)"
            class="rank-row"
          >
            <span class="rank-row__no" :class="{ 'is-top': i < 3 }">
              {{ i + 1 }}
            </span>
            <span class="rank-row__name" :title="row.name || row.symbol || ''">
              {{ row.name || row.symbol || "--" }}
            </span>
            <MoneyDisplay
              :value="row.realized_pnl"
              show-sign
              auto-color
              size="sm"
              class="rank-row__pnl"
            />
            <RiseFallText
              v-if="row.pnl_pct !== null"
              :value="row.pnl_pct"
              size="sm"
              class="rank-row__pct"
            />
            <span v-else class="rank-row__pct is-na">--</span>
          </li>
        </ol>
        <p v-else class="rank-empty">{{ col.empty }}</p>
      </section>
    </div>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import type { ClearedCycle } from "@/api/summary";
import { cycleRowKey, pickTop, type RankDirection } from "./helpers";

defineOptions({ name: "ClearedRankList" });

const props = withDefaults(
  defineProps<{
    /** 当前筛选范围内的清仓周期（已由后端按末卖日裁剪，这里不再过滤） */
    cycles?: readonly ClearedCycle[];
  }>(),
  { cycles: () => [] }
);

type RankColumn = {
  direction: RankDirection;
  title: string;
  empty: string;
  rows: ClearedCycle[];
};

/** 两栏同取前 5；空栏各自给文案，避免用户以为另一栏坏了 */
const columns = computed<RankColumn[]>(() => [
  {
    direction: "win",
    title: "最赚 5 笔",
    empty: "当前范围内没有盈利清仓",
    rows: pickTop(props.cycles, "win")
  },
  {
    direction: "loss",
    title: "最亏 5 笔",
    empty: "当前范围内没有亏损清仓",
    rows: pickTop(props.cycles, "loss")
  }
]);
</script>

<style scoped>
/* 两栏并置：窄屏折成一栏（排行与明细同宽，折行不影响可读性） */
.rank-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--space-standard);
}

.rank-col__head {
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding-bottom: 8px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--border-light);
}

.rank-col__title {
  margin: 0;
  font-size: var(--text-label);
  font-weight: 500;
  color: var(--text-primary);
}

.rank-col__meta {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.rank-list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.rank-row {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) auto 56px;
  gap: 10px;
  align-items: center;
  min-height: 34px;
  border-bottom: 1px solid var(--border-subtle);
}

.rank-row:last-child {
  border-bottom: 0;
}

.rank-row__no {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
}

/* 前三名只加权重、不加奖牌图标：这一节读的是金额，不是比赛 */
.rank-row__no.is-top {
  font-weight: 600;
  color: var(--brand-ink);
}

.rank-row__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-primary);
  white-space: nowrap;
}

.rank-row__pnl,
.rank-row__pct {
  justify-self: end;
  font-variant-numeric: tabular-nums;
}

.rank-row__pct.is-na {
  color: var(--text-tertiary-ink);
}

.rank-empty {
  padding: 18px 0;
  margin: 0;
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}
</style>
