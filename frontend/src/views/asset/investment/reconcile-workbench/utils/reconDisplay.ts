/**
 * 对账中心「后端数据 → 用户语言」翻译层（2026-11-07 新增）。
 *
 * ## 存在理由
 * 此前页面把后端字段原样渲染：`20|001982`、`has_candidate`、`net_mismatch`、
 * `#57 buy 2025-12-12T00:00:00`、`active`、`-17.5 元 → #12`。这些是**程序员视角**的
 * 存储结构，不是用户要做的事。用户看到的应该是「哪笔交易、缺什么、现在能做什么」。
 *
 * 本文件是**纯函数**，不依赖 Vue、不发请求、不推导业务结论。所有「能否处理」的判据
 * 仍以后端 `fixable` / `block_reason` 为准（见 `api/reconciliation.ts`）；这里只把
 * 后端已经给出的信号翻译成中文，不新增判据、不替用户猜归属。
 *
 * ## 口径依据
 * - 日期：`frontend/design.md:1120` 全站走 `@/utils/date`，ISO 带 T 禁止原样渲染。
 * - 金额：`frontend/design.md:1095` ¥ 与数字同基线、千分位、金额 2 位、负号只生成一次。
 * - 文案：`frontend/design.md:1083` 动词 + 名词、禁「请」、禁模糊词。
 * - 枚举：`@/constants` 的 `TXN_TYPE_LABELS` 是全站唯一来源，此处只补兜底。
 */

import { TXN_TYPE_LABELS } from "@/constants";
import { formatDate, formatDateTime } from "@/utils/date";
import { formatAmount } from "@/utils/currency";
import { specialSymbolLabel } from "./reconLabels";

/** 交易类型兜底词：未知码也不许露英文（宁可说「其他类型」，不给用户看存储码） */
const TXN_TYPE_FALLBACK = "其他类型";

/** 交易类型中文。空值按「未填」处理，不返回空串让界面出现空白格。 */
export function reconTxnType(type: string | null | undefined): string {
  if (!type) return "未填类型";
  return TXN_TYPE_LABELS[type] ?? TXN_TYPE_FALLBACK;
}

/**
 * 域 F 的 flags 中文（后端 `dangling_ref_service.py:47-49` 全集，
 * 外加「挂错标的」一类的 `dangling_ref_mislink_service._mislink_flags`）。
 * 未知 flag 归「其他异常」，绝不把 `some_new_flag` 直接印给用户。
 */
const DANGLING_FLAG_LABELS: Record<string, string> = {
  no_symbol: "缺标的代码",
  has_candidate: "已找到可挂回的持仓",
  net_mismatch: "份额与流水不一致",
  cleared_target: "目标持仓已清仓",
  blocked: "暂时不能自动处理",
  mislinked: "挂在别的标的的持仓上",
  no_target: "同标的没有持仓记录",
  venue_conflict: "同代码有不同场所的持仓"
};

export function reconFlag(flag: string): string {
  return DANGLING_FLAG_LABELS[flag] ?? "其他异常";
}

/** 持仓归属状态。后端 `ownership_status` 目前有 active / cleared，未知码不露英文。 */
const OWNERSHIP_LABELS: Record<string, string> = {
  active: "有效",
  cleared: "已清仓"
};

export function reconOwnership(status: string | null | undefined): string {
  if (!status) return "状态未填";
  return OWNERSHIP_LABELS[status] ?? "其他状态";
}

/**
 * 交易日期。`null` 不是「缺交易日期」五个字混在一行里，而是明确的可筛选状态。
 * 后端可能给 `2025-12-12T00:00:00` 或 `2025-12-12`，两者都收敛到 `YYYY-MM-DD`。
 */
export function reconTradeDate(iso: string | null | undefined): string {
  if (!iso) return "交易日期未填";
  const formatted = formatDate(iso);
  return formatted === "--" ? "交易日期未填" : formatted;
}

/** 导入批次时间：`2026-06-07 18:33`，不带秒（design.md:1125） */
export function reconBatchTime(iso: string | null | undefined): string {
  if (!iso) return "时间未填";
  const formatted = formatDateTime(iso);
  return formatted === "--" ? "时间未填" : formatted;
}

/**
 * 金额（元）。后端域 F/G 的 `amount` / `amount_yuan` 已经换算成元，
 * 此处只负责展示格式，不再做 /100。
 *
 * 负号按 `design.md:1109` 只生成一次，数字一律按绝对值格式化 ⇒ `-¥17.50`
 * 而不是 `¥-17.50`。
 */
export function reconMoney(yuan: number | null | undefined): string {
  if (yuan === null || yuan === undefined || !Number.isFinite(yuan)) return "—";
  const sign = yuan < 0 ? "-" : "";
  return `${sign}¥${formatAmount(Math.abs(yuan))}`;
}

