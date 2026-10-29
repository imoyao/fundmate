<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getPositions } from "@/api/positions";
import { getSymbolXirr } from "@/api/performance";
import type { Position } from "@/api/types";
// 计算口径单独成模块，由 __tests__/productPositionMetrics.spec.ts 钉住：
// 尤其「盈亏率必须是百分数」这条——旧实现给了比值却拼上 "%"，小了 100 倍
import { sumUp } from "./productPositionMetrics";
import { groupByLedger } from "./positionSection/positionGrouping";
import PositionChannelTable from "./positionSection/PositionChannelTable.vue";
import PositionMetricGrid from "./positionSection/PositionMetricGrid.vue";
import PositionAdvisorAdjusts from "./positionSection/PositionAdvisorAdjusts.vue";
import type { ChannelGroup } from "./positionSection/positionTypes";

/**
 * 详情页「我的持仓」区块（#1966 · 设计 §4.2；#2005 重做信息密度；持有年化由 #1972 补齐）。
 *
 * 数据来自 `GET /api/positions/?symbol=&market=`，过滤在**后端下推到 SQL**
 * （#1966 同期新增的过滤参数），不在前端拉全量再筛——后者是数据策略硬约束 §6 明令禁止的。
 *
 * ## #2005 改了什么、为什么
 *
 * 旧版按渠道分块，每块自带「渠道名 + 四列表头 + **产品名**」三层壳。产品名在这里是
 * **定义上冗余**的——用户正站在这个产品的详情页上，名字不需要再出现一次；列头也
 * 不需要每组重复一遍。两层壳叠起来，1 行数据要吃掉 3 行的高度，这才是「占区域太大」
 * 的根因，**不是字段多**。删掉这两层后，腾出的空间比旧版整个区块还大，于是顺势
 * 补上后端一直给得出、前端却没展示的口径。
 *
 * 故本组件分两种形态，**都以「账户」为行标签、不再以产品为行标签**：
 * - **单账户**（常见情形）：不进表格，走指标网格——表格的表头 + 单行 + 与该行完全重复的
 *   「合计」行是纯开销，网格用两行就放得下同样的信息；
 * - **多账户**：紧凑表格，一个表头管全部行。
 *
 * ## 口径
 *
 * - 盈亏率 = 盈亏 ÷ 持仓成本（成本单价 × 持有数量），与持仓列表页同一口径；
 * - 持仓天数用后端派生字段 `holding_days`（#862），多笔取**最短**（最早建仓那笔），
 *   不做平均——「拿了多久」的自然是第一笔；
 * - 持有年化 = 跨账户按 symbol 汇总现金流的 XIRR（`scope=symbol`，#1972），与上面的
 *   持仓行**同一套 symbol 归一口径**（后端 `services/symbol_scope.py` 收口），
 *   所以「列表有几行、年化就算几个账户」不会打架；
 * - 涨跌颜色交给 `RiseFallText` / `MoneyDisplay` 的 autoColor（涨红跌绿语义变量），
 *   此处不自己拼颜色。
 *
 * ## 当日盈亏（#2007）
 *
 * 它是「持有盈亏」之外的第二个时间窗口口径：(现价 − 上一确认价) × 数量。基准价由后端
 * `position_price_job` 与 `current_price` **同批**写入 `positions.prev_close`
 * ——同批这个前提不成立时，相减出来的是两段行情之差、不是当日涨跌。
 * 三处刻意为之：
 *
 * - **无基准显示「—」而不是 0**：0 是「今天没涨没跌」这个**结论**，我们没有依据下它；
 * - **基准日明示**（「截至 10-09」）：场外基金是 T-1 净值、场内是最近收盘日，
 *   这个「当日」并不总是今天，不说清就等于让用户自己误会；
 * - **率是百分数**（与后端 `pnl_rate` 一致），由 `productPositionMetrics` 统一收口，
 *   展示层不做单位换算（那条 100× 教训见该模块头注释）。
 *
 * ## 为什么不做抽屉 / 逐条展开
 *
 * 后端能诚实供给的口径仍是一张网格放得下的量（分红方式与卖出费率不在 `positions` 表，
 * 见 #2007 卡的取证结论）。抽屉是为「放不下」准备的方案，而持仓是用户自己的钱、
 * 是打开「我的」产品页的唯一理由，不该多一次点击才能看到。
 *
 * ## #980 拆分（本文件职责）
 *
 * 这里只做**取数 + 聚合 + 形态分流**，两种形态的渲染分别落在
 * `positionSection/PositionMetricGrid.vue` 与 `positionSection/PositionChannelTable.vue`；
 * 账户名（两种形态共用）落在 `positionSection/PositionAccountLink.vue`。
 * 纯搬运，类名、文案、样式声明一律不变。
 */

const props = defineProps<{
  symbol: string;
  /** 市场消歧：同码跨市场时由详情页 resolve 结果带下来 */
  market?: string;
  /**
   * 资产类型。**价格类字段的精度由它决定**（基金/ETF/货币基金 4 位，其余 2 位）——
   * 不传就没有判断依据，只能写死位数，于是股票成本也会被显示成 4 位。
   */
  assetType?: string;
}>();

const loading = ref(false);
const rows = ref<Position[]>([]);
/** 产品级持有年化（XIRR，小数）；`null` = 无数据 / 拉取失败，模板显示 `—` */
const xirr = ref<number | null>(null);

const groups = computed<ChannelGroup[]>(() => groupByLedger(rows.value));

/** 只有一个渠道时不渲染合计行——它与那一行完全相同，是纯冗余 */
const single = computed<ChannelGroup | null>(() =>
  groups.value.length === 1 ? groups.value[0] : null
);

