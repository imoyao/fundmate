<!--
  WatchlistFundFlowCard · 自选页顶部「盘前资金面」卡（#watchlist 资金面）

  定位：与 IndexMarketBar（大盘体温计）上下分层，提供「板块资金双向表现 +
  一句话今日资金主线」，属**个股级资金面之上**的市场级摘要。数据来自东财板块
  资金流（fetchSectorFundFlow：流入头部 + 流出头部两端）。

  与探市页边界：探市页承担全市场温度 / 行业情绪 / 拥挤度（情绪口径），本卡是
  「真金白银流向」口径，两者不重复。

  折叠态为什么是静态数字条、而不是跑马灯：
    资金面的核心读法是「流入端 vs 流出端」的**对比**，一流动就只剩一半；
    且板块数量由数据自动取头尾（3+3），一行放得下，不存在需要流动承接的溢出。
    跑马灯留给大盘指数条（同类单值长列表），两张卡一静一动才有层次。

  折叠态为什么不是整句主线：
    `themeLine` 是 30–50 字的中文句子，窄容器必然折行 → 折叠后仍占 3 行。
    故折叠态只留结构化数字（省一行且可直接比较），整句移到展开态作结论句。
-->
<template>
  <section class="fund-flow-card" aria-label="盘前资金面">
    <header class="fund-flow-card__head">
      <p class="fund-flow-card__heading">
        <span class="fund-flow-card__title">盘前资金面 · 板块主力净流入</span>
        <span class="fund-flow-card__src">东方财富 · 开盘前速览</span>
      </p>
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

    <!-- 折叠态：一行数字条，流入与流出同时可见 -->
    <div v-if="!expanded" class="fund-flow-card__preview">
      <template v-if="hasData">
        <span class="flow-tag flow-tag--in">流入</span>
        <span
          v-for="s in collapsed.inflow"
          :key="`in-${s.code}`"
          class="flow-mini"
        >
          <span class="flow-mini__name">{{ s.name }}</span>
          <span class="flow-mini__val" :class="trendClassOf(s.mainInflow)">
            {{ formatFlow(s.mainInflow) }}
          </span>
        </span>
        <span class="flow-sep" aria-hidden="true" />
        <span class="flow-tag flow-tag--out">流出</span>
        <span
          v-for="s in collapsed.outflow"
          :key="`out-${s.code}`"
          class="flow-mini"
        >
          <span class="flow-mini__name">{{ s.name }}</span>
          <span class="flow-mini__val" :class="trendClassOf(s.mainInflow)">
            {{ formatFlow(s.mainInflow) }}
          </span>
        </span>
      </template>
      <span v-else class="fund-flow-card__empty">板块资金数据加载中…</span>
    </div>

    <!-- 展开态：流入 / 流出双列 TOP4 + 一句话主线 -->
    <div v-else id="fund-flow-body" class="fund-flow-card__body">
      <div class="flow-cols">
        <section v-for="side in expandedSides" :key="side.key" class="flow-col">
          <header class="flow-col__head">
            <span class="flow-tag" :class="`flow-tag--${side.key}`">{{
              side.label
            }}</span>
            <span>主力净{{ side.label }} TOP{{ EXPANDED_TOP_N }}</span>
          </header>
          <ul class="flow-col__list">
            <li
              v-for="s in side.items"
              :key="`${side.key}-${s.code}`"
              class="flow-row"
              :title="`${s.name}：主力净流入 ${formatYuan(s.mainInflow)}`"
            >
              <span class="flow-row__name">{{ s.name }}</span>
              <span class="flow-row__pct" :class="trendClassOf(s.mainInflow)">
                {{ formatChangePct(s.changePct) }}
              </span>
              <span class="flow-row__val" :class="trendClassOf(s.mainInflow)">
                {{ formatFlow(s.mainInflow) }}
              </span>
            </li>
          </ul>
        </section>
      </div>

      <p v-if="themeLine" class="fund-flow-card__theme">{{ themeLine }}</p>
      <div v-else-if="!hasData" class="fund-flow-card__empty">
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
import {
  buildThemeLine,
  formatChangePct,
  formatFlow,
  formatYuan,
  splitSectorFlow,
  trendClassOf
} from "@/views/asset/watchlist/composables/fundFlowModel";

