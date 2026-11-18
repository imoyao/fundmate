/**
 * #2922 契约测试：自选页「本地视图偏好」store（`store/modules/watchlistPrefs`）。
 *
 * 这组用例钉的是**下沉后必须成立的新语义**，不是实现细节：
 *
 * 1. **跨挂载点共享**：两个消费者拿到同一份状态，改一处另一处立即可见
 *    （自选页表格 + 设置抽屉的真实用法）；
 * 2. **可重置**：换一个 pinia 实例状态就归零——这是「从模块级单例搬进 store」
 *    唯一的行为收益，也是旧实现做不到的（模块级 ref 会跨越测试 / 会话残留）；
 * 3. **归一与持久化口径不变**：档位白名单、同值不写、迁移旧键（`pct` → `ratio`）、
 *    读盘只跑一次（记忆化 Promise）。
 *
 * 灵敏度：把 `changePageSize` 的 `return false` 改成 `return true`、或去掉
 * `normalizeSortMetric` 迁移分支，本文件对应用例必定转红（已验证，见 PR 描述）。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

const m = vi.hoisted(() => {
  const store = new Map<string, unknown>();
  return {
    store,
    getItem: vi.fn(async (key: string) => store.get(key) ?? null),
    setItem: vi.fn(async (key: string, value: unknown) => {
      store.set(key, value);
    })
  };
});

vi.mock("@/utils/localforage", () => ({
  localForage: () => ({ getItem: m.getItem, setItem: m.setItem })
}));

const PAGE_SIZE_STORAGE_KEY = "watchlist-page-size";
const SORT_METRICS_STORAGE_KEY = "watchlist-sort-metrics";
const LEGACY_KEY = "watchlist-day-pnl-metric";

async function loadStore() {
  return await import("@/store/modules/watchlistPrefs");
}

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  m.store.clear();
  setActivePinia(createPinia());
});

describe("共享性：两个挂载点看到同一份偏好", () => {
  it("消费者 A 改每页条数，消费者 B 立即可见（同一 store）", async () => {
    const { useWatchlistPrefsStore } = await loadStore();
    const a = useWatchlistPrefsStore();
    const b = useWatchlistPrefsStore();

    expect(a.pageSize).toBe(20);
    a.changePageSize(50);

    expect(b.pageSize).toBe(50);
    expect(a).toBe(b);
  });

  it("消费者 A 切某列口径，消费者 B 读到的就是新口径（按列 key 各存各的）", async () => {
    const { useWatchlistPrefsStore } = await loadStore();
    const a = useWatchlistPrefsStore();
    const b = useWatchlistPrefsStore();

    a.setSortMetric("day_pnl", "ratio");
    a.setSortMetric("holding_pnl", "ratio");

    expect(b.sortMetricOf("day_pnl")).toBe("ratio");
    // 未设过的列仍回落默认，不被别的列带跑
    expect(b.sortMetricOf("yesterday_pnl")).toBe("amount");
    expect(Object.keys(b.sortMetrics).sort()).toEqual([
      "day_pnl",
      "holding_pnl"
    ]);
  });
});

describe("可重置：换 pinia 实例即归零（旧模块级单例做不到）", () => {
  it("新实例从默认 20 起，且不带上一实例的口径", async () => {
    const { useWatchlistPrefsStore } = await loadStore();
    const first = useWatchlistPrefsStore();
    first.changePageSize(100);
    first.setSortMetric("day_pnl", "ratio");
    expect(first.pageSize).toBe(100);

    setActivePinia(createPinia());
    const second = useWatchlistPrefsStore();

    expect(second.pageSize).toBe(20);
    expect(second.sortMetricOf("day_pnl")).toBe("amount");
  });
});

describe("每页条数：归一 + 持久化 + 幂等加载", () => {
  it("合法档位：返回 true、写盘、值生效", async () => {
    const { useWatchlistPrefsStore } = await loadStore();
    const store = useWatchlistPrefsStore();

    expect(store.changePageSize(50)).toBe(true);
    expect(store.pageSize).toBe(50);
    expect(m.setItem).toHaveBeenCalledWith(PAGE_SIZE_STORAGE_KEY, 50);
  });

  it("同值重复点：返回 false 且不写盘（调用方据此不重取）", async () => {
    const { useWatchlistPrefsStore } = await loadStore();
    const store = useWatchlistPrefsStore();

    expect(store.changePageSize(20)).toBe(false);
    expect(m.setItem).not.toHaveBeenCalled();
  });

  it("越界档位回退默认（与后端 per_page 限幅 [1,200] 不冲突）", async () => {
    const { useWatchlistPrefsStore } = await loadStore();
    const store = useWatchlistPrefsStore();
    store.changePageSize(50);

    expect(store.changePageSize(1000)).toBe(true);
    expect(store.pageSize).toBe(20);
  });

  it("initPageSize 幂等：并发 / 重复调用只读一次盘", async () => {
    m.store.set(PAGE_SIZE_STORAGE_KEY, 100);
    const { useWatchlistPrefsStore } = await loadStore();
    const store = useWatchlistPrefsStore();

    await Promise.all([store.initPageSize(), store.initPageSize()]);
    await store.initPageSize();

    expect(m.getItem).toHaveBeenCalledTimes(1);
    expect(store.pageSize).toBe(100);
  });

  it("盘里是非法值（3 / null）时不采信，保持默认", async () => {
    m.store.set(PAGE_SIZE_STORAGE_KEY, 3);
    const { useWatchlistPrefsStore } = await loadStore();
    const store = useWatchlistPrefsStore();

    await store.initPageSize();

    expect(store.pageSize).toBe(20);
  });
});

describe("排序口径：读盘归一 + 旧键迁移 + 只跑一次", () => {
  it("按列 key 读盘；非法值丢弃，`pct` 迁移成 `ratio`", async () => {
    m.store.set(SORT_METRICS_STORAGE_KEY, {
      day_pnl: "pct",
      holding_pnl: "ratio",
      position_market_value: "垃圾值"
    });
    const { useWatchlistPrefsStore } = await loadStore();
    const store = useWatchlistPrefsStore();

    await store.loadSortMetrics();

    expect(store.sortMetricOf("day_pnl")).toBe("ratio");
    expect(store.sortMetricOf("holding_pnl")).toBe("ratio");
    expect(store.sortMetricOf("position_market_value")).toBe("amount");
  });

  it("缺 day_pnl 时读首版单值键做迁移（不读会让老用户静默回落成金额）", async () => {
    m.store.set(LEGACY_KEY, "pct");
    const { useWatchlistPrefsStore } = await loadStore();
    const store = useWatchlistPrefsStore();

    await store.loadSortMetrics();

    expect(store.sortMetricOf("day_pnl")).toBe("ratio");
  });

  it("只跑一次：重复调用不再读盘", async () => {
    const { useWatchlistPrefsStore } = await loadStore();
    const store = useWatchlistPrefsStore();

    await store.loadSortMetrics();
    // 首次 = 读口径键 + （day_pnl 缺失时）再读首版单值键迁移，故不钉绝对值
    const readsAfterFirst = m.getItem.mock.calls.length;
    await store.loadSortMetrics();

    expect(m.getItem.mock.calls.length).toBe(readsAfterFirst);
  });

  it("setSortMetric 换新对象（引用变化才能让排序 computed 重算）", async () => {
    const { useWatchlistPrefsStore } = await loadStore();
    const store = useWatchlistPrefsStore();
    const before = store.sortMetrics;

    store.setSortMetric("day_pnl", "ratio");

    expect(store.sortMetrics).not.toBe(before);
    expect(m.setItem).toHaveBeenCalledWith(
      SORT_METRICS_STORAGE_KEY,
      expect.objectContaining({ day_pnl: "ratio" })
    );
  });

  it("同值不重复写盘", async () => {
    const { useWatchlistPrefsStore } = await loadStore();
    const store = useWatchlistPrefsStore();

    store.setSortMetric("day_pnl", "amount");
    expect(m.setItem).not.toHaveBeenCalled();

    store.setSortMetric("day_pnl", "ratio");
    store.setSortMetric("day_pnl", "ratio");
    expect(m.setItem).toHaveBeenCalledTimes(1);
  });
});
