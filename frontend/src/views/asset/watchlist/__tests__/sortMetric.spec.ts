/**
 * 复合列「排序口径」纯模块判据（2026-10-30 二次优化）。
 *
 * ## 钉什么
 *
 * | # | 判据 | 为什么值得钉 |
 * |---|---|---|
 * | 1 | `amount` 取主行金额、`ratio` 取副行比例 | 三个复合列（当日盈亏 / 持仓市值 / 持仓收益）共用同一套口径，取错一行等于「按金额排却排了涨幅」 |
 * | 2 | 缺值原样传 `null`，不当 0 | 当 0 会让没数据的行看起来像「跌到 0 / 收益 0」，排序还会把它插到队首 |
 * | 3 | `pct` 旧值迁移成 `ratio` | 首版只服务当日盈亏且取值叫 `pct`；不迁移，老用户存过的「按涨幅排序」会静默回落成按金额 |
 * | 4 | 切换两次回到原口径 | 徽标是「点一下换一档」，换不回来就是死值 |
 * | 5 | 徽标符号 `¥` / `%` | 列宽 104px 只放得下一个字符（见 `sortMetric.ts` 注释） |
 */
import { describe, expect, it } from "vitest";

import {
  DEFAULT_SORT_METRIC,
  normalizeSortMetric,
  otherSortMetric,
  pickSortMetric,
  sortMetricSymbol,
  type SortMetric
} from "../sortMetric";

describe("pickSortMetric：两行数各排各的", () => {
  const result = { value: 1234.5, ratio: 2.34 };

  it("金额口径取 value，比例口径取 ratio", () => {
    expect(pickSortMetric(result, "amount")).toBe(1234.5);
    expect(pickSortMetric(result, "ratio")).toBe(2.34);
  });

  it("缺值原样透传 null（交给排序垫底，不当 0）", () => {
    expect(pickSortMetric({ value: null, ratio: 1 }, "amount")).toBeNull();
    expect(pickSortMetric({ value: 1, ratio: null }, "ratio")).toBeNull();
    expect(pickSortMetric({ value: null, ratio: null }, "ratio")).toBeNull();
  });
});

describe("otherSortMetric：徽标点一下就换档，且换得回来", () => {
  it("amount ↔ ratio", () => {
    expect(otherSortMetric("amount")).toBe("ratio");
    expect(otherSortMetric("ratio")).toBe("amount");
    expect(otherSortMetric(otherSortMetric("amount"))).toBe("amount");
  });
});

describe("normalizeSortMetric：读盘值的唯一入口（含旧值迁移）", () => {
  it("现值原样返回", () => {
    expect(normalizeSortMetric("amount")).toBe("amount");
    expect(normalizeSortMetric("ratio")).toBe("ratio");
  });

  it("首版旧值 pct 迁移为 ratio", () => {
    // 旧键 watchlist-day-pnl-metric 存的是 amount / pct
    expect(normalizeSortMetric("pct")).toBe("ratio");
  });

  it("无法识别返回 null，由调用方回落默认", () => {
    for (const bad of [undefined, null, "", "PCT", 1, {}, []]) {
      expect(normalizeSortMetric(bad)).toBeNull();
    }
  });

  it("默认口径是金额（与列主行一致）", () => {
    expect(DEFAULT_SORT_METRIC).toBe("amount");
  });
});

describe("sortMetricSymbol：104px 列头只放得下一个字符", () => {
  it("金额 ¥ / 比例 %", () => {
    const cases: SortMetric[] = ["amount", "ratio"];
    expect(cases.map(sortMetricSymbol)).toEqual(["¥", "%"]);
    // 判据：必须是单字符，两个汉字会把列名或排序三角挤出列宽（见 columnDefs 铁律 1）
    for (const metric of cases) {
      expect(sortMetricSymbol(metric)).toHaveLength(1);
    }
  });
});
