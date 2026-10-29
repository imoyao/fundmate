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
      <!-- 所属组合（D20 二期 UI）**紧跟产品信息**，而不是排到右侧数值列之后：
           本页容器在 xl+ 下是 1082px（正文右侧还有目录 rail），而「操作」列是
           fixed-right，会盖住滚动区右端的列——放到右数第二列就等于「需要横滚才看得见」，
           而归类状态（这个账户里哪些持仓被我拆到了别的组合）恰恰是翻账户时最想问的。

           ⚠️ **列宽预算：10 列合计 1080px，容器 1082px，余量仅 2px。**
           加这一列时实测溢出 78px，把原本可见的「配置目标」推进了 fixed 操作列底下，
           故同步收窄了 5 列（持仓成本 120→104 / 盈亏 170→152 / 盈亏率 100→82 /
           持有时长 110→100 / 所属组合 150→132）才归零。下次谁要再加列，
           必须先减一列或降别的列宽，否则「配置目标」会再次被遮住（`measure_table.py`
           式的量法：读 `.el-table__body-wrapper` 的 scrollWidth − clientWidth）。 -->
      <el-table-column v-if="!p.isUnclassified" label="所属组合" width="132">
        <template #default="{ row }">
          <PortfolioAssignCell
            :row="row as LedgerHoldingRow"
            :portfolios="p.portfolioList"
            :mode="p.resolveHoldingPortfolio(row as LedgerHoldingRow).mode"
            :label-text="
              p.resolveHoldingPortfolio(row as LedgerHoldingRow).labelText
            "
            @select="
              portfolioId =>
                p.reassignPosition(row as LedgerHoldingRow, portfolioId)
            "
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
        width="104"
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
        width="152"
        align="right"
        sortable
        prop="pnl"
      >
        <template #default="{ row }">
          <PnlDualLine
            :confirmed="confirmedPnl(row as LedgerHoldingRow)"
            :estimated="p.valuation.estimatedPnl(row as LedgerHoldingRow)"
            :hint="p.valuation.estimateHint(row as LedgerHoldingRow)"
            :price-date="(row as LedgerHoldingRow).price_date"
            :settled-today="(row as LedgerHoldingRow).settled_today"
          />
        </template>
      </el-table-column>
      <el-table-column
        label="盈亏率"
        width="82"
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
        width="100"
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
      <!-- 配置目标（#1123 P0）：徽章改行内下拉，保存走嵌套持仓 PATCH（后端五笔钱白名单）。
           色点保留原徽章的颜色语义（getAllocColor）；失败时以服务端真值回滚 select 的乐观更新。

           `@click.stop` 挂在整格上：本表 `@row-click` 打开持仓明细抽屉，不阻断的话
           「点开下拉」与「弹出抽屉」同时发生，抽屉会盖住还没选的下拉。
           单元格内的可交互控件必须吞掉冒泡，这是表格类界面的通病，不能靠使用者自觉。 -->
      <el-table-column label="配置目标" width="120" align="right">
        <template #default="{ row }">
          <div class="alloc-cell" @click.stop>
            <span
              class="alloc-dot"
              :style="{ backgroundColor: p.getAllocColor(row.allocation) }"
            />
            <el-select
              v-model="row.allocation"
              size="small"
              class="alloc-select"
              @change="handleAllocationChange(row as LedgerHoldingRow)"
            >
              <el-option
                v-for="opt in ALLOCATION_OPTIONS"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </div>
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
              @click.stop="p.openDeletePositionDialog(row as LedgerHoldingRow)"
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

    <!-- 删除持仓确认（#1830）：「取消」归位为中止，两个删除分支各自自解释 -->
    <DeletePositionDialog
      :visible="p.deletePositionDialog.visible"
      :position-name="p.deletePositionDialog.positionName"
      :loading="p.deletePositionDialog.loading"
      @update:visible="p.closeDeletePositionDialog"
      @confirm="p.handleDeletePosition"
    />
  </el-tab-pane>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import { ElMessage } from "element-plus";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import DeletePositionDialog from "./DeletePositionDialog.vue";
import PnlDualLine from "@/components/PnlDualLine/index.vue";
import RealtimeEstimateToggle from "@/components/RealtimeEstimateToggle/index.vue";
import PortfolioAssignCell from "@/views/asset/inventory/components/PortfolioAssignCell.vue";
import { updateLedgerPosition } from "@/api/ledger";
import { ALLOCATION_OPTIONS } from "@/constants";
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

/** 行内编辑配置目标（#1123 P0）：写回 Position.allocation（后端五笔钱白名单） */
async function handleAllocationChange(row: LedgerHoldingRow) {
  try {
    await updateLedgerPosition(Number(p.ledgerId), row.id, {
      allocation: row.allocation ?? null
    });
    ElMessage.success("配置目标已更新");
  } catch (e) {
    const err = e as { response?: { data?: { message?: string } } };
    ElMessage.error(err?.response?.data?.message || "配置目标更新失败");
    // v-model 已乐观更新 row.allocation：失败后以服务端真值恢复
    p.loadHoldings();
  }
}
</script>

<style lang="scss" scoped>
.alloc-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* 「配置目标」在表格里是**行内文本控件**，不是表单输入框：一个带边框的下拉框
   嵌在密集的只读数字中间，视觉上像「这格还没填」。统一走 design.md「输入框基线
   契约」允许的页面侧手段——**在容器上覆盖令牌**，而不是再写一套 `:deep` 视觉覆盖
   （那会分化出第二份输入框样式，正是该契约要禁止的）：
   - 底色 / 边框三态设 transparent ⇒ 静息呈现为纯文本，与左侧「所属组合」同一语言；
   - 焦点环保留（未覆盖 --input-focus-shadow）⇒ 展开下拉时仍能看出「在改这一格」；
   - hover 底色画在本容器上（纯几何 + 背景），不碰输入框内部。 */
.alloc-cell {
  --input-bg: transparent;
  --input-border-color: transparent;
  --input-hover-border-color: transparent;

  display: flex;
  gap: 4px;
  align-items: center;
  justify-content: flex-end;

  /* 左右 2px 只为了 hover 底色比文本略宽一点；用负 margin 抵消，否则会从
     select 的可用宽度里啃掉 4px，把「长期增值」挤成「长期...」（实测）。 */
  padding: 0 2px;
  margin: 0 -2px;
  border-radius: var(--radius-sm);

  &:hover {
    background: var(--bg-hover);
  }
}

.alloc-select {
  width: 96px;
}
</style>
