<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { fetchProAllocation } from "@/api/products";
import ProductProEntitlementNotice from "./ProductProEntitlementNotice.vue";
import {
  classifyProPanelFailure,
  type ProPanelFailure
} from "./proEntitlement";

/**
 * Pro 模块三「资产配置与相关性」——组合相关性内容（#994 Phase 2）。
 *
 * ## 数据与口径
 *
 * `GET /api/products/pro-allocation/`：以本标的为基准，逐只给出它与你**家庭其余
 * 持仓**的日收益 Pearson 相关系数（|ρ| 降序）。
 *
 * - 相关性按**日收益日期交集**配对：停牌、净值发布延迟只丢样本，不会把两只
 *   错开一天当成同期 ;
 * - 收益率算法与模块二 `analytics/var.py` 同源——同一只基金不会算出两组日收益；
 * - 同期交易日不足 60 天、或某只收益零方差（货基/长期停牌）⇒ 该只跳过，
 *   跳过的只数由后端 `skipped_count` 原样披露：没有进结论的东西要让用户知道。
 *
 * ## 配色纪律（重要）
 *
 * **红绿是涨跌语义专用**，这里不用。ρ 表达的是「联动强度」不是涨跌：
 * - ρ ≥ 0.8 → 危险档（账面分散、风险仍集中）走 `--color-warning-ink`；
 * - 0.4 ≤ ρ < 0.8 → 中等关联，中性主色；
 * - ρ < 0（负相关，真分散）→ 弱化到辅助文字级——它不是问题，反而是对冲。
 */
const props = defineProps<{
  /** 产品代码（与状态位同源） */
  symbol: string;
  /** 入口提示品类（透传，决定序列口径） */
  assetType?: string | null;
}>();

/** 高度相关阈值，与后端 analytics 口径一致（ρ ≥ 0.8 视为实际未分散） */
const HIGH_THRESHOLD = 0.8;
/** 中等相关阈值：以上值得提示，以下不必强调 */
const MID_THRESHOLD = 0.4;

const DASH = "—";

const loading = ref(false);
/** 失败态三选一（`none` / `entitlement` / `error`），判据见 `proEntitlement.ts` */
const failure = ref<ProPanelFailure>("none");
const data = ref<Awaited<ReturnType<typeof fetchProAllocation>>["data"] | null>(
  null
);

const peers = computed(() => data.value?.peers ?? []);
const highCount = computed(() => data.value?.high_correlation_count ?? 0);

/** ρ 的档位（决定配色与文案），不要和「涨跌」混用语义 */
function tone(rho: number): "high" | "mid" | "low" {
  if (rho >= HIGH_THRESHOLD) return "high";
  if (rho >= MID_THRESHOLD || rho <= -MID_THRESHOLD) return "mid";
  return "low";
}

/** 相关系数文案：只描述事实，不给操作建议 */
function describe(rho: number): string {
  if (rho >= HIGH_THRESHOLD) return "基本同步涨跌";
  if (rho >= MID_THRESHOLD) return "明显联动";
  if (rho <= -MID_THRESHOLD) return "走势相反（有对冲作用）";
  if (rho < 0) return "轻度反向";
  return "关联很弱";
}

/** 联动强度条：宽度表达 |ρ|，0.5 对应 50% */
function barWidth(rho: number): string {
  return `${Math.round(Math.abs(rho) * 100)}%`;
}

/** 高度相关的总结句：这条才是本模块真正要让 user 看见的话 */
const summary = computed<string | null>(() => {
  const total = peers.value.length;
  if (total === 0) return null;
  if (highCount.value === 0) {
    return `与你其余 ${total} 只持仓中，没有ρ ≥ ${HIGH_THRESHOLD} 的强联动标的——这一只确实带来了分散。`;
  }
  return `与你其余 ${total} 只持仓中，有 ${highCount.value} 只相关系数 ≥ ${HIGH_THRESHOLD}——账面分散了，风险未必。`;
});

/** 跳过的持仓说明（诚实披露，不静默丢弃） */
const skippedNote = computed<string | null>(() => {
  const n = data.value?.skipped_count ?? 0;
  if (n <= 0) return null;
  return `另有 ${n} 只持仓因同期交易日不足 ${data.value?.min_overlap ?? 60} 天或无波动未纳入计算`;
});

