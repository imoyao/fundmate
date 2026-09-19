#!/usr/bin/env node
/**
 * 文字色对比度审计器（#1586；零依赖，纯静态）
 * ==========================================
 *
 * WHY
 * ---
 * 本仓设计系统把颜色令牌分成两族：
 *   · **底色级**（`--color-rise` / `--temp-mid` / `--text-tertiary` …）——用于背景 / 边框 / 图形；
 *   · **文字级**（同名加 `-ink` 后缀，如 `--color-rise-ink`）——专门用于 `color:`。
 * 直接拿底色级当文字色时，白底对比度常只有 3.3~3.9:1，达不到 WCAG AA 的正文要求（4.5:1）。
 * #1545 建立了 `-ink` 文字族、#1558 修掉了「人工实测清单内」的 12 处；但清单是人手拉的，容易漏。
 *
 * 本脚本只做一件事：**找出「用了底色级令牌当文字色」的地方**，并给出两边的对比度，
 * 让「该不该换 `-ink`」变成一行能读的结论 —— 而不是又拉一张 400 行的噪声清单。
 *
 * 用法
 * ----
 *     node scripts/audit_text_contrast.mjs                  # 全量
 *     node scripts/audit_text_contrast.mjs --scope explore  # 只看某路径片段
 *     node scripts/audit_text_contrast.mjs --all            # 额外列出「已是 -ink 但仍不达标」与「已登记豁免」
 *
 * 人工豁免（**唯一**的正规出口）
 * -----------------------------
 *   判定为「保留不改」的项，在 `color:` 声明上方 3 行内写一行指令 + 理由：
 *       // audit-text-contrast: exempt 非文本图标，3.69:1 ≥ 非文本 3:1（WCAG 1.4.11）
 *   脚本会把它从「不达标」移入「已登记豁免」段（`--all` 时可见），
 *   于是「某范围不达标清零」这句话可以被重跑复核，而不是只能靠人记。
 *
 * 判据（WCAG 2.x）
 * ---------------
 *   正文 ≥ 4.5:1；大字（`font-size >= 24px`，或 `>= 18.66px` 且 `font-weight >= 700`）≥ 3:1。
 *   字号沿「最内层规则 → 外层规则」逐级取（SCSS 嵌套常见把 `font-size` 写在祖先规则里）；
 *   全链路都读不到才标 `?` —— **不替你猜**（宁可让人复核，也别给错结论）。
 *
 * 已知局限（**故意保守，但每条都点明，不留静默漏洞**）
 * ------------------------------------------------
 *   1. 背景只按 `--bg-page` / `--bg-card` 两个基准算，渐变 / 图片 / 多层叠加不模拟
 *      （半透明令牌会先与该基准合成）；
 *   2. 只认 `color: var(--token)` 形式；`color-mix()` / 字面量不拆，通过变量间接赋值
 *      （`:style="expr"`）也不拆 —— 但这类会**显式计数并单列分段**，不留静默；
 *   3. **模板内联样式已纳入扫描**（#1599 批次 2）：`style="color: var(--x)"` 与
 *      `:style="{ color: 'var(--x)' }"`（含跨行、数组写法）都能读到。三处口径与样式块**刻意不同**，
 *      逐条标注在报告里：字号只取「同一 style 属性内」的声明（取不到标 `字号?`，不猜 class 字号）、
 *      基准底一律取**亮色**（亮底对比度更低＝更严口径；暗色端交真机 axe，混算反而给错数字）、
 *      选择器回退为「标签名 + class」；
 *   4. `--text-inverse` 与 `--brand-*` 这两类**按定义不用中性基准底**，单列分段、判定交 axe（见下）；
 *   5. 不判断可见性（禁用态 / `opacity: 0`）与是否被更靠后的规则覆盖 → 由人复核。
 *   因此本脚本用于**缩小复核范围**，不是最终裁决。
 */

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, extname } from 'node:path';
import process from 'node:process';

const SRC = 'frontend/src';
const COLORS_CSS = 'frontend/src/style/colors.css';
const DARK_SCSS = 'frontend/src/style/dark.scss';
const THEME_SCSS = 'frontend/src/style/theme.scss';
const EXTS = new Set(['.vue', '.scss', '.css']);

