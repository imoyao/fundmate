<!--
  TodayPnlCard · 首页「最新收益」卡（2026-11-03 用户拍板的卡面，11-04 改版）

  信息层级四层，从上到下：
    1. 最新收益（hero）+ 当日涨幅   ← 唯一的强色数字
    2. 投资类资产（次级）+ 占家庭总资产（把两个刻度接起来）
    3. 场内权益 / 场外基金两列（分项盈亏 + 收益率 + 市值 + 占投资比）
    4. 家庭口径 · 存量（总资产 / 总负债 / 净资产 + 负债率 + 杠杆结构条）

  为什么第 4 层必须按 总资产 → 负债 → 净资产 排：
  这三个数只有排成 `A = L + E` 才自洽。11-03 版底注只写「净资产 · 总负债」，
  读者拼不出总资产（3.40M），也看不出 411,679 只是家庭的 12%——
  缺的那一项正是把两层刻度连起来的锚点（数据一直在 `/api/summary/` 里）。

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

  入口（2026-11-04）：家庭三列各自可点，去三个**不同**的既有页面——
  总资产→资产总览、总负债→盘点页负债档、净资产→复盘页净值走势。
  于是这张卡多了两处必须是「一个手势一个含义」的地方：
    · 长按 = 窥视金额（在列上长按松手，不能顺势跳页）→ `peekFired` 吃掉那次 click；
    · 触屏长按 = 系统菜单会顶掉窥视 → 遮罩中拦掉 contextmenu。
  这两条一旦漏掉，手机上「想看数字」会变成「被带走」。
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
          <div class="today-pnl__col-foot">
            <MoneyDisplay
              :value="item.market_value"
              size="sm"
              :show-sign="false"
              :auto-color="false"
              custom-color="var(--text-tertiary-ink)"
            />
            <span
              v-if="item.share_of_invested != null"
              class="today-pnl__col-share"
              >占投资 {{ pct1(item.share_of_invested) }}</span
            >
          </div>
        </div>
      </div>

      <p
        v-else
        class="today-pnl__empty"
        :style="{ color: 'var(--text-tertiary-ink)' }"
      >
        还没有可估值的股票或基金持仓
      </p>

      <!-- 家庭口径（存量）：与上面「当日收益（流量）」是两层刻度，故整块独立成带、
           上方用结构分隔线切开。三个数按 总资产 = 总负债 + 净资产 排列，
           顺序本身就是那条恒等式——原先只写「净资产 · 总负债」，读者拼不出总资产。 -->
      <div
        v-if="
          totalAssets != null || netAssets != null || totalLiabilities != null
        "
        class="today-pnl__household"
      >
        <div class="today-pnl__household-head">
          <span class="today-pnl__household-title">家庭口径 · 存量</span>
          <!-- 负债不染涨跌色：红色在这套体系里表示「涨=好」，而负债增加是坏事，
               语义会反转。用比率表达杠杆水平，绝对值保持中性。 -->
          <span
            v-if="liabilityRatioText"
            class="today-pnl__ratio-chip"
            :class="{ 'is-insolvent': isInsolvent }"
          >
            负债率 {{ liabilityRatioText }}
          </span>
        </div>

        <!-- 三列各自是一个入口（2026-11-04 用户拍板）：它们是同一张资产负债表的
             三个切面，但「往下看」的去处不同——
               总资产 → 资产总览（存量结构）· 总负债 → 盘点页负债档（逐笔）
               净资产 → 复盘页净值走势（时间）
             刻意不把三列都指向同一页：同一个链接复制三次，点击只证明「能点」，
             不带来任何新信息。用 `<a href>` 而不是 `<div @click>`，中键新标签页、
             键盘 Enter、读屏「链接」角色都白拿。 -->
        <div class="today-pnl__household-cols">
          <a
            v-for="col in householdCols"
            :key="col.key"
            class="today-pnl__household-col today-pnl__household-col--link"
            :class="{ 'today-pnl__household-col--net': col.strong }"
            :href="col.to"
            :title="col.title"
            @click="onColClick($event, col.to)"
            @contextmenu="onColContextMenu"
          >
            <p class="today-pnl__label">
              <span>{{ col.label }}</span>
              <!-- 箭头默认透明：三个常驻箭头会把「读数区」读成「按钮排」 -->
              <IconifyIconOffline
                icon="ep:arrow-right"
                class="today-pnl__col-go"
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
             纯视觉冗余（不计入读屏），文字结论由上面的 ratio-chip 承担。 -->
        <div
          v-if="debtShare != null && leverageLegend"
          class="today-pnl__leverage"
          aria-hidden="true"
        >
          <div class="today-pnl__leverage-track">
            <span
              class="today-pnl__leverage-debt"
              :class="{ 'is-insolvent': isInsolvent }"
              :style="{ width: debtShare + '%' }"
            />
          </div>
          <div class="today-pnl__leverage-legend">
            <span>负债 {{ leverageLegend.debt }}</span>
            <span>{{ leverageLegend.equity }}</span>
          </div>
        </div>
      </div>
    </div>
  </CardBlock>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import ValuationSourceBadge from "@/components/ValuationSourceBadge/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";
