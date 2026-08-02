// frontend/src/store/modules/temperature.ts
import { defineStore } from "pinia";
import { getTemperatureOverview } from "@/api/temperature";

export interface TemperatureState {
  /** 综合市场温度值 0-100 */
  temperature: number | null;
  /** 综合温度档位文案，如「偏低·偏冷」 */
  temperatureLabel: string;
  /** 综合温度更新时间 */
  temperatureTime: string;
  /** 可转债温度 */
  cbTemperature: {
    value: number | null;
    label: string;
    caption: string;
  } | null;
  /** 市场宽度 */
  marketBreadth: {
    up: number | null;
    down: number | null;
    limitUp: number | null;
    limitDown: number | null;
  } | null;
  /** 指数快照 */
  indices: {
    hs300?: { value: number | null; caption: string };
    zz500?: { value: number | null; caption: string };
    cyb?: { value: number | null; caption: string };
    kcb50?: { value: number | null; caption: string };
    sh?: { value: number | null; caption: string };
    sz?: { value: number | null; caption: string };
    cb?: { value: number | null; caption: string };
    bse50?: { value: number | null; caption: string };
  } | null;
  /** 市场机会清单 */
  opportunityList: Array<{ name: string; desc: string; tone: "safe" | "normal" | "danger" }>;
  /** 加载态 */
  loading: {
    temperature: boolean;
    cbTemperature: boolean;
    marketBreadth: boolean;
    indices: boolean;
    opportunities: boolean;
  };
  /** 错误态 */
  error: {
    temperature: boolean;
    cbTemperature: boolean;
  };
}

const emptyState = (): TemperatureState => ({
  temperature: null,
  temperatureLabel: "",
  temperatureTime: "",
  cbTemperature: null,
  marketBreadth: null,
  indices: null,
  opportunityList: [],
  loading: {
    temperature: false,
    cbTemperature: false,
    marketBreadth: false,
    indices: false,
    opportunities: false
  },
  error: { temperature: false, cbTemperature: false }
});

/** 从概览响应映射出各指数快照 */
function mapIndices(singles: TemperatureState["indices"]) {
  return singles;
}

export const useTemperatureStore = defineStore("temperature", {
  state: (): TemperatureState => emptyState(),
  getters: {
    /** 温度档位 → 用于颜色/文案推导 */
    tempTone(state): "low" | "mid" | "high" {
      const v = state.temperature ?? 50;
      if (v < 40) return "low";
      if (v > 60) return "high";
      return "mid";
    }
  },
  actions: {
    async fetchTemperature(force = false) {
      if (this.loading.temperature && !force) return;
      this.loading.temperature = true;
      this.error.temperature = false;
      try {
        const res = await getTemperatureOverview();
        const d = res?.data;
        if (!d) return;
        const composite = d.composites?.composite_temperature;
        this.temperature = composite?.value ?? null;
        this.temperatureLabel = composite?.level ?? "";
        this.temperatureTime = d.updated_at ?? "";

        // 可转债温度：来自 jisilu_indicator 的中证转债中位数温度
        const jisilu = d.composites?.jisilu_indicator;
        if (jisilu) {
          this.cbTemperature = {
            value: jisilu.median_pb_temperature ?? null,
            label: jisilu.median_pb_temperature != null ? this.cbLevel(jisilu.median_pb_temperature) : "",
            caption: jisilu.price_dt ? `数据时间 ${jisilu.price_dt}` : ""
          };
        }

        // 指数快照：从 singles 映射
        const indices: TemperatureState["indices"] = {};
        for (const s of d.singles ?? []) {
          const key = s.source;
          const allow = ["hs300", "zz500", "cyb", "kcb50", "sh", "sz", "cb", "bse50"];
          // singles.source 为后端指标源名，按 name 宽松匹配
          const matched = allow.find(k => s.name.includes(k.toUpperCase()) || s.source.includes(k));
          if (matched) {
            (indices as any)[matched] = {
              value: typeof s.value === "number" ? s.value : null,
              caption: s.label ?? ""
            };
          }
        }
        this.indices = mapIndices(indices);

        // 市场宽度：jisilu 提供涨跌家数线索，缺失时留空
        if (jisilu) {
          this.marketBreadth = {
            up: null,
            down: null,
            limitUp: null,
            limitDown: null
          };
        }

        // 市场机会：基于 self_calc 股债利差做简单解读
        const self = d.composites?.self_calc;
        this.opportunityList = this.buildOpportunities(self, this.temperature);
      } catch {
        this.error.temperature = true;
      } finally {
        this.loading.temperature = false;
      }
    },
    async fetchCbTemperature(force = false) {
      if (this.loading.cbTemperature && !force) return;
      this.loading.cbTemperature = true;
      this.error.cbTemperature = false;
      try {
        if (this.cbTemperature == null) {
          await this.fetchTemperature(true);
        } else {
          // 已随综合温度一起拉取，这里仅刷新档位文案
          if (this.cbTemperature.value != null) {
            this.cbTemperature = {
              ...this.cbTemperature,
              label: this.cbLevel(this.cbTemperature.value)
            };
          }
        }
      } catch {
        this.error.cbTemperature = true;
      } finally {
        this.loading.cbTemperature = false;
      }
    },
    fetchMarketBreadth(force = false) {
      if (this.loading.marketBreadth && !force) return;
      this.loading.marketBreadth = true;
      return this.fetchTemperature(force)
        .finally(() => (this.loading.marketBreadth = false));
    },
    fetchIndices(force = false) {
      if (this.loading.indices && !force) return;
      this.loading.indices = true;
      return this.fetchTemperature(force)
        .finally(() => (this.loading.indices = false));
    },
    fetchOpportunities(force = false) {
      if (this.loading.opportunities && !force) return;
      this.loading.opportunities = true;
      return this.fetchTemperature(force)
        .finally(() => (this.loading.opportunities = false));
    },
    /** 可转债温度 → 档位文案 */
    cbLevel(v: number): string {
      if (v <= 15) return "极冷·机会区";
      if (v <= 35) return "偏冷";
      if (v <= 65) return "中性";
      if (v <= 85) return "偏热";
      return "极热·谨慎";
    },
    buildOpportunities(
      self: { spread_pct?: number; level?: string } | undefined,
      temp: number | null
    ): TemperatureState["opportunityList"] {
      const list: TemperatureState["opportunityList"] = [];
      if (self && typeof self.spread_pct === "number") {
        const tone = self.spread_pct > 3 ? "safe" : self.spread_pct < 1.5 ? "danger" : "normal";
        list.push({
          name: "股债性价比",
          desc: `利差 ${self.spread_pct.toFixed(2)}%，${self.level ?? "中性"}`,
          tone
        });
      }
      if (temp != null) {
        const tone = temp < 40 ? "safe" : temp > 60 ? "danger" : "normal";
        list.push({
          name: "综合温度",
          desc: `当前 ${temp.toFixed(1)}，${this.temperatureLabel || "中性"}`,
          tone
        });
      }
      return list;
    }
  }
});

export function useTemperatureStoreHook() {
  return useTemperatureStore();
}
