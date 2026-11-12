/**
 * 删除单笔交易流水的确认文案（全站唯一来源，2026-11-12 抽取）。
 *
 * 同一句确认曾两处各写一份（持仓抽屉 `PositionTransactionsList` 与对账中心
 * 抽屉「投资轨迹」`ReconInvestmentTrail`），口径分叉只是时间问题。这里只出
 * **纯文本**；弹窗调用（ElMessageBox.confirm）与删除成功后的控制流由各容器
 * 自己接——控制流允许按容器差异微调，这句话不许再有第二个版本。
 */
export function transactionDeleteConfirmText(label: string): string {
  return `删除后「${label}」的份额与成本会按剩余流水重算；若删的是建仓那笔，持仓会失去成本来源。`;
}
