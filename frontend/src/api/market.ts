// src/api/market.ts
// 探市·大类资产观察 接口（#1436 / #1444 收口实现）
import { http } from "@/utils/http";

/** ⚡ 异动判定（docs/features/market-explorer.md §5.5 双线规则）；未触发为 null */
export interface MarketAnomaly {
  /** 是否亮 ⚡（本类型只在命中时下发，恒为 true；保留字段便于前端显式判断） */
  triggered: boolean;
  /** 命中路径：sigma=线1(自身波动率) / abs=线2(绝对阈值) / both=两条都命中 */
  rule: "sigma" | "abs" | "both";
  /** 当日涨跌幅(%) */
  today_pct: number;
  /** 近 sigma_window 个交易日的日收益标准差(%) */
  sigma: number | null;
  /** |今日涨跌| / sigma 的倍数 */
  multiple: number | null;
  /** 波动率窗口（交易日） */
  sigma_window: number;
  /** 倍数阈值（线 1 上限） */
  sigma_multiple: number;
  /** 绝对阈值(%)（线 2） */
  abs_threshold: number;
  /** 规则自述文案（非新闻事实，见后端 notes 说明） */
  basis_note: string;
}

/** 单个资产项 */
export interface MarketAsset {
  key: string;
  name: string;
  category: string;
  /** 是否可取数；false = 软占位（缺源 / 决策占位） */
  available: boolean;
  /** 当日涨跌幅(%)；软占位为 null */
  change_pct: number | null;
  /** 该资产所属交易日（北京） */
  trade_date: string | null;
  /** 实际取到时刻（北京） */
  data_asof: string | null;
  /** 相对位置（分位）信息；不可得为 null */
  position: {
    percentile: number;
    label: string;
    basis: string;
    window: number;
  } | null;
  /** ⚡ 异动信息；未命中为 null */
  anomaly: MarketAnomaly | null;
  /** 口径提示（商品含夜盘 / 汇率非 DXY 等） */
  caliber: string | null;
  /** 不可得原因（软占位小字） */
  reason: string | null;
}

/** 单个分组 */
export interface MarketGroup {
  category: string;
  assets: MarketAsset[];
}

/** 债券收益率轨（best-effort，可能 null） */
export interface BondYield {
  cn_10y: number;
  cn_10y_change_bp: number;
  us_10y?: number;
  us_10y_change_bp?: number;
}

export interface MarketOverviewResponse {
  data: {
    /** 数据生成时刻（北京） */
    updated_at: string;
    /** 各市场数据截止口径说明 */
    as_of_note: string;
    groups: MarketGroup[];
    /** 软占位资产数量 */
    unavailable_count: number;
    /** ⚡ 异动命中的资产数量 */
    anomaly_count: number;
    bond_yield: BondYield | null;
    /** 全局口径备注 */
    notes: string[];
  };
  message: string;
}

/**
 * 获取探市大类资产观察
 * @param force 是否强制刷新后端缓存（默认 false）
 *
 * 单独放宽 timeout：该接口首屏为**多源实时取数**（后端已并发化），
 * 冷缓存实测约 12s，远超全局默认 10s（utils/http/index.ts），
 * 故此处按接口覆盖为 25s；命中后端 30 分钟缓存时 <0.1s。
 */
export const getMarketOverview = (force = false) => {
  return http.get<MarketOverviewResponse, unknown>(
    `/api/market/overview${force ? "?force=true" : ""}`,
    undefined,
    { timeout: 25000 }
  );
};
