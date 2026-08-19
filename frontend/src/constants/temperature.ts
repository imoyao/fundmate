// src/constants/temperature.ts
/**
 * 温度计页（views/temperature）业务常量。
 * 从 temperature/index.vue 拆分下沉（#980），供页面与表格组件共享，
 * 避免同一阈值/映射在多个文件重复定义。
 */

/** 来源标识 -> 中文显示名（避免页面出现拼音/英文） */
export const SOURCE_DISPLAY_NAMES: Record<string, string> = {
  jiucaishuo_fear: "韭圈儿",
  jiucaishuo_medium: "韭圈儿",
  qieman: "且慢",
  youzhiyouxing: "有知有行",
  jisilu_cb: "集思录",
  jisilu_indicator: "集思录",
  eastmoney_volume: "东财",
  eastmoney: "东财",
  self_calc: "自算",
  fulai: "富来智投",
  default: ""
};

/** 已在顶部核心指标展示过的 singles source，底部「全部市场温度指标」区域过滤掉，避免同页信息重复 */
export const CORE_SINGLE_SOURCES = [
  "jiucaishuo_fear",
  "jisilu_cb",
  "eastmoney_volume"
];

/** 乖离率进度条可视范围（以 0 为中心，[-20, 20] 映射到进度条） */
export const BIAS_BAR_RANGE = 20;

/** 乖离率档位阈值：|bias| >= 15 极端高/低，>= 5 偏高/低 */
export const BIAS_EXTREME_THRESHOLD = 15;
export const BIAS_HIGH_THRESHOLD = 5;

/** 行业拥挤度档位阈值：< 30 冷（低），> 70 热（高），其余中性 */
export const CROWDING_LOW_THRESHOLD = 30;
export const CROWDING_HIGH_THRESHOLD = 70;
