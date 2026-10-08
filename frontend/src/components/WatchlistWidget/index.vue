<!--
  WatchlistWidget · 首页「置顶资产 / 持仓市值最大资产」紧凑摘要表（#1954 重做）

  ── 为什么是「紧凑摘要」而不是自选页那张表的缩小版──
  首页只有 5 行、通栏满宽、要的是「一眼看到关键数」，与自选页的高密度可排序表
  是两种形态。故本组件保留原生 <table>（不套 el-table），样式本地维护——
  这是对 el-table.css 全局基线的**已声明例外**，改样式只改本文件。

  ── 与自选页的对齐契约（#1954，用户反馈「数据列应向自选页面对齐」）──
  本表每一列的口径 / 呈现形态都与 columnDefs.ts + columnRenderers.tsx 同源，
  改动其中一侧必须同步另一侧：
    · 产品信息  → ProductDisplay **compact** 两行（名称 / #代码 + 类型标签）
    · 最新价    → MoneyDisplay，精度 pricePrecision(asset_type)，
                  无行情 → --；静态价把 price_as_of 挂title 标注数据日期
    · 涨跌幅    → RiseFallText，null → --
    · 持仓市值  → MoneyWithRatio（金额在上 + 占比在下），金额不带正负号
    · 持仓收益  → MoneyWithRatio（金额在上 + 收益率在下），金额带正负号、不带 ¥
  刻意**不搬**的三列：「添加自选日」「持有数量」「走势」——对「即时行情摘要」
  信息价值低且会撑宽首页卡片，需要时去自选页看。

  ── 图标语义（全站统一，勿在本组件另立）──
  图钉 mdi:pin = 置顶；星标 ep:star = 特别关注。与自选页 renderActions 一致。
  此前本组件用黄色星标表示置顶，与自选页的「星标=特别关注」直接冲突（#1954）。
-->
<template>
  <div
    class="watchlist-widget rounded-2xl p-6 h-full flex flex-col"
    :style="{
      backgroundColor: 'var(--bg-card)',
      boxShadow: 'var(--shadow-raised)',
      border: '1px solid var(--border-light)'
    }"
  >
    <div class="flex-1 flex flex-col min-h-20">
      <!-- 空状态 -->
      <div
        v-if="displayItems.length === 0 && !loading"
        class="flex-1 flex flex-col items-center justify-center border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer"
        :style="{
          borderColor: 'var(--border-light)',
          color: 'var(--text-tertiary-ink)'
        }"
        role="button"
        tabindex="0"
        @keydown.enter="emit('add')"
        @click="emit('add')"
      >
        <IconifyIconOffline
          icon="ep:star"
          class="text-3xl mb-3"
          :style="{ color: 'var(--text-tertiary-ink)' }"
        />
        <p
          class="text-base font-medium mb-1"
          :style="{ color: 'var(--text-primary)' }"
        >
          暂无自选资产
        </p>
        <p class="text-xs">点击右上角「添加」开始关注资产</p>
      </div>

      <!-- 加载骨架 -->
      <div v-if="loading" class="space-y-3 w-full">
        <div
          v-for="n in 5"
          :key="n"
          class="h-10 rounded-lg animate-pulse"
          :style="{ backgroundColor: 'var(--bg-soft)' }"
        />
      </div>

      <!-- 表格 -->
      <div
        v-if="!loading && displayItems.length > 0"
        class="flex-1 flex flex-col overflow-x-auto"
      >
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
              v-for="item in displayItems"
              :key="item.id"
              class="wl-tr"
              :class="{ 'is-pinned': item.is_pinned === true }"
              tabindex="0"
              @click="handleItemClick()"
              @keydown.enter="handleItemClick()"
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
                   金额是余额不是涨跌 → 不带正负号；占比恒为正 → 中性色，不套涨红跌绿。 -->
              <td class="wl-td wl-td--num">
                <MoneyWithRatio
                  :value="item.position_market_value"
                  :ratio="marketValueRatio(item)"
                  :show-sign="false"
                  :show-currency="true"
                  :ratio-auto-color="false"
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
                <el-tooltip content="在自选页查看与操作" placement="top">
                  <button
                    type="button"
                    class="wl-action"
                    :aria-label="`在自选页查看 ${item.display_name || item.symbol}`"
                    @click.stop="handleItemClick()"
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { getHomeSummary, type HomeSummaryItem } from "@/api/watchlist";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import MoneyWithRatio from "@/components/MoneyWithRatio/index.vue";
import { pricePrecision } from "@/utils/pricePrecision";
import RiseFallText from "@/components/RiseFallText/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import { IconifyIconOffline } from "@/components/ReIcon";

