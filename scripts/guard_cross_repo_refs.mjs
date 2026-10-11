#!/usr/bin/env node
/**
 * 跨仓引用守卫：拦截「本该指向 GitHub、却写成裸 `#N`」的引用。
 *
 * ## WHY（源：CNB issue #2 的踩坑 + 用户实测）
 *
 * CNB 的 issue / PR 正文与评论里，裸 `#123` 一律被解析成**本仓库**（CNB）的编号并渲染成链接：
 * 写「见 GitHub 的 #2050」→ 点进去落到 `cnb.cool/duoduobei/fundmate/-/issues/2050`，  <!-- cross-repo-ref-allow -->
 * 那里根本没有这张卡（CNB 侧只有那批镜像卡 + 首卡）。用户实测撞到，逐字提的：
 * **「你要写完整链接，这样我们才能访问到 GitHub 上面的地址」**。
 *
 * 更隐蔽的是：CNB 侧确实存在同号卡的时候，链接能打开、但打开的是**另一张卡**——
 * 这种「点得开却是错的」比 404 更难发现（换一侧看编号，编号空间完全独立）。
 *
 * 所以规则只有一条：**提到 GitHub 的 issue / PR，前缀必须挂源**。
 * 可接受的三种写法（脚本按前两种查，第三种只有人读得懂，标注后也放行）：
 *
 *   - 完整链接：`https://github.com/imoyao/fundmate/issues/2050`（**首选**）
 *   - 限定形态：`GitHub #2050` / `GH #2050` / `imoyao/fundmate#2050`
 *   - 行内代码里的裸编号：`` `#2050` ``（人读到上下文知道自己指的是 GitHub）
 *
 * 本仓库是「CNB 镜像 + GitHub 原文」双端协作（见 AGENTS.md「双端协作」节），
 * 双端编号是**两个独立空间**，所以这条规则不是风格洁癖，是链接可用性问题。
 *
 * ## 判据（逐行扫，行级豁免优先于行级判据）
 *
 * 正则见 `GH_MARK` 与 `CANDIDATE_RE`：命中「行里有 GitHub 标记、行里还有没被标记的裸 #N」。
 * 命中条件是行级、不是仓库级——**同一文件里讲 CNB 编号的段落不会被误伤**，
 * 这是刻意的：AGENTS.md 那类文件里 `#14`（CNB 里程碑）与 `#2050`（GitHub）混排，
 * 只有「仓库级全或无」会让规则要么失效要么误报。
 *
 * 证据边界：只靠文风提示识别「这行在说 GitHub」必然有假阴性（一句不带任何标记的
 * 「另见 #999」就是）。故守卫尾部打印**裸露高发文件**（正文裸露引用多、且文件本身在讲 GitHub），  <!-- cross-repo-ref-allow -->
 * 提示人工复核；那部分是**报告不是判据**，不影响退出码。
 *
 * ## 存量基线（只管新增）
 *
 * 本守卫上线时全仓有 89 处命中——历史文档、上游项目名（`pytest #3221`）、
 * GitHub Project 编号（`Project #3`）等，多数是误报形态。**一次性改完会把这次修复摊成
 * 90 处无关 diff**，评审反而看不清规则本身；而分级维护会弱化守卫效力。
 * 故取「冻结基线 + 只管新增」：基线键是 `文件|行指纹`（**不是文件名**，
 * 否则已脏文件里新增的引用会跟着蒙混过关），其余一律阻断。
 * 用 `--freeze` 重新生成，守卫还会列出已失效的条目催删档。
 *
 * ## 行级豁免
 *
 * 行内含 `cross-repo-ref-allow` 即跳过该行。三类合法场景：
 *   1. 讲机制本身（本脚本、AGENTS.md 的示例、反例清单）；
 *   2. 代码里的正则 / 字符串字面量（`re.compile(r'... #(\d+)')`）；
 *   3. 本仓（CNB）自己的编号恰好与 GitHub 词同现，如「源 CNB `#2`」。
 * 判据侧另有两道不收窄，配合使用：已挂源的编号靠**区间过滤**放行（不是靠豁免），
 * 行内代码整体剔除后再匹配（所以文档里 `GitHub 编号：#783` 这类示例天然不被判红）。
 *
 * ## 用法
 *
 *     node scripts/guard_cross_repo_refs.mjs            # 扫全仓
 *     node scripts/guard_cross_repo_refs.mjs a.md b.py # 只扫指定文件
 *
 * 回归网与证伪探针见 `scripts/tests/guard_cross_repo_refs.test.js`。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { BASELINE_FILES } from './guard_cross_repo_refs.baseline.mjs';

const ROOT = process.cwd();

/** 扫哪些文件（仓库级：文档 / 脚本 / prompt 都可能被贴进 CNB 评论或镜像卡）。 */
const SCAN_EXT = new Set([
  '.md', '.py', '.js', '.mjs', '.cjs', '.ts', '.vue', '.yml', '.yaml',
  '.sh', '.ps1', '.cmd', '.html', '.txt',
]);

