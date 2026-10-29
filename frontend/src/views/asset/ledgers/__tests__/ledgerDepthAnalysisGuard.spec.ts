/**
 * 账户详情页「持仓结构 / 持仓穿透」守卫（#2739）。
 *
 * 背景：账户详情页原先有一块写着「持仓集中度 / 行业分布规划中，敬请期待」的
 * 占位卡 —— 而这两项能力**早已上线**（#2617 / #870 + #2595）。占位卡是
 * 「把已存在的功能说成不存在」。本守卫钉住「占位卡不许回来」以及三件
 * 改回去也不会有人发现的事：
 *
 * 1. 深度分析真的接上了（不是占位、不是注释掉的一行）；
 * 2. **口径必须是本账户**：`PositionStructurePanel` / `PenetrationPanel` 在
 *    `ledgerId` 缺失时会退化成「全家庭」档 —— 页面标题写着账户详情，数据却
 *    是全家庭的，且面板口径标签还写着「账户」；
 * 3. 未归置持仓伪账户（路由参数是 "unclassified"，没有数字账户 id）不展示
 *    深度分析 —— 那里没有账户口径可言。
 *
 * 判据纪律（本仓「守门通过 ≠ 守门有效」）：断言**模板绑定**，不认标识符
 * 出现过；锚点与导航标签的对应关系按**集合相等**判（多一个少一个都红），
 * 免得「加了锚点忘了登记标签」这种只在 DEV 控制台告警、线上静默少一项的
 * 退化混过去。
 *
 * 为什么用源码断言而不是挂载组件：本仓 vitest 跑在 node 环境、不挂载组件
 * （`vitest.config.ts`），既有同类守卫（`cashLikeCardGuard.spec.ts` /
 * `allocationEditGuard.spec.ts`）即此范式。
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");

/** 账户详情页自己的文件（锚点扫描范围）。 */
const PAGE_FILES = [
  "../detail.vue",
  "../components/LedgerDetailOverview.vue",
  "../components/LedgerDepthAnalysis.vue",
  "../components/LedgerCashLikeCard.vue"
];

/** 区块标题所在处（含共享面板）——标签必须与这里的 SectionHeader 标题逐字一致。 */
const TITLE_FILES = [
  ...PAGE_FILES,
  "../../../../components/PositionStructurePanel/index.vue",
  "../../../../components/PenetrationPanel/index.vue",
  "../../../../components/PnlCalendar/index.vue",
  "../../../../components/PnlAttribution/index.vue",
  "../../../../components/CashFlowPanel/index.vue"
];

const pageSources = PAGE_FILES.map(read);
const titleSources = TITLE_FILES.map(read);

const detail = read("../detail.vue");
const overview = read("../components/LedgerDetailOverview.vue");
const depth = read("../components/LedgerDepthAnalysis.vue");
const cashLike = read("../components/LedgerCashLikeCard.vue");
const detailComposable = read("../../../../composables/useLedgerDetail.ts");

/** 本页全部 nav-* 锚点（模板里的 id= 与 anchor-id= 两种写法都算）。 */
function collectAnchors(): string[] {
  const out = new Set<string>();
  for (const src of pageSources) {
    for (const m of src.matchAll(/\bid="(nav-[a-z-]+)"/g)) out.add(m[1]);
    for (const m of src.matchAll(/\banchor-id="(nav-[a-z-]+)"/g)) out.add(m[1]);
  }
  return [...out].sort();
}

/** 去掉 HTML 注释：注释里提到「规划中」是**说明历史**，不是占位卡。 */
const stripComments = (src: string) => src.replace(/<!--[\s\S]*?-->/g, "");

