/**
 * #2329 自选页「持仓分组」语义回归。
 *
 * 缺陷本体：`index.vue` 挂载时把 `groups.fetchGroups()` 与 `data.fetchData()` 并发发出，
 * 而 `fetchParams` 对**系统分组**是查 `allGroups` 拿过滤语义的。挂载那一刻
 * `allGroups` 还是 `[]`，查不到就把分组条件**静默丢掉** ⇒ 首屏请求退化成「不带
 * status」⇒「持仓」Tab 高亮着、列表却是「全部」的内容（用户实测混进「基金经理」这类
 * 非持仓行）。且 `/watchlist` 是 `keepAlive: true`，切走再回来拿到的是被缓存的、
 * 已经污染的实例，`onMounted` 不再跑，污染持续整个缓存周期。
 *
 * 为什么只在持仓犯病（用户原话「是持仓分组特有的吗」）：自定义分组的 `group_id`
 * 由 key 字符串直接推导、不依赖 `allGroups`；系统分组「全部」的 filter 本就是空对象、
 * 无差异。只有 holding / watching / cleared / favorite 会中招，而默认落 holding。
 *
 * 本文件钉住三条契约：
 * ① 分组语义在列表请求里**真的带上**（正向断言主修复）；
 * ② `fetchGroups` 失败必须**有信号**（拿不到 ≠ 空的，别退化成看起来正常）；
 * ③ 「持仓分组允许哪些资产类型」只有一份真相源，三处消费方全部复用它。
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useWatchlistGroups } from "@/composables/useWatchlistGroups";
import { useWatchlistTags } from "@/composables/useWatchlistTags";
import {
  useWatchlistData,
  type WatchlistToolbarState
} from "@/composables/useWatchlistData";
import {
  HOLDING_ASSET_TYPES,
  HOLDING_ASSET_TYPE_SET,
  WATCHLIST_ASSET_TYPE_OPTIONS,
  narrowToHolding
} from "@/views/asset/watchlist/watchlistAssetTypes";
import type { WatchlistItem } from "@/api/watchlist";

const m = vi.hoisted(() => ({
  getItems: vi.fn(),
  getGroups: vi.fn(),
  getTags: vi.fn()
}));

vi.mock("@/api/watchlist", () => ({
  getWatchlistItems: m.getItems,
  getWatchlistGroups: m.getGroups,
  getWatchlistTags: m.getTags,
  updateWatchlistItem: vi.fn(),
  deleteWatchlistItem: vi.fn(),
  removeItemFromGroup: vi.fn(),
  addItemToGroup: vi.fn()
}));
// node 环境无 DOM：element-plus 只取到用到的两个消息入口，其余不加载
vi.mock("element-plus", () => ({
  ElMessage: { success: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn() }
}));
vi.mock("@/utils/localforage", () => ({
  localForage: () => ({ getItem: vi.fn(), setItem: vi.fn() })
}));

/** 最小 toolbar 状态（useWatchlistToolbar 的形状，纯 ref 集合无行为） */
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

/** 后端返回的分组清单：holding 有数据故展示，watching 无数据故被过滤掉 */
function groupPayload() {
  return {
    data: [
      {
        id: 1,
        key: "all",
        name: "全部",
        label: "全部",
        is_system: true,
        count: 183
      },
      {
        id: 2,
        key: "holding",
        name: "持仓",
        label: "持仓",
        is_system: true,
        count: 142
      },
      {
        id: 3,
        key: "watching",
        name: "观察中",
        label: "观察中",
        is_system: true,
        count: 0
      },
      {
        id: 9,
        key: "custom_9",
        name: "脚踏实地",
        is_system: false,
        count: 11
      }
    ]
  };
}

/** 读源文件（源码级守卫用；仓库根 = frontend/） */
function readSource(relPath: string): string {
  return readFileSync(
    join(process.cwd(), "src", ...relPath.split("/")),
    "utf-8"
  );
}

/**
 * 剥注释后再做源码级匹配。
 *
 * 为什么必须剥：#2329 的注释里**正面写着**旧写法 `["stock", "fund"]`（解释「此前此处
 * 写死两项」），不剥注释的话「不许回退为本地硬编码」这条守卫会被**它自己的注释**触发
 * ——守卫把自己写下的反例当成了被测代码（AGENTS.md §四：先 stripComments 再匹配）。
 *
 * 只剥块注释与「行首空白 + //」的行注释：后者不误伤 `https://` 这类 URL 里的 `//`。
 */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^[ \t]*\/\/.*$/gm, "");
}

beforeEach(() => {
  vi.clearAllMocks();
  m.getItems.mockResolvedValue({ data: [], total: 0 });
  m.getTags.mockResolvedValue({ data: [] });
  m.getGroups.mockResolvedValue(groupPayload());
});

