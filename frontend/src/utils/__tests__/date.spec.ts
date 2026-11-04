/**
 * 日期格式化（#2712 的回归网）。
 *
 * 用户报的是「交易日期显示成 `2026-06-03T00:00:00`」：`transactions.trade_date` 是
 * DateTime 列，两个接口各写各的 `.isoformat()`，其中一个把秒级尾巴带上屏幕。
 * 修复分两层——后端 `iso_date_only` + 共享表格再走 `formatDate` 兜一层；
 * 这里钉住「任何 ISO 形式进来都只出日期」。
 */
import { describe, it, expect } from "vitest";
import { formatDate, formatDateTime } from "../date";

describe("formatDate", () => {
  it("DateTime 字符串只保留日期，不把 T 与秒带上屏幕", () => {
    expect(formatDate("2026-06-03T00:00:00")).toBe("2026-06-03");
    expect(formatDate("2026-06-03T14:30:00")).toBe("2026-06-03");
    expect(formatDate("2026-06-03 14:30:00")).toBe("2026-06-03");
  });

  it("纯日期原样返回（不因时区跨日）", () => {
    expect(formatDate("2026-06-03")).toBe("2026-06-03");
  });

  it("空值给占位而不是 null 字面量", () => {
    expect(formatDate("")).toBe("--");
  });
});

describe("formatDateTime（对照：带时刻的字段才保留 HH:mm）", () => {
  it("保留时分、不保留秒", () => {
    expect(formatDateTime("2026-06-03T14:30:59")).toBe("2026-06-03 14:30");
  });
});