/** 跳过目录：第三方依赖、构建产物、二进制库。 */
const SKIP_DIRS = new Set([
  'node_modules', '.git', '.venv', '__pycache__', 'dist', 'build',
  'coverage', 'playwright-report', 'test-results', '.pdm-build',
]);

/** 单个文件超过这个大小就不扫（生成物 / 数据文件，不是人写的引用）。 */
const MAX_BYTES = 512 * 1024;

/**
 * 「行内在说 GitHub」的标记词。
 * 只收**明确**指向 GitHub 的词：`gh #123` 这种缩写单列，避免裸 `gh` 匹配到拼音 / 变量名。
 */
const GH_WORDS_RE =
  /\b(?:github|ghcr|gh)\b|GitHub\s*#|跨仓|上游仓库|镜像仓|upstream|source-available/i;

/** 完整链接或限定形态（`GitHub #123` / `GH #10` / `GitHub PR #10` / `imoyao/fundmate#10` / `mattupstate/flask-jwt#123`）——命中的编号已被标记。 */
const GH_MARK = /https?:\/\/github\.com\/[^\s)>\]]+|\b(?!github\b)[a-z0-9][a-z0-9_.-]*\/[a-z0-9][a-z0-9_.-]*#\d+|\b(?:github|gh)\b(?:[\s:：]*(?:PR|pr|issue|Issue|卡|号))?[\s:：]*#\d+/gi;

/** 行内的裸编号候选。`(^|\s)` 让它不匹配 `abc#12`（那多半是代码里的标识符）。 */
const CANDIDATE_RE = /(^|\s)#(\d{1,6})\b/g;

/** 统计「行内有 GitHub 词、却一个被标记的编号都没有」的裸露行——报告用，不影响退出码。 */
const REPORT_MIN_HITS = 3;

/** 永久豁免：它本身就是反例清单——每一条「裸 #N」都是被断言的对象，不该也不能改。 */
export const PERMANENT_FILES = new Set(['scripts/tests/guard_cross_repo_refs.test.js']);

/** 基线键：文件 + 行指纹。行文本变了指纹就失效，避免「文件进基线后随便加」。 */
export function baselineKey(file, text) {
  const norm = text.split(' ').filter(Boolean).join(' ');
  return `${file}|${createHash('sha1').update(norm).digest('hex').slice(0, 12)}`;
}

function stripInlineCode(line) {
  return line.replace(/`[^`\n]*`/g, (m) => ' '.repeat(m.length));
}

function walk(dir, out) {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const full = join(dir, name);
    let st;
    try {
      st = statSync(full);
    } catch {
      continue;
    }
    if (st.isDirectory()) {
      walk(full, out);
    } else if (st.isFile()) {
      if (st.size > MAX_BYTES) continue;
      const dot = name.lastIndexOf('.');
      if (dot < 0 || !SCAN_EXT.has(name.slice(dot))) continue;
      out.push(full);
    }
  }
  return out;
}

/** @returns {{hits: Array, exposure: Array}} */
export function scanFiles(paths) {
  const hits = [];
  const exposure = [];
  for (const file of paths) {
    const rel = relative(ROOT, file).split(sep).join('/');
    let text;
    try {
      text = readFileSync(file, 'utf8');
    } catch {
      continue;
    }
    let bareLines = 0;
    let ghLines = 0;
    text.split(/\r?\n/).forEach((line, idx) => {
      if (!GH_WORDS_RE.test(line)) return;
      const stripped = stripInlineCode(line);

      // 已标注源的编号区间（`GitHub #123` / `owner/repo#123` / 完整链接）——这些不该报。
      const marked = [];
      for (const m of stripped.matchAll(GH_MARK)) {
        marked.push([m.index, m.index + m[0].length]);
      }
      if (marked.length) ghLines++;
      else bareLines++;

      if (line.includes('cross-repo-ref-allow')) return;
      for (const m of stripped.matchAll(CANDIDATE_RE)) {
        const start = (m.index || 0) + m[1].length;
        if (marked.some(([a, b]) => start >= a && start < b)) continue;
        hits.push({
          file: rel,
          line: idx + 1,
          number: m[2],
          text: line.trim(),
          column: start + 1,
        });
      }
    });
    if (bareLines >= REPORT_MIN_HITS && bareLines / ghLines > 0.5) {
      exposure.push({ file: rel, bare: bareLines, gh: ghLines });
    }
  }
  return { hits, exposure };
}

