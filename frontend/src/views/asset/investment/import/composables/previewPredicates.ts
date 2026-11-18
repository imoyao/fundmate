/**
 * 预览阶段纯谓词（#2876 增量 1）：从巨型 useImportWizard.ts 下沉的、与 Vue 运行时
 * 完全无关的「行级判定」集合。
 *
 * 设计约束（红线）：
 * - 本文件不 import vue、不读任何 ref / computed，全部函数只吃 `row` 入参，纯函数。
 * - 所有判定口径与 useImportWizard 内历史实现逐字一致——本次只是**搬家**，不修行为。
 * - 任何改动「分类口径」的诉求，都必须先改此处并同步四问验收，禁止在调用点手抄副本。
 *
 * 为什么下沉：#1791 验收②「卡片条数 = 展开后表格条数」靠「三处共用同一谓词」结构性成立，
 * 而不是两处各数一遍对数。把这些谓词集中到无 Vue 依赖的模块，既便于单测（vitest 直接喂
 * 行对象），也避免继续在 3000+ 行的组合式里堆砌纯逻辑（#2876 防上帝模块复发的第一步）。
 */

import type { PreviewRow } from "./previewRow";

/** 问题摘要面板的三卡片分类（#1791）。三类**互斥完备**：每行恰属一类，卡片条数之和恒等于总行数。 */
export type SummaryCategory = "complete" | "duplicate" | "fix";

/**
 * 代码未匹配（fixSectionRows 的 missingCode 分区谓词）。
 *
 * `cash` / `money_fund` 直接放行：这两类入库走同一分支（后端
 * `orchestrator_commit` 的「现金管理类」），**根本不写 symbol**——要它填代码
 * 等于要它填一个自己都不用的字段。券商原文这些行本来就不给代码
 * （table1101.xls 实测：利息归本 2 条、基金红利拨入 5 条，两列皆空），
 * 按 missingCode 拦下会让用户勾不上、也算不进任何计数，只能对着一个
 * 「代码未匹配」标签干看（#2840 / #2843）。
 */
export function isMissingCode(row: PreviewRow): boolean {
  if (row.type === "cash" || row.type === "money_fund") return false;
  return !row.symbol || row.symbol === "UNKNOWN";
}

/**
 * 入账不要求「数量 + 价格」齐全的类型。这些行的金额另有来源（税额、派息额、
 * 兑付到账额），没有成交价格是正常的——`bond_redeem` 是 #2835 之后的常态：
 * 交割单的兑付行只给「发生金额」，成交均价一栏常常是 0。
 */
export const QTY_PRICE_OPTIONAL_OPS = new Set([
  "tax",
  "dividend",
  "dividend_cash",
  "dividend_reinvest",
  "split",
  "bond_redeem"
]);

/**
 * 金额与「数量 × 价格」**无关**的类型：拿成交口径去比对必然误报。
 *
 * - `tax`：税额 = 税率 × 利息。真实交割单的交割「数量/单价」沿用了利息行的
 *   60 / 1.5，于是 |60 × 1.5 − (−18)| = 108 元差额——一分钱问题都没有，
 *   却被判成「数据不一致」，把好好的兑息组染红（#2836 实测）。
 * - `bond_redeem`：兑付到账额 = 面值 × 数量 + 应计利息 − 税，本就不等于
 *   单价 × 数量。
 *
 * 与 `QTY_PRICE_OPTIONAL_OPS` 分开而不是合并：那份管「缺不缺字段」，
 * 这份管「金额该不该这么算」，混成一个集合会让两处判据都无法单独演进。
 */
export const AMOUNT_INDEPENDENT_OPS = new Set(["tax", "bond_redeem"]);

/**
 * 金额差额（元）= |数量×单价 − 金额|。任一端缺失返回 0——缺失由
 * `isMissingAmount` / `isRowBlocked` 负责，此处不重复报警。
 *
 * 两类例外见 `AMOUNT_INDEPENDENT_OPS`；合并行（息 + 税折成的净额行）另用
 * **组等式**：`数量 × 单价 − 组内税额 = 净额`。丰山转债 60 × 1.5 − 18 = 72，
 * 差额 0；不给合并行减掉组内税额的话，18 元的税会被当成 18 元的差额误报。
 */
export function feeDiffOf(row: PreviewRow): number {
  if (AMOUNT_INDEPENDENT_OPS.has(row.op_type)) return 0;
  const qty = Number(row.quantity);
  const prc = Number(row.price);
  const amt = Number(row.amount);
  if (isNaN(qty) || qty <= 0) return 0;
  if (isNaN(prc) || prc <= 0) return 0;
  if (isNaN(amt)) return 0;
  const groupTax = row.is_merged ? taxTotalOf(row) : 0;
  return Math.abs(qty * prc - groupTax - amt);
}

/** 合并行内已并入净额的税额合计（它们本来就从成交额里扣掉了）。 */
export function taxTotalOf(row: PreviewRow): number {
  const children: PreviewRow[] = Array.isArray(row.children)
    ? row.children
    : [];
  return children
    .filter(c => c.op_type === "tax")
    .reduce((sum, c) => sum + Math.abs(Number(c.amount) || 0), 0);
}

