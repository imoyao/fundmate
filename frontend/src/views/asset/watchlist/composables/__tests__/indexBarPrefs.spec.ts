/**
 * 指数条本地偏好（#watchlist 指数个性化设置）的持久化契约测试。
 *
 * 这组用例钉的是**「改得动」之外的那一半**：改动必须真的落盘，且**不依赖任何组件还活着**。
 *
 * ## 为什么要专门测「卸载之后」
 *
 * 旧实现的写盘是 `watch(selected, …)` / `watch(enabled, …)`，而那两个 watcher 是在
 * **组件 setup() 里**创建的 ⇒ 绑在调用方的 effect scope 上，页面一卸载（关页签 / 右键
 * 刷新 / 登出清缓存）就被 stop，而模块级的 `watchStarted` 又挡住了重建。
 * 结果是：顶栏照常显示用户选的指数（内存状态还在），**但再没有任何人写盘**。
 * 用户体感就是「设置存不住，刷新一下又回到默认列表」。
 *
 * `按组件卸载后的 scope 停止` 那条用例就是这条回归的判据：把 `persist` 挪回 watcher、
 * 或把 watcher 建在调用方 scope 里，它必定转红（已用旧实现在本地验证过）。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { effectScope } from "vue";

const KEY_SELECTION = "watchlist-index-bar-selection";
const KEY_MOTION = "watchlist-index-bar-motion";

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

/** 让读盘的 then/catch 跑完（node 环境无假定时器需求） */
function flush(): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, 0));
}

async function loadSelectionModule() {
  return await import("@/views/asset/watchlist/composables/useIndexBarSelection");
}

async function loadMotionModule() {
  return await import("@/views/asset/watchlist/composables/useIndexBarMotionPref");
}

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  m.store.clear();
});

describe("指数选择：读盘", () => {
  it("盘里有值 → 用盘里的（不覆盖、也不重复写盘）", async () => {
    m.store.set(KEY_SELECTION, ["sz399300", "sz399001"]);
    const { useIndexBarSelection } = await loadSelectionModule();

    const { selected } = useIndexBarSelection();
    await flush();

    expect(selected.value).toEqual(["sz399300", "sz399001"]);
    expect(m.setItem).not.toHaveBeenCalled();
  });

  it("盘里为空 → 回落默认列表，但**不写盘**（写盘会把默认值固化成用户选择）", async () => {
    const { useIndexBarSelection } = await loadSelectionModule();

    const { selected } = useIndexBarSelection();
    await flush();

    expect(selected.value.length).toBeGreaterThan(0);
    expect(m.setItem).not.toHaveBeenCalled();
  });

  it("读盘失败 → 回落默认列表，也不写盘", async () => {
    m.getItem.mockRejectedValueOnce(new Error("IDB blocked"));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { useIndexBarSelection } = await loadSelectionModule();

    const { selected } = useIndexBarSelection();
    await flush();

    expect(selected.value.length).toBeGreaterThan(0);
    expect(m.setItem).not.toHaveBeenCalled();
    warn.mockRestore();
  });

  it("脏 key（不在目录中）在读盘时就被剔掉", async () => {
    m.store.set(KEY_SELECTION, ["sh000001", "不存在的东西"]);
    const { useIndexBarSelection } = await loadSelectionModule();

    const { selected } = useIndexBarSelection();
    await flush();

    expect(selected.value).toEqual(["sh000001"]);
  });
});

describe("指数选择：写盘与生命周期无关（回归根因）", () => {
  it("组件卸载（effect scope 停止）之后，保存仍然落盘", async () => {
    const { useIndexBarSelection } = await loadSelectionModule();

    // 模拟 IndexMarketBar 首次挂载：调用发生在组件 setup 的 effect scope 里
    const scope = effectScope();
    scope.run(() => useIndexBarSelection());
    await flush();
    // 模拟页面卸载（关页签 / 右键刷新 / 登出清缓存）
    scope.stop();

    const { setSelection } = useIndexBarSelection();
    setSelection(["sh000016", "sz399006"]);
    await flush();

    expect(m.setItem).toHaveBeenCalledWith(KEY_SELECTION, [
      "sh000016",
      "sz399006"
    ]);
  });

  it("增删改与排序都落盘（不再依赖 watcher 的 flush 时机）", async () => {
    const { useIndexBarSelection } = await loadSelectionModule();
    m.store.set(KEY_SELECTION, ["sh000001", "sz399001", "sz399006"]);
    const api = useIndexBarSelection();
    await flush();
    m.setItem.mockClear();

    api.addIndex("sz399300");
    expect(m.setItem).toHaveBeenLastCalledWith(KEY_SELECTION, [
      "sh000001",
      "sz399001",
      "sz399006",
      "sz399300"
    ]);

    api.moveIndex("sz399300", -1);
    expect(m.setItem).toHaveBeenLastCalledWith(KEY_SELECTION, [
      "sh000001",
      "sz399001",
      "sz399300",
      "sz399006"
    ]);

    api.removeIndex("sh000001");
    expect(m.setItem).toHaveBeenLastCalledWith(KEY_SELECTION, [
      "sz399001",
      "sz399300",
      "sz399006"
    ]);
  });

  it("没有实际变化（重复增 / 越界移动 / 删不存在的）不写盘", async () => {
    m.store.set(KEY_SELECTION, ["sh000001", "sz399001"]);
    const { useIndexBarSelection } = await loadSelectionModule();
    const api = useIndexBarSelection();
    await flush();
    m.setItem.mockClear();

    api.addIndex("sh000001"); // 已在列表
    api.moveIndex("sh000001", -1); // 已是第一个
    api.removeIndex("hkHSI"); // 不在列表

    expect(m.setItem).not.toHaveBeenCalled();
  });

  it("用户先改、读盘后到：迟到的旧值不得覆盖用户选择", async () => {
    m.store.set(KEY_SELECTION, ["sh000001"]);
    const { useIndexBarSelection } = await loadSelectionModule();
    const api = useIndexBarSelection();

    // 读盘尚未 settle 就改了（真实场景：IndexedDB 首次打开较慢）
    api.setSelection(["sz399006"]);
    await flush();

    expect(api.selected.value).toEqual(["sz399006"]);
    expect(m.setItem).toHaveBeenCalledWith(KEY_SELECTION, ["sz399006"]);
  });
});

describe("滚动开关：写盘与生命周期无关", () => {
  it("切换后落盘；组件卸载后再切也落盘", async () => {
    const { useIndexBarMotionPref } = await loadMotionModule();

    const scope = effectScope();
    scope.run(() => useIndexBarMotionPref());
    await flush();
    scope.stop();

    const { enabled, setEnabled } = useIndexBarMotionPref();
    setEnabled(false);
    await flush();

    expect(enabled.value).toBe(false);
    expect(m.setItem).toHaveBeenCalledWith(KEY_MOTION, false);
  });

  it("盘里是 false → 读到就被关掉（不被默认 true 覆盖）", async () => {
    m.store.set(KEY_MOTION, false);
    const { useIndexBarMotionPref } = await loadMotionModule();

    const { enabled } = useIndexBarMotionPref();
    await flush();

    expect(enabled.value).toBe(false);
    expect(m.setItem).not.toHaveBeenCalled();
  });

  it("读盘失败 → 默认开启，且不写盘", async () => {
    m.getItem.mockRejectedValueOnce(new Error("IDB blocked"));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { useIndexBarMotionPref } = await loadMotionModule();

    const { enabled } = useIndexBarMotionPref();
    await flush();

    expect(enabled.value).toBe(true);
    expect(m.setItem).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});
