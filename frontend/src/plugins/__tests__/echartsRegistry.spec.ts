/**
 * ECharts 按需注册守卫（#2453）。
 *
 * ## 为什么需要这张网
 *
 * 本项目走 `echarts/core` 按需引入（`src/plugins/echarts.ts`）。漏注册的后果**不是报错
 * 中断，而是「静默不画」**：控制台只有一行 `Series scatter is used but not imported`，
 * 页面其余部分照常渲染，唯独那一层图形永远不出现——用户看到的是「功能是坏的」，
 * 开发者看到的是「代码写了呀」。#2453 的三个系列（买卖点 scatter / 清仓轮次 markLine /
 * 场内 K 线 candlestick）就是这么**上了线但从没画出来过**。
 *
 * 静默失灵的东西必须有红灯，而 ECharts 的报错只在运行时控制台里——CI 看不见。
 * 所以这里把「用了什么」与「注册了什么」的对账搬进单测：
 *
 * - **用了什么**：扫描 `src/` 下所有 `.vue/.ts` 里的 series `type: "…"` 字面量与
 *   `markLine / markArea / markPoint / dataZoom / toolbox / visualMap` 特性关键字；
 * - **注册了什么**：读 `src/plugins/echarts.ts` 源码，看对应的 Chart/Component 导出名
 *   是否出现在 `use([...])` 里。
 *
 * 判据是**客观存在性检查**（与 PR 四问守卫同一设计哲学）：只保证「新增特性时有人被迫
 * 回来登记」，不判断登记得对不对。
 *
 * ## 已知的粗筛边界（刻意放宽，不追求精确）
 *
 * `type: "line"` 这类字面量在非 ECharts 上下文也可能出现，粗筛无法区分。误报的方向是
 * 「要求注册一个其实没用的图」——那是**可见的**多余登记，评审时一眼能看出，远好于
 * 漏报的静默失灵。所以宁可误报，不收窄到漏报。
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

/** series type 字面量 → echarts/charts 里必须登记的导出名 */
const SERIES_REQUIREMENTS: Record<string, string> = {
  line: "LineChart",
  bar: "BarChart",
  pie: "PieChart",
  sankey: "SankeyChart",
  candlestick: "CandlestickChart",
  scatter: "ScatterChart",
  radar: "RadarChart",
  graph: "GraphChart",
  heatmap: "HeatmapChart",
  tree: "TreeChart",
  treemap: "TreemapChart",
  sunburst: "SunburstChart",
  boxplot: "BoxplotChart",
  funnel: "FunnelChart",
  gauge: "GaugeChart",
  map: "MapChart",
  parallel: "ParallelChart",
  lines: "LinesChart",
  pictorialBar: "PictorialBarChart",
  themeRiver: "ThemeRiverChart"
};

/** 特性关键字 → echarts/components 里必须登记的导出名 */
const COMPONENT_REQUIREMENTS: Record<string, string> = {
  markLine: "MarkLineComponent",
  markArea: "MarkAreaComponent",
  markPoint: "MarkPointComponent",
  dataZoom: "DataZoomComponent",
  toolbox: "ToolboxComponent",
  visualMap: "VisualMapComponent"
};

const SRC_ROOT = join(__dirname, "..", "..");
const PLUGIN_FILE = join(SRC_ROOT, "plugins", "echarts.ts");

/**
 * 从 `echarts.ts` 里抽出**真正登记**的导出名集合。
 *
 * ## 为什么要剥注释（别改成全文件 `includes`）
 *
 * 初版直接 `pluginSource.includes("ScatterChart")`，反向验证立刻戳穿：把注册项删掉后
 * 测试**依然全绿**——因为文件头那段复盘注释里正好写着
 * `//   scatter ×2（详情页走势买卖点）→ ScatterChart（本次补）`，
 * 注释里的名字满足了 `includes`。
 *
 * 这就是「静默失灵的东西必须有红灯」的反面：守卫自己也静默失灵了，而且是在**修复
 * #2453 的同一个文件上**失灵。所以这里必须只认代码：
 *
 *   1. 去掉行注释（`//…`）与块注释（`/* … *\/`）——注释里的名字不是登记；
 *   2. 取 `use([…])` 的数组体——import 语句与别处的提及都不算登记；
 *   3. 抽出数组体里的标识符。
 *
 * 前两条合起来才是「注册」的完整语义：只写在注释里 = 没注册。
 */