/** 页内导航的「锚点 → 标签」映射（usePageNav 的 labels）。 */
function collectLabels(): Map<string, string> {
  const map = new Map<string, string>();
  const block = detail.match(/NAV_LABELS[^=]*=\s*\{([\s\S]*?)\n\};/);
  expect(block, "detail.vue 里找不到 NAV_LABELS 映射").not.toBeNull();
  for (const m of block![1].matchAll(/"(nav-[a-z-]+)":\s*"([^"]+)"/g)) {
    map.set(m[1], m[2]);
  }
  return map;
}

describe("账户详情页深度分析（#2739）", () => {
  it("占位卡不许回来：页内不再出现「规划中 / 敬请期待」", () => {
    // 全目录扫：占位文案换到兄弟文件里也算数（注释不算——注释里提这俩词是说明历史）
    const dir = fileURLToPath(new URL("../", import.meta.url));
    for (const file of readdirSync(dir)) {
      if (!file.endsWith(".vue")) continue;
      const src = stripComments(readFileSync(join(dir, file), "utf-8"));
      expect(src, `${file} 仍写着占位文案`).not.toContain("敬请期待");
      expect(src, `${file} 仍写着占位文案`).not.toContain("规划中");
    }
    expect(stripComments(overview)).not.toContain("敬请期待");
    expect(stripComments(overview)).not.toContain("规划中");
  });

  it("深度分析真的接上了（真开标签，不是注释掉的一行）", () => {
    // 组件存在但没人引用 = 用户看到的还是空白
    expect(overview).toMatch(/^\s*<LedgerDepthAnalysis\b/m);
    expect(overview).toMatch(
      /<LedgerDepthAnalysis[^>]*:ledger-id="p\.ledgerIdNum"/
    );
    // 两个面板都在
    expect(depth).toContain("PositionStructurePanel");
    expect(depth).toContain("PenetrationPanel");
  });

  it("口径必须是本账户：ledgerId 走有限数字，不靠 Number(字符串) 顶替", () => {
    // Number("unclassified") = NaN → 后端按「不传」处理 → 退化成全家庭档，
    // 而面板口径标签还写着「账户」。故必须走 Number.isFinite 过滤后的值。
    expect(detailComposable).toMatch(/const ledgerIdNum = computed/);
    expect(detailComposable).toContain("Number.isFinite(n)");
    // 页面里不得再出现「NaN 直传」的写法
    expect(overview).not.toMatch(/Number\(p\.ledgerId\)/);
    expect(detail).not.toMatch(/Number\(ledgerId\)/);
  });

  it("未归置持仓伪账户不展示深度分析（那里没有账户口径）", () => {
    // 少了 isUnclassified 判据 → 未归置页会展示别的账户（家庭级）的数据
    expect(overview).toMatch(
      /showDepthAnalysis = computed\([\s\S]{0,160}isUnclassified[\s\S]{0,160}ledgerIdNum/
    );
    expect(overview).toMatch(
      /<LedgerDepthAnalysis[\s\S]{0,120}v-if="showDepthAnalysis"/
    );
  });

  it("类现金锚点随整块消失（不留死链）", () => {
    // 本块整块不渲染时（类现金为 0 的普通基金账户）锚点必须跟着消失，
    // 否则导航里留一个点不动的「类现金」。
    expect(cashLike).toMatch(/<template v-if="visible">/);
    expect(cashLike).toContain(':id="anchorId"');
    expect(overview).toContain('anchor-id="nav-cash-like"');
  });

  it("页内导航：锚点与标签一一对应，标签与区块标题逐字一致", () => {
    const anchors = collectAnchors();
    const labels = collectLabels();

    expect(
      anchors.length,
      "本页没有 nav-* 锚点，页内导航是空的"
    ).toBeGreaterThan(1);
    // 多一个少一个都红：加了锚点忘登记标签 → 线上静默少一项
    expect([...anchors].sort()).toEqual([...labels.keys()].sort());
    for (const [id, label] of labels) {
      expect(
        titleSources.some(src => src.includes(`title="${label}"`)),
        `标签「${label}」（${id}）在区块标题里找不到同名字样`
      ).toBe(true);
    }
  });
});
