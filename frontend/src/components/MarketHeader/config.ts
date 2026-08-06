/**
 * MarketHeader 共享配置
 * 探市 / 温度计 / 投资概览 等独立全屏页面使用同一套品牌与导航，避免两页 header 不一致。
 */

import { useRouter } from "vue-router";

export const MARKET_LOGO = "多倍贝";

export function useMarketHeaderNavs() {
  const router = useRouter();

  return [
    {
      label: "探市",
      type: "link" as const,
      onClick: () => router.push("/explore")
    },
    {
      label: "温度计",
      type: "link" as const,
      onClick: () => router.push("/temperature")
    },
    {
      label: "自选",
      type: "primary" as const,
      onClick: () => router.push("/watchlist")
    }
  ];
}
