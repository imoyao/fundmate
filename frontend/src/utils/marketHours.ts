/**
 * 实时行情「取数闸门」的纯判定（#2338）。
 *
 * WHY
 *   休市日 / 盘后仍在周期性打天天基金估值接口（用户 2026-10-18 反馈）。修复把闸门
 *   收敛到 `useRealtimeQuotes.canFetch()` 一处，但判定本身此前是内联的一串 `if`：
 *   既无法单测（vitest 是 node 环境，测不了依赖 http/localStorage 的 composable），
 *   也容易被后来者再抄一遍走样——#2338 的根因正是四条路径各写各的判断。
 *   故把判定抽成纯函数，时钟与日历都由调用方注入：
 *   - `isWithinTradingWindow`：只看时钟；
 *   - `shouldFetchRealtimeQuotes`：时钟 + 交易日。
 *
 * 口径（与后端 `app.core.trading_calendar.is_trading_day` 配套）
 *   - **交易日由后端判定**（法定节假日、调休补班周末——后者打工人上班但交易所休市）。
 *     本模块只接收布尔结果，绝不自己算日历，避免前端再长一份节假日表。
 *   - 交易日历接口不可达时，调用方须把 `isTradingDay` 传 `false`（**保守停抓**）。
 *     宁可盘中少一轮估值，也不要把休市日误判成交易日而空跑——这正是 #2338 的 failure mode。
 *   - 时段按**本地时区** 9:30–15:00，端点闭合（`9:30` 可、`15:01` 不可）。
 *
 * ⚠️ 刻意保留既有口径：**含午休 11:30–13:00**。A 股午休期间行情不跳动，继续轮询
 * 取的仍是午间快照，本轮只解决「休市日空跑」，不动盘中行为（验收第 2 条要求盘中不变）。
 * 若要停午休轮询，那是独立议题，另开卡。
 */

/** 开盘：09:30（自 00:00 起的分钟数） */
export const TRADING_WINDOW_START_MINUTE = 9 * 60 + 30;

/** 收盘：15:00。该分钟本身仍在窗口内，15:01 起不在 */
export const TRADING_WINDOW_END_MINUTE = 15 * 60;

/**
 * 时钟是否落在 A 股交易时段内（9:30–15:00，本地时区，端点闭合）。
 *
 * 只判时钟、不判日历：调用方通常已先拿到交易日结果，分开便于各自单测。
 */
export function isWithinTradingWindow(now: Date): boolean {
  const minutes = now.getHours() * 60 + now.getMinutes();
  return (
    minutes >= TRADING_WINDOW_START_MINUTE &&
    minutes <= TRADING_WINDOW_END_MINUTE
  );
}

/**
 * 是否应当发起实时行情取数（#2338 A 判据的唯一判据）。
 *
 * 所有取数入口（`start()` / `manualRefresh()` / 轮询 tick）都必须过这一关，
 * 不得再各写一段 `getDay()` / `getHours()` 判断——那是 #2338 四条绕过路径的成因。
 */
export function shouldFetchRealtimeQuotes(params: {
  now: Date;
  isTradingDay: boolean;
}): boolean {
  return params.isTradingDay && isWithinTradingWindow(params.now);
}
