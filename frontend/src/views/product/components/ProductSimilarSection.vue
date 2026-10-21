<!-- frontend/src/views/product/components/ProductSimilarSection.vue -->
<!--
  详情页「相似基金」区块（#2480 · 韭圈儿 simfund，免登录）。

  数据契约（后端 services/similar_fund_service.py，契约留档
  docs/working-notes/similar-funds-api-contract-2026-10-21.md）：
  · 按需取 + 后端 6h 缓存，**不落库**（相似度是快照概念）；
  · 降级三态必须分开渲染——「上游暂时取不到」（degraded）与「上游确实没有
    相似基金」（items 空）对用户是两回事，混为一谈会把故障说成无数据；
  · similarity=null = 上游未打分（只给前若干名打分），渲染「—」，**不补 0**；
  · 相似度口径是上游黑盒，区块脚注注明「数据来源：韭圈儿」。

  配色：涨跌一律走语义 token（design.md 红线，禁硬编码）；涨=红跌=绿。
-->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getSimilarFunds, type SimilarFundsResult } from "@/api/funds";
import { productRoute } from "@/utils/productIdentity";
import {
  DASH,
  similarityText,
  similarityTitle,
  incomeText,
  incomeClass
} from "./similarSectionMetrics";

const props = defineProps<{
  /** 标准化 symbol（如 SH000001）或裸码均可——后端按裸码匹配 */
  symbol: string;
}>();

const router = useRouter();
const loading = ref(false);
const data = ref<SimilarFundsResult | null>(null);
/** 网络异常（非 degraded）：后端不 500，这里只可能是真的请求失败 */
const failed = ref(false);

/** 区块脚注：口径黑盒 + 来源注明（契约要求展示层标注） */
const INFO_TEXT =
  "按上游相似度模型给出参照名单（0-100 分，仅前列打分）；口径为上游算法，仅供参考。数据来源：韭圈儿";

const items = computed(() => data.value?.items ?? []);

/** 跳转相似基金详情（裸码即可，productRoute 不拼市场前缀） */
function goFund(code: string) {
  const route = productRoute({ assetType: "fund", symbol: code });
  if (route) router.push(route);
}

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  failed.value = false;
  try {
    const res = await getSimilarFunds(props.symbol);
    data.value = res.data;
  } catch {
    // 请求层失败（网络等）：后端 degraded 契约覆盖不了的情况，
    // 同样按「暂时取不到」降级，不让详情页不可用
    data.value = null;
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(() => props.symbol, load, { immediate: true });
</script>

<template>
  <CardBlock class="similar-funds">
    <SectionHeader title="相似基金" :info="INFO_TEXT" />

    <p v-if="loading" class="similar-funds__hint">正在读取相似基金…</p>

    <!-- 降级态：上游暂时取不到（请求失败或后端 degraded）——与「无相似基金」分开 -->
    <p v-else-if="failed || data?.degraded" class="similar-funds__hint">
      相似基金暂时取不到，请稍后重试
    </p>

    <!-- 上游确实没有相似基金（合法空态）：给「—」+ 一句定调，不显示空表格 -->
    <p v-else-if="!items.length" class="similar-funds__hint">
      {{ DASH }}
      <span class="similar-funds__hint-note">（上游暂无该基金的相似名单）</span>
    </p>

    <ul v-else class="similar-funds__list">
      <li
        v-for="item in items"
        :key="item.fund_code"
        class="similar-funds__row"
        tabindex="0"
        role="link"
        :aria-label="`查看 ${item.fund_name || item.fund_code} 详情`"
        @click="goFund(item.fund_code)"
        @keydown.enter="goFund(item.fund_code)"
      >
        <span class="similar-funds__name" :title="item.fund_name">
          {{ item.fund_name || item.fund_code }}
        </span>
        <span class="similar-funds__code">{{ item.fund_code }}</span>
        <span
          class="similar-funds__similarity"
          :title="similarityTitle(item.similarity)"
        >
          相似度 {{ similarityText(item.similarity) }}
        </span>
        <span
          class="similar-funds__income"
          :class="`similar-funds__income--${incomeClass(item.income_1y_pct)}`"
        >
          {{ incomeText(item.income_1y_pct) }}
          <template v-if="item.window">
            <span class="similar-funds__window">{{ item.window }}</span>
          </template>
        </span>
      </li>
    </ul>
  </CardBlock>
</template>

<style lang="scss" scoped>
.similar-funds {
  &__hint {
    display: flex;
    align-items: baseline;
    margin: 0;
    font-size: var(--text-label);
    color: var(--text-tertiary);
  }

  /* 定调说明跟在「—」后面，避免单独一行像报错 */
  &__hint-note {
    margin-left: 4px;
    font-size: var(--text-label);
    color: var(--text-tertiary-ink);
  }

  &__list {
    display: flex;
    flex-direction: column;
    padding: 0;
    margin: 0;
    list-style: none;
  }

  /* 一行一只：名称 + 代码 + 相似度 + 近1年收益；点击进详情 */
  &__row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto auto;
    gap: var(--space-3);
    align-items: center;
    padding: var(--space-2) var(--space-1);
    cursor: pointer;
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

    /* 行间发丝线：最后一行不要，避免与卡片边框重影 */
    & + & {
      border-top: 1px solid var(--border-light);
    }
  }

  &__name {
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--text-label);
    color: var(--text-primary);
    white-space: nowrap;
  }

  &__code {
    font-size: var(--text-label);
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary);
  }

  &__similarity {
    font-size: var(--text-label);
    font-variant-numeric: tabular-nums;
    color: var(--text-secondary);
  }

  &__income {
    display: inline-flex;
    gap: 4px;
    align-items: baseline;
    justify-content: flex-end;
    min-width: 88px;
    font-size: var(--text-label);
    font-variant-numeric: tabular-nums;

    /* 涨红跌绿（站点语义 token，禁硬编码） */
    &--rise {
      color: var(--color-rise);
    }

    &--fall {
      color: var(--color-fall);
    }

    &--flat {
      color: var(--text-secondary);
    }
  }

  /* 上游收益口径标签（如「近1年」）：与同行小字同号，不抢焦点 */
  &__window {
    font-size: var(--text-label);
    color: var(--text-tertiary);
  }
}
</style>
