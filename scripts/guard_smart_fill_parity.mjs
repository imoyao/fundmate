/**
 * 守卫：导入预览的「金额 ÷ 份额 补单价」只允许一份实现（#2903）。
 *
 * ## 为什么需要这个守卫
 *
 * 同一条规则曾经在 `useImportWizard.ts` 里写了两份：AI / OCR 通道一份（无守卫）、
 * 文件上传通道一份（4 条件守卫），计算式逐字相同。两份很快漂移成**互相矛盾**——
 * 文件通道拿 `!isRowBlocked` 当门禁，而 `isRowBlocked` 在「单价缺失」时恒为 true，
 * 方向恰好写反：该补的普通成交行一个没补，不该补的税额 / 兑付 / 分红行全补了。
 *
 * 改完代码不等于改完机制。没有判据，下一个人再内联一份补价就会悄悄回到原样，
 * 而它**不会报错**——只是两条通道的结果又不一致了。本守卫抓的正是那个具体回潮形态：
 * 「另起一份补价并打 `smartFilled` 标记」。
 *
 * ## 判据
 *
 * 1. `smartFilled = true` 只允许出现在 `cellEditLogic.ts`（行内编辑补缺项，含补数量方向）
 *    与 `smartFillPrice.ts`（装载时补价）——两者都是单点实现，其余文件一律不许；
 * 2. `useImportWizard.ts` 至少调用 `fillSmartPrice(` 两次：OCR 与文件两条通道各一次
 *    （少一处就等于某条通道没接线，而纯函数测试全绿也看不出来）；
 * 3. 目标文件缺失 ⇒ 退出码 2。拿不到输入不得退化成绿（仓内纪律：空 ≠ 没拿到）。
 *
 * ## 边界（已知不覆盖，别把它当万能闸门）
 *
 * 不试图用正则识别任意形式的「除法 + toFixed」：`useImportWizard.ts` 里还有
 * `amount / nav → 份额`（净值推算）与 `autoFillMissing`（用户显式点按钮、且要处理
 * 缺数量方向），同形不同义，一律拦下会逼着后来的人绕过守卫。
 * 判据宁可窄——拦不住的东西，写成「拦住了」比没写更糟。
 *
 * 用法：node scripts/guard_smart_fill_parity.mjs [--root <repoRoot>]
 * 退出码：0 通过 / 1 违规 / 2 拿不到输入
 */

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const argv = process.argv.slice(2);
const rootIdx = argv.indexOf('--root');
const repoRoot =
  rootIdx >= 0 && argv[rootIdx + 1]
    ? argv[rootIdx + 1]
    : join(dirname(fileURLToPath(import.meta.url)), '..');

const IMPORT_DIR = join(
  repoRoot,
  'frontend',
  'src',
  'views',
  'asset',
  'investment',
  'import'
);
const COMPOSABLES = join(IMPORT_DIR, 'composables');
const WIZARD = join(COMPOSABLES, 'useImportWizard.ts');
const SMART_FILLED_ALLOW = [
  join(COMPOSABLES, 'cellEditLogic.ts'),
  join(COMPOSABLES, 'smartFillPrice.ts')
];

function unreadable(what) {
  console.error(`[smart-fill] ${what}`);
  console.error('[smart-fill] 数据不完整，本次结论不可信（退出码 2，不得读成「已通过」）');
  process.exit(2);
}

for (const file of [WIZARD, ...SMART_FILLED_ALLOW]) {
  if (!existsSync(file)) unreadable(`找不到 ${relative(repoRoot, file)}`);
}

/** 递归收集 .ts / .vue；测试目录不参与判据（那里构造回退探针是合法的）。 */
function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === '__tests__') continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.(ts|vue)$/.test(entry)) out.push(full);
  }
  return out;
}

const violations = [];

// 判据 1：smartFilled 的唯一写者
for (const file of walk(IMPORT_DIR)) {
  const text = readFileSync(file, 'utf8');
  const lines = text.split(/\r?\n/);
  lines.forEach((line, i) => {
    if (!/\.smartFilled\s*=\s*true/.test(line)) return;
    if (SMART_FILLED_ALLOW.includes(file)) return;
    violations.push(
      `${relative(repoRoot, file)}:${i + 1} 手写补价标记（补价只允许走 smartFillPrice.fillSmartPrice）`
    );
  });
}

// 判据 2：两条通道都接线
// 计数排除 import 行：OCR 通道是 `normalized.forEach(fillSmartPrice)`（函数引用、
// 没有括号），所以不能按 `fillSmartPrice(` 数——按「出现该标识符的非 import 行」数。
const wizardText = readFileSync(WIZARD, 'utf8');
const wiredLines = wizardText
  .split(/\r?\n/)
  .filter(line => /\bfillSmartPrice\b/.test(line) && !/^\s*import\b/.test(line));
if (wiredLines.length < 2) {
  violations.push(
    `${relative(repoRoot, WIZARD)} 只找到 ${wiredLines.length} 处 fillSmartPrice 使用，` +
      '两条导入通道（OCR / 文件上传）都必须接线'
  );
}

if (violations.length > 0) {
  console.error('[smart-fill] 智能补价出现了不止一份实现（#2903）：');
  for (const v of violations) console.error(`  - ${v}`);
  console.error(
    '[smart-fill] 判据见 scripts/guard_smart_fill_parity.mjs；补价判据与计算式只能有一份，' +
      '改口径请改 frontend/src/views/asset/investment/import/composables/smartFillPrice.ts'
  );
  process.exit(1);
}

console.log('[smart-fill] OK：补价单一实现，两条通道均已接线');
