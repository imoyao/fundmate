import { computed } from "vue";
import type { AggregationProductGroup, AggregationSource } from "@/api/ledger";

/**
 * 聚合视图产品卡片的展示模型（#980 拆分）。
 *
 * 卡片两种模式共用同一套模板，差异全部收敛在这里：
 * - `product`：按产品聚合，副标题 = 基金管理人；
 * - `institution`：按渠道平铺，副标题 = 账本名称（机构全称走 title）。
 *
 * 本文件只做「原始字段 → 展示值」的派生，不含任何 DOM / 样式逻辑，
 * 便于单测直接断言口径（收益率符号、占比分母、日期格式）。
 */
export interface ProductCardModelInput {
  /** 产品模式：传入聚合后的产品组 */
  group?: AggregationProductGroup;
  /** 渠道模式：传入单条来源记录（institution 模式下使用） */
  source?: AggregationSource;
  /** 当前维度 */
  mode?: "product" | "institution";
  /** 参考净值（渠道模式下 source 可能不含此字段，由父组件传入） */
  navYuan?: number | null;
  /** 快照日期 */
  snapshotDate?: string | null;
  /** 总市值（元），用于计算占比；不传则不显示占比 */
  totalYuan?: number | null;
}

/** 把 YYYY-MM-DD 折叠成 MM-DD，其它形态原样返回 */
export function shortDate(d: string | null | undefined): string | null {
  if (!d) return null;
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[2]}-${m[3]}` : d;
}

/** 收益率文本：带正负号（如 "+7.90%"），无成本数据为 "--" */
export function formatReturnPct(v: number | null | undefined): string {
  if (v == null) return "--";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(2)}%`;
}

/** 收益率胶囊语义类：正收益涨色 / 负收益跌色 / 无成本中性 */
export function returnBadgeClass(v: number | null | undefined): string {
  if (v == null || v === 0) return "return-badge--flat";
  return v > 0 ? "return-badge--positive" : "return-badge--negative";
}

export function useProductCardModel(props: ProductCardModelInput) {
  const isInstitution = computed(() => props.mode === "institution");

  const productName = computed(
    () => props.group?.name || props.source?.name || "--"
  );
  const productCode = computed(
    () => props.group?.symbol || props.source?.symbol || ""
  );

  /**
   * 副标题。
   * - institution 维度（按渠道分组、组内按账本平铺）：显示**账本名称**，
   *   用于区分同一渠道下的不同账本；销售机构全称较长，改由悬浮提示承载，
   *   避免挤压卡片布局。注意该维度的分组键是销售机构，不是账本。
   * - product 维度：显示基金管理人。
   */
  const subtitle = computed(() => {
    if (isInstitution.value) return props.source?.ledger_name || null;
    return props.group?.fund_manager || null;
  });
  const subtitleIcon = computed(() => (isInstitution.value ? "ep:wallet" : ""));
  /** 副标题悬浮提示：institution 模式补充销售机构全称（Alias） */
  const subtitleTitle = computed(() => {
    if (isInstitution.value) {
      const org = props.source?.institution_name;
      const alias = props.source?.institution_alias;
      if (org && alias) return `${org}（${alias}）`;
      return org || null;
    }
    return props.group?.fund_manager || null;
  });

  const shares = computed(() => {
    if (isInstitution.value) return (props.source?.quantity || 0) / 10000;
    return (props.group?.quantity || 0) / 10000;
  });

  const marketValueYuan = computed(() => {
    if (isInstitution.value)
      return (props.source?.market_value_cents || 0) / 100;
    return (props.group?.market_value_cents || 0) / 100;
  });

  const nav = computed(() => {
    if (isInstitution.value) return props.navYuan;
    return props.group?.nav_yuan ?? null;
  });

  /** 持仓收益率（小数，如 0.079 → 7.90%）；无成本（后端 return_pct 为 null）时显示 -- */
  const returnPct = computed<number | null>(() => {
    if (isInstitution.value) return props.source?.return_pct ?? null;
    return props.group?.return_pct ?? null;
  });

  const returnText = computed(() => formatReturnPct(returnPct.value));
  const returnClass = computed(() => returnBadgeClass(returnPct.value));

  const channelCount = computed(() => props.group?.sources?.length ?? 0);

  /** 多渠道持有 tooltip 明细（对齐「N 个账户」弱化为图标的诉求） */
  const channelTooltip = computed(() => {
    if (isInstitution.value) return "";
    const names = (props.group?.sources ?? [])
      .map(s => s.ledger_name)
      .filter(Boolean);
    const base = `该基金分散在 ${channelCount.value} 个账户持有`;
    return names.length ? `${base}：${names.join("、")}` : base;
  });

  /** 显示用的快照日期（格式化后） */
  const displayDate = computed(() => {
    const d =
      props.snapshotDate ??
      (isInstitution.value
        ? props.source?.snapshot_date
        : props.group?.snapshot_date);
    return shortDate(d);
  });

  /** 多渠道持有提示 */
  const multiChannelHint = computed(() => {
    if (isInstitution.value) return false;
    const srcCount = props.group?.sources?.length ?? 0;
    return srcCount > 1;
  });

  return {
    isInstitution,
    productName,
    productCode,
    subtitle,
    subtitleIcon,
    subtitleTitle,
    shares,
    marketValueYuan,
    nav,
    returnPct,
    returnText,
    returnClass,
    channelCount,
    channelTooltip,
    displayDate,
    multiChannelHint
  };
}