/**
 * 金额 + 方向说明。扣款比裸负号好读：用户不必自己判断「负数是不是我亏了」。
 * 用于流水明细行，例如 `-17.5` → 「扣款 ¥17.50」。
 */
export function reconMoneyPhrase(yuan: number | null | undefined): string {
  if (yuan === null || yuan === undefined || !Number.isFinite(yuan))
    return "金额未填";
  const abs = reconMoney(Math.abs(yuan));
  if (yuan < 0) return `扣款 ${abs}`;
  if (yuan > 0) return `入账 ${abs}`;
  return "¥0.00";
}

/**
 * 份额 / 数量。`design.md:1101` 规定金额 2 位；份额后端精度到 4 位，
 * 对账场景下把 1.0001 显示成 1.00 会掩盖真实差异（金融计算正确性优先），
 * 故份额保留最多 4 位并去掉尾零，这是对「2 位」的**登记例外**。
 *
 * `formatAmount` 固定小数位（precision=0 会把 1.0001 舍成 1），不适合份额：
 * 这里用 `maximumFractionDigits: 4` + `minimumFractionDigits: 0`，
 * 既保住精度，也保留千分位；负号交给 Intl 生成一次，差额不再被 abs 抹平。
 */
const QUANTITY_FORMATTER = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 4
});

export function reconQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";
  return `${QUANTITY_FORMATTER.format(value)} 份`;
}

/**
 * 分组主标题。`group.key` 形如 `20|001982` 是后端复合主键，**不展示**；
 * 只用 `symbol`，缺失时给可执行的说明而不是空白或英文 none。
 */
export function reconGroupTitle(
  symbol: string | null | undefined,
  displayName?: string | null
): string {
  const name = displayName?.trim();
  if (name) return name;
  const code = symbol?.trim();
  if (!code) return "标的代码未填";
  return specialSymbolLabel(code) ?? code;
}

/** 原样代码，只用于「代码」这类技术行；展示标题一律走 reconGroupTitle */
export function reconSymbolCode(symbol: string | null | undefined): string {
  return symbol?.trim() || "标的代码未填";
}

/**
 * 抽屉 / 弹窗标题：「产品名 · 代码」。
 * 有名称时两者都给（用户认名字，也能拿代码去券商对账）；
 * 没名称时退到 reconGroupTitle（特殊码给中文，普通码给代码）。
 */
export function reconAssetHeading(
  symbol: string | null | undefined,
  displayName?: string | null
): string {
  const code = symbol?.trim();
  if (!code) return "标的代码未填";
  const name = displayName?.trim();
  if (name) return `${name} · ${code}`;
  return specialSymbolLabel(code)
    ? `${specialSymbolLabel(code)} · ${code}`
    : code;
}

/** 标的副标题：有名称就补名称，没有就退到「标的代码」，不臆造产品名。 */
export function reconGroupSubtitle(
  symbol: string | null | undefined,
  name?: string | null
): string {
  const trimmed = name?.trim();
  if (trimmed) return trimmed;
  return reconGroupTitle(symbol) === "标的代码未填"
    ? "补全标的代码后才能继续"
    : "标的代码";
}

/**
 * 内部记录编号：**降级**为「技术详情」里的定位信息，不作为主视觉标识。
 * `#3029` 单独出现在明细行首会让用户以为这是业务编号。
 */
export function reconRecordRef(id: number | null | undefined): string {
  return id === null || id === undefined ? "—" : `记录编号 ${id}`;
}

/** 目标账本：用名称不用 `#12`。名称缺失时明确说「账本名未填」。 */
export function reconLedgerName(name: string | null | undefined): string {
  const trimmed = name?.trim();
  return trimmed ? trimmed : "账本名未填";
}

/** 账户名缺失时的可读文案 */
export function reconAccountName(name: string | null | undefined): string {
  const trimmed = name?.trim();
  return trimmed ? trimmed : "账户名未填";
}

/** 条数：阿拉伯数字 + 量词（design.md:1091），不加逗号以外的装饰 */
export function reconCount(
  count: number | null | undefined,
  unit = "条"
): string {
  const n = Number.isFinite(count)
    ? Math.max(0, Math.trunc(count as number))
    : 0;
  return `${n} ${unit}`;
}

/**
 * 批次下拉标签：把「2026-06-07 18:33（13 条）」写成「来自 2026-06-07 18:33 的导入 · 13 条」。
 * 前者是数据 dump，后者说明这批数据从哪来。
 */
export function reconBatchLabel(
  label: string | null | undefined,
  count: number | null | undefined
): string {
  const when = label?.trim() ? reconBatchTime(label) : "时间未填";
  return `来自 ${when} 的导入 · ${reconCount(count)}`;
}
