<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import CardBlock from "@/components/CardBlock/index.vue";
import SectionHeader from "@/components/SectionHeader/index.vue";
import TransactionTable from "@/components/TransactionTable/index.vue";
import { getTransactions, type TransactionRecord } from "@/api/transactions";
import { getTradeTimeline, type TradeContribution } from "@/api/products";
import {
  PREVIEW_SIZE,
  EXPAND_SIZE,
  needToggle,
  visibleRows as pickVisibleRows,
  shouldFetchMore,
  showsPartial
} from "./transactionSectionMetrics";

/**
 * 详情页「交易记录」区块（#2104 · 设计 §4.2 · 渐进披露 #2160）。
 *
 * 数据来自 `GET /api/transactions/?symbol=`，过滤在**后端下推到 SQL**
 * （#2104 新增的 symbol 参数），不在前端拉全量再筛——后者是数据策略硬约束 §6 明令禁止的。
 *
 * 口径：
 * - 按**交易日期**倒序（与后端 `build_transaction_list` 的
 *   `COALESCE(trade_date, confirm_date) DESC, id DESC` 一致；也与本表 `TransactionTable`
 *   的展示口径同源——交易日优先、确认日兜底）。**不是 `created_at`**：那是写入时间，
 *   批量导入的历史流水会让列表退化成「导入批次顺序」，看起来像正序（#2171 反馈修正）；
 * - 金额/份额基于 money 换算（分 → 元、份 → 份），不直接对 float 做乘除；
 * - 流水金额不表示涨跌，显式关闭 `MoneyDisplay` 的 autoColor——红绿语义只留给
 *   真正的涨跌场景，把正数金额全染红是错误语义。
 *
 * 渐进披露（#2160）：首版写死 `per_page: 10` 且**没有任何提示**，是详情页 17 个区块里
 * 唯一的静默截断——用户既不知道还有更多、也不知道一共多少条。改为三级：
 *   1. 折叠 10 条；
 *   2. 「展开全部 N 条」**就地展开**，表内滚动（高度上限交给 el-table 的 max-height，
 *      由它原生固定表头，比手写 sticky 稳）；
 *   3. 总量超出展开上限 → 「查看全部流水」跳 `TransactionList`（那边本就有完整分页）。
 *
 * 形态取自 `docs/working-notes/product-detail-research-2026-10-12.md` §3.3 优先级 1
 * （top10 紧凑表 + 卡内就地展开），与同页 `ProductHoldingSection.vue` 保持一致；
 * 该文 §3.3 优先级 4 明确否决「默认渲染全表 + 内部滚动」，故滚动**只在展开态**启用。
 *
 * ## 当时成本 / 收益贡献两列（#2171 P2）
 *
 * 数据来自 `GET /api/products/trade-timeline/` 的 contributions（按 txn_id 关联），
 * 与走势卡叠加层同源同口径；本卡自行取数（各区块独立取数是详情页既有形态，
 * 时间线端点是单条索引查询 + 内存重放，代价低于跨组件抬 state）。拉取失败两列
 * 显示 `--`，主表不受影响（设计 §6 诚实降级）。
 */

/** 仅可交易品类渲染本区块；manager / portfolio / index 等查看型详情页整块不渲染 */
const TRADEABLE_ASSET_TYPES = [
  "fund",
  "money_fund",
  "stock",
  "etf",
  "bond",
  "convertible_bond"
];

/**
 * 折叠态行数与展开上限都住在 `transactionSectionMetrics`（含判定与单测），
 * 这里只做「把 ref 喂给纯函数」，避免同一口径出现第二份实现。
 */

/** 展开态表内滚动的高度上限（px）。与 `holding-section__table-wrap--scroll` 同值。 */
const TABLE_MAX_HEIGHT = 420;

const props = defineProps<{
  /** 产品代码（后端经 symbol_scope 两步法匹配流水快照的真实写法） */
  symbol: string;
  /** 资产类型：非可交易品类整块不渲染、也不发请求 */
  assetType: string;
}>();

