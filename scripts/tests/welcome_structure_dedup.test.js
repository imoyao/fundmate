/**
 * #2034 守门：投资概览（welcome）不得再出现「资产构成结构图」。
 *
 * ## 为什么要有这份文件
 *
 * welcome 的「家庭资产看板」曾持有一张资产大类环形图（口径 `category_distribution`），
 * 与资产总览瀑布图**同接口字段、同口径**——同一份「资产大类」在两页画了两遍，
 * 用户在两页之间切换时看到同一个结论换了种形状重讲一次（「像 demo」的来源之一）。
 *
 * 按两页分工（`docs/working-notes/page-split-welcome-vs-panorama-2026-08-13.md`：
 * 「拆解（composition）归资产总览，表现 + 目标归投资概览」），该图已整体移除。
 *
 * **这类「重复」最容易被无意识地加回来**——单看 welcome 一页，那张图完全合理，
 * 只有把两页摆在一起才看得出重复。故用守门钉住，而不是靠记性。
 *
 * ## 三组样本（缺一不可）
 *
 * - 真实文件断言零命中（当前状态正确）；
 * - 把旧写法注回去必须报红（证明判据不是空转）；
 * - 放行样本不得误报（`AssetInsightPanel`、panorama 的瀑布图仍应合法消费该字段）。
 *
 * 依赖：零新依赖（Node 内置 `node:test` / `node:assert` + 文件读取）。
 */

'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync, existsSync } = require('node:fs');
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

const WELCOME_BOARD = 'frontend/src/views/welcome/components/WelcomeAssetBoard.vue';

/**
 * 判据：welcome 资产看板里不得出现「结构图」的两个特征——
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

test('#2034：panorama / AssetInsightPanel 仍应合法消费这些字段（不得误报）', () => {
  // 这两个文件**应当**有结构图——结构拆解归资产总览。
  const waterfall = readCode(
    'frontend/src/views/asset/panorama/components/OverviewSummaryCard.vue'
  );
  const insight = readCode('frontend/src/components/AssetInsight/AssetInsightPanel.vue');
  assert.ok(waterfall && waterfall.includes('category_distribution'), '瀑布图应消费 category_distribution');
  assert.ok(insight && insight.includes('AssetAllocationDonut'), '资产透视应保留环形图');
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
