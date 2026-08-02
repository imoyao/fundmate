// MarketFooter 共享配置：图例 + 数据来源
// 统一「探市 / 温度计」页脚，结合两页优势：
//  - 图例沿用图1文案（偏低（机会）/ 适中 / 偏高（谨慎）），不加「绿= / 金=」等号，更自然
//  - 数据来源合并两页内容：平台官方链接优先取后端 links，缺省回退固定官网；
//    同时保留「自算·股债性价比 / 乖离率(自算)」与「行业拥挤度 / 板块资金流（开发中）」

export interface FooterSource {
  label: string;
  url?: string;
  dev?: boolean;
}

export interface FooterLegendItem {
  label: string;
  tone: "low" | "mid" | "high";
}

// 图例：图1文案风格（无等号、无颜色前缀）
export const marketFooterLegend: FooterLegendItem[] = [
  { label: "偏低（机会）", tone: "low" },
  { label: "适中", tone: "mid" },
  { label: "偏高（谨慎）", tone: "high" }
];

// 平台固定官网（后端未返回 links 时回退）
const PLATFORM_URLS: Record<string, string> = {
  jiucaishuo: "https://www.jiucaishuo.com",
  jisilu: "https://www.jisilu.cn",
  eastmoney: "https://www.eastmoney.com",
  qieman: "https://qieman.com",
  youzhiyouxing: "https://youzhiyouxing.cn"
};

export function buildMarketFooterSources(
  links?: Record<string, string>
): FooterSource[] {
  const url = (key: keyof typeof PLATFORM_URLS) =>
    links?.[key] || PLATFORM_URLS[key];

  return [
    { label: "韭圈儿", url: url("jiucaishuo") },
    { label: "集思录", url: url("jisilu") },
    { label: "且慢", url: url("qieman") },
    { label: "有知有行", url: url("youzhiyouxing") },
    { label: "东方财富", url: url("eastmoney") },
    { label: "自算·股债性价比" },
    { label: "乖离率(自算)" },
    { label: "行业拥挤度（开发中）", dev: true },
    { label: "板块资金流（开发中）", dev: true }
  ];
}
