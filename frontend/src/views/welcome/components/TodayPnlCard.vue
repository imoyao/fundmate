<!--
  TodayPnlCard · 首页「最新收益」卡（2026-11-03 用户拍板的卡面）

  信息层级只有三层，从上到下：
    1. 最新收益（hero）+ 当日涨幅   ← 唯一的强色数字
    2. 投资类资产（次级）+ 股票 / 基金两列（分项盈亏 + 市值）
    3. 家庭净资产 · 总负债（底注，另一层刻度）

  为什么分项和合计能写得这么「敢」：两列与 hero 是**同一份数据**的两个切面
  （后端 `Σ classes.pnl ≡ total_pnl`），前端不做第二次相加。

  估值口径（估 / 确认）：
    · 盘中或收盘估值定格 ⇒ 徽标「估」+ 副标题说明；
    · 官方净值到位 ⇒ 徽标消失、副标题写「官方净值已确认」（安静态，不抢数字）。

  数字跳动（用户要求「不打扰」）：只有 hero 与两列盈亏做 420ms 缓动，
  市值 / 总资产直接落值——它们是稳定锚点，一起动会显得整张卡在抖。
-->
<template>
  <CardBlock class="today-pnl">
    <!-- 失败态（沿用 #1832 口径）：不显示 ¥0。0 在资产语境里是结论，不是「不知道」 -->
    <div
      v-if="error"
      class="today-pnl__state"
      role="alert"
      :style="{ color: 'var(--text-secondary)' }"
    >
      <p class="text-sm">当日收益加载失败，请检查网络后重试</p>
      <el-button size="small" type="primary" @click="emit('retry')">
        重新加载
      </el-button>
    </div>

    <div
      v-else-if="loading && !data"
      class="today-pnl__state"
      :style="{ color: 'var(--text-tertiary-ink)' }"
    >
      <span class="text-sm">正在计算当日收益…</span>
    </div>

    <div v-else-if="data" class="today-pnl__body">
      <div class="today-pnl__head">
        <div class="today-pnl__primary">
          <p class="today-pnl__label">
            <span>最新收益（元）</span>
            <el-tooltip
              v-if="estimated"
              placement="top"
              content="当日价含基金收盘估值，官方净值公布后自动更新为确认值"
            >
              <ValuationSourceBadge
                status="estimated"
                size="sm"
                tip="当日价含基金收盘估值，官方净值公布后自动更新为确认值"
              />
            </el-tooltip>
          </p>
          <div class="today-pnl__hero">
            <MoneyDisplay
              :value="totalTween"
              size="hero"
              :show-currency="false"
            />
            <span
              v-if="data.total_rate != null"
              class="today-pnl__hero-rate"
              :class="rateClass(data.total_rate)"
              >{{ signedRate(data.total_rate) }}</span
            >
          </div>
          <p class="today-pnl__sub">{{ subtitle }}</p>
        </div>

        <div class="today-pnl__invested">
          <el-tooltip
            placement="top"
            content="只统计股票与基金（有当日估值口径的持仓）；房产、现金、理财等见下方家庭净资产"
          >
            <p class="today-pnl__label">投资类资产</p>
          </el-tooltip>
          <MoneyDisplay
            :value="data.invested_value"
            size="lg"
            :show-sign="false"
            :auto-color="false"
            custom-color="var(--text-primary)"
          />
        </div>
      </div>

      <div class="today-pnl__rule" />

      <div v-if="data.classes.length" class="today-pnl__cols">
        <div
          v-for="item in data.classes"
          :key="item.key"
          class="today-pnl__col"
        >
          <p class="today-pnl__label">{{ item.label }}</p>
          <div class="today-pnl__col-value">
            <MoneyDisplay
              :value="tweenOf(item.key)"
              size="lg"
              :show-currency="false"
              empty-text="—"
            />
            <span
              v-if="item.rate != null"
              class="today-pnl__col-rate"
              :class="rateClass(item.rate)"
              >{{ signedRate(item.rate) }}</span
            >
          </div>
          <MoneyDisplay
            :value="item.market_value"
            size="sm"
            :show-sign="false"
            :auto-color="false"
            custom-color="var(--text-tertiary-ink)"
          />
        </div>
      </div>

      <p
        v-else
        class="today-pnl__empty"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      >
        还没有可估值的股票或基金持仓
      </p>

      <p
        v-if="netAssets != null || totalLiabilities != null"
        class="today-pnl__foot"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      >
        家庭净资产 {{ formatted(netAssets) }} · 家庭总负债
        {{ formatted(totalLiabilities) }}
      </p>
    </div>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import ValuationSourceBadge from "@/components/ValuationSourceBadge/index.vue";
import { useTweenNumber } from "@/composables/useTweenNumber";
import type { TodayPnlClass, TodayPnlData } from "@/api/summary";

defineOptions({ name: "TodayPnlCard" });

