<!--
  PnlCalendarCaliberTip · 收益日历的「口径 + 图例」卡片（#1942 第三轮反馈）

  原先这一整段口径说明是一条约 500 字的**字符串**，直接塞进 tooltip 的 `content`：
  没有层级、没有宽度约束，悬停出来就是一堵墙（用户截图的正是它，评价「没有设计感」）。
  文案本身没错，错在**载体**：tooltip 的定位是「补一个数」，不是「读一段文」。

  所以这里把它拆成两块，都做成可扫读的结构：

    口径  3 条：某一天的数字是怎么来的（以及为什么与「总资产日环比」对不上）
    图例  7 态：格子上那些颜色 / 标签 / 纹理各自什么意思

  **图例的态标签直接调 `stateTag()`**，与 `PnlCalendarTile` 同一份文案——
  图例与格子各写一份，迟早出现「图例说未同步、格子说没数据」的分叉。

  更长的口径（公式、as-of 份额、可加性证明）属于文档，不属于气泡：
  这里只留「一眼要用」的那几句。
-->

<template>
  <div class="caliber-tip">
    <div class="caliber-tip__block">
      <div class="caliber-tip__title">口径</div>
      <ul class="caliber-tip__list">
        <li>
          当日收益 = <b>总盈亏的变化</b>，充值与提现不计入。先有 1 万浮盈、再充
          5 万，今天显示的不会是 6 万。
        </li>
        <li>
          与「总资产日环比」有出入是正常的：基金按净值日切、股票按交易日切，
          同一天未必同价。
        </li>
        <li>
          建仓当日不记盈亏（那一刻浮盈本来就是 0）；月 /
          年视图是<b>同一份</b>日盈亏的 合计，点格子可下钻。
        </li>
      </ul>
    </div>

    <div class="caliber-tip__block">
      <div class="caliber-tip__title">图例</div>
      <ul class="caliber-tip__list caliber-tip__list--legend">
        <li>
          <span
            class="caliber-tip__chip caliber-tip__chip--rise"
            aria-hidden="true"
          />
          <span
            class="caliber-tip__chip caliber-tip__chip--fall"
            aria-hidden="true"
          />
          涨红跌绿，底色越深表示幅度越大（相对本区间最大者）
        </li>
        <li v-for="item in LEGEND" :key="item.state">
          <span class="caliber-tip__tag">{{ stateTag(item.state) }}</span>
          {{ item.note }}
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { PnlCalendarState } from "@/api/summary";
import { stateTag } from "./helpers";

defineOptions({ name: "PnlCalendarCaliberTip" });

/**
 * 图例只列「需要解释」的六态：`updown` 由第一行的涨跌色说明，
 * 逐个列出来反而稀释重点（`stateTag(updown)` 本就是空串）。
 */
const LEGEND: { state: PnlCalendarState; note: string }[] = [
  { state: "zero", note: "当天真实为零（不是缺数据）" },
  { state: "partial", note: "部分标的未更新估值：数字可信，但不完整" },
  { state: "no_data", note: "开盘日却没取到当天估值，该去跑同步任务了" },
  { state: "no_position", note: "建仓前 / 清仓后" },
  { state: "closed", note: "非 A 股开盘日（日历只列工作日，周末不占格）" },
  {
    state: "no_price",
    note: "该产品按日没有估值序列（银行理财 / 投顾 / 实物等）"
  }
];
</script>

<style scoped>
.caliber-tip {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.caliber-tip__block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.caliber-tip__title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

/* 口径：普通段落列表（用 disc 圆点分行）。
   ⚠️ 这里**不能**给 `li` 加 `display: flex`：句子里的 `<b>` 会变成独立 flex 项，
   整句被拆成几段并排（实测 2026-10-07：「当日收益 =」「总盈亏的变化」「，充值与…」
   被排成三列）。图例行才需要 flex（标签固定左列）。 */
.caliber-tip__list {
  padding-left: 16px;
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  list-style: disc;
}

.caliber-tip__list li + li {
  margin-top: 4px;
}

/* 图例：去掉圆点，改成「标签（固定宽）+ 解释」两列，扫读时文字不会左右跳 */
.caliber-tip__list--legend {
  padding-left: 0;
  list-style: none;
}

.caliber-tip__list--legend li {
  display: flex;
  gap: 6px;
  align-items: center;
}

.caliber-tip__tag {
  flex-shrink: 0;
  min-width: 44px;
  padding: 1px 6px;
  font-size: 11px;
  color: var(--text-tertiary-ink);
  text-align: center;
  background: var(--bg-card);
  border: 1px dashed var(--border-default);
  border-radius: var(--radius-sm);
}

/* 涨跌两个色点：只表达「红涨绿跌」这一条语义，不复制格子的底色算法 */
.caliber-tip__chip {
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  border-radius: 3px;
}

.caliber-tip__chip--rise {
  background: color-mix(in srgb, var(--color-rise) 24%, var(--bg-card));
}

.caliber-tip__chip--fall {
  background: color-mix(in srgb, var(--color-fall) 24%, var(--bg-card));
}
</style>
