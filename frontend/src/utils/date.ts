// src/utils/date.ts
// 全站日期时间格式化唯一入口（规范见 frontend/design.md「日期时间格式规范」）
// 纯日期 YYYY-MM-DD；日期+时间 YYYY-MM-DD HH:mm（不带秒）；仅时间 HH:mm

/** 解析输入为 Date；无效返回 null。字符串优先识别 YYYY-MM-DD 前缀（本地时区语义，避免 UTC 跨日 off-by-one） */
function toDate(value: string | number | Date): Date | null {
  if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
  if (typeof value === "number") {
    const d = new Date(value);
    return isNaN(d.getTime()) ? null : d;
  }
  const datePart = value.slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(datePart)) {
    // 纯日期字符串 new Date("2026-08-14") 按 UTC 解析会跨日，需本地化
    const [y, m, day] = datePart.split("-").map(Number);
    return new Date(y, m - 1, day);
  }
  const d = new Date(value);
  return isNaN(d.getTime()) ? null : d;
}

/** 纯日期：YYYY-MM-DD。空值/无效返回 "--" */
export function formatDate(value: string | number | Date): string {
  if (!value) return "--";
  if (typeof value === "string") {
    const datePart = value.slice(0, 10);
    if (/^\d{4}-\d{2}-\d{2}$/.test(datePart)) return datePart;
  }
  const d = toDate(value);
  if (!d) return "--";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** 日期+时间：YYYY-MM-DD HH:mm（不带秒）。空值/无效返回 "--"；纯日期输入原样返回不臆造时间 */
export function formatDateTime(value: string | number | Date): string {
  if (!value) return "--";
  if (typeof value === "string") {
    const m = value.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})/);
    if (m) return `${m[1]} ${m[2]}:${m[3]}`;
    if (/^\d{4}-\d{2}-\d{2}$/.test(value.slice(0, 10)))
      return value.slice(0, 10);
  }
  const d = toDate(value);
  if (!d) return "--";
  const date = formatDate(d);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${date} ${hh}:${mm}`;
}

/** 仅时间：HH:mm。空值/无效返回 "--" */
export function formatTime(value: string | number | Date): string {
  if (!value) return "--";
  if (typeof value === "string") {
    const m = value.match(/(\d{2}):(\d{2})/);
    if (m) return `${m[1]}:${m[2]}`;
  }
  const d = toDate(value);
  if (!d) return "--";
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}
