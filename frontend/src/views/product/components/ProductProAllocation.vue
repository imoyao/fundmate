<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { fetchProAllocation } from "@/api/products";

/**
 * Pro 模块三「资产配置与相关性」——组合相关性内容（#994 Phase 2，#2400 画法修订）。
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
 * ## 画法与配色纪律（重要，2026-10-19 #2400 修订）
 *
 * **红绿涨跌语义依然不碰**；但此处的红是**危险语义**（`--color-danger`，与
 * 删除 / 错误同级，#1602 后全站唯一危险色），与涨跌红（`--color-rise`）刻意
 * 区分。ρ ∈ [−1, +1] 表达「联动强度与方向」，两个维度分工：
 *
 * - **方向 = 几何**：发散条形图以 0 轴为界，正相关向右、负相关向左。
 *   （原进度条一律向右，−0.26 与 +0.66 同观感、只差一个负号——这是 #2400
 *   指出并修复的误导源。）
 * - **档位 = 颜色**：映射只在下方 CSS 四处出现一次，TS 的 `tone()` 只选
 *   class、不碰色值：
 *   - ρ ≥ 0.8 → `--color-danger`：账面分散、风险集中，本模块最该被看见的信号；
 *   - 0.4 ≤ ρ < 0.8 → `--color-warning-fill`：明显联动（#2400 新增图形级令牌）；
 *   - ρ ≤ −0.4 → `--color-info`：反向对冲——它不是问题，用信息色冷静呈现；
 *   - |ρ| < 0.4 → 中性灰弱化。
 *
 * 原实现的病灶：顶层档用 `--color-warning-ink`（**文字级**沙金 #806218）做
 * 条形填充 = 褐色；中间档用 `--brand-ink`（亮色 #b8361f 即红）——层级反了，
 * 最危险的档最不显眼。定性文案（明显联动 / 反向对冲…）收进图例，行内只留
 * 数字与样本数，界面更清爽。
 *
 * ## 名称与编码的分工（#2400）
 *
 * 名称**用于阅读**（主文字级）；编码**用于记录**——用户加自选、搜索、跟单时
 * 习惯对着编码找，而不是逐字读名称（名称在不同平台叫法可能不同，编码唯一）。
 * 故编码用等宽小字 + 辅助文字级排在行脚侧，与「N 个同期交易日」同列：
 * 抬头行留给「名称 + ρ」这对本模块真正要对比的信息，不被编码挤占。
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
const failed = ref(false);
const data = ref<Awaited<ReturnType<typeof fetchProAllocation>>["data"] | null>(
  null
);

const peers = computed(() => data.value?.peers ?? []);
const highCount = computed(() => data.value?.high_correlation_count ?? 0);

/** ρ 的档位（决定配色）；档位→令牌的映射只在 CSS 出现一次，见样式区 */
function tone(rho: number): "danger" | "warn" | "hedge" | "low" {
  if (rho >= HIGH_THRESHOLD) return "danger";
  if (rho >= MID_THRESHOLD) return "warn";
  if (rho <= -MID_THRESHOLD) return "hedge";
  return "low";
}

/** 发散条半宽：|ρ| × 50%（半轨），ρ = 1 时贴满一侧、抵达轨道边缘 */
function barWidth(rho: number): string {
  return `${Math.round(Math.abs(rho) * 50)}%`;
}

