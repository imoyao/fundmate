/**
 * `useDiscrepancyBanner` 的状态编排单测（#980 批 B8）。
 *
 * ## 为什么这个文件值得存在
 *
 * `DiscrepancyBanner` 全仓 `src/` 内**无人引用**（孤儿组件），没有 Playwright e2e
 * 能从页面走到它。抽出 composable 之后，横幅「显不显示 / 显示几条 / 点掉后记不记得住」
 * 这些会直接对用户撒谎的逻辑，只能在这一层被钉住。
 *
 * ## 环境约定
 *
 * 前端单测跑 node 环境（无 DOM、无组件实例），所以：
 * - 一律用 `{ autoStart: false }` 关掉 `onMounted`，改由用例显式 `refresh()` 驱动；
 * - `sessionStorage` 用 Map 桩顶掉（node 未开 webstorage）；
 * - `vue-router` / 两个 api 模块整体 mock，`./helpers` 保持真实实现
 *   —— 过滤与排序是这层要验证的口径，不能连它一起 mock 掉。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, reactive, type EffectScope } from "vue";

const route = reactive<{ name: string }>({ name: "Portfolio" });
const push = vi.fn();

vi.mock("vue-router", () => ({
  useRoute: () => route,
  useRouter: () => ({ push })
}));

const listDiscrepancies = vi.fn();
vi.mock("@/api/reconciliation", () => ({
  listDiscrepancies: (...args: unknown[]) => listDiscrepancies(...args)
}));

const getMe = vi.fn();
vi.mock("@/api/auth", () => ({
  getMe: (...args: unknown[]) => getMe(...args)
}));

import { useDiscrepancyBanner } from "../useDiscrepancyBanner";

const STORAGE_KEY = "recon_pending_banner_dismissed";

/** 差异行（只填本模块用到的字段） */
function row(
  id: number,
  domain: string,
  daysAgo: number | null
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
    first_detected_at: daysAgo === null ? null : isoDaysAgo(daysAgo)
  };
}

