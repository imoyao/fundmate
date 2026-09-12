// src/api/market.ts
// 探市·大类资产观察 接口（#1436 / #1444 收口实现）
import { http } from "@/utils/http";

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
    bond_yield: BondYield | null;
    /** 全局口径备注 */
    notes: string[];
  };
  message: string;
}

/**
 * 获取探市大类资产观察
 * @param force 是否强制刷新后端缓存（默认 false）
 */
export const getMarketOverview = (force = false) => {
  return http.get<MarketOverviewResponse, unknown>(
    `/api/market/overview${force ? "?force=true" : ""}`
  );
};
