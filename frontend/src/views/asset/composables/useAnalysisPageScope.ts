/**
 * 复盘页的口径主控（#3287 B）：档位状态 + 账户下拉数据 + 一行口径说明。
 *
 * ## 为什么抽成 composable
 *
 * 复盘页已顶在 `check_vue_size.mjs` 的 400 行闸门上（拆出净值区块后仍然差 11 行），
 * 而这段与页面结构无关——它是「页级口径」这一件事的完整实现。搬进来后页面只剩
 * 一行解构 + 模板里的绑定。
 *
 * ## 为什么账户与组合的选项要分开取
 *
 * 切换器的下拉内容是**档位的函数**：账户档列账户、组合档列组合。合成一份
 * 「id → 名字」的清单会撞 id（账户 3 与组合 3 是两个东西），所以按档位取，
 * 且两个列表都**一次性预热**（切换器要能立刻展开，不能点一下等一次接口）。
 *
 * 取不到只是「这一档暂时没东西可选」，不弹错、不阻塞家庭级首屏——组合接口失败
 * 不该让整页打不开（它只影响组合档的选择）。
 *
 * ## 为什么档位是算出来的
 *
 * `commonAnalysisKinds()` 取所有区块支持档位的**交集**。硬编码 `["family","ledger"]`
 * 会在某天某块补上组合档之后过期（没人记得回来改），而**多开一档的代价是静默错数**：
 * 不支持的块会拿 `undefined` 当 props，面板侧把 `{}` 读成家庭级，于是「组合」标签下
 * 摆着全家庭的钱。
 */

import { computed, ref } from "vue";
import { useAnalysisScope } from "@/composables/analysisScope";
import { getLedgers, type LedgerItem } from "@/api/ledger";
import { getPortfolios, type PortfolioItem } from "@/api/portfolio";
import { commonAnalysisKinds } from "../analysisScopeSupport";

export function useAnalysisPageScope() {
  const scopeKinds = commonAnalysisKinds();
  const {
    kind: scopeKind,
    id: scopeId,
    isReady: scopeReady,
    scopeProps,
    setKind: setScopeKind,
    setId: setScopeId
  } = useAnalysisScope({ kinds: scopeKinds });

  const ledgers = ref<LedgerItem[]>([]);
  const portfolios = ref<PortfolioItem[]>([]);
  const optionsLoading = ref(false);

  /**
   * 下拉选项：**只取 id + 名称**（账户 / 组合对象其余字段这里用不到）。
   *
   * 两份**分开给**，不做「按档位合成一份」：`ScopeBar` 的 `ledgers` / `portfolios`
   * 是两条独立入参，由它自己按档位挑；合成一份再喂给 `ledgers` 会让组合档读到
   * 空的 `portfolios`——切换器照常显示「组合」按钮与「暂无组合」提示，看起来像
   * 「这个家庭还没有组合」，实际是接线错了。两份 id 空间本来就互不相干。
   */
  const toOptions = (list: Array<{ id: number; name: string }>) =>
    list.map(o => ({ id: o.id, name: o.name }));
  const ledgerOptions = computed(() => toOptions(ledgers.value));
  const portfolioOptions = computed(() => toOptions(portfolios.value));

  /** 当前档位对应的那一份（只供本文件的 hint 查名字用，不往模板下传） */
  const scopeOptions = computed(() =>
    scopeKind.value === "portfolio"
      ? portfolioOptions.value
      : ledgerOptions.value
  );

  /**
   * 右侧一行小字：档位按钮说明「按什么看」，这里说明「实际取到了什么」。
   * 未选对象时明说「选择账户后取数」——此时页面不渲染任何数字（见页面的
   * `scopeReady` 分支），不能让人对着一片空白猜发生了什么。
   */
  const scopeHint = computed(() => {
    if (scopeKind.value === "family") {
      return ledgers.value.length
        ? `全家庭 · ${ledgers.value.length} 个账户`
        : "";
    }
    const noun = scopeKind.value === "portfolio" ? "组合" : "账户";
    if (scopeId.value == null) return `选择${noun}后取数`;
    const hit = scopeOptions.value.find(o => o.id === scopeId.value);
    return hit ? `只看 ${hit.name}` : `${noun} #${scopeId.value}`;
  });

  /**
   * 预热两份清单。用 `allSettled` 而不是 `all`：组合接口挂了不该连带把账户列表
   * 一起丢掉（反之亦然），两档各自降级成「暂无可选项」即可。
   */
  const loadScopeOptions = async () => {
    optionsLoading.value = true;
    try {
      const [ledgerRes, portfolioRes] = await Promise.allSettled([
        getLedgers(),
        getPortfolios()
      ]);
      ledgers.value =
        ledgerRes.status === "fulfilled" ? (ledgerRes.value.data ?? []) : [];
      portfolios.value =
        portfolioRes.status === "fulfilled"
          ? (portfolioRes.value.data ?? [])
          : [];
    } finally {
      optionsLoading.value = false;
    }
  };

  return {
    scopeKinds,
    scopeKind,
    scopeId,
    scopeReady,
    scopeProps,
    setScopeKind,
    setScopeId,
    ledgerOptions,
    portfolioOptions,
    optionsLoading,
    scopeHint,
    loadScopeOptions
  };
}
