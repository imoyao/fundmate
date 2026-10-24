// scripts/guard_price_precision.mjs
// 守卫：**价格 / 净值展示必须走 `@/utils/pricePrecision` 契约**，不许各处自己写
// `.toFixed(n)`。
//
// ## 为什么需要这条守卫（起因）
//
// 用户实测反馈「基金详情页的净值应该保留 4 位，现在是 2 位」。查下来位数契约
// 早就存在（`pricePrecision`：基金 / ETF / 货币基金 4 位，其余 2 位），问题在于
// **它只被表格类组件遵守，其它出口各写各的**：
// - 走势图 y 轴压根没设 formatter，交给 echarts 默认 ⇒ 净值 4.8124 在轴上显示成
//   **4.8（只剩 1 位）**——这就是用户实际看到的那处；
// - 持仓「单位成本」写死 `:precision="4"`，股票持仓也跟着变 4 位；
// - tooltip 里写死 `v.toFixed(4)`，与轴各说一套。
//
// 写进文档的规则会被绕开（AGENTS.md 里已经有「价格走 pricePrecision」，仍然漂），
// 所以判据必须在 CI：**新增**的价格硬编码一律拦下。
//
// ## 判据形态（只做客观存在性检查）
//
// 扫 `frontend/src` 下 `.vue` / `.ts`，找「含价格 / 净值语义 且 调用 `.toFixed(`」
// 的行。命中项必须在 BASELINE 里；不在 ⇒ 判红，并提示改用 `pricePrecision` /
// `formatPrice`。**不判断位数写对没有**——那是代码审查的事，守卫只保证
// 「新增的每一处都被人看过一眼」。
//
// 已被规则自动排除、无需登记的：
// - `parseFloat(...)` 包裹：运算回写（算份额 / 反推价格），不是展示；
// - 金额 / 份额语义（amount / amt / qty / quantity / 份 / 万元）；
// - 百分比（`* 100` / `%`）；
// - 「量 × 价」形态（`q * price` 之类），结果是金额；
// - 契约自身 `utils/pricePrecision.ts`。
//
// ## 基线只减不增
//
// 存量 12 处冻结在 BASELINE（值目前都是对的，逐个改会牵动 e2e 文案断言，
// 单独立项收敛）。修掉一处就从 BASELINE 移除一处；脚本对「已消失却仍留在基线」
// 的项打印提示（不阻断）。

import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(ROOT, "frontend", "src");
const EXTS = new Set([".vue", ".ts", ".tsx", ".js", ".jsx"]);

/** 价格 / 净值语义：变量名或相邻中文标签 */
const PRICE_RE = /nav|price|净值|最新价|成本价|均价|收盘|close|unit_/i;
/** 运算回写（算份额 / 反推单价），非展示 */
const CALC_RE = /parseFloat\(/;
/** 金额 / 份额语义，不是单价 */
const NON_PRICE_RE = /amount|amt|qty|quantity|份|万元/i;
/** 百分比 */
const PERCENT_RE = /\*\s*100|%/;
/** 「量 × 价」= 金额 */
const MULT_AMOUNT_RE = /\*\s*(form\.)?price\b|price\s*\*|\*\s*nav\b/i;
/** 契约自身的实现，必须豁免 */
const CONTRACT_FILE = "utils/pricePrecision.ts";

const BASELINE = new Set([
  // 存量 9 处（2026-10-20 冻结，之后随 #980 拆分逐步下修）：值目前正确，改它会牵动 e2e 文案断言，
  // 单独立项收敛。修一处 → 从这里删一处。
  // 2026-10-24：转换表单三处净值（estimate.out / estimate.in / result.out）在拆
  // `ConversionForm.vue` 时改走 `formatPrice(v, "fund")`，已从基线移除（12 → 9）。
  'nav != null ? nav.toFixed(4) : "--"',
  'p.toNumber(row.price) != null ? Number(row.price).toFixed(4) : "--"',
  "? Number(form.price).toFixed(4)",
  "return d ? `${nav.toFixed(4)}（截至 ${d}）` : nav.toFixed(4);",
  "{{ profile.nav.toFixed(4) }}",
  "return row.nav == null ? DASH : row.nav.toFixed(4);",
  "{{ profile.unit_nav != null ? profile.unit_nav.toFixed(4) : DASH }}",
  '? perf.nav_per_10k.toFixed(4) + " 元"',
  '净值 {{ bias.close != null ? bias.close.toFixed(4) : DASH }} ·'
]);

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) out.push(...walk(p));
    else if (EXTS.has(extname(p))) out.push(p);
  }
  return out;
}

