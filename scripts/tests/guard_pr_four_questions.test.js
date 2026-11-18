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
  hasEvidence,
  acceptanceItemsWithoutEvidence,
  BOT_AUTHORS,
  SKIP_MARKER,
} = require('../guard_pr_four_questions.mjs');

const FULL = `
## 解决谁的什么问题

修复 #2411 描述的双事实源问题：进度写在两处，改一处忘另一处。

## 验收标准

- \`node scripts/guard_cross_repo_refs.mjs\` 退出码 0
- 文档站构建通过（走查：CI docs job 绿）

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
  const body = ['## 解决谁的什么问题', '#2411', '## 验收标准', '跑测试（判据：CI 全绿）', '## 风险', '', '## 替代方案', '没有'].join('\n');
  const v = checkFourQuestions({ body });
  assert.equal(v.ok, false);
  assert.deepEqual(v.missing, ['risk']);
  assert.deepEqual(v.missing_evidence, [], '章节缺失时不应再叠加判据噪音');
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
  const body = ['## 谁的问题', '#1', '## 验收条件', '跑测试（判据：CI 全绿）', '## 已知风险', '无风险', '## 备选方案', '没有'].join('\n');
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
  const body = ['## 解决谁的什么问题', '#2411', '## [验收标准](#2411)', '跑测试（判据：CI 全绿）', '## 风险', '无风险', '## 替代方案', '无'].join('\n');
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

// ─────────────────────────────────────────────────────────────
// 第二层判据：验收标准每条须带判据引用（#2449）
//
// 源起 owner 的判断：「先有实现、后补判据」是反复出现的返工模式；
// 若开写前就要求逐条写「这条验收用什么测试钉」，比收口时补课省力。
// 注意边界：这些用例全部钉「有没有写判据」，**没有一条**钉判据质量——
// 后者是主观判断，放进 CI 就是 #2410 那类必然被绕开的软约束换马甲。
// ─────────────────────────────────────────────────────────────

const evidence = (acceptanceLine, rest = ['## 风险', '无风险', '## 替代方案', '无']) =>
  ['## 解决谁的什么问题', '#2449', '## 验收标准', acceptanceLine, ...rest].join('\n');

test('验收项带反引号判据 → 通过', () => {
  assert.equal(checkFourQuestions({ body: evidence('- [x] `test_x.py::test_y` 全绿') }).ok, true);
});

test('验收项带冒号标记判据 → 通过（测试/判据/走查/验证/复算/人工 均认）', () => {
  for (const marker of ['测试：', '判据：', '走查：', '验证：', '复算：', '人工：']) {
    assert.equal(checkFourQuestions({ body: evidence(`- [x] 界面更清爽（${marker}dev 截图）`) }).ok, true, `${marker} 应算判据`);
  }
});

test('真机走查类验收：无测试名但写「走查：」即合格', () => {
  // 这是机制刻意留的口子：不是所有验收都能自动化，逼不出测试名就会逼出废话。
  const body = evidence('- [ ] 亮/暗两种主题各截图（走查：dev 环境切换主题对比）');
  assert.equal(checkFourQuestions({ body }).ok, true);
});

test('验收项无任何判据引用 → 判红，且报出具体条目', () => {
  const v = checkFourQuestions({ body: evidence('- [x] 界面更清爽了\n- [x] 大账户不卡') });
  assert.equal(v.ok, false);
  assert.deepEqual(v.missing, [], '章节层面齐备，只缺判据');
  assert.equal(v.missing_evidence.length, 2);
  assert.match(v.missing_evidence[0], /界面更清爽/);
  assert.match(v.message, /拿什么验/);
});

test('混编：只有无判据的那条被报出来（不虚报）', () => {
  const v = checkFourQuestions({ body: evidence('- [x] `pnpm typecheck` 通过\n- [x] 大账户不卡') });
  assert.equal(v.ok, false);
  assert.equal(v.missing_evidence.length, 1);
  assert.match(v.missing_evidence[0], /大账户不卡/);
});

test('表格行验收：管道前缀剥掉后再判断', () => {
  const ok = evidence('| 验收项 | 判据 |\n| --- | --- |\n| 构建通过 | 走查：CI 绿 |');
  assert.equal(checkFourQuestions({ body: ok }).ok, true);
  const bad = evidence('| 构建通过 | 无 |');
  assert.equal(checkFourQuestions({ body: bad }).ok, false);
});

test('纯文字验收段（无列表）同样要求判据', () => {
  assert.equal(checkFourQuestions({ body: evidence('跑一下测试就行') }).ok, false);
  assert.equal(checkFourQuestions({ body: evidence('跑一下测试（判据：CI 全绿）') }).ok, true);
});

test('豁免仍优先于判据检查（skip 后不再要求判据）', () => {
  const v = checkFourQuestions({ body: `随手改个 typo ${SKIP_MARKER}` });
  assert.equal(v.ok, true);
  assert.deepEqual(v.missing_evidence, []);
});

test('证伪探针：去掉判据检查必须被抓出', () => {
  // 真实现：无判据验收项报红。若退化成「只要写了验收节就算过」，同一输入变绿——
  // 那就退回第一版守卫的失败模式（愿望清单无人拦）。
  const firstGen = (body) => splitSections(body).acceptance !== null;
  const body = evidence('- [x] 界面更清爽了');
  assert.equal(checkFourQuestions({ body }).ok, false, '真实现必须判红');
  assert.equal(firstGen(body), true, '第一版恰好通过 → 说明第二层判据确实拦住了新东西');
});

test('hasEvidence / acceptanceItemsWithoutEvidence 单测（形状稳定）', () => {
  assert.equal(hasEvidence('`test_a.py::test_b`'), true);
  assert.equal(hasEvidence('「test_a」'), true);
  assert.equal(hasEvidence('走查：截图'), true);
  assert.equal(hasEvidence('无任何引用'), false);
  assert.deepEqual(acceptanceItemsWithoutEvidence(null), []);
  assert.deepEqual(acceptanceItemsWithoutEvidence(['- [x] 有判据 `x`', '- [ ] 没判据']), ['没判据']);
});

// ─────────────────────────────────────────────────────────────
// 第三层判据：HTML 注释不算「写过」（模板预填不得变成假绿）
//
// 背景：2026-11-18 加了 `.github/PULL_REQUEST_TEMPLATE.md`，模板里只能靠 HTML 注释
// 写填写提示（渲染时不显示）。若注释被当成小节内容，一份**没人动过的模板**直接判绿
// ——那不是省事，是把守卫关掉了还留着灯。
// ─────────────────────────────────────────────────────────────

test('小节只有 HTML 注释占位 → 判红（否则模板预填＝假绿）', () => {
  const body = [
    '## 解决谁的什么问题',
    '<!-- 一句话：谁被卡住了 -->',
    '## 验收标准',
    '<!-- 每条带判据 -->',
    '## 风险',
    '<!-- 没有就写无风险 -->',
    '## 替代方案',
    '<!-- 为什么不用另一种做法 -->',
  ].join('\n');
  const v = checkFourQuestions({ body });
  assert.equal(v.ok, false, '注释是占位，不是思考过的痕迹');
  assert.deepEqual(v.missing.sort(), ['acceptance', 'alternative', 'problem', 'risk']);
});

test('跨行注释同样不算内容（模板顶部那段多行说明）', () => {
  const body = ['## 风险', '<!--', '多行提示', '仍然只是提示', '-->'].join('\n');
  assert.deepEqual(splitSections(body).risk, [], '标题在、但内容只剩注释 ⇒ 空');
  assert.equal(checkFourQuestions({ body }).ok, false);
});

test('注释与真实内容混排 → 不影响判定（注释不该反过来误伤）', () => {
  const body = [
    '<!-- 顶部说明 -->',
    '## 解决谁的什么问题',
    '#3174 <!-- 关联卡 -->',
    '## 验收标准',
    '- [x] `node scripts/guard_pr_four_questions.mjs --body-file pr.md` 退出码 0 <!-- 命令 -->',
    '## 风险',
    '无风险 <!-- 已确认 -->',
    '## 替代方案',
    '不写模板，每次手抄',
  ].join('\n');
  assert.equal(checkFourQuestions({ body }).ok, true);
});

test('验收条目只剩注释占位 → 判红（在「缺判据」这一层拦住）', () => {
  const body = evidence('- [x] 界面更清爽了 <!-- 待补判据 -->');
  const v = checkFourQuestions({ body });
  assert.equal(v.ok, false);
  assert.equal(v.missing_evidence.length, 1);
  assert.match(v.missing_evidence[0], /界面更清爽/);
});

test('真实模板文件本身必须判红（预填充 ≠ 思考过；模板被填成范文立刻红）', () => {
  // 这条钉的是仓库里的那份文件，不是构造数据：有人往模板里塞示范正文/示范判据，
  // 就等于给所有 PR 预置了通过样本，此处必须转红。
  const fs = require('node:fs');
  const path = require('node:path');
  const tpl = fs.readFileSync(path.join(__dirname, '..', '..', '.github', 'PULL_REQUEST_TEMPLATE.md'), 'utf8');
  const v = checkFourQuestions({ body: tpl });
  assert.equal(v.ok, false, '模板未填时必须判红：四个小节要么缺失、要么只有注释占位');
});

test('证伪探针：去掉注释剥离必须被抓出（同输入变绿）', () => {
  // 对照 1：注释与真实内容混排时，剥离不该误伤。
  const mixed = ['## 解决谁的什么问题', '#3174', '## 验收标准', '- [x] 走查：截图', '## 风险', '无风险', '## 替代方案', '手抄模板 <!-- 待补 -->'].join('\n');
  assert.equal(checkFourQuestions({ body: mixed }).ok, true);
  // 对照 2：四个小节全是占位注释 ⇒ 必须判红。
  const onlyComments = ['## 解决谁的什么问题', '<!-- x -->', '## 验收标准', '<!-- y -->', '## 风险', '<!-- z -->', '## 替代方案', '<!-- w -->'].join('\n');
  assert.equal(checkFourQuestions({ body: onlyComments }).ok, false, '真实现必须判红');
  // 若不剥注释，同一份「全是占位」的正文会被判绿——说明剥离确实拦住了东西。
  const naive = (b) => b.split(/\r?\n/).filter((l) => l.trim() && !l.trim().startsWith('#')).length >= 4;
  assert.equal(naive(onlyComments), true, '不剥注释的版本恰好通过 ⇒ 守卫确实咬住了新形态');
});
