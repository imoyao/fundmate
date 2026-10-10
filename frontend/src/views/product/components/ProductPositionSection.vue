<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import { getPositions } from "@/api/positions";
import { getSymbolXirr } from "@/api/performance";
import type { Position } from "@/api/types";
import { formatQuantity } from "@/utils/format";
// 计算口径单独成模块，由 __tests__/productPositionMetrics.spec.ts 钉住：
// 尤其「盈亏率必须是百分数」这条——旧实现给了比值却拼上 "%"，小了 100 倍
import {
  daysText,
  pnlRate,
  sumUp,
  type ChannelTotals
} from "./productPositionMetrics";

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
 * ## 为什么不做抽屉 / 逐条展开
 *
 * 后端能诚实供给的口径只有 7 个（当日盈亏要 `prev_close`、分红方式与卖出费率不在
 * `positions` 表，见 #2007），一张网格放得下。抽屉是为「放不下」准备的方案，
 * 而持仓是用户自己的钱、是打开「我的」产品页的唯一理由，不该多一次点击才能看到。
 */

const props = defineProps<{
  symbol: string;
  /** 市场消歧：同码跨市场时由详情页 resolve 结果带下来 */
  market?: string;
}>();

const loading = ref(false);
const rows = ref<Position[]>([]);
/** 产品级持有年化（XIRR，小数）；`null` = 无数据 / 拉取失败，模板显示 `—` */
const xirr = ref<number | null>(null);

interface ChannelGroup extends ChannelTotals {
  key: string;
  name: string;
  /** 未归档持仓为 null：**没有落点**，渲染时不得给它套跳转 */
  ledgerId: number | null;
  rows: Position[];
}

const groups = computed<ChannelGroup[]>(() => {
  const map = new Map<number | null, Position[]>();
  for (const row of rows.value) {
    const ledgerId = row.ledger_id ?? null;
    const bucket = map.get(ledgerId);
    if (bucket) {
      bucket.push(row);
    } else {
      map.set(ledgerId, [row]);
    }
  }

  return Array.from(map.entries()).map(([ledgerId, groupRows]) => ({
    key: String(ledgerId ?? "ungrouped"),
    name:
      groupRows[0]?.account_name ||
      (ledgerId ? `账户 #${ledgerId}` : "未归档持仓"),
    ledgerId,
    rows: groupRows,
    ...sumUp(groupRows)
  }));
});

/** 只有一个渠道时不渲染合计行——它与那一行完全相同，是纯冗余 */
const single = computed<ChannelGroup | null>(() =>
  groups.value.length === 1 ? groups.value[0] : null
);

const totals = computed(() => sumUp(rows.value));

const hasRows = computed(() => !!rows.value.length);

const accountPath = (ledgerId: number | null) =>
  ledgerId ? `/asset/ledgers/${ledgerId}` : "";

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
    xirr.value = data && data.cashflow_count > 0 ? data.xirr : null;
  } catch {
    // 持有年化是锦上添花的指标，拉不到就降级 `—`，不惊动整块持仓列表
    xirr.value = null;
  }
}

watch(() => [props.symbol, props.market], load, { immediate: true });
</script>

