/**
 * guard_summary_aggregation 回归样本（imoyao/fundmate#2179，源 CNB duoduobei/fundmate#478 / GitHub #2154）。
 *
 * 守卫的职责是**拦「总资产」的又一份手写累加**。它保护的是一个已经真实分叉过的
 * 东西：`get_ledger_distributions` 曾把 `family_totals` 的累加逻辑逐字重写一遍，
 * 靠 `test_account_snapshots.py` 里一条埋在别处的断言兜着——**靠人找**。
 *
 * 样本分四组，缺一不可：
 *   · **命中样本** —— 规则真能抓到（把累加写回去要红），第一条就是那一处的旧写法；
 *   · **放行样本** —— 不得误报（构造桶、`total = a + b`、别处按账户名分组等）；
 *   · **失败态样本** —— 文件不存在必须退 2 且**不得**报「通过」（#171 的失败态纪律：
 *     拿不到输入 ≠ 输入为空，判据不得退化成一个看起来正常的结论）；
 *   · **真实文件正反两面** —— 当前代码零命中 + 把累加注回去必须报红。
 *     只有后者绿了，前者的绿才不是空转（「守门通过 ≠ 守门有效」）。
 */
import { spawnSync } from "node:child_process";
import { pythonOrFail } from "./_python-interpreter.mjs";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";

const ROOT = process.cwd();
const SCRIPT = join(ROOT, "scripts", "guard_summary_aggregation.py");
const REAL_FILE = join(ROOT, "backend", "app", "services", "summary_service.py");

/**
 * 解释器探测与「静默绿」（#119 的同类教训）。
 *
 * 若写死 `python`，而它在这个容器里不存在（只有 `python3`），`spawnSync` 抛 ENOENT，
 * 被拼进 stdout 后既不含 `ERROR:` 也不含 `Traceback` —— 于是**所有放行断言假通过**：
 * 「守卫没报错」恰好因为「守卫根本没跑」。探测逻辑已收口到唯一一份
 * `_python-interpreter.mjs`（本文件原先是 6 份拷贝之一），取不到即在加载期抛错。
 */
const PY = pythonOrFail();
const PY_BIN = PY[0];
const PY_ARGS = PY.slice(1);

/** 跑守卫：返回 {status, output}。脚本自身崩溃（>1）单独区分，避免伪装成「无回潮」。 */
function runGuard(paths) {
  const r = spawnSync(PY_BIN, [...PY_ARGS, SCRIPT, ...paths], { encoding: "utf8" });
  if (r.error) {
    throw new Error(`守卫脚本无法启动（${PY_BIN}）：${r.error.message}`);
  }
  const output = (r.stdout || "") + (r.stderr || "");
  if (r.status > 2) {
    throw new Error(`守卫脚本异常退出（status=${r.status}）：\n${output}`);
  }
  return { status: r.status, output };
}

function guard(files) {
  const dir = mkdtempSync(join(tmpdir(), "summary-agg-"));
  const paths = files.map((content, i) => {
    const p = join(dir, `s${i}.py`);
    writeFileSync(p, content, "utf8");
    return p;
  });
  return runGuard(paths);
}

/* ---------- 命中样本 ---------- */

test("命中：账户级手写累加（#2179 修复前那一处的原样）→ 报红", () => {
  const { status, output } = guard([
    `def get_ledger_distributions(db, family_id=1):
    positions, assets = _load_user_assets(db, family_id)
    totals = {}
    for p in positions:
        bucket = totals.setdefault(p.ledger_id or 0, {'total_assets': 0.0, 'total_liabilities': 0.0})
        bucket['total_assets'] += 1.0
    return totals
`
  ]);
  assert.equal(status, 1, `该报红却是 ${status}：\n${output}`);
  assert.match(output, /get_ledger_distributions/);
  assert.match(output, /total_assets/);
});

test("命中：裸名累加同样要抓（`total_liabilities += ...`，不是只有下标形态）", () => {
  const { status, output } = guard([
    `def get_distributions(db, family_id=1):
    total_liabilities = 0.0
    total_liabilities += 5.0
    return total_liabilities
`
  ]);
  assert.equal(status, 1, `该报红却是 ${status}：\n${output}`);
  assert.match(output, /total_liabilities/);
});

test("命中：`x = x + y` 写法不能绕过（等价于 +=\\u0029", () => {
  const { status, output } = guard([
    `def some_exit(db, family_id=1):
    total_assets = total_assets + 1.0
    return total_assets
`
  ]);
  assert.equal(status, 1, `该报红却是 ${status}：\n${output}`);
});

test("命中：net_worth 也在射程内（三个桶都是本口径的产物）", () => {
  const { status, output } = guard([
    `def another_exit(db, family_id=1):
    net_worth = 0.0
    net_worth += 3.0
    return net_worth
`
  ]);
  assert.equal(status, 1, `该报红却是 ${status}：\n${output}`);
});

/* ---------- 放行样本（误报源） ---------- */

test("放行：唯一实现 `_per_ledger_buckets` 自己累加（它就是「那一份」）", () => {
  const { status, output } = guard([
    `def _per_ledger_buckets(db, family_id=1):
    totals = {}
    totals[0] = {'total_assets': 0.0}
    totals[0]['total_assets'] += 1.0
    return totals
`
  ]);
  assert.equal(status, 0, `唯一实现被误判：\n${output}`);
});

