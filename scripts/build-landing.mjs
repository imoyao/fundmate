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
const tplPath = path.join(root, 'landing.template.html');
const ymlPath = path.join(root, 'landing.content.yml');
const outPath = path.join(root, 'landing.html');

const tpl = fs.readFileSync(tplPath, 'utf8');
const data = yaml.load(fs.readFileSync(ymlPath, 'utf8'));

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

let html = tpl;

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

// 2) 标量替换
html = html.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_m, p) => {
  const v = get(data, p);
  return v == null ? '' : esc(v);
});

// 3) 图标注入
html = html.replace(/<!--ICON:([\w-]+)-->/g, (_m, name) => ICONS[name] || '');

// 4) Marquee 无缝 + 满宽：将每个 eco-track 的内容重复为偶数份。
//    - 偶数份保证 translateX(-50%) 两半二进制一致 → 无缝循环；
//    - 最小填充份数 MIN_ITEMS 保证轨道宽度大于任意常见视口，滚动时右侧不露白。
//    用「轨道收尾 </div> 后紧跟父级 </div>」定位，末行（最后一条 eco-marquee）同样被处理。
const ECO_MIN_ITEMS = 36; // 每行至少铺满的标签数（含 2 份整除，保证无缝）
html = html.replace(
  /(<div class="eco-track"[^>]*>)([\s\S]*?)(<\/div>\s*(?=<\/div>))/g,
  (_m, open, body, close) => {
    const perSet = (body.match(/eco-item/g) || []).length || 1;
    let copies = Math.max(2, Math.ceil(ECO_MIN_ITEMS / perSet));
    if (copies % 2 !== 0) copies += 1; // 强制偶数
    return open + body.repeat(copies) + close;
  }
);

// 5) 校验：仍有未替换的令牌则告警
const leftover = html.match(/\{\{[^}]+\}\}/g);
if (leftover) {
  console.warn('[build-landing] 未替换的令牌：', [...new Set(leftover)]);
}

fs.writeFileSync(outPath, html);
console.log('[build-landing] 已生成 landing.html');
