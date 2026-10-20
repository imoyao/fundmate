import { describe, expect, it } from "vitest";
import {
  ageLabel,
  pendingDays,
  pickDomainBPending,
  shouldShowOnRoute,
  sortByStaleness,
  WORKBENCH_ROUTE_NAME
} from "../helpers";

/** 构造一条差异行（只填本模块用到的字段） */
function row(
  id: number,
  domain: string,
  firstDetectedAt: string | null
): {
  id: number;
  domain: string;
  symbol: string;
  discrepancy_type: string;
  first_detected_at: string | null;
} {
  return {
    id,
    domain,
    symbol: `CODE${id}`,
    discrepancy_type: "quantity",
    first_detected_at: firstDetectedAt
  };
}

/** 基准时刻：2026-10-20 12:00（本地） */
const NOW = new Date(2026, 9, 20, 12, 0, 0);

describe("pickDomainBPending（只取域 B，#2438）", () => {
  it("只保留域 B，域 C / 域 A 被排除", () => {
    const items = [
      row(1, "B", "2026-09-01T06:06:39.184874"),
      row(2, "C", "2026-10-01T00:00:00"),
      row(3, "A", "2026-10-02T00:00:00")
    ];
    expect(pickDomainBPending(items).map(i => i.id)).toEqual([1]);
  });

  it("空数组返回空数组", () => {
    expect(pickDomainBPending([])).toEqual([]);
  });
});

describe("pendingDays（待处理天数）", () => {
  it("按首次发现日算整天数", () => {
    expect(pendingDays("2026-09-01T06:06:39.184874", NOW)).toBe(49);
  });

  it("同日发现算 0 天（不是 1 天）", () => {
    expect(pendingDays("2026-10-20T01:00:00", NOW)).toBe(0);
  });

  it("带微秒的时间戳照样能解析（后端就是这种格式）", () => {
    expect(pendingDays("2026-10-18T13:45:59.123456", NOW)).toBe(2);
  });

  it("缺失 → null（未知，不假装 0 天）", () => {
    expect(pendingDays(null, NOW)).toBeNull();
    expect(pendingDays(undefined, NOW)).toBeNull();
    expect(pendingDays("", NOW)).toBeNull();
  });

  it("格式非法 → null（不抛错、不假装 0 天）", () => {
    expect(pendingDays("not-a-date", NOW)).toBeNull();
  });

  it("未来日期钳为 0（时钟漂移不产生负天数）", () => {
    expect(pendingDays("2026-11-01T00:00:00", NOW)).toBe(0);
  });
});

describe("sortByStaleness（按「挂得最久」排序）", () => {
  it("挂得最久的排最前", () => {
    const items = [
      row(1, "B", "2026-10-18T00:00:00"), // 2 天
      row(2, "B", "2026-09-01T00:00:00"), // 49 天
      row(3, "B", "2026-10-10T00:00:00") // 10 天
    ];
    expect(sortByStaleness(items, NOW).map(i => i.id)).toEqual([2, 3, 1]);
  });

  it("天数未知（null）排最后——不是最紧急", () => {
    const items = [row(1, "B", null), row(2, "B", "2026-09-01T00:00:00")];
    expect(sortByStaleness(items, NOW).map(i => i.id)).toEqual([2, 1]);
  });

  it("同天数按 id 升序（结果稳定可测）", () => {
    const items = [
      row(9, "B", "2026-10-01T00:00:00"),
      row(3, "B", "2026-10-01T00:00:00")
    ];
    expect(sortByStaleness(items, NOW).map(i => i.id)).toEqual([3, 9]);
  });

  it("不改动入参数组", () => {
    const items = [
      row(1, "B", "2026-10-18T00:00:00"),
      row(2, "B", "2026-09-01T00:00:00")
    ];
    const before = items.map(i => i.id);
    sortByStaleness(items, NOW);
    expect(items.map(i => i.id)).toEqual(before);
  });
});

describe("ageLabel（天数文案）", () => {
  it("未知 → 承认不知道", () => {
    expect(ageLabel(null)).toBe("发现时间未知");
  });

  it("0 / 1 天用口语，其余用数字", () => {
    expect(ageLabel(0)).toBe("今天发现");
    expect(ageLabel(1)).toBe("昨天发现");
    expect(ageLabel(49)).toBe("49 天前发现");
  });
});

describe("shouldShowOnRoute（工作台页不重复展示）", () => {
  it("工作台页不展示", () => {
    expect(shouldShowOnRoute(WORKBENCH_ROUTE_NAME)).toBe(false);
  });

  it("其它页面都展示", () => {
    expect(shouldShowOnRoute("Home")).toBe(true);
    expect(shouldShowOnRoute("AssetAnalysis")).toBe(true);
  });

  it("路由名缺失时展示（宁可多展示一次，也别让提醒静默消失）", () => {
    expect(shouldShowOnRoute(undefined)).toBe(true);
    expect(shouldShowOnRoute(null)).toBe(true);
  });
});
