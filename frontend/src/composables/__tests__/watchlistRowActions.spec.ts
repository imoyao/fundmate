/**
 * #2931 D88 判据：行内 / 批量操作的**刷新出口唯一**。
 *
 * ## 为什么这条判据比「行数变少了」重要
 *
 * 拆出去之前，`togglePin` / `toggleFavorite` / `executeRemove` / `batchDelete` /
 * `batchMoveToGroup` 各自在结尾直接 `fetchData()`：5 个刷新出口。拆的时候最容易
 * 出的错不是「代码写错」，而是**漏接一个 wrapper**——子域返回了「已写库」信号，
 * 父级没接住 ⇒ 操作成功、提示正常、列表却还是旧数据。实测里我第一版就把
 * `executeRemove` 写成纯解构转发（`const { executeRemove } = rowActions`），
 * 移除后列表不刷新且**没有任何报错**，本文件第 3 条用例就是为它写的。
 *
 * 反向的错同样安静：某个操作既自己在子域刷、又被父级 wrapper 刷一次 ⇒ 两次全量请求
 * （`fields=lite` 最多 4 页），表现只是「点一下有点卡」。
 *
 * ## 怎么数「刷新了几次」
 *
 * 一次 `fetchData(refreshAll=true)` 会打两个请求：**页请求**（带 `page`/`per_page`，
 * 不带 `fields`）与 **全量请求**（带 `fields: "lite"`）。所以数 `getWatchlistItems`
 * 的总调用次数会恒为 2，看不出双刷。判据只数**页请求**：一次刷新 = 恰好一次页请求。
 */
import { ref } from "vue";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import { useWatchlistTags } from "@/composables/useWatchlistTags";
import {
  useWatchlistData,
  type WatchlistToolbarState
} from "@/composables/useWatchlistData";
import { useWatchlistRowActions } from "@/composables/watchlist/useWatchlistRowActions";
import type { WatchlistItem } from "@/api/watchlist";

const m = vi.hoisted(() => ({
  getItems: vi.fn(),
  getGroups: vi.fn(),
  getTags: vi.fn(),
  updateItem: vi.fn(),
  deleteItem: vi.fn(),
  removeItemFromGroup: vi.fn(),
  addItemToGroup: vi.fn(),
  confirm: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn()
}));

vi.mock("@/api/watchlist", () => ({
  getWatchlistItems: m.getItems,
  getWatchlistGroups: m.getGroups,
  getWatchlistTags: m.getTags,
  updateWatchlistItem: m.updateItem,
  deleteWatchlistItem: m.deleteItem,
  removeItemFromGroup: m.removeItemFromGroup,
  addItemToGroup: m.addItemToGroup
}));
vi.mock("element-plus", () => ({
  ElMessage: {
    success: m.success,
    warning: m.warning,
    error: m.error
  },
  ElMessageBox: { confirm: m.confirm }
}));
vi.mock("@/utils/localforage", () => ({
  localForage: () => ({ getItem: vi.fn(), setItem: vi.fn() })
}));

function makeToolbar(): WatchlistToolbarState {
  return {
    searchKeyword: ref(""),
    currentView: ref("all"),
    selectedAssetTypes: ref<string[]>([]),
    batchMode: ref(false),
    selectedItems: ref<WatchlistItem[]>([]),
    batchMoveGroupId: ref(undefined)
  };
}

/** 行 fixture：只给判定用到的字段 */
function row(overrides: Partial<WatchlistItem> = {}): WatchlistItem {
  return { id: 1, symbol: "600519", ...overrides } as WatchlistItem;
}

function flush() {
  return new Promise(resolve => setTimeout(resolve, 0));
}

/** **页请求**次数（`fields=lite` 是全量请求，不算「刷新一次」） */
function pageFetches(): number {
  return m.getItems.mock.calls.filter(
    ([params]) => (params as { fields?: string } | undefined)?.fields !== "lite"
  ).length;
}

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
  m.getItems.mockResolvedValue({ data: [], total: 0 });
});

/** 子域实例（不经过父级）：用来证明它自己不会发起列表请求 */
function setupRowActions(toolbar = makeToolbar()) {
  const groups = useWatchlistGroups();
  const rowActions = useWatchlistRowActions(
    {
      activeCustomGroupId: groups.activeCustomGroupId,
      currentIsCustom: groups.currentIsCustom
    },
    {
      batchMode: toolbar.batchMode,
      selectedItems: toolbar.selectedItems,
      batchMoveGroupId: toolbar.batchMoveGroupId
    }
  );
  return { rowActions, toolbar, groups };
}

