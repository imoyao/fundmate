/**
 * #2034 守门：同一口径的「资产构成」图，全站只画一次；且不长得像可切换控件。
 *
 * ## 为什么要有这份文件
 *
 * 三件事都属同一形态——**同一份数据/同一个名字在一个视口里出现两次**：
 *
 * 1. welcome 的「家庭资产看板」曾持有一张资产大类环形图（口径 `category_distribution`），
 *    与资产总览瀑布图**同接口字段、同口径**；按两页分工
 *    （`docs/working-notes/page-split-welcome-vs-panorama-2026-08-13.md`：
 *    「拆解（composition）归资产总览，表现 + 目标归投资概览」），该图已整体移除。
 * 2. panorama 的「资产透视」两张环（原 `AssetInsightPanel`）标题与字段对不上（#2032），
 *    而本页「多维视图」已有同样两套数据的正确命名出口——故整块删除，不是改名。
 * 3. 原卡「问题一」的病灶是**措辞**：一句静态说明写成「按资产大类 X」，
 *    位置与形态都像可切换控件；环形图走了但这句话跟去了 panorama 的口径 tooltip。
 *
 * 这三类都**最容易被无意识地加回来**——单看某一页，那张图/那句话完全合理，
 * 只有把两页摆在一起才看得出重复与撞名。故用守门钉住，而不是靠记性。
 *
 * ## 样本（缺一不可）
 *
 * - 真实文件断言零命中（当前状态正确）；
 * - 把旧写法注回去必须报红（证明判据不是空转）；
 * - 放行样本不得误报（panorama 瀑布图 / 多维视图仍应合法消费这些字段）。
 *
 * 依赖：零新依赖（Node 内置 `node:test` / `node:assert` + 文件读取）。
 */

'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync, existsSync, readdirSync, statSync } = require('node:fs');
const { join } = require('node:path');

const ROOT = process.cwd();

/** 读文件并剥掉注释：判据只看**代码**，文档里讲解旧写法不该被当成回潮。 */
function stripComments(src) {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}

function readCode(rel) {
  const p = join(ROOT, rel);
  if (!existsSync(p)) return null;
  return stripComments(readFileSync(p, 'utf8'));
}

/** 递归收集某个目录下的 `.vue` 源码（剥注释），用于「全站只画一次」这类判据。 */
function collectVueCodes(rel) {
  const out = new Map();
  const walk = dir => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      if (statSync(full).isDirectory()) walk(full);
      else if (name.endsWith('.vue')) out.set(full, stripComments(readFileSync(full, 'utf8')));
    }
  };
  walk(join(ROOT, rel));
  return out;
}

const WELCOME_BOARD = 'frontend/src/views/welcome/components/WelcomeAssetBoard.vue';
const WATERFALL = 'frontend/src/views/asset/panorama/components/OverviewSummaryCard.vue';
// #2093：瀑布图的几何与 option 构造被抽到此模块（纯计算，不碰 DOM / 实例），
// `category_distribution` 的消费随之搬来这里；组件侧只留「何时画 / 画在哪 / 何时 dispose」。
const WATERFALL_HELPER = 'frontend/src/views/asset/panorama/components/assetWaterfall.ts';

/**
 * 判据 A：welcome 资产看板里不得出现「结构图」的两个特征——
 *   ① 环形图组件 `AssetAllocationDonut`；
 *   ② 消费 `category_distribution` / `market_distribution` 的数据逻辑。
 *
 * 两者任一命中即视为结构图回潮（无论包成什么组件名，数据源是逃不掉的锚点）。
 */
function violates(code) {
  return /AssetAllocationDonut/.test(code) || /(category|market)_distribution/.test(code);
}

test('#2034：welcome 资产看板不得再出现资产构成结构图（真实文件零命中）', () => {
  const code = readCode(WELCOME_BOARD);
  assert.ok(code, `${WELCOME_BOARD} 应存在`);
  assert.ok(
    !violates(code),
    `${WELCOME_BOARD} 又出现了结构图：该图与资产总览同字段同口径，结构拆解归资产总览（#2034）`
  );
});

test('#2034：把旧写法注回去必须报红（判据非空转）', () => {
  // 修复前的真实形态：环形图 + category_distribution 口径。
  const regressed = `
    <AssetAllocationDonut :data="distributionData" class="h-[220px]" />
    const distributionData = computed(() => buildDistributionData(props.distributions));
    // 数据源：distributions.category_distribution
  `;
  assert.ok(violates(regressed), '注回旧写法后判据必须命中，否则守门是装饰');

  // 只换数据源、换个组件名也拦得住（数据源才是锚点）。
  assert.ok(violates('const d = props.distributions?.market_distribution ?? []'));
});

test('#2034：panorama 瀑布图仍应合法消费这些字段（不得误报）', () => {
  // 结构拆解归资产总览：这里是**唯一**该画资产大类构成图的地方。
  //
  // ⚠️ 字段消费点会随重构搬家（#2093 抽到 `assetWaterfall.ts`）。断言钉死在哪个
  // 文件，就得跟着搬到哪个文件——否则守门会在**重构成功的那一刻**误报，把
  // 「字段被消费」判成「字段没人用」（#2093 首次 CI 就是这么红的）。故这里守两段
  // 链路：① 计算模块真的读该字段；② 组件仍委托它，没有把数据逻辑搬回组件。
  const helper = readCode(WATERFALL_HELPER);
  assert.ok(
    helper && helper.includes('category_distribution'),
    '瀑布图计算模块应消费 category_distribution'
  );
  const comp = readCode(WATERFALL);
  assert.ok(comp && comp.includes('buildWaterfallBars'), '组件应委托 buildWaterfallBars 画瀑布图');
});

