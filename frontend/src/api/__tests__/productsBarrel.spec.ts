/**
 * `api/products` barrel 契约回归网（#2878 子域拆分）。
 *
 * 拆分把 21 个端点从单文件搬到 `api/products/*.ts`，`products.ts` 只留 `export *`。
 * 这类「纯搬运」最怕两件事：某个子域漏了转发（只 import 类型的调用方可能静默丢类型），
 * 以及搬动时顺手改了 URL / 入参形态。这里把四件事钉住：
 * 1. barrel 的运行时导出恰好是拆分前的 21 个函数，一个不多一个不少；
 * 2. 九个子域各自只认领本域函数（防止声明被搬错模块）；
 * 3. 十个类型仍能从公共入口取到（编译期判据，漏一条 re-export 即 typecheck 红）；
 * 4. 21 个端点的 method / URL / params 逐条与拆分前一致（运行时判据）。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }));

vi.mock("@/utils/http", () => ({
  http: { request: requestMock }
}));

import * as products from "@/api/products";
import * as advisor from "@/api/products/advisor";
import * as fund from "@/api/products/fund";
import * as fundRisk from "@/api/products/fundRisk";
import * as indices from "@/api/products/indices";
import * as manager from "@/api/products/manager";
import * as pro from "@/api/products/pro";
import * as resolve from "@/api/products/resolve";
import * as stock from "@/api/products/stock";
import * as trend from "@/api/products/trend";
import type {
  AdvisorProfileResult,
  FundPerformanceResult,
  FundRiskRankingResult,
  IndexProfileResult,
  ManagerProfileResult,
  ProRiskResult,
  ProductResolveParams,
  StockProfileResult,
  TradeTimelineResult,
  TrendRange
} from "@/api/products";

type Fn = (...args: unknown[]) => unknown;

const runtimeFns = (mod: Record<string, unknown>): string[] =>
  Object.keys(mod)
    .filter(key => typeof mod[key] === "function")
    .sort();

/** 拆分前 `api/products.ts` 的全部函数导出（21 个，字典序）。 */
const ALL_FUNCTIONS = [
  "fetchIndexEtfCompare",
  "fetchIndexReturns",
  "fetchIndexWeights",
  "fetchProAllocation",
  "fetchProInsight",
  "fetchProRisk",
  "fetchProStatus",
  "getAdvisorProfile",
  "getFundHoldingsDetail",
  "getFundPerformance",
  "getFundProfile",
  "getFundRiskRanking",
  "getFundRiskTypes",
  "getIndexProfile",
  "getManagerHoldings",
  "getManagerProfile",
  "getProductTrend",
  "getRelatedSymbols",
  "getStockProfile",
  "getTradeTimeline",
  "resolveProduct"
];

const SUBDOMAINS: Array<[string, unknown, string[]]> = [
  ["resolve", resolve, ["resolveProduct"]],
  [
    "fund",
    fund,
    ["getFundHoldingsDetail", "getFundPerformance", "getFundProfile"]
  ],
  ["fundRisk", fundRisk, ["getFundRiskRanking", "getFundRiskTypes"]],
  [
    "indices",
    indices,
    [
      "fetchIndexEtfCompare",
      "fetchIndexReturns",
      "fetchIndexWeights",
      "getIndexProfile"
    ]
  ],
  ["stock", stock, ["getStockProfile"]],
  ["manager", manager, ["getManagerHoldings", "getManagerProfile"]],
  [
    "trend",
    trend,
    ["getProductTrend", "getRelatedSymbols", "getTradeTimeline"]
  ],
  ["advisor", advisor, ["getAdvisorProfile"]],
  [
    "pro",
    pro,
    ["fetchProAllocation", "fetchProInsight", "fetchProRisk", "fetchProStatus"]
  ]
];

const SYMBOL = "000001";
const CODE = "000001";

type EndpointCase = {
  name: string;
  args: unknown[];
  /** `http.request` 的完整实参列表（拆分前实现逐条抄录） */
  expected: unknown[];
};

const call = (url: string, params?: unknown): unknown[] =>
  params === undefined ? ["get", url] : ["get", url, { params }];

