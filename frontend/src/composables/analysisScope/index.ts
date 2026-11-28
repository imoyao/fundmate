/**
 * 分析页的**页级口径状态**（家庭 / 账户 / 组合）——复盘页各区块共用一套。
 *
 * ## 为什么要有这个 composable
 *
 * 口径在此之前是各页的局部 `ref`：持仓分析页有一份手写的 `scopeKind + scopeId`，
 * 复盘页干脆写死家庭级。两页一旦合并（或同页出现多块），就会出现「上半页家庭级、
 * 下半页账户级」的混合态——**而界面上看不出来**。#2595 的事故（面板漏传 scope 静默
 * 显示家庭数据）就是这个形态的下游表现。
 *
 * 把状态收在这里，换来的是一条可判定的规则：**取数前先问 `isReady`**。
 * `isReady === false` 表示「用户切到了账户档但还没选账户」，此时不许取数——
 * 因为空 props 在面板里等于家庭级，取回来的就是别处的数。
 *
 * ## epoch：给异步响应用
 *
 * 切档时 N 个区块并发重取，返回顺序**不保证**。若各区块自己防抖，必然出现
 * 「XIRR 已是账户级、曲线还是家庭级」的中间态。`epoch` 是页级单调计数：
 * 区块取数时记下 `const e = epoch.value`，回写前 `if (e !== epoch.value) return;`。
 *
 * 这和 `ReturnOverviewSection` 里原有的 `xirrReqSeq` 是同一手法，只是提到了页级
 * （单区块自防抖解决不了跨区块的顺序错乱）。
 *
 * ## URL 同步
 *
 * 口径进 query（`?scope=ledger&scope_id=3`），三个理由：
 * 1. 合并后深链价值高（「帮我看下招行这个账户」可以直接发链接）；
 * 2. `/asset/position-analysis` 收敛成重定向时，要靠这两个参数决定落到哪个锚点；
 * 3. 刷新不丢口径——分析是「看着想」的场景，刷新后回到全家庭等于让人重选一遍。
 *
 * 用 `router.replace` 而不是 `push`：切档是**同一页面的视图参数**，不是导航步骤，
 * 不该在浏览器历史里堆一层（否则「后退」要按十几次才离开本页）。
 *
 * 只在 setup 阶段**同步读一次** URL，之后不监听 `route.query`：监听 + 写回会成环，
 * 且组合切换的并发写容易互相覆盖。代价是浏览器前进/后退不跟随档位——`replace`
 * 本来也不产生历史，两者一致。
 */

import { computed, ref, watch } from "vue";
import type { ComputedRef, Ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  SCOPE_KIND_LABELS,
  toScopeProps,
  toScopeQuery,
  type ScopeKind,
  type ScopeProps,
  type ScopeQuery
} from "./toScopeProps";

/** 三档全集。默认开放全部；调用方可用 `kinds` 收窄到当前真正支持的那几档 */
const ALL_KINDS: readonly ScopeKind[] = ["family", "ledger", "portfolio"];

export interface UseAnalysisScopeOptions {
  /**
   * 本页允许的档位（有序，第一个是初始档位）。
   *
   * 为什么允许收窄：**档位只能在「整页每一块都算得出来」时才摆出来**。
   * 摆出组合档而页面上有 4 块返回「不支持」，用户会以为是半成品；反过来在
   * 没补齐的页面上偷偷让某几块退回家庭级，才是真错数。收窄是显式的诚实。
   */
  kinds?: readonly ScopeKind[];
  /** 是否把口径同步到 URL query（默认 true）。无路由上下文（单测 / 嵌入式面板）可关掉 */
  syncUrl?: boolean;
  /** query 参数名，默认 `scope` / `scope_id` */
  queryKeys?: { kind?: string; id?: string };
}

export interface UseAnalysisScopeReturn {
  /** 当前档位 */
  kind: Ref<ScopeKind>;
  /** 当前选中的账户 / 组合 id；家庭档恒为 null */
  id: Ref<number | null>;
  /** 页级请求纪元：每次有效切换 +1，异步响应回写前比对 */
  epoch: Ref<number>;
  /** 是否可以取数：家庭档恒 true；账户/组合档须先选对象 */
  isReady: ComputedRef<boolean>;
  /** 面板 props（`ledgerId` / `portfolioId`） */
  scopeProps: ComputedRef<ScopeProps>;
  /** 接口查询参数（`scope` + 对应 id） */
  scopeQuery: ComputedRef<ScopeQuery>;
  /** 档位选项，直接喂 `ScopeBar` */
  kindOptions: ComputedRef<Array<{ label: string; value: ScopeKind }>>;
  /** 切档（会清空已选对象——残留上一档的 id 是脏口径） */
  setKind: (next: ScopeKind) => void;
  /** 选对象 / 清空 */
  setId: (next: number | null) => void;
  /** 回到初始档位 */
  reset: () => void;
}

/**
 * 把 query 里的 id 归一成数字。
 *
 * `Number.isFinite` 过滤是硬要求（#2739 的教训）：`Number('unclassified')` 是 `NaN`，
 * `NaN` 传给 axios 会序列化成 `ledger_id=NaN`，后端 `type=int` 解析失败回 `None`，
 * 于是「传了个坏 id」变成「没传 id」= 上级口径 ⇒ 数据标签双错且不报错。
 */
