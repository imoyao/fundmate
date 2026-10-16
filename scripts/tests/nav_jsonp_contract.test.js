/**
 * 净值取数链路契约守卫（2026-10-14 事故回归网）。
 *
 * 事故：东财 lsjz 接口把查询参数从 snake_case（fund_code/start_date/end_date）
 * 改成 camelCase（fundCode/startDate/endDate），前端 JSONP 直连还在用旧参数名，
 * 一律返回 ErrCode:4/404 → 记一笔净值拉取整链失败、阻塞记账。当时 useNavCache
 * 又刻意绕开后端兜底（单点故障），两条腿断一条就全断。
 *
 * 本守卫钉死三件事，防回潮：
 *   1. fundNav.ts 的 URL 必须用 camelCase 参数 + 带横线日期（剥横线会得到
 *      ErrCode:0 但空列表，同样拉不到）；
 *   2. useNavCache.ts 的后端兜底（calcFundNav）不得被删；
 *   3. 旧参数名不得重新出现在 fundNav.ts 的 URL 构造里。
 *
 * 东财契约实证：见 fundNav.ts fetchNavFromEastmoney 内注释。
 */

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..", "..");

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

test("fundNav.ts JSONP URL 使用东财现行契约（camelCase + 带横线日期）", () => {
  const src = read("frontend/src/api/fundNav.ts");

  assert.match(
    src,
    /fundCode=/,
    "lsjz URL 必须用 fundCode=（东财 2026-10 起的契约；旧 fund_code= 一律 ErrCode:4/404）"
  );
  assert.match(
    src,
    /startDate=\$\{targetDate\}&endDate=\$\{targetDate\}/,
    "startDate/endDate 必须直接插带横线的 targetDate（YYYY-MM-DD；剥横线返回空列表）"
  );

  assert.ok(
    !src.includes("fund_code="),
    "fundNav.ts 不得出现 fund_code=（旧参数名，东财已拒，会复现记一笔净值拉不到）"
  );
  assert.ok(
    !src.includes("start_date=") && !src.includes("end_date="),
    "fundNav.ts 不得出现 start_date=/end_date=（旧参数名，东财已拒）"
  );
  assert.ok(
    !/replace\(\/-\/g/.test(src),
    "不得再剥日期横线：lsjz 对 20261013 返回 ErrCode:0 但空列表，对 2026-10-13 才有数据"
  );
});

test("useNavCache.ts 保留后端 calcFundNav 兜底（JSONP 单点故障不断链）", () => {
  const src = read("frontend/src/composables/useNavCache.ts");

  assert.match(
    src,
    /import\s*\{\s*calcFundNav\s*\}\s*from\s*["']@\/api\/funds["']/,
    "useNavCache 必须引入 calcFundNav 作第三级兜底（2026-10-14：JSONP 全断时唯一通路）"
  );
  assert.ok(
    src.includes("calcFundNav("),
    "useNavCache.getNavs 必须实际调用 calcFundNav 兜底，只 import 不调用不算数"
  );
});
