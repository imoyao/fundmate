<template>
  <CardBlock class="net-worth-card" data-region="net-worth">
    <div class="net-worth-card__head">
      <p class="overview-label">净资产</p>
      <!-- 更新时间原先只在 md 以上显示、且吊在卡片右下角；并入眉标行后与「净资产」
           同一条基线，卡片底部因此空出来给指标行，不再出现「右下角孤零零一行小字」。 -->
      <p class="net-worth-card__updated">更新于 {{ lastUpdate }}</p>
    </div>

    <div class="net-worth-card__hero">
      <!-- 净资产是**存量**不是盈亏：不能走 MoneyDisplay 默认的 auto-color
           （>0 会被染成涨红，读成「今天赚了」）。沿用全景页 hero 的口径——
           存量用品牌文字级 --brand-ink 做唯一强色锚点；为负（资不抵债）时
           才切危险色，那是真风险，不该被当成「跌了一点」。 -->
      <MoneyDisplay
        :value="netWorth"
        size="hero"
        :show-sign="false"
        :auto-color="false"
        :custom-color="heroColor"
      />
      <span v-if="showHighLiabilityWarning" class="liability-badge">
        负债率偏高
      </span>
    </div>

    <!-- 指标行：与上方大数字用一条 --border-light 结构性断点隔开（同级并列的
         三格之间才用更弱的 --border-subtle 竖线，见样式块）。 -->
    <div
      class="net-worth-card__metrics"
      :style="{ '--metric-cols': String(metricCols) }"
      data-region="net-worth-metrics"
    >
      <div class="metric" data-metric="total-assets">
        <span class="metric__label">总资产</span>
        <MoneyDisplay
          :value="totalAssets"
          size="md"
          :show-sign="false"
          :auto-color="false"
          custom-color="var(--text-primary)"
        />
      </div>
      <!-- 无负债时整格不渲染（不是显示 0）：摘要里每个 0 都在占用一次阅读，
           而「没有负债」本身不需要一行数字来证明。列数随之从 3 收到 2。 -->
      <div v-if="liabilityTotal > 0" class="metric" data-metric="liability">
        <span class="metric__label">负债</span>
        <MoneyDisplay
          :value="liabilityTotal"
          size="md"
          :show-sign="false"
          :auto-color="false"
          custom-color="var(--text-primary)"
        />
      </div>
      <div class="metric" data-metric="liability-rate">
        <span class="metric__label">负债率</span>
        <span class="metric__rate">{{ liabilityRate }}</span>
      </div>
    </div>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";

defineOptions({ name: "NetWorthCard" });

const props = defineProps<{
  netWorth: number;
  totalAssets: number;
  liabilityTotal: number;
  /** 已格式化的负债率（"53.3%" / "—"），口径在 composable 里，卡片不重算 */
  liabilityRate: string;
  showHighLiabilityWarning: boolean;
  lastUpdate: string;
}>();

/** 负债为 0 时不渲染「负债」格，列数跟着走——写死 3 列会留一个空轨道。 */
const metricCols = computed(() => (props.liabilityTotal > 0 ? 3 : 2));

const heroColor = computed(() =>
  props.netWorth < 0 ? "var(--color-danger)" : "var(--brand-ink)"
);
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

/* 卡片眉标：13px 辅助色，只说明「这块数是什么」，不参与层级竞争。
   壳（bg / border / 圆角 / 阴影 / 24px 内边距）由 CardBlock 提供。 */
.overview-label {
  margin: 0;
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--text-tertiary-ink);
}

.net-worth-card {
  /* hero 字号按档位走：lg~xl 两栏并排时卡片只有 ~360px，57px 放不下
     「¥1,540,962.73」（实测 372px），退到 40px（--text-display-lg）；
     xl 起回到 57px；sm 以下再退到 32px（见文件末尾）。 */
  --hero-size: var(--text-hero);

  display: flex;
  flex-direction: column;
  gap: var(--space-compact);
  justify-content: space-between;
}

/* 把档位变量接到 MoneyDisplay 读取的那个自定义属性上（组件内部
   `.size-hero .number` 用的是 `var(--text-hero)`，从容器覆盖才父子一起缩） */
.net-worth-card__hero {
  --text-hero: var(--hero-size);

  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  align-items: flex-start;
}

.net-worth-card__head {
  display: flex;
  gap: var(--space-3);
  align-items: baseline;
  justify-content: space-between;
}

.net-worth-card__updated {
  margin: 0;
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

/* 负债率警示：负债属中性信息，只有「偏高」才用系统警示色（非涨跌色）。
   胶囊底用警示色 20% 透明（--color-warning-20），与对账 banner 同族。 */
.liability-badge {
  display: inline-block;
  padding: 2px 8px;
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--color-warning-ink);
  background: var(--color-warning-20);
  border-radius: var(--radius-pill);
}

.net-worth-card__metrics {
  display: grid;
  grid-template-columns: repeat(var(--metric-cols, 3), minmax(0, 1fr));
  gap: var(--space-compact);
  padding-top: var(--space-compact);
  border-top: 1px solid var(--border-light);
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;

  /* 数字等宽：三格数字纵向对齐时不能左右跳 */
  font-variant-numeric: tabular-nums;
}

/* 竖线是「同级并列」的弱分隔：降权到 --border-subtle，且与两侧内容留 16px，
   贴上去会读成「线压着字」（同 panorama 摘要卡）。 */
.metric + .metric {
  padding-left: var(--space-compact);
  border-left: 1px solid var(--border-subtle);
}

.metric__label {
  font-size: var(--text-label);
  line-height: 18px;
  color: var(--text-tertiary-ink);
}

.metric__rate {
  font-size: var(--text-body);
  font-weight: 500;
  line-height: 24px;
  color: var(--text-primary);
}

/* 窄屏：三列并排会让「¥3,300,962.73」超出 1/3 轨道（390 视口实测溢出），
   改为「标签左 / 数值右」的三行清单；竖线换横线，同一条分隔语义不换。 */
@include bp.below("sm") {
  .net-worth-card__metrics {
    grid-template-columns: 1fr;
    gap: var(--space-2);
  }

  .metric {
    flex-direction: row;
    gap: var(--space-3);
    align-items: baseline;
    justify-content: space-between;
  }

  .metric + .metric {
    padding-top: var(--space-2);
    padding-left: 0;
    border-top: 1px solid var(--border-subtle);
    border-left: none;
  }

  /* 手机端 hero 必须缩字：57px 下「¥1,540,962.73」在 390 视口会被卡片右缘裁掉。
     覆盖自定义属性而不是写 font-size——`.money-display.size-hero .number` 自带
     `font-size: var(--text-hero)`，从容器改属性才能父子一起缩（同详情页 2026-11-15 修法）。 */
  .net-worth-card__hero {
    --text-hero: var(--text-display);
  }
}

/* lg~xl：两栏并排、卡片约 360~400px，hero 收到 40px（57px 的金额宽 372px 放不下） */
@include bp.above("lg") {
  .net-worth-card {
    --hero-size: var(--text-display-lg);
  }
}

/* xl 起净资产卡拿回 1.2 份额，恢复 57px 主锚点 */
@include bp.above("xl") {
  .net-worth-card {
    --hero-size: var(--text-hero);
  }
}
</style>
