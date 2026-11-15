<!--
  RankBarList · 一行一条的排行条列表（共享渲染器，2026-11-15 上提）

  来源：原 `PenetrationPanel/PenetrationBarList.vue`（穿透面板私有子组件）。
  为什么上提：同一个页面里两块「Top N」榜各写一套 —— 穿透个股层用条列表、
  持仓结构 Top 5 手写 `<table>`，于是同一个问题在两个位置有两种长相；而持仓结构
  那版还并排列了两个同量纲的占比（占组合 5.6% / 占股票 8.6%），实测读不出区别。
  收敛后：同页两块榜共用一个渲染器，右侧只放**一个**百分比，金额等精确值走
  悬浮提示 / 页面下方的持仓明细，不在行内再挤第二个数字。

  只做「渲染」：条长与两侧文案都由父组件按各自口径算好再传进来
  （穿透行业行以「已穿透」为分母、个股行以总市值为分母；持仓结构以占组合为分母
  并按组内最大值归一）——分母口径属于业务语义，不能在一份共享渲染器里猜。
-->
<template>
  <ul class="rank-bar-list">
    <li v-for="row in rows" :key="row.key" class="rank-bar-row">
      <span class="rank-bar-identity" :title="row.title">
        <span class="rank-bar-name">{{ row.name }}</span>
        <span v-if="row.sub" class="rank-bar-sub">{{ row.sub }}</span>
      </span>
      <span class="rank-bar-track" aria-hidden="true">
        <span
          class="rank-bar-fill"
          :class="{ 'is-alt': row.alt }"
          :style="{ width: row.width }"
        />
      </span>
      <span class="rank-bar-value">{{ row.value }}</span>
    </li>
  </ul>
</template>

<script setup lang="ts">
defineOptions({ name: "RankBarList" });

defineProps<{
  rows: {
    key: string;
    /** 主名：产品名 / 行业名 */
    name: string;
    /** 副标题（可选）：代码、合并账户数等身份信息，11px 弱色，另起一行省略 */
    sub?: string;
    /** 悬浮提示：持有基金数 / 市值 / 口径说明等——行内不放的精确值都塞这里 */
    title: string;
    /** 条形宽度（0~100% 的 CSS 宽度字符串） */
    width: string;
    /** 右侧主数值（已格式化）——**只放一个百分比**，不再并排第二个同量纲数字 */
    value: string;
    /** 是否用第二色（个股层与行业层区分） */
    alt?: boolean;
  }[];
}>();
</script>

<style scoped lang="scss">
.rank-bar-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
  padding: 0;
  margin: 0;
  list-style: none;
}

.rank-bar-row {
  display: grid;
  grid-template-columns: minmax(110px, 200px) 1fr 56px;
  gap: var(--space-compact);
  align-items: center;
  font-size: var(--text-small);
  color: var(--text-secondary);
}

/* 名称与副标题上下两行：并排时「招商信用添利债券C」+「009637 · 2 个账户合并」
   在 200px 里互相挤压，名字会被压成半截；上下两行各自省略更稳。 */
.rank-bar-identity {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.rank-bar-name {
  overflow: hidden;
  color: var(--text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rank-bar-sub {
  overflow: hidden;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rank-bar-track {
  height: 8px;
  overflow: hidden;
  background: var(--bg-muted);
  border-radius: 4px;
}

.rank-bar-fill {
  display: block;
  height: 100%;
  background: var(--color-primary);
  border-radius: 4px;
}

.rank-bar-fill.is-alt {
  background: var(--color-info);
}

.rank-bar-value {
  font-variant-numeric: tabular-nums;
  text-align: right;
}
</style>
