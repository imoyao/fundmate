/**
 * 持仓「到期日」的展示与可编辑判据（#931 / D121）。
 *
 * 为什么单独一个模块：这段判断有三处消费方（持仓表的产品信息格、到期日弹窗的提示语、
 * 将来的其它入口），而两种品类的**语义完全不同**——逆回购到期即转现金、不再计入投资；
 * 银行理财到期只是钱回到活期，持仓仍按当前金额计入。写成字符串散在模板里，迟早
 * 一处说「到期就没了」、另一处说「到期还在」。
 *
 * 品类集合与后端 `services/position_write_policy.MATURITY_ASSET_TYPES` 同源：
 * 前端多一个品类 ⇒ 点了就 400；少一个 ⇒ 明明是逆回购却没有入口。
 */

import type { CashLikeBreakdownRow } from "@/composables/ledger/types";
import { formatDate } from "@/utils/date";

/** 有「到期日」语义的品类（后端 fail closed 白名单，改动须同步 position_write_policy） */
export const MATURITY_ASSET_TYPES = ["reverse_repo", "bank_wealth"] as const;

/** 该品类是否可设到期日；`assetType` 缺省（未选标的）时为 false */
export function isMaturityEditable(assetType?: string | null): boolean {
  return (MATURITY_ASSET_TYPES as readonly string[]).includes(assetType ?? "");
}

export type MaturityState = "unset" | "upcoming" | "due";

/**
 * 到期状态。**到期当日算 `due`**——与后端判定逐字一致：`effective_count_as_investment`
 * 用 `as_of < maturity` 判「未到期」，故到期当天逆回购已经变成现金。
 * 前端若用 `>` 判，到期日当天会显示「还有 0 天/未到期」，与资产口径自相矛盾。
 *
 * `today` 可注入（默认今天），测试不必跟着日历走。
 */
export function maturityState(
  iso?: string | null,
  today: string = formatDate(new Date())
): MaturityState {
  if (!iso) return "unset";
  return today >= iso ? "due" : "upcoming";
}

/** 产品信息格里那枚可点的短标签文案 */
export function maturityChipText(
  iso?: string | null,
  today: string = formatDate(new Date())
): string {
  if (!iso) return "设到期日";
  // 直接比字符串即可：wire 值恒为 `YYYY-MM-DD`（后端 iso_date_only 保证）
  return maturityState(iso, today) === "due"
    ? `到期 ${iso} · 已到期`
    : `到期 ${iso}`;
}

/**
 * 弹窗里的口径说明。两类的差别必须说清，不能共用一句「到期日」：
 * 逆回购到期会影响**总资产分类**（转现金），银行理财不影响（只记录）。
 */
export function maturityHint(assetType?: string | null): string {
  if (assetType === "reverse_repo") {
    return "逆回购到期后自动转为现金、不再计入投资；清空则视为「未到期」，一直计入投资。";
  }
  if (assetType === "bank_wealth") {
    return "仅作记录：到期后资金回到活期，但持仓仍按当前金额计入总资产——回款请另记一笔现金。";
  }
  return "该品类没有到期日。";
}

/**
 * 只有银行理财能在本弹窗改名称与登记编码。
 *
 * 基金 / 股票的名称与代码是行情名录（`funds` / `securities`）的投影——用户改它只会让
 * 持仓与名录对不上（估值查不到、分红匹配不到），名录错应该修名录；后端对这个越界
 * fail closed 到 400。银行理财没有中心目录（D121），整条记录都是用户手填的，填错
 * 必须能改。判据与后端 `apply_identity_edit` 的品类守卫同源，两边不一致的形态是
 * 「前端给了输入框、点了红一片」。
 */
export function canEditIdentity(assetType?: string | null): boolean {
  return assetType === "bank_wealth";
}

/** 弹窗标题：银行理财进来是为了改产品信息，只写「到期日」会让人找不到编码栏 */
export function maturityDialogTitle(assetType?: string | null): string {
  return canEditIdentity(assetType) ? "银行理财信息" : "到期日";
}

/** 弹窗提交载荷：到期日必带（null = 清空），名称与编码只在手工标的时出现 */
export interface PositionEditPayload {
  maturity_date: string | null;
  name?: string;
  symbol?: string;
}

/**
 * 这笔逆回购到期后还要不要引导去「登记到期回款」。
 *
 * 三个条件缺一不可，各自失效方式都不报错：
 * 1. 品类是逆回购——银行理财到期只是钱回到活期，**没有回款这个动作**（D121）；
 * 2. 到期日不晚于今天——未来日期只是记一下，现在提示「已转现金」是假警报；
 * 3. 类现金明细里还有在途本金（`net_amount > 0`）——已经结清过再引导，后端只会回
 *    「没有在途本金」，用户点了等于白点。
 *
 * 返回类现金明细行本身（而不是布尔）：调用方要拿它填结清弹窗的本金与开户账户。
 */
export function dueSettleCandidate(input: {
  assetType?: string | null;
  symbol?: string | null;
  maturityDate?: string | null;
  /** 账户概览下发的 `cash_like_breakdown`（已含账外孤儿流水） */
  rows: CashLikeBreakdownRow[];
  today?: string;
}): CashLikeBreakdownRow | null {
  if (input.assetType !== "reverse_repo") return null;
  if (maturityState(input.maturityDate, input.today) !== "due") return null;
  const symbol = input.symbol;
  if (!symbol) return null;
  return (
    input.rows.find(
      row =>
        row.symbol === symbol &&
        row.asset_type === "reverse_repo" &&
        row.net_amount > 0
    ) ?? null
  );
}
