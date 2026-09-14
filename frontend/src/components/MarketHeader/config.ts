/**
 * MarketHeader 共享配置
 * 探市（含概览/深度两档）/ 投资概览 等独立全屏页面使用同一套品牌与导航。
 *
 * 2026-09-12 方案 D：原「温度计」独立入口已收敛为探市页内的「深度」档，
 * 故从导航移除；页内切换入口见 views/explore/index.vue 的胶囊 Tab。
 */

import { useRouter } from "vue-router";

export const MARKET_LOGO = "多多贝";

export function useMarketHeaderNavs() {
  const router = useRouter();

  return [
    {
      label: "探市",
      type: "link" as const,
      onClick: () => router.push("/explore")
    },
    {
      label: "自选",
      type: "primary" as const,
      onClick: () => router.push("/watchlist")
    }
  ];
}