function registeredExports(): Set<string> {
  const raw = readFileSync(PLUGIN_FILE, "utf-8");
  // 先剥注释，再取use([...]) 的数组体
  const code = raw.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  const m = code.match(/\buse\(\s*\[([\s\S]*?)\]\s*\)/);
  if (!m) {
    // 找不到 use([...]) 就当成「一个都没登记」——此时上面两条断言必然转红，
    // 比静默放行安全（守卫失效必须是红灯，不是绿灯）。
    return new Set();
  }
  return new Set(
    m[1]
      .split(",")
      .map(s => s.trim())
      .filter(s => /^[A-Za-z_$][\w$]*$/.test(s))
  );
}

/** 递归收集 src 下的 .vue / .ts（排除本测试目录与 echarts.ts 自身） */
function collectFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "__tests__") continue;
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) collectFiles(p, out);
    else if (/\.(vue|ts)$/.test(name) && p !== PLUGIN_FILE) out.push(p);
  }
  return out;
}

const usedFiles = collectFiles(SRC_ROOT);

function usedFeatures(keywords: string[]): Map<string, string[]> {
  const hits = new Map<string, string[]>();
  for (const f of usedFiles) {
    const text = readFileSync(f, "utf-8");
    for (const kw of keywords) {
      if (text.includes(kw)) {
        const rel = relative(SRC_ROOT, f).replace(/\\/g, "/");
        if (!hits.has(kw)) hits.set(kw, []);
        hits.get(kw)!.push(rel);
      }
    }
  }
  return hits;
}

/** series `type: "xxx"`（含单引号写法）；`type:` 前允许任意空白 */
function usedSeriesTypes(): Map<string, string[]> {
  const hits = new Map<string, string[]>();
  for (const f of usedFiles) {
    const text = readFileSync(f, "utf-8");
    for (const type of Object.keys(SERIES_REQUIREMENTS)) {
      const re = new RegExp(`type:\\s*["']${type}["']`);
      if (re.test(text)) {
        const rel = relative(SRC_ROOT, f).replace(/\\/g, "/");
        if (!hits.has(type)) hits.set(type, []);
        hits.get(type)!.push(rel);
      }
    }
  }
  return hits;
}

describe("ECharts 按需注册对账（#2453）", () => {
  it("守卫自身有效：能从 plugins/echarts.ts 里抽出真实登记项", () => {
    // 防「registeredExports 返回空集→ 断言恰好也找不到 used」这种双向假绿灯。
    // 判据是客观存在性：登记项非空、且能定位到具体的 use([...]) 数组体。
    const reg = registeredExports();
    expect(reg.size).toBeGreaterThan(0);
    // 反例说明：初版对全文件做 includes，删掉注册项后因为注释里写着名字而依然全绿。
    // 登记项必须来自代码，而不是来自注释——这里钉住这条语义。
    expect(reg.has("CanvasRenderer")).toBe(true);
  });

  it("项目里用到的每种 series 都已在 plugins/echarts.ts 登记", () => {
    const used = usedSeriesTypes();
    expect(used.size).toBeGreaterThan(0); // 扫描本身必须有效，防「空目录假绿灯」
    const reg = registeredExports();
    const missing: string[] = [];
    for (const [type, files] of used) {
      const exportName = SERIES_REQUIREMENTS[type];
      if (!reg.has(exportName)) {
        missing.push(`${type} → ${exportName}（用于 ${files.join(", ")}）`);
      }
    }
    expect(missing).toEqual([]);
  });

  it("项目里用到的每个 ECharts 组件特性都已在 plugins/echarts.ts 登记", () => {
    const used = usedFeatures(Object.keys(COMPONENT_REQUIREMENTS));
    const reg = registeredExports();
    const missing: string[] = [];
    for (const [kw, files] of used) {
      const exportName = COMPONENT_REQUIREMENTS[kw];
      if (!reg.has(exportName)) {
        missing.push(`${kw} → ${exportName}（用于 ${files.join(", ")}）`);
      }
    }
    expect(missing).toEqual([]);
  });

  it("renderer 至少注册一个（没有 renderer 图一张都画不出来）", () => {
    expect(registeredExports().has("CanvasRenderer")).toBe(true);
  });
});
