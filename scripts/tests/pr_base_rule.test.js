/**
 * `scripts/pr_base_rule.js` 的回归用例（源 CNB #123）。
 *
 * ## WHY 有这份文件
 *
 * 这份判据的正确性不能靠「看着对」——它要判的是**别处**（真实 PR 列表）的对错，
 * 而它自己出错的方式恰恰是**假绿灯**：判据写松了，违规 PR 会被判成合规，
 * 而「分支乱提」这件事就会继续静默发生（这正是 #123 的起因）。
 *
 * 因此重点用例是三类边界，而不是 happy path：
 *
 *   - `base=main` + `head=feat/x` → **必须红**。这是本次的核心违规形态，
 *     且是**最容易被「理由充分」掉**的一种（「它要跑 cron」）；
 *   - `base=main` + `head=dev` → 绿。这是发版 PR，唯一合法的 main 用法；
 *   - `refs/heads/` 前缀两种写法都要认——CNB API 返回的就是带前缀的形式，
 *     判据只认裸 `dev` 就会把**全部** PR 判成违规（假红灯，同样坏）。
 *
 * ## 怎么跑
 *
 *     node --test "scripts/tests/*.test.js"     # 或根目录 `pnpm test:scripts`
 *
 * 依赖：**零新依赖**（只用 Node 内置 `node:test` / `node:assert`），纯离线。
 */

'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');

const rule = require('../../scripts/pr_base_rule.js');
const {
  normalizeRef,
  isReleasePull,
  checkPullBase,
  findBaseViolations,
  KNOWN_HISTORICAL_VIOLATIONS,
} = rule;

// ---------------------------------------------------------------------------
// 一、ref 归一化（两种写法都要认）
// ---------------------------------------------------------------------------

test('normalizeRef: 去掉 refs/heads/ 前缀', () => {
  assert.equal(normalizeRef('refs/heads/dev'), 'dev');
  assert.equal(normalizeRef('refs/heads/feat/x'), 'feat/x');
  assert.equal(normalizeRef('dev'), 'dev');
});

test('normalizeRef: 非字符串输入不抛异常，返回空串', () => {
  assert.equal(normalizeRef(undefined), '');
  assert.equal(normalizeRef(null), '');
  assert.equal(normalizeRef(123), '');
});

test('normalizeRef: 前后空格容忍（CNB 响应里出现过）', () => {
  assert.equal(normalizeRef('  dev  '), 'dev');
});

// ---------------------------------------------------------------------------
// 二、发版 PR 的判据：head 必须就是 dev
// ---------------------------------------------------------------------------

test('isReleasePull: 只有 head=dev 才算发版', () => {
  assert.equal(isReleasePull('dev'), true);
  assert.equal(isReleasePull('refs/heads/dev'), true);
  assert.equal(isReleasePull('feat/x'), false);
  assert.equal(isReleasePull('docs/1-x'), false);
  assert.equal(isReleasePull('dev-something'), false, '前缀相同但不是 dev 本身，不能算发版');
});

// ---------------------------------------------------------------------------
// 三、核心违规形态：base=main + head=功能分支 → 必须红
// ---------------------------------------------------------------------------

test('checkPullBase: base=main + head=feat/x → 违规（#123 的核心形态）', () => {
  const res = checkPullBase({ number: 999, base: 'main', head: 'feat/bridge-fix' });
  assert.equal(res.ok, false);
  assert.match(res.reason, /base=main/);
  assert.equal(res.expectedBase, 'dev');
});

test('checkPullBase: base=main + head=docs/x → 违规', () => {
  const res = checkPullBase({ number: 998, base: 'main', head: 'docs/118-mirror-route' });
  assert.equal(res.ok, false);
});

test('checkPullBase: base=main + head=fix/x → 违规（即使理由听起来合理）', () => {
  const res = checkPullBase({ number: 997, base: 'main', head: 'fix/118-mirror-snapshot-header' });
  assert.equal(res.ok, false);
});

test('checkPullBase: CNB 带前缀写法同样抓到 base=main 的违规', () => {
  const res = checkPullBase({ number: 996, base: 'refs/heads/main', head: 'refs/heads/feat/x' });
  assert.equal(res.ok, false);
});

