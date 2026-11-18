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
:deep(.el-table) 覆盖**；行高走全局 44px 基线（`tr` 的 height
是**最小高度**语义， 两行产品单元 + 状态胶囊会自然撑开，不设 size /
row-style）； * - 列宽一律 minWidth，仅固定列（product 左冻结 / _actions 右冻结
/ expand）用 width； * - 产品列必须走 ProductDisplay（表格产品列统一）； * -
行内操作按钮 hover 200ms 淡入（design.md「行内操作交互规范」： *
禁止常驻按钮；:focus-within 时也显现，保键盘可达）； * - 金额一律 MoneyDisplay
且 autoColor=false：**流水金额不表示涨跌**， *
红绿语义只留给真正的涨跌场景（把正数金额全染红是错误语义）； * - 数字列经
formatQuantity / MoneyDisplay 的 .number 走 tabular-nums。 * *
口径统一（本组件即全站口径）： * - 日期：trade_date 优先、confirm_date
兜底（交易日是 用户心智里的「哪天买的」； *
确认日是份额/资金交收到账日，详情页曾只认 trade_date、账本 Tab 只认 *
confirm_date，同一笔交易两端显示可以不同天）； * - 类型着色：买入/存入 =
涨红，卖出/取出 = 跌绿，分红等中性 = info，**一律 -ink 档** * （原值作文字只有
3.86:1 / 2.0:1，白底不达 AA）； * - 数量：formatQuantity（2 位小数 +
千分位，份额不是货币不参与涨跌语义）。 * *
持仓三态与展开详情（docs/design/transaction-flow-redesign.md §三 / §十二-4）： *
- 资产列/账户列/状态列的渲染各自拆成子组件（`TransactionAssetCell` / *
`TransactionAccountCell`），本文件只保留骨架——三态判断、胶囊文案、可点与否 *
都属于 「口径」，混在一个 `v-if` 链里就会重演 #980 的「已删除 + 整格置灰」； * -
展开详情**不** 从列表数据拼：展开事件抛给容器，容器按 id 单独取 `GET *
/api/transactions/{id}/` 回填（「展开哪行取哪行」，见 TransactionDetailPanel）。
*/
<!-- 行类型不在这里再导出：`TransactionRow` 的真源是 `./model`，容器直接从那里
     import type。此前本文件用普通脚本块转一手，而 setup 块又从同一模块 import 了同名
     类型——两个脚本块合并后 TransactionRow 既是局部 import 又被 re-export，
     vue-tsc 生成的 d.ts 会丢掉这个导出，消费方全部报「has no exported member」。
     类型从真源拿，少一层转发就少一处会坏的地方。 -->
<script setup lang="ts">
import { computed, ref } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import { txnTypeLabel } from "@/constants";
import { formatQuantity } from "@/utils/format";
import { pricePrecision } from "@/utils/pricePrecision";
import { txnStatusLabel } from "@/utils/transactionStatus";
import TransactionAccountCell from "./TransactionAccountCell.vue";
import TransactionActionsCell from "./TransactionActionsCell.vue";
import TransactionAssetCell from "./TransactionAssetCell.vue";
import TransactionDetailPanel from "./TransactionDetailPanel.vue";
import TransactionNotesCell from "./TransactionNotesCell.vue";
import { createExpandAccordion, type ExpandableTable } from "./expandAccordion";
import {
  compareTradeDate,
  formatTradeDate,
  statusTone,
  typeClass,
  type TransactionDetailState,
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
    /** 账户列 */
    showAccount?: boolean;
    /** 状态列（成功 / 失败 / 已撤单 / 可撤单）：资产流水页使用（#2712 收编） */
    showStatus?: boolean;
    /** 备注列：资产流水页使用（#2712 收编） */
    showNotes?: boolean;
    /** 操作列：编辑 / 删除按钮（hover 淡入）。删除需确认由容器负责 */
    showEdit?: boolean;
    showDelete?: boolean;
    /**
     * 行展开详情列（设计 §十二 第 4 条）。
     *
     * 展开**不**从列表数据拼详情：展开事件抛给容器，容器按 id 单独取一次
     * `GET /api/transactions/<id>/` 再回填 `detailOf`——「展开哪行取哪行」。
     */
    showExpand?: boolean;
    /** 行 id → 详情状态（容器维护的按需缓存） */
    detailOf?: (id: number) => TransactionDetailState | undefined;
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
    /**
     * 行级编辑判据（可选；不传 = 所有行可编辑，既有调用零变化）。
     * 非空返回值 = 该行编辑按钮置灰，返回值同时作为 tooltip 说明原因。
     * 判据本体（纯函数）与置灰语义见 TransactionActionsCell / design.md。
     */
    editDisabledReason?: (row: TransactionRow) => string;
  }>(),
  {
    showAsset: false,
    showFee: false,
    showAccount: false,
    showStatus: false,
    showNotes: false,
    showEdit: false,
    showDelete: false,
    showExpand: false,
    sortable: false,
    tableId: "transaction-table"
  }
);