const args = process.argv.slice(2);
const scope = args.includes('--scope') ? args[args.indexOf('--scope') + 1] : null;
const showAll = args.includes('--all');

// ---------------------------------------------------------------- 颜色工具

function parseHex(str) {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec((str || '').trim());
  if (!m) return null;
  let h = m[1];
  if (h.length === 3) h = h.split('').map(c => c + c).join('');
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

/**
 * 把令牌值解析成 rgb。支持 `#hex` 与 `rgb(r g b)` / `rgb(r g b / a%)`
 * （暗色端大量令牌是半透明写法；不合成就会整片漏扫，等于暗色端零覆盖）。
 */
function parseColor(str, bg) {
  const s = (str || '').trim();
  const hex = parseHex(s);
  if (hex) return hex;
  const m = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:\s*[/,]\s*([\d.]+%?))?\s*\)$/i.exec(s);
  if (!m) return null;
  const rgb = [Number(m[1]), Number(m[2]), Number(m[3])];
  const rawA = m[4];
  const alpha = rawA === undefined ? 1 : rawA.endsWith('%') ? Number.parseFloat(rawA) / 100 : Number(rawA);
  if (alpha >= 1) return rgb;
  const base = bg || [255, 255, 255];
  return rgb.map((v, i) => v * alpha + base[i] * (1 - alpha));
}

