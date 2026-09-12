// frontend/src/composables/temperature/useTemperatureOverview.ts
// 市场温度总览数据 composable：探市页（/explore）的「概览」与「深度」两档共用。
//
// 【为什么是单例】（2026-09-12 重构，见 #980）
// 本 composable 原是**工厂函数**：每次调用都新建一整套 ref，并各自请求一次
// `GET /api/temperature/overview`。方案 D 把原独立温度计页收进探市页后，
// 「概览 / 深度」两档各调一次 ⇒ 切档（v-if 卸载重建）会**反复请求同一份数据**，
// 且两档各自持有一份互不感知的副本。
// 现改为**模块级单例 + 并发去重**：所有调用方共享同一份状态，同一时刻只发一个请求。
//
// 契约与改造前一致（返回字段不变）；唯一新增是 `fetchTemperature(force?)`。
// 抽取自 explore/index.vue 的温度数据块（原 587-740 行，见 #980）。
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

function createTemperatureOverview() {
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

  /** 真正执行请求（并发去重由外层 fetchTemperature 负责） */
  const doFetch = async () => {
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

  /** 进行中的请求：并发调用方复用它，不重复打接口 */
  let inflight: Promise<void> | null = null;

  /**
   * 拉取市场温度总览。
   * @param force 为 true 时忽略进行中的请求，强制再拉一次（手动刷新场景）
   */
  const fetchTemperature = (force = false): Promise<void> => {
    if (inflight && !force) return inflight;
    inflight = doFetch().finally(() => {
      inflight = null;
    });
    return inflight;
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

type TemperatureOverview = ReturnType<typeof createTemperatureOverview>;

/**
 * 模块级单例：探市页「概览」「深度」两档共享同一份温度数据。
 * 首次调用创建，后续调用直接复用（不新建 ref、不重复请求）。
 */
let shared: TemperatureOverview | null = null;

export function useTemperatureOverview(): TemperatureOverview {
  if (!shared) {
    shared = createTemperatureOverview();
  }
  return shared;
}