describe("#2329 分组语义必须进入列表请求", () => {
  it("分组就绪后 fetchParams 带上 status=HOLDING（自定义分组则带 group_id）", async () => {
    const groups = useWatchlistGroups();
    const tags = useWatchlistTags();
    const data = useWatchlistData(groups, tags, makeToolbar());

    // 默认 activeGroup 即 holding；分组就绪后解析出 { status: "HOLDING" }
    await groups.fetchGroups();
    expect(data.fetchParams.value.status).toBe("HOLDING");

    // 自定义分组不依赖 allGroups，靠 key 字符串推导 group_id（对照组）
    groups.activeGroup.value = "custom_9";
    expect(data.fetchParams.value.group_id).toBe(9);
    expect(data.fetchParams.value.status).toBeUndefined();
  });

  it("fetchGroups 失败必须返回 false，不能与「分组为空」同形", async () => {
    const groups = useWatchlistGroups();
    m.getGroups.mockRejectedValue(new Error("network down"));

    await expect(groups.fetchGroups()).resolves.toBe(false);
    // allGroups 仍是空 —— 调用方据此回退 activeGroup 到「全部」，
    // 而不是让「持仓」Tab 高亮着展示未过滤的内容（见 index.vue onMounted）
    expect(groups.allGroups.value).toEqual([]);
    expect(groups.activeGroup.value).toBe("holding");
  });

  it("分组成功时返回 true；count=0 的系统分组按既有口径隐藏", async () => {
    const groups = useWatchlistGroups();

    await expect(groups.fetchGroups()).resolves.toBe(true);
    const keys = groups.allGroups.value.map(g => g.key);
    expect(keys).toContain("holding");
    expect(keys).toContain("custom_9");
    // watching count=0 被过滤（沿用既有「系统默认组无数据不展示」口径）
    expect(keys).not.toContain("watching");
  });
});

describe("#2329 持仓分组允许的资产类型只有一份真相源", () => {
  it("常量本身：含 5 种持仓类型，不含非持仓类型与非法 key", () => {
    expect([...HOLDING_ASSET_TYPES]).toEqual([
      "stock",
      "fund",
      "etf",
      "bond",
      "index"
    ]);
    // manager / portfolio 按后端定义「不进 positions」，持仓视图下筛不出东西
    expect(HOLDING_ASSET_TYPE_SET.has("manager")).toBe(false);
    expect(HOLDING_ASSET_TYPE_SET.has("portfolio")).toBe(false);
    // `convertible` 根本不是合法 asset_type（后端 bond 即可转债），
    // 旧 index.vue 的持仓集合里混着这个死项，本次一并清掉
    expect(HOLDING_ASSET_TYPE_SET.has("convertible")).toBe(false);
    expect(WATCHLIST_ASSET_TYPE_OPTIONS).not.toContain("convertible");
  });

  it("HOLDING_ASSET_TYPES 是合法类型池的子集（不会出现拼错的 key）", () => {
    for (const t of HOLDING_ASSET_TYPES) {
      expect(WATCHLIST_ASSET_TYPE_OPTIONS).toContain(t);
    }
  });

  it("narrowToHolding：剔除非持仓类型、保持顺序、不改入参", () => {
    // 用户实报的形态：偏好里配了「基金经理」，切到持仓分组后必须消失
    expect(narrowToHolding(["manager", "stock", "portfolio", "fund"])).toEqual([
      "stock",
      "fund"
    ]);
    // 全是非持仓类型 ⇒ 收成空集（不是原样放行）
    expect(narrowToHolding(["manager", "portfolio"])).toEqual([]);
    // 空入参 / 全持仓类型：原样返回
    expect(narrowToHolding([])).toEqual([]);
    expect(narrowToHolding(["etf", "bond", "index"])).toEqual([
      "etf",
      "bond",
      "index"
    ]);
    // 不改入参（调用方多处复用同一份 ref 派生态）
    const src = ["stock", "manager"];
    narrowToHolding(src);
    expect(src).toEqual(["stock", "manager"]);
    // 类型池全集收窄后与常量**同集合**（顺序随类型池原序，故比集合不比数组）
    expect(
      [...narrowToHolding([...WATCHLIST_ASSET_TYPE_OPTIONS])].sort()
    ).toEqual([...HOLDING_ASSET_TYPES].sort());
  });

  it("三处消费方真的**调用**共享函数，而非只 import（#2329 探针实测）", () => {
    // ⚠️ 前两版静态守卫写成「文件里出现常量名」，而**光一条 import 就能让它通过**，
    // 于是「导入了却没真正用」的回退完全咬不住（探针 P2/P3/P4 全 MISS）。
    // 现在统一断言**调用点**：`narrowToHolding(` 带括号，import 行匹配不到。
    const callers: Array<[string, string]> = [
      ["① index.vue 唯一写入点", "views/asset/watchlist/index.vue"],
      [
        "② FilterPanelBody 弹层可选集",
        "views/asset/watchlist/components/FilterPanelBody.vue"
      ],
      [
        "③ WatchlistFilterBar 快捷胶囊",
        "views/asset/watchlist/WatchlistFilterBar.vue"
      ]
    ];
    for (const [label, rel] of callers) {
      const src = stripComments(readSource(rel));
      expect(src, `${label} 未调用 narrowToHolding`).toContain(
        "narrowToHolding("
      );
      // 也不许回退成「本地再写一份类型清单」
      expect(src, `${label} 疑似回退为本地硬编码`).not.toMatch(
        /HOLDING_ALLOWED_TYPES|"stock"\s*,\s*"fund"/
      );
    }

    // index.vue 另有两处不得回退：非法 key convertible / 失效的分组回退值
    const index = stripComments(readSource("views/asset/watchlist/index.vue"));
    expect(index).not.toMatch(/"convertible"/);
    expect(index).toMatch(/await\s+groups\.fetchGroups\(\)/);
    expect(index).toMatch(/if\s*\(!groupsOk\)/);

    // FilterPanelBody 不得再持有本地 HOLDING_ALLOWED_TYPES
    expect(
      stripComments(
        readSource("views/asset/watchlist/components/FilterPanelBody.vue")
      )
    ).not.toMatch(/HOLDING_ALLOWED_TYPES/);
  });
});