test('#2034：welcome 不再请求 distributions（少一次无消费方的请求）', () => {
  const data = readCode('frontend/src/views/welcome/composables/useWelcomeData.ts');
  assert.ok(data, 'useWelcomeData.ts 应存在');
  assert.ok(
    !/getDistributions/.test(data),
    'welcome 已无结构图消费方，不应再调 getDistributions（#2034）'
  );
});

test('#2034：随图失效的 distributionLogic 已删除', () => {
  assert.ok(
    readCode('frontend/src/views/welcome/composables/distributionLogic.ts') === null,
    'distributionLogic.ts 已无消费方，应删除而非留作死代码（#2034）'
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// 二轮：#2034 只落了一半 —— 「资产透视」区块（#2032 的两张错名环）
// ─────────────────────────────────────────────────────────────────────────────

test('#2032/#2034：panorama 不得再挂「资产透视」区块（两块环名与字段对不上）', () => {
  const panorama = readCode('frontend/src/views/asset/panorama/index.vue');
  assert.ok(panorama, 'panorama/index.vue 应存在');
  assert.ok(
    !/AssetInsightPanel/.test(panorama),
    '「资产透视」两张环标题与数据字段对不上（#2032），且「多维视图」已有正确命名出口；' +
      '同一份数据不得在首屏画第二遍（#2034），故该区块应保持删除'
  );
  assert.ok(
    !existsSync(join(ROOT, 'frontend/src/components/AssetInsight/AssetInsightPanel.vue')),
    'AssetInsightPanel.vue 已无消费方，应删除而非留作死代码'
  );
});

test('#2032/#2034：把区块注回 panorama 必须报红（判据非空转）', () => {
  const regressed = '<AssetInsightPanel class="mb-4" />';
  assert.ok(/AssetInsightPanel/.test(regressed), '注回旧写法后判据必须命中');
});

test('#2034：标题不得与切换按钮上的字同名（切过去像没切）', () => {
  const waterfall = readCode(WATERFALL);
  assert.ok(waterfall, 'OverviewSummaryCard.vue 应存在');
  // 瀑布态标题：维度词，不是「资产构成」「资产大类构成」这类与按钮文字同长的名字。
  assert.ok(
    /"资产大类"/.test(waterfall),
    '瀑布态标题应为「资产大类」（维度词），给下卡片上的 (i) 口径说明'
  );
  for (const banned of ['"资产大类构成"', '"总资产构成"']) {
    assert.ok(!waterfall.includes(banned), `标题不应为 ${banned}（与切换按钮同名 / 名实不符）`);
  }
  // 按钮/标题互斥字面必须在：切过去要能看出来。
  assert.ok(
    /日历|收益日历/.test(waterfall) && /资产大类/.test(waterfall),
    '两态标题必须各自可辨'
  );
});

test('#2034：口径 tooltip 不得再用「按 X 拆解」这种像控件的措辞', () => {
  const waterfall = readCode(WATERFALL);
  assert.ok(waterfall, 'OverviewSummaryCard.vue 应存在');
  assert.ok(
    !/按资产大类/.test(waterfall),
    '「按资产大类…」正是原卡病灶措辞（位置 + 维度词 = 像可切换控件），应改为「口径：…」'
  );
  assert.ok(
    /口径：各大类金额逐项累加/.test(waterfall),
    '口径 tooltip 应保留（内容是对的，只是措辞要换）'
  );
});

test('#2034：注回旧措辞必须报红（判据非空转）', () => {
  const regressed = 'content="按资产大类拆解：各大类金额逐项累加，扣除负债后落到净资产"';
  assert.ok(/按资产大类/.test(regressed), '注回旧措辞后判据必须命中');
});

// ─────────────────────────────────────────────────────────────────────────────
// 全站口径：同一份「资产大类构成」图，只允许画一次
// ─────────────────────────────────────────────────────────────────────────────

test('#2034：全站只有 panorama 瀑布图一处画「资产大类构成」图', () => {
  const hits = [];
  for (const [file, code] of collectVueCodes('frontend/src')) {
    // 组件消费 `category_distribution` 即视为画了一张「资产大类构成」图。
    if (/category_distribution/.test(code)) hits.push(file.replace(ROOT, '').replace(/\\/g, '/'));
  }
  const allowed = [
    // 资产大类构成瀑布图（本卡之后**唯一**的资产大类构成出口）
    '/frontend/src/views/asset/panorama/components/OverviewSummaryCard.vue',
    // 大类余额明细表：与瀑布图同口径的**表格**表达（同一区块的两种读法，非第二个「图」）
    '/frontend/src/views/asset/panorama/components/CategoryBalanceTable.vue',
    // 智能分析首屏的大类卡片 + 环形图（#2034 三轮开口项，见 tech-debt）
    '/frontend/src/views/asset/IntelligentAnalysis.vue',
    // 盘点页复用「投资理财」切片，不画构成图
    '/frontend/src/views/asset/inventory/useInventoryData.ts'
  ];
  const unexpected = hits.filter(h => !allowed.includes(h));
  assert.deepEqual(
    unexpected,
    [],
    '又出现了新的「资产大类构成」图：同一份数据在一个产品里画两遍是「像 demo」的来源，' +
      '新页面请先查有没有既有出口（#2034）'
  );
});
