<!--
  TodayPnlHouseholdBand · 首页「最新收益」卡的第 4 层：家庭口径 · 存量

  为什么它必须是一块**独立**的带，而不是底注一行小字：
  上面三层是「当日收益（流量，会天天变）」，这一层是「家庭存量（总资产 / 负债 /
  净资产，天天几乎不变）」。两种刻度混排且没有分界，读者会把 1,760,000 当成
  「今天还亏了这么多」。故整块独立、上方用 `--border-light` 结构线切开。

  为什么三列必须按 总资产 → 负债 → 净资产 排：
  只有排成 `A = L + E` 才自洽。11-03 版只写「净资产 · 总负债」，读者拼不出总资产，
  也看不出卡面 hero 只是家庭的 12%——缺的那一项正是把两层刻度连起来的锚点。

  为什么三列各自是**不同**的入口（2026-11-04 用户拍板）：
    总资产 → 资产总览（存量结构）· 总负债 → 盘点页负债档（逐笔）
    净资产 → 复盘页净值走势（时间）
  同一个链接复制三次，点击只能证明「能点」，不带来任何新信息。
  用 `<a href>` 而非 `<div @click>`：中键新标签、键盘 Enter、读屏「链接」角色都白拿；
  click 里 preventDefault 后自行 router.push（history 模式下 href 直跳等于整页刷新）。

  负债为什么不用涨跌色：红在这套体系里是「涨=好」，而负债增加是坏事，直接套用会
  语义反转。故绝对值恒为中性色，杠杆水平交给「负债率」表达；只有资不抵债
  （≥100%）才升级为危险色——那时它表达的是「风险」，不是「符号」。
-->
<template>
  <section class="household" @contextmenu="onContextMenu">
    <div class="household__head">
      <span class="household__title">家庭口径 · 存量</span>
      <span
        v-if="ratioText"
        class="household__chip"
        :class="{ 'is-insolvent': isInsolvent }"
      >
        负债率 {{ ratioText }}
      </span>
    </div>

    <div class="household__cols">
      <a
        v-for="col in cols"
        :key="col.key"
        class="household__col household__col--link"
        :class="{ 'household__col--net': col.strong }"
        :href="col.to"
        :title="col.title"
        @click="onClick($event, col.to)"
      >
        <p class="household__label">
          <span>{{ col.label }}</span>
          <!-- 箭头默认透明：三个常驻箭头会把「读数区」读成「按钮排」 -->
          <IconifyIconOffline
            icon="ep:arrow-right"
            class="household__go"
            aria-hidden="true"
          />
        </p>
        <MoneyDisplay
          :value="col.value"
          size="md"
          :show-sign="false"
          :auto-color="false"
          :custom-color="col.color"
        />
      </a>
    </div>

    <!-- 杠杆结构条：把 1,760,000 从「一个吓人的数」变成「一个水位」。
         纯视觉冗余（不计入读屏），文字结论由上面的 chip 承担。 -->
    <div
      v-if="debtShare != null && legend"
      class="household__leverage"
      aria-hidden="true"
    >
      <div class="household__track">
        <span
          class="household__debt"
          :class="{ 'is-insolvent': isInsolvent }"
          :style="{ width: debtShare + '%' }"
        />
      </div>
      <div class="household__legend">
        <span>负债 {{ legend.debt }}</span>
        <span>{{ legend.equity }}</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { HOUSEHOLD_COLS } from "../composables/householdCols";
import { pct1 } from "../composables/pnlFormat";
import { useHouseholdLinks } from "../composables/useHouseholdLinks";

defineOptions({ name: "TodayPnlHouseholdBand" });