describe("子域只报「是否已写库」，不自己刷新", () => {
  it("togglePin 成功 → true，且一个列表请求都不发", async () => {
    const { rowActions } = setupRowActions();
    m.updateItem.mockResolvedValue(undefined);

    await expect(rowActions.togglePin(row({ is_pinned: false }))).resolves.toBe(
      true
    );
    expect(m.updateItem).toHaveBeenCalledWith(1, { is_pinned: true });
    expect(pageFetches()).toBe(0);
  });

  it("togglePin 虚拟行（id=null）→ false，连写请求都不发", async () => {
    const { rowActions } = setupRowActions();

    await expect(
      rowActions.togglePin(row({ id: null as never }))
    ).resolves.toBe(false);
    expect(m.updateItem).not.toHaveBeenCalled();
    expect(pageFetches()).toBe(0);
  });

  it("togglePin 请求失败 → false（不谎报成功）", async () => {
    const { rowActions } = setupRowActions();
    m.updateItem.mockRejectedValue(new Error("boom"));

    await expect(rowActions.togglePin(row())).resolves.toBe(false);
    expect(m.error).toHaveBeenCalled();
    expect(pageFetches()).toBe(0);
  });

  it("toggleFavorite 成功 → true", async () => {
    const { rowActions } = setupRowActions();
    m.updateItem.mockResolvedValue(undefined);

    await expect(
      rowActions.toggleFavorite(row({ favorite: false }))
    ).resolves.toBe(true);
    expect(m.updateItem).toHaveBeenCalledWith(1, { favorite: true });
    expect(pageFetches()).toBe(0);
  });

  it("executeRemove 彻底删除成功 → true；持仓行被闸门拦下 → false 且不发删除", async () => {
    const { rowActions } = setupRowActions();
    m.deleteItem.mockResolvedValue(undefined);

    rowActions.confirmRemove(row({ status: "ACTIVE" }));
    expect(rowActions.removeDialogVisible.value).toBe(true);
    // 非自定义分组 ⇒ 默认「彻底删除」
    expect(rowActions.removeScope.value).toBe("all");
    await expect(rowActions.executeRemove()).resolves.toBe(true);
    expect(m.deleteItem).toHaveBeenCalledWith(1);
    expect(rowActions.removeDialogVisible.value).toBe(false);
    expect(pageFetches()).toBe(0);

    m.deleteItem.mockClear();
    rowActions.confirmRemove(row({ status: "HOLDING" }));
    await expect(rowActions.executeRemove()).resolves.toBe(false);
    expect(m.deleteItem).not.toHaveBeenCalled();
    expect(m.warning).toHaveBeenCalled();
  });

  it("batchDelete：选中全为持仓 → false 且不弹确认框", async () => {
    const toolbar = makeToolbar();
    const { rowActions } = setupRowActions(toolbar);
    toolbar.selectedItems.value = [row({ status: "HOLDING" })];

    await expect(rowActions.batchDelete()).resolves.toBe(false);
    expect(m.confirm).not.toHaveBeenCalled();
    expect(m.deleteItem).not.toHaveBeenCalled();
  });

  it("batchDelete 确认成功 → true，退出批量态并清空选择", async () => {
    const toolbar = makeToolbar();
    const { rowActions } = setupRowActions(toolbar);
    toolbar.batchMode.value = true;
    toolbar.selectedItems.value = [row({ id: 7, status: "ACTIVE" })];
    m.confirm.mockResolvedValue(undefined);
    m.deleteItem.mockResolvedValue(undefined);

    await expect(rowActions.batchDelete()).resolves.toBe(true);
    expect(m.deleteItem).toHaveBeenCalledWith(7);
    expect(toolbar.batchMode.value).toBe(false);
    expect(toolbar.selectedItems.value).toEqual([]);
    expect(pageFetches()).toBe(0);
  });

  it("batchDelete 用户取消 → false，批量态保持（用户还在挑）", async () => {
    const toolbar = makeToolbar();
    const { rowActions } = setupRowActions(toolbar);
    toolbar.batchMode.value = true;
    toolbar.selectedItems.value = [row({ id: 7, status: "ACTIVE" })];
    m.confirm.mockRejectedValue(new Error("cancel"));

    await expect(rowActions.batchDelete()).resolves.toBe(false);
    expect(m.deleteItem).not.toHaveBeenCalled();
    expect(toolbar.batchMode.value).toBe(true);
  });

  it("batchMoveToGroup 成功 → true，清空目标分组与选择", async () => {
    const toolbar = makeToolbar();
    const { rowActions } = setupRowActions(toolbar);
    toolbar.batchMode.value = true;
    toolbar.batchMoveGroupId.value = 3;
    toolbar.selectedItems.value = [row({ id: 5 }), row({ id: 6 })];
    m.addItemToGroup.mockResolvedValue(undefined);

    await expect(rowActions.batchMoveToGroup(3)).resolves.toBe(true);
    expect(m.addItemToGroup).toHaveBeenCalledTimes(2);
    expect(toolbar.batchMoveGroupId.value).toBeUndefined();
    expect(toolbar.batchMode.value).toBe(false);
    expect(toolbar.selectedItems.value).toEqual([]);
    expect(pageFetches()).toBe(0);
  });

  it("batchMoveToGroup 无目标分组 → false", async () => {
    const toolbar = makeToolbar();
    const { rowActions } = setupRowActions(toolbar);
    toolbar.selectedItems.value = [row({ id: 5 })];

    await expect(rowActions.batchMoveToGroup(undefined)).resolves.toBe(false);
    expect(m.addItemToGroup).not.toHaveBeenCalled();
  });
});

