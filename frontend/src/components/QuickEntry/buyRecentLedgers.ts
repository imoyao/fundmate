// 买入表单「最近使用账户置顶」（#2305）——#980 拆分时从 BuyForm.vue 原样搬出。
// localStorage 记录最近使用的 ledger_id，账户下拉按此排序置顶。
const RECENT_LEDGER_KEY = "fm:buy:recent_ledgers";
/** 只保留最近 20 个，避免 localStorage 无限增长 */
const RECENT_LEDGER_LIMIT = 20;

export function loadRecentLedgerIds(): number[] {
  try {
    const raw = localStorage.getItem(RECENT_LEDGER_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((id: unknown) => typeof id === "number");
  } catch {
    return [];
  }
}

function persistRecentLedgerIds(ids: number[]): void {
  try {
    localStorage.setItem(RECENT_LEDGER_KEY, JSON.stringify(ids));
  } catch {
    /* 存储满 / 私有模式：静默忽略 */
  }
}

/** 提交成功后把该账户提到最近列表首位 */
export function bumpRecentLedger(ledgerId: number): void {
  if (!ledgerId) return;
  const ids = loadRecentLedgerIds();
  const filtered = ids.filter(id => id !== ledgerId);
  filtered.unshift(ledgerId);
  persistRecentLedgerIds(filtered.slice(0, RECENT_LEDGER_LIMIT));
}

/**
 * 按最近使用顺序置顶，其余保持原序。
 * 注意：最近列表由调用方在 setup 时读一次（非响应式）——历史行为如此，改动会
 * 让提交后的排序在同一个挂载周期里突然跳变，故保持。
 */
export function sortByRecentUsage<T extends { id: number }>(
  items: T[],
  recentIds: number[]
): T[] {
  if (recentIds.length === 0) return items;
  const recentSet = new Set(recentIds);
  const recent: T[] = [];
  const rest: T[] = [];
  for (const item of items) {
    if (recentSet.has(item.id)) recent.push(item);
    else rest.push(item);
  }
  // 按最近列表顺序排列
  recent.sort((a, b) => recentIds.indexOf(a.id) - recentIds.indexOf(b.id));
  return [...recent, ...rest];
}