test("放行：`family_totals` 做桶相加（它 = 各账户桶按位相加）", () => {
  const { status, output } = guard([
    `def family_totals(db, family_id=1):
    merged = {'total_assets': 0.0}
    for bucket in _per_ledger_buckets(db, family_id).values():
        merged['total_assets'] += bucket['total_assets']
    return merged
`
  ]);
  assert.equal(status, 0, `家庭级出口被误判：\n${output}`);
});

test("放行：构造桶（`total_assets = 0.0`）不是累加", () => {
  const { status, output } = guard([
    `def _empty_bucket():
    return {'total_assets': 0.0, 'total_liabilities': 0.0, 'net_worth': 0.0}
`
  ]);
  assert.equal(status, 0, `构造桶被误判成累加：\n${output}`);
});

test("放行：`total = a + b` 这种「左边不等于右边引用」不是累加", () => {
  const { status, output } = guard([
    `def payload(x, y):
    total_assets = x + y
    return total_assets
`
  ]);
  assert.equal(status, 0, `普通加法被误判：\n${output}`);
});

test("放行：别的函数遍历同一批数据但不算总资产（首版误报就出在这里）", () => {
  // get_account_groups 按「账户名」分组、get_ledger_pnl 算的是盈亏——
  // 它们和唯一实现**碰的是同一批数据**，但累加的不是同一个桶。
  const { status, output } = guard([
    `def get_account_groups(db, family_id=1):
    positions, assets = _load_user_assets(db, family_id)
    groups = {}
    for p in positions:
        groups[p.account_name] = groups.get(p.account_name, 0) + 1
    return groups


def get_ledger_pnl(db, family_id=1):
    positions, _ = _load_user_assets(db, family_id)
    totals = {}
    for p in positions:
        totals[p.ledger_id or 0] = p.unrealized
    return totals
`
  ]);
  assert.equal(status, 0, `正常函数被误判（首版就是这么红的）：\n${output}`);
});

test("放行：注释里写的旧写法不算代码", () => {
  const { status, output } = guard([
    `def delegated(db, family_id=1):
    # 旧写法是 bucket['total_assets'] += ...，现已委托 _per_ledger_buckets
    return _per_ledger_buckets(db, family_id)
`
  ]);
  assert.equal(status, 0, `注释被当成代码了：\n${output}`);
});

test("放行：行内 summary-aggregation-allow 豁免（带理由）", () => {
  const { status, output } = guard([
    `def legacy(db, family_id=1):
    total_assets += 1.0  # summary-aggregation-allow: 历史遗留，待 #9999 收敛
    return total_assets
`
  ]);
  assert.equal(status, 0, `豁免没生效：\n${output}`);
});

/* ---------- 失败态样本（#171 的失败态纪律） ---------- */

test("失败态：文件不存在必须退 2，且不得报「通过」", () => {
  const { status, output } = runGuard([join(tmpdir(), "definitely-not-here-2179.py")]);
  assert.equal(status, 2, `拿不到输入却退 ${status}（不得退化成看起来正常的结论）：\n${output}`);
  assert.doesNotMatch(output, /^OK:/m, `拿不到输入却报了通过：\n${output}`);
});

test("失败态：语法错误必须退 2，不得当成「没违规」", () => {
  const { status, output } = guard([`def broken(:\n  pass\n`]);
  assert.equal(status, 2, `解析失败却退 ${status}：\n${output}`);
  assert.doesNotMatch(output, /^OK:/m, `解析失败却报了通过：\n${output}`);
});

/* ---------- 真实文件：正反两面 ---------- */

test("真实文件：summary_service.py 当前必须零命中", () => {
  const { status, output } = runGuard([REAL_FILE]);
  assert.equal(status, 0, `当前代码不该报红：\n${output}`);
});

test("回退探针：把账户级的手写累加注回真实文件 → 必须报红", () => {
  const src = readFileSync(REAL_FILE, "utf8");
  const eol = src.includes("\r\n") ? "\r\n" : "\n";

  // 修复后的形态：get_ledger_distributions 直接委托唯一实现
  const anchor = [
    "    # 不再自己累加：委托与 family_totals 共用的唯一实现（#2179），",
    "    # 故「Σ账户桶 ≡ 家庭桶」是构造出来的恒等式，而不是两边各自算对。",
    "    buckets = _per_ledger_buckets(db, family_id)",
    "    return {ledger_id: _round_totals(bucket) for ledger_id, bucket in buckets.items()}"
  ].join(eol);
  const reverted = [
    "    positions, assets = _load_user_assets(db, family_id)",
    "    totals = {}",
    "    for p in positions:",
    "        key = p.ledger_id or 0",
    "        bucket = totals.setdefault(key, _empty_bucket())",
    "        bucket['total_assets'] += Money.cents_to_yuan(market_value_cents(p))",
    "    return {ledger_id: _round_totals(bucket) for ledger_id, bucket in totals.items()}"
  ].join(eol);

  assert.ok(
    src.includes(anchor),
    "探针失效：源文件里找不到 get_ledger_distributions 的委托锚点，说明写法已变，请更新本探针。"
  );

  const mutated = src.split(anchor).join(reverted);
  assert.notEqual(mutated, src, "探针失效：回退替换没有生效。");

  const { status, output } = guard([mutated]);
  assert.equal(status, 1, `把累加注回去却没报红，守门失效：\n${output}`);
  assert.match(output, /get_ledger_distributions/);
});
