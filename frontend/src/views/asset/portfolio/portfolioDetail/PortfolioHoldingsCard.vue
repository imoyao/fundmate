<script setup lang="ts">
import { computed, onMounted, ref, toRef } from "vue";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import PnlDualLine from "@/components/PnlDualLine/index.vue";
import RealtimeEstimateToggle from "@/components/RealtimeEstimateToggle/index.vue";
import { useEnumLabels } from "@/composables/useEnumLabels";
import {
  PNL_DUAL_SCOPE_TIP,
  confirmedPnl,
  usePositionValuation
} from "@/composables/usePositionValuation";
import {
  type PortfolioHolding,
  slicePage,
  sortHoldings
} from "./portfolioDetailModel";
// 归属判断与盘点页持仓表共用同一实现：`undefined`（资产行）与 `null`（继承态）必须分开，
// 这个坑只在一处写清楚，避免两个页面各写一份 `!row.portfolio_id` 而把现金标成「随账户」。
import { isInheritedFromLedger } from "@/views/asset/inventory/portfolioAssignModel";
import PortfolioTableEmpty from "./PortfolioTableEmpty.vue";

/**
 * 持仓明细（#1104：盈亏双线 —— 已确认 / 当日预估）。
 *
 * 排序与分页都是**前端**行为（后端一次返回全量持仓）：`sortProp/sortOrder` 管排序，
 * `holdingsPage` 管切片。两者都在本组件内，翻页/排序不会触碰父层的取数。
 */
defineOptions({ name: "PortfolioHoldingsCard" });

const props = defineProps<{
  holdings: PortfolioHolding[];
}>();

const HOLDINGS_PAGE_SIZE = 20;

// 枚举中文标签（来源等），从后端 /api/utils/enums 单一真相源获取。
// ⚠️ `enums` ref 是**每个实例一份**（只有请求在模块级去重），所以读标签的组件必须
// 自己 `ensure()` 一次：父层预热只填了父层那个实例，本组件的 ref 仍为空，
// `positionSourceLabel` 会退化成英文原键（英文原键上屏 = #1969 同款缺陷）。
const { ensure: ensureEnums, positionSourceLabel } = useEnumLabels();

const sortProp = ref<string | null>(null);
const sortOrder = ref<"ascending" | "descending" | null>(null);
const holdingsPage = ref(1);

/**
 * 盈亏双线（#1104）：估值接线。
 *
 * 传**全量** `holdings` 而非当前页 `pagedHoldings`——本页分页是前端 slice，传当前页会让
 * 每次翻页都重取一轮行情（`usePositionValuation` 的 `watch` 会触发）；而估值引擎是
 * 一次批量请求（基金一批 / 场内一批），全量代价一样。页面也没有「预估合计」这类
 * 跨页汇总，不存在被误读成全仓的口径风险。
 *
 * 三个 `estimate*` 是 `usePositionValuation` 提供的顶层别名：模板不会解包嵌套 ref，
 * 用它才能直接绑定（详见该组合式函数返回值处的注释）。
 */
const {
  estimatedPnl,
  estimateHint,
  estimateEnabled,
  estimateStatus,
  estimateUpdatedAt,
  toggleText: estimateToggleText,
  realtime: estimateQuotes
} = usePositionValuation(toRef(props, "holdings"));

const sortedHoldings = computed(() =>
  sortHoldings(props.holdings, sortProp.value, sortOrder.value)
);

const pagedHoldings = computed(() =>
  slicePage(sortedHoldings.value, holdingsPage.value, HOLDINGS_PAGE_SIZE)
);

function handleSortChange(sort: {
  prop: string;
  order: "ascending" | "descending" | null;
}) {
  sortProp.value = sort.order ? sort.prop : null;
  sortOrder.value = sort.order || null;
  holdingsPage.value = 1; // 排序后重置到第一页
}

/**
 * 该行是否靠「账户默认组合」继承而来（D20 二期 UI）。
 *
 * 判据收在 `portfolioAssignModel.isInheritedFromLedger`——**严格 `=== null`**，
 * 不能用 `!row.portfolio_id`：资产行（现金）压根不带该字段，`undefined` 会被错判成继承。
 */
onMounted(() => void ensureEnums());
</script>

