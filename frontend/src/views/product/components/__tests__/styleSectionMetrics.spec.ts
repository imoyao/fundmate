/**
 * 「投资风格」展示口径测试（#2478 · 详情页「投资风格」区块）。
 *
 * 重点钉住几个**静默错误**：
 * - 8 分类顺序被改 / 缺项被补 0（「缺失」与「0 暴露」是两件事，null 必须保留）；
 * - dominant_changed 被前端重算或下结论（后端算好的只透出）；
 * - null 暴露被渲染成 0% 而非「—」；
 * - 历史折线空数据仍生成 option（应返回 null 隐藏图表）。
 */
import { describe, it, expect } from "vitest";
import type { FundStyleBox, FundStyleHistory } from "@/api/funds";
import {
  STYLE_DISPLAY_ORDER,
  formatStyleValue,
  styleColorVar,
  hasStyleData,
  orderedStyles,
  styleDrift,
  driftText,
  buildStyleHistoryOption
} from "../styleSectionMetrics";

describe("STYLE_DISPLAY_ORDER", () => {
  it("固定 8 分类且顺序正确（晨星式 大/中/小盘 × 成长/价值 + 港股/固收）", () => {
    expect(STYLE_DISPLAY_ORDER).toEqual([
      "大盘成长",
      "大盘价值",
      "中盘成长",
      "中盘价值",
      "小盘成长",
      "小盘价值",
      "港股风格",
      "固收风格"
    ]);
  });
});

describe("formatStyleValue", () => {
  it("保留一位小数百分比", () => {
    expect(formatStyleValue(12.34)).toBe("12.3%");
    expect(formatStyleValue(0)).toBe("0.0%");
  });
  it("null / undefined 渲染「—」而非 0", () => {
    expect(formatStyleValue(null)).toBe("—");
    expect(formatStyleValue(undefined)).toBe("—");
  });
});

describe("styleColorVar", () => {
  it("映射 --chart-01..08 且循环兜底", () => {
    expect(styleColorVar(0)).toBe("--chart-01");
    expect(styleColorVar(7)).toBe("--chart-08");
    expect(styleColorVar(8)).toBe("--chart-01");
  });
});

describe("hasStyleData", () => {
  it("null box 无数据", () => {
    expect(hasStyleData(null)).toBe(false);
  });
  it("全 null 视为无数据（不把缺失当 0）", () => {
    const box: FundStyleBox = {
      fund_code: "000001",
      stat_date: "2026-10-01",
      styles: STYLE_DISPLAY_ORDER.map(name => ({
        style_name: name,
        value: null
      })),
      dominant_style: null,
      style_period: "2026-10-01",
      prev_dominant_style: null,
      prev_period: null,
      dominant_changed: false,
      source: "jiucaishuo_style"
    };
    expect(hasStyleData(box)).toBe(false);
  });
  it("至少一个非 null 即有数据", () => {
    const box: FundStyleBox = {
      fund_code: "000001",
      stat_date: "2026-10-01",
      styles: [{ style_name: "大盘价值", value: 30 }],
      dominant_style: "大盘价值",
      style_period: "2026-10-01",
      prev_dominant_style: null,
      prev_period: null,
      dominant_changed: false,
      source: "jiucaishuo_style"
    };
    expect(hasStyleData(box)).toBe(true);
  });
});

