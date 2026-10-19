<!--
  ProductIdentityCard · 详情页识别卡（#1964 · 设计 §4）

  只放事实项（代码 / 市场 / 场所 / 自选 / 持仓）。**名称与品类不在这里**——
  它们由 PageHeaderBar 页头承担（标题=产品名、副标题=品类）；卡内再排一次
  h2 名称 + 类型徽章是纯重复（用户实测「同一名称出现 4 次」，#2107 起删掉）。

  未登录时 in_watchlist / has_position 为 null（resolve 是「可选登录」端点），
  此时不渲染徽标——「未知」不是「没有」，不能显示成「未自选」。

  **「代码」项按品类隐藏**（#2216 / #2228 · 设计 §2.6）：组合 / 经理类的 `symbol` 是
  内部编码（`MGR_98CE0328FFF1`、投顾组合的平台原生码），对使用者没有任何意义 ——
  这两类靠「名称 + 品类 + 平台 / 主理人」识别。判定收口在
  `productIdentityFacts.showsCodeItem`（含单测）：设计早就这么写了，是这里漏了落地
  （原先是**无条件**渲染）。

  为什么独立成组件：#1968 页内导航接线后 detail.vue 越过 400 行门禁线
  （scripts/check_vue_size.mjs），识别卡是纯展示、无取数，是最直接的拆出单元。
-->
<script setup lang="ts">
import { onMounted } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import { useEnumLabels } from "@/composables/useEnumLabels";
import type { ProductResolveResult } from "@/api/products";
import { showsCodeItem } from "./productIdentityFacts";

defineProps<{
  product: ProductResolveResult;
}>();

// 市场 / 场所的中文标签来自后端 /api/utils/enums（**无前端镜像**，不像 asset_type
// 那样有同步回退），必须等拉取完成；marketLabel/venueLabel 读 enums ref，
// 拉到的瞬间模板自动重渲染。fetch 走模块级缓存，与宿主页的 ensure 是同一次请求。
const { ensure: ensureEnums, marketLabel, venueLabel } = useEnumLabels();

onMounted(() => {
  void ensureEnums();
});
</script>

<template>
  <CardBlock class="product-detail__hero">
    <dl class="product-detail__facts">
      <!-- 代码项按品类隐藏（#2216 / #2228 · 设计 §2.6）：组合 / 经理类的 symbol 是
           **内部编码**（`MGR_98CE0328FFF1` 经 resolve 大写化、投顾组合的平台原生码），
           对使用者没有任何意义 —— 这两类靠「名称 + 品类 + 平台 / 主理人」识别
           （经理靠「姓名 + 任职基金」）。其余品类照常展示。判定收口在
           `productIdentityFacts.showsCodeItem`（含单测）。 -->
      <div
        v-if="showsCodeItem(product.asset_type)"
        class="product-detail__fact"
      >
        <dt class="product-detail__fact-label">代码</dt>
        <dd class="product-detail__fact-value product-detail__symbol">
          {{ product.symbol }}
        </dd>
      </div>
      <!-- 市场 / 场所走 /enums 中文标签：#1969 前此处把 CN_A / SH / EXCHANGE
           这些内部词表原键直接排版给用户看，等于让用户去猜我们的枚举 -->
      <div v-if="product.market" class="product-detail__fact">
        <dt class="product-detail__fact-label">市场</dt>
        <dd class="product-detail__fact-value">
          {{ marketLabel(product.market) }}
        </dd>
      </div>
      <div v-if="product.venue" class="product-detail__fact">
        <dt class="product-detail__fact-label">场所</dt>
        <dd class="product-detail__fact-value">
          {{ venueLabel(product.venue) }}
        </dd>
      </div>
      <!-- 未登录时这两项为 null（端点为可选登录），此时不渲染徽标，
           不能当成「未自选 / 未持有」——那是「未知」不是「没有」 -->
      <div v-if="product.in_watchlist === true" class="product-detail__fact">
        <dt class="product-detail__fact-label">自选</dt>
        <dd class="product-detail__fact-value">已关注</dd>
      </div>
      <div v-if="product.has_position === true" class="product-detail__fact">
        <dt class="product-detail__fact-label">持仓</dt>
        <dd class="product-detail__fact-value">已持有</dd>
      </div>
    </dl>
  </CardBlock>
</template>

<style scoped>
/* 识别卡只有 facts 一行，无卡内标题（标题由页头承担，见组件头注释） */
.product-detail__hero {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
}

.product-detail__facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  margin: 0;
}

.product-detail__fact-label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.product-detail__fact-value {
  margin: 4px 0 0;
  font-size: var(--text-small);
  color: var(--text-primary);
}

/* 代码原样展示：不做缩写 / 不补前缀 / 不剥市场前缀 */
.product-detail__symbol {
  font-family: var(--font-mono, monospace);
}
</style>