/** `days` 天前的本地日期 + 后端那种带微秒的时间尾巴 */
function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T06:06:39.184874`;
}

/** 等一轮微任务（取数是 promise 链，且 watch 回调里是 void 调用） */
const flush = () => new Promise(resolve => setTimeout(resolve, 0));

let store: Map<string, string>;
/**
 * 每个用例一个 effectScope：composable 里的 `watch` 没有组件实例可依附，
 * 不放进 scope 就会挂到共享的 `route` 上，跨用例累积重复触发（实测会把
 * 「应该 2 次」变成 15 次）。
 */
let scope: EffectScope;

/** 在独立 scope 里调一次 composable，用例结束时统一 stop */
function setup() {
  return scope.run(() => useDiscrepancyBanner({ autoStart: false }))!;
}

beforeEach(() => {
  scope = effectScope();
  store = new Map();
  vi.stubGlobal("sessionStorage", {
    getItem: (k: string) => (store.has(k) ? store.get(k) : null),
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear()
  });
  route.name = "Portfolio";
  push.mockReset();
  listDiscrepancies.mockReset();
  getMe.mockReset();
  getMe.mockResolvedValue({ data: { family: { id: 7 } }, message: "" });
  listDiscrepancies.mockResolvedValue({ data: [], message: "" });
});

afterEach(() => {
  scope.stop();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("取数口径", () => {
  it("只统计域 B：域 A / C 的待处理差异不进横幅数字", async () => {
    listDiscrepancies.mockResolvedValue({
      data: [row(1, "B", 3), row(2, "A", 3), row(3, "C", 3), row(4, "B", 3)],
      message: ""
    });
    const banner = setup();
    await banner.refresh();
    expect(banner.count.value).toBe(2);
    expect(banner.loading.value).toBe(false);
  });

  it("只问一次「待处理」：参数写死 status=pending", async () => {
    const banner = setup();
    await banner.refresh();
    expect(listDiscrepancies).toHaveBeenCalledWith({ status: "pending" });
  });

  it("接口失败按「没有差异」处理，不抛也不残留旧数据", async () => {
    listDiscrepancies.mockRejectedValue(new Error("boom"));
    const banner = setup();
    await banner.refresh();
    expect(banner.count.value).toBe(0);
    expect(banner.stalestDays.value).toBeNull();
    expect(banner.loading.value).toBe(false);
  });

  it("getMe 只打一次：家庭 id 在本次调用内缓存", async () => {
    const banner = setup();
    await banner.refresh();
    await banner.refresh();
    expect(getMe).toHaveBeenCalledTimes(1);
  });
});

describe("挂得最久的那条", () => {
  it("stalestDays 取排序后的第一条，不是接口返回的第一条", async () => {
    listDiscrepancies.mockResolvedValue({
      data: [row(1, "B", 2), row(2, "B", 49), row(3, "B", 7)],
      message: ""
    });
    const banner = setup();
    await banner.refresh();
    expect(banner.stalestDays.value).toBe(49);
    expect(banner.visibleItems.value[0].id).toBe(2);
  });

  it("发现时间缺失的排最后，不冒充最紧急", async () => {
    listDiscrepancies.mockResolvedValue({
      data: [row(1, "B", null), row(2, "B", 5)],
      message: ""
    });
    const banner = setup();
    await banner.refresh();
    expect(banner.visibleItems.value.map(i => i.id)).toEqual([2, 1]);
    expect(banner.stalestDays.value).toBe(5);
  });
});

describe("收起 / 展开", () => {
  const many = () =>
    listDiscrepancies.mockResolvedValue({
      data: Array.from({ length: 8 }, (_, i) => row(i + 1, "B", 10 - i)),
      message: ""
    });

  it("收起态最多 5 条，其余折成计数", async () => {
    many();
    const banner = setup();
    await banner.refresh();
    expect(banner.visibleItems.value).toHaveLength(5);
    expect(banner.hiddenCount.value).toBe(3);
  });

  it("展开态全给，计数归零（不重复显示「还有 N 条」）", async () => {
    many();
    const banner = setup();
    await banner.refresh();
    banner.expanded.value = true;
    expect(banner.visibleItems.value).toHaveLength(8);
    expect(banner.hiddenCount.value).toBe(0);
  });

  it("不足 5 条时计数不为负", async () => {
    listDiscrepancies.mockResolvedValue({
      data: [row(1, "B", 1)],
      message: ""
    });
    const banner = setup();
    await banner.refresh();
    expect(banner.hiddenCount.value).toBe(0);
  });
});

describe("关闭开关（家庭级）", () => {
  it("关过之后不再打接口，只把 loading 收掉", async () => {
    store.set(`${STORAGE_KEY}:7`, "1");
    const banner = setup();
    await banner.refresh();
    expect(listDiscrepancies).not.toHaveBeenCalled();
    expect(banner.loading.value).toBe(false);
    expect(banner.count.value).toBe(0);
  });

  it("dismiss() 立即隐藏，并按家庭 id 落盘", async () => {
    const banner = setup();
    await banner.refresh();
    banner.dismiss();
    expect(banner.dismissed.value).toBe(true);
    await flush();
    expect(store.get(`${STORAGE_KEY}:7`)).toBe("1");
  });

  it("换家庭不继承开关：另一个家庭 id 的 key 互不影响", async () => {
    store.set(`${STORAGE_KEY}:8`, "1");
    const banner = setup();
    await banner.refresh();
    expect(listDiscrepancies).toHaveBeenCalledTimes(1);
  });

  it("拿不到家庭时退化为无后缀 key —— 宁可隔离失效，也不要开关失效", async () => {
    getMe.mockRejectedValue(new Error("401"));
    const banner = setup();
    await banner.refresh();
    banner.dismiss();
    await flush();
    expect(store.get(STORAGE_KEY)).toBe("1");
  });
});

describe("路由相关", () => {
  it("工作台页自己不挂站外提醒", () => {
    route.name = "ReconcileWorkbench";
    const banner = setup();
    expect(banner.routeAllowed.value).toBe(false);
  });

  it("其它页面都挂", () => {
    route.name = "Portfolio";
    const banner = setup();
    expect(banner.routeAllowed.value).toBe(true);
  });

  it("从工作台返回时重新取数（处理完差异后数字要跟着变）", async () => {
    const banner = setup();
    await banner.refresh();
    expect(listDiscrepancies).toHaveBeenCalledTimes(1);

    route.name = "ReconcileWorkbench";
    await flush();
    route.name = "Portfolio";
    await flush();
    expect(listDiscrepancies).toHaveBeenCalledTimes(2);
    expect(banner.count.value).toBe(0);
  });

  it("非工作台之间的跳转不重复打接口", async () => {
    setup();
    route.name = "Assets";
    await flush();
    route.name = "ProductDetail";
    await flush();
    expect(listDiscrepancies).not.toHaveBeenCalled();
  });

  it("已关闭的横幅不因路由返回而复活并重新取数", async () => {
    const banner = setup();
    await banner.refresh();
    banner.dismiss();
    await flush();

    route.name = "ReconcileWorkbench";
    await flush();
    route.name = "Portfolio";
    await flush();
    // 只有首屏那一次
    expect(listDiscrepancies).toHaveBeenCalledTimes(1);
  });

  it("goToWorkbench 落到工作台并带上域 B", () => {
    const banner = setup();
    banner.goToWorkbench();
    expect(push).toHaveBeenCalledWith({
      path: "/investment/reconcile-workbench",
      query: { domain: "B" }
    });
  });
});
