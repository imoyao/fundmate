<!-- src/components/TransactionTable/index.vue -->
/** * 交易流水表 —— 全站唯一实现（#2104 验收：「有持仓时数据与账本详情页 *
PositionTransactionsDrawer 同源一致（同一接口/同一组件，禁止第二套实现）」）。 *
* 此前三处各写一套表格（详情页 ProductTransactionSection / 账本 Tab *
LedgerDetailTransactionsPane / 持仓抽屉 PositionTransactionsDrawer）， *
字段名（type vs txn_type）、日期口径（trade_date vs confirm_date）、 *
类型着色、手续费列、操作列全不一致——用户感知为「切割感」。本组件收口 *
列定义与视觉口径，**容器各自取数**（接口不同：按 symbol / 按 ledger 分页 / * 按
position），只需把行适配成 TransactionRow。 * *
设计规范（frontend/design.md「Table」+ docs/design/components.md）： * -
el-table 视觉基线全局统一（src/style/el-table.css），本组件**不写任何 *
:deep(.el-table) 覆盖**；行高走 44px 基线，**不设 size**（规范禁止 * size /
:row-style 单独覆盖）； * - 列宽一律 minWidth，仅固定列（product 左冻结 /
_actions 右冻结）用 width； * - 产品列必须走 ProductDisplay（表格产品列统一）；
* - 行内操作按钮 hover 200ms 淡入（design.md「行内操作交互规范」： *
禁止常驻按钮；:focus-within 时也显现，保键盘可达）； * - 金额一律 MoneyDisplay
且 autoColor=false：**流水金额不表示涨跌**， *
红绿语义只留给真正的涨跌场景（把正数金额全染红是错误语义）； * - 数字列经
formatQuantity / MoneyDisplay 的 .number 走 tabular-nums。 * *
口径统一（本组件即全站口径）： * - 日期：trade_date 优先、confirm_date
兜底（交易日是用户心智里的「哪天买的」； *
确认日是份额/资金交收到账日，详情页曾只认 trade_date、账本 Tab 只认 *
confirm_date，同一笔交易两端显示可以不同天）； * - 类型着色：买入/存入 =
涨红，卖出/取出 = 跌绿，分红等中性 = info * （原 getTxnTypeClass 判据，自
useLedgerTransactions 上收）； * - 数量：formatQuantity（2 位小数 +
千分位，份额不是货币不参与涨跌语义）。 */
<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import { txnTypeLabel } from "@/constants";
import { formatQuantity } from "@/utils/format";
import { pricePrecision } from "@/utils/pricePrecision";

/**
 * 交易行（三端容器的最大公约数）。容器负责把各自接口返回映射到本结构：
 * - 详情页 TransactionRecord：字段同名（type/trade_date/quantity/price/amount/fee），可直接传；
 * - 账本 Tab LedgerTxnRow：txn_type → type；
 * - 持仓抽屉 getPositionTransactions 行：txn_type → type（spread 保留原字段，
 *   编辑弹窗所需的 notes/import_hash 运行时仍在，仅类型层面不收）。
 */
export interface TransactionRow {
  id: number;
  /** 交易类型：buy/sell/dividend/dividend_reinvest/deposit/withdraw/split */
  type: string;
  trade_date?: string | null;
  confirm_date?: string | null;
  price?: number | null;
  quantity?: number | null;
  amount?: number | null;
  fee?: number | null;
  asset_type?: string | null;
  position_name?: string;
  symbol?: string;
  account_name?: string;
  /** 账户 ID：非空时账户名可点击跳转账户详情（/asset/ledgers/:id）；
      空 = 未归档（如探市录入），保持纯文本——那里没有落点，链过去是坏的 */
  ledger_id?: number | null;
}

