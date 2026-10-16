/**
 * #1449 快捷筛选偏好：归一化纯函数 + 本地 ↔ 云端同步流。
 *
 * 同步流经 vi.mock 切断 localforage / userPreference API，模块级单例状态
 * 每用例 vi.resetModules() 后重新导入，避免用例间泄漏。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  defaultQuickFilters,
  normalizeQuickFilters,
  QUICK_FILTERS_PREF_KEY
} from "@/composables/watchlistQuickFilters";

const m = vi.hoisted(() => ({
  getItem: vi.fn(),
  setItem: vi.fn(),
  getPref: vi.fn(),
  putPref: vi.fn()
}));

vi.mock("@/utils/localforage", () => ({
  localForage: () => ({ getItem: m.getItem, setItem: m.setItem })
}));
vi.mock("@/api/userPreference", () => ({
  getUserPreference: m.getPref,
  putUserPreference: m.putPref
}));

/** 重置模块（单例状态不跨用例）并触发一次偏好同步，返回本用例的实例 */
async function freshQuickFilters() {
  vi.resetModules();
  const mod = await import("@/composables/useWatchlistQuickFilters");
  return mod.useWatchlistQuickFilters();
}

/** 等待已入队的同步微任务全部落地（断言「没有发生某事」前用） */
function flushAsync() {
  return new Promise(resolve => setTimeout(resolve, 0));
}

beforeEach(() => {
  vi.clearAllMocks();
  m.getItem.mockResolvedValue(null);
  m.setItem.mockResolvedValue(undefined);
  m.getPref.mockResolvedValue({ data: null });
  m.putPref.mockResolvedValue({ data: null });
});

describe("normalizeQuickFilters（归一化纯函数）", () => {
  it("非数组 / 空数组 / 全部无效 → null（调用方回退默认）", () => {
    expect(normalizeQuickFilters(null)).toBeNull();
    expect(normalizeQuickFilters(undefined)).toBeNull();
    expect(normalizeQuickFilters("stock")).toBeNull();
    expect(normalizeQuickFilters([])).toBeNull();
    expect(normalizeQuickFilters(["nope", 42, null])).toBeNull();
  });

  it("剔除未知类型与非字符串、去重、保留原有顺序", () => {
    expect(
      normalizeQuickFilters(["bond", "nope", "bond", 1, "stock", "bond"])
    ).toEqual(["bond", "stock"]);
  });

  it("有效类型子集原样返回（顺序即用户配置的外露次序）", () => {
    expect(normalizeQuickFilters(["money_fund", "index", "crypto"])).toEqual([
      "money_fund",
      "index",
      "crypto"
    ]);
  });
});

describe("useWatchlistQuickFilters（本地 ↔ 云端同步）", () => {
  it("两侧都无值 → 维持默认外露集，不产生云端写", async () => {
    const { quickFilters } = await freshQuickFilters();
    await vi.waitFor(() => expect(m.getPref).toHaveBeenCalled());
    expect(quickFilters.value).toEqual(defaultQuickFilters());
    expect(m.putPref).not.toHaveBeenCalled();
  });

  it("本地缓存先应用；云端较新则覆盖并把云端值回写本地", async () => {
    m.getItem.mockResolvedValue({
      filters: ["money_fund"],
      updated_at: 1000
    });
    m.getPref.mockResolvedValue({
      data: {
        value: { filters: ["crypto"] },
        updated_at: "1970-01-01T00:00:02.000Z" // 2000ms > 本地 1000ms
      }
    });
    const { quickFilters } = await freshQuickFilters();
    // #2199：应用路径补注入常驻项——云端旧值缺 stock/fund，生效值仍恒含且置顶
    await vi.waitFor(() =>
      expect(quickFilters.value).toEqual(["stock", "fund", "crypto"])
    );
    // 落盘仍是云端原值（注入只发生在应用层，云端值本身未被改写）
    expect(m.setItem).toHaveBeenCalledWith(
      QUICK_FILTERS_PREF_KEY,
      expect.objectContaining({ filters: ["crypto"], updated_at: 2000 })
    );
  });

  it("本地较新 → 本地生效并单向回传云端（剥离本地时钟字段）", async () => {
    m.getItem.mockResolvedValue({ filters: ["etf"], updated_at: 5000 });
    m.getPref.mockResolvedValue({
      data: {
        value: { filters: ["fund"] },
        updated_at: "1970-01-01T00:00:01.000Z" // 1000ms < 本地 5000ms
      }
    });
    const { quickFilters } = await freshQuickFilters();
    await vi.waitFor(() => expect(m.putPref).toHaveBeenCalled());
    // #2199：应用层注入 stock（fund 本地已有，只补缺的）并置顶
    expect(quickFilters.value).toEqual(["stock", "fund", "etf"]);
    // 回传值仍是本地原值（注入不改写偏好数据本身）
    expect(m.putPref).toHaveBeenCalledWith(QUICK_FILTERS_PREF_KEY, {
      filters: ["etf"]
    });
  });

  it("setQuickFilters 归一化（去重 / 剔无效）后本地 + 云端双写", async () => {
    const { quickFilters, setQuickFilters } = await freshQuickFilters();
    await vi.waitFor(() => expect(m.getPref).toHaveBeenCalled());
    setQuickFilters(["etf", "etf", "nope", "stock"]);
    // #2199：保存路径同样注入常驻项（fund 缺失被补上）并置顶，双写值与生效值一致
    expect(quickFilters.value).toEqual(["stock", "fund", "etf"]);
    expect(m.setItem).toHaveBeenCalledWith(
      QUICK_FILTERS_PREF_KEY,
      expect.objectContaining({ filters: ["stock", "fund", "etf"] })
    );
    expect(m.putPref).toHaveBeenCalledWith(QUICK_FILTERS_PREF_KEY, {
      filters: ["stock", "fund", "etf"]
    });
  });

  it("常驻项注入（#2199）：旧值缺 stock/fund 被补齐置顶，已有则只调序不重复", async () => {
    m.getItem.mockResolvedValue({
      filters: ["bond", "fund"],
      updated_at: 5000
    });
    m.getPref.mockResolvedValue({ data: null });
    const { quickFilters, setQuickFilters } = await freshQuickFilters();
    await vi.waitFor(() => expect(m.putPref).toHaveBeenCalled());
    // fund 已在列表中：只把 stock 补齐、fund 不重复，常驻项恒居前两位
    expect(quickFilters.value).toEqual(["stock", "fund", "bond"]);
    // 保存路径同样保证常驻项（显式传入 fund 在中间也不影响置顶语义）
    setQuickFilters(["bond", "fund"]);
    expect(quickFilters.value).toEqual(["stock", "fund", "bond"]);
  });

  it("云端值损坏 → 维持本地生效值，不触发任何覆盖写", async () => {
    m.getItem.mockResolvedValue({ filters: ["bond"], updated_at: 1000 });
    m.getPref.mockResolvedValue({
      data: {
        value: { filters: "oops" },
        updated_at: "1970-01-01T00:00:00.000Z"
      }
    });
    const { quickFilters } = await freshQuickFilters();
    await vi.waitFor(() => expect(m.getPref).toHaveBeenCalled());
    await flushAsync();
    // #2199：本地值应用时同样补注入常驻项
    expect(quickFilters.value).toEqual(["stock", "fund", "bond"]);
    expect(m.setItem).not.toHaveBeenCalled();
    expect(m.putPref).not.toHaveBeenCalled();
  });
});
