/**
 * 隐私模式（「鸵鸟模式」）的判据。
 *
 * 这个功能的价值全在「真的藏住了」这四个字上，所以测试只钉三件事：
 * 1. 状态**持久化**：刷新后仍然遮着（否则每次进页面都要重新点一遍）；
 * 2. 状态**全局单例**：同一页面内所有金额一起遮（半遮半掩比不遮更糟）；
 * 3. 长按窥视是**临时**的：松手立刻复原，且不足 180ms 不触发（否则滚动一下
 *    整页数字就闪一下，等于向旁边的人提示「这里有东西」）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const KEY = "fundmate:privacy:mask-amounts";

/** 最小 window 替身：只提供本 composable 真正用到的四个成员（node 环境无 DOM） */
function installWindow(seed: Record<string, string> = {}) {
  const store = new Map<string, string>(Object.entries(seed));
  vi.stubGlobal("window", {
    localStorage: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
      removeItem: (key: string) => void store.delete(key)
    },
    setTimeout: (fn: () => void, ms: number) => setTimeout(fn, ms),
    clearTimeout: (id: number) => clearTimeout(id)
  });
  return store;
}

/** 模块级单例 ⇒ 每次取「新进程」语义都必须 resetModules，否则拿到的是上一例的状态 */
async function loadComposable() {
  vi.resetModules();
  return import("../usePrivacyMode");
}

describe("usePrivacyMode", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("默认不遮罩", async () => {
    installWindow();
    const { usePrivacyMode } = await loadComposable();

    const { masked, visible } = usePrivacyMode();

    expect(masked.value).toBe(false);
    expect(visible.value).toBe(true);
  });

  it("读过一次遮罩偏好后，刷新仍然遮着（持久化到 localStorage）", async () => {
    installWindow({ [KEY]: "1" });
    const { usePrivacyMode } = await loadComposable();

    const { masked, visible } = usePrivacyMode();

    expect(masked.value).toBe(true);
    expect(visible.value).toBe(false);
  });

  it("toggle 同时改写状态与存储，两个消费方看到同一份状态", async () => {
    const store = installWindow();
    const { usePrivacyMode } = await loadComposable();

    const first = usePrivacyMode();
    const second = usePrivacyMode();
    first.toggle();

    expect(store.get(KEY)).toBe("1");
    // 单例语义：另一个组件立刻跟着遮（不是各拿一份 ref）
    expect(second.masked.value).toBe(true);

    first.toggle();
    expect(store.get(KEY)).toBe("0");
    expect(second.masked.value).toBe(false);
  });

  it("长按满 180ms 才揭示，松手立刻复原", async () => {
    installWindow({ [KEY]: "1" });
    const { usePrivacyMode } = await loadComposable();
    const { visible, startPeek, endPeek } = usePrivacyMode();

    expect(visible.value).toBe(false);

    startPeek();
    vi.advanceTimersByTime(179);
    expect(visible.value).toBe(false); // 差 1ms 仍不揭示：滚动误触不能窥屏

    vi.advanceTimersByTime(1);
    expect(visible.value).toBe(true);

    endPeek();
    expect(visible.value).toBe(false);
  });

  it("不足 180ms 就松手 ⇒ 从头到尾没有揭示过", async () => {
    installWindow({ [KEY]: "1" });
    const { usePrivacyMode } = await loadComposable();
    const { visible, startPeek, endPeek } = usePrivacyMode();

    startPeek();
    vi.advanceTimersByTime(100);
    endPeek();
    vi.advanceTimersByTime(500);

    expect(visible.value).toBe(false);
  });

  it("没开遮罩时长按不产生任何效果（也不该揭开一个本来就可见的数）", async () => {
    installWindow();
    const { usePrivacyMode } = await loadComposable();
    const { visible, startPeek } = usePrivacyMode();

    startPeek();
    vi.advanceTimersByTime(500);

    expect(visible.value).toBe(true);
  });
});
