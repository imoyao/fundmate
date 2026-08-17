/**
 * watchlist 自选表格单元格渲染器注册表
 *
 * 对应 issue #995（umbrella #1022）。
 * 与 columnDefs.ts 配套：模板 v-for 列定义，按 def.renderer 分发到本文件的函数式组件。
 *
 * 核心职责（设计文档 §4）：把 index.vue 模板里散落的
 *   v-if="realtimeEnabled && getValuationItem(row.symbol)"
 * 双分支「实时覆盖静态」逻辑，内聚进 money/riseFall renderer，模板不再出现双分支。
 *
 * 约束（AGENTS.md / realtime-data-sources.md）：不得在此新开 JSONP 通道；
 * 实时数据一律来自 ctx.getValuationItem（useRealtimeQuotes 链路）。
 *
 * ── 维护者须知 ──
 * 本注册表的 product / actions renderer 当前在 index.vue 中【未启用】
 * （index.vue 的 product/marker/selection/actions 四列仍保留原模板，
 * 原因见 docs/spec/watchlist-column-defs.md §3 实施偏差）。这两个 renderer
 * 是 #995 步骤 3 的预备实现：待 #980 重构合入、数据列驱动稳定后，
 * index.vue 将切换到用本注册表渲染 product/actions，届时删除对应硬编码列。
 * 在此之前若改 product/actions 交互，需同步更新本文件与 index.vue 两处。
 */

import { h, type FunctionalComponent, type VNode } from "vue";
import MoneyDisplay from "@/components/MoneyDisplay/index.vue";
import RiseFallText from "@/components/RiseFallText/index.vue";
import MoneyWithRatio from "@/components/MoneyWithRatio/index.vue";
import ProductDisplay from "@/components/ProductDisplay/index.vue";
import { formatDate } from "@/utils/date";
import type { ColumnDef, ColumnRenderer, WatchlistRow } from "./columnDefs";

/** 实时估值项（与 useRealtimeQuotes.getValuationItem 返回结构一致） */
export interface ValuationItem {
  currentPrice?: number;
  changePct?: number;
}

/** 派生值结果（组合计算列，由 index.vue 注入计算函数） */
export interface DerivedValue {
  value: number;
  ratio: number;
}

/** 渲染上下文：承载页面级状态与方法（避免 renderer 直接耦合大组件） */
export interface RenderCtx {
  /** 是否开启实时估值 */
  realtimeEnabled: boolean;
  /** 取某 symbol 的实时估值项 */
  getValuationItem: (symbol: string) => ValuationItem | undefined;
  /** 全部标签（用于 product 列渲染 tag chips） */
  allTags: { id: number; name: string; color?: string }[];
  /** 派生计算列的取值函数（注入 index.vue 的 addedReturnAmount 等） */
  derived: (kind: "addedReturn" | "marketValue", row: WatchlistRow) => DerivedValue;
  /** 操作回调（actions 列） */
  actions: {
    togglePin: (row: WatchlistRow) => void;
    toggleFavorite: (row: WatchlistRow) => void;
    remove: (row: WatchlistRow) => void;
  };
}

/** 安全地从 row 取任意字段（WatchlistItem 无索引签名，需经 unknown 中转） */
function field(row: WatchlistRow, key: string): unknown {
  return (row as unknown as Record<string, unknown>)[key];
}

/** 解析某列应显示的「基础静态值」与「实时覆盖值」 */
function resolveValue(
  row: WatchlistRow,
  def: ColumnDef,
  ctx: RenderCtx
): { staticVal: number; realtimeVal?: number; useRealtime: boolean } {
  const staticVal = Number(field(row, def.key)) || 0;
  if (def.realtimeField && ctx.realtimeEnabled) {
    const item = ctx.getValuationItem(row.symbol);
    if (item && typeof item[def.realtimeField] === "number") {
      return { staticVal, realtimeVal: item[def.realtimeField], useRealtime: true };
    }
  }
  return { staticVal, useRealtime: false };
}

// ---- 各 renderer 实现 ----

const renderDate: FunctionalComponent<{ row: WatchlistRow; def: ColumnDef }> = (
  props
) => {
  const v = field(props.row, props.def.key);
  return h("span", { class: "text-sm" }, v ? formatDate(String(v)) : "--");
};

const renderMoney: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = (props) => {
  const { staticVal, realtimeVal, useRealtime } = resolveValue(
    props.row,
    props.def,
    props.ctx
  );
  return h(MoneyDisplay, {
    value: useRealtime ? realtimeVal! : staticVal,
    size: "sm",
  });
};

const renderRiseFall: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = (props) => {
  const { staticVal, realtimeVal, useRealtime } = resolveValue(
    props.row,
    props.def,
    props.ctx
  );
  return h(RiseFallText, {
    value: useRealtime ? realtimeVal! : staticVal,
    size: "sm",
  });
};

