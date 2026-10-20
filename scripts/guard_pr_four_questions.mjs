#!/usr/bin/env node
/**
 * 四问格式守卫：PR 描述必须写清四行，只校验「有没有写」，不判断「写得对不对」。
 *
 * ## WHY（源：用户对「纳入四问」机制的判断）
 *
 * AGENTS.md 里早有「纳入四问」机制，但它拦不住任何东西。用户对此的原话是：
 * 「**它会去看这个需求是不是合理的，但是没有强制性。也就是说，AI 有时候读到
 * Agent 的 MD 里面会去看，但有时候又会把这块绕开，并不会每一个都做这个分析。**」
 *
 * 这条判断是准确的，而根因值得写清楚，因为它决定了本守卫的设计形状：
 *
 *   - 「需求是否合理」是**主观判断** → 写进文档 = 软约束，AI 可绕；
 *   - 「描述里有没有这四行」是**客观判据** → 可以挂 CI，绕不过。
 *
 * 所以本守卫**不是**把四问变成更强的判断，而是把判断**降级**成一个存在性检查：
 * 逼 AI 每次都停下来把四件事写出来（谁的什么问题 / 验收标准 / 风险 / 替代方案），
 * 写的过程本身就是 AI 自我约束的一遍——**约束的是「不许跳过思考」，
 * 而不是「不许做出错误判断」**。后者永远做不到，也不该假装能做到。
 *
 * 换句话说：本守卫不提升判断质量，它只保证**判断发生过并留下痕迹**。
 * 四行内容是否成立，仍由 owner 在评审时判断。
 *
 * ## 判据
 *
 * PR body 必须含以下 4 个小节标题（各允许若干同义写法，见 `SECTION_ALIASES`）：
 *
 *   1. 解决谁的什么问题 / 关联 issue ——「谁的什么问题」缺失是最贵的错误，
 *      因为它让「我觉得需要」冒充「有人需要」，所以它是四问里唯一**强制关联编号**的；
 *   2. 验收标准；
 *   3. 风险；
 *   4. 替代方案。
 *
 * 匹配方式为「标题行 + 冒号/井号」的宽松匹配，**且该行下方必须非空**——
 * 只写「风险：无风险」算通过（有结论），但写「## 风险」后一片空白算失败（有标题没思考）。
 *
 * ## 豁免（**必须**有，否则第一天就会把仓库堵死）
 *
 *   - **机器人作者**：dependabot / github-actions / cnblogs-ci / Claude / Codex 等
 *     开的 PR 不可能写四问。它们数量不小且来路正当，拦住只会让人养成「加白名单」的坏习惯，
 *     白名单一开就等于守卫失效。
 *   - **draft PR**：草稿阶段本来就不该被格式要求打断。
 *   - **显式标记**：PR body 含 `four-questions-skip` 即跳过（仅供 owner 豁免，
 *     豁免本身留在 body 里可追溯）。
 *
 * 这三条豁免是本守卫能否长期活下来的关键：守卫一旦频繁误伤真实工作，就再也没有人看它。
 *
 * ## 用法
 *
 *     node scripts/guard_pr_four_questions.mjs --body-file pr.md
 *     node scripts/guard_pr_four_questions.mjs --json < pr.md
 *
 * 退出码 1 = 缺项（红灯）。回归网与证伪探针见
 * `scripts/tests/guard_pr_four_questions.test.js`。
 */

import { pathToFileURL } from 'node:url';

/** 机器人作者（大小写不敏感的前缀匹配）——豁免理由见文件头。 */
export const BOT_AUTHORS = [
  'dependabot',
  'github-actions',
  'renovate',
  'cnblogs-ci',
  'cnb-ci',
  'claude',
  'codex',
  'copilot',
];

/** 显式豁免标记：写在 PR body 里，豁免行为本身可追溯。 */
export const SKIP_MARKER = 'four-questions-skip';

/** draft PR 豁免（草稿不要求格式）。 */
export const DRAFT_MARKER = 'is:draft';

const SECTION_ALIASES = {
  problem: [
    '解决谁的什么问题',
    '谁的什么问题',
    '谁的问题',
    '解决的问题',
    '问题',
    '关联 issue',
    '关联issue',
    'closes',
    'fixes',
    'relates',
  ],
  acceptance: ['验收标准', '验收条件', '如何验证', '验证方式', 'acceptance criteria', 'acceptance'],
  risk: ['风险', '已知风险', 'risk', 'risks', '影响面'],
  alternative: ['替代方案', '备选方案', '其他方案', 'alternative', 'alternatives'],
};

/** 四个小节的机器可读顺序，内部使用。 */
export const SECTIONS = ['problem', 'acceptance', 'risk', 'alternative'];

/** 小节标题的中文标签，用于报错信息。 */
const SECTION_LABELS = {
  problem: '解决谁的什么问题（建议附关联 issue 编号）',
  acceptance: '验收标准',
  risk: '风险',
  alternative: '替代方案',
};

