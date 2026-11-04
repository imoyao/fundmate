/**
 * 投顾调仓明细的展示口径（#2740）。
 *
 * 为什么单列：同一批调仓数据现在有两个出口——自选速览抽屉（`quickView/QuickViewAdjustSection`）
 * 与产品详情页的持仓区块（`position/section/PositionAdvisorAdjusts`）。两处若各写一份
 * 「比例怎么拼」「加仓算哪种颜色」，就会出现「抽屉写 `10.00% → 20.00%`、详情页写
 * `10%→20%`」这类漂移——而它们是同一条调仓记录。
 *
 * 这里只放**口径**（拼字符串、判方向），不放类名或颜色：两边样式体系不同
 * （抽屉用 `wqv-op--add`，详情页用本区块的 BEM 类），类名由调用方映射。
 */
import type { AdvisorAdjustItem } from "@/api/funds";

/** 调仓方向：加仓 / 减仓用涨跌语义色，新增 / 建仓 / 持平保持中性（它们不是行情涨跌） */
export type AdvisorOpTone = "add" | "cut" | "neutral";

/**
 * 调仓方向口径。**两套用词并存**，因为来源不同：
 *
 * - 天天基金 / 且慢快照推导：`加仓` / `减仓` / `新增` / `建仓` / `持平`
 *   （`constants.ADVISOR_ADJUST_OP_NAME`）；
 * - 且慢**官方**调仓：`调入` / `调增` / `调出` / `调减` / `持平`
 *   （`/alfa/v1/graphql` 的 `movementName`，比前者细一档——「调入」是新建仓，「调增」是加仓）。
 *
 * 漏掉官方那套的后果不是报错，而是**整片变灰**：所有官方行的 op_name 都落进 `neutral`，
 * 页面看起来像「调仓功能坏了」。故两套都在这里映射，`持平` 与未知值一律中性。
 */
export function advisorOpTone(op: string | null | undefined): AdvisorOpTone {
  // 天天基金 / 快照推导
  if (op === "加仓") return "add";
  if (op === "减仓") return "cut";
  // 且慢官方（调入=新建仓，调增=加仓；调出=清仓，调减=减仓）
  if (op === "调入" || op === "调增") return "add";
  if (op === "调出" || op === "调减") return "cut";
  return "neutral";
}

/**
 * 调仓比例文案：只有一侧有值时也要说清是哪一侧（「10.00% → —」而不是空白），
 * 两侧都缺才返回空串（由调用方决定不显示这一行）。
 */
export function advisorRatioText(
  it: Pick<AdvisorAdjustItem, "pre_ratio" | "after_ratio">
): string {
  const pre = it.pre_ratio;
  const after = it.after_ratio;
  if (pre == null && after == null) return "";
  if (pre == null) return `${after?.toFixed(2)}%`;
  if (after == null) return `${pre.toFixed(2)}% → —`;
  return `${pre.toFixed(2)}% → ${after.toFixed(2)}%`;
}
