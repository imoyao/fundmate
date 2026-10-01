<template>
  <!-- 持仓明细 Tab -->
  <el-tab-pane label="持仓明细" name="holdings">
    <!-- 盈亏双线（#1104）：口径说明 + 实时估值开关就地给出（本 Tab 没有 SectionHeader 可挂） -->
    <div class="flex items-center justify-end gap-2 mb-2">
      <el-tooltip :content="PNL_DUAL_SCOPE_TIP" placement="top">
        <span
          class="text-xs"
          :style="{ color: 'var(--text-tertiary-ink)', cursor: 'help' }"
          >盈亏口径</span
        >
      </el-tooltip>
      <RealtimeEstimateToggle
        :enabled="p.valuation.estimateEnabled"
        :status="p.valuation.estimateStatus"
        :last-update-time="p.valuation.estimateUpdatedAt"
        :text="p.valuation.toggleText"
        @toggle="p.valuation.realtime.toggle"
      />
    </div>
    <el-table
      :data="p.holdingsList"
      stripe
      size="default"
      :default-sort="{ prop: 'market_value', order: 'descending' }"
      @row-click="p.openPositionDrawer"
    >
      <el-table-column label="产品信息" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <ProductDisplay
            :name="row.name"
            :symbol="row.symbol"
            :type-label="row.type_label"
          />
        </template>
      </el-table-column>
      <el-table-column
        label="市值"
        width="110"
        align="right"
        sortable
        prop="market_value"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.market_value || 0"
            :show-sign="false"
            :auto-color="false"
            size="sm"
          />
        </template>
      </el-table-column>

      <!-- 持仓成本（#862）：接口已返回 avg_price，仅补展示列 -->
      <el-table-column
        label="持仓成本"
        width="120"
        align="right"
        sortable
        prop="avg_price"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.avg_price || 0"
            :precision="pricePrecision(row.asset_type)"
            :show-sign="false"
            :auto-color="false"
            size="sm"
          />
        </template>
      </el-table-column>
      <!-- 盈亏双线（#1104）：主行＝已确认（后端 current_price 口径），副行＝当日预估。
           排序仍按后端 `pnl` 字段——它与已确认口径同一公式 `(现价 − 成本) × 数量`，
           唯货基 / 逆回购在显示上改为 `--`（后端给 0，排序视作 0）。
           不加 `show-overflow-tooltip`：内容是两行组件，会被截断成一行文本反而误导。 -->
      <el-table-column
        label="盈亏"
        width="170"
        align="right"
        sortable
        prop="pnl"
      >
        <template #default="{ row }">
          <PnlDualLine
            :confirmed="confirmedPnl(row as LedgerHoldingRow)"
            :estimated="p.valuation.estimatedPnl(row as LedgerHoldingRow)"
            :hint="p.valuation.estimateHint(row as LedgerHoldingRow)"
          />
        </template>
      </el-table-column>
      <el-table-column
        label="盈亏率"
        width="100"
        align="right"
        sortable
        prop="pnl_rate"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.pnl_rate || 0"
            :precision="2"
            :show-currency="false"
            suffix="%"
            size="sm"
          />
        </template>
      </el-table-column>

      <!-- 持有时长（#862）：后端按 confirm_date 计算返回 holding_days；无确认日显示 -- ；
                       口径为「本轮」：自本轮建仓日起算，清仓后重新计起，不累计历史（见 docs/working-notes/holding-days-semantics-2026-09-02.md） -->
      <el-table-column
        label="持有时长"
        width="110"
        align="right"
        sortable
        prop="holding_days"
        show-overflow-tooltip
      >
        <template #header>
          <el-tooltip
            content="自本轮建仓日起算；清仓后重新计起，不累计历史持仓"
            placement="top"
          >
            <span>持有时长(本轮)</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span v-if="row.holding_days != null">{{ row.holding_days }} 天</span>
          <span v-else>--</span>
        </template>
      </el-table-column>
      <el-table-column
        label="配置目标"
        width="90"
        align="right"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <span
            class="px-2 py-0.5 rounded-full text-xs"
            :style="{ color: p.getAllocColor(row.allocation) }"
          >
            {{ row.allocation_label }}
          </span>
        </template>
      </el-table-column>
      <el-table-column
        v-if="!p.isUnclassified"
        label="操作"
        width="130"
        fixed="right"
      >
        <template #default="{ row }">
          <div class="flex items-center gap-1" style="white-space: nowrap">
            <el-button
              text
              size="small"
              @click.stop="
                p.migrateDialogRef?.openMigrateDialog(row as LedgerHoldingRow)
              "
              >迁移</el-button
            >
            <el-button
              text
              size="small"
              type="danger"
              @click.stop="p.confirmDeletePosition(row as LedgerHoldingRow)"
              >删除</el-button
            >
          </div>
        </template>
      </el-table-column>
      <el-table-column v-if="p.isUnclassified" label="归入账户" width="160">
        <template #default="{ row }">
          <el-select
            v-model="p.assignMap[row.id]"
            placeholder="选择账户"
            size="small"
            @change="p.handleAssign(row.id)"
          >
            <el-option
              v-for="ledger in p.ledgers"
              :key="ledger.id"
              :label="ledger.name"
              :value="ledger.id"
            />
          </el-select>
        </template>
      </el-table-column>
    </el-table>

    <div class="flex justify-end mt-4">
      <el-pagination
        v-model:current-page="p.holdingsPage"
        :page-size="p.holdingsPageSize"
        layout="prev, pager, next"
        :total="p.holdingsTotal"
        small
        @current-change="p.loadHoldings"
      />
    </div>
  </el-tab-pane>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import PnlDualLine from "@/components/PnlDualLine/index.vue";
import RealtimeEstimateToggle from "@/components/RealtimeEstimateToggle/index.vue";
import { pricePrecision } from "@/utils/pricePrecision";
import type { LedgerHoldingRow } from "@/composables/useLedgerDetail";
import {
  confirmedPnl,
  PNL_DUAL_SCOPE_TIP
} from "@/composables/usePositionValuation";
import type { useLedgerDetailPage } from "../composables/useLedgerDetailPage";

defineOptions({ name: "LedgerDetailHoldingsPane" });

// #980 P1-C 拆分自 detail.vue：持仓明细 Tab 面板（表格 + 分页 + 行操作）。
// pricePrecision / LedgerHoldingRow 为本组件局部导入，模板内保持裸用。
const props = defineProps<{ page: ReturnType<typeof useLedgerDetailPage> }>();
// `reactive` 的好处在这里体现：`page` 里既有顶层 ref（holdingsList）也有嵌套 ref
// （valuation.estimateEnabled），经 reactive 代理后模板里都能直接绑，不必手写 `.value`。
const p = reactive(props.page);
</script>
