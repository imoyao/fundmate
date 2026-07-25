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
      collected_at: string;
    }>;
    composites: {
      self_calc?: {
        pe: number;
        percent: number;
        level: string;
        spread_pct: number;
        y10: number;
        cpi: number;
        collected_at: string;
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
  return http.get<TemperatureOverviewResponse>("/api/temperature/overview");
};
