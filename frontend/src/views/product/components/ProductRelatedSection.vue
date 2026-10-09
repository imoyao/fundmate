<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import {
  getRelatedSymbols,
  type RelatedSymbolLink,
  type RelatedSymbolsResult
} from "@/api/products";
import { productRoute } from "@/utils/productIdentity";

/**
 * 详情页「关联标的」区块（#1976 · 设计 §6 / 数据策略 L4 关联关系类）。
 *
 * 展示同一底层资产的跨渠道同义标的：指数 ↔ 场内 ETF ↔ 场外联接基金。
 * 关系表 `channel_links` 存**有向**关系，本区块拿到的已按裸代码双向展开——
 * 站在指数侧看到 ETF，站在 ETF 侧看到指数 + 联接，**称呼随角色变化**
 * （「同标的 ETF」/「跟踪指数」/「场外联接」），前端不自行推断方向。
 *
 * 降级（数据策略：按需取 + 可降级）：
 * - 无关联 → 渲染 `—`，**不用「0 个」**（与全表「无数据一律 —」一致）；
 * - 关系靠名称匹配建立，落库口径覆盖率约 66.4%（跨境 / 商品 ETF 的跟踪标的
 *   不在 `index_catalog` 内，缺口见 #1419），故「没有关联」不等于「没有对应标的」，
 *   故给一句定调说明，避免用户误判为数据缺失。
 *
 * 跳转：关联标的的品类由其代码前缀决定不了（关系表存裸代码），故按关系类型推断
 * —— `index_etf` 的另一端可能是指数也可能是 ETF，`etf_feeder` 的另一端是场外联接基金。
 * 这里统一跳 **基金 / ETF 详情页**（`/fund/`），指数详情属二期（#1974）。
 */
const props = defineProps<{
  /** 标准化 symbol（`SH510300`）或裸代码均可——后端按裸代码匹配 */
  symbol: string;
}>();

const loading = ref(false);
const related = ref<RelatedSymbolsResult | null>(null);
const failed = ref(false);

const DASH = "—";

/** 按 label 分组，保持后端给定的顺序（groups 已去重） */
const grouped = computed(() => {
  const data = related.value;
  if (!data?.links.length) return [];
  return data.groups
    .map(label => ({
      label,
      items: data.links.filter((x: RelatedSymbolLink) => x.label === label)
    }))
    .filter(g => g.items.length > 0);
});

/** 关联标的的跳转路径：`etf_feeder` 那端是场外联接基金，其余按场内基金处理 */
function linkTo(item: RelatedSymbolLink) {
  return productRoute({ assetType: "fund", symbol: item.code });
}

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  try {
    const res = await getRelatedSymbols({ symbol: props.symbol });
    related.value = res.data;
  } catch {
    // 关联关系是补充信息，取不到不该让详情页不可用
    related.value = null;
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <CardBlock class="rel-section">
    <SectionHeader title="关联标的" />

    <p v-if="loading" class="rel-section__hint">正在读取关联标的…</p>

    <p v-else-if="failed" class="rel-section__hint">
      {{ DASH }}
    </p>

    <p v-else-if="!related?.links.length" class="rel-section__hint">
      {{ DASH }}
      <span class="rel-section__hint-note">
        （关联关系按名称匹配建立，跨境与商品类标的可能尚未覆盖）
      </span>
    </p>

    <div v-else class="rel-section__groups">
      <div v-for="g in grouped" :key="g.label" class="rel-section__group">
        <h4 class="rel-section__subtitle">{{ g.label }}</h4>
        <ul class="rel-section__list">
          <li v-for="item in g.items" :key="`${item.link_type}-${item.code}`">
            <RouterLink class="rel-section__link" :to="linkTo(item)">
              {{ item.name || item.code }}
            </RouterLink>
          </li>
        </ul>
      </div>
    </div>
  </CardBlock>
</template>

<style lang="scss" scoped>
.rel-section {
  &__hint {
    margin: 0;
    font-size: 13px;
    color: var(--text-tertiary);
  }

  /* 覆盖率说明跟在「—」后面，避免单独一行像报错 */
  &__hint-note {
    margin-left: 4px;
    font-size: 12px;
    color: var(--text-tertiary-ink);
  }

  &__groups {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  &__subtitle {
    margin: 0 0 var(--space-2);
    font-size: 13px;
    color: var(--text-secondary);
  }

  &__list {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    padding: 0;
    margin: 0;
    list-style: none;
  }

  &__link {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    font-size: 13px;
    color: var(--text-primary);
    text-decoration: none;
    background: var(--bg-muted);
    border-radius: var(--radius-sm);
    transition: background-color 0.2s ease;

    &:hover,
    &:focus-visible {
      background: var(--bg-hover);
    }

    /* 键盘焦点必须可见（#1838 可访问性） */
    &:focus-visible {
      outline: 2px solid var(--brand-700);
      outline-offset: 2px;
    }
  }
}
</style>
