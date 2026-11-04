<!--
  TodayPnlCard · 首页「最新收益」卡（2026-11-03 用户拍板的卡面，11-04 改版）

  信息层级四层，从上到下：
    1. 最新收益（hero）+ 当日涨幅              ← 唯一的强色数字
    2. 投资类资产（次级）+ 占家庭总资产          ← 把两个刻度接起来
    3. 场内权益 / 场外基金两列                  ← `TodayPnlClassColumns`
    4. 家庭口径 · 存量（三列 + 负债率 + 结构条）  ← `TodayPnlHouseholdBand`

  为什么第 3、4 层拆成子组件：这张卡从 370 行涨到 838 行，越过仓库
  「页面规模只减不增」门禁（#980，阈值 400 行）。拆法按**读者的问题**切，
  不按代码块切——第 3 层答「今天谁赚的」，第 4 层答「我家底子多厚」，
  两者连数据来源都不同（today-pnl vs summary），本就不该同处一室。

  为什么分项和合计能写得这么「敢」：两列与 hero 是**同一份数据**的两个切面
  （后端 `Σ classes.pnl ≡ total_pnl`），前端不做第二次相加；占比也一律后端直出
  （`share_of_invested` / `invested_ratio_of_assets`），卡面不做除法。

  估值口径（估 / 确认）：
    · 盘中或收盘估值定格 ⇒ 徽标「估」+ 副标题说明；
    · 官方净值到位 ⇒ 徽标消失、副标题写「官方净值已确认」（安静态，不抢数字）。

  数字跳动（用户要求「不打扰」）：只有 hero 与两列盈亏做 420ms 缓动，
  市值 / 总资产直接落值——它们是稳定锚点，一起动会显得整张卡在抖。

  隐私模式：金额换 `••••`（渲染层替换，不是 CSS 模糊），百分比 / 涨跌色 / 负债率
  全部保留；长按卡面可临时窥视。详见 `composables/usePrivacyMode.ts`。

  手势只有一个来源：长按 = 窥视、短按 = 跳页。`peekGuard` 把「刚才揭开过吗」
  递给家庭带——不递的话，长按松手那一下会先亮出真值、再顺势把用户带走。
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

    <div
      v-else-if="data"
      class="today-pnl__body"
      @pointerdown="onPeekStart"
      @pointerup="onPeekEnd"
      @pointerleave="onPeekEnd"
      @pointercancel="onPeekEnd"
    >
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
          <p class="today-pnl__sub">
            {{ subtitle }}
            <span v-if="masked" class="today-pnl__peek-hint"
              >· 长按查看金额</span
            >
          </p>
        </div>

        <div class="today-pnl__invested">
          <el-tooltip
            placement="top"
            content="只统计场内权益（股票/ETF/可转债）与场外基金；房产、现金、理财等见下方家庭净资产"
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
          <!-- 占比把「411,679 在 3,395,884 里算什么」一句话说完：这张卡上半是
               投资口径、下半是家庭口径，中间原本没有任何桥 -->
          <p
            v-if="data.invested_ratio_of_assets != null"
            class="today-pnl__invested-ratio"
          >
            占家庭总资产 {{ pct1(data.invested_ratio_of_assets) }}
          </p>
        </div>
      </div>

      <div class="today-pnl__rule" />

      <TodayPnlClassColumns :classes="data.classes" />

      <TodayPnlHouseholdBand
        :total-assets="totalAssets"
        :net-assets="netAssets"
        :total-liabilities="totalLiabilities"
        :liability-ratio="liabilityRatio"
        :peek-guard="consumePeekClick"
      />
    </div>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import ValuationSourceBadge from "@/components/ValuationSourceBadge/index.vue";
import { useTweenNumber } from "@/composables/useTweenNumber";
import { usePrivacyMode } from "@/composables/usePrivacyMode";
import TodayPnlClassColumns from "./TodayPnlClassColumns.vue";
import TodayPnlHouseholdBand from "./TodayPnlHouseholdBand.vue";
import { pct1, rateClass, signedRate } from "../composables/pnlFormat";
import type { TodayPnlData } from "@/api/summary";

defineOptions({ name: "TodayPnlCard" });

const props = defineProps<{
  data: TodayPnlData | null;
  /** 口径 + 时间（盘中 / 收盘估值 / 已确认 / 最近交易日），由 composable 算 */
  subtitle: string;
  loading: boolean;
  error: boolean;
  /** 家庭总资产（后端 `total_assets_cny` 直出） */
  totalAssets: number | null;
  /** 家庭净资产（直出字段，前端不二次算） */
  netAssets: number | null;
  /** 家庭总负债（同上） */
  totalLiabilities: number | null;
  /** 负债率（%，后端 `ratio_pct` 直出）；null = 总资产为 0，此时不显示比率 */
  liabilityRatio: number | null;
}>();

const emit = defineEmits<{ retry: [] }>();

/** 含估值价（收盘估值定格或盘中替换）⇒ 挂「估」徽标；确认后自动消失 */
const estimated = computed(() => props.data?.status === "estimated");

const totalTween = useTweenNumber(
  computed(() => props.data?.total_pnl ?? null)
);

// ── 隐私模式（只藏金额，保留百分比）──
const { masked, peeking, startPeek, endPeek } = usePrivacyMode();

/**
 * 长按窥视与「三列可点击」是同一个手势的两个含义：按住 = 看数字，短按 = 跳走。
 * 不处理的话，长按松手那一下会先亮出真值、再顺势把用户带走——「看一眼」的代价
 * 变成换页。故记一次「这次按压确实揭开过」，由家庭带的点击处理吃掉紧随的 click。
 * 每次 pointerdown 都重置，不会误伤下一次正常点击。
 */
let peekFired = false;
const onPeekStart = () => {
  peekFired = false;
  startPeek();
};
const onPeekEnd = () => {
  if (peeking.value) peekFired = true;
  endPeek();
};

/**
 * 递给子组件：这次点击是不是长按的余波。
 *
 * 做成「消费一次就复位」而不是直接传 `peekFired` 变量：真值在父组件，
 * 若让子组件读原始标记，同一次长按会连累下一次正常点击（标记没人清）。
 */
function consumePeekClick(): boolean {
  if (!peekFired) return false;
  peekFired = false;
  return true;
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

/* 投资类资产的占比：紧贴数字下方、与标签同色阶，读作「这个数的一个注解」 */
.today-pnl__invested-ratio {
  margin: 5px 0 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 遮罩态的提示：只在金额被藏起来时出现，告诉用户「不是坏了，是藏了，长按能看」 */
.today-pnl__peek-hint {
  color: var(--text-tertiary-ink);
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
