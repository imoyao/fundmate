import type { fetchProAllocation } from "@/api/products";

/**
 * 「资产配置与相关性」区块的口径（#980 拆分，纯函数）。
 *
 * 抽出来的理由很实际：档位阈值（0.8 / 0.4）与四段文案是最容易被顺手改掉的
 * 地方——把 `>=` 写成 `>`、或把 ρ = −0.4 归到「关联很弱」，视觉上只差一档颜色，
 * review 时几乎看不出，但结论就错了。
 */

export type AllocData = Awaited<ReturnType<typeof fetchProAllocation>>["data"];

/** 单只对比标的（相关性行） */
export type AllocPeer = AllocData["peers"][number];

/** 高度相关阈值，与后端 analytics 口径一致（ρ ≥ 0.8 视为实际未分散） */
export const HIGH_THRESHOLD = 0.8;
/** 中等相关阈值：以上值得提示，以下不必强调 */
export const MID_THRESHOLD = 0.4;

export const DASH = "—";

export type AllocTone = "danger" | "warn" | "hedge" | "low";

/**
 * ρ 的档位（决定配色）；档位→令牌的映射只在 CSS 出现一次，见各组件样式区。
 *
 * 边界是**闭区间**：ρ 恰为 0.8 就已是「实际未分散」，恰为 −0.4 就已是「反向对冲」。
 */
export function tone(rho: number): AllocTone {
  if (rho >= HIGH_THRESHOLD) return "danger";
  if (rho >= MID_THRESHOLD) return "warn";
  if (rho <= -MID_THRESHOLD) return "hedge";
  return "low";
}

/** 发散条半宽：|ρ| × 50%（半轨），ρ = 1 时贴满一侧、抵达轨道边缘 */
export function barWidth(rho: number): string {
  return `${Math.round(Math.abs(rho) * 50)}%`;
}

/** 图例：原每行重复的定性文案收敛到此（#2400） */
export const LEGEND = [
  { tier: "danger", text: `风险集中 ρ ≥ ${HIGH_THRESHOLD}` },
  { tier: "warn", text: "明显联动" },
  { tier: "hedge", text: "反向对冲" },
  { tier: "low", text: "关联很弱" }
] as const;

/**
 * 高度相关的总结句：这条才是本模块真正要让 user 看见的话。
 *
 * 没有 peer 时不说话（null）——此时页面走的是空态引导，不是「没有强联动」。
 */
export function buildSummary(
  peerCount: number,
  highCount: number
): string | null {
  if (peerCount === 0) return null;
  if (highCount === 0) {
    return `与你其余 ${peerCount} 只持仓中，没有ρ ≥ ${HIGH_THRESHOLD} 的强联动标的——这一只确实带来了分散。`;
  }
  return `与你其余 ${peerCount} 只持仓中，有 ${highCount} 只相关系数 ≥ ${HIGH_THRESHOLD}——账面分散了，风险未必。`;
}

/** 跳过的持仓说明（诚实披露，不静默丢弃） */
export function buildSkippedNote(
  data: AllocData | null | undefined
): string | null {
  const n = data?.skipped_count ?? 0;
  if (n <= 0) return null;
  return `另有 ${n} 只持仓因同期交易日不足 ${data?.min_overlap ?? 60} 天或无波动未纳入计算`;
}

/** 脚注：口径、窗口与样本量，缺一不可复核 */
export function buildFootnote(data: AllocData | null | undefined): string {
  if (!data) return "";
  const parts: string[] = [];
  if (data.basis) parts.push(data.basis);
  parts.push(`近${data.window}窗口 · 基准序列 ${data.sample_days} 个交易日`);
  if (data.caveats.length) parts.push(data.caveats[0]);
  return parts.join(" · ");
}