import { useTweenNumber } from "@/composables/useTweenNumber";
import { usePrivacyMode } from "@/composables/usePrivacyMode";
import type { TodayPnlClass, TodayPnlData } from "@/api/summary";

defineOptions({ name: "TodayPnlCard" });

const props = defineProps<{
  data: TodayPnlData | null;
  /** 口径 + 时间（盘中 / 收盘估值 / 已确认 / 最近交易日），由 composable 算 */
  subtitle: string;
  loading: boolean;
  error: boolean;
  /** 家庭总资产（底注三列之一；后端 `total_assets_cny` 直出） */
  totalAssets: number | null;
  /** 家庭净资产（底注；与卡内「投资类资产」是两层刻度）——直出字段，前端不二次算 */
  netAssets: number | null;
  /** 家庭总负债（同上） */
  totalLiabilities: number | null;
  /** 负债率（%，后端 `ratio_pct` 直出）；null = 总资产为 0，此时不显示比率 */
  liabilityRatio: number | null;
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

/**
 * 结构占比统一 1 位小数（51.8% / 12.1%）。
 *
 * 与收益率（2 位）刻意不同档：收益率是「今天赚了多少」的精确刻度，两位有意义；
 * 结构占比回答的是「大致占多少」，第二位小数只是噪音，还会让三列数字看起来更吵。
 */
const pct1 = (value: number) => `${value.toFixed(1)}%`;

// ── 隐私模式（只藏金额，保留百分比）──
const { masked, peeking, startPeek, endPeek } = usePrivacyMode();

/**
 * 长按窥视与「三列可点击」是同一个手势的两个含义：按住 = 看数字，短按 = 跳走。
 * 不处理的话，长按松手那一下会先亮出真值、再顺势把用户带走——「看一眼」的代价
 * 变成换页。故记一次「这次按压确实揭开过」，由 `onColClick` 吃掉紧随的 click。
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

/** 资不抵债（负债率 ≥ 100%）：唯一允许把负债率染成危险色的情形 */
const isInsolvent = computed(() => (props.liabilityRatio ?? 0) >= 100);

/** 负债率文案（null 时不渲染整枚徽标，而不是渲染成 0.0%） */
const liabilityRatioText = computed(() =>
  props.liabilityRatio == null ? null : pct1(props.liabilityRatio)
);

/**
 * 结构条下方的图例。两段结构只在「净资产为正」时成立：
 * 负债率 ≥ 100% 时剩余部分是负的，再写「净资产 -12.3%」会被读成「还有一截」，
 * 故换成一句结论——条已满，原因是负债吃穿了资产。
 */
const leverageLegend = computed(() => {
  const ratio = props.liabilityRatio;
  if (ratio == null) return null;
  return {
    debt: pct1(ratio),
    equity: isInsolvent.value ? "已资不抵债" : `净资产 ${pct1(100 - ratio)}`
  };
});

/**
 * 家庭口径三列 = 三个入口，`to` 全部指向**既有**路由（没有新增路径）：
 *  - 总资产 → `/panorama`               资产总览：大类构成 + 桑基流向
 *  - 总负债 → `/inventory?tab=liability` 全面盘点：负债档，逐笔可看可改
 *  - 净资产 → `/analysis`               投资复盘：资产净值走势（每日快照）
 *
 * 净资产去「复盘」而不是「总览」，是因为总览页只拿快照算环比同比，
 * 真正的净值时间序列在复盘页——「这个数最近怎么走」只有那里答得了。
 */
const householdCols = computed(() => [
  {
    key: "assets",
    label: "家庭总资产",
    value: props.totalAssets,
    color: "var(--text-primary)",
    to: "/panorama",
    title: "查看资产构成",
    strong: false
  },
  {
    key: "liabilities",
    label: "家庭总负债",
    value: props.totalLiabilities,
    color: "var(--text-secondary)",
    to: "/inventory?tab=liability",
    title: "查看负债明细",
    strong: false
  },
  {
    key: "net",
    label: "家庭净资产",
    value: props.netAssets,
    color: "var(--text-primary)",
    to: "/analysis",
    title: "查看资产净值走势",
    strong: true
  }
]);

const router = useRouter();

/**
 * 三列点击自己接管导航，而不是让 `<a href>` 直接跳：
 * 1. history 模式下 href 直跳等于整页刷新，丢掉 SPA 状态；
 * 2. 要能吃掉长按窥视之后的误触（见 `peekFired`）。
 * 修饰键 / 中键一律放行，交给浏览器开新标签页——那是 `<a>` 的本分。
 */
function onColClick(e: MouseEvent, to: string) {
  if (peekFired) {
    peekFired = false;
    e.preventDefault();
    return;
  }
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0)
    return;
  e.preventDefault();
  router.push(to);
}

