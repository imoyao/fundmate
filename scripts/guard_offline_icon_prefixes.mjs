/**
 * 守卫：离线图标通道只允许引用「已注册进离线集」的图标集（#2937）。
 *
 * ## 为什么需要这个守卫
 *
 * 仓里有两条互不相通的图标通道，长相几乎一样，失败形态却完全不同：
 *
 *   - **离线通道**（`@iconify/vue/dist/offline`，经 `components/ReIcon` 的
 *     `IconifyIconOffline` 暴露，且 `main.ts` 全局注册成同名标签）：
 *     只认 `offlineIcon.ts` 里 `addCollection(...)` 注册过的图标集。**永不联网**，
 *     找不到就是渲染一个空注释节点 `<!---->`——不报错、不告警、控制台干净。
 *   - **在线通道**（`import { Icon } from "@iconify/vue"`）：按需向 api.iconify.design 取，
 *     任何图标集都能出图（离线时退化为空白，但有网络就正常）。
 *
 * `offlineIcon.ts` 只注册了 `ep`（`ri` 那两行是注释），于是全仓 5 处写错的
 * `lucide:` / `mdi:` / `ri:` 静默变成空气：导入向导与 E账户卡片的**上传主图标**、
 * 「下载模板」按钮、顶栏搜索、自选卡置顶图钉——全是用户第一眼看到的位置。
 * 机器上没有任何东西会因此变红，所以它活了很久（#2937）。
 *
 * 修完那 5 处不等于修完机制：下一个人写 `icon="lucide:check"` 时同样不会报错。
 * 本守卫抓的就是这个具体回潮形态。
 *
 * ## 判据
 *
 * 1. 注册集合**只从离线通道的注册点读**：`components/ReIcon/src/offlineIcon.ts` 里
 *    `addCollection(<标识符>)` 的实参，回溯到 `import ... from "@iconify-json/<prefix>"`
 *    得到前缀集合。**注释掉的 `addCollection` 不算**（`ri` 就躺在注释里）。
 *    刻意**不读** `main.ts` 的 `addCollection`：它 import 的是 `@iconify/vue`（在线构建），
 *    与 `dist/offline` 是**两份互不可见的 module storage**（实测：向在线构建
 *    addCollection 后，离线 Icon 仍渲染 `<!---->`）。把它算进注册集合会制造假绿。
 * 2. 逐文件判定**通道归属，不按组件名判**：同一份代码里 `Icon as IconifyIconOffline`
 *    这种别名遍地都是（`components/ImageUploader`、`views/profile/**`、
 *    `views/asset/watchlist/columnRenderers.tsx` 全是**在线** Icon 套了个离线名字），
 *    按名字判会把这批正确的用法全报成违规，守卫会立刻被绕过。故按 import 来源判。
 * 3. 在离线组件上提取 `icon` 的取值——静态属性、`:icon="'x:y'"`、JSX `icon={"x:y"}`、
 *    三元里的每个字面量、以及 `h(OfflineComp, { icon: "x:y" })`——凡出现 `前缀:名字`
 *    且前缀不在注册集合内即违规。
 * 4. **拿不到输入 / 模型失效 ⇒ 退出码 2，不得退化成绿**：
 *    注册文件缺失、注册集合为空、或全仓一个离线图标都没扫到（说明通道判定已经
 *    与代码脱节，此时「0 违规」毫无意义）。
 *
 * ## 边界（已知不覆盖，别把它当万能闸门）
 *
 * - **动态 icon 名是盲区**：`:icon="row.icon"` / `icon={item.meta.icon}` 这类，
 *   值在运行期才确定，静态扫描看不见。真正的兜底是 review 时问一句「这个名字注册了吗」。
 * - **不判在线通道**：`views/profile/**`、`components/ImageUploader`、
 *   `watchlist/columnRenderers.tsx` 走在线通道，图标能出（依赖联网），不在本卡范围
 *   （#2937 已记为范围外）。若哪天要求离线可用，得另开一条判据，别在本脚本里放宽。
 * - **不判 `~icons/xx/yy`**：那是 unplugin-icons 的编译期内联，构建产物就是 SVG，
 *   与 iconify 运行时无关，天然离线可用。
 * - 判据是**前缀级**的：`ep:typo-name`（集对、名字拼错）拦不住——需要加载图标集
 *   数据才能查名字，成本与收益不成比例。
 *
 * 用法：node scripts/guard_offline_icon_prefixes.mjs [--root <repoRoot>] [--report]
 * 退出码：0 通过 / 1 违规 / 2 拿不到输入（结论不可信）
 */

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const argv = process.argv.slice(2);
const rootIdx = argv.indexOf('--root');
const repoRoot =
  rootIdx >= 0 && argv[rootIdx + 1]
    ? argv[rootIdx + 1]
    : join(dirname(fileURLToPath(import.meta.url)), '..');
const reportOnly = argv.includes('--report');

const SRC = join(repoRoot, 'frontend', 'src');
const OFFLINE_REGISTRY = join(
  SRC,
  'components',
  'ReIcon',
  'src',
  'offlineIcon.ts'
);