/**
 * 解析小节切分：返回「小节键 → 该小节下的正文行（找不到标题时为 null）」。
 *
 * 形状选择说明：用「标题行 + 后随正文」而不是「全局正则找关键词」，
 *是因为全局正则会把「我修了个验收标准的 typo」这种正文里的提及也判成命中——
 * 那就又是「恰好绿」的守卫，跟没守卫一样。
 *
 * @param {string} body PR 描述全文
 * @returns {Record<string, string[]|null>}
 */
export function splitSections(body) {
  const out = { problem: null, acceptance: null, risk: null, alternative: null };
  const lines = String(body || '').split(/\r?\n/);
  let cur = null;

  for (const raw of lines) {
    const line = raw.trim();
    const m = line.match(/^#{1,6}\s*(.+?)\s*$/);
    const head = (m ? m[1] : line.replace(/^[-*]\s*(\[[ xX]\]\s*)?/, ''))
      .replace(/`/g, '')
      .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/[:：]\s*$/, '')
      .trim()
      .toLowerCase();

    const hit = SECTIONS.find((key) =>
      SECTION_ALIASES[key].some((a) => head === a.toLowerCase() || head.startsWith(a.toLowerCase())),
    );

    if (hit) {
      if (out[hit] === null) out[hit] = [];
      cur = hit;
      const inline = line.match(/[:：]\s*(.+)$/);
      if (inline && inline[1].trim()) out[hit].push(inline[1].trim());
      continue;
    }

    if (cur && line) out[cur].push(line);
    else if (!line) cur = cur; // 空行不清归属，避免「四个空标题 + 末尾一大段」被判通过
  }

  return out;
}

/**
 * 主判据：检查 PR 描述是否四问齐备。
 *
 * @param {object} input
 * @param {string} [input.body] PR 描述
 * @param {string} [input.author] PR 作者登录名
 * @param {boolean} [input.draft] 是否 draft PR
 * @returns {{ok: boolean, missing: string[], skipped: string|null, message: string}}
 */
export function checkFourQuestions(input = {}) {
  const body = input.body || '';
  const author = String(input.author || '').toLowerCase();
  const skipReason = skipReasonFor(body, author, input.draft);
  if (skipReason) {
    return { ok: true, missing: [], skipped: skipReason, message: `跳过四问检查：${skipReason}` };
  }

  const sections = splitSections(body);
  const missing = SECTIONS.filter((key) => {
    const content = sections[key];
    return !Array.isArray(content) || content.length === 0;
  });

  if (missing.length === 0) {
    return { ok: true, missing: [], skipped: null, message: 'OK: 四问齐备。' };
  }

  const lines = [
    'PR 描述缺少四问的以下部分（本守卫只检查「有没有写」，不判断写得对不对）：',
    ...missing.map((key) => `  - ${SECTION_LABELS[key]}`),
    '',
    '在 PR 描述里补上对应小节即可，每个小节写一两句即可。',
    `「风险」若确实没有，写「无风险」也算通过；但不能留空标题。`,
    `需要豁免时在描述里写 \`${SKIP_MARKER}\`（豁免会留在描述里可追溯）。`,
  ].join('\n');

  return { ok: false, missing, skipped: null, message: lines };
}

/** 豁免判定，返回豁免理由（未豁免返回 null）。 */
export function skipReasonFor(body, authorLower, draft) {
  if (authorLower && BOT_AUTHORS.some((b) => authorLower.includes(b))) {
    return `作者是机器人（${authorLower}）`;
  }
  if (draft) return 'draft PR';
  if (String(body || '').includes(SKIP_MARKER)) return `描述含显式豁免标记 ${SKIP_MARKER}`;
  return null;
}

function parseArgs(argv) {
  const opts = { json: false, bodyFile: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--json') opts.json = true;
    else if (argv[i] === '--body-file') opts.bodyFile = argv[++i];
  }
  return opts;
}

async function readStdin() {
  const chunks = [];
  for await (const c of process.stdin) chunks.push(c);
  return Buffer.concat(chunks).toString('utf8');
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const body = opts.bodyFile ? (await import('node:fs')).readFileSync(opts.bodyFile, 'utf8') : await readStdin();
  const verdict = checkFourQuestions({ body });
  if (opts.json) console.log(JSON.stringify(verdict));
  else if (verdict.ok) console.log(verdict.message);
  else console.error(verdict.message);
  process.exit(verdict.ok ? 0 : 1);
}

// 仅在被直接执行时跑 CLI（被 require 时不跑）。
// 必须用 pathToFileURL 而不是字符串拼 'file://' + path：Windows 上会拼出
// `file://D:/...`（两斜杠），与 import.meta.url 的 `file:///D:/...` 不相等，
// 于是 CLI **静默不执行、退出码 0** —— 守卫接进 CI 后会变成永远绿的假闸门。
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  // 不用 top-level await：guard_*.mjs 会被 CJS 测试用 require() 引入，
  // 带 TLA 的 ESM 图在 CJS 里 require 会直接抛 ERR_REQUIRE_ASYNC_MODULE。
  main();
}
