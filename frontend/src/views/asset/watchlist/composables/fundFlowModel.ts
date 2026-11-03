/**
 * 板块资金面的纯计算与格式化（#watchlist 盘前资金面卡）。
 *
 * 抽出来的原因有二：
 *   1. 组件规模门禁（#980，400 行）——卡片同时要承载折叠数字条与展开双列榜；
 *   2. 「流入端 / 流出端怎么切」是这张卡唯一有语义的逻辑，必须能单测：
 *      早先的实现只取降序前 N（后端也只请求了降序前 50），导致「流出居前」
 *      其实只是「流入前 N 里恰好为负的两个」，文案与数据口径都不成立。
 */
import type { SectorFundFlow } from "@/utils/realtimeDataSources";

export interface SectorFlowBoard {
  /** 净流入为正的头部，按净流入降序 */
  inflow: SectorFundFlow[];
  /** 净流出最多的头部，按净流出从多到少（即净流入升序） */
  outflow: SectorFundFlow[];
}

/**
 * 把「流入 + 流出两端」的板块列表切成展示用的两块。
 *
 * 入参不要求有序：内部先按净流入降序排一遍，故调用方给全量或给两端合并结果都安全。
 * `topN` 为每侧数量。
 */
export function splitSectorFlow(
  list: SectorFundFlow[],
  topN: number
): SectorFlowBoard {
  const sorted = [...list].sort((a, b) => b.mainInflow - a.mainInflow);
  return {
    inflow: sorted.filter(s => s.mainInflow > 0).slice(0, topN),
    // 末尾即最负；reverse 后「流出最多」排第一
    outflow: sorted
      .filter(s => s.mainInflow < 0)
      .slice(-topN)
      .reverse()
  };
}

/**
 * 一句话资金主线：流入前三 + 流出前二（最被抛售的两端）。
 *
 * 无数据返回空串（模板据此不渲染）。两端都空时同样返回空串，
 * 不再拼出「获主力净流入居前。」这种半句。
 */
export function buildThemeLine(board: SectorFlowBoard): string {
  const inNames = board.inflow.slice(0, 3).map(s => s.name);
  const outNames = board.outflow.slice(0, 2).map(s => s.name);
  if (inNames.length && outNames.length) {
    return `今日资金主线：${inNames.join("、")} 获主力净流入居前；${outNames.join(
      "、"
    )} 主力净流出居前。`;
  }
  if (inNames.length) {
    return `今日资金主线：${inNames.join("、")} 获主力净流入居前。`;
  }
  if (outNames.length) {
    return `今日资金主线：${outNames.join("、")} 主力净流出居前。`;
  }
  return "";
}

/** 亿 / 万自适应缩写（亿元口径更贴合主力资金量级） */
export function formatFlow(v: number): string {
  const abs = Math.abs(v);
  const sign = v > 0 ? "+" : v < 0 ? "-" : "";
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${sign}${Math.round(abs / 1e4)}万`;
  return `${sign}${abs.toFixed(0)}`;
}

/** 板块涨跌幅：东财 `f3` 在 `fltt=2` 下已是百分数（0.31 = 0.31%） */
export function formatChangePct(v: number): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

/** 完整元（悬浮说明用） */
export function formatYuan(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toLocaleString("zh-CN")} 元`;
}

/** 资金流语义色（A 股习惯：流入红 / 流出绿） */
export function trendClassOf(mainInflow: number): string {
  if (mainInflow > 0) return "is-rise";
  if (mainInflow < 0) return "is-fall";
  return "is-flat";
}
