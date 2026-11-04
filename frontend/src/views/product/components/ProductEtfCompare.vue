<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  fetchIndexEtfCompare,
  type IndexEtfCompareResult
} from "@/api/products";
import {
  DASH,
  footnoteOf,
  indexBaselineOf,
  recommendRowsOf
} from "./etfCompare/etfCompareModel";
import EtfComparePicks from "./etfCompare/EtfComparePicks.vue";
import EtfCompareTable from "./etfCompare/EtfCompareTable.vue";

/**
 * 详情页「关联 ETF 对比表」子区块（#2275 · P0）：同指数场内 ETF 的购买决策横向比较。
 *
 * ## 为什么是表
 *
 * 同跟踪一只指数的 ETF 收益几乎同质，**费率差即净收益差、规模决定冲击成本**；
 * 用户此前只能逐只跳第三方比较（#2275 背景）。P0 给：最新净值 / 当日涨幅 /
 * 成交额 / 近 1·3·6·12 月涨跌幅 / 跟踪差；#2333 补上规模与运行费率两列
 * （东财 F10 + 同花顺双源 + 小表缓存，后端 etf_scale_fee 服务）。
 *
 * #2334（形态 B）：对比表**上方**加「优选 ETF」小卡区块——后端按跟踪差降序、
 * 门槛内取前三算好 `recommend_rank`（1/2/3），前端最多展示 3 只、第 1 名品牌色
 * 突出；`recommend_rank` 全为 null 时**整块不渲染**（不是空壳标题）。
 *
 * ## 口径与降级
 *
 * - ETF 清单来自本地 `channel_links`（名称匹配建链，覆盖率约 66.4%，#1419）——
 *   对比表**继承该边界**，列不全是数据源边界而非缺陷；无关联 → 整块不渲染
 *   （父组件按 `peer_role === "etf"` 决定挂载）；
 * - 净值止于 T-1（与 `fund_nav_job` 同纪律）；当日涨幅/成交额为新浪现货快照
 *   （东财 spot 实测 push2delay 不可靠，2026-10-17 三连挂）；
 * - **跟踪差 = ETF 近 1 年涨幅 − 指数近 1 年涨幅**：ETF 用场内价格（含折溢价
 *   噪声），是购买决策的粗粒度贴合度参考，**非严格跟踪误差**（title 标注）；
 * - 优选小卡的跟踪差与表内同源同口径，缺失显「—」；
 * - 任一字段失败 → 「—」，不阻塞整表。
 *
 * 本组件是 ProductRelatedSection 的**子区块**（同卡内渲染）。
 *
 * #980 拆分：格式化与降级判定在 `etfCompare/etfCompareModel.ts`（纯函数），
 * 横滚渐隐在 `etfCompare/useScrollFade.ts`，优选小卡与对比表各成一个组件；
 * 本文件只留取数、三态（加载 / 失败 / 有数据）与两段脚注。
 */
const props = defineProps<{
  /** 指数代码（裸 6 位码或带前缀形态，后端归一） */
  symbol: string;
}>();

const loading = ref(false);
const failed = ref(false);
const data = ref<IndexEtfCompareResult | null>(null);

const rows = computed(() => data.value?.rows ?? []);

/** 有任何一行存在即渲染（哪怕行情字段全降级，表壳 + 名称/跳转仍有价值） */
const hasRows = computed(() => rows.value.length > 0);

// ── 优选小卡（#2334 形态 B）────────────────────────────────────────
// 后端按「跟踪差降序、门槛内 Top3」算好 recommend_rank（1/2/3）；null = 不参评。
const recommendRows = computed(() => recommendRowsOf(rows.value));

/** 渲染门禁（失败态铁律）：至少一行参评才画整块；全 null 时整块消失、不留空壳标题 */
const hasRecommend = computed(() => recommendRows.value.length > 0);

/** 指数基准行：任一窗口有值才渲染（全 null 时画一行「—」没有信息量） */
const indexBaseline = computed(() => indexBaselineOf(data.value));

const footnote = computed(() => footnoteOf(data.value));

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  data.value = null;
  try {
    const res = await fetchIndexEtfCompare(props.symbol);
    data.value = res.data;
  } catch {
    // 对比表是补充信息，接口失败不阻塞关联标的区块其余内容
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <section class="etf-cmp">
    <h3 class="etf-cmp__title">关联 ETF 对比</h3>

    <p v-if="loading" class="etf-cmp__hint">正在读取关联 ETF 行情…</p>

    <!-- 接口失败 / 无关联 ETF：整块静默收敛（父层同样按 peer_role 门控挂载） -->
    <p v-else-if="failed || !hasRows" class="etf-cmp__hint">
      {{ DASH }}
    </p>

    <template v-else>
      <EtfComparePicks v-if="hasRecommend" :picks="recommendRows" />

      <EtfCompareTable
        :rows="rows"
        :baseline="indexBaseline"
        :index-code="data?.index_code ?? ''"
      />

      <p v-if="footnote" class="section-footnote section-footnote--spaced">
        {{ footnote }}
      </p>
      <p class="section-footnote section-footnote--attached">
        对比表按成交额排序；跟踪差含折溢价噪声、非严格跟踪误差；规模与费率为
        按需抓取的第三方公开数据，缺失时显示「—」。
      </p>
    </template>
  </section>
</template>

<style scoped>
.etf-cmp {
  margin-top: var(--space-4);
}

.etf-cmp__title {
  margin: 0 0 var(--space-3);
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.etf-cmp__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 脚注族已迁至共享类 .section-footnote（#2320）：来源是**分隔型**（--spaced，
   与上方表格拉开），口径说明是**续接型**（--attached，紧随来源、属同一组信息）。 */
</style>