function parseId(raw: unknown): number | null {
  if (raw == null || raw === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function isKind(
  value: unknown,
  kinds: readonly ScopeKind[]
): value is ScopeKind {
  return typeof value === "string" && kinds.includes(value as ScopeKind);
}

export function useAnalysisScope(
  options: UseAnalysisScopeOptions = {}
): UseAnalysisScopeReturn {
  const kinds = options.kinds?.length ? options.kinds : ALL_KINDS;
  const syncUrl = options.syncUrl !== false;
  const kindKey = options.queryKeys?.kind ?? "scope";
  const idKey = options.queryKeys?.id ?? "scope_id";

  const route = useRoute();
  const router = useRouter();

  const kind = ref<ScopeKind>(kinds[0]);
  const id = ref<number | null>(null);
  const epoch = ref(0);

  const isReady = computed(() => kind.value === "family" || id.value != null);
  const scopeProps = computed(() => toScopeProps(kind.value, id.value));
  const scopeQuery = computed(() => toScopeQuery(kind.value, id.value));
  const kindOptions = computed(() =>
    kinds.map(k => ({ label: SCOPE_KIND_LABELS[k], value: k }))
  );

  /**
   * 写回 URL。家庭档**删掉两个键**而不是写 `scope=family`：
   * 干净 URL 是可分享的默认态，"全家庭" 是本页的常态，不值得每次都出现在地址栏里。
   *
   * ## 为什么用 `history.replaceState` 而不是 `router.replace`
   *
   * 本仓的 `lay-content` 给 `<router-view>` 绑了 `:key="fullPath"`——**query 一变，
   * 整个页面销毁重建**。走 router 的后果实测是：切一次口径 → 页面所有区块重新挂载、
   * 重发十余个请求、每块闪一遍骨架，而其中大半与口径无关。
   *
   * 更糟的是它会**造出静默错口径**：重建后 `onMounted` 重新取数，此时若档位是「单账户
   * 但还没选人」，请求不带 id ⇒ 拿回家庭级数据摆在「单账户」标签下。2026-11-27 走查
   * 实测到这一条（切档 780ms 后四卡从 `--` 变回家庭数）。
   *
   * `replaceState` 只改地址栏：刷新 / 分享走 `readUrl` 解析（深链能力保留），
   * 当前会话不重建、不产生历史条目。代价是 `route.query` 与实际地址栏不同步——
   * 本模块的读取只发生在 setup 阶段一次，故无影响；将来若要 watch 路由参数，
   * 得先解掉 `:key="fullPath"` 那个绑定。
   */
  function writeUrl() {
    if (!syncUrl || !route || !router) return;
    const next: Record<string, string> = {};
    for (const [k, v] of Object.entries(route.query)) {
      if (typeof v === "string" && k !== kindKey && k !== idKey) next[k] = v;
    }
    if (kind.value !== "family") {
      next[kindKey] = kind.value;
      if (id.value != null) next[idKey] = String(id.value);
    }
    if (typeof history === "undefined" || !history.replaceState) return;
    const resolved = router.resolve({ path: route.path, query: next }).href;
    // hash 模式下 `href` 是 `/path?query`，要补 `#`；history 模式原样用
    const hashMode =
      typeof window !== "undefined" && window.location.hash.startsWith("#/");
    history.replaceState(
      history.state,
      "",
      hashMode ? `#${resolved}` : resolved
    );
  }

  /**
   * setup 阶段**同步**读 URL（不用 onMounted）：子组件的 `onMounted` 先于父页触发，
   * 挂在父页 mounted 上的初始化会晚于首屏取数 ⇒ 深链打开先按家庭级拉一遍再切，
   * 用户会看到数字跳一次。
   */
  function readUrl() {
    if (!syncUrl || !route) return;
    const rawKind = route.query[kindKey];
    if (!isKind(rawKind, kinds)) return;
    kind.value = rawKind;
    id.value = rawKind === "family" ? null : parseId(route.query[idKey]);
  }

  readUrl();

  // 有效切换才推进 epoch：同一 tick 内「清 id + 换档」会被 Vue 合并成一次回调，
  // 因此一次用户操作只 +1（不会让区块收到两个纪元而白白丢弃一次响应）。
  //
  // ⚠️ 注册顺序有意义：本 watcher 在 `useAnalysisScope()` 内注册，早于宿主页自己
  // 那个「口径变了就重取」的 watcher。Vue 按创建顺序执行同一批 job，所以宿主页
  // 取数时读到的 `epoch` **已经是新值**。若把本文件挪到宿主 watch 之后初始化，
  // 宿主会先发请求（带旧 mark）再被 +1，响应回来时永远「过期」⇒ 请求全丢。
  watch([kind, id], () => {
    epoch.value += 1;
    writeUrl();
  });

  function setKind(next: ScopeKind) {
    if (!isKind(next, kinds) || next === kind.value) return;
    kind.value = next;
    id.value = null;
  }

  function setId(next: number | null) {
    id.value = next;
  }

  function reset() {
    kind.value = kinds[0];
    id.value = null;
  }

  return {
    kind,
    id,
    epoch,
    isReady,
    scopeProps,
    scopeQuery,
    kindOptions,
    setKind,
    setId,
    reset
  };
}