function luminance([r, g, b]) {
  const f = v => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function contrast(a, b) {
  const [hi, lo] = luminance(a) > luminance(b) ? [luminance(a), luminance(b)] : [luminance(b), luminance(a)];
  return (hi + 0.05) / (lo + 0.05);
}

/** 抽 `--token: #hex | rgb(...)` 定义（取首次出现）。 */
function collectTokens(text) {
  const out = new Map();
  for (const m of text.matchAll(/^\s*(--[A-Za-z0-9_-]+)\s*:\s*(#[0-9a-fA-F]{3,6}|rgba?\([^)]*\))\s*;/gm)) {
    if (!out.has(m[1])) out.set(m[1], m[2]);
  }
  return out;
}

/**
 * 抽 `--token: var(--other);` 别名并**解引用**成实际色值（#1599 批次 2）。
 *
 * WHY 必须做：Element Plus 的主题映射层（`style/theme.scss`）把 `--el-color-primary` 写成
 * `var(--brand-700)` —— 原 `collectTokens` 只认字面量，于是 `--el-color-*` 系列**不在令牌表里**，
 * `parseColor` 返回 null 后 `continue` → **用它们当文字色的地方全站漏扫**（静态实测 81 处，
 * 而 issue #1599 里只登记了 1 处 axe 命中）。这正是「工具悄悄给错答案」的又一例：
 * 人拿「静态清零」当验收依据，实际有一整族令牌从未被看过。
 */
function collectVarAliases(text, base) {
  const out = new Map();
  for (const m of text.matchAll(/^\s*(--[A-Za-z0-9_-]+)\s*:\s*var\(\s*(--[A-Za-z0-9_-]+)\s*\)\s*;/gm)) {
    const v = base.get(m[2]);
    if (v && !out.has(m[1])) out.set(m[1], v);
  }
  return out;
}

// ---------------------------------------------------------------- 源码扫描

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (EXTS.has(extname(p))) out.push(p);
  }
  return out;
}

/**
 * 解析出全部规则块（含 SCSS 嵌套）：内层规则会落在外层规则的 [start, end] 区间里。 * 逐字符扫描并跳过注释/字符串，保证行号与源码一致。
 */
function buildRules(text) {
  const rules = [];
  const stack = [];
  let line = 1;
  let inBlock = false;
  let inLine = false;
  let quote = null;
  let buf = '';

  for (let k = 0; k < text.length; k++) {
    const c = text[k];
    const next = text[k + 1];
    if (c === '\n') {
      line++;
      inLine = false;
      continue;
    }
    if (inLine) continue;
    if (inBlock) {
      if (c === '*' && next === '/') {
        inBlock = false;
        k++;
      }
      continue;
    }
    if (quote) {
      if (c === quote) quote = null;
      continue;
    }
    if (c === '/' && next === '*') {
      inBlock = true;
      k++;
      continue;
    }
    if (c === '/' && next === '/') {
      inLine = true;
      continue;
    }
    if (c === '"' || c === "'") {
      quote = c;
      continue;
    }
    if (c === '{') {
      const rule = { start: line, end: Number.MAX_SAFE_INTEGER, selector: buf.trim().replace(/\s+/g, ' ') };
      rules.push(rule);
      stack.push(rule);
      buf = '';
      continue;
    }
    if (c === '}') {
      const r = stack.pop();
      if (r) r.end = line;
      buf = '';
      continue;
    }
    if (c === ';') buf = '';
    else buf += c;
  }
  return rules;
}

/** 每行起始字符偏移：把「行号」换算成「字符区间」用（判定某声明是否落在内联样式属性值里）。 */
function lineOffsets(rawText) {
  const offsets = [0];
  for (let i = 0; i < rawText.length; i++) if (rawText[i] === '\n') offsets.push(i + 1);
  return offsets;
}

/** SFC 的 `<template>` 块行区间（第一个 `<template` → 最后一个 `</template>`）；无则返回 null。 */
function templateRange(lines) {
  let start = -1;
  let end = -1;
  for (let i = 0; i < lines.length; i++) {
    if (start < 0 && /<template[\s>]/.test(lines[i])) start = i;
    if (/<\/template>/.test(lines[i])) end = i;
  }
  return start < 0 || end < start ? null : { start, end };
}

/**
 * 收集**模板内联样式**里的 `color: var(--x)`（#1599 批次 2）。
 *
 * WHY 单开一个收集器而不是复用 `collectColorUses`
 * ------------------------------------------------
 * 两者要读的语料不同：样式块是「选择器 + 声明」，内联是「元素属性值（CSS 串或 JS 对象字面量）」。
 * 硬塞进一个函数会让 `buildRules` 把 Vue 插值 `{{ }}` 和 `:style="{…}"` 也当成规则块，
 * 得出的「选择器」是垃圾、字号来源也是错的 —— 也就是**又给一次错答案**。
 *
 * 三处口径与样式块不同（都写进报告，不静默）：
 *   · 字号：只取同一 style 属性内的 `font-size` / `fontSize`；取不到标 `字号?`，按正文 4.5:1 判；
 *   · 主题：基准底一律取**亮色**（亮底对比度更低＝更严口径；暗色端由真机 axe 覆盖）；
 *   · 选择器：回退为「标签名 + class」，作为人工定位线索。
 *
 * 返回 `{ uses, covered, unresolved }`：`covered` 是属性值的字符区间，
 * 供样式块扫描跳过（多行 `style="` 里的 `color:` 在行首，会被两处都读到 → 重复计数）。
 */
function collectInlineColorUses(rawText, path) {
  const uses = [];
  const covered = [];
  const unresolved = [];
  if (!path.endsWith('.vue')) return { uses, covered, unresolved };

  const lines = rawText.split('\n');
  const range = templateRange(lines);
  if (!range) return { uses, covered, unresolved };
  const offsets = lineOffsets(rawText);
  const lineAt = idx => {
    let lo = 0;
    let hi = offsets.length - 1;
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2);
      if (offsets[mid] <= idx) lo = mid;
      else hi = mid - 1;
    }
    return lo + 1;
  };

  // 只在 `<template>` 行区间内找 style 属性（避开 `<script>` 里以字符串形式出现的 "style="）
  const segStart = offsets[range.start];
  const segEnd = offsets[Math.min(range.end + 1, lines.length - 1)] ?? rawText.length;
  const seg = rawText.slice(segStart, segEnd);

  // `:style=` / `v-bind:style=` 是一支，裸 `style=` 是另一支（后面的 lookbehind 防止把 `:style` 再吃一次）
  const attrRe = /(?:(?::|v-bind:)style|(?<![:\w-])style)\s*=\s*"([^"]*)"/g;
  const cssColorRe = /(?<![-a-z])color\s*:\s*var\(\s*(--[A-Za-z0-9_-]+)\s*\)/g;
  const cssSizeRe = /(?<![-a-z])font-size\s*:\s*([^;"'`]+)/;
  const cssWeightRe = /(?<![-a-z])font-weight\s*:\s*([^;"'`]+)/;
  const jsColorRe = /(?<![-a-zA-Z])(?:['"]color['"]|color)\s*:\s*['"`]\s*var\(\s*(--[A-Za-z0-9_-]+)\s*\)/g;
  // 兜底判据必须与上面的解析同源：只认**小写 color 键**。
  // 用 `/color/i` 会把 `backgroundColor` / `background-color` 也算成文字色声明，
  // 于是「不可静态解析」清单被底色声明灌满 —— 那是另一种「静默」：真问题被噪声埋掉。
  const cssColorKeyRe = /(?<![-a-z])color\s*:/;
  const jsColorKeyRe = /(?<![-a-zA-Z])(?:['"]color['"]|color)\s*:/;
  const jsSizeRe = /['"]?fontSize['"]?\s*:\s*['"`]?\s*([\d.]+(?:px|rem|em)?)/;
  const jsWeightRe = /['"]?fontWeight['"]?\s*:\s*['"`]?\s*(\d+)/;

  let m;
  while ((m = attrRe.exec(seg)) !== null) {
    const bound = m[0].trimStart().startsWith(':') || m[0].includes('v-bind:');
    const value = m[1];
    const valueStart = segStart + m.index + m[0].indexOf('"') + 1;
    covered.push([valueStart, valueStart + value.length]);
    const lineno = lineAt(valueStart);

    // 元素上下文：属性往前最近的 `<` 起算，取标签名与 class（内联样式没有选择器可报）
    const head = seg.slice(Math.max(0, m.index - 400), m.index);
    const seg2 = head.slice(head.lastIndexOf('<'));
    const tag = (/^<\s*([A-Za-z][\w.-]*)/.exec(seg2) || [])[1] || '';
    const cls = (/class\s*=\s*"([^"]*)"/.exec(seg2) || [])[1] || '';
    const ctx = `${tag || '?'}${cls ? `.${cls.trim().split(/\s+/).join('.')}` : ''} 的 style 属性`;
    const origin = '模板内联';

    const found = [];
    for (const re of bound ? [jsColorRe] : [cssColorRe]) {
      re.lastIndex = 0;
      let c;
      while ((c = re.exec(value)) !== null) found.push(c[1]);
    }
    if (!found.length) {
      // 值是「颜色声明」但不可静态解析（`:style="{ color: textColor }"` / `style="color: #333"`）
      // → 显式登记，不静默（判据与解析同源，见上面的 cssColorKeyRe / jsColorKeyRe）
      if ((bound ? jsColorKeyRe : cssColorKeyRe).test(value)) {
        unresolved.push({ file: path, line: lineno, ctx });
      }
      continue;
    }
    const sizeM = (bound ? jsSizeRe : cssSizeRe).exec(value);
    const weightM = (bound ? jsWeightRe : cssWeightRe).exec(value);
    for (const token of found) {
      uses.push({
        file: path,
        line: lineno,
        token,
        selector: ctx,
        fontSize: sizeM ? sizeM[1].trim() : null,
        fontWeight: weightM ? weightM[1].trim() : null,
        sizeScope: ctx,
        origin,
        originKind: bound ? ':style 绑定' : 'style 属性',
      });
    }
  }
  return { uses, covered, unresolved };
}

/** 收集样式块里的 `color: var(--x)` 声明：行号、选择器、以及**按 CSS 级联**取到的字号/字重。 */
function collectColorUses(rawText, path, covered = []) {
  const uses = [];
  const lines = rawText.split('\n');
  const declRe = /^\s*color:\s*var\(\s*(--[A-Za-z0-9_-]+)/;
  const sizeRe = /^\s*(font-size|font-weight)\s*:\s*([^;]+);/;
  const rules = buildRules(rawText);
  const offsets = lineOffsets(rawText);
  const isInline = idx => covered.some(c => idx >= c[0] && idx < c[1]);

  for (let i = 0; i < lines.length; i++) {
    const m = declRe.exec(lines[i]);
    if (!m) continue;
    // 落在某个 style 属性值内部的声明归内联口径（否则会被两个口径各报一次）
    if (isInline(offsets[i] + m[0].indexOf('color'))) continue;
    const lineno = i + 1;

    // 包含该行的规则，按 start 降序 = 由内到外。字号可能声明在外层规则里（SCSS 嵌套）。
    const chain = rules.filter(r => r.start <= lineno && lineno <= r.end).sort((a, b) => b.start - a.start);
    const selector = chain.length ? chain[0].selector : '?';

    let fontSize = null;
    let fontWeight = null;
    let sizeScope = '?';
    for (const r of chain) {
      for (let j = r.start - 1; j <= Math.min(r.end - 1, lines.length - 1); j++) {
        const d = sizeRe.exec(lines[j]);
        if (!d) continue;
        if (d[1] === 'font-size' && !fontSize) {
          fontSize = d[2].trim();
          sizeScope = r.selector;
        }
        if (d[1] === 'font-weight' && !fontWeight) fontWeight = d[2].trim();
      }
      if (fontSize) break;
    }
    uses.push({ file: path, line: lineno, token: m[1], selector, fontSize, fontWeight, sizeScope });
  }
  return uses;
}

/** 判据：大字 3:1 / 正文 4.5:1；字号未知按正文（保守，多报不漏）。 */
function need(ratio, fontSize, fontWeight) {
  const px = fontSize ? Number.parseFloat(fontSize) : null;
  const fw = fontWeight ? Number.parseFloat(fontWeight) : 400;
  const large = px !== null && (px >= 24 || (px >= 18.66 && fw >= 700));
  const limit = large ? 3 : 4.5;
  return { limit, ok: ratio >= limit, large };
}

// ---------------------------------------------------------------- 主流程

const light = collectTokens(readFileSync(COLORS_CSS, 'utf8'));
const dark = collectTokens(readFileSync(DARK_SCSS, 'utf8'));
// Element Plus 主题映射层：`--el-color-primary: var(--brand-700)` 这类别名要解引用后并入，
// 否则整族 `--el-color-*` 不在令牌表里 → 用它们当文字色的地方全站漏扫（见 collectVarAliases 注释）。
if (existsSync(THEME_SCSS)) {
  for (const [k, v] of collectVarAliases(readFileSync(THEME_SCSS, 'utf8'), light)) {
    if (!light.has(k)) light.set(k, v);
  }
}
// Element Plus 自带的两个绝对色（无本项目映射，值即字面量）
if (!light.has('--el-color-white')) light.set('--el-color-white', '#ffffff');
if (!light.has('--el-color-black')) light.set('--el-color-black', '#000000');
const WHITE = [255, 255, 255];

const isTextLevel = t => t.endsWith('-ink') || t.startsWith('--text-') || t === '--text-inverse';
const inkOf = t => (light.has(`${t}-ink`) ? `${t}-ink` : null);
/**
 * 静态**不可判定**的令牌：它们的背景按定义不是这两条中性基准底，拿基准底去算必然误报。
 * `--text-inverse` 是「品牌色 / 深色实底上的反色白字」（如 `.btn-primary`、`.el-menu-item.is-active`），
 * 白底上算恒为 1.00:1 —— 实测 20 处全是误报。此名单只影响**报告归类**，不影响真机 axe 的判定
 * （axe 能读到渲染后的有效背景，品牌实底白字不达标时它照样会报，见 #1600）。
 */
const NO_BASELINE = new Set(['--text-inverse', '--el-color-white']);
/**
 * `--brand-*` 当 `color:` 用：**此前两个分类桶都不收**（它既不是「有同名 -ink 的底色级」，也不是
 * `--text-*` 文字级）→ 被静默忽略。实测全站 214 处，其中 brand-100~600 是极浅色调，对白底只有
 * 1.5~3.0:1。**但不能机械替换**：品牌实底上浅色调当文字可能是刻意为之 —— 判定依赖**有效背景**，
 * 只能交给真机 axe。本器只给「规模 + 基准底对比度」，`--brand-detail` 才逐条列出。
 */
const BRAND_PREFIX = '--brand-';
const brandDetail = args.includes('--brand-detail');

/**
 * 人工豁免指令（写在 `color:` 声明上方 3 行内，或同一行）：
 *     audit-text-contrast: exempt <理由>
 * 以行注释或块注释承载均可。用途：把「已判定并登记为保留」的项从「不达标」里摘出来，
 * 但仍在报告里单列 —— 让「不达标清零」这一验收口径可被机器复核，而不是靠人记忆。
 */
const EXEMPT_RE = /audit-text-contrast:\s*exempt\b\s*([^\n]*)/;
function findExempt(lines, idx) {
  for (let j = idx; j >= Math.max(0, idx - 3); j--) {
    const m = EXEMPT_RE.exec(lines[j]);
    if (!m) continue;
    // 理由里可能含 Markdown 加粗（`**…**`）与注释收尾（`*/` 或 HTML 的 `-->`）—— 按行取满，再剥掉尾部记号
    const why = m[1]
      .replace(/(?:\*\/|-->)\s*$/, '')
      .replace(/[\s*]+$/, '')
      .trim();
    return why || '（未写理由）';
  }
  return null;
}

const files = walk(SRC).filter(f => !scope || f.includes(scope));
const offenders = []; // 底色级当文字色（本卡的目标类）
const inkBad = []; // 已是文字级但仍不达标
const exempted = []; // 人工豁免（有指令 + 理由）
const noBaseline = []; // 静态不可判定（背景非中性基准底）→ 交真机 axe
const brandRows = []; // `--brand-*` 当文字色：同样须真机判定，但此前被静默忽略
const orphanBad = []; // 底色级当文字色**且无同名 -ink**：此前两个桶都不收 → 被静默丢弃
const unresolvedInline = []; // 内联 style 绑定了颜色但值不可静态解析 → 显式登记，不静默
let inlineTotal = 0; // 模板内联命中的总处数（含达标项，用于让「覆盖了多少」一眼可见）
for (const f of files) {
  const raw = readFileSync(f, 'utf8');
  const lines = raw.split('\n');
  const inline = collectInlineColorUses(raw, f);
  unresolvedInline.push(...inline.unresolved);
  const styleBlock = collectColorUses(raw, f, inline.covered);
  for (const u of [...styleBlock, ...inline.uses].sort((a, b) => a.line - b.line)) {
    // 主题上下文：选择器里带 dark / 文件就是 dark.scss → 用暗色令牌值与暗色卡底，
    // 否则用亮色（避免拿亮色值去算暗色块，得出毫无意义的 1.0:1 / 2.0:1）。
    // 内联样式例外：基准底一律取亮色（亮底对比度更低＝更严口径），暗色端交真机 axe。
    const darkCtx = u.origin ? false : /dark/i.test(u.selector) || f.includes('dark.');
    if (u.origin) inlineTotal++;
    const rawVal = (darkCtx ? dark.get(u.token) : light.get(u.token)) || light.get(u.token) || dark.get(u.token);
    const bgCard = parseColor(darkCtx ? dark.get('--bg-card') || '#242120' : light.get('--bg-card') || '#ffffff') || WHITE;
    const bgPage = parseColor(darkCtx ? dark.get('--bg-page') || '#1a1816' : light.get('--bg-page') || '#ffffff') || WHITE;
    // 半透明令牌须先按各自背景合成，才谈得上对比度。
    const rgbOnPage = parseColor(rawVal, bgPage);
    const rgbOnCard = parseColor(rawVal, bgCard);
    if (!rgbOnPage || !rgbOnCard) continue;
    const onWhite = contrast(rgbOnPage, bgPage);
    const onCard = contrast(rgbOnCard, bgCard);
    const worst = Math.min(onWhite, onCard);
    const v = need(worst, u.fontSize, u.fontWeight);
    const row = { ...u, hex: rawVal, onWhite, onCard, worst, ...v };

    const ink = inkOf(u.token);
    if (ink) {
      row.ink = ink;
      // 「换后对比度」必须与当前行同主题：暗色行若拿亮色 -ink 值去算，
      // 会得出「换完仍是 2.67:1」这种误导性建议（#1586 回归用例抓到）。
      const inkRaw = (darkCtx ? dark.get(ink) : light.get(ink)) || light.get(ink) || dark.get(ink);
      row.inkWorst = Math.min(contrast(parseColor(inkRaw, bgPage), bgPage), contrast(parseColor(inkRaw, bgCard), bgCard));
    }
    const exemptWhy = findExempt(lines, u.line - 1);
    if (exemptWhy) {
      row.exemptWhy = exemptWhy;
      exempted.push(row);
      continue;
    }
    if (NO_BASELINE.has(u.token)) {
      if (!v.ok) noBaseline.push(row);
      continue;
    }
    if (u.token.startsWith(BRAND_PREFIX)) {
      brandRows.push(row);
      continue;
    }
    if (!isTextLevel(u.token) && ink) offenders.push(row);
    else if (isTextLevel(u.token) && !v.ok) inkBad.push(row);
    // 第三类静默漏洞：底色级令牌当文字色、且**没有同名 -ink** → 前两个分支都不收，直接被丢弃。
    // Element Plus 主题映射族（`--el-color-primary` 等）就是这么漏的：既不是 `--text-*` 文字级，
    // 也没有 `-ink` 变体。实测静默 81 处，其中不达标的必须报出来。
    else if (!isTextLevel(u.token) && !ink && !v.ok) orphanBad.push(row);
  }
}

const fmt = r => {
  const ratioStr = `页底 ${r.onWhite.toFixed(2)}:1 / 卡片底 ${r.onCard.toFixed(2)}:1`;
  const size = r.fontSize || '字号?';
  const heavy = r.fontWeight ? ` ${r.fontWeight}` : '';
  const sizeSrc = r.fontSize && r.sizeScope && r.sizeScope !== r.selector ? `（继承自 ${r.sizeScope.slice(0, 40)}）` : '';
  const fix =
    r.inkWorst !== null && r.inkWorst !== undefined
      ? `→ 换 \`${r.ink}\` 后 ${r.inkWorst.toFixed(2)}:1${r.inkWorst >= 4.5 ? '（达标 ✅）' : '（仍不足，需另选色/加粗）'}`
      : '（无同名 `-ink` 令牌，需人工判断）';
  return (
    `${relative(process.cwd(), r.file)}:${r.line}\n` +
    `    ${r.token} ${r.hex}  ${ratioStr}  [${size}${heavy}]${sizeSrc}${r.origin ? '  [模板内联]' : ''}  需 ${r.limit}  ${r.ok ? '（大字豁免内 OK）' : '**不达标**'}\n` +
    `    选择器: ${String(r.selector).replace(/\s+/g, ' ').slice(0, 100)}\n` +
    `    建议:   ${fix}`
  );
};

const reallyBad = offenders.filter(r => !r.ok);
console.log(`扫描 ${files.length} 个文件；发现「底色级令牌当文字色」 ${offenders.length} 处，其中按其字号判据不达标 ${reallyBad.length} 处`);
console.log(`（模板内联样式另命中 ${inlineTotal} 处：\`style="color: var(--x)"\` 与 \`:style="{ color: 'var(--x)' }"\`，已并入下列各段并标 [模板内联]）`);
console.log(`（另有「底色级令牌当文字色且无同名 -ink」不达标 ${orphanBad.length} 处 —— 这类此前被静默丢弃，\`--all\` 时列出）\n`);
console.log('=== 不达标（建议换 -ink） ===');
for (const r of reallyBad.sort((a, b) => a.worst - b.worst)) console.log(fmt(r));

const largeOk = offenders.filter(r => r.ok);
if (showAll && largeOk.length) {
  console.log('\n=== 大字/装饰场景，按 4.5 不足但按 3:1 达标（可不改，建议留注释） ===');
  for (const r of largeOk) console.log(fmt(r));
}

if (showAll && inkBad.length) {
  const badNoInk = inkBad.filter(r => !r.ink);
  const badWithInk = inkBad.filter(r => r.ink);
  console.log(`\n=== 已是文字级令牌但仍不达标（需逐处判定，共 ${inkBad.length} 处） ===`);
  if (badWithInk.length) {
    console.log(`\n--- A. 有同名 -ink 可换（${badWithInk.length} 处） ---`);
    for (const r of badWithInk.sort((a, b) => a.worst - b.worst)) console.log(fmt(r));
  }
  if (badNoInk.length) {
    console.log(`\n--- B. 无同名 -ink（${badNoInk.length} 处，需改字号/加粗或登记豁免） ---`);
    for (const r of badNoInk.sort((a, b) => a.worst - b.worst)) console.log(fmt(r));
  }
}

if (showAll && orphanBad.length) {
  console.log(`\n=== 底色级令牌当文字色 · 无同名 -ink（${orphanBad.length} 处 → 换语义令牌 / 补 -ink / 登记豁免） ===`);
  console.log('（这类此前**两个分类桶都不收，等于静默丢弃**；Element Plus 主题映射族 `--el-color-*` 是主要来源）');
  for (const r of orphanBad.sort((a, b) => a.worst - b.worst)) console.log(fmt(r));
}

if (showAll && noBaseline.length) {
  console.log(`\n=== 静态不可判定（背景为品牌/彩色实底，共 ${noBaseline.length} 处 → 交真机 axe） ===`);
  console.log('（这些令牌按定义不用中性基准底，拿白底/卡底算必然误报；判定一律以 axe 为准）');
  for (const r of noBaseline) {
    console.log(
      `${relative(process.cwd(), r.file)}:${r.line}  ${r.token}  [${r.fontSize || '字号?'}]  选择器: ${String(r.selector).replace(/\s+/g, ' ').slice(0, 70)}`
    );
  }
}

if (brandRows.length) {
  const byTok = new Map();
  for (const r of brandRows) {
    if (!byTok.has(r.token)) byTok.set(r.token, { n: 0, worst: Infinity, rows: [] });
    const e = byTok.get(r.token);
    e.n++;
    e.worst = Math.min(e.worst, r.worst);
    e.rows.push(r);
  }
  const below = brandRows.filter(r => !r.ok).length;
  console.log(`\n=== 品牌色当文字色（\`--brand-*\`，共 ${brandRows.length} 处，其中基准底口径下不达标 ${below} 处） ===`);
  console.log('（**判断依据是有效背景**：品牌实底上浅色调当文字可能是刻意的 → 一律交真机 axe 判；');
  console.log('  本器只报规模与「白底 / 页底」口径的对比度，逐条位置加 `--brand-detail`）');
  for (const [tok, e] of [...byTok.entries()].sort((a, b) => a[1].worst - b[1].worst)) {
    console.log(`  ${tok.padEnd(12)} ${String(e.n).padStart(3)} 处   基准底最差 ${e.worst.toFixed(2)}:1${e.worst < 4.5 ? '  ← 若确实落在中性底上则不达标' : ''}`);
  }
  if (brandDetail) {
    console.log('\n  —— 逐条（--brand-detail）——');
    for (const r of brandRows.sort((a, b) => a.worst - b.worst)) {
      console.log(`  ${relative(process.cwd(), r.file)}:${r.line}  ${r.token}  [${r.fontSize || '字号?'}]  ${String(r.selector).replace(/\s+/g, ' ').slice(0, 60)}`);
    }
  }
}

if (showAll && exempted.length) {
  console.log(`\n=== 已登记豁免（代码内有 audit-text-contrast 指令，共 ${exempted.length} 处） ===`);
  for (const r of exempted.sort((a, b) => a.worst - b.worst)) {
    console.log(
      `${relative(process.cwd(), r.file)}:${r.line}  ${r.token} ${r.hex}  ${r.worst.toFixed(2)}:1  [${r.fontSize || '字号?'}]\n` +
        `    选择器: ${String(r.selector).replace(/\s+/g, ' ').slice(0, 100)}\n` +
        `    理由: ${r.exemptWhy}`
    );
  }
}

if (unresolvedInline.length) {
  console.log(`\n=== 内联样式不可静态解析（${unresolvedInline.length} 处 → 交真机 axe / 人工确认） ===`);
  console.log('（`:style` 绑定了颜色但值不是字面量 `var(--x)`（如 `:style="{ color: textColor }"`）—— 本器无从判定，');
  console.log('  列出位置只为让「还有多少没被扫到」这件事可被复核；判定一律**交真机 axe**，不留静默）');
  for (const r of unresolvedInline) {
    console.log(`${relative(process.cwd(), r.file)}:${r.line}  ${String(r.ctx).slice(0, 90)}`);
  }
}

console.log('\n说明：背景取 `--bg-page`（页底）与 `--bg-card`（卡片底）两个基准，半透明令牌先按各自背景合成；');
console.log('      字体字号沿「最内层规则 → 外层规则」逐级取，`字号?` 表示全链路未声明、需人工确认；');
console.log('      模板内联样式（#1599 批次 2）口径见文件头「已知局限」第 3 条：字号只取属性内声明、');
console.log('      基准底一律取亮色（更严）、选择器回退为「标签名 + class」；暗色端一律以真机 axe 为准；');
console.log('      本脚本不模拟渐变与图片背景、不判断可见性，用于**缩小复核范围**，不是最终裁决。');