describe("orderedStyles", () => {
  it("按固定序整形，缺项补 value=null（不补 0）并带上色与 index", () => {
    const box: FundStyleBox = {
      fund_code: "000001",
      stat_date: "2026-10-01",
      // 故意只给两个风格，且乱序
      styles: [
        { style_name: "小盘成长", value: 12 },
        { style_name: "大盘成长", value: 40 }
      ],
      dominant_style: "大盘成长",
      style_period: "2026-10-01",
      prev_dominant_style: null,
      prev_period: null,
      dominant_changed: false,
      source: "jiucaishuo_style"
    };
    const rows = orderedStyles(box);
    expect(rows.map(r => r.style_name)).toEqual([...STYLE_DISPLAY_ORDER]);
    // 大盘成长在第一位、值 40
    expect(rows[0]).toMatchObject({ style_name: "大盘成长", value: 40 });
    // 小盘成长本来乱序，现在归位到第 5 位
    expect(rows[4]).toMatchObject({ style_name: "小盘成长", value: 12 });
    // 缺项补 null，而不是 0
    expect(rows[1].value).toBeNull();
    expect(rows[7].colorVar).toBe("--chart-08");
  });
});

describe("styleDrift / driftText", () => {
  const base = (over: Partial<FundStyleBox>): FundStyleBox => ({
    fund_code: "000001",
    stat_date: "2026-10-01",
    styles: [{ style_name: "大盘价值", value: 30 }],
    dominant_style: "大盘价值",
    style_period: "2026-10-01",
    prev_dominant_style: null,
    prev_period: null,
    dominant_changed: false,
    source: "jiucaishuo_style",
    ...over
  });

  it("切换：由上一主导切换为当前主导", () => {
    const box = base({
      dominant_style: "大盘成长",
      prev_dominant_style: "大盘价值",
      dominant_changed: true,
      prev_period: "2026-09-01"
    });
    const d = styleDrift(box);
    expect(d.changed).toBe(true);
    expect(d.current).toBe("大盘成长");
    expect(d.previous).toBe("大盘价值");
    expect(driftText(d)).toContain("由「大盘价值」切换为「大盘成长」");
  });

  it("未切换：维持提示含上一时点", () => {
    const box = base({
      dominant_style: "大盘价值",
      prev_dominant_style: "大盘价值",
      dominant_changed: false,
      prev_period: "2026-09-01"
    });
    const d = styleDrift(box);
    expect(d.changed).toBe(false);
    expect(driftText(d)).toContain("维持「大盘价值」");
    expect(driftText(d)).toContain("2026-09-01");
  });

  it("透出后端结论，不自行重算主导（prev 缺失时不编造）", () => {
    const box = base({ prev_dominant_style: null, dominant_changed: true });
    const d = styleDrift(box);
    expect(d.current).toBe("大盘价值");
    expect(d.previous).toBeNull();
    expect(driftText(d)).toBe("当前主导风格为「大盘价值」");
  });
});

describe("buildStyleHistoryOption", () => {
  it("无数据 / 空点返回 null（组件据此隐藏图表）", () => {
    expect(buildStyleHistoryOption(null, () => "#000")).toBeNull();
    expect(
      buildStyleHistoryOption(
        { fund_code: "x", points: [], count: 0 },
        () => "#000"
      )
    ).toBeNull();
  });

  it("生成 8 条系列、时间轴升序、颜色走注入的解析色", () => {
    const history: FundStyleHistory = {
      fund_code: "000001",
      count: 2,
      points: [
        { stat_date: "2026-10-01", styles: { 大盘成长: 40, 大盘价值: 30 } },
        { stat_date: "2026-09-01", styles: { 大盘成长: 35, 大盘价值: 28 } }
      ]
    };
    const colorOf = (i: number) => `#color${i}`;
    const opt = buildStyleHistoryOption(history, colorOf) as any;
    expect(opt.series).toHaveLength(STYLE_DISPLAY_ORDER.length);
    // yAxis 取值 0-100
    expect(opt.yAxis.max).toBe(100);
    // 时间轴升序（倒序输入被纠正）
    expect(opt.xAxis.data).toEqual(["2026-09-01", "2026-10-01"]);
    // 颜色由 colorOf 注入（非 CSS 变量字符串）
    expect(opt.series[0].lineStyle.color).toBe("#color0");
    // 缺失风格补 null（不补 0）
    expect(opt.series[2].data).toEqual([null, null]);
  });
});