/**
 * 收集「价格 / 净值硬编码 toFixed」的指纹（行内容，不用行号——
 * 行号会随无关改动漂移，制造假红灯）。
 *
 * @param {string} [srcDir] 扫描根目录，默认 `frontend/src`
 * @returns {string[]} 指纹数组（`rel  ::  trim(line)`）
 */
export function collectPriceHardcodes(srcDir = SRC) {
  const out = [];
  for (const f of walk(srcDir)) {
    const rel = relative(ROOT, f).replace(/\\/g, "/");
    if (rel.endsWith(CONTRACT_FILE)) continue;
    readFileSync(f, "utf8")
      .split(/\r?\n/)
      .forEach(line => {
        const t = line.trim();
        if (!/\.toFixed\(/.test(t)) return;
        if (!PRICE_RE.test(t)) return;
        if (CALC_RE.test(t)) return;
        if (NON_PRICE_RE.test(t)) return;
        if (PERCENT_RE.test(t)) return;
        if (MULT_AMOUNT_RE.test(t)) return;
        out.push(`${rel}  ::  ${t}`);
      });
  }
  return out;
}

/** 指纹 → 基线键（去掉文件路径前缀，只留代码行） */
const key = fp => fp.slice(fp.indexOf("  ::  ") + 6);

/**
 * 主判据。
 * @param {{ hardcodes?: string[], baseline?: Iterable<string> }} [input]
 * @returns {{ ok: boolean, added: string[], stale: string[], message: string }}
 */
export function checkPricePrecision(input = {}) {
  const hardcodes = input.hardcodes ?? collectPriceHardcodes();
  const baseline = new Set(input.baseline ?? BASELINE);
  const seen = new Set();
  const added = [];
  for (const fp of hardcodes) {
    const k = key(fp);
    if (baseline.has(k)) {
      seen.add(k);
      continue;
    }
    added.push(fp);
  }
  const stale = [...baseline].filter(k => !seen.has(k));

  if (added.length) {
    const lines = [
      `价格 / 净值展示出现 ${added.length} 处**新增**硬编码 toFixed：`,
      ...added.map(a => `  - ${a}`),
      "",
      "请改用契约：组件用 `:precision=\"pricePrecision(assetType)\"`，",
      "非组件出口（echarts 轴标签 / tooltip / 标注）用 `formatPrice(v, assetType)`。",
      "确属运算或金额语义（被规则误判）时，把它加进 BASELINE 并在注释里写明理由。",
      "（守卫只检查「有没有绕过契约」，不检查位数写对没有。）"
    ];
    return { ok: false, added, stale, message: lines.join("\n") };
  }
  return {
    ok: true,
    added: [],
    stale,
    message: `价格精度契约检查通过（存量基线 ${baseline.size} 处，本次无新增硬编码）。`
  };
}

// CLI 入口：Windows 下 `import.meta.url` 与 `process.argv[1]` 的斜杠数不一致，
// 必须用 pathToFileURL 比较，否则守卫会静默不执行、exit 0（假绿灯）。
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  // `GUARD_PRICE_SRC` 只服务于回归用例（造临时目录喂样本），正常跑不必设
  const srcOverride = process.env.GUARD_PRICE_SRC;
  const v = srcOverride
    ? checkPricePrecision({ hardcodes: collectPriceHardcodes(srcOverride) })
    : checkPricePrecision();
  console.log(v.message);
  if (v.stale.length) {
    console.log(
      `提示：基线中 ${v.stale.length} 项已不存在，可从 BASELINE 移除：${v.stale.join(" | ")}`
    );
  }
  process.exit(v.ok ? 0 : 1);
}