/**
 * 只对外抛 `add`（空态点击 → 打开添加弹窗）。
 * 此前还有一个 `select` 事件，但欢迎页的处理器是空函数（`// TODO: 跳转到资产详情`），
 * 事件抛出去无人消费——行点击的跳转改由本组件内部完成（#1954）。
 * 待单标的详情页（#1909）落地后，再把跳转收回父组件、恢复 `select` 事件。
 */
const emit = defineEmits<{
  add: [];
}>();

const router = useRouter();

const items = ref<HomeSummaryItem[]>([]);
const loading = ref(true);

const hasPinned = computed(() =>
  items.value.some(item => item.is_pinned === true)
);

const displayItems = computed(() => {
  if (hasPinned.value) {
    return items.value.filter(item => item.is_pinned === true);
  }
  return items.value;
});

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
 * 持仓市值占比（%）。分母是**本表实际展示行**的市值之和。
 *
 * 两个关键约束：
 * 1. 分母必须是 displayItems 而非 items —— 有置顶时表格只渲染置顶那些行，
 *    拿全量当分母会让「占比之和 ≠ 100%」，用户一眼看出数字不对；
 * 2. 它不是「占总资产比例」—— 本组件只拿到 ≤5 行的摘要数据，拿不到全量自选总市值。
 *    故列头 title 与文案都不宣称占比口径。
 */
const totalMarketValue = computed(() =>
  displayItems.value.reduce((sum, i) => sum + (i.position_market_value ?? 0), 0)
);

function marketValueRatio(item: HomeSummaryItem): number | null {
  const total = totalMarketValue.value;
  if (total <= 0) return null;
  return ((item.position_market_value ?? 0) / total) * 100;
}

/**
 * 行点击 / 操作按钮 → 去自选页。
 * 此前整行 cursor-pointer 但落地是个空函数，行内还有「快速记账」按钮 emit 到那里，
 * 按钮有 hover 反馈却点了什么都不发生——「像个 demo」的直接来源（#1954）。
 * 现阶段没有单标的详情页可跳（#1909 待做），去自选页是唯一诚实且可用的去向。
 */
function handleItemClick() {
  void router.push("/watchlist");
}

async function fetchData() {
  loading.value = true;
  try {
    const res = await getHomeSummary();
    items.value = res.data ?? [];
  } catch (e) {
    console.error("Failed to fetch home summary:", e);
  } finally {
    loading.value = false;
  }
}

onMounted(fetchData);
defineExpose({ hasPinned });
</script>

<style scoped>
/* ── 表格骨架（#1954）────────────────────────────────────────────
   横线规则只有一处：.wl-th / .wl-td 的 border-bottom。
   此前用 tbody 的 Tailwind `divide-y` 给 tr 加 border-top，在默认
   border-collapse:separate 下与 th 的 border-b 绘制不一致，出现粗细不一的线；
   组件顶部还有一条独立的说明文字 border-b，与表头线挤在一起。
   现在：表头一条线 + 每个数据行一条线，粗细统一为 1px var(--border-light)，
   末行无线（:last-child 去掉），也不再有额外横线。 */
.wl-table {
  border-collapse: collapse;
  border-spacing: 0;
}

.wl-th {
  padding: 0 0 10px;
  font-size: 12px;
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
  background-color: var(--bg-hover);
  outline: none;
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
  font-size: 12px;
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
  font-size: 14px;
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
