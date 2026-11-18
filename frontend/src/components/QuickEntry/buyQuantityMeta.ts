import { TRADE_FIELD_LABELS } from "@/constants";
import { getStep } from "@/utils/trading";

/**
 * 记一笔「买入数量」字段的品种口径（单一出口）。
 *
 * ## 为什么按品种分叉
 *
 * 基金与股票的**已知量**不是同一个：
 * - 基金申购时净值未知（T 日净值当晚才出），用户手里只有金额 ⇒ 金额是主量，
 *   份额是算出来的那个数（可手动微调，官方确认份额可能不同）；
 * - 股票 / ETF / 可转债的成交价与成交数量都是已成交事实，金额是
 *   `数量 × 成交价 + 手续费` 的派生量，且 A 股买入必须整手（百股 / 科创板 200 股 /
 *   可转债 10 张）。
 *
 * 此前两者共用一套「买入金额 → 确认份额」口径：股票填 5200 元、价 5.20、费 1.05
 * 会算出 999.7981 股 —— 展示成整数 1000，后端 `validate_buy` 却按整手校验把它拦下
 * （2026-11-16 用户报「股票买入怎么也是按份额算」）。
 *
 * 故本模块只做一件事：给定品种，回答「这个字段该叫什么、几位精度、一手多少、
 * 金额是主量还是派生量」。组件与提交校验都从这里取，避免第三份口径。
 */

export type BuyQuantityMode = "fund" | "trade" | "none";

export interface BuyQuantityMeta {
  mode: BuyQuantityMode;
  /** 表单标签：基金「确认份额」/ 非基金「成交数量」（全站成交字段唯一叫法） */
  label: string;
  /** 输入精度：基金 2 位（申购口径），股票/ETF/可转债 0 位 */
  precision: number;
  /** 一手数量（0 = 不设步进） */
  step: number;
  min: number;
  /** 单位：份 / 股 / 张 */
  unit: string;
  placeholder: string;
  hint: string;
  /** 金额是否由数量派生（true = 金额只读，数量是主量） */
  amountDerived: boolean;
}

/**
 * 品种 → 口径。`money_fund` 走基金口径（按金额申购、份额 2 位）；
 * 投顾组合没有份额与价格（D70），返回 `none`（整块不渲染）。
 */
export function buyQuantityMode(input: {
  /** 已选标的类型；未选标的时为空 */
  type?: string;
  /** 账户类型：未选标的时用它兜底（证券账户先按股票口径展示） */
  ledgerType?: string;
}): BuyQuantityMode {
  if (input.type === "portfolio") return "none";
  if (input.type) {
    return input.type === "fund" || input.type === "money_fund"
      ? "fund"
      : "trade";
  }
  return input.ledgerType === "stock" ? "trade" : "fund";
}

export function buyQuantityMeta(input: {
  type?: string;
  ledgerType?: string;
  market?: string;
  symbol?: string;
}): BuyQuantityMeta {
  const mode = buyQuantityMode(input);

  if (mode === "trade") {
    // getStep 按裸 6 位代码判断代码段（688 / 8 开头），而界面上是带市场前缀的
    // 标准码（SH688981 / SZ159915）——不去前缀会把科创板 200 股一手判成 100。
    const bare = (input.symbol ?? "").replace(/^(SH|SZ|BJ)/i, "");
    const lot = getStep({
      // 未选标的时给一手默认值，等选中后按代码段重算（科创板 200 / 可转债 10）
      type: input.type ?? "stock",
      market: input.market ?? "CN_A",
      symbol: bare
    });
    const unit = input.type === "bond" ? "张" : "股";
    return {
      mode,
      label: TRADE_FIELD_LABELS.quantity,
      precision: 0,
      step: lot,
      min: lot,
      unit,
      placeholder: `一手 ${lot} ${unit}，如 ${lot * 10}`,
      hint: `按整手申报（${lot} ${unit}/手）；买入金额 = 数量 × 成交价格 + 手续费`,
      amountDerived: true
    };
  }

  return {
    mode,
    label: "确认份额",
    precision: 2,
    step: 0,
    min: 0,
    unit: "份",
    placeholder: "自动计算或手动微调份额",
    hint: "买入金额扣除手续费后的确认份额，可手动微调",
    amountDerived: false
  };
}