const ENDPOINTS: EndpointCase[] = [
  {
    name: "resolveProduct",
    args: [{ symbol: SYMBOL }],
    expected: call("/api/products/resolve/", { symbol: SYMBOL })
  },
  {
    name: "getFundProfile",
    args: [CODE],
    expected: call("/api/products/fund-profile/", { code: CODE })
  },
  {
    name: "getIndexProfile",
    args: [SYMBOL],
    expected: call("/api/products/index-profile/", { symbol: SYMBOL })
  },
  {
    name: "fetchIndexReturns",
    args: [SYMBOL],
    expected: call("/api/products/index-returns/", { symbol: SYMBOL })
  },
  {
    name: "fetchIndexWeights",
    args: [SYMBOL],
    expected: call("/api/products/index-weights/", { symbol: SYMBOL })
  },
  {
    name: "fetchIndexEtfCompare",
    args: [SYMBOL],
    expected: call("/api/products/index-etf-compare/", { symbol: SYMBOL })
  },
  {
    name: "getFundPerformance",
    args: [CODE],
    expected: call("/api/products/fund-performance/", { code: CODE })
  },
  {
    name: "getFundHoldingsDetail",
    args: [CODE],
    expected: call("/api/products/fund-holdings-detail/", { code: CODE })
  },
  {
    name: "getStockProfile",
    args: [{ symbol: SYMBOL }],
    expected: call("/api/products/stock-profile/", { symbol: SYMBOL })
  },
  {
    name: "getManagerProfile",
    args: [{ mgr_code: "M001" }],
    expected: call("/api/products/manager-profile/", { mgr_code: "M001" })
  },
  {
    name: "getManagerHoldings",
    args: [{ mgr_code: "M001" }],
    expected: call("/api/products/manager-holdings/", { mgr_code: "M001" })
  },
  {
    name: "getRelatedSymbols",
    args: [{ symbol: SYMBOL }],
    expected: call("/api/products/related-symbols/", { symbol: SYMBOL })
  },
  {
    name: "getProductTrend",
    args: [{ symbol: SYMBOL, range: "1M" }],
    expected: call("/api/products/trend/", { symbol: SYMBOL, range: "1M" })
  },
  {
    name: "getTradeTimeline",
    args: [{ symbol: SYMBOL }],
    expected: call("/api/products/trade-timeline/", { symbol: SYMBOL })
  },
  {
    name: "getAdvisorProfile",
    args: [{ code: CODE }],
    expected: call("/api/products/advisor-profile/", { code: CODE })
  },
  {
    name: "getFundRiskTypes",
    args: [],
    expected: call("/api/products/fund-risk-types/")
  },
  {
    name: "getFundRiskRanking",
    args: [{ fund_type_id: 1, metric: "sharpe" }],
    expected: call("/api/products/fund-risk-ranking/", {
      fund_type_id: 1,
      metric: "sharpe"
    })
  },
  {
    name: "fetchProStatus",
    args: [SYMBOL, null],
    expected: call("/api/products/pro/", {
      symbol: SYMBOL,
      asset_type: undefined
    })
  },
  {
    name: "fetchProInsight",
    args: [SYMBOL, null],
    expected: call("/api/products/pro-insight/", {
      symbol: SYMBOL,
      asset_type: undefined
    })
  },
  {
    name: "fetchProRisk",
    args: [SYMBOL, null],
    expected: call("/api/products/pro-risk/", {
      symbol: SYMBOL,
      asset_type: undefined
    })
  },
  {
    name: "fetchProAllocation",
    args: [SYMBOL, null],
    expected: call("/api/products/pro-allocation/", {
      symbol: SYMBOL,
      asset_type: undefined
    })
  }
];

describe("api/products barrel（#2878）", () => {
  beforeEach(() => {
    requestMock.mockReset();
  });

  it("运行时导出恰好是拆分前的 21 个函数", () => {
    expect(runtimeFns(products as unknown as Record<string, unknown>)).toEqual(
      ALL_FUNCTIONS
    );
  });

  it("九个子域各自只认领本域函数，合计仍是 21 个", () => {
    const flat: string[] = [];
    for (const [, mod, expected] of SUBDOMAINS) {
      expect(runtimeFns(mod as Record<string, unknown>)).toEqual(expected);
      flat.push(...expected);
    }
    expect(flat.sort()).toEqual(ALL_FUNCTIONS);
  });

  it("类型仍能从公共入口取到（编译期判据）", () => {
    // 十个类型来自九个不同子域；任一条 `export *` 漏写，typecheck 即失败。
    type Sample = [
      ProductResolveParams,
      FundPerformanceResult,
      FundRiskRankingResult,
      IndexProfileResult,
      StockProfileResult,
      ManagerProfileResult,
      TradeTimelineResult,
      TrendRange,
      AdvisorProfileResult,
      ProRiskResult
    ];
    const arity: Sample["length"] = 10;
    expect(arity).toBe(10);
  });

  it.each(ENDPOINTS)(
    "$name 的 method / URL / params 未变",
    ({ name, args, expected }) => {
      const fn = (products as unknown as Record<string, Fn>)[name];
      expect(typeof fn).toBe("function");
      fn(...args);
      expect(requestMock).toHaveBeenCalledWith(...expected);
    }
  );

  it("Pro 端点把 assetType 原样映射为 asset_type", () => {
    (products as unknown as Record<string, Fn>).fetchProStatus(SYMBOL, "fund");
    expect(requestMock).toHaveBeenCalledWith("get", "/api/products/pro/", {
      params: { symbol: SYMBOL, asset_type: "fund" }
    });
  });
});