const router = useRouter();

const renderable = computed(() =>
  TRADEABLE_ASSET_TYPES.includes(props.assetType)
);

const loading = ref(false);
/** 展开态的增量加载：此时已有 10 行在屏上，不能再换成整块骨架屏（那等于把已给的信息收回去） */
const expanding = ref(false);
const transactions = ref<TransactionRecord[]>([]);
/** 后端返回的该标的流水总数；`0` 表示尚未取数（与「确实为 0 条」靠 hasTransactions 区分） */
const total = ref(0);
const errorMsg = ref<string | null>(null);
const expanded = ref(false);

/**
 * 「当时成本 / 收益贡献」两列的数据源（#2171 P2）。
 *
 * 与走势卡的时间线是**两次独立请求**：本卡与走势卡各自取自己需要投影——
 * 时间线端点是单条索引查询 + 内存重放，代价远低于为共享一份数据在两个组件间
 * 抬 state（详情页各区块本就各自取数，见 ProductFundSection 等同侪）。
 * 拉取失败静默降级：两列显示「—」，主表不受影响（设计 §6）。
 */
const contributionMap = ref<Map<number, TradeContribution>>(new Map());

async function loadContributions() {
  if (!renderable.value) return;
  try {
    const res = await getTradeTimeline({ symbol: props.symbol });
    contributionMap.value = new Map(
      (res.data.contributions ?? [])
        .filter(c => c.txn_id !== null)
        .map(c => [c.txn_id as number, c])
    );
  } catch {
    contributionMap.value = new Map();
  }
}

const hasTransactions = computed(() => transactions.value.length > 0);

/**
 * 必须用 `total` 判断，不能用 `transactions.length`：折叠态只取了 PREVIEW_SIZE 条，
 * `transactions.length` 恒等于 10——拿它判断会在「恰好 10 条」时永远不出按钮，
 * 在「100 条」时也只按已取到的量判断，两个方向都错。
 */
const needToggleBtn = computed(() => needToggle(total.value));

/** 折叠时只渲染前 10 行；展开时渲染已取到的全部 */
const visibleRows = computed(() =>
  pickVisibleRows(transactions.value, expanded.value)
);

/** 已取到的量少于总量、且用户已展开 → 明示当前看到的是切片，并给出第 3 级出口 */
const showsPartialWhenExpanded = computed(() =>
  showsPartial(expanded.value, transactions.value.length, total.value)
);

/**
 * 「查看全部流水」的落点是 `TransactionList`（`/transactions`）而**不是**账本详情页：
 * 账本侧要 `positionId` 才能打开流水抽屉，而详情页看的可能压根是没持有的标的
 * （无持仓 → 无 ledger / positionId，这条路直接断）；且 #2104 的初衷正是
 * 「不再让用户绕到账本」。`TransactionList` 才是为查明细设计的页面，且本就有完整分页。
 */
const allTransactionsLink = computed(() => ({
  name: "TransactionList",
  query: { symbol: props.symbol }
}));

async function loadTransactions(perPage: number) {
  loading.value = true;
  errorMsg.value = null;
  try {
    const { data, total: t } = await getTransactions({
      symbol: props.symbol,
      per_page: perPage
    });
    transactions.value = data;
    total.value = t;
  } catch (err) {
    console.error("加载交易记录失败", err);
    errorMsg.value = "加载失败，请稍后重试";
  } finally {
    loading.value = false;
  }
}

// 挂载时只取折叠态所需的量（非可交易品类不请求）。
// 刻意不在这里取满 EXPAND_SIZE：绝大多数用户不会展开，为不会看的行付请求代价不划算。
if (renderable.value) {
  void loadTransactions(PREVIEW_SIZE);
  void loadContributions();
}

