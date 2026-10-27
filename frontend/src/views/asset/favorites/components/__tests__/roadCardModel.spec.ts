/**
 * 未竟之蹊单卡的字段解析（#980 批 B6 拆出 `roadCardModel.ts` 时补的网）。
 *
 * 这些函数原先是一串 computed，兜底值散在模板与脚本两处。最值得钉的是三件事：
 * 1. **未知值不显示空**：实体未登记要显示「资产」、状态未登记要显示「观察中」，
 *    否则卡片上会出现一个空胶囊；但 `venue` 相反——未登记要**原样显示**（后端
 *    可能先上新市场），空值才省掉这一段。两个方向的兜底混起来就出 bug。
 * 2. **`manager` 不显示 asset_type**：它是域特有实体、不是通用 asset_type，
 *    显示英文原键对用户无意义。
 * 3. **7 天边界**：复盘提醒的「临近」判据是 `<= 7`，含逾期（负数）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WatchlistTag } from "@/api/watchlist";
import {
  DEFAULT_ENTITY_COLOR,
  DEFAULT_ENTITY_LABEL,
  DEFAULT_STATE_LABEL,
  emptyMetricsText,
  entityColorOf,
  entityLabelOf,
  favoriteDaysOf,
  isReviewDue,
  metricKindLabelOf,
  normalizeAssetType,
  pickTags,
  reviewTextOf,
  stateChipStyleOf,
  stateLabelOf,
  venueLabelOf
} from "../roadCardModel";

const TAG = (id: number, name: string): WatchlistTag =>
  ({ id, name, color: "#fff" }) as WatchlistTag;

describe("entityColorOf / entityLabelOf", () => {
  it("已登记实体取令牌与中文名", () => {
    expect(entityColorOf("fund")).toBe("var(--asset-cat-fund)");
    expect(entityLabelOf("fund")).toBe("基金");
  });

  it("未登记实体回落默认色与「资产」，不留空胶囊", () => {
    expect(entityColorOf("crypto")).toBe(DEFAULT_ENTITY_COLOR);
    expect(entityLabelOf("crypto")).toBe(DEFAULT_ENTITY_LABEL);
  });
});

describe("stateLabelOf", () => {
  it("三种真实状态各有中文名", () => {
    expect(stateLabelOf("holding")).toBe("持仓中");
    expect(stateLabelOf("watching")).toBe("观察中");
    expect(stateLabelOf("cleared")).toBe("已清仓");
  });

  it("未知状态回落「观察中」（最保守的那一档）", () => {
    expect(stateLabelOf("liquidated")).toBe(DEFAULT_STATE_LABEL);
  });
});

describe("venueLabelOf", () => {
  it("已登记交易所取映射", () => {
    expect(venueLabelOf("SH")).toBeTruthy();
  });

  it("未登记交易所原样显示 —— 兜底方向与实体相反", () => {
    expect(venueLabelOf("BSE")).toBe("BSE");
  });

  it("空值省掉这一节", () => {
    expect(venueLabelOf(null)).toBe("");
    expect(venueLabelOf(undefined)).toBe("");
    expect(venueLabelOf("")).toBe("");
  });
});

describe("normalizeAssetType", () => {
  it("转小写后交给标签表", () => {
    expect(normalizeAssetType("FUND")).toBe("fund");
    expect(normalizeAssetType("Stock")).toBe("stock");
  });

  it("manager 返回空串：域特有实体，不显示英文原键", () => {
    expect(normalizeAssetType("manager")).toBe("");
    expect(normalizeAssetType("MANAGER")).toBe("");
  });

  it("空值返回空串", () => {
    expect(normalizeAssetType(null)).toBe("");
    expect(normalizeAssetType(undefined)).toBe("");
    expect(normalizeAssetType("")).toBe("");
  });
});

describe("metricKindLabelOf", () => {
  it("基金画净值、指数画点位、股票画价格", () => {
    expect(metricKindLabelOf("fund")).toBe("净值");
    expect(metricKindLabelOf("index")).toBe("点位");
    expect(metricKindLabelOf("stock")).toBe("价格");
  });

  it("经理没有价格曲线，不标注", () => {
    expect(metricKindLabelOf("manager")).toBe("");
    expect(metricKindLabelOf("crypto")).toBe("");
  });
});

describe("stateChipStyleOf", () => {
  it("持仓态走品牌色（语义色，非涨跌）", () => {
    expect(stateChipStyleOf("holding")).toEqual({
      backgroundColor: "var(--brand-100)",
      color: "var(--brand-700)"
    });
  });

  it("未知状态回落观察态配色", () => {
    expect(stateChipStyleOf("liquidated")).toEqual(
      stateChipStyleOf("watching")
    );
  });

  it("每次返回新对象：调用方改动不会污染下一次（色表是共享常量）", () => {
    const a = stateChipStyleOf("holding");
    a.backgroundColor = "red";
    expect(stateChipStyleOf("holding").backgroundColor).toBe(
      "var(--brand-100)"
    );
  });
});

describe("pickTags", () => {
  const tags = [TAG(1, "长期持有"), TAG(2, "待观察"), TAG(3, "已复盘")];

  it("顺序沿用 tag_ids（用户勾选顺序），不按标签表重排", () => {
    expect(pickTags([3, 1], tags).map(t => t.name)).toEqual([
      "已复盘",
      "长期持有"
    ]);
  });

  it("找不到的 id 直接丢弃（后端删标签后本地残留 id 是常态）", () => {
    expect(pickTags([1, 99], tags).map(t => t.name)).toEqual(["长期持有"]);
  });

  it("空 tag_ids ⇒ 空数组，不抛错", () => {
    expect(pickTags([], tags)).toEqual([]);
  });
});

describe("复盘提醒（7 天边界）", () => {
  beforeEach(() => {
    // 固定在 2026-10-27，避免跨零点跑测试时 ±1 天漂移
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-27T10:00:00"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("reviewTextOf：逾期 / 今天 / 7 天内 / 更远 四档文案", () => {
    expect(reviewTextOf("2026-10-24")).toBe("复盘已逾期 3 天");
    expect(reviewTextOf("2026-10-27")).toBe("今天该复盘了");
    expect(reviewTextOf("2026-10-30")).toBe("还有 3 天该复盘");
    expect(reviewTextOf("2026-12-01")).toBe("2026-12-01 复盘");
  });

  it("reviewTextOf：无日期 / 非法日期 ⇒ null，由模板降级", () => {
    expect(reviewTextOf(null)).toBeNull();
    expect(reviewTextOf("不是日期")).toBeNull();
  });

  it("isReviewDue：7 天内含第 7 天与逾期", () => {
    expect(isReviewDue("2026-11-03")).toBe(true); // +7
    expect(isReviewDue("2026-10-20")).toBe(true); // 逾期
    expect(isReviewDue("2026-10-27")).toBe(true); // 今天
  });

  it("isReviewDue：第 8 天起不算临近", () => {
    expect(isReviewDue("2026-11-04")).toBe(false); // +8
  });

  it("isReviewDue：无日期 ⇒ false（没有日期就没有「临近」）", () => {
    expect(isReviewDue(null)).toBe(false);
  });
});

describe("favoriteDaysOf", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-27T10:00:00"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("按自然日算天数", () => {
    expect(favoriteDaysOf("2026-10-17")).toBe(10);
  });

  it("未来日期夹到 0（clock 漂移不产生负数天数）", () => {
    expect(favoriteDaysOf("2026-11-10")).toBe(0);
  });

  it("缺失 ⇒ null，模板据此省掉「关注 N 天」", () => {
    expect(favoriteDaysOf(null)).toBeNull();
  });
});

describe("emptyMetricsText", () => {
  it("经理与其它实体的「没数据」不是一回事", () => {
    expect(emptyMetricsText("manager")).toBe("经理生涯数据接入中");
    expect(emptyMetricsText("fund")).toBe("行情数据积累中");
    expect(emptyMetricsText("stock")).toBe("行情数据积累中");
  });
});
