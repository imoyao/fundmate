/**
 * #2034 守门：同一口径的「资产构成」图，全站只画一次；且不长得像可切换控件。
 *
 * ## 为什么要有这份文件
 *
 * 三件事都属同一形态——**同一份数据/同一个名字在一个视口里出现两次**：
 *
 * 1. welcome 的「家庭资产看板」曾持有一张资产大类环形图（口径 `category_distribution`），
 *    与资产总览构成图**同接口字段、同口径**；按两页分工
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
 * - 放行样本不得误报（panorama 构成图 / 多维视图仍应合法消费这些字段）。
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
// 2026-10-27（#980 批 B6）：摘要卡拆成左右两张组件，构成图态（标题 / 口径 tooltip /
// PnlCalendar 宿主）搬到 `OverviewInsightCard.vue`。判据跟着搬家——被检查的代码换了
// 文件，指针不动就成假绿。
const COMPOSITION = 'frontend/src/views/asset/panorama/components/OverviewInsightCard.vue';
// #2093：图的几何与 option 构造被抽到此模块（纯计算，不碰 DOM / 实例），
// `category_distribution` 的消费随之搬来这里；组件侧只留「何时画 / 画在哪 / 何时 dispose」。
// 2026-10-25：卡片从瀑布图改为「资产大类构成柱状图」，本模块随之更名
// `assetComposition.ts`——判据只钉「谁消费字段、谁委托谁」，图型换了不该让守门失效。
const COMPOSITION_HELPER =
  'frontend/src/views/asset/panorama/components/assetComposition.ts';
// 2026-10-24（#980 页面规模基线）：取色与 option 组装再从组件抽到本模块，
// 组件里只剩「何时画 / 画在哪 / 何时 dispose」。委托点跟着搬——判据因此查
// 「组件 → 取色/组装模块 → 计算模块」这条链路，而不是钉死在一个文件上。
const COMPOSITION_VIEW =
  'frontend/src/views/asset/panorama/components/compositionView.ts';

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

test('#2034：panorama 构成图仍应合法消费这些字段（不得误报）', () => {
  // 结构拆解归资产总览：这里是**唯一**该画资产大类构成图的地方。
  //
  // ⚠️ 字段消费点会随重构搬家（#2093 抽到 `assetComposition.ts`）。断言钉死在哪个
  // 文件，就得跟着搬到哪个文件——否则守门会在**重构成功的那一刻**误报，把
  // 「字段被消费」判成「字段没人用」（#2093 首次 CI 就是这么红的）。故这里守两段
  // 链路：① 计算模块真的读该字段；② 组件仍委托它，没有把数据逻辑搬回组件。
  const helper = readCode(COMPOSITION_HELPER);
  assert.ok(
    helper && helper.includes('category_distribution'),
    '构成图计算模块应消费 category_distribution'
  );
  const view = readCode(COMPOSITION_VIEW);
  assert.ok(
    view && view.includes('buildCompositionOption'),
    '取色/组装模块应委托 buildCompositionOption 组装构成图'
  );
  const comp = readCode(COMPOSITION);
  assert.ok(
    comp && comp.includes('buildCompositionViewOption'),
    '组件应委托 buildCompositionViewOption 画构成图，不得把数据逻辑搬回组件'
  );
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
  const chartCard = readCode(COMPOSITION);
  assert.ok(chartCard, 'OverviewInsightCard.vue 应存在');
  // 构成图态标题：维度词，不是「资产构成」「资产大类构成」这类与按钮文字同长的名字。
  assert.ok(
    /"资产大类"/.test(chartCard),
    '构成图态标题应为「资产大类」（维度词），给下卡片上的 (i) 口径说明'
  );
  for (const banned of ['"资产大类构成"', '"总资产构成"']) {
    assert.ok(!chartCard.includes(banned), `标题不应为 ${banned}（与切换按钮同名 / 名实不符）`);
  }
  // 按钮/标题互斥字面必须在：切过去要能看出来。
  assert.ok(
    /日历|收益日历/.test(chartCard) && /资产大类/.test(chartCard),
    '两态标题必须各自可辨'
  );
});

test('#2034：口径 tooltip 不得再用「按 X 拆解」这种像控件的措辞', () => {
  const chartCard = readCode(COMPOSITION);
  assert.ok(chartCard, 'OverviewInsightCard.vue 应存在');
  assert.ok(
    !/按资产大类/.test(chartCard),
    '「按资产大类…」正是原卡病灶措辞（位置 + 维度词 = 像可切换控件），应改为「口径：…」'
  );
  // 2026-10-25：图从瀑布换成构成柱状图，tooltip 必须跟着说「只统计资产端」。
  // 旧的「逐项累加、扣负债落到净资产」是瀑布口径，留着就是 ⓘ 描述另一张图。
  assert.ok(
    /口径：.*资产端/.test(chartCard),
    '口径 tooltip 必须说明「只统计资产端」，否则读者会以为图里含负债'
  );
  assert.ok(
    /负债与净资产见左侧卡片/.test(chartCard),
    '负债与净资产不在图内，ⓘ 必须把它们指向左卡（否则说明不了该去哪看）'
  );
  assert.ok(
    !/逐项累加/.test(chartCard),
    '「逐项累加、扣负债落到净资产」是瀑布图的读法，构成图不得沿用'
  );
});

test('#2034：注回旧措辞必须报红（判据非空转）', () => {
  const regressed = 'content="按资产大类拆解：各大类金额逐项累加，扣除负债后落到净资产"';
  assert.ok(/按资产大类/.test(regressed), '注回旧措辞后判据必须命中');
});

// ─────────────────────────────────────────────────────────────────────────────
// 全站口径：同一份「资产大类构成」图，只允许画一次
// ─────────────────────────────────────────────────────────────────────────────

test('#2034：全站只有 panorama 构成图一处画「资产大类构成」图', () => {
  const hits = [];
  for (const [file, code] of collectVueCodes('frontend/src')) {
    // 组件消费 `category_distribution` 即视为画了一张「资产大类构成」图。
    if (/category_distribution/.test(code)) hits.push(file.replace(ROOT, '').replace(/\\/g, '/'));
  }
  const allowed = [
    // 资产大类构成图（本卡之后**唯一**的资产大类构成出口；#980 批 B6 起在图卡组件里）
    '/frontend/src/views/asset/panorama/components/OverviewInsightCard.vue',
    // 大类余额明细表：与构成图同口径的**表格**表达（同一区块的两种读法，非第二个「图」）
    '/frontend/src/views/asset/panorama/components/CategoryBalanceTable.vue',
    // 复盘页（原「智能分析」）已在 #2150 删掉大类卡片 + 环形图，此处**不再豁免**。
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

// ─────────────────────────────────────────────────────────────────────────────
// #2150：/analysis 重新定义定位 —— 与 panorama 去重，且删了就得保持删着
// ─────────────────────────────────────────────────────────────────────────────

const ANALYSIS = 'frontend/src/views/asset/IntelligentAnalysis.vue';

test('#2150：全站不再有第四处消费 category_distribution（复盘页已去重）', () => {
  const hits = [];
  for (const [file, code] of collectVueCodes('frontend/src')) {
    if (/category_distribution/.test(code)) {
      hits.push(file.replace(ROOT, '').replace(/\\/g, '/'));
    }
  }
  const allowed = [
    // 资产大类构成图（全站唯一的「资产大类构成」图出口；#980 批 B6 起在图卡组件里）
    '/frontend/src/views/asset/panorama/components/OverviewInsightCard.vue',
    // 大类余额明细表：与构成图同口径的**表格**表达（同一区块的两种读法）
    '/frontend/src/views/asset/panorama/components/CategoryBalanceTable.vue',
    // 构成图的数据整形 + option 计算模块（#2093 从组件抽出）
    '/frontend/src/views/asset/panorama/components/assetComposition.ts',
    // 盘点页复用「投资理财」切片，不画构成图
    '/frontend/src/views/asset/inventory/useInventoryData.ts'
  ];
  assert.deepEqual(
    hits.filter(h => !allowed.includes(h)),
    [],
    '又出现了新的「资产大类构成」出口：复盘页（原智能分析）已按 #2150 去重，' +
      '其余页请先查有没有既有出口'
  );
});

test('#2150：复盘页不得再出现与 panorama 同字段同接口同算法的四块', () => {
  const code = readCode(ANALYSIS);
  assert.ok(code, `${ANALYSIS} 应存在`);

  // ① 总资产 + 环比/同比 ← panorama 摘要卡左卡（OverviewAssetsCard，2026-10-27 拆分前在 OverviewSummaryCard 里）
  assert.ok(
    !/monthly_change_pct|yearly_change_pct/.test(code),
    '总资产环比/同比归 panorama 首卡（同字段同接口），复盘页不得再画一遍'
  );
  // ② 大类占比的二次计算 ← panorama CategoryBalanceTable 逐字同公式
  assert.ok(
    !/\(d\.value\s*\/\s*total\)\s*\*\s*100/.test(code),
    '「(值/合计)*100」与 panorama 大类表逐字同公式，属重复拆解'
  );
  // ③ category_distribution ← panorama 构成图 + 明细表
  assert.ok(
    !/category_distribution|getDistributions/.test(code),
    'category_distribution 全站只画一次（panorama），复盘页不得消费'
  );
  // ④ getPositionGroups ← panorama DetailGroupList 同接口同维度
  assert.ok(
    !/getPositionGroups/.test(code),
    '持仓分组表归 panorama 多维视图（同接口同维度），复盘页不得再画一遍'
  );
});

test('#2150：判据非空转——把四块任意一块注回去必须报红', () => {
  const samples = [
    'const monthlyChangePct = computed(() => latestSnapshot.value?.monthly_change_pct)',
    'share: total ? (d.value / total) * 100 : 0',
    'distributionData.value = dist?.category_distribution ?? []',
    'const res = await getPositionGroups("type");'
  ];
  const code = readCode(ANALYSIS);
  for (const smp of samples) {
    // 把样本拼进真实文件内容，确认上面四条断言真的会命中（而不是靠文件里恰好没有）。
    const injected = code + '\n' + smp;
    const hit =
      /monthly_change_pct|yearly_change_pct/.test(injected) ||
      /\(d\.value\s*\/\s*total\)\s*\*\s*100/.test(injected) ||
      /category_distribution|getDistributions/.test(injected) ||
      /getPositionGroups/.test(injected);
    assert.ok(hit, `注回「${smp}」后判据必须命中`);
  }
});

test('#2150：复盘页的独占项（净值走势）必须还在——删重复不等于删自己', () => {
  // 2026-10-25：净值走势的取数/绘图拆进了 composables/useNetWorthTrend.ts
  //（页内导航接入后按 #980 拆 composable 让页面净减少），独占项的判据随迁：
  // 页面必须仍消费该 composable 并持有 canvas，取数必须仍在复盘页专属文件里。
  const code = readCode(ANALYSIS);
  assert.ok(
    /useNetWorthTrend/.test(code),
    '复盘页必须仍接入净值走势 composable（useNetWorthTrend）——它是本页唯一的独占项（welcome 已让出、panorama 只取最新快照做环比），删了页面就没有存在理由'
  );
  assert.ok(
    /netWorthChartRef/.test(code),
    '净值走势的 canvas 必须还在'
  );
  const trend = readCode(
    'frontend/src/views/asset/composables/useNetWorthTrend.ts'
  );
  assert.ok(
    trend && /getSnapshots/.test(trend),
    'useNetWorthTrend 必须仍读 /summary/snapshots/（资产净值走势独占数据源）'
  );
});

test('#2150：页面标题与入口文案一致（复盘），且路由声明只有一份', () => {
  const router = readCode('frontend/src/router/modules/asset.ts');
  assert.ok(router, 'asset.ts 应存在');
  const analysisRoute = router.match(/path: "\/analysis"[\s\S]{0,600}?title: "([^"]+)"/);
  assert.ok(analysisRoute, '应有 /analysis 路由声明');
  assert.strictEqual(
    analysisRoute[1],
    '复盘',
    '路由标题应为「复盘」（#2150 重定义定位后的命名）'
  );
  assert.ok(
    !/"智能分析"/.test(router),
    '「智能分析」作为**标题字面量**不应再出现在路由表里（可用作历史沿革注释）'
  );
  const panorama = readCode('frontend/src/views/asset/panorama/index.vue');
  assert.ok(
    />\s*复盘\s*</.test(panorama),
    'panorama 页头入口按钮文案应随页面标题改为「复盘」，否则点过去标题对不上'
  );
});
