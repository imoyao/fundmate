<!--
  LedgerCashLikeCard · 账户「类现金」区块（#2155 / CNB #479）

  背景（真机：账户「同花顺——银河」id=12，stock）：
  - 持仓总市值 296,042 元
  - 孤儿货基流水净额（账外）476,951 元

  后者不建持仓、不进 `total_market_value`，页面上任何地方都看不到。
  此前它是靠「把投资资产算成负数」的错误方式挤进环形图的（#1606 修掉）。

  本卡片的职责是**并列展示 + 解释去向**，不是补一笔漏账：
  - 四项分列（持仓内 / 账外孤儿 / 账户现金 / 合计），把 `cash_like_amount`
    这个汇总数拆开——卡面明确要求「不要合并成一个数，否则又回到口径混淆」；
  - 账外两项各带一句「不建持仓，故不在环形图内」，回答「这笔钱是什么、为什么不在持仓里」；
  - 配可展开的逐产品明细（只给一个 476,951，用户问的还是同一个问题）。

  ⚠️ 本卡片**刻意不进环形图**。环形图两片是「持仓市值的划分」（合计 = 总市值），
  把账外类现金并进去就会重演 `总市值 − cash_like_amount = -180,909` 的负数 bug。
  两者口径解耦（decisions.md D59），故页面上必须有一句话说明「环形图合计 ≠ 总资产」。

  #2739 页内导航锚点：本组件是**多根**（`<template v-if>` 下两个根），
  父级挂 `id` 会被 Vue 丢弃并告警，故由 `anchorId` prop 显式下发，
  落在块内标题行（SectionHeader 根节点）上——与本页其余锚点同一手法
  （锚点 = 区块标题行的顶边，跳转后标题正好停在吸顶导航下方）。
  锚点挂在**块内**而非块外：本块整块不渲染时锚点随之消失，
  导航项被 usePageNav 的 DOM 存在性过滤收走，不留死链
  （类现金为 0 的普通基金账户占绝大多数，不挂准就会留下一个点不动的导航项）。
