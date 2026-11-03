import { describe, expect, it } from "vitest";
import type { SectorFundFlow } from "@/utils/realtimeDataSources";
import {
  buildThemeLine,
  formatChangePct,
  formatFlow,
  splitSectorFlow,
  trendClassOf
} from "@/views/asset/watchlist/composables/fundFlowModel";

function sector(name: string, inflowYi: number): SectorFundFlow {
  return {
    code: `BK${name}`,
    name,
    mainInflow: inflowYi * 1e8,
    changePct: 0
  };
}

/** 故意打乱顺序：splitSectorFlow 不依赖入参有序 */
const SECTORS: SectorFundFlow[] = [
  sector("银行", -9.2),
  sector("半导体", 12.3),
  sector("保险", -4.1),
  sector("电池", 8.1),
  sector("白酒", -6.7),
  sector("光伏设备", 5.4)
];

describe("splitSectorFlow", () => {
  it("两端同时取：流入按降序、流出按最负在前", () => {
    const board = splitSectorFlow(SECTORS, 3);
    expect(board.inflow.map(s => s.name)).toEqual([
      "半导体",
      "电池",
      "光伏设备"
    ]);
    expect(board.outflow.map(s => s.name)).toEqual(["银行", "白酒", "保险"]);
  });

  it("每侧数量受 topN 限制", () => {
    const board = splitSectorFlow(SECTORS, 1);
    expect(board.inflow).toHaveLength(1);
    expect(board.outflow).toHaveLength(1);
    expect(board.outflow[0].name).toBe("银行");
  });

  it("没有负值时流出端为空（不再从流入榜里凑负值充数）", () => {
    const board = splitSectorFlow([sector("半导体", 12.3)], 3);
    expect(board.outflow).toEqual([]);
    expect(board.inflow).toHaveLength(1);
  });

  it("不修改入参数组", () => {
    const input = [...SECTORS];
    splitSectorFlow(input, 3);
    expect(input.map(s => s.name)).toEqual(SECTORS.map(s => s.name));
  });
});

describe("buildThemeLine", () => {
  it("两端都有时同时点名（流入前 3 + 流出前 2）", () => {
    const line = buildThemeLine(splitSectorFlow(SECTORS, 4));
    expect(line).toBe(
      "今日资金主线：半导体、电池、光伏设备 获主力净流入居前；银行、白酒 主力净流出居前。"
    );
  });

  it("只有流入时不出现「流出」半句", () => {
    expect(buildThemeLine(splitSectorFlow([sector("半导体", 12.3)], 3))).toBe(
      "今日资金主线：半导体 获主力净流入居前。"
    );
  });

  it("无数据返回空串", () => {
    expect(buildThemeLine({ inflow: [], outflow: [] })).toBe("");
  });
});

describe("格式化与着色", () => {
  it("净流入按亿/万自适应并保留符号", () => {
    expect(formatFlow(1234000000)).toBe("+12.34亿");
    expect(formatFlow(-92000000)).toBe("-9200万");
    expect(formatFlow(0)).toBe("0");
  });

  it("板块涨跌幅不再被多除 100（f3 已是百分数）", () => {
    expect(formatChangePct(0.31)).toBe("+0.31%");
    expect(formatChangePct(-3.99)).toBe("-3.99%");
  });

  it("语义色按资金方向", () => {
    expect(trendClassOf(1)).toBe("is-rise");
    expect(trendClassOf(-1)).toBe("is-fall");
    expect(trendClassOf(0)).toBe("is-flat");
  });
});