const props = withDefaults(
  defineProps<{
    rows: TransactionRow[];
    /** compact = 详情页/抽屉的单标的紧凑表；full = 账本 Tab 的全量表（多产品列） */
    mode: "compact" | "full";
    /** 产品列（position_name + symbol，左冻结）。仅 full 有意义 */
    showAsset?: boolean;
    /** 手续费列 */
    showFee?: boolean;
    /** 账户列。仅 compact（详情页）使用 */
    showAccount?: boolean;
    /** 操作列：编辑 / 删除按钮（hover 淡入）。删除需确认由容器负责 */
    showEdit?: boolean;
    showDelete?: boolean;
    /** 日期列是否可排序（账本 Tab 传 true；紧凑表数据量小不传） */
    sortable?: boolean;
    /** 展开态的「表格内部滚动」高度上限（px）；缺省不滚动 */
    maxHeight?: number;
    /** el-table 的 id：调用方的 aria-controls 指向它 */
    tableId?: string;
    /** 价格列标签覆写（基金抽屉传「确认净值」） */
    priceLabel?: string;
    /** 数量列标签覆写（基金抽屉传「确认份额」） */
    quantityLabel?: string;
  }>(),
  {
    showAsset: false,
    showFee: false,
    showAccount: false,
    showEdit: false,
    showDelete: false,
    sortable: false,
    tableId: "transaction-table"
  }
);

const emit = defineEmits<{
  edit: [row: TransactionRow];
  delete: [row: TransactionRow];
}>();

const hasActions = computed(() => props.showEdit || props.showDelete);

/** 日期口径：交易日优先、确认日兜底（详见文件头） */
function formatDate(row: TransactionRow): string {
  return row.trade_date || row.confirm_date || "--";
}

/** 类型着色：买入/存入 = 涨红，卖出/取出 = 跌绿，分红等中性 = info */
function typeClass(type: string): string {
  if (type === "buy" || type === "deposit") return "txn-type--rise";
  if (type === "sell" || type === "withdraw") return "txn-type--fall";
  return "txn-type--info";
}
</script>