describe("父级 wrapper：每个操作恰好刷新一次", () => {
  /** 构造父级 composable（每次新建，避免用例间状态残留） */
  function setupData() {
    const groups = useWatchlistGroups();
    const tags = useWatchlistTags();
    const toolbar = makeToolbar();
    const data = useWatchlistData(groups, tags, toolbar);
    return { data, toolbar, groups };
  }

  it("handleTogglePin → 恰好一次刷新（不是两次）", async () => {
    const { data } = setupData();
    m.updateItem.mockResolvedValue(undefined);

    await data.handleTogglePin(row({ is_pinned: false }));
    await flush();

    expect(m.updateItem).toHaveBeenCalled();
    expect(pageFetches()).toBe(1);
  });

  it("executeRemove → 恰好一次刷新（回归：曾漏接 wrapper，移除后列表不动）", async () => {
    const { data } = setupData();
    m.deleteItem.mockResolvedValue(undefined);

    data.confirmRemove(row({ status: "ACTIVE" }));
    await data.executeRemove();
    await flush();

    expect(m.deleteItem).toHaveBeenCalled();
    expect(pageFetches()).toBe(1);
  });

  it("handleToggleFavorite → 恰好一次刷新", async () => {
    const { data } = setupData();
    m.updateItem.mockResolvedValue(undefined);

    await data.handleToggleFavorite(row({ favorite: true }));
    await flush();

    expect(pageFetches()).toBe(1);
  });

  it("handleBatchDelete → 恰好一次刷新", async () => {
    const { data, toolbar } = setupData();
    toolbar.selectedItems.value = [row({ id: 9, status: "ACTIVE" })];
    m.confirm.mockResolvedValue(undefined);
    m.deleteItem.mockResolvedValue(undefined);

    await data.handleBatchDelete();
    await flush();

    expect(pageFetches()).toBe(1);
  });

  it("handleBatchMoveToGroup → 恰好一次刷新", async () => {
    const { data, toolbar } = setupData();
    toolbar.selectedItems.value = [row({ id: 9 })];
    m.addItemToGroup.mockResolvedValue(undefined);

    await data.handleBatchMoveToGroup(4);
    await flush();

    expect(pageFetches()).toBe(1);
  });

  it("操作未写库（持仓闸门 / 无选中）→ 一次都不刷新", async () => {
    const { data } = setupData();
    data.confirmRemove(row({ status: "HOLDING" }));
    await data.executeRemove();
    await flush();

    await data.handleBatchDelete(); // 无选中项
    await flush();

    expect(pageFetches()).toBe(0);
  });

  it("对外契约不变：页面与 useWatchlistTable 用到的名字都还在", () => {
    const { data } = setupData();
    for (const key of [
      "handleTogglePin",
      "handleToggleFavorite",
      "confirmRemove",
      "executeRemove",
      "removingItem",
      "removeScope",
      "removeDialogVisible",
      "handleSelectionChange",
      "handleBatchDelete",
      "handleBatchMoveToGroup"
    ]) {
      expect(data, `对外返回值缺 ${key}`).toHaveProperty(key);
    }
  });
});

describe("结构：子域不得持有刷新能力（防回潮）", () => {
  const SRC = join(process.cwd(), "src");

  /** 剥注释后再匹配：本仓踩过「注释里写着名字，守卫拿它当已登记」的假绿灯（#2453） */
  function stripComments(source: string): string {
    return source
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "")
      .replace(/\s\/\/[^\n"']*$/gm, "");
  }

  const rowActionsCode = stripComments(
    readFileSync(
      join(SRC, "composables/watchlist/useWatchlistRowActions.ts"),
      "utf-8"
    )
  );

  it("子域里没有 fetchData / getWatchlistItems（刷新入口不落地）", () => {
    expect(rowActionsCode).not.toContain("fetchData");
    expect(rowActionsCode).not.toContain("getWatchlistItems");
  });

  it("子域不反向 import 父 composable", () => {
    expect(rowActionsCode).not.toContain(
      'from "@/composables/useWatchlistData"'
    );
    expect(rowActionsCode).toContain('from "@/api/watchlist"');
  });

  it("五个写操作都返回 Promise<boolean>（信号形态，不是副作用）", () => {
    for (const fn of [
      "togglePin",
      "toggleFavorite",
      "executeRemove",
      "batchDelete",
      "batchMoveToGroup"
    ]) {
      expect(rowActionsCode, `${fn} 的返回类型必须是 Promise<boolean>`).toMatch(
        new RegExp(`function ${fn}\\b[^)]*\\)\\s*:\\s*Promise<boolean>`)
      );
    }
  });

  it("父文件不再直接调用四个写接口（写操作已全部下沉）", () => {
    const parentCode = stripComments(
      readFileSync(join(SRC, "composables/useWatchlistData.ts"), "utf-8")
    );
    for (const api of [
      "updateWatchlistItem",
      "deleteWatchlistItem",
      "removeItemFromGroup",
      "addItemToGroup"
    ]) {
      expect(parentCode, `父文件仍直接调用 ${api}`).not.toContain(api);
    }
  });
});