const props = defineProps<{
  /** 家庭总资产（后端 `total_assets_cny` 直出） */
  totalAssets: number | null;
  /** 家庭净资产（直出字段，前端不二次算） */
  netAssets: number | null;
  /** 家庭总负债（同上） */
  totalLiabilities: number | null;
  /** 负债率（%，后端 `ratio_pct` 直出）；null = 总资产为 0，此时不显示比率 */
  liabilityRatio: number | null;
  /**
   * 「刚才那次按压揭开过真值 ⇒ 这次 click 是手势余波，应被吃掉」。
   * 长按窥视绑在整张卡上（父组件持有状态），而点击发生在这里，
   * 故用一个函数把判断权递进来，而不是把整套手势状态复制一份。
   */
  peekGuard: () => boolean;
}>();

/** 资不抵债（负债率 ≥ 100%）：唯一允许把负债率染成危险色的情形 */
const isInsolvent = computed(() => (props.liabilityRatio ?? 0) >= 100);

/** 负债率文案（null 时不渲染整枚徽标，而不是渲染成 0.0%） */
const ratioText = computed(() =>
  props.liabilityRatio == null ? null : pct1(props.liabilityRatio)
);

/**
 * 结构条里「负债」那一段的宽度（%）。
 *
 * clamp 到 0–100 是必需的：负净资产时负债率会 > 100%，直接当 width 用会让
 * 负债段溢出轨道、把「净资产 10%」画成负数——那时它不是两段结构，而是
 * 「负债已经吃掉全部资产还有余」，由 `isInsolvent` 接管文案。
 */
const debtShare = computed(() => {
  const ratio = props.liabilityRatio;
  if (ratio == null) return null;
  return Math.min(100, Math.max(0, ratio));
});

/**
 * 结构条下方的图例。两段结构只在「净资产为正」时成立：
 * 负债率 ≥ 100% 时剩余部分是负的，再写「净资产 -12.3%」会被读成「还有一截」，
 * 故换成一句结论——条已满，原因是负债吃穿了资产。
 */
const legend = computed(() => {
  const ratio = props.liabilityRatio;
  if (ratio == null) return null;
  return {
    debt: pct1(ratio),
    equity: isInsolvent.value ? "已资不抵债" : `净资产 ${pct1(100 - ratio)}`
  };
});

/** 三列 = 三个入口；列定义（标签 / 入口 / 取值口径）见 composables/householdCols */
const cols = computed(() =>
  HOUSEHOLD_COLS.map(col => ({ ...col, value: col.pick(props) }))
);

// 短按跳页 / 长按余波 / 触屏长按菜单的契约都在 composable 里（见其文件头）
const { onClick, onContextMenu } = useHouseholdLinks(props.peekGuard);
</script>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

/* 上方 --border-light 是**结构断点**（流量 → 存量），与卡片外框同重；
   三列之间用 --border-subtle 竖线（同级并列，降一档），两级线重不可互换。 */
.household {
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 12px);
  padding-top: var(--space-compact, 16px);
  border-top: 1px solid var(--border-light);
}