<template>
  <CardBlock class="product-position">
    <template #header>
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
    </template>

    <div v-loading="loading" class="product-position__body">
      <!-- 拉取中 / 拉不到时 hasRows 为假：给一句明确的空态，而不是让整块凭空消失。
           原先 CardBlock 挂 v-if="hasRows"，连带让这里的 v-loading 永远不触发——
           加载中 hasRows 必为假、整块不渲染，遮罩自然无处可挂，故改为空态接管。 -->
      <p v-if="!loading && !hasRows" class="product-position__hint">
        当前产品暂无持仓记录。
      </p>

      <!-- 单账户：不进表格、不重复表头，走紧凑指标网格 -->
      <template v-else-if="single">
        <div class="product-position__channel">
          <router-link
            v-if="single.ledgerId"
            class="product-position__account"
            :to="accountPath(single.ledgerId)"
          >
            {{ single.name }}
          </router-link>
          <span
            v-else
            class="product-position__account product-position__account--plain"
          >
            {{ single.name }}
          </span>
        </div>

        <div class="product-position__grid">
          <!-- 盈亏两项是用户打开这一页真正要看的，字号提一档；其余保持同级 -->
          <div class="metric metric--hero">
            <span class="metric__label">持有盈亏</span>
            <span class="metric__value">
              <MoneyDisplay :value="single.pnl" :precision="2" size="lg" />
            </span>
          </div>
          <div class="metric metric--hero">
            <span class="metric__label">持有盈亏率</span>
            <span class="metric__value">
              <RiseFallText :value="pnlRate(single)" suffix="%" />
            </span>
          </div>
          <div class="metric">
            <span class="metric__label">持有金额</span>
            <span class="metric__value">
              <MoneyDisplay
                :value="single.marketValue"
                :auto-color="false"
                :show-sign="false"
              />
            </span>
          </div>
          <div class="metric">
            <span class="metric__label">持有份额</span>
            <span class="metric__value">{{
              formatQuantity(single.quantity)
            }}</span>
          </div>
          <div class="metric">
            <span class="metric__label">持仓成本</span>
            <span class="metric__value">
              <MoneyDisplay
                :value="single.cost"
                :auto-color="false"
                :show-sign="false"
              />
            </span>
          </div>
          <div class="metric">
            <span class="metric__label">单位成本</span>
            <span class="metric__value">
              <MoneyDisplay
                :value="single.avgPrice"
                :auto-color="false"
                :show-sign="false"
                :precision="4"
              />
            </span>
          </div>
          <div class="metric">
            <span class="metric__label">持仓天数</span>
            <span class="metric__value">{{
              daysText(single.holdingDays)
            }}</span>
          </div>
        </div>
      </template>

      <!-- 多账户：一个表头管全部行；产品列与每组表头都已去掉 -->
      <div v-else class="product-position__scroll">
        <table class="product-position__table">
          <thead>
            <tr>
              <th class="is-account">账户</th>
              <th>持有份额</th>
              <th>持仓成本</th>
              <th>持有金额</th>
              <th>持有盈亏</th>
              <th>盈亏率</th>
              <th>持仓天数</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in groups" :key="g.key">
              <td class="is-account">
                <router-link
                  v-if="g.ledgerId"
                  class="product-position__account"
                  :to="accountPath(g.ledgerId)"
                >
                  {{ g.name }}
                </router-link>
                <span
                  v-else
                  class="product-position__account product-position__account--plain"
                >
                  {{ g.name }}
                </span>
              </td>
              <td>{{ formatQuantity(g.quantity) }}</td>
              <td>
                <MoneyDisplay
                  :value="g.cost"
                  :auto-color="false"
                  :show-sign="false"
                />
              </td>
              <td>
                <MoneyDisplay
                  :value="g.marketValue"
                  :auto-color="false"
                  :show-sign="false"
                />
              </td>
              <td>
                <MoneyDisplay :value="g.pnl" :precision="2" />
              </td>
              <td>
                <RiseFallText :value="pnlRate(g)" suffix="%" />
              </td>
              <td>{{ daysText(g.holdingDays) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td class="is-account">合计</td>
              <td />
              <td>
                <MoneyDisplay
                  :value="totals.cost"
                  :auto-color="false"
                  :show-sign="false"
                />
              </td>
              <td>
                <MoneyDisplay
                  :value="totals.marketValue"
                  :auto-color="false"
                  :show-sign="false"
                />
              </td>
              <td>
                <MoneyDisplay :value="totals.pnl" :precision="2" />
              </td>
              <td>
                <RiseFallText :value="pnlRate(totals)" suffix="%" />
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  </CardBlock>
</template>

<style lang="scss" scoped>
@use "@/style/breakpoints" as bp;

.product-position {
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
}

.product-position :deep(.card-block__header) {
  padding-bottom: var(--space-compact);
  margin-bottom: var(--space-compact);
  border-bottom: 1px solid var(--border-light);
}

.product-position__body {
  font-size: 13px;
}

/* 账户名：可点击时给链接态，未归档持仓只读——那里没有落点，链过去是坏的 */
.product-position__account {
  font-weight: 500;
  color: var(--text-primary);
  text-decoration: none;
  border-bottom: 1px solid transparent;
}

.product-position__account:not(.product-position__account--plain):hover {
  color: var(--color-primary-ink);
  border-bottom-color: currentColor;
}

.product-position__account--plain {
  color: var(--text-primary);
  cursor: default;
}

/* ===== 单账户：指标网格 ===== */
.product-position__channel {
  display: flex;
  gap: var(--space-1);
  align-items: center;
  margin-bottom: var(--space-compact);
  font-size: 13px;
}

.product-position__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3) var(--space-compact);
}

/* 断点走单一来源（#1571，`_breakpoints.scss`）：md = 48rem = 768px，
   与模板里的 Tailwind `md:` 前缀同阈值同语义，禁止另写裸 @media。 */
@include bp.above("md") {
  .product-position__grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.metric__label {
  font-size: 12px;
  line-height: 1.3;
  color: var(--text-tertiary-ink);
}

.metric__value {
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  line-height: 1.4;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

/* 盈亏两项是这一页的核心，字号提一档；不改颜色，颜色仍由 RiseFallText / MoneyDisplay 按语义变量给 */
.metric--hero .metric__value {
  font-size: 17px;
}

/* ===== 多账户：紧凑表格 ===== */
.product-position__scroll {
  overflow-x: auto;
}

.product-position__table {
  width: 100%;
  font-size: 13px;
  white-space: nowrap;
  border-collapse: collapse;
}

.product-position__table th,
.product-position__table td {
  padding: 6px var(--space-2);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.product-position__table th {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-tertiary-ink);
  border-bottom: 1px solid var(--border-light);
}

.product-position__table tbody tr + tr td {
  border-top: 1px solid var(--border-subtle);
}

.product-position__table .is-account {
  padding-left: 0;
  text-align: left;
}

.product-position__table tfoot td {
  padding-top: var(--space-2);
  font-weight: 500;
  color: var(--text-primary);
  border-top: 1px solid var(--border-light);
}

.product-position__table tfoot td:first-child {
  font-weight: 400;
  color: var(--text-tertiary-ink);
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
  font-size: 12px;
  color: var(--text-tertiary-ink);
}

.product-position__xirr-empty {
  color: var(--text-tertiary-ink);
}

/* 空态提示（拉取失败 / 确无记录） */
.product-position__hint {
  margin: 0;
  font-size: 13px;
  color: var(--text-tertiary-ink);
}
</style>