// ---------------------------------------------------------------------------
// 四、正向：发版 PR 与普通功能 PR 都要绿
// ---------------------------------------------------------------------------

test('checkPullBase: base=main + head=dev → 合规（发版 PR）', () => {
  const res = checkPullBase({ number: 1, base: 'main', head: 'dev' });
  assert.equal(res.ok, true);
  assert.match(res.reason, /发版/);
});

test('checkPullBase: base=dev → 一律合规，与 head 无关', () => {
  for (const head of ['feat/x', 'fix/y', 'docs/z', 'auto/mirror-correction-ledger']) {
    const res = checkPullBase({ number: 2, base: 'dev', head });
    assert.equal(res.ok, true, `head=${head} 应为合规`);
  }
});

// ---------------------------------------------------------------------------
// 五、其它非法 base
// ---------------------------------------------------------------------------

test('checkPullBase: base 是第三条分支 → 违规', () => {
  const res = checkPullBase({ number: 3, base: 'staging', head: 'feat/x' });
  assert.equal(res.ok, false);
  assert.match(res.reason, /不是合法目标分支/);
});

test('checkPullBase: 缺 base 或 head → 违规（不静默放过）', () => {
  assert.equal(checkPullBase({ number: 4, head: 'feat/x' }).ok, false);
  assert.equal(checkPullBase({ number: 5, base: 'dev' }).ok, false);
  assert.equal(checkPullBase({}).ok, false);
});

// ---------------------------------------------------------------------------
// 六、批量：豁免要生效，且不能把别人的违规一起豁免掉
// ---------------------------------------------------------------------------

test('findBaseViolations: 空输入 → 无违规', () => {
  assert.deepEqual(findBaseViolations([]), []);
  assert.deepEqual(findBaseViolations(undefined), []);
});

test('findBaseViolations: 只报违规项，合规项不出现', () => {
  const out = findBaseViolations([
    { number: 10, base: 'dev', head: 'feat/a' },
    { number: 11, base: 'main', head: 'dev' },
    { number: 12, base: 'main', head: 'feat/b' },
  ]);
  assert.equal(out.length, 1);
  assert.equal(out[0].number, 12);
});

test('findBaseViolations: 豁免编号被跳过，未豁免的仍被抓', () => {
  const out = findBaseViolations(
    [
      { number: 114, base: 'main', head: 'feat/github-issue-cnb-mirror' },
      { number: 130, base: 'main', head: 'feat/new-one' },
    ],
    { exemptNumbers: [114] }
  );
  assert.equal(out.length, 1);
  assert.equal(out[0].number, 130, '豁免不能变成「全都放行」');
});

test('findBaseViolations: 违规项带着 base/head 原值，便于人直接定位', () => {
  const out = findBaseViolations([{ number: 20, base: 'refs/heads/main', head: 'refs/heads/feat/x' }]);
  assert.equal(out[0].base, 'main');
  assert.equal(out[0].head, 'feat/x');
});

// ---------------------------------------------------------------------------
// 七、白名单自身的纪律：每条都要有编号与原因（防「顺手加个号」）
// ---------------------------------------------------------------------------

test('KNOWN_HISTORICAL_VIOLATIONS: 每条都有编号与非空原因', () => {
  assert.ok(KNOWN_HISTORICAL_VIOLATIONS.length > 0, '至少有 #123 实测出的那几条');
  for (const item of KNOWN_HISTORICAL_VIOLATIONS) {
    assert.equal(typeof item.number, 'number');
    assert.ok(item.number > 0);
    assert.equal(typeof item.reason, 'string');
    assert.ok(item.reason.trim().length >= 4, `#${item.number} 的豁免原因太短，等于没写`);
  }
});

test('KNOWN_HISTORICAL_VIOLATIONS: 编号不重复', () => {
  const nums = KNOWN_HISTORICAL_VIOLATIONS.map((x) => x.number);
  assert.equal(new Set(nums).size, nums.length);
});

// ---------------------------------------------------------------------------
// 八、冻结契约：常量本身是判据的一部分，改动必须是有意的
// ---------------------------------------------------------------------------

test('契约: 集成分支是 dev、稳定分支是 main', () => {
  assert.equal(rule.INTEGRATION_BRANCH, 'dev');
  assert.equal(rule.RELEASE_BRANCH, 'main');
});