/** 图例：原每行重复的定性文案收敛到此（#2400） */
const LEGEND = [
  { tier: "danger", text: `风险集中 ρ ≥ ${HIGH_THRESHOLD}` },
  { tier: "warn", text: "明显联动" },
  { tier: "hedge", text: "反向对冲" },
  { tier: "low", text: "关联很弱" }
] as const;

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
  failed.value = false;
  data.value = null;
  try {
    const res = await fetchProAllocation(props.symbol, props.assetType);
    data.value = res.data;
  } catch {
    // 接口失败：整块降级，不阻塞 Pro 卡内其余内容
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <section class="pro-alloc">
    <p v-if="loading" class="pro-alloc__hint">正在计算与你其余持仓的相关性…</p>

    <p v-else-if="failed" class="pro-alloc__hint">
      相关性暂时取不到，稍后再来看看
    </p>

    <template v-else-if="peers.length">
      <p v-if="summary" class="pro-alloc__summary">{{ summary }}</p>

      <ul class="pro-alloc__legend" aria-label="相关性档位图例">
        <li
          v-for="item in LEGEND"
          :key="item.tier"
          class="pro-alloc__legend-item"
        >
          <span
            class="pro-alloc__legend-dot"
            :class="`pro-alloc__legend-dot--${item.tier}`"
          />
          {{ item.text }}
        </li>
        <li class="pro-alloc__legend-note">
          虚线 = 0 轴 · 轨道全程 ρ ∈ [−1, +1]
        </li>
      </ul>

      <ul class="pro-alloc__list">
        <li
          v-for="peer in peers"
          :key="peer.symbol"
          class="pro-alloc__row"
          :class="`pro-alloc__row--${tone(peer.correlation)}`"
        >
          <div class="pro-alloc__row-head">
            <span class="pro-alloc__name">{{ peer.name || peer.symbol }}</span>
            <span class="pro-alloc__rho">
              {{ peer.correlation > 0 ? "+" : ""
              }}{{ peer.correlation.toFixed(2) }}
            </span>
          </div>
          <div class="pro-alloc__track">
            <div class="pro-alloc__track-half">
              <div
                v-if="peer.correlation < 0"
                class="pro-alloc__bar"
                :style="{ width: barWidth(peer.correlation) }"
              />
            </div>
            <div class="pro-alloc__axis" aria-hidden="true" />
            <div class="pro-alloc__track-half">
              <div
                v-if="peer.correlation >= 0"
                class="pro-alloc__bar"
                :style="{ width: barWidth(peer.correlation) }"
              />
            </div>
          </div>
          <div class="pro-alloc__row-foot">
            <!-- 编码用于「记录」：加自选 / 搜索 / 对账时按码定位，不靠名称认。
                 原样展示，不缩写、不补前缀（与身份卡「代码」项同一原则）。 -->
            <span class="pro-alloc__code" :title="`基金代码 ${peer.symbol}`">{{
              peer.symbol
            }}</span>
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

/* ===== 图例（#2400）：每行重复的定性文案收敛到此 ===== */
.pro-alloc__legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-3);
  align-items: center;
  padding: 0;
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
  list-style: none;
}

.pro-alloc__legend-item {
  display: inline-flex;
  gap: var(--space-1);
  align-items: center;
}

.pro-alloc__legend-dot {
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  background: var(--border-default);
  border-radius: var(--radius-xs);
}

.pro-alloc__legend-dot--danger {
  background: var(--color-danger);
}

.pro-alloc__legend-dot--warn {
  background: var(--color-warning-fill);
}

.pro-alloc__legend-dot--hedge {
  background: var(--color-info);
}

.pro-alloc__legend-note {
  color: var(--text-tertiary-ink);
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

/* ρ ≥ 0.8：账面分散而风险集中——危险语义红（与涨跌红 --color-rise 刻意区分，#1602） */
.pro-alloc__row--danger .pro-alloc__rho {
  color: var(--color-danger-ink);
}

/* 明显联动 / 反向对冲：提到主文字级，让人看见但不过度刺激 */
.pro-alloc__row--warn .pro-alloc__rho,
.pro-alloc__row--hedge .pro-alloc__rho {
  color: var(--text-primary);
}

/* 关联很弱：弱化到辅助级 */
.pro-alloc__row--low .pro-alloc__rho {
  font-weight: 400;
  color: var(--text-tertiary-ink);
}

/* ===== 发散轨道（#2400）：0 轴居中，正右负左 ===== */
.pro-alloc__track {
  display: flex;
  align-items: center;
  height: 10px;
}

.pro-alloc__track-half {
  display: flex;
  flex: 1;
  align-items: center;
  min-width: 0;
  height: 4px;
}

/* 左半轨：条从 0 轴向左生长（右对齐贴轴） */
.pro-alloc__track-half:first-child {
  justify-content: flex-end;
}

.pro-alloc__axis {
  flex-shrink: 0;
  width: 0;
  height: 14px;
  border-left: 1px dashed var(--border-default);
}

.pro-alloc__bar {
  height: 100%;
  background: var(--border-default);
  border-radius: var(--radius-pill);
}

/* 右半轨的条：左端贴 0 轴，圆角留右端 */
.pro-alloc__track-half:last-child .pro-alloc__bar {
  border-radius: var(--radius-pill) 0 0 var(--radius-pill);
}

/* 左半轨的条：右端贴 0 轴，圆角留左端 */
.pro-alloc__track-half:first-child .pro-alloc__bar {
  border-radius: 0 var(--radius-pill) var(--radius-pill) 0;
}

/* 四档配色（#2400）：档位→令牌单一映射，只在此处出现一次 */
.pro-alloc__row--danger .pro-alloc__bar {
  background: var(--color-danger);
}

.pro-alloc__row--warn .pro-alloc__bar {
  background: var(--color-warning-fill);
}

.pro-alloc__row--hedge .pro-alloc__bar {
  background: var(--color-info);
}

.pro-alloc__row--low .pro-alloc__bar {
  background: var(--border-default);
}

.pro-alloc__row-foot {
  display: flex;
  gap: var(--space-2);
  justify-content: space-between;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 编码：等宽 + 辅助级（#2400）。名称是阅读对象、编码是记录对象，视觉权重必须
   低于名称——故不加标签底色、不加边框，只靠等宽字形与弱化色区分。 */
.pro-alloc__code {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-mono, monospace);
  font-size: var(--text-mono-small);
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
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