const props = defineProps<{ sectors: SectorFundFlow[] }>();

// #watchlist 资金面卡收起：默认折叠省版面；展开态才渲染完整板块榜 + 主线。
// 折叠/展开状态本地记忆（useCollapsedState）。
const { expanded } = useCollapsedState("fund-flow");
const toggleIcon = computed(() => (expanded.value ? ArrowUp : ArrowDown));
function toggle(): void {
  expanded.value = !expanded.value;
}

/** 折叠态每侧数量：3+3 在 ~1080px 内容宽下一行放得下，不需要滚动 */
const COLLAPSED_TOP_N = 3;
/** 展开态每侧数量 */
const EXPANDED_TOP_N = 4;

const collapsed = computed(() =>
  splitSectorFlow(props.sectors, COLLAPSED_TOP_N)
);
const expandedBoard = computed(() =>
  splitSectorFlow(props.sectors, EXPANDED_TOP_N)
);

const hasData = computed(
  () => collapsed.value.inflow.length > 0 || collapsed.value.outflow.length > 0
);

const expandedSides = computed(() => [
  { key: "in", label: "流入", items: expandedBoard.value.inflow },
  { key: "out", label: "流出", items: expandedBoard.value.outflow }
]);

const themeLine = computed(() => buildThemeLine(expandedBoard.value));
</script>

<style scoped lang="scss">
.fund-flow-card {
  padding: 12px 12px 10px;
  margin-bottom: 12px;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-default, #eee);
  border-radius: 12px;
}

// 标题与来源同行：来源是副标题，不该独占一行（折叠态省下的正是这一行）
.fund-flow-card__head {
  display: flex;
  gap: 8px;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}

.fund-flow-card__heading {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: baseline;
  margin: 0;
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

// 展开/收起按钮：复用 IndexMarketBar 的折叠交互样式（#1546 T2.2 范式）
.fund-flow-card__toggle {
  display: inline-flex;
  flex-shrink: 0;
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

// 折叠态数字条：一行内「流入 3 + 分隔 + 流出 3」，不滚动
.fund-flow-card__preview {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: baseline;
  margin: 0;
  line-height: 1.5;
}

.flow-tag {
  flex-shrink: 0;
  padding: 1px 6px;
  font-size: var(--text-label);
  font-weight: 600;
  background: var(--bg-subtle, #f7f3ee);
  border-radius: 4px;

  &--in {
    color: var(--color-rise-ink);
  }

  &--out {
    color: var(--color-fall-ink);
  }
}

.flow-mini {
  display: inline-flex;
  flex-shrink: 0;
  gap: 4px;
  align-items: baseline;
  font-size: var(--text-label);
  white-space: nowrap;

  &__name {
    color: var(--text-secondary, #666);
  }

  &__val {
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
}

.flow-sep {
  flex-shrink: 0;
  align-self: center;
  width: 1px;
  height: 14px;
  background: var(--border-default, #eee);
}

.fund-flow-card__body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.flow-cols {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.flow-col {
  padding: 8px 10px;
  background: var(--bg-page, #fafafa);
  border: 1px solid var(--border-default, #eee);
  border-radius: 10px;

  &__head {
    display: flex;
    gap: 6px;
    align-items: center;
    margin-bottom: 6px;
    font-size: var(--text-label);
    color: var(--text-secondary, #666);
  }

  &__list {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 0;
    margin: 0;
    list-style: none;
  }
}

.flow-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 8px;
  align-items: baseline;
  padding: 2px 0;
  font-size: var(--text-label);

  &__name {
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-primary, #333);
    white-space: nowrap;
  }

  &__pct {
    font-variant-numeric: tabular-nums;
    opacity: 0.85;
  }

  &__val {
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
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

// 资金流语义色（A 股习惯：流入红 / 流出绿）
.is-rise {
  color: var(--color-rise);
}

.is-fall {
  color: var(--color-fall-ink);
}

.is-flat {
  color: var(--text-secondary, #888);
}
</style>