const renderQty: FunctionalComponent<{ row: WatchlistRow; def: ColumnDef }> = (
  props
) => {
  const v = Number(field(props.row, props.def.key)) || 0;
  const unit = field(props.row, "venue") === "OTC" ? "份" : "股";
  return h("span", { class: "font-mono text-sm" }, v > 0 ? `${v} ${unit}` : "--");
};

const renderMoneyRatio: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = (props) => {
  const { row, def, ctx } = props;
  // 派生列（添加后涨幅 / 持仓市值比例）：直接取注入的计算结果
  if (def.derived) {
    const d = ctx.derived(def.derived, row);
    return h(MoneyWithRatio, { value: d.value, ratio: d.ratio, moneySize: "sm" });
  }
  // 直接字段列（持仓收益）：value=def.key, ratio=props.ratioKey
  const value = Number(field(row, def.key)) || 0;
  const ratioKey = (def.props?.ratioKey as string) || "change_pct";
  const ratio = Number(field(row, ratioKey)) || 0;
  const hasPosition = (Number(field(row, "holding_quantity")) || 0) > 0;
  return h(MoneyWithRatio, {
    value: hasPosition ? value : null,
    ratio: hasPosition ? ratio : null,
    moneySize: "sm",
    showSign: true,
    showCurrency: false,
  });
};

const renderProduct: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = (props) => {
  const row = props.row;
  const tagIds = Array.isArray(field(row, "tag_ids"))
    ? (field(row, "tag_ids") as number[])
    : [];
  const tags = props.ctx.allTags.filter((t) => tagIds.includes(t.id));
  return h("div", { class: "flex items-center gap-2 min-w-0" }, [
    h(ProductDisplay, {
      symbol: row.symbol,
      name: (field(row, "display_name") as string) || row.symbol,
      assetType: row.asset_type,
    }),
    ...(tags.length
      ? [
          h(
            "div",
            { class: "flex gap-1 shrink-0" },
            tags.map((t) =>
              h(
                "span",
                {
                  class: "px-1.5 py-0.5 rounded text-xs",
                  style: { backgroundColor: t.color || "var(--bg-hover)" },
                },
                t.name
              )
            )
          ),
        ]
      : []),
  ]);
};

const renderActions: FunctionalComponent<{
  row: WatchlistRow;
  def: ColumnDef;
  ctx: RenderCtx;
}> = (props) => {
  const row = props.row;
  const a = props.ctx.actions;
  const mkBtn = (icon: string, title: string, onClick: () => void) =>
    h(
      "button",
      {
        class:
          "w-7 h-7 rounded-full grid place-items-center hover:bg-[var(--bg-hover)]",
        title,
        onClick: (e: Event) => {
          e.stopPropagation();
          onClick();
        },
      },
      [h("i", { class: `icon ${icon}` })]
    );
  return h("div", { class: "flex items-center justify-center gap-1" }, [
    mkBtn(
      row.is_pinned ? "ep:star-filled" : "ep:star",
      "置顶",
      () => a.togglePin(row)
    ),
    mkBtn("ep:medal", "关注", () => a.toggleFavorite(row)),
    h(
      "el-tooltip",
      {
        content:
          row.status === "HOLDING"
            ? "持仓资产无法直接从自选移除"
            : "移除",
        placement: "top",
      },
      {
        default: () =>
          h(
            "el-button",
            {
              circle: true,
              size: "small",
              class: "btn-delete-ghost",
              disabled: row.status === "HOLDING",
              onClick: (e: Event) => {
                e.stopPropagation();
                a.remove(row);
              },
            },
            () => [h("i", { class: "icon ep:delete" })]
          ),
      }
    ),
  ]);
};

/** renderer 类型 -> 函数式组件 的注册表 */
const REGISTRY: Record<
  ColumnRenderer,
  FunctionalComponent<{
    row: WatchlistRow;
    def: ColumnDef;
    ctx: RenderCtx;
  }>
> = {
  product: renderProduct as never,
  date: renderDate as never,
  money: renderMoney as never,
  riseFall: renderRiseFall as never,
  qty: renderQty as never,
  moneyRatio: renderMoneyRatio as never,
  actions: renderActions as never,
};

/** 按 renderer 类型取对应函数式组件（模板 <component :is> 用） */
export function resolveRenderer(type: ColumnRenderer) {
  return REGISTRY[type];
}

/** 渲染单个单元格（供测试或命令式调用） */
export function renderCell(
  def: ColumnDef,
  row: WatchlistRow,
  ctx: RenderCtx
): VNode {
  const Comp = resolveRenderer(def.renderer);
  return h(Comp, { row, def, ctx });
}
