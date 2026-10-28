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
<script lang="ts">
// 类型再导出：容器统一从 SFC 处 `import { type TransactionRow }`，真源在 `./model`
// （结构与格式化拆出去是为了守住 `check_vue_size.mjs` 的 400 行门禁）。
export type { TransactionRow } from "./model";
</script>

<script setup lang="ts">
import { computed } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import { txnTypeLabel } from "@/constants";
import { formatQuantity } from "@/utils/format";
import { pricePrecision } from "@/utils/pricePrecision";
import { txnStatusLabel, txnStatusTag } from "@/utils/transactionStatus";
import {
  compareTradeDate,
  formatTradeDate,
  typeClass,
  type TransactionRow
} from "./model";

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
    /** 状态列（成功 / 失败 / 已撤单 / 可撤单）：资产流水页使用（#2712 收编） */
    showStatus?: boolean;
    /** 备注列：资产流水页使用（#2712 收编） */
    showNotes?: boolean;
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
    showStatus: false,
    showNotes: false,
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
        <!-- `position_id === null` = 持仓已删，流水仍在（#980 的「已删除」标记）。
             标记收进共享组件后，资产流水页 / 账本 Tab 的语义一致，不必各写一段 slot。 -->
        <div
          class="txn-table__asset"
          :class="{
            'txn-table__asset--orphan':
              (row as TransactionRow).position_id === null
          }"
        >
          <ProductDisplay :name="row.position_name" :symbol="row.symbol" />
          <span
            v-if="(row as TransactionRow).position_id === null"
            class="txn-table__deleted"
            >已删除</span
          >
        </div>
      </template>
    </el-table-column>
    <el-table-column
      prop="trade_date"
      label="交易日期"
      min-width="100"
      :sortable="sortable"
      :sort-method="compareTradeDate"
    >
      <template #default="{ row }">{{
        formatTradeDate(row as TransactionRow)
      }}</template>
    </el-table-column>
    <el-table-column label="类型" min-width="60">
      <template #default="{ row }">
        <span :class="typeClass(row.type)">{{
          txnTypeLabel(row.type) || row.type
        }}</span>
      </template>
    </el-table-column>
    <!-- 价格 / 数量：**没有就不画 0**（#2712）。存入 / 取出 / 分红这类行本来没有成交价
         与份额，此前渲染成 `0.0000` / `0.00`，用户读成「这笔交易价格是 0」。
         零 = 无此语义而不是「值是 0」，统一显示 `—`。 -->
    <el-table-column :label="priceLabel || '价格'" min-width="90" align="right">
      <template #default="{ row }">
        <MoneyDisplay
          v-if="row.price"
          :value="row.price"
          :precision="pricePrecision(row.asset_type)"
          :show-sign="false"
          :show-currency="false"
          :auto-color="false"
          size="sm"
        />
        <span v-else class="txn-table__empty">—</span>
      </template>
    </el-table-column>
    <el-table-column
      :label="quantityLabel || '数量'"
      min-width="80"
      align="right"
    >
      <template #default="{ row }">
        <span v-if="row.quantity">{{ formatQuantity(row.quantity) }}</span>
        <span v-else class="txn-table__empty">—</span>
      </template>
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
    <!-- 状态列（#2712）：资产流水页的「成功/失败/已撤单」在别处看不到，但列序与配色
         必须与其它口径同语言，故收进共享组件而不是页面自建 -->
    <el-table-column v-if="showStatus" label="状态" min-width="80">
      <template #default="{ row }">
        <el-tag
          :type="txnStatusTag((row as TransactionRow).status)"
          size="small"
          effect="plain"
        >
          {{ txnStatusLabel((row as TransactionRow).status) }}
        </el-tag>
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
    <!-- 备注列（#2712）：资产流水页原本自建表格里才有，收进共享组件后各表列序一致 -->
    <el-table-column
      v-if="showNotes"
      label="备注"
      min-width="120"
      show-overflow-tooltip
    >
      <template #default="{ row }">
        <span class="txn-table__notes">{{
          (row as TransactionRow).notes || "-"
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

/* 无此语义（价格/数量为 0）与大段空白的备注：弱色，不与真实数字抢注意力 */
.txn-table__empty,
.txn-table__notes {
  color: var(--text-tertiary-ink);
}

/* 已删除持仓的流水：整格置灰（用户扫一眼就知道这条对应的资产没了），
   「已删除」小字与名称同列左对齐，不额外占一列 */
.txn-table__asset--orphan {
  opacity: 0.5;
  filter: grayscale(1);
}

.txn-table__deleted {
  display: block;
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
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