/**
 * 差额**被手续费解释**（2026-11-02）：同花顺交割单的「发生金额」是含手续费的发生额，
 * 而入库 `amount` 恒按 单价×数量 重算（`position_service.py` 卖出/买入分支）、fee 另列，
 * 于是带费行在预览里天然差一笔 fee。判据 `差额 ≤ |fee| + 0.01` 即视为已解释。
 *
 * 与 `isAmountMismatch` **互斥且互补**（差额 ≤ 0.01 时两者皆 false）：
 * 解释得掉 → 归「数据完整」可导入；解释不掉 → 才进 mismatch 分区。
 * 旧版只看 `差额 > 0.01`，把全部带费行打成「需要修正」（#磁盘 152 条的成因）。
 */
export function isFeeExplained(row: PreviewRow): boolean {
  const diff = feeDiffOf(row);
  if (diff <= 0.01) return false;
  return diff <= Math.abs(Number(row.fee) || 0) + 0.01;
}

/**
 * 金额不一致（fixSectionRows 的 mismatch 分区谓词）：有份额有价格，但差额
 * **超出**手续费能解释的范围。超出的那部分才是真对不上——费用列可能漏项
 * （只有佣金缺印花税/过户费），或金额本身被改过。
 */
export function isAmountMismatch(row: PreviewRow): boolean {
  const diff = feeDiffOf(row);
  if (diff <= 0.01) return false;
  return diff > Math.abs(Number(row.fee) || 0) + 0.01;
}

/**
 * 三卡片分类谓词——卡片条数、fix 细分统计、表格状态过滤三处共用（#1791 验收②：
 * 「卡片条数 = 展开后表格条数」靠共用谓词结构性成立，而不是两处各数一遍对数）。
 *
 * - duplicate：解析期已判重（(ledger_id, import_hash) 已在库）
 * - fix：解析错误 → 代码未匹配 → 数量/价格缺失 → 金额不一致（顺序对齐 fixSectionRows 分区）
 * - complete：其余——含资金划转行（数据完整，是否入库由后端统一裁决 #1010）、
 *   含 _ignored 行（数据完整是质量口径，勾没勾是选择口径，二者分开）
 */
export function categorizeRow(row: PreviewRow): SummaryCategory {
  if (row.is_duplicate) return "duplicate";
  if (row.error) return "fix";
  if (row.is_cash_transfer) return "complete";
  if (isMissingCode(row)) return "fix";
  if (isRowBlocked(row)) return "fix";
  if (isAmountMismatch(row)) return "fix";
  return "complete";
}

/**
 * 这行有没有「需要修正」的问题——与 `fixSectionRows` 的分区判据同源
 * （顺序也对齐：error → missingCode → missingQtyPrice → mismatch）。
 *
 * 抽出来是因为 `mergeLinkGroups` 要问同一个问题：能不能把一组折起来，取决于
 * 这组干不干净。两处各写一份必然漂移，而漂移的后果就是「概览条说这组没问题、
 * 修正面板里却躺着一条」这种用户没法自己解释的矛盾。
 */
export function hasFixProblem(row: PreviewRow): boolean {
  if (row.is_duplicate || row.is_cash_transfer) return false;
  return (
    Boolean(row.error) ||
    isMissingCode(row) ||
    isRowBlocked(row) ||
    isAmountMismatch(row)
  );
}

export function isRowBlocked(row: PreviewRow): boolean {
  if (row.is_cash_transfer || row.error || row.is_duplicate) return false;
  // #2836：被配对消费的行不入账，自然不需要凑齐数量价格。真实交割单的
  // 「股份转出」只有份额（110 张）、没有价格——不豁免的话它会被判「待补全」，
  // 用户被迫去填一个根本用不到的单价。
  if (row.consumed_by) return false;
  // #2836：豁免清单收敛到 QTY_PRICE_OPTIONAL_OPS（原先是就地写死的 5 个 op_type，
  // 加 bond_redeem 时漏改就会让「兑付无价格」被判待补全——而这已是常态）
  if (QTY_PRICE_OPTIONAL_OPS.has(row.op_type)) return false;
  if (row.type === "money_fund" || row.type === "reverse_repo") return false;
  const qty = Number(row.quantity),
    prc = Number(row.price);
  return isNaN(qty) || qty <= 0 || isNaN(prc) || prc <= 0;
}

/**
 * 全选 / 恢复忽略行的勾选取止：疑似重复行默认不勾（要导自己手动勾，#1882），
 * 解析错误 / 数量价格缺失 / 资金划转 / 已忽略行不参与。
 * selectAllValid 与 toggleIgnoreRow 恢复分支共用，保证两处口径一致。
 */
export function isAutoSelectableRow(row: PreviewRow): boolean {
  return (
    !row.is_duplicate &&
    !row.error &&
    !isRowBlocked(row) &&
    // #2836：代码未匹配的行没有产品可落，后端建不出持仓——默认勾上等于
    // 让用户在「确认导入」之后才吃一次失败回执
    !isMissingCode(row) &&
    !row.is_cash_transfer &&
    !row._ignored &&
    // #2836：被消费的行勾了也白勾（后端跳过），默认不选才是诚实的选择
    !row.consumed_by
  );
}
