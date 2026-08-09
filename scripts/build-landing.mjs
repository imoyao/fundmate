// 构建时注入：读取 landing.content.yml，替换 landing.template.html 中的令牌，
// 输出纯静态 landing.html（无运行时依赖，SEO 友好）。
//
// 令牌语法：
//   {{ path.to.value }}            标量替换（点路径）
//   {{#each path.to.array}} ... {{/each}}   循环；循环体内用 {{field}} 引用当前项
//   {{.}}                           循环项为字符串时引用自身
//   <!--ICON:name-->                替换为脚本内 ICONS 映射的 SVG 内部路径（设计素材，不入 YML）
//
// 运行：node scripts/build-landing.mjs   或   pnpm run build:landing

import fs from 'node:fs';
import path from 'node:path';
import yaml from 'js-yaml';

const root = process.cwd();
const ymlPath = path.join(root, 'landing.content.yml');
const data = yaml.load(fs.readFileSync(ymlPath, 'utf8'));

// 多页构建：landing / about 共用同一份 YML 文案源，各自独立模板
// ===== 全局贝壳装饰片段（<!--SHELL_DECO--> 注入） =====
// 线条手绘风格贝壳/海星/气泡，用于点缀各页面空白区域
// CSS 与 landing.template.html 的 .shell-deco 保持一致，通过 --line-dark 共享描边色
const SHELL_DECO = `<style>
  /* ===== 线条贝壳散落装饰（沙滩上的贝壳） ===== */
  .shell-deco {
    position: absolute; pointer-events: none; z-index: 1;
    opacity: 0.12; transition: opacity 0.4s ease;
  }
  .shell-deco svg { width: 100%; height: 100%; overflow: visible; }
  .shell-deco path, .shell-deco ellipse, .shell-deco circle, .shell-deco line {
    fill: none; stroke: var(--line-dark); stroke-width: 0.8;
    stroke-linecap: round; stroke-linejoin: round;
  }
  .shell-deco--nautilus   { width: 64px; height: 60px; }
  .shell-deco--scallop    { width: 68px; height: 58px; }
  .shell-deco--conch      { width: 52px; height: 80px; }
  .shell-deco--clam       { width: 72px; height: 46px; }
  .shell-deco--starfish   { width: 60px; height: 56px; }
  .shell-deco--bubble     { width: 36px; height: 36px; }
  @media (max-width: 720px) { .shell-deco { display: none; } }
</style>
<!-- 散落贝壳装饰（页面级绝对定位，各模板按需放置） -->
<div class="shell-deco shell-deco--nautilus" style="top:18%;left:3%;transform:rotate(-25deg)" aria-hidden="true">
  <svg viewBox="0 0 64 60"><path d="M12,48 Q8,30 22,16 T48,10 Q58,20 52,38 T28,54Q16,52 12,48M22,16 Q32,8 44,14M28,24 Q38,18 46,26M20,32 Q32,26 40,34M18,40 Q28,36 34,42" /></svg>
</div>
<div class="shell-deco shell-deco--scallop" style="top:42%;right:2%;transform:rotate(15deg)" aria-hidden="true">
  <svg viewBox="0 0 68 58"><path d="M6,38 Q34,6 62,38 Q34,54 6,38M34,14 V38M22,20 Q34,16 46,20M16,26 Q34,20 52,26M10,32 Q34,26 58,32" /><path d="M30,42 Q34,44 38,42" stroke-width="0.5"/></svg>
</div>
<div class="shell-deco shell-deco--starfish" style="top:72%;left:5%;transform:rotate(-10deg)" aria-hidden="true">
  <svg viewBox="0 0 60 56"><path d="M30,4 L34,22 L52,18 L40,32 L56,42 L38,40 L30,56 L22,40 L4,42 L20,32 L8,18 L26,22Z" /><circle cx="30" cy="28" r="4" stroke-width="0.5"/><circle cx="26" cy="26" r="0.8" fill="var(--line-dark)"/><circle cx="34" cy="26" r="0.8" fill="var(--line-dark)"/></svg>
</div>
<div class="shell-deco shell-deco--conch" style="top:65%;right:5%;transform:rotate(20deg)" aria-hidden="true">
  <svg viewBox="0 0 52 80"><path d="M26,4 Q38,8 40,24 Q42,44 30,64 Q18,48 16,28 Q14,12 26,4M20,18 Q26,14 32,18M18,28 Q26,22 34,28M18,38 Q26,34 32,38M22,50 Q26,46 30,50" /><path d="M26,4 Q20,10 18,20" stroke-width="0.5"/></svg>
</div>
<div class="shell-deco shell-deco--bubble" style="top:28%;right:8%" aria-hidden="true">
  <svg viewBox="0 0 36 36"><ellipse cx="18" cy="18" rx="16" ry="14" /><path d="M10,14 Q14,10 18,13M22,12 Q26,14 24,18" stroke-width="0.5"/></svg>
</div>
<div class="shell-deco shell-deco--scallop" style="bottom:12%;left:12%;transform:rotate(-18deg);width:44px;height:38px" aria-hidden="true">
  <svg viewBox="0 0 68 58"><path d="M6,38 Q34,6 62,38 Q34,54 6,38M34,14 V38M22,20 Q34,16 46,20M16,26 Q34,20 52,26" /></svg>
</div>`;