const emit = defineEmits<{
  edit: [row: TransactionRow];
  delete: [row: TransactionRow];
  /** 行被展开（容器据此按需请求详情，已缓存则不重复请求） */
  expand: [row: TransactionRow];
  /** 详情取失败后的重试 */
  retryDetail: [row: TransactionRow];
}>();

const hasActions = computed(() => props.showEdit || props.showDelete);

const detailStateOf = (
  row: TransactionRow
): TransactionDetailState | undefined => props.detailOf?.(row.id);

/** `el-table` 实例：手风琴收起其它行时要用它的 `toggleRowExpansion` */
const tableRef = ref<ExpandableTable | null>(null);

/**
 * 行展开走**手风琴**：同时只留一个详情面板展开，打开新的旧的自动关闭
 * （否则两三个面板同时摊开，屏幕被占满、还互相抢「哪行被展开」的注意力）。
 *
 * 判定与「element-plus 同步重入」的解法在 `./expandAccordion` 的文件头注释里，
 * 那里写清了为什么**不能**在回调里直接 `toggleRowExpansion` 收旧行。
 */
const { handleExpandChange } = createExpandAccordion({
  getTable: () => tableRef.value,
  onExpand: (row: TransactionRow) => emit("expand", row)
});
</script>

<template>
  <el-table
    :id="tableId"
    ref="tableRef"
    :data="rows"
    :max-height="maxHeight"
    :default-sort="
      sortable ? { prop: 'trade_date', order: 'descending' } : undefined
    "
    @expand-change="handleExpandChange"
  >
    <!-- 展开详情列（设计 §十二 第 4 条）：确认日 / 来源 / 备注全文 / 费用明细 /
         持仓现状 / 编辑。默认不渲染——账本 Tab 与持仓抽屉不传 showExpand。 -->
    <el-table-column v-if="showExpand" type="expand" width="40">
      <template #default="{ row }">
        <TransactionDetailPanel
          :row="row as TransactionRow"
          :detail="detailStateOf(row as TransactionRow)?.data ?? null"
          :loading="detailStateOf(row as TransactionRow)?.loading ?? false"
          :error="detailStateOf(row as TransactionRow)?.error ?? null"
          :show-edit="showEdit"
          @edit="emit('edit', $event)"
          @retry="emit('retryDetail', $event)"
        />
      </template>
    </el-table-column>
    <!-- 产品列：左冻结（design.md「冻结列」：名称+代码作为首列固定 180-220px，
         用户横向滚动时始终锚定；固定列是唯一允许 width 的列）。
         单元格自己负责「已清仓 / 资金流水 / 无代码」三态，见 TransactionAssetCell。 -->
    <el-table-column v-if="showAsset" label="资产名称" width="200" fixed="left">
      <template #default="{ row }">
        <TransactionAssetCell :row="row as TransactionRow" />
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
    <!-- 状态列（#2712）：成功是常态，**常态不染色**——一屏 20 枚绿色「成功」徽章
         会把注意力从金额上拽走。只有失败 / 可撤单着色，已撤单加描边。 -->
    <el-table-column v-if="showStatus" label="状态" min-width="80">
      <template #default="{ row }">
        <span
          class="txn-status"
          :class="`txn-status--${statusTone((row as TransactionRow).status)}`"
        >
          {{ txnStatusLabel((row as TransactionRow).status) }}
        </span>
      </template>
    </el-table-column>
    <el-table-column
      v-if="showAccount"
      label="账户"
      min-width="100"
      show-overflow-tooltip
    >
      <template #default="{ row }">
        <TransactionAccountCell :row="row as TransactionRow" />
      </template>
    </el-table-column>
    <!-- 备注列（#2712）：资产流水页原本自建表格里才有，收进共享组件后各表列序一致。
         迁移占位备注渲染成安静徽标 + 人话，不再把「（L3，2026-08-14）」这种内部标记甩给用户。 -->
    <el-table-column
      v-if="showNotes"
      label="备注"
      min-width="120"
      show-overflow-tooltip
    >
      <template #default="{ row }">
        <TransactionNotesCell :notes="(row as TransactionRow).notes" />
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

    <!-- 操作列：右冻结。按钮本体与 hover 淡入 / 置灰 tooltip 收在
         TransactionActionsCell（与 TransactionNotesCell 同款拆分，400 行门禁），
         行级编辑判据 editDisabledReason 由容器传入，缺省 = 所有行可编辑（既有调用零变化）。 -->
    <el-table-column v-if="hasActions" label="操作" width="140" fixed="right">
      <template #default="{ row }">
        <TransactionActionsCell
          :row="row as TransactionRow"
          :show-edit="showEdit"
          :show-delete="showDelete"
          :edit-disabled-reason="editDisabledReason"
          @edit="emit('edit', $event)"
          @delete="emit('delete', $event)"
        />
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
/* 类型着色：涨红跌绿（A 股惯例），分红等中性走 info。
   令牌必须用 **-ink 档**：`--color-rise` / `--color-fall` 作正文文字实测只有
   3.86:1 / 2.0:1，白底不达 AA。`-ink` 是同一个色相的「文字级」版本（5.60 / ~5.7），
   语义不变，只是把亮度压到能读。 */
