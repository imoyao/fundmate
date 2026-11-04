<!--
  PortfolioCard · 组合列表卡片（2026-10-30 重设计，源用户反馈）

  用户原话：「这个卡片重新设计一下，现在都挤到一块了，而且主次不分，只写数字用户
  怎么知道你的数字是什么含义呢？主数字为什么是黑色？」

  三条问题的落点（依据 frontend/design.md 与 docs/design/components.md）：

  1. 「只写数字，不知道含义」→ 每个数字补 label（13px / 500 / --text-secondary），
     结构照 MetricCard 的「标题 → 大数字」范式（components.md §MetricCard）：
     主指标「持仓市值」label 在上、数字在下；次指标「累计盈亏」label 左、值右。
  2. 「主次不分」→ 三级字阶拉开：主数字 24px/600 > 盈亏 16px/600（语义色）>
     元信息 13px/400（--text-tertiary-ink）；组合名 16px/600 只作卡片标题，不抢
     主数字。分组间距 16px、卡片内边距 24px（--space-standard），不再 8/4/12 混排。
  3. 「主数字为什么是黑色」→ 按设计规范**保持 `--text-primary`**，理由见
     「主数字为什么不用品牌色」：品牌暖红在本站同时是「涨色」（design.md 设计原则 4
     「品牌色 = 涨色 = 暖红」），拿它当金额主色，用户会读成「这个组合在涨」。
     数字的权重由字号 / 字重 / 留白承担，颜色只留给涨跌语义——卡片里唯一的
     彩色是盈亏，这恰好反过来让主数字更「主」。

  数据口径（后端 list_portfolio_cards，PR #2760）：
  market_value 含账户级现金；pnl_rate 在成本为 0 时为 null（「不知道」≠「没赚没亏」）；
  target_progress 未设目标金额时为 null（整块不渲染，不显示 0%）。
-->
<template>
  <article class="portfolio-card" @click="emit('open', item.id)">
    <!-- 卡头：组合名 + 目的徽章；删除按钮 hover / 键盘聚焦才显现（常驻红钮会抢主数字） -->
    <header class="portfolio-card__head">
      <h3 class="portfolio-card__name" :title="item.name">{{ item.name }}</h3>
      <span class="portfolio-card__purpose">{{
        item.purpose || "未设定目的"
      }}</span>
      <el-popconfirm
        title="确定删除此组合？关联账户将自动解绑。"
        confirm-button-text="删除"
        cancel-button-text="取消"
        popper-class="danger-popconfirm"
        @confirm="emit('delete', item.id)"
        @click.stop
      >
        <template #reference>
          <el-button
            text
            size="small"
            class="portfolio-card__delete"
            aria-label="删除此组合"
            @click.stop
          >
            <IconifyIconOffline icon="ep:delete" />
          </el-button>
        </template>
      </el-popconfirm>
    </header>

    <!-- 主指标：持仓市值（label 在上，数字独占一行承载视觉重量） -->
    <div class="portfolio-card__metric">
      <span class="portfolio-card__label">持仓市值</span>
      <MoneyDisplay
        class="portfolio-card__value"
        :value="item.market_value ?? 0"
        size="lg"
        :show-sign="false"
        :auto-color="false"
      />
    </div>

    <!-- 次指标：累计盈亏（与主指标同构：label 在上、值在下，别让右侧浮一个游离的数字） -->
    <div class="portfolio-card__metric">
      <span class="portfolio-card__label">累计盈亏</span>
      <span class="portfolio-card__pnl">
        <MoneyDisplay :value="item.pnl ?? 0" size="md" />
        <span v-if="item.pnl_rate != null" class="portfolio-card__rate">
          <MoneyDisplay
            :value="item.pnl_rate"
            size="sm"
            :show-currency="false"
            suffix="%"
          />
        </span>
      </span>
    </div>

    <div class="portfolio-card__divider" />

    <!-- 元信息：账户 / 持仓是「这张卡覆盖什么」，目标达成是唯一的比例型进度 -->
    <footer class="portfolio-card__meta">
      <p class="portfolio-card__meta-line">
        {{ item.account_count ?? 0 }} 个账户 ·
        {{ item.position_count ?? 0 }} 只持仓
      </p>
      <div v-if="item.target_progress != null" class="portfolio-card__target">
        <div class="portfolio-card__target-row">
          <span class="portfolio-card__label">目标达成</span>
          <span class="portfolio-card__target-pct">{{ progressText }}</span>
        </div>
        <!-- 达成率不封顶（后端如此），进度条封顶 100%：数字说「超了多少」，条说「已满」 -->
        <div class="portfolio-card__track">
          <i
            class="portfolio-card__fill"
            :style="{ width: targetFillWidth(item.target_progress) }"
          />
        </div>
      </div>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import type { PortfolioItem } from "@/api/portfolio";
