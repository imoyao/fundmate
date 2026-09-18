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
 * 已知局限（**故意保守**）
 * ------------------------
 *   1. 背景只按 `--bg-page` / `--bg-card` 两个基准算，渐变 / 图片 / 多层叠加不模拟
 *      （半透明令牌会先与该基准合成）；
 *   2. 只认 `color: var(--token)` 形式；`color-mix()` / 字面量不拆；
 *   3. 不判断可见性（禁用态 / `opacity: 0`）与是否被更靠后的规则覆盖 → 由人复核。
 *   因此本脚本用于**缩小复核范围**，不是最终裁决。
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, extname } from 'node:path';
import process from 'node:process';

const SRC = 'frontend/src';
const COLORS_CSS = 'frontend/src/style/colors.css';
const DARK_SCSS = 'frontend/src/style/dark.scss';
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

/** 收集 `color: var(--x)` 声明：行号、选择器、以及**按 CSS 级联**取到的字号/字重。 */
function collectColorUses(rawText, path) {
  const uses = [];
  const lines = rawText.split('\n');
  const declRe = /^\s*color:\s*var\(\s*(--[A-Za-z0-9_-]+)/;
  const sizeRe = /^\s*(font-size|font-weight)\s*:\s*([^;]+);/;
  const rules = buildRules(rawText);

  for (let i = 0; i < lines.length; i++) {
    const m = declRe.exec(lines[i]);
    if (!m) continue;
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
const WHITE = [255, 255, 255];

const isTextLevel = t => t.endsWith('-ink') || t.startsWith('--text-') || t === '--text-inverse';
const inkOf = t => (light.has(`${t}-ink`) ? `${t}-ink` : null);

/**
 * 人工豁免指令（写在 `color:` 声明上方 3 行内，或同一行）：
 *     audit-text-contrast: exempt <理由>
 * 以行注释或块注释承载均可。用途：把「已判定并登记为保留」的项从「不达标」里摘出来，
 * 但仍在报告里单列 —— 让「不达标清零」这一验收口径可被机器复核，而不是靠人记忆。
 */
const EXEMPT_RE = /audit-text-contrast:\s*exempt\b\s*([^\n*]*)/;
function findExempt(lines, idx) {
  for (let j = idx; j >= Math.max(0, idx - 3); j--) {
    const m = EXEMPT_RE.exec(lines[j]);
    if (m) return m[1].replace(/[\s*]+$/, '').trim() || '（未写理由）';
  }
  return null;
}

const files = walk(SRC).filter(f => !scope || f.includes(scope));
const offenders = []; // 底色级当文字色（本卡的目标类）
const inkBad = []; // 已是文字级但仍不达标
const exempted = []; // 人工豁免（有指令 + 理由）
for (const f of files) {
  const raw = readFileSync(f, 'utf8');
  const lines = raw.split('\n');
  for (const u of collectColorUses(raw, f)) {
    // 主题上下文：选择器里带 dark / 文件就是 dark.scss → 用暗色令牌值与暗色卡底，
    // 否则用亮色（避免拿亮色值去算暗色块，得出毫无意义的 1.0:1 / 2.0:1）。
    const darkCtx = /dark/i.test(u.selector) || f.includes('dark.');
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
      const inkRaw = light.get(ink);
      row.inkWorst = Math.min(contrast(parseColor(inkRaw, bgPage), bgPage), contrast(parseColor(inkRaw, bgCard), bgCard));
    }
    const exemptWhy = findExempt(lines, u.line - 1);
    if (exemptWhy) {
      row.exemptWhy = exemptWhy;
      exempted.push(row);
      continue;
    }
    if (!isTextLevel(u.token) && ink) offenders.push(row);
    else if (isTextLevel(u.token) && !v.ok) inkBad.push(row);
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
    `    ${r.token} ${r.hex}  ${ratioStr}  [${size}${heavy}]${sizeSrc}  需 ${r.limit}  ${r.ok ? '（大字豁免内 OK）' : '**不达标**'}\n` +
    `    选择器: ${String(r.selector).replace(/\s+/g, ' ').slice(0, 100)}\n` +
    `    建议:   ${fix}`
  );
};

const reallyBad = offenders.filter(r => !r.ok);
console.log(`扫描 ${files.length} 个文件；发现「底色级令牌当文字色」 ${offenders.length} 处，其中按其字号判据不达标 ${reallyBad.length} 处\n`);
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

if (showAll && exempted.length) {
  console.log(`\n=== 已登记豁免（代码内有 audit-text-contrast 指令，共 ${exempted.length} 处） ===`);
  for (const r of exempted.sort((a, b) => a.worst - b.worst)) {
    console.log(`${relative(process.cwd(), r.file)}:${r.line}  ${r.token} ${r.hex}  ${r.worst.toFixed(2)}:1  [${r.fontSize || '字号?'}]\n    理由: ${r.exemptWhy}`);
  }
}

console.log('\n说明：背景取 `--bg-page`（页底）与 `--bg-card`（卡片底）两个基准，半透明令牌先按各自背景合成；');
console.log('      字体字号沿「最内层规则 → 外层规则」逐级取，`字号?` 表示全链路未声明、需人工确认；');
console.log('      本脚本不模拟渐变与图片背景、不判断可见性，用于**缩小复核范围**，不是最终裁决。');