async function toggleExpanded() {
  if (expanded.value) {
    expanded.value = false;
    return;
  }
  expanded.value = true;
  // 首次展开才补取全量；已取够时不重复发请求
  if (shouldFetchMore(transactions.value.length, total.value)) {
    expanding.value = true;
    await loadTransactions(EXPAND_SIZE);
    expanding.value = false;
  }
}

/**
 * 换产品时复位。详情页路由带 `keepAlive: true`，切标的**不会**重新挂载本组件——
 * 不 watch 就会残留上一只标的的展开状态与行数，用户点开另一只基金看到的还是
 * 「展开着 47 条」。这里同时清空数据，避免旧 symbol 的行在新 symbol 下闪一帧。
 */
watch(
  () => props.symbol,
  (next, prev) => {
    if (!prev || next === prev) return;
    expanded.value = false;
    expanding.value = false;
    transactions.value = [];
    total.value = 0;
    contributionMap.value = new Map();
    if (renderable.value) {
      void loadTransactions(PREVIEW_SIZE);
      void loadContributions();
    }
  }
);

/** 行 → 当时成本（元）；无重放数据（拆分等未参与类型 / 拉取失败）为 null。
    入参不标 TransactionRecord：el-table 默认槽的 row 是 DefaultRow（无索引签名，
    整个对象传不进强类型函数），与模板里其余列一样按属性访问即可。 */
function rowField(
  row: unknown,
  field: "cost_after_yuan" | "profit_contribution_yuan"
) {
  const id = (row as { id?: number }).id;
  if (typeof id !== "number") return null;
  return contributionMap.value.get(id)?.[field] ?? null;
}

function goAllTransactions() {
  void router.push(allTransactionsLink.value);
}
</script>

<template>
  <!-- SectionHeader 必须是 CardBlock 的**直接子节点**：CardBlock 只有一个匿名
       <slot />，没有 header 具名插槽——<template #header> 会被 Vue 静默丢弃，
       整张卡的标题跟着消失（#2104 首版正是这么写的，交易记录卡一直无标题；
       同款坑在 ProductPositionSection 的注释里有记录）。 -->
  <CardBlock v-if="renderable" class="transaction-section">
    <SectionHeader title="交易记录" />

    <div v-if="loading" class="transaction-section__loading">
      <el-skeleton :rows="3" animated />
    </div>

    <div v-else-if="errorMsg" class="transaction-section__error">
      <span>{{ errorMsg }}</span>
    </div>

    <div v-else-if="!hasTransactions" class="transaction-section__empty">
      <span>暂无交易记录</span>
    </div>

    <template v-else>
      <!-- 总数与表同屏、不藏脚注：首版的静默截断让用户以为「这就是全部」（#2160）。
           有更多时才提示「最近 10 条」，否则「共 N 条」本身就是完整信息。 -->
      <p class="transaction-section__count">
        共 {{ total }} 条
        <span v-if="needToggleBtn && !expanded">
          （当前显示最近 {{ PREVIEW_SIZE }} 条）
        </span>
      </p>

      <!-- 表格本体走全站统一的 TransactionTable（#2104 验收「同一组件」：
           此前详情页 / 账本 Tab / 持仓抽屉三套表格，字段与口径全不一致）。
           本容器只负责渐进披露（折叠 10 条 → 就地展开 → 出口）与文案。 -->
      <TransactionTable
        :rows="visibleRows"
        mode="compact"
        show-account
        table-id="transaction-detail-table"
        :max-height="expanded && needToggleBtn ? TABLE_MAX_HEIGHT : undefined"
      >
        <!-- #2171 P2 扩展列：TransactionTable 是公共组件（#2104 统一），不带这两列；
             经其 #extra-columns slot 注入。字段口径归本容器（交易时间线重放）。
             注意：交易日期/类型/数量/价格/金额/账户六列由 TransactionTable 基础列
             无条件渲染，此处不得重复注入（重复曾致详情页 14 列、6 列双份）。 -->
        <template #extra-columns>
          <!-- 当时成本 / 收益贡献（#2171 P2）：由交易时间线重放得出（与走势卡
             同源口径），无重放数据的类型（拆分等）显示 — -->
          <el-table-column label="当时成本" width="100">
            <template #default="{ row }">
              <MoneyDisplay
                :value="rowField(row, 'cost_after_yuan')"
                :decimals="2"
                :auto-color="false"
              />
            </template>
          </el-table-column>
          <el-table-column label="收益贡献" width="100">
            <template #default="{ row }">
              <!-- 收益贡献是盈亏语义：开 auto-color（涨红跌绿）；无重放数据时
                 MoneyDisplay 空值渲染 --（与价格/金额列一致） -->
              <MoneyDisplay
                :value="rowField(row, 'profit_contribution_yuan')"
                :decimals="2"
                :show-sign="true"
              />
            </template>
          </el-table-column>
        </template>
      </TransactionTable>

      <!-- 两列的口径脚注：收益贡献是盈亏语义（涨红跌绿），当时成本是事实值（中性色）。
           写清楚「怎么算的」，用户才不会把「当时成本 0」误读成免费拿到。 -->
      <p class="transaction-section__footnote">
        当时成本 / 收益贡献由交易时间线重放得出：成本含手续费；收益贡献 =
        卖出净回款 − 释放成本，分红按 +金额，买入记 0（建仓未实现）。
      </p>

      <button
        v-if="needToggleBtn"
        type="button"
        class="transaction-section__more"
        :aria-expanded="expanded"
        aria-controls="transaction-detail-table"
        :disabled="expanding"
        @click="toggleExpanded"
      >
        {{ expanding ? "加载中…" : expanded ? "收起" : `展开全部 ${total} 条` }}
      </button>

      <!-- 第 3 级出口：展开后仍看不全时，把「查全部」交给本就是为查明细设计的流水页。
           只在展开态出现——折叠态就摆这条链接，是在给一个多数用不到的出口加噪声。 -->
      <p v-if="showsPartialWhenExpanded" class="transaction-section__footnote">
        仅显示最近 {{ transactions.length }} 条 ·
        <button
          type="button"
          class="transaction-section__link"
          @click="goAllTransactions"
        >
          查看全部流水
        </button>
      </p>
    </template>
  </CardBlock>
