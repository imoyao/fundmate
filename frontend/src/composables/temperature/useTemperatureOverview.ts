// frontend/src/composables/temperature/useTemperatureOverview.ts
// 市场温度总览数据 composable：探市页（/explore）的「概览」与「深度」两档共用。
// （2026-09-12 方案 D 前为 /explore 与 /temperature 两页共用。）
// 抽取自 explore/index.vue 的温度数据块（原 587-740 行），temperature 页后续接入（见 #980）。
// 契约以 explore 现有行为为基准：解析 getTemperatureOverview 的 singles/composites，
// 产出页面所需的全部温度 refs 与 fetchTemperature() 方法。
import { ref } from "vue";
import {
  getTemperatureOverview,
  type TemperatureOverviewResponse
} from "@/api/temperature";

/** 集思录估值指标（与后端 composites.jisilu_indicator 对齐，仅取页面所需字段） */
export interface JisiluIndicator {
  median_pb: number;
  median_pb_temperature: number;
  median_pb_level?: string;
  median_pe: number;
  median_pe_temperature: number;
  median_pe_level?: string;
}

export function useTemperatureOverview() {
  /** 请求进行中标记 */
  const loading = ref(false);
  /** 原始响应（data 部分），供需要完整数据的调用方使用 */
  const overview = ref<TemperatureOverviewResponse["data"] | null>(null);

  // 综合温度（后端两源合成，当前占位）
  const compositeTemperature = ref<{ value: number; level: string } | null>(
    null
  );

  // 自算·股债利差（不涉 PE）
  const selfCalcPercent = ref<number | null>(null);
  const selfCalcLevel = ref<string>("数据暂缺");

  // 来源链接（底部来源条）
  const links = ref<Record<string, string>>({});

  // 成交量
  const volumeData = ref<{ value: number; label: string } | null>(null);

  // L2 温度数据
  const fearData = ref<{ value: number; label: string } | null>(null);
  const jiucaishuoMediumData = ref<{ value: number; label: string } | null>(
    null
  );
  const qiemanData = ref<{ value: number; label: string } | null>(null);
  const youzhiData = ref<{ value: number; label: string } | null>(null);
  const cbTemperature = ref<number | null>(null);
  const cbLabel = ref<string>("");
  const jisiluIndicator = ref<JisiluIndicator | null>(null);

  const fetchTemperature = async () => {
    loading.value = true;
    try {
      const res = await getTemperatureOverview();
      const data = res.data;
      if (!data) throw new Error("无效响应");
      overview.value = data;

      // 自算·股债利差（不涉 PE）
      const selfCalc = data.composites?.self_calc;
      if (selfCalc) {
        selfCalcPercent.value = selfCalc.percent ?? null;
        selfCalcLevel.value = selfCalc.level ?? "暂无";
      } else {
        selfCalcLevel.value = "数据暂缺";
      }

      // 综合温度（两源合成）
      compositeTemperature.value =
        data.composites?.composite_temperature || null;

      // 来源链接
      links.value = data.links || {};

      // 成交量
      const vol = data.singles?.find(s => s.source === "eastmoney_volume");
      if (vol) {
        volumeData.value = {
          value: vol.value,
          label: vol.label || "温和"
        };
      }

      // L2：各类温度数据
      const singles = data.singles || [];

      const fear = singles.find(s => s.source === "jiucaishuo_fear");
      if (fear) {
        fearData.value = { value: fear.value, label: fear.label };
      }

      const medium = singles.find(s => s.source === "jiucaishuo_medium");
      if (medium) {
        jiucaishuoMediumData.value = {
          value: medium.value,
          label: medium.label
        };
      }

      const qieman = singles.find(s => s.source === "qieman");
      if (qieman) {
        qiemanData.value = { value: qieman.value, label: qieman.label };
      }

      const youzhi = singles.find(s => s.source === "youzhiyouxing");
      if (youzhi) {
        youzhiData.value = { value: youzhi.value, label: youzhi.label };
      }

      const cb = singles.find(s => s.source === "jisilu_cb");
      if (cb) {
        cbTemperature.value = cb.value;
        cbLabel.value = cb.label || "";
      }

      const indicator = data.composites?.jisilu_indicator;
      if (indicator) {
        jisiluIndicator.value = {
          median_pb: indicator.median_pb,
          median_pb_temperature: indicator.median_pb_temperature,
          median_pb_level: indicator.median_pb_level,
          median_pe: indicator.median_pe,
          median_pe_temperature: indicator.median_pe_temperature,
          median_pe_level: indicator.median_pe_level
        };
      }

      if (selfCalcLevel.value === "数据暂缺") {
        console.warn("自算股债利差数据暂缺，显示占位");
      }
    } catch (error) {
      console.warn("获取市场温度失败:", error);
      selfCalcLevel.value = "数据暂缺";
    } finally {
      loading.value = false;
    }
  };

  return {
    loading,
    overview,
    compositeTemperature,
    selfCalcPercent,
    selfCalcLevel,
    links,
    volumeData,
    fearData,
    jiucaishuoMediumData,
    qiemanData,
    youzhiData,
    cbTemperature,
    cbLabel,
    jisiluIndicator,
    fetchTemperature
  };
}