<template>
  <el-table
    :id="tableId"
    :data="rows"
    stripe
    :max-height="maxHeight"
    :default-sort="
      sortable ? { prop: 'trade_date', order: 'descending' } : undefined
    "
  >
    <!-- 产品列：左冻结（design.md「冻结列」：名称+代码作为首列固定 180-220px，
         用户横向滚动时始终锚定；固定列是唯一允许 width 的列）。走 ProductDisplay
         而非手写两行 span。 -->
    <el-table-column v-if="showAsset" label="资产名称" width="200" fixed="left">
      <template #default="{ row }">
        <ProductDisplay :name="row.position_name" :symbol="row.symbol" />
      </template>
    </el-table-column>
    <el-table-column
      prop="trade_date"
      label="交易日期"
      min-width="100"
      :sortable="sortable"
    >
      <template #default="{ row }">{{
        formatDate(row as TransactionRow)
      }}</template>
    </el-table-column>
    <el-table-column label="类型" min-width="60">
      <template #default="{ row }">
        <span :class="typeClass(row.type)">{{
          txnTypeLabel(row.type) || row.type
        }}</span>
      </template>
    </el-table-column>
    <el-table-column :label="priceLabel || '价格'" min-width="90" align="right">
      <template #default="{ row }">
        <MoneyDisplay
          :value="row.price ?? 0"
          :precision="pricePrecision(row.asset_type)"
          :show-sign="false"
          :show-currency="false"
          :auto-color="false"
          size="sm"
        />
      </template>
    </el-table-column>
    <el-table-column
      :label="quantityLabel || '数量'"
      min-width="80"
      align="right"
    >
      <template #default="{ row }">{{
        formatQuantity(row.quantity ?? 0)
      }}</template>
    </el-table-column>
    <el-table-column label="金额" min-width="100" align="right">
      <template #default="{ row }">
        <MoneyDisplay
          :value="row.amount ?? 0"
          :show-sign="false"
          :auto-color="false"
          size="sm"
        />
      </template>
    </el-table-column>
    <el-table-column v-if="showFee" label="手续费" min-width="80" align="right">
      <template #default="{ row }">
        <MoneyDisplay
          :value="row.fee ?? 0"
          :show-sign="false"
          :auto-color="false"
          size="sm"
        />
      </template>
    </el-table-column>
    <el-table-column
      v-if="showAccount"
      label="账户"
      min-width="100"
      show-overflow-tooltip
    >
      <!-- 账户名可点击跳账户详情（与 ProductPositionSection 的账户链接同款：
           ledger_id 有值才给落点，未归档流水保持纯文本） -->
      <template #default="{ row }">
        <router-link
          v-if="(row as TransactionRow).ledger_id"
          class="txn-table__account"
          :to="`/asset/ledgers/${(row as TransactionRow).ledger_id}`"
        >
          {{ row.account_name || "未知账户" }}
        </router-link>
        <span v-else class="txn-table__account txn-table__account--plain">{{
          row.account_name || "未知账户"
        }}</span>
      </template>
    </el-table-column>
    <!-- 扩展列 slot（#2171 P2）：调用方注入**完整的 el-table-column**（如详情页的
         「当时成本 / 收益贡献」重放列）。**可选**：三端既有调用（账本 Tab / 持仓抽屉）
         不传即不渲染，零影响。
         为什么走 slot 而不是加 props：这两列是 #2171 特有的重放口径，塞进公共组件会
         让另外两端平白多两列看不懂的字段；slot 让「字段归属」留在调用方。
         注意：slot 必须放在 </el-table> 之前、且由调用方自己写 el-table-column，
         因为 el-table-column 的作用域只能来自 el-table 的默认 slot。 -->
    <slot name="extra-columns" />

    <!-- 操作列：右冻结。hover 行才淡入（200ms ease-out），:focus-within 保键盘可达。
         这是 design.md 明确允许保留的「行内行为样式」，不触视觉基线。 -->
    <el-table-column v-if="hasActions" label="操作" width="140" fixed="right">
      <template #default="{ row }">
        <div class="txn-table__actions">
          <el-button
            v-if="showEdit"
            text
            size="small"
            @click.stop="emit('edit', row as TransactionRow)"
            >编辑</el-button
          >
          <el-button
            v-if="showDelete"
            text
            size="small"
            type="danger"
            @click.stop="emit('delete', row as TransactionRow)"
            >删除</el-button
          >
        </div>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
/* 类型着色：涨红跌绿（A 股惯例），分红等中性走 info。
   借 --color-rise / --color-fall 语义令牌，禁硬编码色值。 */
.txn-type--rise {
  color: var(--color-rise);
}

.txn-type--fall {
  color: var(--color-fall);
}

.txn-type--info {
  color: var(--color-info);
}

/* 账户链接：与 ProductPositionSection 的 .product-position__account 同款口径
   （可点击给链接态 hover，未归档无落点保持纯文本），禁硬编码色值 */
.txn-table__account {
  color: var(--text-primary);
  text-decoration: none;
  border-bottom: 1px solid transparent;
}

.txn-table__account:not(.txn-table__account--plain):hover {
  color: var(--color-primary-ink);
  border-bottom-color: currentColor;
}

.txn-table__account--plain {
  cursor: default;
}

/* 行内操作 hover 淡入（design.md「行内操作交互规范」：默认 opacity 0，
   hover 行 200ms ease-out 淡入）。两个可达性兜底（guard_a11y_interaction）：
   - :focus-within：键盘 Tab 到按钮即显现；
   - @media (hover: none)：触屏设备没有 hover 态，按钮常驻——
     否则触屏用户永远点不到「编辑」。 */
.txn-table__actions {
  display: flex;
  gap: 4px;
  justify-content: flex-end;
  white-space: nowrap;
  opacity: 0;
  transition: opacity 200ms ease-out;
}

:deep(.el-table__row:hover) .txn-table__actions {
  opacity: 1;
}

.txn-table__actions:focus-within {
  opacity: 1;
}

@media (hover: none) {
  .txn-table__actions {
    opacity: 1;
  }
}
</style>
