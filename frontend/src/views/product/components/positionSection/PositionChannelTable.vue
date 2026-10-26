<script setup lang="ts">
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import { formatQuantity } from "@/utils/format";
import { dayPnlRate, daysText, pnlRate } from "../productPositionMetrics";
import type { ChannelTotals } from "../productPositionMetrics";
import type { ChannelGroup } from "./positionTypes";
import PositionAccountLink from "./PositionAccountLink.vue";

/**
 * 多账户形态：一个表头管全部行，产品列与每组表头都已去掉（#980 拆分产物）。
 *
 * 表口径见 `_detail-table.scss`（#553）：分隔 / 表头 / 表尾 / 数字列不由本组件决定。
 * 多列且列宽固定 → 加 `--fixed`，窄屏横滚（`.product-position__scroll`）。
 */
defineProps<{
  groups: ChannelGroup[];
  totals: ChannelTotals;
}>();
</script>

<template>
  <div class="product-position__scroll">
    <table class="detail-table detail-table--fixed product-position__table">
      <thead>
        <tr>
          <th class="detail-table__product">账户</th>
          <th class="detail-table__num">持有份额</th>
          <th class="detail-table__num">持仓成本</th>
          <th class="detail-table__num">持有金额</th>
          <th class="detail-table__num">持有盈亏</th>
          <th class="detail-table__num">盈亏率</th>
          <th class="detail-table__num">当日盈亏</th>
          <th class="detail-table__num">当日盈亏率</th>
          <th class="detail-table__num">持仓天数</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="g in groups" :key="g.key">
          <td class="detail-table__product">
            <PositionAccountLink :name="g.name" :ledger-id="g.ledgerId" />
          </td>
          <td class="detail-table__num">
            {{ formatQuantity(g.quantity) }}
          </td>
          <td class="detail-table__num">
            <MoneyDisplay
              :value="g.cost"
              :auto-color="false"
              :show-sign="false"
            />
          </td>
          <td class="detail-table__num">
            <MoneyDisplay
              :value="g.marketValue"
              :auto-color="false"
              :show-sign="false"
            />
          </td>
          <td class="detail-table__num">
            <MoneyDisplay :value="g.pnl" :precision="2" />
          </td>
          <td class="detail-table__num">
            <RiseFallText :value="pnlRate(g)" suffix="%" />
          </td>
          <td class="detail-table__num">
            <MoneyDisplay
              v-if="g.dayPnl != null"
              :value="g.dayPnl"
              :precision="2"
            />
            <span v-else class="product-position__empty">—</span>
          </td>
          <td class="detail-table__num">
            <RiseFallText
              v-if="dayPnlRate(g) !== null"
              :value="dayPnlRate(g) ?? 0"
              suffix="%"
            />
            <span v-else class="product-position__empty">—</span>
          </td>
          <td class="detail-table__num">{{ daysText(g.holdingDays) }}</td>
        </tr>
      </tbody>
      <tfoot>
        <tr>
          <td class="detail-table__product">合计</td>
          <td class="detail-table__num" />
          <td class="detail-table__num">
            <MoneyDisplay
              :value="totals.cost"
              :auto-color="false"
              :show-sign="false"
            />
          </td>
          <td class="detail-table__num">
            <MoneyDisplay
              :value="totals.marketValue"
              :auto-color="false"
              :show-sign="false"
            />
          </td>
          <td class="detail-table__num">
            <MoneyDisplay :value="totals.pnl" :precision="2" />
          </td>
          <td class="detail-table__num">
            <RiseFallText :value="pnlRate(totals)" suffix="%" />
          </td>
          <td class="detail-table__num">
            <MoneyDisplay
              v-if="totals.dayPnl != null"
              :value="totals.dayPnl"
              :precision="2"
            />
            <span v-else class="product-position__empty">—</span>
          </td>
          <td class="detail-table__num">
            <RiseFallText
              v-if="dayPnlRate(totals) !== null"
              :value="dayPnlRate(totals) ?? 0"
              suffix="%"
            />
            <span v-else class="product-position__empty">—</span>
          </td>
          <td class="detail-table__num" />
        </tr>
      </tfoot>
    </table>
    <!-- 「当日」到底指哪一天要写出来（#2007）：场外基金是 T-1 净值、场内是最近收盘日，
         不总是今天。多账户各自基准日可能不同，故给最新那一天，并说明口径。 -->
    <p v-if="totals.dayBasisDate" class="product-position__asof">
      当日盈亏 =（现价 − 上一确认价）× 数量；最新基准日
      {{ totals.dayBasisDate }}（场外基金为 T-1 净值，与平台披露节奏一致）
    </p>
  </div>
</template>

<style lang="scss" scoped>
/* ===== 多账户：紧凑表格 ===== */
.product-position__scroll {
  overflow-x: auto;
}

/* 表格自身的 padding / 分隔线 / 表头 / 表尾 / 数字列已全部由共享约定
   `.detail-table` 提供（#553，#2320 同一条延长线），此处不保留任何覆盖——
   原先那份把 `tabular-nums` 加在整张表上（含中文列），既无意义，
   又让「数字列唯一写法」失去单一来源。 */

/* 多账户表格下方的基准日说明：把「当日」的日期口径说在表格外，不额外占一列 */
.product-position__asof {
  margin: var(--space-2) 0 0;
  font-size: var(--text-label);
  line-height: 1.5;
  color: var(--text-tertiary-ink);
}

/* 「—」占位统一样式：保持字号但走弱色，避免被读成一个真值 */
.product-position__empty {
  color: var(--text-tertiary-ink);
}
</style>
