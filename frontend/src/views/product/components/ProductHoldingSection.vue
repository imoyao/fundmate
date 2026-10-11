<script setup lang="ts">
import { computed } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import type { FundHoldingsDetailResult } from "@/api/products";

/**
 * 详情页「持仓明细」区块（#2029 卡 C · 设计卡 §4.1 #5）。
 *
 * 表格：代码 / 名称 / 占净值比 / 持股数 / 市值 / 排名，数据来自
 * `GET /api/products/fund-holdings-detail/`。
 *
 * 口径与降级（设计卡 §4.2③ · penetration 硬口径 7）：
 * - **必须展示 `basis_label`** —— 季报只披露前十大，`top10` 与 `full` 不可混。
 *   不标注的话用户会把「只披露了 10 只」误读成「只买了 10 只」，据此判断
 *   持仓集中度会得出完全错误的结论。
 * - 缺失字段逐项降级为「—」，**不按 0 展示**（0 意味着「确实没配这只」，
 *   缺失只是「没采到」，两者语义相反）。
 */

const props = defineProps<{
  detail: FundHoldingsDetailResult | null;
  source: string;
}>();

const holdings = computed(() => props.detail?.holdings ?? null);
const rows = computed(() => holdings.value?.rows ?? []);

/** `top10` 口径下必须提示：这是季报前十大，不等于全部持仓 */
const isTop10 = computed(() => holdings.value?.basis === "top10");
</script>

<template>
  <CardBlock class="holding-section">
    <SectionHeader title="持仓明细" />

    <p v-if="!rows.length" class="holding-section__hint">暂无持仓明细数据</p>

    <template v-else>
      <!-- 口径标注：与表格同屏，不藏在脚注里（用户第一眼就要看到「这是前十大」） -->
      <p v-if="holdings?.basis_label" class="holding-section__basis">
        披露口径：{{ holdings.basis_label }}
        <template v-if="holdings.report_period">
          · 报告期 {{ holdings.report_period }}
        </template>
      </p>

      <div class="holding-section__table-wrap">
        <table class="holding-section__table">
          <thead>
            <tr>
              <th scope="col" class="holding-section__num">序号</th>
              <th scope="col">代码</th>
              <th scope="col">名称</th>
              <th scope="col" class="holding-section__num">占净值比</th>
              <th scope="col" class="holding-section__num">持股数(万股)</th>
              <th scope="col" class="holding-section__num">市值(万元)</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(r, i) in rows"
              :key="r.stock_code + '-' + (r.rank ?? i)"
            >
              <td class="holding-section__num">
                {{ r.rank ?? i + 1 }}
              </td>
              <td class="holding-section__code">
                {{ r.stock_code }}
              </td>
              <td>{{ r.stock_name ?? "—" }}</td>
              <td class="holding-section__num">
                {{ r.ratio != null ? r.ratio.toFixed(2) + "%" : "—" }}
              </td>
              <td class="holding-section__num">
                {{ r.shares != null ? r.shares.toLocaleString() : "—" }}
              </td>
              <td class="holding-section__num">
                {{
                  r.market_value != null ? r.market_value.toLocaleString() : "—"
                }}
              </td>
            </tr>
          </tbody>
          <tfoot v-if="holdings?.shown_total_ratio != null">
            <tr>
              <th scope="row" colspan="3">所示合计</th>
              <td class="holding-section__num">
                {{ holdings.shown_total_ratio.toFixed(2) }}%
              </td>
              <td class="holding-section__num">—</td>
              <td class="holding-section__num">—</td>
            </tr>
          </tfoot>
        </table>
      </div>

      <p v-if="isTop10" class="holding-section__caveat">
        ⚠️ 以上为季报披露的前十大重仓，不代表该基金的全部持仓。
      </p>
      <p class="holding-section__footnote">
        数据来源：{{ source }} · 持仓为报告期快照（非日期序列）
        <template v-if="holdings?.report_date">
          · 截至 {{ holdings.report_date }}</template
        >
      </p>
    </template>
  </CardBlock>
</template>

<style scoped>
.holding-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.holding-section__hint,
.holding-section__footnote {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.holding-section__basis {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

/* ⚠️ 口径警告：这是**用户必须看到**的信息，不能做成不显眼的脚注 */
.holding-section__caveat {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  background: var(--bg-subtle, var(--bg-card));
  border-left: 3px solid var(--color-warning, var(--brand-700));
  border-radius: 0 var(--radius-sm, 4px) var(--radius-sm, 4px) 0;
}

.holding-section__table-wrap {
  overflow-x: auto;
}

.holding-section__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.holding-section__table th,
.holding-section__table td {
  padding: var(--space-2) var(--space-2);
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid var(--border-light);
}

.holding-section__table thead th {
  font-weight: 500;
  color: var(--text-tertiary);
}

.holding-section__num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.holding-section__code {
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}
</style>