function unreadable(what) {
  console.error(`[offline-icon] ${what}`);
  console.error(
    '[offline-icon] 数据不完整，本次结论不可信（退出码 2，不得读成「已通过」）'
  );
  process.exit(2);
}

for (const target of [SRC, OFFLINE_REGISTRY]) {
  if (!existsSync(target)) unreadable(`找不到 ${relative(repoRoot, target)}`);
}

const rel = file => relative(repoRoot, file).split(sep).join('/');

/**
 * 去注释。刻意用「行首/空白后才是 `//`」这一条限定：`https://` 里的 `//`
 * 前一个字符是 `:`，不会被当成注释起点（否则整行后半段被吃掉，
 * 可能把 `icon="..."` 一并抹掉，变成静默漏检）。
 * @param {string} text
 */
function stripComments(text) {
  let out = text.replace(/<!--[\s\S]*?-->/g, '');
  out = out.replace(/\/\*[\s\S]*?\*\//g, '');
  out = out
    .split(/\r?\n/)
    .map(line => line.replace(/(^|\s)\/\/.*$/, '$1'))
    .join('\n');
  return out;
}

// ── 判据 1：离线注册集合 ────────────────────────────────────────────────
const registryText = stripComments(readFileSync(OFFLINE_REGISTRY, 'utf8'));

/** @type {Map<string, string>} 本地标识符 -> iconify 前缀 */
const setImports = new Map();
for (const m of registryText.matchAll(
  /import\s*\{\s*icons\s+as\s+([A-Za-z_$][\w$]*)\s*\}\s*from\s*["']@iconify-json\/([^"']+)["']/g
)) {
  setImports.set(m[1], m[2]);
}
for (const m of registryText.matchAll(
  /import\s+([A-Za-z_$][\w$]*)\s+from\s*["']@iconify-json\/([^"']+)["']/g
)) {
  setImports.set(m[1], m[2]);
}

const registered = new Set();
for (const m of registryText.matchAll(/addCollection\s*\(\s*([A-Za-z_$][\w$]*)\s*\)/g)) {
  const prefix = setImports.get(m[1]);
  if (prefix) registered.add(prefix);
}
// addIcon(name, data) 形式无法静态得知集名，忽略——它注册的是离散图标，
// 与本判据（前缀集合）不同维度。

if (registered.size === 0) {
  unreadable(
    `${rel(OFFLINE_REGISTRY)} 里没有解析出任何 addCollection(<import 自 @iconify-json/xxx>)`
  );
}

// ── 判据 2：逐文件的通道归属 ────────────────────────────────────────────
const OFFLINE_MODULES = [
  '@iconify/vue/dist/offline',
  '@/components/ReIcon/src/iconifyIconOffline'
];
const ONLINE_MODULES = ['@iconify/vue'];

/** 从 `@/components/ReIcon` 引入时的名字 -> 通道 */
const REICON_CHANNEL = {
  IconifyIconOffline: 'offline',
  IconifyIconOnline: 'online'
  // FontIcon / useRenderIcon 不是图标集组件，忽略
};

function isOfflineModule(mod) {
  return OFFLINE_MODULES.some(m => mod === m || mod.startsWith(`${m}/`));
}

function isOnlineModule(mod) {
  return ONLINE_MODULES.some(m => mod === m) || mod.endsWith('/ReIcon');
}

/**
 * 解析一个文件的 import，产出「本地名 -> 通道」。
 * 未在此表出现的名字按全局注册处理（见 channelOf）。
 * @param {string} text 已去注释的文件内容
 */
function bindingsOf(text) {
  /** @type {Map<string, 'offline'|'online'>} */
  const bindings = new Map();
  const importRe = /import\s+([\s\S]*?)\s+from\s*["']([^"']+)["']/g;
  for (const m of text.matchAll(importRe)) {
    const clause = m[1];
    const mod = m[2];
    let channel = null;
    if (isOfflineModule(mod)) channel = 'offline';
    else if (isOnlineModule(mod)) channel = 'online';
    if (!channel) continue;

    const named = clause.match(/\{([\s\S]*)\}/);
    if (named) {
      for (const piece of named[1].split(',')) {
        const one = piece.trim();
        if (!one) continue;
        const alias = one.match(/^(?:type\s+)?([A-Za-z_$][\w$]*)(?:\s+as\s+([A-Za-z_$][\w$]*))?$/);
        if (!alias) continue;
        const localName = alias[2] || alias[1];
        const fromReIcon = mod.endsWith('/ReIcon');
        bindings.set(
          localName,
          fromReIcon ? (REICON_CHANNEL[alias[1]] ?? null) : channel
        );
      }
    }
    // default import：`import IconifyIconOffline from ".../iconifyIconOffline"`
    const def = clause.match(/^([A-Za-z_$][\w$]*)\s*(?:,|$)/);
    if (def && !clause.trim().startsWith('{')) bindings.set(def[1], channel);
  }
  // 显式 null（不是图标组件）不该被当成通道，清掉
  for (const [k, v] of bindings) if (v === null) bindings.delete(k);
  return bindings;
}

/** 全局注册的名字（main.ts 的 app.component）兜底 */
function channelOf(name, bindings) {
  if (bindings.has(name)) return bindings.get(name);
  if (name === 'IconifyIconOffline') return 'offline';
  if (name === 'IconifyIconOnline') return 'online';
  return undefined;
}

// ── 判据 3：在离线组件上提取 icon 取值 ──────────────────────────────────
/** 从 `<Name ...>` / `<Name ... />` 的开始位置截出整段标签文本 */
function readTag(text, start) {
  let i = start;
  let quote = null;
  while (i < text.length) {
    const ch = text[i];
    if (quote) {
      if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch;
    } else if (ch === '>') {
      return { tag: text.slice(start, i + 1), end: i + 1 };
    }
    i += 1;
  }
  return { tag: text.slice(start), end: text.length };
}

const ICON_ATTR =
  /(?:^|\s)(?::|v-bind:)?icon\s*=\s*(?:"([^"]*)"|'([^']*)'|\{\s*["'`]([^"'`]*)["'`]\s*\})/g;
