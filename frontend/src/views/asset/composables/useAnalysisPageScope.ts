/**
 * 复盘页的口径主控（#3287 B）：档位状态 + 账户下拉数据 + 一行口径说明。
 *
 * ## 为什么抽成 composable
 *
 * 复盘页已顶在 `check_vue_size.mjs` 的 400 行闸门上（拆出净值区块后仍然差 11 行），
 * 而这段与页面结构无关——它是「页级口径」这一件事的完整实现。搬进来后页面只剩
 * 一行解构 + 模板里的绑定。
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
  const ledgerLoading = ref(false);
  /** 下拉选项：只取 id + 名称，账户对象其余字段这里用不到 */
  const ledgerOptions = computed(() =>
    ledgers.value.map(l => ({ id: l.id, name: l.name }))
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
    if (scopeId.value == null) return "选择账户后取数";
    const hit = ledgers.value.find(l => l.id === scopeId.value);
    return hit ? `只看 ${hit.name}` : `账户 #${scopeId.value}`;
  });

  const loadLedgers = async () => {
    ledgerLoading.value = true;
    try {
      const res = await getLedgers();
      ledgers.value = res.data ?? [];
    } catch {
      // 账户列表拿不到只影响切换器的下拉，不影响家庭级首屏——不弹错、不阻塞
      ledgers.value = [];
    } finally {
      ledgerLoading.value = false;
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
    ledgerLoading,
    scopeHint,
    loadLedgers
  };
}
