<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getIndexProfile, type IndexProfileResult } from "@/api/products";

/**
 * 详情页「指数资料与估值」区块（#2028 · 设计 §6 品类矩阵二期；#2278 信息增强）。
 *
 * ## 取数
 *
 * `GET /api/products/index-profile/` 一次返回：名录资料（名称 / 发布机构）
 * + 中证官方估值（PE / 股息率，最新一期）+ PE 历史分位（乐咕月频近 5 年窗口现算，
 * 口径见 #1407 拍板）+ #2278 三块（快照四字段 / 阶段性收益 / 十大权重，见下）。
 *
 * ## 分位的语义边界（勿混）
 *
 * - `pe_percentile === null` 意为「基线样本不足 1 年（<12 点）或该指数乐咕无覆盖」，
 *   **不是**「分位为 0」——两者语义相反。前端显示「—」并附说明，不显示 0%；
 * - 分位口径 = 乐咕滚动市盈率（与 PE 绝对值的中证官方口径**不同源**），脚注必须
 *   同时给出口径名与基线日期，避免用户拿 PE 绝对值去核对分位（对不上是预期）；
 * - 股息率分位本期**恒为 null**（乐咕无股息率序列，自建日频积累未满 1 年），
 *   不显示占位。
 *
 * ## 降级（设计 §6 诚实降级）
 *
 * 缺官方估值文件的指数（中证只给自有/合作指数发 indicator 文件）：PE / 股息率
 * 逐项降级「—」，名录资料照常展示；整卡不因估值缺失而消失。
 *
 * `description`（指数简介）来自中证官网 index-basic-info（后端按需抓+进程内缓存）：
 * `null` = 官网未收录（399 系等）或抓取失败——散文不是指标，**整段隐藏**而不显示「—」。
 *
 * ## #2278 三块（同响应、独立降级、互不拖垮）
 *
 * - **快照四字段**（发布日期 / 样本数 / 加权方式 / 币种）并入 facts 行，
 *   与 basic-info 同一次请求，null →「—」（实测 931151 的样本数/加权方式即 null）；
 * - **阶段性收益**：6 窗口 + 近 1 年年化波动，服务端现算（中证官网日线优先、
 *   腾讯兜底），覆盖不足的窗口 null →「—」；整块 null（双源皆空/源异常）显「—」
 *   **不隐藏**——用户要知道这里本该有数据；
 * - **十大权重**：akshare 月频（12h 缓存），按权重降序前 N + 占比条 +
 *   前十大合计；整块 null 同上显「—」。月频数据滞后一期是常态，脚注标注 as_of。
 */
const props = defineProps<{
  /** 指数代码（裸 6 位码或带前缀形态，后端归一） */
  symbol: string;
}>();

const DASH = "—";

/** 收益窗口展示序（与后端 windows 键一一对应） */
const RETURN_WINDOWS = [
  { key: "1m", label: "近 1 月" },
  { key: "3m", label: "近 3 月" },
  { key: "ytd", label: "今年至今" },
  { key: "1y", label: "近 1 年" },
  { key: "2y", label: "近 2 年" },
  { key: "3y", label: "近 3 年" }
] as const;

const loading = ref(false);
const failed = ref(false);
const profile = ref<IndexProfileResult | null>(null);

/** 分位展示文本：null 是「样本不足」不是 0，必须区分 */
const percentileText = computed(() => {
  const p = profile.value?.pe_percentile;
  return p == null ? DASH : `${p.toFixed(0)}%`;
});

/** 分位语言化解读（近似三档，避免精确分档显得比数据更确定） */
const percentileHint = computed(() => {
  const p = profile.value?.pe_percentile;
  if (p == null) return "";
  if (p >= 70) return "处于近 5 年高位";
  if (p <= 30) return "处于近 5 年低位";
  return "处于近 5 年中位区间";
});

/** 阶段性收益格子（整块 null → null，前端显「—」；单窗口 null → 该格「—」） */
const returnCells = computed(() => {
  const pr = profile.value?.period_returns;
  if (!pr) return null;
  return RETURN_WINDOWS.map(w => ({
    key: w.key,
    label: w.label,
    value: pr.windows[w.key]
  }));
});

/** 波动率不是收益方向指标，不染涨跌色 */
const volatilityText = computed(() => {
  const v = profile.value?.period_returns?.volatility_1y;
  return v == null ? DASH : `${v.toFixed(2)}%`;
});

const returnsAsOf = computed(
  () => profile.value?.period_returns?.as_of ?? null
);

const topWeights = computed(() => profile.value?.top_weights ?? null);

/** 占比条归一基准：按行内最大权重拉满（与行业配置同惯例，不按合计） */
const maxWeight = computed(() => {
  const rows = topWeights.value?.rows ?? [];
  return rows.reduce((m, r) => Math.max(m, r.weight), 0);
});

