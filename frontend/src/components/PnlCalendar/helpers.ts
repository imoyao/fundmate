/**
 * PnlCalendar 的日期小工具（#1925 拆 `PnlCalendarGrid` 时抽出）。
 *
 * 日 / 月 / 年三粒度都要构造请求区间与格子日期，日期格式必须**只有一份实现**——
 * 两处各写一份 `padStart` 迟早漏掉补零，而后端只认 `YYYY-MM-DD`。
 */

/** 取该月首日（存 1 号，避免时区漂移） */
export function firstOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

/** `YYYY-MM-DD`（本地时区，月 / 日补零） */
export function ymd(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}
