// frontend/src/api/temperature.ts
import { http } from "@/utils/http";

export interface TemperatureBand {
  name: string;
  value: number | null;
  level: string;
}

export interface TemperatureOverviewResponse {
  data: {
    updated_at: string;
    /** #1431 数据新鲜度守卫：最新数据日期距今超阈值即为陈旧，前端须显式提示 */
    freshness?: {
      latest: string | null;
      age_days: number | null;
      stale: boolean;
      threshold_days: number;
    };
    singles: Array<{
      source: string;
      name: string;
      value: number;
      label: string;
      unit: string;
      /** 平台原生更新时间（精确到秒，尊重平台规范） */
      updated_at: string;
    }>;
    composites: {
      self_calc?: {
        percent: number;
        level: string;
        spread_pct: number;
        y10: number;
        cpi: number;
        collected_at: string;
      };
      composite_temperature?: {
        value: number;
        level: string;
        weights?: Record<string, number>;
        available?: string[];
      };
      jisilu_indicator?: {
        median_pb: number;
        median_pb_temperature: number;
        median_pe: number;
        median_pe_temperature: number;
        stock_count: number;
        ipo_count: number;
        st_count: number;
        index_point: number;
        price_dt: string;
        median_pb_level?: string;
        median_pe_level?: string;
      };
      temperature_bands?: {
        short?: TemperatureBand;
        medium?: TemperatureBand;
        long?: TemperatureBand;
      };
    };
    /** B3: 市场机会解读文案（name/desc/tone），后端归集、前端仅映射样式 */
    insights: Array<{
      name: string;
      desc: string;
      tone: "safe" | "normal" | "danger";
    }>;
    /** B3: 综合温度环下方结论副文案 */
    conclusion: string;
    links: {
      jisilu: string;
      jiucaishuo: string;
      qieman: string;
      youzhiyouxing: string;
      eastmoney: string;
    };
  };
  message: string;
}

export const getTemperatureOverview = () => {
  return http.get<TemperatureOverviewResponse, unknown>(
    "/api/temperature/overview"
  );
};

// ============================================================
// 新增 API
// ============================================================

export interface TemperatureHistoryResponse {
  data: {
    dates: string[];
    values: (number | null)[];
    levels?: string[];
    labels?: string[];
    source: string;
  };
  message: string;
}

/**
 * 获取综合温度历史趋势
 * @param days 最近天数，默认 90
 * @param source 指标来源，默认 composite_temperature
 */
export const getTemperatureHistory = (
  days: number = 90,
  source: string = "composite_temperature"
) => {
  return http.get<TemperatureHistoryResponse, unknown>(
    `/api/temperature/history?days=${days}&source=${source}`
  );
};

export interface MultiItemsResponse {
  data: {
    source: string;
    date: string;
    /** 任一记录滞后（东财抓取失败时回退旧数据）即整体滞后 */
    stale?: boolean;
    items: Array<{
      item_type: string;
      item_code: string;
      item_name: string;
      data: any;
      /** 该记录是否为滞后数据（非实时） */
      stale?: boolean;
    }>;
  };
  message: string;
}

/**
 * 获取多维列表数据（乖离率、行业拥挤度等）
 * @param source 数据源，如 bias / crowding / sector_flow
 * @param date 指定日期，默认最新
 */
export const getMultiItems = (source: string, date?: string) => {
  let url = `/api/temperature/multi?source=${source}`;
  if (date) {
    url += `&date=${date}`;
  }
  return http.get<MultiItemsResponse, unknown>(url);
};

export interface CrowdingHistoryResponse {
  // 外部源不可用时后端返回 data: null + 可读 message（前端提示，不报错）
  data: {
    dates: string[];
    items: Array<{ code: string; name: string; values: (number | null)[] }>;
    freq: string;
    mode: string;
    indicator: string;
    category: string;
    source_kind?: string;
  } | null;
  message: string;
}

/**
 * 获取行业 / 赛道拥挤度历史序列（趋势视图）
 *
 * 历史序列不落库，由后端代理外部临时源并缓存（#1431；源见 #1502）。
 * @param category sw（申万行业）/ track（热门赛道）
 * @param indicator crowding / turnover_ratio / turnover_rate / ma60_ratio / high60_ratio / margin_ratio / big_order
 * @param freq weekly / monthly（外部源不支持 daily）
 * @param mode value（原值）/ pct（分位）
 */
export const getCrowdingHistory = (params: {
  category: string;
  indicator?: string;
  freq?: string;
  mode?: string;
}) => {
  const query = new URLSearchParams({
    category: params.category,
    indicator: params.indicator || "crowding",
    freq: params.freq || "weekly",
    mode: params.mode || "value"
  });
  return http.get<CrowdingHistoryResponse, unknown>(
    `/api/temperature/crowding-history?${query.toString()}`
  );
};
