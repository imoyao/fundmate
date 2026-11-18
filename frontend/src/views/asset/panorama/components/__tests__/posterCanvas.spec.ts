import { describe, expect, it, vi } from "vitest";

import { drawPoster, renderPoster } from "../posterCanvas";
import { buildPosterData } from "../posterModel";

/**
 * Canvas 绘制层的判据（#1016）。
 *
 * 用假 context 断言「绘制调用了什么」而非像素：
 * - 空数据/脏数据不抛（对应验收「弱网下不崩」，网络失败时数据为空）；
 * - 盈亏按涨红跌绿着色（语义色不能错）；
 * - 无 2D context 时 renderPoster 抛可读错误，不静默产出空白图。
 */

type Calls = { method: string; args: unknown[] }[];

type TextCall = { text: unknown; fillStyle: string };

function fakeContext(): {
  ctx: CanvasRenderingContext2D;
  calls: Calls;
  texts: TextCall[];
} {
  const calls: Calls = [];
  const texts: TextCall[] = [];
  const record =
    (method: string) =>
    (...args: unknown[]) => {
      calls.push({ method, args });
    };
  const ctx = {
    save: record("save"),
    restore: record("restore"),
    fillRect: record("fillRect"),
    beginPath: record("beginPath"),
    moveTo: record("moveTo"),
    lineTo: record("lineTo"),
    quadraticCurveTo: record("quadraticCurveTo"),
    closePath: record("closePath"),
    fill: record("fill"),
    // fillText 必须在调用「当时」抓取 fillStyle；事后读 ctx.fillStyle 已被
    // 后续绘制改成页脚色，拿不到当次语义色（这是 mock 缺陷，不是实现缺陷）。
    fillText: (text: unknown) => {
      calls.push({ method: "fillText", args: [text] });
      texts.push({ text, fillStyle: String(ctx.fillStyle) });
    },
    scale: record("scale"),
    textBaseline: "",
    font: "",
    fillStyle: ""
  } as unknown as CanvasRenderingContext2D;
  return { ctx, calls, texts };
}

const base = {
  date: "2026-11-18",
  totalAssets: 1_000_000,
  totalLiabilities: 200_000,
  netAssets: 800_000,
  totalPnl: -12_345.67,
  colors: ["#e34f38"]
};

describe("drawPoster", () => {
  it("正常数据：画出标题、金额与页脚，不抛异常", () => {
    const { ctx, calls } = fakeContext();
    const data = buildPosterData({
      ...base,
      categories: [
        { name: "基金", value: 600_000 },
        { name: "股票", value: 400_000 }
      ]
    });
    expect(() => drawPoster(ctx, data)).not.toThrow();
    const texts = calls
      .filter(c => c.method === "fillText")
      .map(c => c.args[0]);
    expect(texts).toContain("我的资产全景");
    expect(texts).toContain("¥1,000,000.00");
    expect(texts.some(t => String(t).includes("多多贝"))).toBe(true);
  });

  it("空数据（弱网/空账户）：走占位文案，不抛、不印 NaN", () => {
    const { ctx, calls } = fakeContext();
    const data = buildPosterData({
      ...base,
      totalAssets: 0,
      totalLiabilities: 0,
      netAssets: 0,
      totalPnl: 0,
      categories: []
    });
    expect(() => drawPoster(ctx, data)).not.toThrow();
    const texts = calls
      .filter(c => c.method === "fillText")
      .map(c => String(c.args[0]));
    expect(texts).toContain("暂无资产数据，录入后即可生成分布");
    expect(texts.some(t => t.includes("NaN") || t.includes("Infinity"))).toBe(
      false
    );
  });

  it("盈亏语义色：亏损为绿、盈利为红（A 股涨红跌绿）", () => {
    const loss = fakeContext();
    drawPoster(
      loss.ctx,
      buildPosterData({ ...base, totalPnl: -100, categories: [] })
    );
    expect(loss.texts.find(t => t.text === "-¥100.00")?.fillStyle).toBe(
      "#2e9e6b"
    );

    const gain = fakeContext();
    drawPoster(
      gain.ctx,
      buildPosterData({ ...base, totalPnl: 100, categories: [] })
    );
    expect(gain.texts.find(t => t.text === "¥100.00")?.fillStyle).toBe(
      "#e34f38"
    );
  });

  it("save/restore 成对，不污染调用方的 canvas 状态", () => {
    const { ctx, calls } = fakeContext();
    drawPoster(ctx, buildPosterData({ ...base, categories: [] }));
    const saves = calls.filter(c => c.method === "save").length;
    const restores = calls.filter(c => c.method === "restore").length;
    expect(saves).toBe(1);
    expect(restores).toBe(1);
  });
});

describe("renderPoster", () => {
  it("无 2D context：抛可读错误，不静默产出空白图", () => {
    const canvas = {
      width: 0,
      height: 0,
      getContext: vi.fn(() => null)
    } as unknown as HTMLCanvasElement;
    const data = buildPosterData({ ...base, categories: [] });
    expect(() => renderPoster(canvas, data)).toThrow(/Canvas 2D/);
  });

  it("正常：设置画布尺寸并返回 dataURL", () => {
    const ctxCalls: string[] = [];
    const ctx = {
      scale: () => ctxCalls.push("scale"),
      save: () => {},
      restore: () => {},
      fillRect: () => {},
      beginPath: () => {},
      moveTo: () => {},
      lineTo: () => {},
      quadraticCurveTo: () => {},
      closePath: () => {},
      fill: () => {},
      fillText: () => {},
      textBaseline: "",
      font: "",
      fillStyle: ""
    } as unknown as CanvasRenderingContext2D;
    const canvas = {
      width: 0,
      height: 0,
      getContext: vi.fn(() => ctx),
      toDataURL: vi.fn(() => "data:image/png;base64,AAAA")
    } as unknown as HTMLCanvasElement;
    const data = buildPosterData({ ...base, categories: [] });
    expect(renderPoster(canvas, data)).toBe("data:image/png;base64,AAAA");
    expect(canvas.width).toBeGreaterThan(0);
    expect(canvas.height).toBeGreaterThan(0);
    expect(ctxCalls).toContain("scale");
  });
});
