// frontend/src/api/temperature.ts
import { http } from "@/utils/http";

export interface TemperatureOverviewResponse {
  data: {
    updated_at: string;
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
      };
    };
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
  return http.get<TemperatureOverviewResponse, unknown>("/api/temperature/overview");
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
export const getTemperatureHistory = (days: number = 90, source: string = "composite_temperature") => {
  return http.get<TemperatureHistoryResponse, unknown>(`/api/temperature/history?days=${days}&source=${source}`);
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
