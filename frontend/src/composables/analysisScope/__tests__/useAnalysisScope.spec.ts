/**
 * 页级口径状态（#3287）。
 *
 * 这份状态是「切换器 → N 个区块」的唯一来源，钉四件事：
 * 1. **切档必须清对象**（残留上一档的 id = 脏口径，面板只认 props，不会替我们校验）；
 * 2. **`isReady` 的语义**（切到账户档但没选账户时不许取数，否则取到的是家庭级）；
 * 3. **纪元只按用户操作推进一次**（同 tick 的清 id + 换档不能被算成两次，
 *    否则并发中的响应会被误判为过期而丢弃）；
 * 4. **URL 归一**：伪 id（`Number()` 得 NaN）必须落成 `null`，否则
 *    `ledger_id=NaN` 会让后端按「没传」处理，界面却显示已选账户。
 *
 * ## 环境约定
 *
 * 前端单测跑 node 环境（无组件实例），`watch` 不会被自动回收 → 每个用例用
 * `effectScope` 包住并在 `afterEach` 停掉，否则前一个用例的 watcher 会继续
 * 观察自己的 ref（虽然不会互相干扰，但泄漏出来的回调会污染 `replace` 的调用计数）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, type EffectScope } from "vue";

const route = { query: {} as Record<string, string>, path: "/asset/x" };
const replaceState = vi.fn();

// 实现用 `history.replaceState` 而不是 `router.replace`（后者会因 router-view 的
// `:key="fullPath"` 整页重建，见 index.ts 的 writeUrl 注释）。这里把两样都桩掉：
// router 只用来 resolve 出目标 href。
vi.stubGlobal("history", { state: null, replaceState });
// node 环境没有 window；hash 模式的 URL 拼接要读 `location.hash` 判断模式，
// 故这里给一个最小桩（值与真实站点一致：`#/asset/x`）
vi.stubGlobal("window", { location: { hash: "#/asset/x" } });
vi.mock("vue-router", () => ({
  useRoute: () => route,
  useRouter: () => ({
    resolve: ({
      path,
      query
    }: {
      path: string;
      query: Record<string, string>;
    }) => ({
      href:
        path +
        (Object.keys(query).length
          ? "?" + new URLSearchParams(query).toString()
          : "")
    })
  })
}));

import { useAnalysisScope } from "../index";
import type { UseAnalysisScopeOptions } from "../index";

const scopes: EffectScope[] = [];

/** 在独立的 effectScope 里建实例，便于统一回收 */
function makeScope(options: UseAnalysisScopeOptions = {}) {
  const es = effectScope();
  scopes.push(es);
  return es.run(() => useAnalysisScope({ syncUrl: false, ...options }))!;
}

describe("useAnalysisScope：状态与契约", () => {
  beforeEach(() => {
    route.query = {};
    replaceState.mockClear();
  });

  afterEach(() => {
    while (scopes.length) scopes.pop()?.stop();
  });

  it("默认家庭档、无对象、可以取数", () => {
    const scope = makeScope();

    expect(scope.kind.value).toBe("family");
    expect(scope.id.value).toBeNull();
    expect(scope.isReady.value).toBe(true);
    expect(scope.scopeProps.value).toEqual({});
    expect(scope.scopeQuery.value).toEqual({ scope: "family" });
  });

  it("切到账户档会清空对象，且在选对象之前不可取数", async () => {
    const scope = makeScope();

    scope.setKind("ledger");
    await nextTick();

    expect(scope.kind.value).toBe("ledger");
    expect(scope.id.value).toBeNull();
    // 这一条是核心：不可取数。若放行，请求不带 id ⇒ 拿到家庭级数据，
    // 而界面上写着「单账户」—— #2595 同型的静默错口径
    expect(scope.isReady.value).toBe(false);

    scope.setId(3);
    expect(scope.isReady.value).toBe(true);
    expect(scope.scopeProps.value).toEqual({ ledgerId: 3 });
    expect(scope.scopeQuery.value).toEqual({ scope: "ledger", ledger_id: 3 });
  });

  it("家庭 → 账户 → 组合 时不会残留上一档的 id", async () => {
    const scope = makeScope();

    scope.setKind("ledger");
    await nextTick();
    scope.setId(3);
    expect(scope.scopeProps.value).toEqual({ ledgerId: 3 });

    scope.setKind("portfolio");
    await nextTick();

    expect(scope.id.value).toBeNull();
    expect(scope.scopeProps.value).toEqual({});
    // 组合档下绝不能还带着 { ledgerId: 3 }：面板会照它取数
    expect("ledgerId" in scope.scopeProps.value).toBe(false);
  });

  it("同一次操作只推进一次纪元（清 id + 换档在同 tick 内合并）", async () => {
    const scope = makeScope();

    scope.setKind("ledger");
    await nextTick();
    const marks = scope.epoch.value;

    // 同一 tick 连续两次赋值：Vue 的 watch 合并成一次回调
    scope.setId(3);
    scope.setKind("portfolio");
    await nextTick();

    expect(scope.epoch.value).toBe(marks + 1);
  });

  it("允许收窄档位：不在白名单里的档位切换被忽略", () => {
    const scope = makeScope({ kinds: ["family", "ledger"] });

    expect(scope.kindOptions.value.map(o => o.value)).toEqual([
      "family",
      "ledger"
    ]);

    scope.setKind("portfolio");
    expect(scope.kind.value).toBe("family");
  });

  it("URL 深链：?scope=ledger&scope_id=3 直接落在账户档", () => {
    route.query = { scope: "ledger", scope_id: "3" };

    const scope = makeScope({ syncUrl: true });

    expect(scope.kind.value).toBe("ledger");
    expect(scope.id.value).toBe(3);
    expect(scope.isReady.value).toBe(true);
  });

  it("URL 里的伪 id 落成 null（不许变成 NaN 传给后端）", () => {
    route.query = { scope: "ledger", scope_id: "unclassified" };

    const scope = makeScope({ syncUrl: true });

    expect(scope.kind.value).toBe("ledger");
    expect(scope.id.value).toBeNull();
    expect(Number.isNaN(scope.id.value)).toBe(false);
  });

  it("URL 里的未知档位被忽略，保持默认家庭档", () => {
    route.query = { scope: "household", scope_id: "3" };

    const scope = makeScope({ syncUrl: true });

    expect(scope.kind.value).toBe("family");
    expect(scope.id.value).toBeNull();
  });

  it("切到家庭档时把 URL 参数清干净（默认态不该在地址栏留垃圾）", async () => {
    route.query = { scope: "ledger", scope_id: "3", tab: "pnl" };

    const scope = makeScope({ syncUrl: true });
    scope.setKind("family");
    await nextTick();

    expect(replaceState).toHaveBeenCalled();
    // 其他 query 参数必须原样保留——切口径不该顺手丢掉页面的其他状态
    const url = replaceState.mock.calls.at(-1)?.[2] as string;
    expect(url).toBe("#/asset/x?tab=pnl");
  });

  it("换对象时写回 URL：scope 与 scope_id 同时更新", async () => {
    const scope = makeScope({ syncUrl: true });

    scope.setKind("ledger");
    await nextTick();
    scope.setId(9);
    await nextTick();

    const url = replaceState.mock.calls.at(-1)?.[2] as string;
    expect(url).toContain("scope=ledger");
    expect(url).toContain("scope_id=9");
  });
});