const PAGES = {
  landing: { tpl: 'landing.template.html', out: 'landing.html' },
  about: { tpl: 'about.template.html', out: 'about.html' },
  story: { tpl: 'story.template.html', out: 'story.html' },
};

// ===== about 章节结构校验（与 docs/site/about.md 对齐） =====
// 规则：
//   - YML about.blocks[*].title 必须全部存在于 docs/site/about.md 的 `## ` 标题中（双向）。
// 用途：about.html 是品牌页，文案可自由润色美化（用户裁决：不要求逐句镜像 docs）；
//       但章节结构应与 docs/site/about.md 保持对齐，防止某个 section 被悄悄删除而两处脱节。
const ABOUT_DOCS_PATH = path.join(root, 'docs', 'about.md');

function verifyAboutDrift() {
  if (!data.about) return;
  if (!fs.existsSync(ABOUT_DOCS_PATH)) {
    console.warn('[build-landing] 未找到 ' + ABOUT_DOCS_PATH + '，跳过 about 结构校验');
    return;
  }
  const md = fs.readFileSync(ABOUT_DOCS_PATH, 'utf8');
  const mdTitles = [...md.matchAll(/^##\s+(.+)$/gm)].map((m) => m[1].trim());
  const ymlTitles = (data.about.blocks || []).map((b) => b.title);
  const errors = [];
  for (const t of ymlTitles) {
    if (!mdTitles.includes(t)) errors.push('章节「' + t + '」在 docs/site/about.md 中缺失');
  }
  for (const t of mdTitles) {
    if (!ymlTitles.includes(t)) errors.push('章节「' + t + '」在 YML about.blocks 中缺失');
  }
  if (errors.length) {
    console.error('[build-landing] ✗ about 章节结构与 docs/site/about.md 脱节：\n  - ' + errors.join('\n  - '));
    console.error('  docs/site/about.md 与 landing.content.yml about.blocks 的章节标题需保持一致。');
    process.exit(1);
  }
  console.log('[build-landing] ✓ about 章节结构校验通过（文案不受限，可自由润色）');
}

function buildPage(key) {
  if (key === 'about') verifyAboutDrift();
  const { tpl: tplFile, out: outFile } = PAGES[key];
  const tplPath = path.join(root, tplFile);
  const outPath = path.join(root, outFile);
  let html = fs.readFileSync(tplPath, 'utf8');

// 内联 SVG 图标内部路径（设计素材，不属于「可见文案」，故不入 YML）
const ICONS = {
  layers: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
  'trending-up': '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
  list: '<rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="10" x2="16" y2="10"/><line x1="8" y1="14" x2="12" y2="14"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  'shield-check': '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="12 8 12 12 15 14"/>',
  monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  activity: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  'grad-cap': '<path d="M22 10L12 5 2 10l10 5 10-5z"/><path d="M6 12v5c0 1 3 3 6 3s6-2 6-3v-5"/>',
  refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
  rect: '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/>',
  'circle-x': '<circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>',
  'file-text': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
  'bell-off': '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
  'user-plus': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="17" y1="11" x2="23" y2="11"/><line x1="20" y1="8" x2="20" y2="14"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  chart: '<path d="M3 3v18h18"/><path d="M3 14l4-5 4 3 5-7 5 6"/>',
};

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function get(obj, p) {
  if (p === '.' || p === '') return obj;
  return p.split('.').reduce((o, k) => (o == null ? o : o[k]), obj);
}

// html 已在 buildPage() 内读取（见上方）

// 1) 循环块（先于标量，避免循环体内的 {{field}} 被标量正则误伤）
const eachRe = /\{\{#each\s+([\w.]+)\}\}([\s\S]*?)\{\{\/each\}\}/g;
html = html.replace(eachRe, (_m, p, body) => {
  const arr = get(data, p) || [];
  return arr
    .map((item) =>
      body.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_mm, f) => {
        const v = get(item, f);
        return v == null ? '' : esc(v);
      })
    )
    .join('');
});

// 1.5) 条件块（{{#if path}}...{{/if}}，路径存在且非空才保留）
const ifRe = /\{\{#if\s+([\w.]+)\}\}([\s\S]*?)\{\{\/if\}\}/g;
html = html.replace(ifRe, (_m, p, body) => {
  const v = get(data, p);
  return v ? body : '';
});

// 1.7) 三花括号 {{{ }}} 原样输出（不转义），用于内容中需保留 HTML 的字段
//      （如 footer.tagline 的 <br/>、footer.bottom2 的 <a> 链接）。
//      必须在标量替换之前处理，避免被 {{ }} 正则从内部部分匹配。
const rawRe = /\{\{\{\s*([\w.]+)\s*\}\}\}/g;
html = html.replace(rawRe, (_m, p) => {
  const v = get(data, p);
  return v == null ? '' : String(v);
});

// 2) 标量替换（转义）
html = html.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_m, p) => {
  const v = get(data, p);
  return v == null ? '' : esc(v);
});

// 3) 图标注入
html = html.replace(/<!--ICON:([\w-]+)-->/g, (_m, name) => ICONS[name] || '');

// 3.5) 全局贝壳装饰注入
html = html.replace(/<!--SHELL_DECO-->/g, SHELL_DECO);

// 4) Marquee 无缝 + 满宽 + 去重打乱：
//    - 收集所有 eco-item 文本 → Set 去重 → Fisher-Yates 随机打乱；
//    - 偶数份保证 translateX(-50%) 两半二进制一致 → 无缝循环；
//    - 最小填充份数 MIN_ITEMS 保证轨道宽度大于任意常见视口，滚动时右侧不露白。
//    ⚠️ 为什么是 36（勿随手调小）：无缝循环的接缝要求"半轨宽 ≥ 视口宽"。
//      每项约 120–150px：24 项 → 半轨 ≈ 1800px，1920px 屏接缝处仍露白（曾实测）；
//      36 项 → 半轨 18 项 ≈ 2700px，可覆盖 1920px，4K 屏仅接缝瞬间略欠。
//      保持偶数份（此处 perSet=6 → copies=6）是 -50% 两半一致的前提。
const ECO_MIN_ITEMS = 36;
function shuffle(arr) { // Fisher-Yates
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}
html = html.replace(
  /(<div class="eco-track"[^>]*>)([\s\S]*?)(<\/div>\s*(?=<\/div>))/g,
  (_m, open, body, close) => {
    // 提取 track 内所有 item：既支持纯文字 <span class="eco-item">文字</span>，
    // 也支持真实 Logo <div class="eco-item eco-logo">…<img>…</div>。
    // 按"内容"去重（文字按文本、Logo 按内部 HTML），原样保留各自标签，避免 logo 被丢弃。
    const itemRe = /<(span|div) class="eco-item(?: eco-logo)?"[^>]*>([\s\S]*?)<\/\1>/g;
    const raw = [...body.matchAll(itemRe)].map(m => {
      const [_, tag, inner] = m;
      return tag === 'div'
        ? { key: 'logo:' + inner, html: `<div class="eco-item eco-logo">${inner}</div>` }
        : { key: inner.trim(), html: `<span class="eco-item">${inner.trim()}</span>` };
    }).filter(x => x.key);
    // 去重 + 打乱
    const unique = shuffle([...new Map(raw.map(x => [x.key, x])).values()]);
    // 重建去重打乱后的 body
    const shuffledBody = unique.map(x => x.html).join('');
    const perSet = unique.length || 1;
    let copies = Math.max(2, Math.ceil(ECO_MIN_ITEMS / perSet));
    if (copies % 2 !== 0) copies += 1; // 强制偶数
    return open + shuffledBody.repeat(copies) + close;
  }
);

// 5) 内联 site.css：将 <link href="/site/css"> 替换为 <style> 块（保证产物可在 file:// 协议下自包含）
const siteCssPath = path.join(root, 'site', 'style.css');
if (fs.existsSync(siteCssPath)) {
  const siteCss = fs.readFileSync(siteCssPath, 'utf8');
  html = html.replace(
    /<link[^>]*href=["']\/site\/style\.css["'][^>]*>/,
    `<style>\n/* ==== auto-inlined from site/style.css ==== */\n${siteCss}\n/* ==== end inline ==== */\n</style>`
  );
  console.log('[build-landing] 已内联 site/style.css');
} else {
  console.warn('[build-landing] site/style.css 不存在，跳过内联（产物依赖 HTTP server）');
}

// 6) 校验：仍有未替换的令牌则告警
const leftover = html.match(/\{\{[^}]+\}\}/g);
if (leftover) {
  console.warn('[build-landing] 未替换的令牌：', [...new Set(leftover)]);
}

  fs.writeFileSync(outPath, html);
  console.log('[build-landing] 已生成 ' + outFile);
}

// 入口：node scripts/build-landing.mjs [page]   默认 landing；all = 全部页面
const arg = process.argv[2] || 'landing';
if (arg === 'all') {
  Object.keys(PAGES).forEach(buildPage);
} else if (PAGES[arg]) {
  buildPage(arg);
} else {
  console.error('[build-landing] 未知页面: ' + arg + '（可选: landing / about / story / all）');
  process.exit(1);
}