</template>

<style scoped>
.transaction-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.transaction-section__loading {
  padding: 16px;
}

.transaction-section__error {
  padding: 16px;

  /* #2314：错误提示原用 --color-fall（跌绿），双重语义错误——错误状态不该用涨跌色，
     且「绿色错误文字」违反红涨绿跌直觉。改走危险文字级令牌（#1602 已将
     --color-danger-system 并入 --color-danger，文字级用 -ink，白底 4.74:1）。 */
  color: var(--color-danger-ink);
  text-align: center;
}

.transaction-section__empty {
  padding: 24px;
  color: var(--text-tertiary);
  text-align: center;
}

.transaction-section__count,
.transaction-section__footnote {
  margin: 0;
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

/* 展开/收起是主操作，给品牌色；「查看全部流水」是次级出口，弱化成普通链接 */
.transaction-section__more {
  align-self: flex-start;
  padding: 0;
  font-size: var(--text-label);
  color: var(--brand-700, var(--brand-500));
  cursor: pointer;
  background: none;
  border: none;
}

.transaction-section__more:hover:not(:disabled) {
  text-decoration: underline;
}

.transaction-section__more:disabled {
  color: var(--text-tertiary);
  cursor: default;
}

.transaction-section__more:focus-visible,
.transaction-section__link:focus-visible {
  outline: 2px solid var(--brand-500);
  outline-offset: 2px;
  border-radius: var(--radius-sm, 4px);
}

.transaction-section__link {
  padding: 0;
  font-size: var(--text-label);
  color: var(--brand-700, var(--brand-500));
  cursor: pointer;
  background: none;
  border: none;
}

.transaction-section__link:hover {
  text-decoration: underline;
}
</style>
