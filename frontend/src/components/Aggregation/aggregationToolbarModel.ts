import { ASSET_TYPE_LABELS } from "@/constants/assetType";
import type {
  AggregationDimension,
  AggregationResult,
  AggregationSort
} from "@/api/ledger";

/**
 * 聚合视图工具条（维度切换 / 搜索 / 类型 Tab / 排序）的常量与派生逻辑（#980）。
 *
 * 这些内容原先内联在 `AggregationPage.vue` 里；抽出来既让页面壳变薄，
 * 也让「类型 Tab 有哪些选项」这条口径可以被单测直接覆盖。
 */

/** 维度切换：按产品 / 按渠道 */
export const DIMENSION_OPTIONS: {
  label: string;
  value: AggregationDimension;
}[] = [
  { label: "按产品展示", value: "product" },
  // 该维度的分组键是 institution_id（销售机构/购买渠道），不是 Ledger（账本），
  // 故文案用「渠道」而非「账户」，避免与账本概念混淆（#1185）
  { label: "按渠道展示", value: "institution" }
];

/** 常驻排序快捷按钮：点击即切换字段，同一字段再点反转升降序 */
export const SORT_OPTIONS: { label: string; value: AggregationSort }[] = [
  { label: "市值", value: "market_value" },
  { label: "份额", value: "quantity" },
  { label: "收益率", value: "return_pct" },
  { label: "名称", value: "name" }
];

/** asset_type 中文标签 → 原始值 的反查表（复用前端镜像，禁止手抄第二份） */
const ASSET_TYPE_VALUE_BY_LABEL: Record<string, string> = Object.fromEntries(
  Object.entries(ASSET_TYPE_LABELS).map(([value, label]) => [label, value])
);

/**
 * 类型筛选 Tab：动态生成，只显示实际有产品的分类（#1224 反馈）。
 * 「全部」常驻；基金侧中间分类来自后端 fund_type_counts（有产品才显示）+「未分类」；
 * 证券侧从 fund_type_breakdown（已按 asset_type 聚类的中文标签）反查原始 asset_type 值。
 * 仅当 showTypeTab 时渲染。
 */
export function buildTypeOptions(
  result: AggregationResult | null | undefined,
  typeFilterField: "fund_type" | "asset_type" | undefined
): { label: string; value: string }[] {
  const opts: { label: string; value: string }[] = [
    { label: "全部", value: "" }
  ];
  if (typeFilterField === "asset_type") {
    for (const b of result?.fund_type_breakdown ?? []) {
      const raw = ASSET_TYPE_VALUE_BY_LABEL[b.name];
      if (raw) opts.push({ label: b.name, value: raw });
    }
    return opts;
  }
  const counts = result?.fund_type_counts ?? {};
  for (const [name, count] of Object.entries(counts)) {
    if (count > 0) opts.push({ label: name, value: name });
  }
  if ((result?.fund_type_unclassified_count ?? 0) > 0) {
    opts.push({ label: "未分类", value: "__none__" });
  }
  return opts;
}