const totals = computed(() => sumUp(rows.value));

const hasRows = computed(() => !!rows.value.length);

/**
 * 投顾组合持仓 id（#2740）：有它才挂「主理人最近调仓」。
 *
 * 组合持仓按 `symbol` 查、跨账户可能有多行，但调仓明细是**组合级**的（与哪个账户无关），
 * 取任意一行即可；这里取第一行，稳定且不额外发请求。
 */
const portfolioPositionId = computed<number | null>(() => {
  if (props.assetType !== "portfolio") return null;
  return rows.value[0]?.id ?? null;
});

async function load() {
  if (!props.symbol) return;
  loading.value = true;
  xirr.value = null;
  try {
    const res = await getPositions({
      symbol: props.symbol,
      market: props.market,
      per_page: 100
    });
    rows.value = res.data ?? [];
  } catch {
    // 拉不到就当作「暂无持仓」：这是详情页的附属区块，不该为它显示错误态，
    // 更不该显示假数据。rows 置空后，正文转为「当前产品暂无持仓记录」空态。
    rows.value = [];
  } finally {
    loading.value = false;
  }
  // 持有年化跟着同一次刷新走；没有持仓行时不发请求（正文只剩空态提示）
  if (rows.value.length) void loadXirr();
}

async function loadXirr() {
  try {
    const res = await getSymbolXirr(props.symbol);
    // cashflow_count = 0 表示该产品无成交：后端给的是全 0 结构，按「无数据」显示 `—`
    const data = res.data;
    xirr.value = data && data.cashflow_count > 0 ? (data.xirr ?? null) : null;
  } catch {
    // 持有年化是锦上添花的指标，拉不到就降级 `—`，不惊动整块持仓列表
    xirr.value = null;
  }
}

watch(() => [props.symbol, props.market], load, { immediate: true });
</script>

<template>
  <!-- 外层只是「持仓 + 主理人调仓」两张卡的排版壳：详情页正文靠 `.product-detail__main`
       的 flex gap 控制节奏，本组件若返回多根就继承不到 `id="nav-position"`（导航胶囊会失去锚点），
       故保留单根、由本壳承担间距。 -->
  <div class="product-position-shell">
    <!-- SectionHeader 必须是 CardBlock 的**直接子节点**：CardBlock 只有一个匿名
       <slot />，没有 header 具名插槽，写 <template #header> 会被 Vue 静默丢弃——
       本组件曾这么写，结果标题、info 口径说明与持有年化整段不渲染。 -->
    <CardBlock class="product-position">
      <SectionHeader
        title="我的持仓"
        info="按渠道（账户）分列；盈亏率 = 盈亏 ÷ 持仓成本。未归档持仓单独一组。持有年化为跨账户合并现金流后的 XIRR。"
        info-label="关于持仓口径"
      >
        <template #action>
          <!-- 持有年化挂在标题右侧，不占表格列（#1972）。区块已由 detail.vue 的
             has_position 门槛保证「确有持仓」才挂载，故不再判 rows.length。 -->
          <p class="product-position__xirr">
            <span class="product-position__xirr-label">持有年化</span>
            <RiseFallText
              v-if="xirr !== null"
              :value="xirr"
              size="sm"
              :precision="2"
            />
            <span v-else class="product-position__xirr-empty">—</span>
          </p>
        </template>
      </SectionHeader>

      <div v-loading="loading" class="product-position__body">
        <!-- 拉取中 / 拉不到时 hasRows 为假：给一句明确的空态，而不是让整块凭空消失。
           原先 CardBlock 挂 v-if="hasRows"，连带让这里的 v-loading 永远不触发——
           加载中 hasRows 必为假、整块不渲染，遮罩自然无处可挂，故改为空态接管。 -->
        <p v-if="!loading && !hasRows" class="product-position__hint">
          当前产品暂无持仓记录。
        </p>

        <!-- 单账户：不进表格、不重复表头，走紧凑指标网格 -->
        <PositionMetricGrid
          v-else-if="single"
          :group="single"
          :asset-type="props.assetType"
        />

        <!-- 多账户：一个表头管全部行；产品列与每组表头都已去掉 -->
        <PositionChannelTable v-else :groups="groups" :totals="totals" />
      </div>
    </CardBlock>

    <!-- 主理人最近调仓（#2740 / D70）：仅投顾组合、且确有持仓时挂载。
       文案与降级口径见该组件头注释——重点是别让人误读成「我自己的调仓」。 -->
    <PositionAdvisorAdjusts
      v-if="portfolioPositionId !== null"
      :position-id="portfolioPositionId"
    />
  </div>
</template>

<style lang="scss" scoped>
/* 排版壳：与详情页正文同一套节奏（`.product-detail__main` 的 gap = --space-5） */
.product-position-shell {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  min-width: 0;
}

.product-position {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
}

/* 标题与正文的间距由 SectionHeader 自带的 margin-bottom 给，
   此处不再写 :deep(.card-block__header) —— CardBlock 是纯容器
   （<section class="card-block"><slot /></section>），根本没有这个元素。 */

.product-position__body {
  font-size: var(--text-label);
}

/* 产品级持有年化（#1972）：挂在区块标题右侧，不占表格列 */
.product-position__xirr {
  display: flex;
  gap: var(--space-2);
  align-items: baseline;
  margin: 0;
  font-variant-numeric: tabular-nums;
}

.product-position__xirr-label {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

.product-position__xirr-empty {
  color: var(--text-tertiary-ink);
}

/* 空态提示（拉取失败 / 确无记录） */
.product-position__hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}
</style>
