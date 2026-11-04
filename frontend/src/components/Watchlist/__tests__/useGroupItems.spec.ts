import { beforeEach, describe, expect, it, vi } from "vitest";
import { ElMessage } from "element-plus";
import type { WatchlistItem, WatchlistGroup } from "@/api/watchlist";
import {
  addItemToGroup,
  getWatchlistItems,
  removeItemFromGroup
} from "@/api/watchlist";
import { useGroupItems } from "../useGroupItems";

vi.mock("@/api/watchlist", () => ({
  getWatchlistItems: vi.fn(),
  addItemToGroup: vi.fn(),
  removeItemFromGroup: vi.fn()
}));

// ElMessage 会往 document 上挂节点，测试环境是 node，直接替换成空实现
vi.mock("element-plus", () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() }
}));

/**
 * #980 拆分回归：分组抽屉的数据层。
 *
 * 锁三条行为（都是历史上真出过 bug 的地方）：
 * 1. 本组成员按 group_id 单独拉取 —— 与主列表同源（#1449 Bug 2）；
 * 2. 候选池排除「已在本组」与「无 id 的虚拟持仓行」；
 * 3. 增删走乐观更新并回调 onChanged，不整表重拉。
 */
const item = (over: Partial<WatchlistItem> = {}) =>
  ({
    id: 1,
    symbol: "000001",
    display_name: "华夏成长",
    asset_type: "fund",
    ...over
  }) as unknown as WatchlistItem;

const memberItem = item({ id: 1, symbol: "000001", display_name: "华夏成长" });
const otherItem = item({ id: 2, symbol: "600519", display_name: "贵州茅台" });
const virtualItem = item({ id: null, symbol: "V1", display_name: "虚拟持仓" });

const group = { id: 7, name: "核心仓" } as unknown as WatchlistGroup;

function mount(onChanged = vi.fn()) {
  return { ...useGroupItems(() => group, onChanged), onChanged };
}

beforeEach(() => {
  vi.mocked(getWatchlistItems).mockReset();
  vi.mocked(addItemToGroup).mockReset();
  vi.mocked(removeItemFromGroup).mockReset();

  vi.mocked(getWatchlistItems).mockImplementation(async params => {
    // 带 group_id 的调用 = 本组成员；不带 = 全量自选池
    if (params && "group_id" in params && params.group_id != null) {
      return { data: [memberItem], total: 1 } as any;
    }
    return { data: [memberItem, otherItem, virtualItem], total: 3 } as any;
  });
});

describe("useGroupItems：取数", () => {
  it("本组按 group_id 拉取，全量池不带分组过滤", async () => {
    const vm = mount();
    await vm.reload();

    expect(vi.mocked(getWatchlistItems)).toHaveBeenCalledWith({
      group_id: 7,
      page: 1,
      per_page: 200
    });
    expect(vi.mocked(getWatchlistItems)).toHaveBeenCalledWith({
      page: 1,
      per_page: 200
    });
    expect(vm.inGroup.value.map(i => i.id)).toEqual([1]);
  });

  it("候选池排除本组成员与无 id 的虚拟持仓行", async () => {
    const vm = mount();
    await vm.reload();

    expect(vm.candidates.value.map(i => i.id)).toEqual([2]);
  });

  it("搜索词同时过滤两栏（代码 / 名称 / 副标题）", async () => {
    const vm = mount();
    await vm.reload();

    vm.keyword.value = "茅台";
    expect(vm.inGroup.value).toHaveLength(0);
    expect(vm.candidates.value.map(i => i.id)).toEqual([2]);

    vm.keyword.value = "华夏";
    expect(vm.inGroup.value.map(i => i.id)).toEqual([1]);
    expect(vm.candidates.value).toHaveLength(0);
  });

  it("重新打开（reload）会清空搜索词", async () => {
    const vm = mount();
    await vm.reload();
    vm.keyword.value = "茅台";

    await vm.reload();
    expect(vm.keyword.value).toBe("");
    expect(vm.candidates.value.map(i => i.id)).toEqual([2]);
  });

  it("group 为 null 时本组为空，且不请求本组接口", async () => {
    const vm = useGroupItems(() => null, vi.fn());
    await vm.reload();

    expect(vm.inGroup.value).toHaveLength(0);
    expect(vi.mocked(getWatchlistItems)).not.toHaveBeenCalledWith(
      expect.objectContaining({ group_id: expect.anything() })
    );
  });
});

describe("useGroupItems：增删", () => {
  it("加入分组：调接口 + 乐观更新候选池 + 回调 onChanged", async () => {
    vi.mocked(addItemToGroup).mockResolvedValue({} as any);
    const vm = mount();
    await vm.reload();

    await vm.addItem(otherItem);

    expect(vi.mocked(addItemToGroup)).toHaveBeenCalledWith(2, 7);
    expect(vm.inGroup.value.map(i => i.id)).toEqual([1, 2]);
    expect(vm.candidates.value).toHaveLength(0);
    expect(vm.onChanged).toHaveBeenCalledTimes(1);
  });

  it("同一产品重复加入不会在本组里出现两次", async () => {
    vi.mocked(addItemToGroup).mockResolvedValue({} as any);
    const vm = mount();
    await vm.reload();

    await vm.addItem(memberItem);
    expect(vm.inGroup.value.map(i => i.id)).toEqual([1]);
  });

  it("移出分组：本组与候选池同步，并回调 onChanged", async () => {
    vi.mocked(removeItemFromGroup).mockResolvedValue({} as any);
    const vm = mount();
    await vm.reload();

    await vm.removeItem(memberItem);

    expect(vi.mocked(removeItemFromGroup)).toHaveBeenCalledWith(1, 7);
    expect(vm.inGroup.value).toHaveLength(0);
    expect(vm.candidates.value.map(i => i.id)).toEqual([1, 2]);
    expect(vm.onChanged).toHaveBeenCalledTimes(1);
  });

  it("接口失败：不乐观更新，也不回调（避免父级刷新出不一致数据）", async () => {
    vi.mocked(addItemToGroup).mockRejectedValue(new Error("boom"));
    const vm = mount();
    await vm.reload();

    await vm.addItem(otherItem);

    expect(vm.inGroup.value.map(i => i.id)).toEqual([1]);
    expect(vm.onChanged).not.toHaveBeenCalled();
    expect(vi.mocked(ElMessage.error)).toHaveBeenCalledWith("添加失败，请重试");
  });
});
