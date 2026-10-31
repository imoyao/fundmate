/**
 * 持仓「所属组合」归属解析（D20 二期 UI）。
 *
 * ## 为什么单独成 model
 * 这段是**服务端口径的前端投影**（`portfolio_service.portfolio_position_conditions`：
 * 显式 `positions.portfolio_id` 压过 `ledgers.portfolio_id` 继承）。四态里任一分支判错，
 * 界面上都看不出异常——「继承」被显示成「显式」、「未知」被显示成「未归属」，
 * 渲染结果都是「一个组合名」，只有单测能钉住。故收成纯函数，组件与数据层共用一份。
 *
 * ## 五态为什么不能合并
 * | 状态 | 含义 | 展示 |
 * |---|---|---|
 * | `explicit` | 用户显式指派过 | 组合名 + 实心点 |
 * | `inherited` | 无人指派，靠账户默认组合带进来 | 组合名 + 灰点 + 「随账户」 |
 * | `none` | 既未指派、账户也没默认组合 | 「未归属」 |
 * | `unknown` | 响应里没有该字段 | 「—」 |
 * | `excluded` | 后端说该品种根本不计入组合（货基 / 逆回购 / 现金） | 「— 不进组合」+ 禁用改派 |
 *
 * 把 `unknown` 当 `none` 会谎报「它不属于任何组合」；当 `inherited` 会谎报
 * 「随账户继承」——两者都会让用户对归类状态做出错误判断，而这正是本次要修的病。
 *
 * `excluded` 同理不能并进 `none`：`none` 的含义是「可以归、但还没归」，
 * 后面跟着可点的改派入口；`excluded` 是「归了也不会生效」，入口必须关掉。
 * 两者都显示「未归属」类的文案，用户就会去点、点了没效果（D20 二期开口项 4）。
 */

import type { PortfolioItem } from "@/api/portfolio";

/** 归属状态（见文件头五态表） */
export type PortfolioMode =
  "explicit" | "inherited" | "none" | "unknown" | "excluded";

export interface PortfolioAssignment {
  mode: PortfolioMode;
  /** 当前实际归属的组合名（`explicit` / `inherited` 有值，其余为 `null`） */
  labelText: string | null;
}

export interface PortfolioLookup {
  /** 全部可选组合（用于 id → 名称映射） */
  portfolios: PortfolioItem[];
  /** 账户 id → 该账户的默认组合 id（`null` = 账户未设默认组合，或账户不在列表里） */
  ledgerPortfolioMap: Record<number, number | null>;
}

/** 归属解析所需的最小行字段（`Position` / `PortfolioHolding` 都满足） */
export interface PortfolioAssignableRow {
  portfolio_id?: number | null;
  ledger_id?: number | null;
  /** 是否计入组合（后端 `enrich_position_dict` 下发，见 `PortfolioMode.excluded`） */
  in_portfolio?: boolean;
}

/**
 * 组合 id → 展示名。
 *
 * 找不到时返回 `组合 #<id>` 而不是空串或「未知组合」：组合被删 / 列表未加载完时，
 * 用户至少还能从 id 认出「是那个组合」，也不会让整格变成空白被误读成「未归属」。
 */
export function portfolioLabel(
  portfolios: PortfolioItem[],
  portfolioId: number
): string {
  return (
    portfolios.find(p => p.id === portfolioId)?.name ?? `组合 #${portfolioId}`
  );
}

/**
 * 解析一条持仓的「所属组合」归属状态。
 *
 * ⚠️ **`undefined` 与 `null` 必须分开**：
 * - `null` = 后端明确说「没有显式指派」→ 走账户继承路径；
 * - `undefined` = 响应里压根没有这个字段（接口未升级 / 资产行）→ 状态未知。
 *
 * 混同的后果：资产行（现金，`build_portfolio_holdings` 明确不含该字段）会被
 * 标成「随账户」，而现金**没有**持仓级组合概念，标签本身就是错的。
 */
export function resolvePortfolioOf(
  row: PortfolioAssignableRow,
  lookup: PortfolioLookup
): PortfolioAssignment {
  // 「不进组合」优先于一切归属判断（D20 二期开口项 4）：这类品种改派了也不会出现在
  // 组合里，先答「能不能归」再答「归到哪」。判据只认后端下发的 `false`——
  // `undefined`（字段缺失）**不能**当 `false`，否则所有旧接口的行都会被标成不进组合。
  if (row.in_portfolio === false) {
    return { mode: "excluded", labelText: null };
  }
  if (row.portfolio_id === undefined) {
    return { mode: "unknown", labelText: null };
  }
  if (row.portfolio_id !== null) {
    return {
      mode: "explicit",
      labelText: portfolioLabel(lookup.portfolios, row.portfolio_id)
    };
  }
  const defaultPortfolioId =
    row.ledger_id != null
      ? (lookup.ledgerPortfolioMap[row.ledger_id] ?? null)
      : null;
  if (defaultPortfolioId === null) {
    return { mode: "none", labelText: null };
  }
  return {
    mode: "inherited",
    labelText: portfolioLabel(lookup.portfolios, defaultPortfolioId)
  };
}

/**
 * 该行是否靠「账户默认组合」继承而来。
 *
 * **严格 `=== null`**，不是 `!row.portfolio_id`：后者会把资产行的 `undefined`
 * 也算成继承（见 `resolvePortfolioOf` 的注释）。
 */
export function isInheritedFromLedger(row: {
  portfolio_id?: number | null;
}): boolean {
  return row.portfolio_id === null;
}