/**
 * 触屏长按链接会弹系统菜单（新标签打开 / 拷贝链接），而这一带的长按已经被
 * 「窥视金额」占了——菜单一弹，窥视就断。只在**粗指针 + 遮罩中**拦：
 * 桌面右键照旧（拷贝链接、新标签页打开是正当操作），未开遮罩时也不拦。
 */
function onColContextMenu(e: MouseEvent) {
  if (masked.value && window.matchMedia("(hover: none)").matches) {
    e.preventDefault();
  }
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

/* 投资类资产的占比：紧贴数字下方、与标签同色阶，读作「这个数的一个注解」 */
.today-pnl__invested-ratio {
  margin: 5px 0 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 分项脚注：市值在左、占比在右。原先市值孤零零挂在列左，右半列是空的；
   占比填进这个空位，同时回答「股票和基金谁占大头」。 */
.today-pnl__col-foot {
  display: flex;
  gap: var(--space-2, 8px);
  align-items: baseline;
  justify-content: space-between;
}

.today-pnl__col-share {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  white-space: nowrap;
}

/* 遮罩态的提示：只在金额被藏起来时出现，告诉用户「不是坏了，是藏了，长按能看」 */
.today-pnl__peek-hint {
  color: var(--text-tertiary-ink);
}

/* ===== 家庭口径（存量）带 =====
   上方 --border-light 是**结构断点**（流量 → 存量），与卡片外框同重；
   三列之间用 --border-subtle 竖线（同级并列，降一档），两级线重不可互换。 */
.today-pnl__household {
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 12px);
  padding-top: var(--space-compact, 16px);
  border-top: 1px solid var(--border-light);
}

.today-pnl__household-head {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.today-pnl__household-title {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
  letter-spacing: 0.4px;
}

/* 负债率徽标：负债的「特殊显示」落点。
   绝对值保持中性色——负债不是亏损，用涨跌色会语义反转（红=涨=好 vs 负债增=坏）；
   只有资不抵债（≥100%）才升级为危险色，那时它表达的是「风险」而非「符号」。 */
.today-pnl__ratio-chip {
  padding: 1px 8px;
  font-size: var(--text-label);
  color: var(--text-secondary);
  white-space: nowrap;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
}

.today-pnl__ratio-chip.is-insolvent {
  color: var(--color-danger-ink);
  background-color: var(--color-danger-10);
  border-color: var(--color-danger-20);
}

.today-pnl__household-cols {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.today-pnl__household-col {
  min-width: 0;
  padding: 0 var(--space-compact, 16px);
}

.today-pnl__household-col:first-child {
  padding-left: 0;
}

.today-pnl__household-col:last-child {
  padding-right: 0;
}

.today-pnl__household-col + .today-pnl__household-col {
  border-left: 1px solid var(--border-subtle);
}

/* 净资产是这一带的结论：只加字重，不加字号/颜色——否则三列会打成三个主角 */
.today-pnl__household-col--net :deep(.number) {
  font-weight: 600;
}

/* ===== 三列 = 入口（2026-11-04） =====
   悬停只铺一层 --bg-soft，不动字号/颜色/字重：这一带是「读数」，数字在悬停时
   跳一下会让人以为数值变了。命中区就交给列自身——桌面端一列 44px 高、宽度撑满
   1/3 卡宽，**不再**用「padding + 负 margin」抬命中区：那招在窄屏（三行只隔
   8px gap）会让相邻两行的命中区互相盖住，点「总负债」落到「总资产」上。 */
.today-pnl__household-col--link {
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
.today-pnl__col-go {
  width: 12px;
  height: 12px;
  color: var(--text-tertiary-ink);
  opacity: 0;
  transform: translateX(-2px);
  transition:
    opacity 0.15s ease,
    transform 0.15s ease;
}

.today-pnl__household-col--link:hover .today-pnl__col-go,
.today-pnl__household-col--link:focus-visible .today-pnl__col-go {
  opacity: 0.7;
  transform: translateX(0);
}

/* 触屏没有 hover 可「揭示」：箭头常驻一档淡色，否则用户不知道这几列能点 */
@media (hover: none) {
  .today-pnl__col-go {
    opacity: 0.45;
    transform: translateX(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .today-pnl__household-col--link,
  .today-pnl__col-go {
    transition: none;
  }
}

/* ===== 杠杆结构条 =====
   把「负债 1,760,000」变成「水位 51.8%」。负债段中性色，剩余部分是净资产；
   资不抵债时整条转危险色（此时没有「净资产段」可言，不能画成两段）。 */
.today-pnl__leverage {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.today-pnl__leverage-track {
  height: 4px;
  overflow: hidden;
  background-color: var(--border-subtle);
  border-radius: 2px;
}

.today-pnl__leverage-debt {
  display: block;
  height: 100%;
  background-color: var(--color-neutral);
  border-radius: 2px 0 0 2px;
}

.today-pnl__leverage-debt.is-insolvent {
  background-color: var(--color-danger);
  border-radius: 2px;
}

.today-pnl__leverage-legend {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  font-size: var(--text-label);
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

  /* 三列在 320px 下每列只剩 ~100px，装不下 10 个字符的金额：
     改成「标签左 / 数字右」的行式清单，顺序仍是 总资产 → 负债 → 净资产，
     恒等式读起来不断。 */
  .today-pnl__household-cols {
    grid-template-columns: 1fr;
    gap: var(--space-2, 8px);
  }

  .today-pnl__household-col {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 0;
  }

  .today-pnl__household-col + .today-pnl__household-col {
    border-left: none;
  }

  .today-pnl__household-col .today-pnl__label {
    margin-bottom: 0;
  }

  /* 行式清单：整行是入口，补一点纵向 padding 把命中区从 21px 抬到 ~37px。
     只加 padding、不加负 margin——三行只隔 8px gap，负 margin 会让相邻两行
     的命中区互相盖住。 */
  .today-pnl__household-col--link {
    padding: 8px 0;
  }
}
</style>
