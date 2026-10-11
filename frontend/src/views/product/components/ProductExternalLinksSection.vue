<script setup lang="ts">
import { computed } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { externalQuoteLinks } from "@/utils/externalLinks";

/**
 * 详情页「第三方数据」区块（#1969）。
 *
 * 定位：我们不做行情终端。资金流、五档盘口、财务报表这类深度数据交给专业站，
 * 我们专注「我在这只产品上赚了多少」。这也是对数据完整度的诚实处理——与其
 * 半吊子地抄别人，不如把用户送过去。
 *
 * 红线：
 * - 一律**新标签页**打开（`target="_blank"`）并带 `noopener noreferrer`，
 *   避免第三方页面拿到我们的 referrer / window.opener；
 * - 品类没有对应站点时整卡不渲染（`v-if="links.length"`），不留一个空标题；
 * - URL 拼接全在 `utils/externalLinks.ts`，本组件不拼字符串。
 */
const props = defineProps<{
  symbol: string;
  /** 后端判定的品类（stock / etf / bond / fund / index…） */
  assetType?: string | null;
  /** 契约市场（消歧用，形态判断主要看 symbol 前缀） */
  market?: string | null;
}>();

const links = computed(() =>
  externalQuoteLinks({
    symbol: props.symbol,
    assetType: props.assetType,
    market: props.market
  })
);
</script>

<template>
  <CardBlock v-if="links.length" class="ext-links">
    <SectionHeader
      title="第三方数据"
      info="资金流、盘口、财务等深度数据请到专业网站查看；链接在新标签页打开。"
      info-label="关于第三方数据"
    />
    <div class="ext-links__row">
      <a
        v-for="link in links"
        :key="link.key"
        class="ext-links__item"
        :href="link.url"
        target="_blank"
        rel="noopener noreferrer"
        referrerpolicy="no-referrer"
      >
        {{ link.label }}
        <IconifyIconOffline icon="ep:top-right" class="ext-links__icon" />
      </a>
    </div>
  </CardBlock>
</template>

<style scoped>
.ext-links {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.ext-links__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.ext-links__item {
  display: inline-flex;
  gap: var(--space-1);
  align-items: center;
  padding: var(--space-1) var(--space-3);
  font-size: 13px;
  color: var(--text-secondary);
  text-decoration: none;
  border: 1px solid var(--border-default);
  border-radius: 4px;
  transition:
    color 0.15s,
    border-color 0.15s;
}

.ext-links__item:hover {
  color: var(--brand-700);
  border-color: var(--brand-700);
}

.ext-links__icon {
  font-size: 12px;
}
</style>
