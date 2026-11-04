<script setup lang="ts">
import type { HomeSummaryItem } from "@/api/watchlist";
import { useInvestmentTotalMv } from "@/composables/useInvestmentTotalMv";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import MoneyWithRatio from "@/components/MoneyWithRatio/index.vue";
import { pricePrecision } from "@/utils/pricePrecision";
import RiseFallText from "@/components/RiseFallText/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";

/**
 * 首页自选摘要表（#1954 / #980 拆分自 `WatchlistWidget/index.vue`）。
 *
 * 只负责「行怎么画」：每列的口径 / 呈现形态与自选页 columnDefs + columnRenderers 同源，
 * 改动其中一侧必须同步另一侧（详见父组件的契约说明）。
 * 取数、空态、骨架仍留在父组件——本组件是纯展示，`items` 变即重渲染。
 */
defineOptions({ name: "WatchlistWidgetTable" });

defineProps<{
  items: HomeSummaryItem[];
}>();

const emit = defineEmits<{
  select: [item: HomeSummaryItem];
}>();

/**
 * 展示行内是否有真实持仓（holding_quantity > 0）。
 * 纯观察标的（只加入自选、未建仓）持仓字段后端均为 null，
 * 这里再判一次是为了把「有持仓但盈亏恰为 0」与「无持仓」区分开：
 * 前者要显示 ¥0.00 / 0.00%，后者显示 --。
 */
function hasHolding(item: HomeSummaryItem): boolean {
  return (item.holding_quantity ?? 0) > 0;
}

/**
 * 分母 = 投资类产品总市值（GitHub #2239，与自选页同口径，#1954 对齐契约）。
 * 取数 / 回退语义与单例共享见 composables/useInvestmentTotalMv——
 * 此前用「本表实际展示行市值之和」当分母，置顶 ≤5 行的摘要占比彼此孤立、
 * 也与自选页对不上（2026-10-16 用户反馈）。
 */
const { investmentTotalMv } = useInvestmentTotalMv();

/**
 * 持仓市值占**投资类产品总市值**的比例（%）（#2239）。
 *
 * 分母取不到（接口失败 / 无投资类持仓）返回 null，隐藏比例行——
 * 不回退到「本表合计」等旧口径，错误口径比没有数字更伤。
 */
function marketValueRatio(item: HomeSummaryItem): number | null {
  const total = investmentTotalMv.value;
  if (total == null || total <= 0) return null;
  return ((item.position_market_value ?? 0) / total) * 100;
}

/** 行点击 / 操作按钮 → 抛 `select` 给父组件（欢迎页）跳产品详情 */
function handleItemClick(item: HomeSummaryItem) {
  emit("select", item);
}
</script>

