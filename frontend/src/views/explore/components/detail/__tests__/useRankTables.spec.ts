/**
 * 行业 / 赛道排行数据层测试（#980 拆分时补）。
 *
 * 这层的三个静默错误点：
 * 1. 切到「热门赛道」时没把视图退回「拥挤度」→ 停在空视图（赛道没有乖离率）；
 * 2. 「标题行的更新时间」取错表（分类 × 视图四种组合，取错不会报错，只是显示别的表的时间）；
 * 3. `item_code === "__NA__"` 的整组占位没被过滤 → 表格里出现一行「暂无数据」的假行业。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/temperature", () => ({ getMultiItems: vi.fn() }));

import { getMultiItems } from "@/api/temperature";
import {
  CROWDING_HIGH_THRESHOLD,
  CROWDING_LOW_THRESHOLD
} from "@/constants/temperature";
import { RANK_LEGEND, useRankTables } from "../useRankTables";

const mocked = vi.mocked(getMultiItems);

function item(code: string, name = code) {
  return { item_code: code, item_name: name };
}

function respond(payload: Record<string, unknown>) {
  mocked.mockImplementation((source: string) => {
    const data = payload[source];
    return Promise.resolve({ data } as any);
  });
}

describe("useRankTables", () => {
  beforeEach(() => {
    mocked.mockReset();
  });

  it("默认停在「申万行业 × 拥挤度」", () => {
    const t = useRankTables();
    expect(t.rankCategory.value).toBe("sw");
    expect(t.rankView.value).toBe("crowding");
  });

  it("切到热门赛道时强制回到拥挤度（赛道没有乖离率视图）", () => {
    const t = useRankTables();
    t.rankView.value = "bias";
    t.switchCategory("track");
    expect(t.rankCategory.value).toBe("track");
    expect(t.rankView.value).toBe("crowding");
  });

  it("切回申万行业不改变当前视图", () => {
    const t = useRankTables();
    t.rankView.value = "bias";
    t.switchCategory("sw");
    expect(t.rankView.value).toBe("bias");
  });

  it("赛道分类只有「拥挤度」一个选项", () => {
    const t = useRankTables();
    expect(t.rankViewOptions.value.map(o => o.value)).toEqual([
      "crowding",
      "bias"
    ]);
    t.rankCategory.value = "track";
    expect(t.rankViewOptions.value.map(o => o.value)).toEqual(["crowding"]);
  });

  it("三张表按 source 各自取数，并带上日期与滞后标记", async () => {
    respond({
      industry_crowding: {
        items: [item("sw_1")],
        date: "2026-10-23",
        stale: true
      },
      track_crowding: {
        items: [item("t_1")],
        date: "2026-10-22",
        stale: false
      },
      bias: { items: [item("sw_1")], date: "2026-10-21", stale: false }
    });
    const t = useRankTables();
    await t.fetchRankTables();

    expect(mocked.mock.calls.map(c => c[0]).sort()).toEqual([
      "bias",
      "industry_crowding",
      "track_crowding"
    ]);
    expect(t.activeRankView.value.date).toBe("2026-10-23");
    expect(t.activeRankView.value.stale).toBe(true);

    t.rankView.value = "bias";
    expect(t.activeRankView.value.date).toBe("2026-10-21");

    t.rankCategory.value = "track";
    t.rankView.value = "crowding";
    expect(t.activeRankView.value.date).toBe("2026-10-22");
  });

  it("任一条 stale 也算整表滞后（后端只给组级标记时）", async () => {
    respond({
      industry_crowding: {
        items: [item("a"), { ...item("b"), stale: true }],
        date: "2026-10-23",
        stale: false
      },
      track_crowding: { items: [], date: "", stale: false },
      bias: { items: [], date: "", stale: false }
    });
    const t = useRankTables();
    await t.fetchRankTables();
    expect(t.activeRankView.value.stale).toBe(true);
  });

  it("过滤 item_code 为 __NA__ 的整组占位（不渲染成假行业）", async () => {
    respond({
      industry_crowding: {
        items: [item("__NA__", "暂无数据"), item("sw_1")],
        date: "2026-10-23"
      },
      track_crowding: {
        items: [item("__NA__", "暂无数据"), item("t_1"), item("t_2")],
        date: "2026-10-23"
      },
      bias: { items: [], date: "" }
    });
    const t = useRankTables();
    await t.fetchRankTables();

    expect(t.activeCrowdingItems.value.map((i: any) => i.item_code)).toEqual([
      "sw_1"
    ]);
    t.rankCategory.value = "track";
    expect(t.activeCrowdingItems.value.map((i: any) => i.item_code)).toEqual([
      "t_1",
      "t_2"
    ]);
  });

  it("data 为 null 时清空条目但不报错（外部源关停 / 读库无快照）", async () => {
    respond({ industry_crowding: null, track_crowding: null, bias: null });
    const t = useRankTables();
    await t.fetchRankTables();
    expect(t.activeCrowdingItems.value).toEqual([]);
    expect(t.biasItems.value).toEqual([]);
  });

  it("请求失败时静默清空并记录日志，不把错误抛给调用方", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    mocked.mockRejectedValue(new Error("boom"));
    const t = useRankTables();
    await expect(t.fetchRankTables()).resolves.toBeDefined();
    expect(t.activeCrowdingItems.value).toEqual([]);
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  it("loading 在请求前后翻转（首屏骨架依赖它）", async () => {
    // 三张表并发，各自持有一个未决 promise —— 收集 release 逐个放行，
    // 只解一个会让 Promise.all 永远等另外两个（第一版就踩了这个超时）。
    const releases: Array<(v: any) => void> = [];
    mocked.mockImplementation(
      () => new Promise(res => releases.push(res)) as any
    );
    const t = useRankTables();
    const pending = t.fetchRankTables();
    expect(releases).toHaveLength(3);
    expect(t.activeCrowdingLoading.value).toBe(true);
    releases.forEach(release => release({ data: { items: [], date: "" } }));
    await pending;
    expect(t.activeCrowdingLoading.value).toBe(false);
  });

  it("分类选项只暴露 label/value，不漏出 source 等业务字段", () => {
    const t = useRankTables();
    expect(t.rankCategoryOptions).toEqual([
      { label: "申万行业", value: "sw" },
      { label: "热门赛道", value: "track" }
    ]);
    for (const opt of t.rankCategoryOptions) {
      expect(Object.keys(opt).sort()).toEqual(["label", "value"]);
    }
  });
});

describe("RANK_LEGEND", () => {
  it("三段文案直接引用阈值常量，不写死数字", () => {
    expect(RANK_LEGEND.map(l => l.label)).toEqual([
      `低迷 <${CROWDING_LOW_THRESHOLD}`,
      `中性 ${CROWDING_LOW_THRESHOLD}–${CROWDING_HIGH_THRESHOLD}`,
      `过热 >${CROWDING_HIGH_THRESHOLD}`
    ]);
  });

  it("色点类名与三段一一对应", () => {
    expect(RANK_LEGEND.map(l => l.dotClass)).toEqual([
      "rank-legend__dot--low",
      "rank-legend__dot--mid",
      "rank-legend__dot--high"
    ]);
  });
});