.txn-type--rise {
  color: var(--color-rise-ink);
}

.txn-type--fall {
  color: var(--color-fall-ink);
}

.txn-type--info {
  color: var(--color-info);
}

/* 无此语义（价格/数量为 0）：弱色，不与真实数字抢注意力 */
.txn-table__empty {
  color: var(--text-tertiary-ink);
}

/* 状态列：默认静默（纯文字、次要色），只有异常态才出声。
   「成功」是常态，一屏 20 枚绿色徽章会把注意力从金额上拽走——
   这是设计里「状态默认不出声」那条自律的唯一实现点。 */
.txn-status {
  font-size: var(--text-small);
  color: var(--text-tertiary-ink);
}

.txn-status--danger {
  color: var(--color-danger-ink);
}

.txn-status--warning {
  color: var(--color-warning-ink);
}

/* 已撤单：加描边而不是底色——它是「没发生」，不该和失败一样醒目 */
.txn-status--outline {
  padding: 0 5px;
  color: var(--text-tertiary-ink);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xs);
}

/* 行 hover → 操作列淡入。**必须留在本文件**：`.el-table__row` 是
   `TransactionActionsCell` 根元素的祖先，子组件里的 `:deep()` 只能穿透后代，
   写在那边会编译成 `[data-v-cell] .el-table__row:hover …` 而永不匹配
   （2026-11-12 实测编译产物，表现为鼠标用户看不到编辑 / 删除按钮）。
   整段包进 `:deep()` 才能命中子组件渲染的 `.txn-table__actions`。 */
:deep(.el-table__row:hover .txn-table__actions) {
  opacity: 1;
}
</style>
