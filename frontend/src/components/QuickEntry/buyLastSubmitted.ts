// 买入表单「重记一笔」会话快照（#2305）——#980 拆分时从 BuyForm.vue 原样搬出。
// 仅 sessionStorage（刷新即清空），不落盘；预填产品 + 账户，金额/日期/份额留空。
// 本模块只认纯数据：读 / 写 / 比对 / 预填映射。**刻意不依赖 element-plus**
// ——「是否重复记录」的确认弹窗属于提交编排，放在 useBuySubmit 里。
const LAST_SUBMITTED_KEY = "fm:buy:last_submitted";

export interface BuyLastSubmitted {
  ledger_id: number | null;
  symbol: string;
  name: string;
  market: string;
  type: string;
  trade_date: string;
  buyAmount: number | undefined;
  shares: number | undefined;
  fee: number | undefined;
}

/** 要从表单里落进快照的字段（快照只关心「同一笔」的判据） */
export interface BuySnapshotSource {
  ledger_id: number | null;
  symbol: string;
  name: string;
  market: string;
  type: string;
  trade_date: string;
  buyAmount: number | undefined;
  shares: number | undefined;
  fee: number | undefined;
}

export function buildBuySnapshot(form: BuySnapshotSource): BuyLastSubmitted {
  return {
    ledger_id: form.ledger_id,
    symbol: form.symbol,
    name: form.name,
    market: form.market,
    type: form.type,
    trade_date: form.trade_date,
    buyAmount: form.buyAmount,
    shares: form.shares,
    fee: form.fee
  };
}

export function loadBuyLastSubmitted(): BuyLastSubmitted | null {
  try {
    const raw = sessionStorage.getItem(LAST_SUBMITTED_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as BuyLastSubmitted;
    if (!parsed || typeof parsed !== "object") return null;
    if (parsed.ledger_id == null && !parsed.symbol) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveBuyLastSubmitted(snapshot: BuyLastSubmitted): void {
  try {
    sessionStorage.setItem(LAST_SUBMITTED_KEY, JSON.stringify(snapshot));
  } catch {
    /* 存储满 / 私有模式：静默忽略，不影响主流程 */
  }
}

/**
 * 防呆：与上次提交完全一致时须二次确认，避免同一笔记两遍。
 * 只比这 6 个字段 —— 备注/配置目标改了不算「同一笔」。
 */
export function isSameAsLastSubmitted(
  last: BuyLastSubmitted,
  current: BuyLastSubmitted
): boolean {
  return (
    last.ledger_id === current.ledger_id &&
    last.symbol === current.symbol &&
    last.trade_date === current.trade_date &&
    last.buyAmount === current.buyAmount &&
    last.shares === current.shares &&
    last.fee === current.fee
  );
}

/** 快照 → 表单可回填的字段（日期/金额/份额/手续费故意不回填，避免误提交上次金额） */
export function snapshotToFormPatch(snapshot: BuyLastSubmitted) {
  return {
    ledger_id: snapshot.ledger_id,
    symbol: snapshot.symbol,
    name: snapshot.name,
    market: snapshot.market,
    type: snapshot.type
  };
}

/** 快照 → 搜索框回显项（下拉里没有这项也不会崩，value-key 按 symbol 匹配） */
export function snapshotToSecurityOption(snapshot: BuyLastSubmitted) {
  return {
    symbol: snapshot.symbol,
    name: snapshot.name,
    market: snapshot.market,
    type: snapshot.type,
    type_label: snapshot.type === "fund" ? "基金" : "股票"
  };
}
