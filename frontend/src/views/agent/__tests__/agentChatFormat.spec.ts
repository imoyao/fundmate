import { describe, expect, it } from "vitest";
import {
  cellClass,
  describeError,
  formatCell,
  isCancelled,
  isScalarRecord,
  roleLabel,
  sanitizeBlocks,
  stripEmoji
} from "../agentChatFormat";
import type { AgentBlock } from "@/api/agent";

describe("stripEmoji", () => {
  it("剔除 emoji 但保留正文", () => {
    expect(stripEmoji("净值 📈 上涨 1.2%")).toBe("净值  上涨 1.2%");
  });

  it("连 ZWJ / 变体选择符这类组合残留一并清掉", () => {
    // 家庭 emoji 由 ZWJ 拼接，只删主体会留下不可见的连接符（这里用转义写死，避免编辑期被规范化）
    expect(
      stripEmoji("组合 \u{1F468}\u200D\u{1F469}\u200D\u{1F467} 结束")
    ).not.toMatch(/\u200D/);
  });

  it("纯文本原样返回（中文 / 数字 / 标点）", () => {
    expect(stripEmoji("持仓成本 15200.00 元，浮亏 8.4%。")).toBe(
      "持仓成本 15200.00 元，浮亏 8.4%。"
    );
  });
});

describe("sanitizeBlocks", () => {
  const blocks: AgentBlock[] = [
    { type: "summary", text: "结论 🎯 一句话" },
    { type: "risk", text: "风险 ⚠️ 提示" },
    {
      type: "table",
      columns: [
        { key: "name", label: "名称", kind: "plain" },
        { key: "pnl", label: "盈亏", kind: "pnl" }
      ],
      rows: [
        { name: "某某混合A 🚀", pnl: 1200 },
        { name: "某某债券C", pnl: -300 }
      ],
      truncated: true
    }
  ];

  it("文本块的 emoji 被剔除", () => {
    const out = sanitizeBlocks(blocks) as Array<{ text?: string }>;
    expect(out[0].text).toBe("结论  一句话");
    expect(out[1].text).toBe("风险  提示");
  });

  it("表格只洗字符串单元格，数值原样保留", () => {
    const table = sanitizeBlocks(blocks)[2];
    expect(table.type).toBe("table");
    if (table.type !== "table") throw new Error("unreachable");
    expect(table.rows[0]).toEqual({ name: "某某混合A ", pnl: 1200 });
    expect(table.rows[1]).toEqual({ name: "某某债券C", pnl: -300 });
  });

  it("不修改入参（纯函数，避免响应式对象被就地改写）", () => {
    const before = JSON.stringify(blocks);
    sanitizeBlocks(blocks);
    expect(JSON.stringify(blocks)).toBe(before);
  });

  it("空数组返回空数组", () => {
    expect(sanitizeBlocks([])).toEqual([]);
  });
});

describe("roleLabel", () => {
  it("用户消息不署名（气泡靠右已足够表达）", () => {
    expect(roleLabel("user")).toBe("");
  });

  it("错误态说人话叫「服务提示」", () => {
    expect(roleLabel("error")).toBe("服务提示");
  });

  it("助手消息署名「账本精灵」", () => {
    expect(roleLabel("assistant")).toBe("账本精灵");
  });
});

describe("isScalarRecord", () => {
  it("扁平标量记录可渲染成指标 chips", () => {
    expect(isScalarRecord({ a: "1", b: 2, c: true, d: null })).toBe(true);
  });

  it("空对象也算（Object.values([]).every → true）", () => {
    expect(isScalarRecord({})).toBe(true);
  });

  it("嵌套对象 / 数组 / null 一律不渲染（避免渲染出 [object Object]）", () => {
    expect(isScalarRecord({ a: { b: 1 } })).toBe(false);
    expect(isScalarRecord({ a: [1, 2] })).toBe(false);
    expect(isScalarRecord(null)).toBe(false);
    expect(isScalarRecord("string")).toBe(false);
  });
});

describe("formatCell", () => {
  it("空值统一 —（null / undefined / 空串三个入口）", () => {
    expect(formatCell(null)).toBe("—");
    expect(formatCell(undefined)).toBe("—");
    expect(formatCell("")).toBe("—");
  });

  it("数值千分位 2 位小数", () => {
    expect(formatCell(1234.5)).toBe("1,234.50");
    expect(formatCell(-300)).toBe("-300.00");
  });

  it("字符串原样，布尔值转字符串", () => {
    expect(formatCell("某某混合A")).toBe("某某混合A");
    expect(formatCell(true)).toBe("true");
  });
});

describe("cellClass", () => {
  it("pnl 列正数染涨红、负数染跌绿", () => {
    expect(cellClass(1, "pnl")).toBe("msg__cell--rise");
    expect(cellClass(-1, "pnl")).toBe("msg__cell--fall");
  });

  it("0 / 非数值不染（汇总行与 0 盈亏不该带方向色）", () => {
    expect(cellClass(0, "pnl")).toBe("");
    expect(cellClass("—", "pnl")).toBe("");
    expect(cellClass("", "pnl")).toBe("");
    expect(cellClass(null, "pnl")).toBe("");
  });

  it("非 pnl 列一律不染", () => {
    expect(cellClass(1200, "plain")).toBe("");
    expect(cellClass(-1200, "plain")).toBe("");
  });

  it("数字字符串按数值判断（后端可能把数值序列化）", () => {
    expect(cellClass("1200", "pnl")).toBe("msg__cell--rise");
    expect(cellClass("-1200.5", "pnl")).toBe("msg__cell--fall");
  });
});

describe("describeError", () => {
  it("超时单独说清楚（不是链路坏了，是模型想久了）", () => {
    expect(describeError({ code: "ECONNABORTED" })).toMatch(/请求超时/);
    expect(describeError({ message: "timeout of 120000ms exceeded" })).toMatch(
      /请求超时/
    );
  });

  it("401 / 403 返回空串（全局拦截器已统一提示，不再进气泡）", () => {
    expect(describeError({ response: { status: 401 } })).toBe("");
    expect(describeError({ response: { status: 403 } })).toBe("");
  });

  it("429 优先用后端文案，缺失时给默认文案", () => {
    expect(
      describeError({
        response: { status: 429, data: { message: "已超出分析轮次" } }
      })
    ).toBe("已超出分析轮次");
    expect(describeError({ response: { status: 429 } })).toMatch(/过于频繁/);
  });

  it("503 走「服务繁忙」默认文案，也认后端文案", () => {
    expect(describeError({ response: { status: 503 } })).toMatch(/繁忙/);
    expect(
      describeError({
        response: { status: 503, data: { message: "上游限流" } }
      })
    ).toBe("上游限流");
  });

  it("其余一律「请求失败」兜底", () => {
    expect(describeError({ response: { status: 500 } })).toBe(
      "请求失败，请稍后重试。"
    );
    expect(describeError(new Error("boom"))).toBe("请求失败，请稍后重试。");
    expect(describeError(undefined)).toBe("请求失败，请稍后重试。");
  });
});

describe("isCancelled", () => {
  it("axios 的 ERR_CANCELED 与 CanceledError 文案都识别", () => {
    expect(isCancelled({ code: "ERR_CANCELED" })).toBe(true);
    expect(isCancelled({ message: "canceled" })).toBe(true);
  });

  it("普通错误不算取消（不能被误吞成「静默结束」）", () => {
    expect(isCancelled({ message: "Network Error" })).toBe(false);
    expect(isCancelled(undefined)).toBe(false);
  });
});
