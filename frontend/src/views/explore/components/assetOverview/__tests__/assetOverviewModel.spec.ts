/**
 * 大类资产观察展示口径测试（#980 拆分时补）。
 *
 * 这些函数都是纯函数，但错起来是**静默的**：
 * - 分位标签三档里漏一档 → 游标颜色与文字色不一致，只在特定行情下暴露；
 * - 分类未命中时返回空串 → 色点变成透明，看起来像「这个分类没有颜色」；
 * - 未取数时把计数算成 0 → 折叠态会显示「0 个标的」，等于编造。
 */
import { describe, it, expect } from "vitest";
import type { MarketAnomaly, MarketAsset, MarketGroup } from "@/api/market";
import {
  categoryColor,
  collapsedCountText,
  flattenAnomalies,
  groupCountOf,
  loadedAssetCountOf,
  positionColor,
  positionLabelColor,
  yieldTone
} from "../assetOverviewModel";

function makeAsset(over: Partial<MarketAsset> = {}): MarketAsset {
  return {
    key: "000300",
    name: "沪深300",
    category: "A股",
    available: true,
    change_pct: 0.62,
    trade_date: "2026-10-23",
    data_asof: "2026-10-23 15:00",
    position: null,
    anomaly: null,
    caliber: null,
    reason: null,
    ...over
  };
}

function makeAnomaly(over: Partial<MarketAnomaly> = {}): MarketAnomaly {
  return {
    triggered: true,
    rule: "sigma",
    today_pct: 2.31,
    sigma: 0.8,
    multiple: 2.9,
    sigma_window: 20,
    basis_note: "单日涨幅达近 20 日波动 2.9 倍",
    ...over
  } as MarketAnomaly;
}

describe("categoryColor", () => {
  it("已知分类取对应令牌", () => {
    expect(categoryColor("A股")).toBe("var(--asset-cat-stock)");
    expect(categoryColor("债券")).toBe("var(--asset-cat-bond)");
    expect(categoryColor("汇率")).toBe("var(--asset-cat-saving)");
  });

  it("未知分类退到次级文字色，而不是透明 / 空串", () => {
    expect(categoryColor("加密货币")).toBe("var(--text-secondary)");
    expect(categoryColor("")).toBe("var(--text-secondary)");
  });
});

describe("positionColor / positionLabelColor", () => {
  const withLabel = (label: string) =>
    makeAsset({
      position: { percentile: 30, label, basis: "近5年分位", window: 5 }
    });

  it("偏低走低档色、偏高走高当色、其余走中档", () => {
    expect(positionColor(withLabel("偏低"))).toBe("var(--temp-low)");
    expect(positionColor(withLabel("偏高"))).toBe("var(--temp-high)");
    expect(positionColor(withLabel("适中"))).toBe("var(--temp-mid)");
  });

  it("无 position 时按中档处理（不是报错也不是空色）", () => {
    expect(positionColor(makeAsset())).toBe("var(--temp-mid)");
    expect(positionLabelColor(makeAsset())).toBe("var(--temp-mid-ink)");
  });

  it("标签文字必须用 -ink 一族（实色作文字对比度不足，见 #1545）", () => {
    expect(positionLabelColor(withLabel("偏低"))).toBe("var(--temp-low-ink)");
    expect(positionLabelColor(withLabel("偏高"))).toBe("var(--temp-high-ink)");
    expect(positionLabelColor(withLabel("适中"))).toBe("var(--temp-mid-ink)");
  });

  it("颜色族与文字族不混用", () => {
    for (const label of ["偏低", "适中", "偏高"]) {
      expect(positionLabelColor(withLabel(label))).not.toBe(
        positionColor(withLabel(label))
      );
      expect(positionLabelColor(withLabel(label))).toMatch(/-ink\)$/);
    }
  });
});

describe("yieldTone", () => {
  it("收益率变动恒为中性色，不套涨红跌绿（§3.4 纪律）", () => {
    expect(yieldTone(12.5)).toBe("var(--text-secondary)");
    expect(yieldTone(-12.5)).toBe("var(--text-secondary)");
    expect(yieldTone(undefined)).toBe("var(--text-secondary)");
  });
});

describe("flattenAnomalies", () => {
  it("只留命中项，保持 groups / assets 的原始顺序", () => {
    const groups: MarketGroup[] = [
      {
        category: "A股",
        assets: [
          makeAsset({ key: "a", anomaly: makeAnomaly({ today_pct: 1 }) }),
          makeAsset({ key: "b" })
        ]
      },
      {
        category: "商品",
        assets: [
          makeAsset({ key: "c", anomaly: makeAnomaly({ today_pct: 3 }) })
        ]
      }
    ];
    expect(flattenAnomalies(groups).map(x => x.asset.key)).toEqual(["a", "c"]);
  });

  it("全无命中时返回空数组（面板靠 length 决定不渲染）", () => {
    expect(
      flattenAnomalies([{ category: "A股", assets: [makeAsset()] }])
    ).toEqual([]);
  });

  it("空 groups 不抛错", () => {
    expect(flattenAnomalies([])).toEqual([]);
  });
});

describe("groupCountOf", () => {
  const groups: MarketGroup[] = [
    { category: "A股", assets: [makeAsset(), makeAsset()] },
    { category: "债券", assets: [makeAsset()] }
  ];

  it("命中的分类返回标的数", () => {
    expect(groupCountOf(groups, "A股")).toBe(2);
    expect(groupCountOf(groups, "债券")).toBe(1);
  });

  it("未取数（空数组）时返回 null，不返回 0", () => {
    expect(groupCountOf([], "A股")).toBeNull();
  });

  it("分类不存在时也返回 null（数据缺组 ≠ 该组 0 个标的）", () => {
    expect(groupCountOf(groups, "汇率")).toBeNull();
  });
});

describe("loadedAssetCountOf", () => {
  it("已取数时返回实际总数", () => {
    expect(
      loadedAssetCountOf([
        { category: "A股", assets: [makeAsset(), makeAsset()] },
        { category: "债券", assets: [makeAsset()] }
      ])
    ).toBe(3);
  });

  it("未取数时回退到标称的 20 个（仅用于按钮文案）", () => {
    expect(loadedAssetCountOf([])).toBe(20);
  });
});

describe("collapsedCountText", () => {
  it("有数据给「N 个标的」", () => {
    expect(
      collapsedCountText(
        [{ category: "A股", assets: [makeAsset(), makeAsset()] }],
        "A股"
      )
    ).toBe("2 个标的");
  });

  it("未取数返回 null（父层据此不渲染那段 span）", () => {
    expect(collapsedCountText([], "A股")).toBeNull();
  });

  it("分类缺组同样返回 null", () => {
    expect(
      collapsedCountText([{ category: "A股", assets: [makeAsset()] }], "汇率")
    ).toBeNull();
  });
});