const props = defineProps<{
  data: TodayPnlData | null;
  /** 口径 + 时间（盘中 / 收盘估值 / 已确认 / 最近交易日），由 composable 算 */
  subtitle: string;
  loading: boolean;
  error: boolean;
  /** 家庭净资产（底注；与卡内「投资类资产」是两层刻度）——直出字段，前端不二次算 */
  netAssets: number | null;
  /** 家庭总负债（同上） */
  totalLiabilities: number | null;
}>();

const emit = defineEmits<{ retry: [] }>();

/** 含估值价（收盘估值定格或盘中替换）⇒ 挂「估」徽标；确认后自动消失 */
const estimated = computed(() => props.data?.status === "estimated");

const classOf = (key: TodayPnlClass["key"]) =>
  props.data?.classes.find(item => item.key === key) ?? null;

const totalTween = useTweenNumber(
  computed(() => props.data?.total_pnl ?? null)
);
const stockTween = useTweenNumber(
  computed(() => classOf("stock")?.pnl ?? null)
);
const fundTween = useTweenNumber(computed(() => classOf("fund")?.pnl ?? null));

const tweenOf = (key: TodayPnlClass["key"]) =>
  key === "stock" ? stockTween.value : fundTween.value;

const rateClass = (value: number) =>
  value > 0 ? "is-rise" : value < 0 ? "is-fall" : "is-zero";

/** `+0.20%` / `-1.17%`：符号与数值同号，零值不带符号 */
const signedRate = (value: number) =>
  `${value > 0 ? "+" : value < 0 ? "-" : ""}${Math.abs(value).toFixed(2)}%`;

/** 千分位金额（底注用；与 MoneyDisplay 同一格式，但不需要涨跌色与货币符号） */
function formatted(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const fixed = Math.abs(value).toFixed(2);
  const [intPart, decimals] = fixed.split(".");
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `¥${grouped}.${decimals}`;
}
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.today-pnl {
  display: flex;
  flex-direction: column;
  gap: var(--space-standard);
}

.today-pnl__state {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  justify-content: center;
  padding: 32px 0;
}

.today-pnl__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-standard);
}

/* 头部：左侧收益（主角）+ 右侧投资类资产（次级锚点）。
   两者不等宽——主角占满剩余，副锚按内容宽，避免「两个大数字打架」。 */
.today-pnl__head {
  display: flex;
  gap: var(--space-5, 24px);
  align-items: flex-start;
  justify-content: space-between;
}

.today-pnl__primary {
  min-width: 0;
}

.today-pnl__invested {
  flex: none;
  text-align: right;
}

.today-pnl__label {
  display: flex;
  gap: 6px;
  align-items: center;
  margin: 0 0 6px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.today-pnl__invested .today-pnl__label {
  justify-content: flex-end;
}

/* hero + 涨幅：涨幅随 hero 的基线走，比 hero 小一档（--text-title）——
   「+0.20%」是注解，不该与「+1,227.88」平起平坐。 */
.today-pnl__hero {
  display: flex;
  gap: 10px;
  align-items: baseline;
  min-width: 0;
}

.today-pnl__hero-rate {
  font-size: var(--text-title, 24px);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.today-pnl__sub {
  display: flex;
  gap: 6px;
  align-items: center;
  margin: 8px 0 0;
  font-size: var(--text-label);
  color: var(--text-secondary);
}

.today-pnl__rule {
  height: 1px;
  background-color: var(--border-light);
}

/* 两列分项：竖线是同级弱分隔（--border-subtle），比外框横线轻一档 */
.today-pnl__cols {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.today-pnl__col {
  min-width: 0;
  padding: 0 var(--space-compact);
}

.today-pnl__col:first-child {
  padding-left: 0;
}

.today-pnl__col + .today-pnl__col {
  border-left: 1px solid var(--border-subtle);
}

.today-pnl__col-value {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin-bottom: 4px;
}

.today-pnl__col-rate {
  font-size: var(--text-small, 14px);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.today-pnl__empty {
  margin: 0;
  font-size: var(--text-small);
}

.today-pnl__foot {
  padding-top: var(--space-3, 12px);
  margin: 0;
  font-size: var(--text-label);
  border-top: 1px solid var(--border-light);
}

.is-rise {
  color: var(--color-rise-ink);
}

.is-fall {
  color: var(--color-fall-ink);
}

.is-zero {
  color: var(--text-secondary);
}

/* <768（md 档）：与 Tailwind `md:` 同阈值，刻度走 _breakpoints.scss 单一来源 */
@include bp.below("md") {
  .today-pnl__head {
    flex-direction: column;
    gap: var(--space-3, 12px);
  }

  .today-pnl__invested {
    text-align: left;
  }

  .today-pnl__invested .today-pnl__label {
    justify-content: flex-start;
  }

  /* 小屏降一档字阶（57 → 32）：hero 与 24px 涨幅挤在一行会溢出 320px 容器。
     只调数字与涨幅，标签 / 市值保持原档，层级关系不变。 */
  .today-pnl__hero :deep(.money-display.size-hero .number) {
    font-size: var(--text-display, 32px);
  }

  .today-pnl__hero-rate {
    font-size: var(--text-body, 16px);
  }
}
</style>
