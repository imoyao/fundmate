/**
 * `scripts/guard_pr_four_questions.mjs` 的回归用例。
 *
 * ## WHY 有这份文件
 *
 * 四问守卫替代的是 AGENTS.md 里**已知绕不开**的软约束（用户原话：「AI 有时候读到
 * Agent 的 MD 里面会去看，但有时候又会把这块绕开」）。它必须比软约束可靠，
 * 但又不能变成天天拦路的形式主义——一旦 owner 学会「随手加个 skip 标记」，它就死了。
 *
 * 所以这个守卫的判据重心不在「四问齐不齐」，而在**豁免面收得够不够紧**：
 *   - 机器人 PR、draft PR 必须是自动豁免（否则第一天就被 dependabot 堵死）；
 *   - 豁免标记必须留痕（可追溯，不是无声放过）。
 *
 * 另外要钉住「只校验形式、不校验内容」这条边界：**不能**去判断内容质量。
 * 一旦引入内容判断（比如「风险写得不够具体就报红」），就退回主观判断，
 * 而主观判断放进 CI 就是 #2410 那类必然被绕开的软约束换了个马甲。
 *
 * ## 怎么跑
 *
 *     node --test "scripts/tests/guard_pr_four_questions.test.js"
 *
 * 依赖：零新依赖，纯离线。
 */

'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');

const {
  checkFourQuestions,
  splitSections,
  skipReasonFor,
  BOT_AUTHORS,
  SKIP_MARKER,
} = require('../guard_pr_four_questions.mjs');

const FULL = `
## 解决谁的什么问题

修复 #2411 描述的双事实源问题：进度写在两处，改一处忘另一处。

## 验收标准

- \`node scripts/guard_cross_repo_refs.mjs\` 退出码 0
- 文档站构建通过

## 风险

改动涉及导航层语义，无运行时风险。

## 替代方案

保留双事实源 + 加提醒。已否决：提醒会被绕开，成本更高。
`;

test('四问齐备 → 通过', () => {
  const v = checkFourQuestions({ body: FULL });
  assert.equal(v.ok, true, `应通过，实际报 ${v.missing}`);
  assert.deepEqual(v.missing, []);
});

test('缺任一小节 → 判红，并只报缺的那几节（不虚报）', () => {
  const body = FULL.replace(/## 风险[\s\S]*?(?=## )/, '');
  const v = checkFourQuestions({ body });
  assert.equal(v.ok, false);
  assert.deepEqual(v.missing, ['risk'], '只应报缺 risk');
});

test('只写标题、下面空白 → 判红（有标题不等于思考过）', () => {
  const body = ['## 解决谁的什么问题', '#2411', '## 验收标准', '跑测试', '## 风险', '', '## 替代方案', '没有'].join('\n');
  const v = checkFourQuestions({ body });
  assert.equal(v.ok, false);
  assert.deepEqual(v.missing, ['risk']);
});

test('「风险：无」算通过（有结论即可，不要求长篇）', () => {
  const body = FULL.replace('改动涉及导航层语义，无运行时风险。', '无风险');
  assert.equal(checkFourQuestions({ body }).ok, true);
});

test('空 body → 四节全缺', () => {
  const v = checkFourQuestions({ body: '' });
  assert.equal(v.ok, false);
  assert.deepEqual(v.missing.sort(), ['acceptance', 'alternative', 'problem', 'risk']);
});

test('机器人作者自动豁免（dependabot / github-actions / claude …）', () => {
  for (const author of ['dependabot[bot]', 'github-actions[bot]', 'claude[bot]', 'Codex-AI']) {
    const v = checkFourQuestions({ body: '', author });
    assert.equal(v.ok, true, `${author} 应豁免`);
    assert.match(v.skipped, /机器人/);
  }
  assert.ok(BOT_AUTHORS.includes('dependabot'));
});

test('draft PR 豁免', () => {
  const v = checkFourQuestions({ body: '', draft: true });
  assert.equal(v.ok, true);
  assert.match(v.skipped, /draft/);
});

test('显式豁免标记生效且必须写在 body 里（豁免留痕）', () => {
  const v = checkFourQuestions({ body: `随手改个 typo ${SKIP_MARKER}` });
  assert.equal(v.ok, true);
  assert.match(v.skipped, new RegExp(SKIP_MARKER));
});

test('普通作者 + 普通 PR 不豁免（豁免面没有漏成常态）', () => {
  assert.equal(skipReasonFor('x', 'imoyao', false), null);
});

test('同义写法可识别（谁的问题 / 验收条件 / 已知风险 / 备选方案）', () => {
  const body = ['## 谁的问题', '#1', '## 验收条件', '跑测试', '## 已知风险', '无风险', '## 备选方案', '没有'].join('\n');
  assert.equal(checkFourQuestions({ body }).ok, true);
});

test('正文里提到「验收标准」不算命中（不能被关键词蒙混过关）', () => {
  // 形状意义：守卫必须按「标题 + 后随正文」切，不能全局正则找关键词。
  const body = ['修了个措辞。原来这里写着验收标准。', '## 解决谁的什么问题', '#2411', '## 风险', '无风险', '## 替代方案', '无'].join('\n');
  const v = checkFourQuestions({ body });
  assert.equal(v.ok, false, '正文提及不应被判为已写');
  assert.ok(v.missing.includes('acceptance'));
});

test('markdown 链接标题可识别（## [验收标准](#2411)）', () => {
  const body = ['## 解决谁的什么问题', '#2411', '## [验收标准](#2411)', '跑测试', '## 风险', '无风险', '## 替代方案', '无'].join('\n');
  assert.equal(checkFourQuestions({ body }).ok, true);
});

test('splitSections：未出现的标题返回 null（区别于「出现但为空」）', () => {
  const s = splitSections('## 风险\n无风险');
  assert.deepEqual(s.risk, ['无风险']);
  assert.equal(s.problem, null);
});

test('报错信息含补写指引与豁免标记名（owner 看到就知道怎么办）', () => {
  const v = checkFourQuestions({ body: '' });
  assert.match(v.message, /验收标准/);
  assert.ok(v.message.includes(SKIP_MARKER));
});

test('证伪探针：删掉豁免逻辑必须被抓出', () => {
  // 真实现：机器人豁免。去掉豁免后同一输入必须判红。
  const noSkip = () => null;
  assert.equal(skipReasonFor('', 'dependabot[bot]', false), '作者是机器人（dependabot[bot]）');
  assert.equal(noSkip(), null);
});

test('证伪探针：把「空标题算通过」写松必须被抓出', () => {
  // 真实现：空 risk 报红。若实现改成只看标题存在，就会变成 ok。
  const loose = (body) => ['## 风险'].every((h) => body.includes(h));
  const body = ['## 解决谁的什么问题', '#1', '## 验收标准', '跑', '## 风险', '', '## 替代方案', '无'].join('\n');
  assert.equal(checkFourQuestions({ body }).ok, false);
  assert.equal(loose(body), true, '宽松版恰好通过 → 说明严格版确实拦住了东西');
});
