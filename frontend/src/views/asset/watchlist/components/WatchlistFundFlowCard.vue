<!--
  WatchlistFundFlowCard · 自选页顶部「盘前资金面」卡（#watchlist 资金面）

  定位：与 IndexMarketBar（大盘体温计）上下分层，提供「板块今日资金表现 +
  一句话今日资金主线」，属**个股级资金面之上**的市场级摘要。数据来自东财板块
  资金流（fetchSectorFundFlow，行业板块主力净流入排名）。

  与探市页边界：探市页承担全市场温度 / 行业情绪 / 拥挤度（情绪口径），本卡是
  「真金白银流向」口径，两者不重复。

  着色：主力净流入为正（资金买入主导）→ 涨色；为负（净流出）→ 跌色（A 股习惯）。
-->
<template>
  <section class="fund-flow-card" aria-label="盘前资金面">
    <header class="fund-flow-card__head">
      <div class="fund-flow-card__heading">
        <span class="fund-flow-card__title">盘前资金面 · 板块主力净流入</span>
        <span class="fund-flow-card__src">东方财富 · 开盘前速览</span>
      </div>
      <button
        type="button"
        class="fund-flow-card__toggle"
        :aria-expanded="expanded ? 'true' : 'false'"
        aria-controls="fund-flow-body"
        @click="toggle"
      >
        <span>{{ expanded ? "收起" : "展开" }}</span>
        <el-icon><component :is="toggleIcon" /></el-icon>
      </button>
    </header>

    <!-- 折叠态：一行预览，保留资金主线上下文但省版面（默认折叠） -->
    <div v-if="!expanded" class="fund-flow-card__preview">
      <span v-if="themeLine">{{ themeLine }}</span>
      <span v-else class="fund-flow-card__empty">板块资金数据加载中…</span>
    </div>

    <!-- 展开态：完整板块榜 + 主线 -->
    <div v-else id="fund-flow-body" class="fund-flow-card__body">
      <ul v-if="sectors.length" class="sector-list">
        <li
          v-for="s in topSectors"
          :key="s.code"
          class="sector-item"
          :class="flowClass(s)"
          :title="`${s.name}：主力净流入 ${formatYuan(s.mainInflow)}（${
            s.changePct >= 0 ? '+' : ''
          }${s.changePct.toFixed(2)}%）`"
        >
          <span class="sector-item__name">{{ s.name }}</span>
          <span class="sector-item__val">{{ formatFlow(s.mainInflow) }}</span>
        </li>
      </ul>
      <p v-if="themeLine" class="fund-flow-card__theme">{{ themeLine }}</p>
      <div v-else-if="!sectors.length" class="fund-flow-card__empty">
        板块资金数据加载中…
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { ArrowDown, ArrowUp } from "@element-plus/icons-vue";
import type { SectorFundFlow } from "@/utils/realtimeDataSources";
import { useCollapsedState } from "@/views/asset/watchlist/composables/useCollapsedState";

const props = defineProps<{ sectors: SectorFundFlow[] }>();

// #watchlist 资金面卡收起：默认折叠省版面；展开态才渲染完整板块榜 + 主线。
// 折叠/展开状态本地记忆（useCollapsedState）。
const { expanded } = useCollapsedState("fund-flow");
const toggleIcon = computed(() => (expanded.value ? ArrowUp : ArrowDown));
function toggle(): void {
  expanded.value = !expanded.value;
}

const TOP_N = 6;

const topSectors = computed(() => props.sectors.slice(0, TOP_N));

/** 亿 / 万自适应缩写（亿元口径更贴合主力资金量级） */
function formatFlow(v: number): string {
  const abs = Math.abs(v);
  const sign = v > 0 ? "+" : v < 0 ? "-" : "";
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${sign}${Math.round(abs / 1e4)}万`;
  return `${sign}${abs.toFixed(0)}`;
}

/** 完整元（用于 title 悬浮说明） */
function formatYuan(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toLocaleString("zh-CN")} 元`;
}

function flowClass(s: SectorFundFlow): string {
  if (s.mainInflow > 0) return "is-inflow";
  if (s.mainInflow < 0) return "is-outflow";
  return "is-flat";
}

/**
 * 一句话今日资金主线：取主力净流入前三（买入主导）、净流出前二（最被抛售），
 * 动态拼出，不写死。无数据时返回空串（模板不渲染）。
 */
const themeLine = computed(() => {
  const list = props.sectors;
  if (!list.length) return "";
  const sorted = [...list].sort((a, b) => b.mainInflow - a.mainInflow);
  const inflow = sorted.filter(s => s.mainInflow > 0).slice(0, 3);
  const outflow = sorted
    .filter(s => s.mainInflow < 0)
    .slice(-2)
    .reverse();
  const inNames = inflow.map(s => s.name);
  const outNames = outflow.map(s => s.name);
  if (inNames.length && outNames.length) {
    return `今日资金主线：${inNames.join("、")} 获主力净流入居前；${outNames.join(
      "、"
    )} 主力净流出居前。`;
  }
  if (inNames.length) {
    return `今日资金主线：${inNames.join("、")} 获主力净流入居前。`;
  }
  if (outNames.length) {
    return `今日资金主线：${outNames.join("、")} 主力净流出居前。`;
  }
  return "";
});
</script>

<style scoped lang="scss">
.fund-flow-card {
  padding: 12px 12px 10px;
  margin-bottom: 12px;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-default, #eee);
  border-radius: 12px;
}

.fund-flow-card__head {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}

.fund-flow-card__heading {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

// 展开/收起按钮：复用 IndexMarketBar 的折叠交互样式（#1546 T2.2 范式）
.fund-flow-card__toggle {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 4px 12px;
  font-family: inherit;
  font-size: var(--text-label);
  color: var(--text-secondary, #888);
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--border-light, #f0ebe4);
  border-radius: var(--radius-pill, 9999px);
  transition:
    background-color 150ms ease,
    color 150ms ease;

  &:hover {
    color: var(--text-primary, #333);
    background: var(--bg-hover, #f2ede8);
  }

  &:focus-visible {
    outline: none;
    box-shadow: var(--focus-ring);
  }
}

.fund-flow-card__preview {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-primary, #333);
}

.fund-flow-card__title {
  font-size: var(--text-label);
  font-weight: 600;
  color: var(--text-primary, #333);
}

.fund-flow-card__src {
  font-size: var(--text-label);
  color: var(--text-disabled, #bbb);
}

.fund-flow-card__body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sector-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.sector-item {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 84px;
  padding: 6px 10px;
  background: var(--bg-page, #fafafa);
  border: 1px solid var(--border-default, #eee);
  border-radius: 8px;
}

.sector-item__name {
  font-size: var(--text-label);
  color: var(--text-secondary, #666);
}

.sector-item__val {
  font-size: var(--text-num-strong);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

// 资金流符号色（A 股习惯：流入红 / 流出绿）
.is-inflow .sector-item__val {
  color: var(--color-rise);
}

.is-outflow .sector-item__val {
  color: var(--color-fall-ink);
}

.is-flat .sector-item__val {
  color: var(--text-secondary, #888);
}

.fund-flow-card__theme {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-primary, #333);
}

.fund-flow-card__empty {
  font-size: var(--text-label);
  color: var(--text-disabled, #bbb);
}
</style>
