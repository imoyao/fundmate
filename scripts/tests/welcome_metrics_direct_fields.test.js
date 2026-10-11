/**
 * #119 守门：投资概览资产看板的三项指标**全部来自 `/api/summary/` 直出字段**。
 *
 * ## 为什么要有这份文件
 *
 * 首页「家庭资产看板」同时展示 总资产 / 净资产 / 总负债 三项。净资产与总负债
 * 后端 `/api/summary/` **已经直出**（`net_assets_cny` / `total_liabilities_cny`，
 * 见 `backend/app/services/summary_service.py`），但历史上这两个槽位长期是
 * 「—（即将上线）」死位——同一份数据，卡片头用了、别处不用（#119 的原始现象）。
 *
 * 修法 A 的口径（#119 拍板）：三个指标一律消费直出字段，
 * **禁止前端 `total - liabilities` 二次计算**——净资产是后端唯一口径，
 * 前端再算一遍会出现「两处算法哪天不一致」的隐患（同类原则见 `AGENTS.md`
 * 「统一输出 `signed_amount` 为唯一计算字段，前端禁止二次运算」）。
 *
 * 另一条：**不要为了填一个占位槽而临时造数据源**。历史上的 `netAssetsYoy`
 * （净资产同比）在本仓没有后端来源——它需要净资产时间序列（快照），
 * 属于「按工程完整性驱动」而非「按产品场景驱动」（`AGENTS.md` 数据策略）。
 * 没有就老实不展示，好过造一个恒为 `—` 的壳。
 *
 * ## 三组样本（缺一不可，照 `welcome_structure_dedup.test.js` 的写法）
 *
 * - 真实文件断言零命中（当前状态正确）；
 * - 把旧写法注回去必须报红（证明判据不是空转）；
 * - 反向样本不得误报（后端直出、注释里的旧写法讲解不算回潮）。
 *
 * ## 边界：判据只能看代码，不能看渲染
 *
 * 本守门钉的是**源码形态**（取值来源 / 有无死位字面量），不是运行时渲染结果。
 * 「数字是否真的画出来」由组件渲染测试覆盖，这里不重复。
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
const WELCOME_DATA = 'frontend/src/views/welcome/composables/useWelcomeData.ts';

/**
 * 判据一：前端二次计算净资产。
 *
 * 要拦的是「用两个直出字段做减法得到净资产」，形态不止一种：
 *   - `summary.total_assets_cny - summary.total_liabilities_cny`
 *   - `(summary?.total_assets_cny ?? 0) - (summary?.total_liabilities_cny ?? 0)`
 *
 * 写这条判据连崩了两次，两个方向都错，值得记下来：
 *   ① 用「两侧紧邻减号」（`total_assets_cny\s*-\s*total_liabilities_cny`）漏——
 *      真实旧写法中间夹着 `) - (`；
 *   ② 退成「两个字段都出现 + 文中有减号」又误报——同一文件里两个字段本就要各自
 *      出现（一个是 hero 数字、一个是右栏），而 CSS/类名里减号满地都是。
 *
 * 正解：要求两个字段出现在**同一段减法表达式**里，中间允许 `?.` / `()` / `?? 0`
 * 这类噪声，但不允许跨越整段模板去连线。
 */
const NET_ASSETS_SUBTRACTION =
  /total_assets_cny[\s\S]{0,80}?-[\s\S]{0,80}?total_liabilities_cny|total_liabilities_cny[\s\S]{0,80}?-[\s\S]{0,80}?total_assets_cny/;

function computesNetAssetsInline(code) {
  return NET_ASSETS_SUBTRACTION.test(code);
}

/** 判据二：模板里出现「即将上线」占位死位。 */
function hasComingSoonPlaceholder(code) {
  return /即将上线/.test(code);
}

test('#119：资产看板的净资产取直出字段 net_assets_cny（真实文件命中）', () => {
  const code = readCode(WELCOME_BOARD);
  assert.ok(code, `${WELCOME_BOARD} 应存在`);
  assert.ok(
    /summary\??\.net_assets_cny/.test(code),
    `${WELCOME_BOARD} 应消费直出字段 summary.net_assets_cny（修法 A，禁止前端二次计算）`
  );
});

test('#119：资产看板的总负债取直出字段 total_liabilities_cny（真实文件命中）', () => {
  const code = readCode(WELCOME_BOARD);
  assert.ok(code, `${WELCOME_BOARD} 应存在`);
  assert.ok(
    /summary\??\.total_liabilities_cny/.test(code),
    `${WELCOME_BOARD} 应消费直出字段 summary.total_liabilities_cny（修法 A）`
  );
});

test('#119：资产看板不得前端二次计算净资产（真实文件零命中）', () => {
  const code = readCode(WELCOME_BOARD);
  assert.ok(code, `${WELCOME_BOARD} 应存在`);
  assert.ok(
    !computesNetAssetsInline(code),
    `${WELCOME_BOARD} 出现 total_assets_cny - total_liabilities_cny 二次计算；净资产有直出字段，禁止前端再算一遍（#119）`
  );
});

test('#119：资产看板不得再有「即将上线」死位（真实文件零命中）', () => {
  const code = readCode(WELCOME_BOARD);
  assert.ok(code, `${WELCOME_BOARD} 应存在`);
  assert.ok(
    !hasComingSoonPlaceholder(code),
    `${WELCOME_BOARD} 又出现「即将上线」占位；死位要么有真数据、要么不出现（#119）`
  );
});

test('#119：把旧写法注回去必须报红（判据非空转）', () => {
  // 修复前的真实形态一：净资产前端自己减。
  assert.ok(
    computesNetAssetsInline(
      '<MoneyDisplay :value="(summary?.total_assets_cny ?? 0) - (summary?.total_liabilities_cny ?? 0)" />'
    ),
    '注回「前端二次计算净资产」后判据必须命中，否则守门是装饰'
  );

  // 修复前的真实形态二：「即将上线」死位。
  assert.ok(
    hasComingSoonPlaceholder('<span>—</span><span>即将上线</span>'),
    '注回「即将上线」占位后判据必须命中'
  );
});

test('#119：不得为占位槽造无来源入参（netAssetsYoy 无后端来源）', () => {
  const code = readCode(WELCOME_DATA);
  assert.ok(code, `${WELCOME_DATA} 应存在`);
  assert.ok(
    !/netAssetsYoy/.test(code),
    `${WELCOME_DATA} 出现 netAssetsYoy——本仓无净资产时间序列，该同比无后端来源，不得为填占位槽造数据源（#119 修法 A）`
  );
});

test('#119：反向样本不得误报（注释里的旧写法讲解不算回潮）', () => {
  // 文档/注释里讲到旧写法是**在讲机制**，stripComments 后不应命中。
  const docOnly = stripComments(
    '<!-- 历史：这里曾是 `total_assets_cny - total_liabilities_cny` 与「即将上线」 -->\n<template/>'
  );
  assert.ok(!computesNetAssetsInline(docOnly), '注释里的旧写法不应被当成回潮');
  assert.ok(!hasComingSoonPlaceholder(docOnly), '注释里的「即将上线」讲解不应被当成占位');
});