<template>
  <CardBlock class="mb-6">
    <SectionHeader title="持仓明细" :info="PNL_DUAL_SCOPE_TIP">
      <template #action>
        <RealtimeEstimateToggle
          :enabled="estimateEnabled"
          :status="estimateStatus"
          :last-update-time="estimateUpdatedAt"
          :text="estimateToggleText"
          @toggle="estimateQuotes.toggle"
        />
      </template>
    </SectionHeader>
    <el-table
      v-if="holdings.length"
      :data="pagedHoldings"
      stripe
      size="default"
      :default-sort="{ prop: 'market_value', order: 'descending' }"
      @sort-change="handleSortChange"
    >
      <el-table-column label="产品信息" min-width="180">
        <template #default="{ row }">
          <ProductDisplay
            :name="row.name || ''"
            :symbol="row.symbol || ''"
            :type-label="row.type_label || ''"
          />
        </template>
      </el-table-column>

      <el-table-column
        label="市值"
        width="130"
        align="right"
        sortable
        prop="market_value"
      >
        <template #default="{ row }">
          <MoneyDisplay
            :value="row.market_value || 0"
            :show-sign="false"
            :auto-color="false"
          />
        </template>
      </el-table-column>
      <!-- 盈亏双线（#1104）：主行＝已确认（后端 current_price 口径），副行＝当日预估。
           排序仍按后端 `pnl`（与已确认同一公式）——资产行无份额 / 现价，两行都显示 `--`。 -->
      <el-table-column
        label="盈亏"
        width="170"
        align="right"
        sortable
        prop="pnl"
      >
        <template #default="{ row }">
          <PnlDualLine
            :confirmed="confirmedPnl(row as PortfolioHolding)"
            :estimated="estimatedPnl(row as PortfolioHolding)"
            :hint="estimateHint(row as PortfolioHolding)"
            :price-date="(row as PortfolioHolding).price_date"
            :settled-today="(row as PortfolioHolding).settled_today"
          />
        </template>
      </el-table-column>
      <el-table-column
        label="盈亏率"
        width="90"
        align="right"
        sortable
        prop="pnl_rate"
      >
        <template #default="{ row }">
          <RiseFallText :value="row.pnl_rate || 0" />
        </template>
      </el-table-column>
      <el-table-column label="来源" width="110">
        <template #default="{ row }">
          <el-tag
            v-if="positionSourceLabel(row.source)"
            size="small"
            type="info"
          >
            {{ positionSourceLabel(row.source) }}
          </el-tag>
          <span v-else style="color: var(--text-tertiary-ink)">—</span>
        </template>
      </el-table-column>
      <!-- 归属方式（D20 二期 UI，**只读**）：标明这行是「本组合显式指派」还是「随账户继承」。
           本页不提供改派入口——这里语义是「按组合看持仓」，改派动作放在盘点页持仓表。
           在此给完整浮层会诱导误读：用户看得见的是「它在这个组合里」，想做的事往往是
           「把某条弄出去」，而不是「在这里给它挑新家」，两者操作路径不同。 -->
      <el-table-column label="所属账户 / 归属" min-width="170">
        <template #default="{ row }">
          <span class="ledger-cell">
            <span class="ledger-name">{{ row.account_name || "未归档" }}</span>
            <span
              v-if="isInheritedFromLedger(row as PortfolioHolding)"
              class="inherit-chip"
              title="该持仓未显式指派组合，靠所属账户的默认组合归入本组合"
              >随账户</span
            >
          </span>
        </template>
      </el-table-column>
    </el-table>
    <PortfolioTableEmpty v-else>
      暂无持仓数据，可先在各账户新建持仓后再关联到此组合。
    </PortfolioTableEmpty>
    <div v-if="holdings.length > 0" class="flex justify-end mt-4">
      <el-pagination
        v-model:current-page="holdingsPage"
        :page-size="HOLDINGS_PAGE_SIZE"
        layout="prev, pager, next"
        :total="holdings.length"
        small
      />
    </div>
  </CardBlock>
</template>

<style lang="scss" scoped>
/* 归属标记（D20 二期 UI）：账户名 + 「随账户」小标签。
   标签刻意用中性底 + 辅助字色，不用品牌红——「继承」是常态而非异常，
   用强调色会让大多数行看起来像在报警，反而失去提示价值。 */
.ledger-cell {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  max-width: 100%;
}

.ledger-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inherit-chip {
  flex: 0 0 auto;
  padding: 0 4px;
  font-size: 0.8em;
  line-height: 16px;
  color: var(--text-tertiary-ink);
  background: var(--bg-soft);
  border-radius: 3px;
}
</style>
