/**
 * #2922 防回潮守卫：三个巨型 composable 的**状态归属**不许再糊回去。
 *
 * ## 为什么用「结构判据」而不是行数门禁
 *
 * 行数只是症状。真正的病是「同一份状态被两处声明 / 一个文件同时持有本页派生与
 * 跨挂载共享两种东西」。行数门禁可以靠把注释搬来搬去糊过去，归属判据不行：
 *
 * | 判据 | 编不过的实现长什么样 |
 * |---|---|
 * | W1 | `useWatchlistData` 顶层又冒出 `const pageSize = ref(...)`（模块级单例回潮） |
 * | W2 | 另开一处读写 `watchlist-page-size` / `watchlist-sort-metrics`（偏好像素分裂） |
 * | N1 | `usePageNav` 自己又写一份滚动度量（几何层被绕过） |
 * | L1 | `useLedgerDetail` 又自己声明 `summaryData` / `portfolioList`（子域被绕过） |
 *
 * ⚠️ 判据一律**先剥注释**再匹配：本仓踩过「注释里写着名字，守卫就拿它当已登记」
 * 的假绿灯（#2453）。注释保留在文件头是本项目的习惯，不能因为它而让守卫失明。
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

/** 去掉块注释与行注释，只留代码（字符串字面量里的 `//` 不在本仓这些文件里出现） */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "")
    .replace(/\s\/\/[^\n"']*$/gm, "");
}

function readCode(relPath: string): string {
  return stripComments(readFileSync(join(SRC, relPath), "utf-8"));
}

/** 递归收集 src 下的 .ts / .vue，返回相对路径 */
function walk(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "__tests__" || entry === "node_modules") continue;
      walk(full, acc);
    } else if (/\.(ts|vue)$/.test(entry)) {
      acc.push(relative(SRC, full).replace(/\\/g, "/"));
    }
  }
  return acc;
}

describe("W1 useWatchlistData 不得再持有模块级共享单例", () => {
  it("剥注释后，顶层没有 `const X = ref(...)` 形式的模块级状态", () => {
    const code = readCode("composables/useWatchlistData.ts");
    const moduleLevelRefs = code
      .split("\n")
      .filter(line => /^const \w+ = (ref|reactive|shallowRef)[<(]/.test(line));

    // 跨挂载点共享的偏好只能由 store 声明；本文件里出现的 ref 必须都在函数体内（缩进）
    expect(moduleLevelRefs).toEqual([]);
  });

  it("composable 仍对外暴露同一份 API（拆分不改契约）", () => {
    const code = readCode("composables/useWatchlistData.ts");
    for (const key of [
      "pageSize",
      "pageSizeOptions",
      "initPageSize",
      "setPageSize",
      "sortMetrics",
      "sortMetricOf",
      "setSortMetric"
    ]) {
      expect(code, `useWatchlistData 返回值缺 ${key}`).toContain(key);
    }
  });
});

describe("W2 本地偏好的存储键只有一个所有者（store）", () => {
  const KEYS = [
    "watchlist-page-size",
    "watchlist-sort-metrics",
    "watchlist-day-pnl-metric"
  ];

  // 全量扫描 src（1600+ 文件）是 IO 密集的：并发跑单测时 5s 默认超时会被
  // 其他 worker 抢 IO 抢掉（与 echartsRegistry 同类，属环境噪声而非判据失效），
  // 故显式放宽——判据本身仍是「所有者唯一」。
  it(
    "三个存储键只在 store/modules/watchlistPrefs.ts 里出现",
    { timeout: 30000 },
    () => {
      const files = walk(SRC);
      expect(files.length).toBeGreaterThan(100); // 扫描本身必须有效，防「空目录假绿灯」

      for (const key of KEYS) {
        const owners = files.filter(f =>
          readFileSync(join(SRC, f), "utf-8").includes(key)
        );
        expect(owners, `${key} 的所有者应唯一`).toEqual([
          "store/modules/watchlistPrefs.ts"
        ]);
      }
    }
  );
});

describe("N1 滚动几何只在 scrollGeometry.ts 里实现", () => {
  const GEOMETRY_MARKERS = [
    "getComputedStyle(node).overflowY",
    "document.documentElement.scrollHeight"
  ];

  it("scrollGeometry.ts 保有度量实现", () => {
    const code = readCode("composables/pageNav/scrollGeometry.ts");
    for (const marker of GEOMETRY_MARKERS) {
      expect(code, `几何层缺判据 ${marker}`).toContain(marker);
    }
    expect(code).toContain("export function resetScrollerCache");
  });

  it("usePageNav 不再自带度量实现，也不再持有容器缓存", () => {
    const code = readCode("composables/usePageNav.ts");
    for (const marker of GEOMETRY_MARKERS) {
      expect(code, `usePageNav 又自己算几何：${marker}`).not.toContain(marker);
    }
    expect(code).not.toContain("cachedScroller");
    // 但必须真的用几何层（防「删了实现、守卫仍绿」）
    expect(code).toContain('from "@/composables/pageNav/scrollGeometry"');
  });
});

describe("L1 账户详情的概览 / 组合状态只由子域声明", () => {
  it("useLedgerDetail 不再自己声明这三组状态", () => {
    const code = readCode("composables/useLedgerDetail.ts");
    for (const decl of [
      "const summaryData = ref",
      "const moneyFundData = ref",
      "const portfolioList = ref",
      "const portfoliosLoaded = ref",
      "const ledgersLoaded = ref"
    ]) {
      expect(code, `useLedgerDetail 又自己声明：${decl}`).not.toContain(decl);
    }
    expect(code).toContain("useLedgerOverview(");
    expect(code).toContain("useLedgerPositionPortfolio(");
  });

  it("子域各自收敛（避免两边都改、或都没改）", () => {
    expect(readCode("composables/ledger/useLedgerOverview.ts")).toContain(
      "const summaryData = ref"
    );
    expect(
      readCode("composables/ledger/useLedgerPositionPortfolio.ts")
    ).toContain("const portfolioList = ref");
  });
});