import { formatTargetProgress, targetFillWidth } from "../portfolioCardModel";

const props = defineProps<{ item: PortfolioItem }>();

const emit = defineEmits<{
  /** 整卡点击 → 由页面负责路由（组件不碰路由，便于单测与复用） */
  (e: "open", id: number): void;
  (e: "delete", id: number): void;
}>();

/** 达成率文案（整数百分比；数字不封顶、条封顶的口径见 portfolioCardModel） */
const progressText = computed(() =>
  formatTargetProgress(props.item.target_progress)
);
</script>

<style lang="scss" scoped>
.portfolio-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
  padding: var(--space-standard);
  cursor: pointer;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-raised);
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;

  &:hover {
    border-color: var(--border-default);
    box-shadow: var(--shadow-float);
    transform: translateY(-2px);
  }

  /* 键盘用户：聚焦到删除按钮时整卡给出可见反馈（否则 hover 样式是唯一提示） */
  &:focus-within {
    border-color: var(--brand-400);
  }

  /* ===== 卡头 ===== */
  &__head {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    min-height: 24px;
  }

  &__name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--text-body);
    font-weight: 600;
    line-height: 1.4;
    color: var(--text-primary);
    white-space: nowrap;
  }

  &__purpose {
    flex: none;
    padding: 1px var(--space-2);
    font-size: var(--text-label);
    font-weight: 500;
    line-height: 1.5;
    color: var(--text-secondary);
    background: var(--bg-soft);
    border-radius: var(--radius-pill);
  }

  /* 常驻红钮 = 卡片里最抢眼的元素，而删除是低频且有破坏性的动作：
     默认隐形，hover / 聚焦显现；无 hover 的触屏设备常显（否则点不到） */
  &__delete {
    flex: none;
    margin-left: auto;
    color: var(--text-tertiary-ink);
    opacity: 0;
    transition: opacity 0.18s ease;
  }

  &:hover &__delete,
  &:focus-within &__delete {
    opacity: 1;
  }

  /* ===== 指标 ===== */
  &__metric {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  &__label {
    font-size: var(--text-label);
    font-weight: 500;
    line-height: 1.4;
    color: var(--text-secondary);
  }

  /* 主数字：24px（--text-num-hero 同档）。MoneyDisplay 内部 .number 是 500，
     这里对齐「数字强调」的 600——只在本卡片覆写，不动全站组件默认值 */
  &__value {
    :deep(.number) {
      font-weight: 600;
    }
  }

  &__pnl {
    display: inline-flex;
    gap: var(--space-2);
    align-items: baseline;
  }

  /* 比例胶囊：底用中性 --bg-soft、字由 MoneyDisplay 上语义色——
     站内没有「涨/跌底色」令牌（只有 -ink 文字级），现造一个等于开第二套色；
     金额本身已是彩色，胶囊只承担「和金额区分开」的角色 */
  &__rate {
    flex: none;
    padding: 0 var(--space-2);
    background: var(--bg-soft);
    border-radius: var(--radius-pill);
  }

  &__divider {
    height: 1px;
    background: var(--border-light);
  }

  /* ===== 元信息 ===== */

  /* 不贴底（原本 margin-top:auto）：三张卡的前三块内容一致，贴底会让「没设目标」的卡
     把元信息甩到最下面、和其它卡错位；空白留在卡底比信息错位好 */
  &__meta {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  &__meta-line {
    font-size: var(--text-label);
    line-height: 1.4;
    color: var(--text-tertiary-ink);
  }

  &__target-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: var(--space-1);

    /* 目标达成是次级信息：label 再弱一档，只让百分比数字（600）说话 */
    .portfolio-card__label {
      color: var(--text-tertiary-ink);
    }
  }

  &__target-pct {
    font-size: var(--text-label);
    font-weight: 600;
    color: var(--text-primary);
  }

  &__track {
    height: 4px;
    overflow: hidden;
    background: var(--bg-soft);
    border-radius: var(--radius-pill);
  }

  /* 4px 细条上 --brand-400 过淡（实测几乎看不见），取 500 档：可见但仍弱于任何数字 */
  &__fill {
    display: block;
    height: 100%;
    background: var(--brand-500);
    border-radius: var(--radius-pill);
  }
}

/* 触屏没有 hover：删除按钮常显（宁可多一点噪声，也不能让操作点不到） */
@media (hover: none) {
  .portfolio-card__delete {
    opacity: 1;
  }
}
</style>
