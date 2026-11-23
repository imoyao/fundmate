<template>
  <button
    type="button"
    class="fund-link"
    :title="row.fund_name ? row.fund_code : undefined"
    @click="emit('open', row.fund_code)"
  >
    <!-- 名称独占一行：列宽只有 232px，名称后面再挂一枚徽章会把长名称挤到
         换行 / 截断，而且徽章贴着名称末字读起来像名称的一部分（「…发起C 持仓」）。
         类型标记下移到代码行，和「这只基金是谁」的两条元信息排在一起。 -->
    <span class="fund-link__name">{{ row.fund_name || row.fund_code }}</span>
    <span class="fund-link__meta">
      <!-- 名称与代码都显示：跳详情、复核数据都要代码；
                           funds 资料缺失时名称回退代码，此时不重复显示两遍 -->
      <span v-if="row.fund_name" class="fund-link__code">{{
        row.fund_code
      }}</span>
      <!-- 持仓体检定位的锚点：榜上哪只是「我的」 -->
      <span v-if="row.in_holdings" class="fund-tag fund-tag--holding"
        >持仓</span
      >
      <span v-else-if="row.in_watchlist" class="fund-tag fund-tag--watch"
        >自选</span
      >
    </span>
  </button>
</template>

<script setup lang="ts">
// 榜单「基金」单元格（#980 拆分自 index.vue）：名称主显示、代码次要小字、
// 持仓 / 自选徽章。整块可点击跳详情；名称缺失时回退代码且不重复显示两遍。
//
// 只有 props + 一个 emit，不知道榜单、排序、口径——换榜单形态时可单独复用。
import type { FundRiskRankingRow } from "@/api/products";

defineProps<{
  row: FundRiskRankingRow;
}>();
const emit = defineEmits<{
  /** 点整块 → 父层跳详情 */
  open: [code: string];
}>();
</script>

<style scoped lang="scss">
/* 基金列：名称主显示、代码次要小字（只显 6 位代码用户认不出产品，2026-10-17）。
   整块可点击跳详情；名称缺失时回退代码，此时不重复显示。
   ⚠️ 必须是 lang="scss"：本块用了 `&__x` / `&--x` 这类拼接式嵌套，原生 CSS 嵌套
   只允许 `&` 后接组合符或伪类，`&__name` 是非法选择器 ⇒ 浏览器**整条嵌套规则丢弃**。
   这块此前正是普通 `<style scoped>`：名称因此没拿到 13px / 省略号，徽章没拿到配色
   （「持仓」渲染成一段灰字，和基金名连成一句话），hover 下划线也没生效。 */
.fund-link {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: flex-start;
  max-width: 100%;
  overflow: hidden;
  text-align: left;
  cursor: pointer;
  background: none;
  border: none;

  &:hover .fund-link__name {
    color: var(--brand-700);
    text-decoration: underline;
  }

  /* 名称独占一行并自行截断：列宽 232px，长名称（13~15 字）本来就贴边，
     再和徽章共享一行会把徽章挤到换行或截掉半个字（旧实现实测「…发起A 持」）。 */
  &__name {
    display: block;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--text-label);
    color: var(--text-primary);
    white-space: nowrap;
  }

  /* 元信息行：代码 + 类型标记。两者都是「这只基金是谁」的附属信息，
     同一行同一基调；间距 6px 让胶囊与代码分得开，不再读成名称的一部分。 */
  &__meta {
    display: flex;
    gap: 6px;
    align-items: center;
    max-width: 100%;
    overflow: hidden;
  }

  &__code {
    font-size: var(--text-label);
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary-ink);
  }
}

/* 持仓 / 自选徽章：几何与 ValuationSourceBadge 一致（16px 高、胶囊、600 字重），
   不用涨跌色——标记的是「这是你的」，不是盈亏语义。
   持仓走 design.md「Badge 品牌档」（--brand-200 底）：旧实现用 --brand-100 底，
   白卡片上几乎看不出底色，徽章与基金名连成一句话（用户实测反馈）。 */
.fund-tag {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  height: 16px;
  padding: 0 6px;
  font-size: var(--text-label);
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
  border-radius: var(--radius-pill);

  &--holding {
    color: var(--brand-ink);
    background: var(--brand-200);
  }

  &--watch {
    color: var(--text-secondary);
    background: var(--bg-soft);
  }
}
</style>
