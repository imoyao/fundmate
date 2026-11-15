/**
 * 持仓结构面板「视角由账户类型决定」守卫（#2739）。
 *
 * 背景：账户是基金账户还是股票账户，由 `ledgers.ledger_type` 确定（owner
 * 裁定）。因此持仓结构里的「股票 / 基金」双视角切换对账户级**没有价值**：
 * 证券账户只该看股票、基金账户只该看基金，银行账户除现金外按基金视角。
 * 组合级 / 家庭级跨类型账户混合，切换才有意义 ⇒ 保留。
 *
 * 本守卫钉住三件「改回去也没人会发现」的事：
 *
 * 1. **账户级不渲染切换控件**（`v-if="showSwitcher"` + 由 `data.view` 决定）——
 *    否则用户面对一个毫无意义的开关；
 * 2. **组合/家庭级仍保留切换** —— 误伤已上线的组合页比不做更糟；
 * 3. **主榜取固定视角**，不是取用户上次选的那个 —— 否则账户级仍会显示基金榜。
 *
 * 判据纪律（本仓「守门通过 ≠ 守门有效」）：断言**模板绑定与计算属性实现**，
 * 不认标识符出现过。组合级保留切换这条尤其要断言 `view === null` 分支存在，
 * 否则把 `showSwitcher` 写成恒 false 也能过「账户级不显示」那一条。
 *
 * 为什么用源码断言而不是挂载组件：本仓 vitest 跑在 node 环境、不挂载组件
 * （`vitest.config.ts`），既有同类守卫（`cashLikeCardGuard.spec.ts` 等）即此范式。
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

const panel = read("../index.vue");
const api = read("../../../api/summary.ts");

describe("持仓结构视角由账户类型决定（#2739）", () => {
  it("切换控件的出现由 showSwitcher 决定，而不是恒显示", () => {
    // 控件必须挂在 v-if 上，否则账户级也会出开关
    expect(panel).toMatch(/<SegmentedControl[\s\S]{0,120}v-if="showSwitcher"/);
    // showSwitcher 必须由「后端给的固定视角是否为 null」推导
    expect(panel).toMatch(
      /const showSwitcher = computed\(\(\) => fixedView\.value === null\)/
    );
  });

  it("固定视角取自后端 data.view，不在前端另算一套", () => {
    // 前端不得自己按 asset_type / 账户名猜视角 —— 那是把口径复制一份
    expect(panel).toMatch(
      /const fixedView = computed[\s\S]{0,120}data\.value\?\.view/
    );
    expect(panel).not.toMatch(/ledger_type\s*===\s*["']stock["']/);
  });

  it("主榜取固定视角（不是用户上次选的那个）", () => {
    // 少了这行 → 账户级仍显示用户先前切到的基金榜
    expect(panel).toMatch(
      /groups\?\.\[fixedView\.value \?\? activeClass\.value\]/
    );
  });

  it("组合/家庭级保留切换（view 为 null 分支必须真的驱动行为）", () => {
    // 后端在组合/家庭级返回 view=null ⇒ 前端仍能切
    expect(api).toMatch(/view:\s*"stock"\s*\|\s*"fund"\s*\|\s*null/);
    // 且面板确实按 null 走了「保留切换」的分支。
    // ⚠️ 只断言 "fixedView.value === null" 字样存在是不够的：
    // 把 showSwitcher 写成恒 false（组合页被误伤）也能通过那条字面断言。
    // 故这里断言**该字样出现在 showSwitcher 的定义里**。
    expect(panel).toMatch(
      /const showSwitcher = computed\(\(\) => fixedView\.value === null\)/
    );
  });

  it("口径说明写明视角已固定（否则用户无从判断数字含义）", () => {
    expect(panel).toContain("视角已按账户类型固定");
  });
});

describe("Top 榜只有一套渲染器、只有一个占比（2026-11-15 反馈）", () => {
  it("与穿透面板共用 RankBarList，不再手写表格", () => {
    // 同一个页面两块 Top 榜各写一套：条列表 vs 手写 <table>，同一个问题两种长相
    expect(panel).toContain(
      'import RankBarList from "@/components/RankBarList/index.vue"'
    );
    expect(panel).toMatch(/<RankBarList[^>]*:rows="groupRows"/);
    expect(panel).not.toContain('<table class="detail-table">');
  });

  it("逐行只有一个占比（占组合 / 占账户），组内占比只留在标题行", () => {
    // 反号的两列（占组合 5.6% / 占股票 8.6%）并排实测读不出区别，用户要求去掉一个
    expect(panel).not.toMatch(/pct\(row\.ratio_of_group\)/);
    expect(panel).toMatch(/pct\(row\.ratio_of_total\)/);
    // 组内集中度仍在标题行，且写明分母
    expect(panel).toMatch(/组内前 5 集中度[\s\S]{0,80}top5_ratio_of_group/);
  });

  it("标题行不再重复「占组合」的集中度（与逐行的占比重叠）", () => {
    // 原来这里是「组内前 5 集中度 34.4% · 占组合 22.4%」，
    // 后半个数与逐行的占组合列讲同一件事，只多一个数字要读。
    expect(panel).not.toContain("showTotalRatioCol");
    expect(panel).not.toMatch(/· 占\{\{ scopeUnit \}\}/);
  });
});
