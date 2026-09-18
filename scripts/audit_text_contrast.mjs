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
 *     node scripts/audit_text_contrast.mjs --all            # 额外列出「已是 -ink 但仍不达标」的行
 *
 * 判据（WCAG 2.x）
 * ---------------
 *   正文 ≥ 4.5:1；大字（`font-size >= 24px`，或 `>= 18.66px` 且 `font-weight >= 700`）≥ 3:1。
 *   字号从**同一条规则内**读取；读不到就标 `?`，**不替你猜**（宁可让人复核，也别给错结论）。
 *
 * 已知局限（**故意保守**）
 * ------------------------
 *   1. 背景固定按白底 `#ffffff` 与 `--bg-card` 两个基准算（最严格场景），
 *      渐变 / 图片 / 半透明叠加不模拟；
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

/** 抽 `--token: #hex` 定义（取首次出现）。 */
function collectTokens(text) {
  const out = new Map();
  for (const m of text.matchAll(/^\s*(--[A-Za-z0-9_-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\s*;/gm)) {
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

function styleText(text, path) {
  if (path.endsWith('.vue')) {
    return [...text.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m => m[1]).join('\n');
  }
  return text;
}

/** 收集 `color: var(--x)` 声明：行号、选择器（近似）、同规则内的字号/字重。 */
function collectColorUses(rawText, path) {
  const uses = [];
  const lines = rawText.split('\n');
  const declRe = /^\s*color:\s*var\(\s*(--[A-Za-z0-9_-]+)/;
  const sizeRe = /^\s*(font-size|font-weight)\s*:\s*([^;]+);/;
  for (let i = 0; i < lines.length; i++) {
    const m = declRe.exec(lines[i]);
    if (!m) continue;
    let selector = '?';
    for (let j = i - 1; j >= 0 && j > i - 60; j--) {
      const cand = /^\s*([^;{}]+?)\s*\{\s*$/.exec(lines[j]);
      if (cand) {
        selector = cand[1].trim();
        break;
      }
    }
    let fontSize = null;
    let fontWeight = null;
    for (let j = i; j < lines.length && j < i + 40; j++) {
      const d = sizeRe.exec(lines[j]);
      if (d) {
        if (d[1] === 'font-size' && !fontSize) fontSize = d[2].trim();
        if (d[1] === 'font-weight' && !fontWeight) fontWeight = d[2].trim();
      }
      if (j > i && /^\s*\}/.test(lines[j])) break;
    }
    uses.push({ file: path, line: i + 1, token: m[1], selector, fontSize, fontWeight });
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
const cardRgb = parseHex(light.get('--bg-card') || '#ffffff') || WHITE;

const isTextLevel = t => t.endsWith('-ink') || t.startsWith('--text-') || t === '--text-inverse';
const inkOf = t => (light.has(`${t}-ink`) ? `${t}-ink` : null);

const files = walk(SRC).filter(f => !scope || f.includes(scope));
const offenders = []; // 底色级当文字色（本卡的目标类）
const inkBad = []; // 已是文字级但仍不达标
for (const f of files) {
  const raw = readFileSync(f, 'utf8');
  const style = styleText(raw, f);
  for (const u of collectColorUses(raw, f)) {
    // 主题上下文：选择器里带 dark / 文件就是 dark.scss → 用暗色令牌值与暗色卡底，
    // 否则用亮色（避免拿亮色值去算暗色块，得出毫无意义的 1.0:1 / 2.0:1）。
    const darkCtx = /dark/i.test(u.selector) || f.includes('dark.');
    const hex = (darkCtx ? dark.get(u.token) : light.get(u.token)) || light.get(u.token) || dark.get(u.token);
    const rgb = parseHex(hex);
    if (!rgb) continue;
    const bgCard = darkCtx ? parseHex(dark.get('--bg-card') || '#242120') : cardRgb;
    const bgPage = darkCtx ? parseHex(dark.get('--bg-page') || '#1a1816') : WHITE;
    const onWhite = contrast(rgb, bgPage);
    const onCard = contrast(rgb, bgCard);
    const worst = Math.min(onWhite, onCard);
    const v = need(worst, u.fontSize, u.fontWeight);
    const row = { ...u, hex, onWhite, onCard, worst, ...v };

    const ink = inkOf(u.token);
    if (!isTextLevel(u.token) && ink) {
      const inkRgb = parseHex(light.get(ink));
      row.ink = ink;
      row.inkWorst = inkRgb ? Math.min(contrast(inkRgb, WHITE), contrast(inkRgb, cardRgb)) : null;
      offenders.push(row);
    } else if (isTextLevel(u.token) && !v.ok) {
      inkBad.push(row);
    }
  }
}

const fmt = r => {
  const ratioStr = `白底 ${r.onWhite.toFixed(2)}:1 / 卡片 ${r.onCard.toFixed(2)}:1`;
  const size = r.fontSize || '字号?';
  const heavy = r.fontWeight ? ` ${r.fontWeight}` : '';
  const fix =
    r.inkWorst !== null && r.inkWorst !== undefined
      ? `→ 换 \`${r.ink}\` 后 ${r.inkWorst.toFixed(2)}:1${r.inkWorst >= 4.5 ? '（达标 ✅）' : '（仍不足，需另选色/加粗）'}`
      : '（无同名 `-ink` 令牌，需人工判断）';
  return (
    `${relative(process.cwd(), r.file)}:${r.line}\n` +
    `    ${r.token} ${r.hex}  ${ratioStr}  [${size}${heavy}]  需 ${r.limit}  ${r.ok ? '（大字豁免内 OK）' : '**不达标**'}\n` +
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
  console.log('\n=== 已是文字级令牌但仍不达标（需重新选色） ===');
  for (const r of inkBad) console.log(fmt(r));
}

console.log('\n说明：背景按白底 / --bg-card 两个基准（最严格场景）；字体字号取同规则声明，`字号?` 表示需人工确认；');
console.log('      本脚本不模拟渐变与图片背景、不判断可见性，用于**缩小复核范围**，不是最终裁决。');
