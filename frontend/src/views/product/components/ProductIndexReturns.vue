<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { fetchIndexReturns, type IndexReturnsResult } from "@/api/products";

/**
 * 详情页「阶段性收益」子区块（#2278）：指数的六窗口区间收益 + 近 1 年年化波动率。
 *
 * ## 取数与降级
 *
 * `GET /api/products/index-returns/`（#2278 新增）：后端按需拉全历史日线（中证官网
 * 优先 / 腾讯兜底）→ 服务端现算区间收益与年化波动 → 聚合返回，不入库 + TTL 缓存。
 * - 历史不足某窗口 → 该窗口 `null` → 显示「—」，**不编数**；
 * - 年化波动率历史不足 1 年 → `null` → 「—」；
 * - 外部源全空 / 接口失败 → `as_of` 为 null → 整块显示「暂无可展示的收益数据」，
 *   不阻塞指数卡内其余内容（详情页各区块独立降级）。
 *
 * 本组件是 ProductIndexSection 的**子区块**（同卡内渲染，不单独占导航锚点）：
 * 由父组件在指数资料就绪后挂载，避免名录外的代码白打外部接口。
 */
const props = defineProps<{
  /** 指数代码（裸 6 位码或带前缀形态，后端归一） */
  symbol: string;
}>();

const DASH = "—";

/** 窗口定义：key 与后端 IndexReturnsWindows 对齐（顺序即展示顺序） */
const WINDOWS = [
  { key: "m1", label: "近1月" },
  { key: "m3", label: "近3月" },
  { key: "ytd", label: "今年至今" },
  { key: "y1", label: "近1年" },
  { key: "y2", label: "近2年" },
  { key: "y3", label: "近3年" }
] as const;

/** 数据来源 → 用户可读标签（source 为 null 时不出现） */
const SOURCE_LABELS: Record<string, string> = {
  csindex: "中证指数官网",
  tencent: "腾讯行情"
};

const loading = ref(false);
const failed = ref(false);
const data = ref<IndexReturnsResult | null>(null);

/** 非空收窄：as_of 存在才认为「有行情数据」 */
const loaded = computed(() => {
  const d = data.value;
  return d != null && d.as_of != null;
});

const cells = computed(() => {
  const d = data.value;
  if (!d || !d.as_of) return [];
  return WINDOWS.map(w => ({
    key: w.key,
    label: w.label,
    value: d.returns[w.key]
  }));
});

const volatility = computed(() => {
  const d = data.value;
  return d && d.as_of ? d.volatility_y1 : null;
});

const footnote = computed(() => {
  const d = data.value;
  if (!d || !d.as_of) return "";
  const source = d.source ? (SOURCE_LABELS[d.source] ?? d.source) : "";
  return source
    ? `行情截至 ${d.as_of} · 来源：${source}`
    : `行情截至 ${d.as_of}`;
});

/** 收益率文本：null → 「—」；正负带符号区分涨跌色（红涨绿跌） */
function valueText(value: number | null): string {
  return value == null ? DASH : `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function valueClass(value: number | null): Record<string, boolean> {
  return {
    "idx-returns__value--rise": value != null && value > 0,
    "idx-returns__value--fall": value != null && value < 0
  };
}

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  data.value = null;
  try {
    const res = await fetchIndexReturns(props.symbol);
    data.value = res.data;
  } catch {
    // 接口失败：整块降级，不阻塞指数卡内其余内容（详情页各区块独立降级）
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <section class="idx-returns">
    <h3 class="idx-returns__title">阶段性收益</h3>

    <p v-if="loading" class="idx-returns__hint">正在计算阶段性收益…</p>

    <p v-else-if="failed || !loaded" class="idx-returns__hint">
      暂无可展示的收益数据
    </p>

    <template v-else>
      <dl class="facts-grid">
        <div v-for="cell in cells" :key="cell.key" class="idx-returns__cell">
          <dt class="facts-grid__label">{{ cell.label }}</dt>
          <dd class="facts-grid__value" :class="valueClass(cell.value)">
            {{ valueText(cell.value) }}
          </dd>
        </div>
        <div class="idx-returns__cell">
          <dt class="facts-grid__label">年化波动率（近1年）</dt>
          <dd class="facts-grid__value">{{ valueText(volatility) }}</dd>
        </div>
      </dl>

      <p class="section-footnote section-footnote--spaced">{{ footnote }}</p>
    </template>
  </section>
</template>

<style scoped>
.idx-returns {
  margin-top: var(--space-4);
}

.idx-returns__title {
  margin: 0 0 var(--space-3);
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--text-primary);
}

.idx-returns__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.idx-returns__cell {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.idx-returns__value--rise {
  /* #2314：文字色统一 -ink 文字级令牌（图形级 --color-rise 禁作前景文字，design.md:131） */
  color: var(--color-rise-ink);
}

.idx-returns__value--fall {
  color: var(--color-fall-ink);
}

/* 脚注已迁至共享类 .section-footnote--spaced（#2320） */
</style>
