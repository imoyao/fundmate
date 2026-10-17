<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getIndexProfile, type IndexProfileResult } from "@/api/products";
import ProductIndexReturns from "./ProductIndexReturns.vue";
import ProductIndexWeights from "./ProductIndexWeights.vue";

/**
 * 详情页「指数资料与估值」区块（#2028 · 设计 §6 品类矩阵二期）。
 *
 * ## 取数
 *
 * `GET /api/products/index-profile/`（本卡新增）一次返回：名录资料（名称 / 发布机构）
 * + 中证官方估值（PE / 股息率，最新一期）+ PE 历史分位（乐咕月频近 5 年窗口现算，
 * 口径见 #1407 拍板）。此前指数三张表（`index_catalog` / `index_valuations` /
 * `index_valuation_baselines`）**都没有 API 出口**，详情页只有 3 个数字的薄页。
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
 * #2278 扩展：同一份 index-basic-info 顺带取快照字段（发布日期 / 样本数 / 加权方式 /
 * 币种）并入上方事实格，逐字段降级「—」；卡内追加两个子区块——阶段性收益
 * （ProductIndexReturns）与十大权重（ProductIndexWeights），各自取数、独立降级，
 * 仅在名录资料就绪后挂载（避免名录外代码白打外部接口）。
 */
const props = defineProps<{
  /** 指数代码（裸 6 位码或带前缀形态，后端归一） */
  symbol: string;
}>();

const DASH = "—";

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
        <!-- 快照字段（#2278，来自中证官网 index-basic-info 同一请求）：逐字段降级「—」 -->
        <div class="index-section__fact">
          <dt class="index-section__label">发布日期</dt>
          <dd class="index-section__value">
            {{ profile.publish_date || DASH }}
          </dd>
        </div>
        <div class="index-section__fact">
          <dt class="index-section__label">样本数</dt>
          <dd class="index-section__value">
            {{ profile.cons_number != null ? profile.cons_number : DASH }}
          </dd>
        </div>
        <div class="index-section__fact">
          <dt class="index-section__label">加权方式</dt>
          <dd class="index-section__value">
            {{ profile.weighting_type || DASH }}
          </dd>
        </div>
        <div class="index-section__fact">
          <dt class="index-section__label">币种</dt>
          <dd class="index-section__value">
            {{ profile.currency || DASH }}
          </dd>
        </div>
      </dl>

      <!-- 指数简介（中证官网原文）：散文段落，无简介时整段隐藏而非占位 -->
      <p v-if="profile.description" class="index-section__desc">
        {{ profile.description }}
      </p>

      <!-- 阶段性收益 + 十大权重（#2278）：子组件各自取数、独立降级，
           仅在名录资料就绪后挂载，避免名录外的代码白打外部接口 -->
      <ProductIndexReturns v-if="profile" :symbol="symbol" />
      <ProductIndexWeights v-if="profile" :symbol="symbol" />

      <!-- 样本不足的定调说明：比一排「—」更诚实（告诉用户为什么没有，而不是假装没数据） -->
      <p v-if="profile.pe_percentile == null" class="index-section__note">
        该指数暂无足够历史样本计算分位（基线需 ≥1
        年月频数据），估值绝对值仍可参考。
      </p>

      <p v-for="note in footnotes" :key="note" class="index-section__footnote">
        {{ note }}
      </p>
    </template>
  </CardBlock>
</template>

<style scoped>
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
</style>