// 在一个 icon 取值（可能是三元/模板串）里捞出所有 `prefix:name` 字面量
const ICON_NAME = /[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*/g;

const LINE_OF = text => {
  const starts = [0];
  for (let i = 0; i < text.length; i += 1) if (text[i] === '\n') starts.push(i + 1);
  return idx => {
    let lo = 0;
    let hi = starts.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (starts[mid] <= idx) lo = mid;
      else hi = mid - 1;
    }
    return lo + 1;
  };
};

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === '__tests__') continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.(vue|tsx?|jsx?)$/.test(entry) && !/\.d\.ts$/.test(entry)) out.push(full);
  }
  return out;
}

const violations = [];
let offlineIconCount = 0;

for (const file of walk(SRC)) {
  const raw = readFileSync(file, 'utf8');
  const text = stripComments(raw);
  if (!/icon/i.test(text)) continue;

  const bindings = bindingsOf(text);
  const offlineNames = new Set();
  for (const [name, channel] of bindings) if (channel === 'offline') offlineNames.add(name);
  if (!bindings.has('IconifyIconOffline') && /<IconifyIconOffline\b/.test(text)) {
    offlineNames.add('IconifyIconOffline');
  }
  if (offlineNames.size === 0) continue;

  const lineOf = LINE_OF(text);

  /** 收集一处图标引用：`values` 是可能出现在该处的 icon 取值 */
  const collect = (values, at) => {
    for (const value of values) {
      const names = String(value).match(ICON_NAME);
      if (!names) continue;
      for (const name of names) {
        offlineIconCount += 1;
        const prefix = name.slice(0, name.indexOf(':'));
        if (registered.has(prefix)) continue;
        violations.push(
          `${rel(file)}:${lineOf(at)}  离线通道引用了未注册的图标集「${prefix}」` +
            `（${name}）——离线集只有 ${[...registered].sort().join(', ')}`
        );
      }
    }
  };

  // ① 模板 / JSX 标签：<OfflineComp icon="..." />
  for (const name of offlineNames) {
    const tagStart = new RegExp(`<${name}\\b`, 'g');
    for (const m of text.matchAll(tagStart)) {
      const { tag } = readTag(text, m.index);
      const values = [];
      for (const a of tag.matchAll(ICON_ATTR)) values.push(a[1] ?? a[2] ?? a[3] ?? '');
      if (values.length) collect(values, m.index);
    }
    // ② 渲染函数：h(OfflineComp, { icon: "..." })
    const hCall = new RegExp(`\\bh\\(\\s*${name}\\s*,[\\s\\S]{0,400}?`, 'g');
    for (const m of text.matchAll(hCall)) {
      const window = text.slice(m.index, m.index + 400);
      const values = [];
      for (const a of window.matchAll(/icon\s*:\s*(["'`])([^"'`]*)\1/g)) {
        values.push(a[2]);
      }
      if (values.length) collect(values, m.index);
    }
  }
}

if (offlineIconCount === 0) {
  unreadable(
    '全仓没有扫到任何「离线组件 + 静态 icon 名」——通道判定已与代码脱节，' +
      '此时「0 违规」不可信（检查 bindingsOf 的 import 解析是否还跟得上写法）'
  );
}

if (violations.length > 0) {
  console.error('[offline-icon] 离线图标通道引用了未注册的图标集（#2937）：');
  for (const v of violations) console.error(`  - ${v}`);
  console.error(
    '[offline-icon] 二选一：① 换成本地已注册的图标集（`ep:*`）；② 该图形 `ep` 里没有时，' +
      '按 `components/CloudUploadIcon/index.vue` 的范式内联 SVG（不引入新图标集）。' +
      ' 判据见 scripts/guard_offline_icon_prefixes.mjs'
  );
  if (!reportOnly) process.exit(1);
  console.log(
    `[offline-icon] --report 模式：发现 ${violations.length} 处，退出码 0（同一批判据在 CI 拦阻断）`
  );
} else {
  console.log(
    `[offline-icon] OK：离线通道只用了已注册的 ${[...registered].sort().join(', ')}` +
      `（${offlineIconCount} 处图标引用）`
  );
}
