// frontend/src/utils/externalQuoteLinks.ts
/**
 * 观察列表「深度分析」跳转：把标的代码映射到外部行情 / 基金页 URL。
 *
 * 纯函数（无副作用、无外部依赖），从 explore/index.vue 抽出，
 * 见 #980「第二步：抽纯函数、工具方法」——这类逻辑与页面结构无关，页面大改也能复用。
 *
 * 市场判定与原实现一致：`6` 开头视为沪市（SH），其余视为深市（SZ）。
 */
export type ExternalLinkCommand = "xueqiu" | "eastmoney" | "tiantian";

/**
 * 构造外部跳转 URL。
 * @returns 命中的 URL；未识别的 command 返回 null（调用方据此不跳转）
 */
export function buildExternalQuoteUrl(
  symbol: string,
  command: ExternalLinkCommand
): string | null {
  const isShanghai = symbol.startsWith("6");
  const market = isShanghai ? "SH" : "SZ";
  const marketLower = isShanghai ? "sh" : "sz";

  switch (command) {
    case "xueqiu":
      return `https://xueqiu.com/S/${market}${symbol}`;
    case "eastmoney":
      return `https://quote.eastmoney.com/${marketLower}${symbol}.html`;
    case "tiantian":
      return `https://fund.eastmoney.com/${symbol}.html`;
    default:
      return null;
  }
}