function collectTargets(argv) {
  const paths = argv.filter((a) => !a.startsWith('--'));
  if (paths.length) return paths.map((p) => join(ROOT, p));
  return walk(ROOT, []);
}

function main() {
  const args = process.argv.slice(2);
  const files = collectTargets(args);
  const { hits: allHits, exposure } = scanFiles(files);

  if (args.includes('--freeze')) {
    // 冻结 = 把「当前全部命中」写进基线，故**不过滤已有基线**（否则重建会越冻越少）。
    const keys = allHits
      .filter((h) => !PERMANENT_FILES.has(h.file) && !h.file.includes('guard_cross_repo_refs'))
      .map((h) => baselineKey(h.file, h.text));
    console.log([...new Set(keys)].sort().map((k) => `  '${k}',`).join('\n'));
    return;
  }

  const isFrozen = (h) => PERMANENT_FILES.has(h.file) || BASELINE_FILES.has(baselineKey(h.file, h.text));
  const hits = allHits.filter((h) => !isFrozen(h));
  const frozen = allHits.filter(isFrozen);

  for (const h of hits) {
    console.log(`${h.file}:${h.line}:${h.column}: [cross-repo-ref] 裸 #${h.number} —— ${h.text}`);
  }
  if (frozen.length) {
    console.log(`\n存量基线内 ${frozen.length} 处（不阻断；改到那行时顺手挂源，改完从 guard_cross_repo_refs.baseline.mjs 删档）：`);
    for (const h of frozen) console.log(`  ${h.file}:${h.line} 裸 #${h.number}`);
  }
  // 基线里已失效的条目（行文本被改过 / 文件被删）：提示删档，避免基线长成「永远豁免」的垃圾桶
  const live = new Set(allHits.filter((h) => !PERMANENT_FILES.has(h.file)).map((h) => baselineKey(h.file, h.text)));
  const stale = [...BASELINE_FILES].filter((k) => !live.has(k));
  if (stale.length) {
    console.log(`\n基线中已失效 ${stale.length} 条（行已改动 / 已挂源），请从 guard_cross_repo_refs.baseline.mjs 删除：`);
    for (const k of stale.slice(0, 20)) console.log(`  ${k}`);
    if (stale.length > 20) console.log(`  …另有 ${stale.length - 20} 条`);
  }

  if (exposure.length) {
    console.log('\n人工复核（报告，非判据）：以下文件多在讲 GitHub，但正文里有裸露编号：');
    for (const e of exposure) console.log(`  ${e.file}（裸露 ${e.bare} / 提及 GitHub ${e.gh} 行）`);
  }

  if (hits.length) {
    console.log(`\n[cross-repo-ref] 命中 ${hits.length} 处。`);
    console.log('提到 GitHub 的 issue / PR 必须写源，三选一：');
    console.log('  · https://github.com/imoyao/fundmate/issues/2050（首选）');
    console.log('  · GitHub #2050 / imoyao/fundmate#2050');  // cross-repo-ref-allow（示例本身）
    console.log('  · 行内代码 `#2050`（人读上下文知道指 GitHub）');
    console.log('确实不是 GitHub 编号（或本行在讲机制本身），在行尾加 `cross-repo-ref-allow` 豁免。');
    console.log('背景见 AGENTS.md「双端协作（CNB ↔ GitHub）」节。');
    process.exitCode = 1;
    return;
  }

  console.log(`[cross-repo-ref] OK：${files.length} 个文件，无未标注源号的跨仓引用。`);
}

// 被测试 import 时不要执行扫描（否则 `node --test` 一 require 就打印全仓命中、
// 并把 exitCode 置 1，把测试文件本身判成失败）。
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}
