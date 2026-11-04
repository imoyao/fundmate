/**
 * 类型快捷胶囊栏的派生规则（#2329 持仓收窄 / #2199 单选覆盖式切换）。
 *
 * ## 这个文件钉什么
 *
 * 1. **持仓分组收窄**：`manager` / `portfolio` 这类「不进 positions」的类型在
 *    持仓视图下永远筛不出东西，胶囊栏必须不露它们；而 `stock` / `fund` 是
 *    PINNED 常驻项，收窄不能把它们一并摘掉（#2329 用户实测的原始 bug 就是
 *    持仓分组下冒出了「基金经理」）。
 * 2. **高亮判据对「实际渲染的选项」求值**：若拿裸外露列表判，会出现「高亮了
 *    一个根本不渲染的胶囊」这种高亮与可见性对不上的状态。
 * 3. **单选覆盖式语义**：点非当前项 → 覆盖为该项；再点当前项 → 取消回「全部」；
 *    点「全部」→ 清空。「全部」的早退（本来就没筛就不刷新）由调用方守卫，
 *    本模型只负责「下一次的值是什么」。
 *
 * ⚠️ 为什么测 `../quickTypeModel` 而不是挂载 WatchlistFilterBar：vitest 环境是
 * node（无 DOM，且仓库未装 @vue/test-utils），而 .vue 那条依赖链会拖起
 * element-plus / router。按本目录既有约定（见 bondFormats.spec.ts 的说明），
 * 可测的派生逻辑一律留在纯模块里。
 */
import { describe, expect, it } from "vitest";

import {
  buildQuickTypeOptions,
  nextQuickSelection,
  resolveQuickActiveValue,
  QUICK_TYPE_ALL
} from "../quickTypeModel";

/** 模拟 assetTypeLabel：英文 key 直接借用即可，本测试不关心中文映射 */
const labelOf = (value: string) => value.toUpperCase();

const ALL_EXPOSED = ["stock", "fund", "etf", "bond", "manager", "portfolio"];

describe("buildQuickTypeOptions", () => {
  it("「全部」恒为首项，其后是外露类型（保持偏好顺序）", () => {
    const options = buildQuickTypeOptions(ALL_EXPOSED, false, labelOf);
    expect(options.map(o => o.value)).toEqual([
      QUICK_TYPE_ALL,
      "stock",
      "fund",
      "etf",
      "bond",
      "manager",
      "portfolio"
    ]);
    expect(options[0].label).toBe("全部");
    expect(options[1].label).toBe("STOCK");
  });

  it("持仓分组下收窄掉 manager / portfolio，但保留 stock / fund（PINNED）", () => {
    const options = buildQuickTypeOptions(ALL_EXPOSED, true, labelOf);
    expect(options.map(o => o.value)).toEqual([
      QUICK_TYPE_ALL,
      "stock",
      "fund",
      "etf",
      "bond"
    ]);
  });

  it("持仓分组下 index 保留、crypto / reverse_repo 剔除（HOLDING_ASSET_TYPES 口径）", () => {
    const options = buildQuickTypeOptions(
      ["crypto", "index", "reverse_repo"],
      true,
      labelOf
    );
    expect(options.map(o => o.value)).toEqual([QUICK_TYPE_ALL, "index"]);
  });

  it("外露列表为空时只剩「全部」", () => {
    expect(buildQuickTypeOptions([], true, labelOf)).toEqual([
      { label: "全部", value: QUICK_TYPE_ALL }
    ]);
  });

  it("不改入参（纯函数）", () => {
    const exposed = ["manager", "stock"];
    buildQuickTypeOptions(exposed, true, labelOf);
    expect(exposed).toEqual(["manager", "stock"]);
  });
});

describe("resolveQuickActiveValue", () => {
  const options = buildQuickTypeOptions(ALL_EXPOSED, false, labelOf);

  it("无类型筛选 → 高亮「全部」", () => {
    expect(resolveQuickActiveValue([], options)).toBe(QUICK_TYPE_ALL);
  });

  it("恰好单选一个可见类型 → 高亮它", () => {
    expect(resolveQuickActiveValue(["etf"], options)).toBe("etf");
  });

  it("多选 → 无高亮（组合态，看「筛选」角标）", () => {
    expect(resolveQuickActiveValue(["etf", "bond"], options)).toBe("");
  });

  it("单选了不渲染的类型 → 无高亮（高亮与可见性必须一致）", () => {
    const holdingOptions = buildQuickTypeOptions(ALL_EXPOSED, true, labelOf);
    expect(resolveQuickActiveValue(["manager"], holdingOptions)).toBe("");
  });
});

describe("nextQuickSelection", () => {
  it("点「全部」→ 清空类型筛选", () => {
    expect(nextQuickSelection(["etf", "bond"], QUICK_TYPE_ALL)).toEqual([]);
  });

  it("再点当前唯一项 → 取消回「全部」", () => {
    expect(nextQuickSelection(["etf"], "etf")).toEqual([]);
  });

  it("点其它类型 → 覆盖为唯一项（单选覆盖式，不是追加）", () => {
    expect(nextQuickSelection(["etf"], "bond")).toEqual(["bond"]);
  });

  it("多选态下点某类型 → 收敛为该单一项", () => {
    expect(nextQuickSelection(["etf", "bond"], "bond")).toEqual(["bond"]);
  });

  it("不改入参（纯函数）", () => {
    const selected = ["etf", "bond"];
    nextQuickSelection(selected, "stock");
    expect(selected).toEqual(["etf", "bond"]);
  });
});