.household__head {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.household__title {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  letter-spacing: 0.4px;
}

/* 负债率徽标：负债的「特殊显示」落点。
   绝对值保持中性色——负债不是亏损，用涨跌色会语义反转（红=涨=好 vs 负债增=坏）；
   只有资不抵债（≥100%）才升级为危险色，那时它表达的是「风险」而非「符号」。 */
.household__chip {
  padding: 1px 8px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  white-space: nowrap;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
}

.household__chip.is-insolvent {
  color: var(--color-danger-ink);
  background-color: var(--color-danger-10);
  border-color: var(--color-danger-20);
}

.household__cols {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.household__col {
  min-width: 0;
  padding: 0 var(--space-compact, 16px);
}

.household__col:first-child {
  padding-left: 0;
}

.household__col:last-child {
  padding-right: 0;
}

.household__col + .household__col {
  border-left: 1px solid var(--border-subtle);
}

.household__label {
  display: flex;
  gap: 6px;
  align-items: center;
  margin: 0 0 6px;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 净资产是这一带的结论：只加字重，不加字号/颜色——否则三列会打成三个主角 */
.household__col--net :deep(.number) {
  font-weight: 600;
}

/* ===== 三列 = 入口 =====
   悬停只铺一层 --bg-soft，不动字号/颜色/字重：这一带是「读数」，数字在悬停时
   跳一下会让人以为数值变了。命中区就交给列自身——桌面端一列 44px 高、宽度撑满
   1/3 卡宽，**不再**用「padding + 负 margin」抬命中区：那招在窄屏（三行只隔
   8px gap）会让相邻两行的命中区互相盖住，点「总负债」落到「总资产」上。 */
.household__col--link {
  position: relative;
  display: block;
  color: inherit;
  text-decoration: none;
  border-radius: var(--radius-sm);
  transition: background-color 0.15s ease;

  /* iOS 长按链接会浮出 callout（预览 / 拷贝），把「长按窥视」顶掉 */
  -webkit-touch-callout: none;

  &:hover {
    background-color: var(--bg-soft);
  }

  /* 触屏没有 :hover 可依，用 :active 给一次按压反馈 */
  &:active {
    background-color: var(--bg-soft);
  }

  /* 焦点环用全局 --focus-ring（两段式，与站内其它可点击块一致）。
     不用 outline：圆角块上 outline 会画成直角，且贴边的列会把外侧描边切掉。 */
  &:focus-visible {
    z-index: 1;
    outline: none;
    box-shadow: var(--focus-ring);
  }
}

/* 箭头默认透明：三个常驻箭头会把「读数区」读成「按钮排」。
   悬停/聚焦才淡入，并从左 2px 归位——120ms 的小动作负责说「这里能去」。 */
.household__go {
  width: 12px;
  height: 12px;
  color: var(--text-tertiary-ink);
  opacity: 0;
  transform: translateX(-2px);
  transition:
    opacity 0.15s ease,
    transform 0.15s ease;
}

.household__col--link:hover .household__go,
.household__col--link:focus-visible .household__go {
  opacity: 0.7;
  transform: translateX(0);
}

/* 触屏没有 hover 可「揭示」：箭头常驻一档淡色，否则用户不知道这几列能点 */
@media (hover: none) {
  .household__go {
    opacity: 0.45;
    transform: translateX(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .household__col--link,
  .household__go {
    transition: none;
  }
}

/* ===== 杠杆结构条 =====
   把「负债 1,760,000」变成「水位 51.8%」。负债段中性色，剩余部分是净资产；
   资不抵债时整条转危险色（此时没有「净资产段」可言，不能画成两段）。 */
.household__leverage {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.household__track {
  height: 4px;
  overflow: hidden;
  background-color: var(--border-subtle);
  border-radius: 2px;
}

.household__debt {
  display: block;
  height: 100%;
  background-color: var(--color-neutral);
  border-radius: 2px 0 0 2px;
}

.household__debt.is-insolvent {
  background-color: var(--color-danger);
  border-radius: 2px;
}

.household__legend {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* <768（md 档）：与 Tailwind `md:` 同阈值，刻度走 _breakpoints.scss 单一来源 */
@include bp.below("md") {
  /* 三列在 320px 下每列只剩 ~100px，装不下 10 个字符的金额：
     改成「标签左 / 数字右」的行式清单，顺序仍是 总资产 → 负债 → 净资产，
     恒等式读起来不断。 */
  .household__cols {
    grid-template-columns: 1fr;
    gap: var(--space-2, 8px);
  }

  .household__col {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 0;
  }

  .household__col + .household__col {
    border-left: none;
  }

  .household__label {
    margin-bottom: 0;
  }

  /* 行式清单：整行是入口，补一点纵向 padding 把命中区从 21px 抬到 ~37px。
     只加 padding、不加负 margin——三行只隔 8px gap，负 margin 会让相邻两行
     的命中区互相盖住。 */
  .household__col--link {
    padding: 8px 0;
  }
}
</style>
