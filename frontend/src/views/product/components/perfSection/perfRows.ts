import type { FundPerformanceResult } from "@/api/products";
import {
  DASH,
  PEER_METRIC_LABEL,
  fmtPct,
  fmtRatio,
  peerText
} from "./perfFormat";

/**
 * 指标行的构造（#980 拆分，纯函数）。
 *
 * 抽出来的价值：行序、hint 文案、以及「全空就不画这一块」的判定都能被单测钉住。
 * 原实现把这三件事写在 computed 里，改一个字段名不会有任何测试报警。
 */

/** 一行指标的展示形态（PerfFactGrid 的输入） */
export interface PerfFactItem {
  key: string;
  label: string;
  /** 有 hint 才渲染解释图标（el-tooltip） */
  hint?: string;
  /** 已格式化的文本值 */
  value?: string;
  /** 数值：走 RiseFallText 的涨跌色（区间收益用） */
  num?: number | null;
  /** 值下方的口径副行（高点 / 区间） */
  sub?: string;
}

/**
 * 风险比（#167）：只摆数字与口径，不给排序、不着色 —— 跨类别不可比。
 * 债基波动天生小、夏普系统性偏高，画排行榜就是误导。
 */
export function buildRiskRows(p: FundPerformanceResult | null): PerfFactItem[] {
  if (!p || p.fund_kind !== "fund") return [];
  return [
    {
      key: "calmar",
      label: "卡玛比率",
      hint: "赚的钱抵不抵得过最深的亏损——年化收益 ÷ 最大回撤，数字越大越划算",
      value: fmtRatio(p.calmar)
    },
    {
      key: "sortino",
      label: "索提诺",
      hint: "思路和夏普一样，但只把下跌的波动算作风险：涨得猛不会拉低它，跌得又频繁又深才会",
      value: fmtRatio(p.sortino)
    },
    {
      key: "sharpe",
      label: "夏普",
      hint: "（年化收益 − 无风险利率）÷ 年化波动率——每承担 1 份波动换来多少超额回报",
      value: fmtRatio(p.sharpe)
    },
    {
      key: "ulcer",
      label: "溃疡指数",
      hint: "回撤的深度与持续时间合成的值（UI）——越大说明持有过程越煎熬",
      value: fmtPct(p.ulcer_index)
    },
    { key: "upi", label: "UPI", hint: "年化收益 / UI", value: fmtRatio(p.upi) },
    {
      key: "rrd",
      label: "波回比",
      hint: "年化收益 ÷（波动率 × 最大回撤）：平时涨跌的幅度和最深一次亏损都算进分母，数字越大越好",
      value: fmtRatio(p.return_drawdown_ratio)
    },
    {
      // #167 收尾 · 拟涨幅2：四段**互不重叠**区间收益的加权连乘。
      // 它与上面的比值族不同源（比值族看「风险调整后收益」，它看「多周期收益合成」），
      // 故在 hint 里点明口径，避免被当成「另一个夏普」。历史不足一年时为「—」。
      key: "shape_gain2",
      label: "拟涨幅",
      hint: "把最近 1 个月、3 个月、6 个月、1 年四段互不重复的涨幅，按越近占比越高合成的参考值",
      value: fmtPct(p.shape_gain2?.shape_gain2)
    }
  ];
}

/** 同类分位：按固定键序取有值的项（缺键即后端判定样本不足，不补位） */
export function buildPeerRows(p: FundPerformanceResult | null): PerfFactItem[] {
  const pcts = p?.peer_percentiles;
  if (!pcts) return [];
  return Object.keys(PEER_METRIC_LABEL)
    .filter(k => pcts[k] != null)
    .map(k => ({
      key: k,
      label: PEER_METRIC_LABEL[k],
      // 分位在这里就折成「前 12%」：模板只负责排版，不再做换算
      value: peerText(pcts[k])
    }));
}

/** 基准相对指标行（仅 available=true 时） */
export function buildBenchmarkRows(
  p: FundPerformanceResult | null
): PerfFactItem[] {
  const b = p?.benchmark;
  if (!b || !b.available) return [];
  return [
    {
      key: "excess",
      label: "超额收益",
      hint: "基金年化 − 基准年化",
      value: fmtPct(b.excess_return)
    },
    {
      key: "ir",
      label: "信息比率",
      hint: "年化超额 / 跟踪误差；>1 说明超额比较稳定",
      value: fmtRatio(b.information_ratio)
    },
    {
      key: "up",
      label: "上行捕获",
      hint: "基准涨时它涨多少；>100% = 涨得比基准多",
      value: fmtPct(b.upside_capture)
    },
    {
      key: "down",
      label: "下行捕获",
      hint: "基准跌时它跌多少；<100% = 跌得比基准少",
      value: fmtPct(b.downside_capture)
    }
  ];
}

/** 全空不画：一排「—」是「没数据」的另一种噪声 */
export function hasAnyValue(rows: PerfFactItem[]): boolean {
  return rows.some(r => r.value !== DASH);
}