/** 收益文本：正数带 + 号，null 显「—」 */
function returnText(v: number | null): string {
  if (v == null) return DASH;
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

/** 涨跌染色（A 股惯例：正=涨=红）；null 与 0 不染——0 不是「跌」 */
function returnClass(v: number | null): string {
  if (v == null || v === 0) return "";
  return v > 0 ? "index-section__ret--rise" : "index-section__ret--fall";
}

function weightBarWidth(w: number): string {
  if (maxWeight.value <= 0 || w <= 0) return "0%";
  return `${((w / maxWeight.value) * 100).toFixed(2)}%`;
}

const footnotes = computed(() => {
  const p = profile.value;
  if (!p) return [];
  const notes: string[] = [];
  if (p.pe_percentile != null) {
    let note = `分位口径：${p.percentile_metric || "滚动市盈率"}`;
    if (p.percentile_date) note += `，基线截至 ${p.percentile_date}`;
    notes.push(note);
  }
  if (p.valuation_date) {
    notes.push(`估值数据截至 ${p.valuation_date}（中证指数官方口径）`);
  }
  return notes;
});

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  profile.value = null;
  try {
    const res = await getIndexProfile(props.symbol);
    profile.value = res.data;
  } catch {
    // 未收录 / 网络异常：整块降级为空态，不影响详情页其余区块
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <CardBlock class="index-section">
    <SectionHeader title="指数资料" />

    <p v-if="loading" class="index-section__hint">正在读取指数资料…</p>

    <p v-else-if="failed || !profile" class="index-section__hint">
      暂无可展示的指数资料
    </p>

    <template v-else>
      <dl class="index-section__facts">
        <div class="index-section__fact">
          <dt class="index-section__label">指数名称</dt>
          <dd class="index-section__value index-section__value--strong">
            {{ profile.name || DASH }}
          </dd>
        </div>
        <div class="index-section__fact">
          <dt class="index-section__label">发布机构</dt>
          <dd class="index-section__value">
            {{ profile.publisher_label || DASH }}
          </dd>
        </div>
        <div class="index-section__fact">
          <dt class="index-section__label">市盈率 PE</dt>
          <dd class="index-section__value">
            <template v-if="profile.pe != null">
              {{ profile.pe.toFixed(2) }}
            </template>
            <template v-else>{{ DASH }}</template>
          </dd>
        </div>
        <div class="index-section__fact">
          <dt class="index-section__label">股息率</dt>
          <dd class="index-section__value">
            <template v-if="profile.dividend_yield != null">
              {{ profile.dividend_yield.toFixed(2) }}%
            </template>
            <template v-else>{{ DASH }}</template>
          </dd>
        </div>
        <div class="index-section__fact">
          <dt class="index-section__label">PE 历史分位</dt>
          <dd class="index-section__value index-section__value--strong">
            {{ percentileText }}
            <span v-if="percentileHint" class="index-section__sub">
              {{ percentileHint }}
            </span>
          </dd>
        </div>
        <!-- #2278 快照四字段（basic-info 同请求顺手取，官网无值显「—」） -->
        <div class="index-section__fact">
          <dt class="index-section__label">发布日期</dt>
          <dd class="index-section__value">
            {{ profile.publish_date || DASH }}
          </dd>
        </div>
        <div class="index-section__fact">
          <dt class="index-section__label">样本数</dt>
          <dd class="index-section__value">
            {{ profile.cons_number ?? DASH }}
          </dd>
        </div>
        <div class="index-section__fact">
          <dt class="index-section__label">加权方式</dt>
          <dd class="index-section__value">
            {{ profile.weighting_type || DASH }}
          </dd>
        </div>
        <div class="index-section__fact">
          <dt class="index-section__label">计价币种</dt>
          <dd class="index-section__value">
            {{ profile.currency || DASH }}
          </dd>
        </div>
      </dl>

      <!-- 指数简介（中证官网原文）：散文段落，无简介时整段隐藏而非占位 -->
      <p v-if="profile.description" class="index-section__desc">
        {{ profile.description }}
      </p>

      <!-- 样本不足的定调说明：比一排「—」更诚实（告诉用户为什么没有，而不是假装没数据） -->
      <p v-if="profile.pe_percentile == null" class="index-section__note">
        该指数暂无足够历史样本计算分位（基线需 ≥1
        年月频数据），估值绝对值仍可参考。
      </p>

      <!-- ── #2278 阶段性收益 ─────────────────────────────────────────── -->
      <p class="index-section__subhead">阶段性收益</p>
      <template v-if="returnCells">
        <dl class="index-section__returns">
          <div
            v-for="cell in returnCells"
            :key="cell.key"
            class="index-section__ret"
          >
            <dt class="index-section__ret-label">{{ cell.label }}</dt>
            <dd
              class="index-section__ret-value"
              :class="returnClass(cell.value)"
            >
              {{ returnText(cell.value) }}
            </dd>
          </div>
          <div class="index-section__ret">
            <dt class="index-section__ret-label">年化波动（近 1 年）</dt>
            <dd class="index-section__ret-value">{{ volatilityText }}</dd>
          </div>
        </dl>
        <p v-if="returnsAsOf" class="index-section__footnote">
          收益截至 {{ returnsAsOf }}（按收盘价现算）
        </p>
      </template>
      <p v-else class="index-section__hint">{{ DASH }}</p>

      <!-- ── #2278 十大权重 ───────────────────────────────────────────── -->
      <p class="index-section__subhead">
        十大权重
        <span v-if="topWeights" class="index-section__subhead-aside">
          前十大合计 {{ topWeights.top_sum.toFixed(2) }}%
        </span>
      </p>
      <template v-if="topWeights && topWeights.rows.length">
        <table class="index-section__wtable">
          <thead>
            <tr>
              <th scope="col">代码</th>
              <th scope="col">名称</th>
              <th scope="col" class="index-section__whead">权重</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in topWeights.rows" :key="row.symbol">
              <th scope="row" class="index-section__wcode">
                {{ row.symbol }}
              </th>
              <td class="index-section__wname">{{ row.name }}</td>
              <td class="index-section__wcell">
                <span
                  v-if="row.weight > 0"
                  class="index-section__wtrack"
                  aria-hidden="true"
                >
                  <span
                    class="index-section__wfill"
                    :style="{ width: weightBarWidth(row.weight) }"
                  />
                </span>
                <span class="index-section__wvalue">
                  {{ row.weight.toFixed(2) }}%
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <p class="index-section__footnote">
          权重截至 {{ topWeights.as_of }}（月频，可能滞后一期）· 全成分
          {{ topWeights.total_count }} 只
        </p>
      </template>
      <p v-else class="index-section__hint">{{ DASH }}</p>

      <p v-for="note in footnotes" :key="note" class="index-section__footnote">
        {{ note }}
      </p>
    </template>
  </CardBlock>
</template>

<style scoped lang="scss">
@use "@/style/breakpoints" as bp;

.index-section__hint {
  margin: 0;
  font-size: 13px;
  color: var(--text-tertiary-ink);
}

.index-section__facts {
  display: grid;

  /* auto-fit + 真实最小列宽：`minmax(0, 1fr)` 会让轨道塌到几像素、标签逐字竖排（#1969 P0） */
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--space-3) var(--space-6);
  margin: 0;
}

.index-section__fact {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.index-section__label {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.index-section__value {
  margin: 0;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.index-section__value--strong {
  font-size: 18px;
  font-weight: 600;
}

.index-section__sub {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-tertiary-ink);
}

.index-section__desc {
  margin: var(--space-3) 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.index-section__note {
  margin: var(--space-3) 0 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.index-section__footnote {
  margin: var(--space-2) 0 0;
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

/* ── #2278 子区块标题（卡内分组标签，非页面级 h2——SectionHeader 只给卡标题） ── */
.index-section__subhead {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  justify-content: space-between;
  margin: var(--space-5) 0 var(--space-2);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.index-section__subhead-aside {
  font-size: 12px;
  font-weight: 400;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* ── 阶段性收益格子 ─────────────────────────────────────────────────── */
.index-section__returns {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: var(--space-3) var(--space-4);
  margin: 0;
}

.index-section__ret {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.index-section__ret-label {
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.index-section__ret-value {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* 涨跌染色走文字级 ink 变量（ProductAdvisor/Manager 同惯例）；0 与 null 不染 */
.index-section__ret--rise {
  color: var(--color-rise-ink);
}

.index-section__ret--fall {
  color: var(--color-fall-ink);
}

/* ── 十大权重表（表内嵌条，与行业配置同惯例） ───────────────────────── */
.index-section__wtable {
  width: 100%;
  font-size: 13px;
  border-collapse: collapse;
}

.index-section__wtable th,
.index-section__wtable td {
  padding: var(--space-2) 0;
  text-align: left;
  border-bottom: 1px solid var(--border-light);
}

.index-section__wtable thead th {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary-ink);
}

.index-section__wtable tbody tr:last-child th,
.index-section__wtable tbody tr:last-child td {
  border-bottom: none;
}

.index-section__wcode {
  width: 80px;
  font-weight: 400;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.index-section__wname {
  color: var(--text-primary);
}

.index-section__whead {
  text-align: right;
}

.index-section__wcell {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  justify-content: flex-end;
}

.index-section__wtrack {
  display: inline-block;
  flex: none;
  width: 96px;
  height: 8px;
  overflow: hidden;
  background: var(--bg-muted);
  border-radius: 4px;
}

.index-section__wfill {
  display: block;
  min-width: 3px;
  height: 100%;
  background: var(--chart-01);
  border-radius: 4px;
}

.index-section__wvalue {
  min-width: 52px;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
  text-align: right;
}

@include bp.below("sm") {
  .index-section__wtrack {
    width: 48px;
  }
}
</style>