-->
<template>
  <template v-if="visible">
    <SectionHeader
      :id="anchorId"
      title="类现金"
      info="类现金 = 随时可变现、不承担净值波动的资金。含四部分：持仓内货基、账外孤儿货基/逆回购流水、账户现金。"
    />
    <CardBlock class="mb-6">
      <!-- 四项并列。合计放最左并 featured：它是这一区块最该被记住的数。 -->
      <MetricGrid>
        <MetricCard
          title="类现金合计"
          :value="formatAmount(total)"
          unit="元"
          featured
          caption="下列四项之和"
        />
        <MetricCard
          title="持仓内货基"
          :value="formatAmount(inPositions)"
          unit="元"
          caption="已建持仓，在环形图内"
        />
        <MetricCard
          title="账外孤儿流水"
          :value="formatAmount(orphanNet)"
          unit="元"
          caption="不建持仓，故不在环形图内"
        />
        <MetricCard
          title="账户现金"
          :value="formatAmount(accountCash)"
          unit="元"
          caption="不建持仓，故不在环形图内"
        />
      </MetricGrid>

      <!-- 与「总资产」的关系必须在 UI 上说清楚（卡面验收第 2 条）。
           环形图合计 = 总资产 = 持仓市值，账外类现金不在其中 —— 这是 D59 解耦的
           可见后果，不说就会变成「新增一个困惑」。 -->
      <div class="cash-like-notes">
        <p class="cash-like-notes__line">
          环形图两片是「持仓市值的划分」，合计等于上方总资产
          {{ formatAmount(totalMarketValue) }}
          元；「账外孤儿流水」与「账户现金」不建持仓、不在环形图内，故
          <strong>环形图合计 ≠ 类现金合计</strong>。
        </p>
        <p v-if="orphanIncome > 0" class="cash-like-notes__line">
          另有账外渠道收益
          {{ formatAmount(orphanIncome) }} 元（已计入家庭总资产，
          不重复计本金）。
        </p>
        <p
          v-if="hasOrphan"
          class="cash-like-notes__line cash-like-notes__line--warn"
        >
          这笔账外流水金额较大时，可能混有跨账本重复导入（同一份交割单在两个账本各导一次）。
          去对账中心核对之前，请把本区块视为「待核实」口径。
        </p>
      </div>

      <!-- 逐产品明细：卡面验收第 2 条「给出可见的解释与去向」的载体。 -->
      <template v-if="breakdown.length">
        <el-button
          text
          size="small"
          class="cash-like-toggle"
          :aria-expanded="expanded"
          @click="expanded = !expanded"
        >
          {{ expanded ? "收起明细" : `展开 ${breakdown.length} 个产品的明细` }}
        </el-button>

        <div v-if="expanded" class="cash-like-table-wrap">
          <table class="cash-like-table">
            <thead>
              <tr>
                <th scope="col">产品</th>
                <th scope="col">类型</th>
                <th scope="col" class="num">本金净额</th>
                <th scope="col" class="num">其中收益</th>
                <th scope="col" class="num">笔数</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in breakdown" :key="rowKey(row)">
                <td>
                  <span class="cash-like-table__name">{{ row.name }}</span>
                  <span v-if="row.symbol" class="cash-like-table__symbol">
                    {{ row.symbol }}</span
                  >
                </td>
                <td>
                  <AssetTypeBadge
                    :type="row.asset_type || ''"
                    :label="row.asset_type_label"
                  />
                </td>
                <td class="num">
                  <MoneyDisplay
                    :value="row.net_amount"
                    size="sm"
                    :show-sign="false"
                    :auto-color="false"
                  />
                </td>
                <td class="num">
                  <MoneyDisplay
                    :value="row.income_amount"
                    size="sm"
                    :show-sign="false"
                    :auto-color="false"
                  />
                </td>
                <td class="num">{{ row.txn_count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </CardBlock>
  </template>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import CardBlock from "@/components/CardBlock/index.vue";
import MetricCard from "@/components/MetricCard/index.vue";
import MetricGrid from "@/components/MetricGrid/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import AssetTypeBadge from "@/components/AssetTypeBadge/index.vue";
import { formatAmount } from "@/utils/currency";
import type { LedgerSummaryData } from "@/composables/useLedgerDetail";

defineOptions({ name: "LedgerCashLikeCard" });

const props = defineProps<{
  summary: LedgerSummaryData | null;
  /** #2739 页内导航锚点 id（落在块内标题行上，见文件头注释）。可空 = 不挂锚点。 */
  anchorId?: string;
}>();

const expanded = ref(false);

const inPositions = computed(
  () => props.summary?.cash_like_in_positions_amount ?? 0
);
const orphanNet = computed(() => props.summary?.orphan_amount ?? 0);
const accountCash = computed(() => props.summary?.account_cash_amount ?? 0);
const orphanIncome = computed(() => props.summary?.orphan_income_amount ?? 0);
const breakdown = computed(() => props.summary?.cash_like_breakdown ?? []);
const total = computed(() => props.summary?.cash_like_amount ?? 0);
const totalMarketValue = computed(() => props.summary?.total_market_value ?? 0);

const hasOrphan = computed(() => orphanNet.value !== 0);

/**
 * 只在两个条件任一成立时渲染整块。
 *
 * ⚠️ 为什么不是「有值就显示」：类现金为 0 的普通基金账户（绝大多数）不该多一张空卡，
 * 那只会把页面撑长。但**账外孤儿非 0 时即使合计数为 0 也必须显示**——否则又回到
 * 「钱在库里、页面上没有出口」的原点，而账外孤儿是唯一可能被净额抵消到 0 的项
 * （买 1000 卖 1000）。
 */
const visible = computed(
  () => total.value !== 0 || orphanNet.value !== 0 || breakdown.value.length > 0
);

const rowKey = (row: { symbol?: string | null; name?: string | null }) =>
  `${row.symbol || ""}|${row.name || ""}`;
</script>

<style lang="scss" scoped>
.cash-like-notes {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: var(--space-compact);

  &__line {
    margin: 0;
    font-size: var(--text-label);
    line-height: 1.6;

    /* 说明文字用 --text-secondary，不用 tertiary：tertiary 是「占位/次要」级，
       而这里承载的是「环形图合计 ≠ 类现金合计」这一条必须被读到的口径信息。 */
    color: var(--text-secondary);

    &--warn {
      color: var(--text-tertiary-ink);
    }
  }
}

.cash-like-toggle {
  padding: 0;
  margin-top: var(--space-compact);
}

.cash-like-table-wrap {
  margin-top: 8px;
  overflow-x: auto;
}

.cash-like-table {
  width: 100%;
  font-size: var(--text-label);
  border-collapse: collapse;

  th,
  td {
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border-subtle);
  }

  th {
    font-size: var(--text-label);
    font-weight: 500;
    color: var(--text-tertiary-ink);
    white-space: nowrap;
  }

  td {
    color: var(--text-primary);
  }

  .num {
    font-variant-numeric: tabular-nums;
    text-align: right;
    white-space: nowrap;
  }

  &__name {
    margin-right: 6px;
  }

  &__symbol {
    font-size: var(--text-label);
    font-variant-numeric: tabular-nums;
    color: var(--text-tertiary-ink);
  }
}
</style>