<template>
  <div class="flex-1 flex flex-col overflow-x-auto">
    <!-- border-collapse: collapse 是硬要求（#1954）：默认的 border-collapse:separate
         下 tr 上的边框绘制与 th 的 border-b 对不齐，横线粗细不一、位置漂移。
         配合 .wl-table 的 border-bottom 规则，行间线才是干净的 1px。 -->
    <table class="wl-table w-full text-sm">
      <thead>
        <tr>
          <th class="wl-th wl-th--product">代码/名称</th>
          <th class="wl-th wl-th--num">最新价</th>
          <th class="wl-th wl-th--num">涨跌幅</th>
          <th
            class="wl-th wl-th--num"
            title="占比 = 本行市值 ÷ 本区块全部展示行的市值之和（非总资产占比）"
          >
            持仓市值
          </th>
          <th class="wl-th wl-th--num">持仓收益</th>
          <th class="wl-th wl-th--num wl-th--actions">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in items"
          :key="item.id"
          class="wl-tr"
          :class="{ 'is-pinned': item.is_pinned === true }"
          tabindex="0"
          @click="handleItemClick(item)"
          @keydown.enter="handleItemClick(item)"
        >
          <td class="wl-td wl-td--product">
            <!-- 内层 flex 包裹：td 本身不能设 display:flex（会破坏表格单元格布局），
                 而 ProductDisplay 根节点是 block 级 div，直接与置顶图钉并排会换行。 -->
            <div class="wl-product">
              <!-- 置顶标记：图钉（不是星标——星标在全站表示「特别关注」）。
                   内联在名称前，与自选页 renderProduct 的置顶标记同位置同语义。
                   置顶行的淡品牌底由 .is-pinned 提供，与自选页 .is-pinned-row 一致。 -->
              <span
                v-if="item.is_pinned === true"
                class="wl-pin"
                title="已置顶"
                aria-label="已置顶"
                role="img"
              >
                <IconifyIconOffline icon="mdi:pin" />
              </span>

              <!-- compact 两行：名称 / #代码 + 类型标签。与自选页 product 列同一组件、
                   同一形态（此前用默认两行模式且额外挂了一个 AssetTypeBadge，
                   导致基金显示「基金 基」重复、股票因后端缺 type_label 完全空白）。 -->
              <ProductDisplay
                compact
                class="min-w-0 flex-1"
                :name="item.display_name || item.symbol"
                :symbol="item.symbol"
                :type-label="item.type_label"
              />
            </div>
          </td>

          <!-- 最新价：无行情 → --（不是 0.00，0.00 会被误读成「跌到底」）。
               静态价把数据日期挂 title，避免盘中看到上一交易日价被当成实时价。 -->
          <td class="wl-td wl-td--num">
            <span
              v-if="item.current_price != null"
              :title="
                item.price_as_of
                  ? `数据日期 ${item.price_as_of}（最近交易日收盘价 / 确认净值）`
                  : undefined
              "
            >
              <MoneyDisplay
                :value="item.current_price"
                :precision="pricePrecision(item.asset_type)"
                :show-sign="false"
                :show-currency="false"
                size="sm"
              />
            </span>
            <span v-else class="wl-empty">--</span>
          </td>

          <!-- 涨跌幅 -->
          <td class="wl-td wl-td--num">
            <RiseFallText
              v-if="item.change_pct != null"
              :value="item.change_pct"
              suffix="%"
              size="sm"
            />
            <span v-else class="wl-empty">--</span>
          </td>

          <!-- 持仓市值：金额 + 占展示行市值合计的比例（自选页同形态）。
               金额是余额不是涨跌 → 不带正负号；占比恒为正的仓位权重 → 中性色，
               同样不带 +/- 号（show-ratio-sign，#2209），不套涨红跌绿。 -->
          <td class="wl-td wl-td--num">
            <MoneyWithRatio
              :value="item.position_market_value"
              :ratio="marketValueRatio(item)"
              :show-sign="false"
              :show-currency="true"
              :ratio-auto-color="false"
              :show-ratio-sign="false"
              money-size="sm"
            />
          </td>

          <!-- 持仓收益：金额 + 收益率。与自选页 renderMoneyRatio 的「直接字段列」
               分支同口径——无真实持仓时 value/ratio 同为 null，由组件显示 --。 -->
          <td class="wl-td wl-td--num">
            <MoneyWithRatio
              :value="hasHolding(item) ? item.holding_pnl : null"
              :ratio="hasHolding(item) ? item.holding_pnl_percent : null"
              :show-sign="true"
              :show-currency="false"
              money-size="sm"
            />
          </td>

          <!-- 操作列：只放能「对这一行做什么」的控件。
               此前这里混进了类型 / 持仓状态标签（AssetTypeBadge），
               语义错位且与产品信息列重复（#1954）。 -->
          <td class="wl-td wl-td--num wl-td--actions">
            <el-tooltip content="查看产品详情" placement="top">
              <button
                type="button"
                class="wl-action"
                :aria-label="`查看 ${item.display_name || item.symbol} 详情`"
                @click.stop="handleItemClick(item)"
              >
                <IconifyIconOffline icon="ep:right" />
              </button>
            </el-tooltip>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 「查看全部」入口：后端 build_home_summary 最多返回 5 条，
         原footer 条件写的是 `items.length > 10` —— 该条件恒不成立，
         这段「还有 N 条，查看全部 →」从未渲染过（死代码，#1954）。
         区块标题行右侧本就有「查看全部」按钮（welcome/index.vue），
         摘要表内不再重复一份。 -->
  </div>
