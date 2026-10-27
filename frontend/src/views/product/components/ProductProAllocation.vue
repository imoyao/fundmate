<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { fetchProAllocation } from "@/api/products";
import ProductProEntitlementNotice from "./ProductProEntitlementNotice.vue";
import {
  classifyProPanelFailure,
  type ProPanelFailure
} from "./proEntitlement";
import AllocEmpty from "./proAlloc/AllocEmpty.vue";
import AllocLegend from "./proAlloc/AllocLegend.vue";
import AllocRow from "./proAlloc/AllocRow.vue";
import {
  buildFootnote,
  buildSkippedNote,
  buildSummary,
  type AllocData
} from "./proAlloc/allocModel";

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
 * - **档位 = 颜色**：映射只在 CSS 四处出现一次，TS 的 `tone()` 只选
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
 *
 * ## 结构（#980 拆分）
 *
 * - `proAlloc/allocModel.ts` —— 档位阈值 / 条形宽度 / 四段文案（纯函数）
 * - `proAlloc/AllocLegend.vue` —— 档位图例
 * - `proAlloc/AllocRow.vue` —— 单行（名称 + ρ + 发散轨道 + 编码）
 * - `proAlloc/AllocEmpty.vue` —— 无 peer 时的引导（不是错误态）
 */
const props = defineProps<{
  /** 产品代码（与状态位同源） */
  symbol: string;
  /** 入口提示品类（透传，决定序列口径） */
  assetType?: string | null;
}>();

const loading = ref(false);
/** 失败态三选一（`none` / `entitlement` / `error`），判据见 `proEntitlement.ts` */
const failure = ref<ProPanelFailure>("none");
const data = ref<AllocData | null>(null);

const peers = computed(() => data.value?.peers ?? []);
const highCount = computed(() => data.value?.high_correlation_count ?? 0);

/** 高度相关的总结句：这条才是本模块真正要让 user 看见的话 */
const summary = computed(() =>
  buildSummary(peers.value.length, highCount.value)
);

/** 跳过的持仓说明（诚实披露，不静默丢弃） */
const skippedNote = computed(() => buildSkippedNote(data.value));

const footnote = computed(() => buildFootnote(data.value));

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

      <AllocLegend />

      <ul class="pro-alloc__list">
        <AllocRow v-for="peer in peers" :key="peer.symbol" :peer="peer" />
      </ul>

      <p v-if="skippedNote" class="pro-alloc__skipped">{{ skippedNote }}</p>
      <p v-if="footnote" class="pro-alloc__footnote">{{ footnote }}</p>
    </template>

    <!-- 无 peer 时的引导（不是错误态）：把「为什么没内容」讲清楚 -->
    <AllocEmpty v-else :reason="data?.reason" />
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

.pro-alloc__skipped,
.pro-alloc__footnote {
  margin: 0;
  font-size: var(--text-label);
  line-height: 1.6;
  color: var(--text-tertiary-ink);
}
</style>
