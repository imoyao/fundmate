import type { Ref } from "vue";
import type { ProductResolveResult } from "@/api/products";
import { usePageNav } from "@/composables/usePageNav";

/**
 * 产品详情页的页内导航（#1968 子卡）——共享 `usePageNav` 的产品配置层。
 *
 * 通用滚动机制（scroll-spy / 跳转动画 / 用户接管 / MutationObserver 补扫）
 * 已上提到 `src/composables/usePageNav.ts`（2026-10-25，配合组合详情 / 复盘
 * 页接入 PageNav + PageToc）；本文件只剩产品页专属的两件事：
 *
 * 1. 锚点 → 标签映射表（与各区块 SectionHeader 标题逐字一致）；
 * 2. 股票 / ETF 的动态标签特判（`ProductStockSection.sectionTitle` 随品类），
 *    以及品类切换时的重扫（经 `rescanOn` 下发）。
 */
const NAV_LABELS: Record<string, string> = {
  "nav-position": "我的持仓",
  "nav-trend": "走势",
  "nav-transactions": "交易记录",
  "nav-fund": "基金资料",
  "nav-performance": "业绩与风险",
  // 「行业配置 + 持仓明细」共用一个容器端点（#2029 卡 C），合并为一个入口
  "nav-holdings": "行业与持仓",
  // 相似基金（#2480）：韭圈儿 simfund，详情页独立区块，需可点击跳转
  "nav-similar": "相似基金",
  // 投资风格（#2478）：韭圈儿月度风格箱，晨星式 8 分类 + 漂移信号，需可点击跳转
  "nav-style": "投资风格",
  "nav-index": "指数资料",
  "nav-manager": "基金经理",
  "nav-advisor": "投顾组合",
  "nav-bond": "深度分析",
  "nav-related": "关联标的",
  "nav-external": "更多数据",
  "nav-pro": "高级洞察 Pro"
};

/** 股票 / ETF 的区块标题是动态的，导航标签随之 */
function labelFor(
  id: string,
  assetType: string | undefined
): string | undefined {
  if (id === "nav-stock") {
    return assetType === "etf" ? "ETF 行情" : "股票行情";
  }
  return NAV_LABELS[id];
}

export function useProductPageNav(
  product: Ref<ProductResolveResult | null>,
  container: Ref<HTMLElement | undefined>
) {
  return usePageNav(container, {
    labels: NAV_LABELS,
    resolveLabel: id => labelFor(id, product.value?.asset_type),
    rescanOn: () => product.value
  });
}