</template>

<style scoped>
/* ── 表格骨架（#1954）────────────────────────────────────────────
   横线规则只有一处：.wl-th / .wl-td 的 border-bottom。
   此前用 tbody 的 Tailwind `divide-y` 给 tr 加 border-top，在默认
   border-collapse:separate 下与 th 的 border-b 绘制不一致，出现粗细不一的线；
   组件顶部还有一条独立的说明文字 border-b，与表头线挤在一起。
   现在：表头一条线 + 每个数据行一条线，粗细统一为 1px var(--border-light)，
   末行无线（:last-child 去掉），也不再有额外横线。 */
.wl-table {
  border-spacing: 0;
  border-collapse: collapse;
}

.wl-th {
  padding: 0 0 10px;
  font-size: var(--text-label);
  font-weight: 400;
  line-height: 1.4;
  color: var(--text-tertiary-ink);
  text-align: right;
  white-space: nowrap;
  border-bottom: 1px solid var(--border-light);
}

.wl-th--product {
  width: 38%;
  padding-right: 16px;
  text-align: left;
}

/* 操作列不参与等宽分配：给它固定宽度，避免长名称把操作按钮挤出可视区 */
.wl-th--actions,
.wl-td--actions {
  width: 56px;
  padding-left: 12px;
}

.wl-td {
  padding: 10px 0;
  vertical-align: middle;
  border-bottom: 1px solid var(--border-light);
}

/* 产品信息单元格：内层 flex（置顶图钉 + ProductDisplay 两行块并排）。
   min-width:0 让 ProductDisplay 内部的 ellipsis 生效——列宽不够时名称截断并
   由 title 兜全名，而不是把图钉挤出单元格。 */
.wl-product {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
}

.wl-td--product {
  padding-right: 16px;
}

.wl-td--num {
  text-align: right;
  white-space: nowrap;
}

.wl-tr:last-child .wl-td {
  border-bottom: none;
}

/* 行 hover：与自选页行内交互一致（--bg-hover），键盘聚焦同强度，
   保证 tab 到该行时也有可见反馈（行可聚焦，见 tabindex）。 */
.wl-tr {
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.wl-tr:hover,
.wl-tr:focus-visible {
  outline: none;
  background-color: var(--bg-hover);
}

/* 置顶行：极淡品牌底，让「上面这一块是置顶的」一眼可辨。
   与自选页 .is-pinned-row（WatchlistTableSection.vue）同款，hover 再递进一档。 */
.wl-tr.is-pinned {
  background-color: var(--brand-100);
}

.wl-tr.is-pinned:hover,
.wl-tr.is-pinned:focus-visible {
  background-color: var(--brand-200);
}

/* 置顶图钉：品牌色 token（暗色模式自动适配），
   不再硬编码 text-yellow-500（#1954）。 */
.wl-pin {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 18px;
  color: var(--brand-700);
}

/* 空值占位：与 el-table.css 的 .cell-pending 同一语言（灰字，不用胶囊——
   胶囊是「可点击去补全」的语义，这里只是「没有数据」，不能误导）。 */
.wl-empty {
  font-size: var(--text-label);
  color: var(--text-tertiary-ink);
}

/* 操作按钮：与自选页操作列同一套弱显语言（常驻 45% → 行 hover 全亮），
   但用原生 button 而非 el-button circle：单按钮无需圆形包裹，
   圆形会让一个箭头图标看起来像可点的头像。 */
.wl-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  font-size: var(--text-small);
  color: var(--text-secondary);
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  opacity: 0.45;
  transition:
    opacity 150ms ease,
    color 150ms ease;
}

.wl-tr:hover .wl-action,
.wl-tr:focus-visible .wl-action,
.wl-action:hover,
.wl-action:focus-visible {
  color: var(--brand-700);
  opacity: 1;
}

.wl-action:focus-visible {
  outline: 1px solid var(--brand-400);
  outline-offset: 1px;
}
</style>