const footnote = computed(() => {
  const d = data.value;
  if (!d) return "";
  const parts: string[] = [];
  if (d.basis) parts.push(d.basis);
  parts.push(`近${d.window}窗口 · 基准序列 ${d.sample_days} 个交易日`);
  if (d.caveats.length) parts.push(d.caveats[0]);
  return parts.join(" · ");
});

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failure.value = "none";
  data.value = null;
  try {
    const res = await fetchProAllocation(props.symbol, props.assetType);
    data.value = res.data;
  } catch (error) {
    // 权益未开通（403 + error_code=1007）≠ 故障：前者讲边界、后者讲「稍后再试」。
    // 两种态都只降级本块，不阻塞 Pro 卡内其余内容
    failure.value = classifyProPanelFailure(error);
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <section class="pro-alloc">
    <p v-if="loading" class="pro-alloc__hint">正在计算与你其余持仓的相关性…</p>

    <ProductProEntitlementNotice
      v-else-if="failure === 'entitlement'"
      subject="相关性分析"
    />

    <p v-else-if="failure === 'error'" class="pro-alloc__hint">
      相关性暂时取不到，稍后再来看看
    </p>

    <template v-else-if="peers.length">
      <p v-if="summary" class="pro-alloc__summary">{{ summary }}</p>

      <ul class="pro-alloc__list">
        <li
          v-for="peer in peers"
          :key="peer.symbol"
          class="pro-alloc__row"
          :class="`pro-alloc__row--${tone(peer.correlation)}`"
        >
          <div class="pro-alloc__row-head">
            <span class="pro-alloc__name" :title="peer.symbol">{{
              peer.name || peer.symbol
            }}</span>
            <span class="pro-alloc__rho">
              {{ peer.correlation > 0 ? "+" : ""
              }}{{ peer.correlation.toFixed(2) }}
            </span>
          </div>
          <div class="pro-alloc__bar-track">
            <div
              class="pro-alloc__bar"
              :style="{ width: barWidth(peer.correlation) }"
            />
          </div>
          <div class="pro-alloc__row-foot">
            <span>{{ describe(peer.correlation) }}</span>
            <span>{{ peer.overlap_days }} 个同期交易日</span>
          </div>
        </li>
      </ul>

      <p v-if="skippedNote" class="pro-alloc__skipped">{{ skippedNote }}</p>
      <p v-if="footnote" class="pro-alloc__footnote">{{ footnote }}</p>
    </template>

    <!-- 无 peer 时的引导（不是错误态）：把「为什么没内容」讲清楚 -->
    <div v-else class="pro-alloc__empty">
      <p class="pro-alloc__empty-title">这里将展示「你是否真的分散了」</p>
      <p class="pro-alloc__empty-desc">
        买入这只标的后，会逐只计算它与你其余持仓的日收益相关系数：<br />
        相关系数 ≥ {{ HIGH_THRESHOLD }} 说明账面分散、风险仍集中。{{
          data?.reason ? `当前：${data.reason}` : DASH
        }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.pro-alloc {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--bg-muted);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.pro-alloc__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.pro-alloc__summary {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-primary);
}

.pro-alloc__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: 0;
  margin: 0;
  list-style: none;
}

.pro-alloc__row {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.pro-alloc__row-head {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  justify-content: space-between;
}

.pro-alloc__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-label);
  color: var(--text-primary);
  white-space: nowrap;
}

.pro-alloc__rho {
  flex-shrink: 0;
  font-size: var(--text-mono-small);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

/* ρ ≥ 0.8：账面分散而风险集中——用警示色而非涨跌红（红绿是涨跌语义专用） */
.pro-alloc__row--high .pro-alloc__rho {
  color: var(--color-warning-ink);
}

/* 明显联动 / 明显反向：提到主文字级，让人看见但不过度刺激 */
.pro-alloc__row--mid .pro-alloc__rho {
  color: var(--text-primary);
}

/* 关联很弱：弱化到辅助级 */
.pro-alloc__row--low .pro-alloc__rho {
  font-weight: 400;
  color: var(--text-tertiary-ink);
}

.pro-alloc__bar-track {
  height: 4px;
  overflow: hidden;
  background: var(--bg-soft);
  border-radius: var(--radius-pill);
}

.pro-alloc__bar {
  height: 100%;
  background: var(--border-default);
  border-radius: var(--radius-pill);
}

.pro-alloc__row--high .pro-alloc__bar {
  background: var(--color-warning-ink);
}

.pro-alloc__row--mid .pro-alloc__bar {
  background: var(--brand-ink);
}

.pro-alloc__row-foot {
  display: flex;
  gap: var(--space-2);
  justify-content: space-between;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.pro-alloc__skipped,
.pro-alloc__footnote {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}

.pro-alloc__empty {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.pro-alloc__empty-title {
  margin: 0;
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.pro-alloc__empty-desc {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-secondary);
}
</style>
