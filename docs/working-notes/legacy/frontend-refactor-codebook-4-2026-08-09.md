# batch4 浠ｇ爜鎵嬪唽锛堝彲鐩存帴闃呰鐨勫叏閮ㄦ簮鐮侊級

> 鏈枃浠剁敱 `fundmate-optimization/batch4/` 涓嬪疄闄呬氦浠樻枃浠跺師鏍锋嫾鍚堬紝鐢ㄤ簬鍦ㄤ粎鏀寔 Markdown 鐨勫鎴风閲岄槄璇绘簮鐮併€?
> 鍏?12 涓枃浠躲€?

## `composables/ledger/context.ts`

```ts
// ============================================================================
// ledgers/detail 涓婁笅鏂囷細provide / inject 娉ㄥ叆閿?+ 绫诲瀷
// ----------------------------------------------------------------------------
// 澹崇粍浠?LedgerDetail.vue 缁勮鍏ㄩ儴 composable 杩斿洖鍊硷紝缁熶竴 provide锛?// 瀛愮粍浠堕€氳繃 useLedgerDetailContext() 娉ㄥ叆锛岄伩鍏?prop 閫忎紶涓庨噸澶嶅疄渚嬪寲銆?// 涓庢壒娆?2锛坕mport锛? 鎵规 3锛坵atchlist锛夊悓涓€濂楁満鍒躲€?// ============================================================================
import { inject } from "vue";
import type { InjectionKey } from "vue";
import type { useLedgerDetail } from "./useLedgerDetail";
import type { useAccountEdit } from "./useAccountEdit";
import type { useHoldings } from "./useHoldings";
import type { useTransactions } from "./useTransactions";
import type { useLedgerCharts } from "./useLedgerCharts";

export interface LedgerDetailContext {
  core: ReturnType<typeof useLedgerDetail>;
  accountEdit: ReturnType<typeof useAccountEdit>;
  holdings: ReturnType<typeof useHoldings>;
  transactions: ReturnType<typeof useTransactions>;
  charts: ReturnType<typeof useLedgerCharts>;
}

export const ledgerDetailContextKey: InjectionKey<LedgerDetailContext> = Symbol(
  "ledgerDetailContext"
);

export function useLedgerDetailContext(): LedgerDetailContext {
  const ctx = inject(ledgerDetailContextKey);
  if (!ctx) {
    throw new Error(
      "useLedgerDetailContext() 蹇呴』鍦?LedgerDetail.vue 鎻愪緵鐨?ledgerDetailContextKey 涔嬩笅浣跨敤"
    );
  }
  return ctx;
}
```

## `composables/ledger/index.ts`

```ts
// ============================================================================
// ledgers/detail composables 缁熶竴鍑哄彛锛坆arrel锛?// ----------------------------------------------------------------------------
// import { useLedgerDetail, useLedgerDetailContext } from "@/composables/ledger"
// ============================================================================
export * from "./types";
export * from "./useLedgerDetail";
export * from "./useAccountEdit";
export * from "./useHoldings";
export * from "./useTransactions";
export * from "./useLedgerCharts";
export * from "./context";
```

## `composables/ledger/types.ts`

```ts
// ============================================================================
// 璐︽埛鏄庣粏椤碉紙ledgers/detail锛夌被鍨嬪畾涔?// ----------------------------------------------------------------------------
// 鎶界鑷?frontend/src/views/asset/ledgers/detail.vue锛堝師 44KB 鍗曟枃浠剁粍浠讹級銆?// 鍛藉悕涓?@/api/ledger锛堝強鍏宠仈鎺ュ彛锛夎繑鍥炵粨鏋勫榻愶紱瀛楁浠ョ湡瀹炲悗绔负鍑嗭紙瑙?README 鐨?TODO锛夈€?// ============================================================================

/** 璐︽埛锛堝彴璐?/ ledger锛?*/
export interface Ledger {
  id: number | string;
  name: string;
  /** 璐︽埛绫诲瀷锛屽 fund / stock / bank / cash ...锛堢敤浜?subTitle 涓庡悓绫诲瀷绛涢€夛級 */
  type?: string;
  portfolio_id?: number;
  /** 鏄惁涓恒€屾湭鍒嗙被銆嶈櫄鎷熻处鎴?*/
  is_unclassified?: boolean;
  [key: string]: any;
}

/** 璐︽埛姒傝锛堥《閮?3 寮犲崱鐗囨暟鎹級 */
export interface LedgerSummary {
  total_market_value?: number;
  position_pnl?: number;
  holdings_count?: number;
  cash_balance?: number;
  /** 閾惰绫昏处鎴峰叧鑱旂殑璐熷€?*/
  liability?: number;
  [key: string]: any;
}

/** 鎸佷粨鏄庣粏琛?*/
export interface Position {
  id: number;
  code?: string;
  name?: string;
  quantity?: number;
  cost?: number;
  market_value?: number;
  pnl?: number;
  ledger_id?: number;
  [key: string]: any;
}

/** 浜ゆ槗璁板綍琛?*/
export interface Transaction {
  id: number;
  type?: string;
  amount?: number;
  fee?: number;
  notes?: string;
  date?: string;
  ledger_id?: number;
  [key: string]: any;
}

/** 缁勫悎锛坧ortfolio锛?*/
export interface Portfolio {
  id: number;
  name: string;
  [key: string]: any;
}

/** 浜ゆ槗绫诲瀷 鈫?灞曠ず鏍囩/閰嶈壊 */
export type TxnType = string;
```

## `composables/ledger/useAccountEdit.ts`

```ts
// ============================================================================
// useAccountEdit 鈥斺€?缂栬緫璐︽埛寮圭獥 composable
// ----------------------------------------------------------------------------
// 鎶界鑷?ledgers/detail.vue 鐨勩€岀紪杈戣处鎴枫€嶅璇濇閫昏緫銆?// 渚濊禆 core锛堣处鎴蜂俊鎭€佺粍鍚堝垪琛ㄣ€佹洿鏂版帴鍙ｃ€佸埛鏂帮級銆?// 琛ㄥ崟瀛楁娓叉煋澶嶇敤椤圭洰宸叉湁缁勪欢 AccountFormFields.vue銆?// ============================================================================
import { ref } from "vue";
import { ElMessage } from "element-plus";

type Core = ReturnType<typeof import("./useLedgerDetail").useLedgerDetail>;

export function useAccountEdit(core: Core) {
  const showEditDialog = ref(false);
  const saving = ref(false);
  const editForm = ref<Record<string, any>>({});

  async function openEditDialog() {
    if (!core.portfolioList.value.length) await core.getPortfolioList();
    editForm.value = { ...(core.accountInfo.value ?? {}) };
    showEditDialog.value = true;
  }

  async function handleUpdate() {
    saving.value = true;
    try {
      await core.updateLedger(core.ledgerId.value, editForm.value);
      showEditDialog.value = false;
      // 鍒锋柊璐︽埛淇℃伅 + 姒傝锛坅ccountInfo 鐢?ledgers 娲剧敓锛?      await core.getLedgersList();
      await core.loadSummary();
      ElMessage.success("璐︽埛宸叉洿鏂?);
    } finally {
      saving.value = false;
    }
  }

  return {
    showEditDialog,
    saving,
    editForm,
    openEditDialog,
    handleUpdate
  };
}
```

## `composables/ledger/useHoldings.ts`

```ts
// ============================================================================
// useHoldings 鈥斺€?鎸佷粨鏄庣粏 tab composable
// ----------------------------------------------------------------------------
// 鎶界鑷?ledgers/detail.vue 鐨勩€屾寔浠撴槑缁嗐€嶈〃鏍奸€昏緫锛?//   鍒嗛〉鍔犺浇銆佹寔浠撴娊灞夈€佸崟鏉?鎵归噺杩佺Щ銆佹湭鍒嗙被鎸囨淳銆佸垹闄ゃ€?// 渚濊禆 core锛堣处鎴?id銆佹湭鍒嗙被鎸囨淳锛夈€?// ============================================================================
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  getLedgerPositions,
  updateLedgerPosition,
  deleteLedgerPosition,
  migrateLedgerPositions
} from "@/api/ledger";
import type { Position } from "./types";

type Core = ReturnType<typeof import("./useLedgerDetail").useLedgerDetail>;

const PAGE_SIZE = 20;

export function useHoldings(core: Core) {
  const holdingsList = ref<Position[]>([]);
  const holdingsPage = ref(1);
  const holdingsTotal = ref(0);

  // 鍗曟潯杩佺Щ
  const migrateDialogVisible = ref(false);
  const migratingItem = ref<Position | null>(null);
  const migrateTargetLedgerId = ref<number | string | null>(null);

  // 鎵归噺杩佺Щ
  const batchMigrateVisible = ref(false);
  const batchMigrating = ref(false);
  const batchTargetLedgerId = ref<number | string | null>(null);

  // 鎶藉眽
  const drawerVisible = ref(false);
  const selectedPosition = ref<Position | null>(null);

  async function loadHoldings(page = 1) {
    if (core.isUnclassified.value) return;
    holdingsPage.value = page;
    const res = await getLedgerPositions(core.ledgerId.value, {
      page,
      page_size: PAGE_SIZE
    });
    holdingsList.value = res?.items ?? res?.data ?? res?.list ?? [];
    holdingsTotal.value = res?.total ?? holdingsList.value.length;
  }

  function openPositionDrawer(row: Position) {
    selectedPosition.value = row;
    drawerVisible.value = true;
  }

  function openMigrateDialog(row: Position) {
    migratingItem.value = row;
    migrateTargetLedgerId.value = null;
    migrateDialogVisible.value = true;
  }

  async function handleMigrate() {
    if (!migratingItem.value || migrateTargetLedgerId.value == null) return;
    await updateLedgerPosition(migratingItem.value.id, {
      ledger_id: migrateTargetLedgerId.value
    });
    migrateDialogVisible.value = false;
    migratingItem.value = null;
    await loadHoldings(holdingsPage.value);
    ElMessage.success("宸茶縼绉?);
  }

  function openBatchMigrateDialog() {
    batchTargetLedgerId.value = null;
    batchMigrateVisible.value = true;
  }

  async function handleBatchMigrate() {
    if (batchTargetLedgerId.value == null) return;
    batchMigrating.value = true;
    try {
      await migrateLedgerPositions(core.ledgerId.value, {
        target: batchTargetLedgerId.value
      });
      batchMigrateVisible.value = false;
      await loadHoldings(1);
      ElMessage.success("鎵归噺杩佺Щ瀹屾垚");
    } finally {
      batchMigrating.value = false;
    }
  }

  async function confirmDeletePosition(row: Position) {
    try {
      await ElMessageBox.confirm(`纭畾鍒犻櫎鎸佷粨銆?{row.name ?? row.code}銆嶏紵`, "鎻愮ず", {
        type: "warning"
      });
    } catch {
      return;
    }
    await deleteLedgerPosition(row.id);
    await loadHoldings(holdingsPage.value);
    ElMessage.success("宸插垹闄?);
  }

  return {
    // 鐘舵€?    holdingsList,
    holdingsPage,
    holdingsTotal,
    holdingsPageSize: PAGE_SIZE,
    migrateDialogVisible,
    migratingItem,
    migrateTargetLedgerId,
    batchMigrateVisible,
    batchMigrating,
    batchTargetLedgerId,
    drawerVisible,
    selectedPosition,
    // 鍔ㄤ綔
    loadHoldings,
    openPositionDrawer,
    openMigrateDialog,
    handleMigrate,
    openBatchMigrateDialog,
    handleBatchMigrate,
    confirmDeletePosition
  };
}
```

## `composables/ledger/useLedgerCharts.ts`

```ts
// ============================================================================
// useLedgerCharts 鈥斺€?璐︽埛鏄庣粏椤靛浘琛ㄧ敓鍛藉懆鏈?composable锛堜慨澶嶆牳蹇冿級
// ----------------------------------------------------------------------------
// 杩欓噷鐢ㄦ壒娆?1 鐨?useEchartsLifecycle 缁熶竴绠＄悊 2 涓?ECharts 瀹炰緥
// 锛堣祫浜ч厤缃ゼ鍥?+ 鏀剁泭瓒嬪娍鎶樼嚎锛夛紝褰诲簳鏇挎崲鍘?detail.vue 涓細
//   - 鎵嬪啓 echarts.init / setOption
//   - 閲嶅娉ㄥ唽鐨?onBeforeUnmount锛坆atch0 宸茬敤鑴氭湰鏈烘淇繃锛岃繖閲屼粠鏍逛笂娑堥櫎锛?//   - 鎵嬪啓 window resize 鐩戝惉 + resizeTimer 闃叉姈
//   - 缂哄け鐨?onActivated锛坘eepAlive 椤靛垏鍥炲墠鍙颁笉閲嶇粯锛?// 鍗曞疄渚嬨€佸崟澶?resize/dispose锛屾暟鎹彉鍖栬嚜鍔ㄩ噸缁樸€?// ============================================================================
import { ref, watch, nextTick } from "vue";
import type { Ref } from "vue";
import * as echarts from "echarts";
import { useEchartsLifecycle } from "@/composables/echarts/useEchartsLifecycle";
import { ECHARTS_COLOR } from "@/composables/echarts/theme";
import type { Position } from "./types";

export function useLedgerCharts(holdings: Ref<Position[]>) {
  const pieRef = ref<HTMLElement | null>(null);
  const lineRef = ref<HTMLElement | null>(null);
  /** 鏀剁泭瓒嬪娍鍛ㄦ湡锛歞ay / month / year */
  const trendPeriod = ref<"day" | "month" | "year">("month");

  // 楗煎浘锛氭寜鎸佷粨甯傚€艰仛鍚?  function buildPieOption(rows: Position[]) {
    const data = rows
      .filter((r) => r.market_value)
      .map((r) => ({ name: r.name || r.code || String(r.id), value: r.market_value }));
    return {
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
      legend: { bottom: 0, type: "scroll" },
      series: [
        {
          name: "璧勪骇閰嶇疆",
          type: "pie",
          radius: ["40%", "70%"],
          avoidLabelOverlap: true,
          itemStyle: { borderRadius: 6, borderColor: "#fff", borderWidth: 2 },
          color: ECHARTS_COLOR,
          data
        }
      ]
    };
  }

  // 鎶樼嚎锛氭敹鐩婅秼鍔匡紙鍗犱綅锛屽緟浜ゆ槗瓒嬪娍鎺ュ彛灏辩华鍚庡彲濉厖 series.data锛?  function buildLineOption() {
    return {
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: [] as string[] },
      yAxis: { type: "value" },
      series: [{ name: "鏀剁泭", type: "line", smooth: true, data: [] as number[] }]
    };
  }

  const { render, resize, charts } = useEchartsLifecycle(
    [pieRef, lineRef],
    [
      (el) => {
        const c = echarts.init(el);
        c.setOption(buildPieOption(holdings.value));
        return c;
      },
      (el) => {
        const c = echarts.init(el);
        c.setOption(buildLineOption());
        return c;
      }
    ],
    // 璐︽埛鏄庣粏涓?keepAlive 缂撳瓨椤?鈫?蹇呴』浼?true锛屽惁鍒欏垏鍥炲墠鍙板浘琛ㄧ┖鐧?    { keepAlive: true }
  );

  // 鎸佷粨鏄庣粏鍙樺寲 鈫?閲嶇粯楗煎浘
  watch(holdings, () => nextTick(render), { deep: true });
  // 瓒嬪娍鍛ㄦ湡鍒囨崲 鈫?閲嶇粯鎶樼嚎锛堟帴鍙ｅ氨缁悗鍦ㄦ閲嶆媺鏁版嵁锛?  watch(trendPeriod, () => nextTick(render));

  return { pieRef, lineRef, trendPeriod, render, resize, charts };
}
```

## `composables/ledger/useLedgerDetail.ts`

```ts
// ============================================================================
// useLedgerDetail 鈥斺€?璐︽埛鏄庣粏椤点€屽叡浜牳銆峜omposable
// ----------------------------------------------------------------------------
// 鎶界鑷?ledgers/detail.vue 鐨勮处鎴风骇鐘舵€佷笌鍔ㄤ綔锛?//   璺敱鍙傛暟瑙ｆ瀽銆佽处鎴蜂俊鎭€佹瑙堝姞杞姐€佽处鎴峰垪琛?缁勫悎鍒楄〃銆佸垹闄や笌鏈垎绫绘寚娲俱€?// 鍔熻兘 composable锛堢紪杈?鎸佷粨/浜ゆ槗/鍥捐〃锛夐€氳繃鍙傛暟娉ㄥ叆鏈牳锛岄伩鍏嶅惊鐜緷璧栥€?// ============================================================================
import { ref, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  getLedgers,
  getLedgerSummary,
  getPortfolios,
  updateLedger,
  updateAsset
} from "@/api/ledger";
import type { Ledger, LedgerSummary, Portfolio } from "./types";

/** 璐︽埛绫诲瀷 鈫?涓枃鏍囩锛堜笌 subTitle 涓€鑷达級 */
const TYPE_LABELS: Record<string, string> = {
  fund: "鍩洪噾",
  stock: "鑲＄エ",
  bank: "閾惰",
  cash: "鐜伴噾",
  precious: "璐甸噾灞?,
  realestate: "鎴夸骇"
};

export function useLedgerDetail() {
  const route = useRoute();
  const router = useRouter();

  // ---- 璺敱鍙傛暟 ----
  const ledgerId = computed<string | number>(() => route.params.id as string);
  const isUnclassified = computed(
    () => route.params.id === "unclassified" || !!route.query.name
  );
  const targetAccountName = computed(() => (route.query.name as string) || "");

  // ---- 鍏变韩鏁版嵁 ----
  const loading = ref(false);
  const ledgers = ref<Ledger[]>([]);
  const portfolioList = ref<Portfolio[]>([]);
  const assignMap = ref<Record<number, number>>({});
  const summaryData = ref<LedgerSummary>({});

  // ---- 鍒犻櫎寮圭獥锛堝疄闄呭垹闄ゅ姩浣滃湪 DeleteLedgerDialog 缁勪欢鍐咃級----
  const deleteDialogVisible = ref(false);
  const deletingAccount = ref<Ledger | null>(null);

  // ---- 褰撳墠璐︽埛娲剧敓淇℃伅 ----
  const accountInfo = computed<Ledger | undefined>(() =>
    ledgers.value.find((l) => String(l.id) === String(ledgerId.value))
  );
  const accountName = computed(() => accountInfo.value?.name ?? targetAccountName.value);
  const subTitle = computed(() => {
    const t = accountInfo.value?.type;
    return t ? TYPE_LABELS[t] ?? t : "";
  });
  const cashLedgers = computed(() => ledgers.value.filter((l) => l.type === "bank"));
  const sameTypeLedgers = computed(() =>
    ledgers.value.filter(
      (l) => l.type === accountInfo.value?.type && l.id !== accountInfo.value?.id
    )
  );

  // ---- 鏁版嵁鍔犺浇 ----
  async function getLedgersList() {
    ledgers.value = (await getLedgers()) ?? [];
  }
  async function getPortfolioList() {
    portfolioList.value = (await getPortfolios()) ?? [];
  }
  async function loadSummary() {
    if (isUnclassified.value) return; // 鏈垎绫昏处鎴锋棤姒傝
    summaryData.value = (await getLedgerSummary(ledgerId.value)) ?? {};
  }

  // ---- 鍒犻櫎 ----
  function openDeleteDialog(account: Ledger) {
    deletingAccount.value = account;
    deleteDialogVisible.value = true;
  }

  // ---- 鏈垎绫昏祫浜ф寚娲惧埌鏌愯处鎴?----
  async function handleAssign(id: number) {
    const target = assignMap.value[id];
    if (!target) return;
    await updateAsset(id, { ledger_id: target });
    delete assignMap.value[id];
  }

  return {
    // 璺敱
    route,
    router,
    ledgerId,
    isUnclassified,
    targetAccountName,
    // 鏁版嵁
    loading,
    ledgers,
    portfolioList,
    assignMap,
    summaryData,
    // 鍒犻櫎
    deleteDialogVisible,
    deletingAccount,
    // 娲剧敓
    accountInfo,
    accountName,
    subTitle,
    cashLedgers,
    sameTypeLedgers,
    // 鍔ㄤ綔
    getLedgersList,
    getPortfolioList,
    loadSummary,
    openDeleteDialog,
    handleAssign,
    // 澶嶇敤锛氭洿鏂拌处鎴蜂俊鎭紙缂栬緫寮圭獥鎻愪氦鏃惰皟鐢級
    updateLedger
  };
}
```

## `composables/ledger/useTransactions.ts`

```ts
// ============================================================================
// useTransactions 鈥斺€?浜ゆ槗璁板綍 tab composable
// ----------------------------------------------------------------------------
// 鎶界鑷?ledgers/detail.vue 鐨勩€屼氦鏄撹褰曘€嶈〃鏍奸€昏緫锛?//   鍒嗛〉鍔犺浇銆佺被鍨嬫爣绛炬槧灏勩€佺紪杈戙€佸垹闄ゃ€?// 渚濊禆 core锛堣处鎴?id锛夈€?// ============================================================================
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  getLedgerTransactions,
  updateLedgerTransaction,
  deleteLedgerTransaction
} from "@/api/ledger";
import type { Transaction } from "./types";

type Core = ReturnType<typeof import("./useLedgerDetail").useLedgerDetail>;

const PAGE_SIZE = 20;

/** 浜ゆ槗绫诲瀷 鈫?涓枃鏍囩 */
const TXN_TYPE_LABELS: Record<string, string> = {
  buy: "涔板叆",
  sell: "鍗栧嚭",
  dividend: "鍒嗙孩",
  fee: "璐圭敤",
  deposit: "瀛樺叆",
  withdraw: "鍙栧嚭"
};
/** 浜ゆ槗绫诲瀷 鈫?閰嶈壊 class锛堜笌 getTxnTypeClass 涓€鑷达級 */
const TXN_TYPE_CLASS: Record<string, string> = {
  buy: "text-danger",
  sell: "text-success",
  dividend: "text-warning",
  fee: "text-info",
  deposit: "text-primary",
  withdraw: "text-gray"
};

export function useTransactions(core: Core) {
  const transactionsList = ref<Transaction[]>([]);
  const transactionsPage = ref(1);
  const transactionsTotal = ref(0);
  const editTxnDialogVisible = ref(false);
  const editTxnForm = ref<{ id: number; fee: number; notes: string }>({
    id: 0,
    fee: 0,
    notes: ""
  });

  async function loadTransactions(page = 1) {
    if (core.isUnclassified.value) return;
    transactionsPage.value = page;
    const res = await getLedgerTransactions(core.ledgerId.value, {
      page,
      page_size: PAGE_SIZE
    });
    transactionsList.value = res?.items ?? res?.data ?? res?.list ?? [];
    transactionsTotal.value = res?.total ?? transactionsList.value.length;
  }

  function txnTypeLabel(type?: string): string {
    return (type && TXN_TYPE_LABELS[type]) || type || "鍏朵粬";
  }
  function getTxnTypeClass(type?: string): string {
    return (type && TXN_TYPE_CLASS[type]) || "text-gray";
  }

  function openEditTxnDialog(row: Transaction) {
    editTxnForm.value = { id: row.id, fee: row.fee ?? 0, notes: row.notes ?? "" };
    editTxnDialogVisible.value = true;
  }

  async function handleUpdateTransaction() {
    await updateLedgerTransaction(editTxnForm.value.id, {
      fee: editTxnForm.value.fee,
      notes: editTxnForm.value.notes
    });
    editTxnDialogVisible.value = false;
    await loadTransactions(transactionsPage.value);
    ElMessage.success("浜ゆ槗宸叉洿鏂?);
  }

  async function confirmDeleteTxn(row: Transaction) {
    try {
      await ElMessageBox.confirm("纭畾鍒犻櫎璇ヤ氦鏄撹褰曪紵", "鎻愮ず", { type: "warning" });
    } catch {
      return;
    }
    await deleteLedgerTransaction(row.id);
    await loadTransactions(transactionsPage.value);
    ElMessage.success("宸插垹闄?);
  }

  return {
    // 鐘舵€?    transactionsList,
    transactionsPage,
    transactionsTotal,
    transactionsPageSize: PAGE_SIZE,
    editTxnDialogVisible,
    editTxnForm,
    // 鍔ㄤ綔
    loadTransactions,
    txnTypeLabel,
    getTxnTypeClass,
    openEditTxnDialog,
    handleUpdateTransaction,
    confirmDeleteTxn
  };
}
```

## `views/asset/ledgers/LedgerDetail.vue`

```vue
<script setup lang="ts">
// ============================================================================
// 璐︽埛鏄庣粏椤碉紙閲嶆瀯鍚庣殑澹崇粍浠讹級
// ----------------------------------------------------------------------------
// 鐢?44KB 鐨?ledgers/detail.vue 閲嶆瀯鑰屾潵锛?//   - 璐︽埛绾х姸鎬?姒傝/鍒楄〃  鈫?useLedgerDetail
//   - 缂栬緫璐︽埛寮圭獥          鈫?useAccountEdit
//   - 鎸佷粨鏄庣粏 tab          鈫?useHoldings
//   - 浜ゆ槗璁板綍 tab          鈫?useTransactions
//   - 鍥捐〃鐢熷懡鍛ㄦ湡锛堜慨澶嶇偣锛夆啋 useLedgerCharts锛堝唴閮ㄧ敤鎵规1鐨?useEchartsLifecycle锛?// 鍏ㄩ儴 composable 杩斿洖鍊肩粍瑁呬负 LedgerDetailContext 鍚?provide锛?// 瀛愮粍浠堕€氳繃 useLedgerDetailContext() 娉ㄥ叆锛岄伩鍏?prop 閫忎紶涓庨噸澶嶅疄渚嬪寲銆?// ============================================================================
import { ref, provide } from "vue";
import { ArrowLeft } from "@element-plus/icons-vue";
import AccountFormFields from "./components/AccountFormFields.vue";
import DeleteLedgerDialog from "./components/DeleteLedgerDialog.vue";
import PositionTransactionsDrawer from "./components/PositionTransactionsDrawer.vue";

import {
  useLedgerDetail,
  useAccountEdit,
  useHoldings,
  useTransactions,
  useLedgerCharts,
  ledgerDetailContextKey
} from "@/composables/ledger";
import { usePageRefresh } from "@/composables/usePageRefresh";
import AccountSummaryCards from "./components/AccountSummaryCards.vue";
import HoldingsTable from "./components/HoldingsTable.vue";
import TransactionsTable from "./components/TransactionsTable.vue";

// ---- 缁勮鍏ㄩ儴 composable ----
const core = useLedgerDetail();
const accountEdit = useAccountEdit(core);
const holdings = useHoldings(core);
const transactions = useTransactions(core);
// 鍥捐〃渚濊禆 holdings 鍒楄〃锛堥ゼ鍥炬寜鍏惰仛鍚堬級
const charts = useLedgerCharts(holdings.holdingsList);

// 瑙ｆ瀯鍒伴《灞傦紝渚涙ā鏉胯嚜鍔ㄨВ鍖?const {
  ledgerId,
  isUnclassified,
  loading,
  accountName,
  subTitle,
  accountInfo,
  deleteDialogVisible,
  deletingAccount,
  openDeleteDialog,
  loadSummary,
  getLedgersList,
  getPortfolioList,
  ledgers
} = core;
const { showEditDialog, saving, editForm, openEditDialog, handleUpdate } = accountEdit;
const {
  holdingsList,
  holdingsPage,
  holdingsTotal,
  holdingsPageSize,
  loadHoldings,
  openPositionDrawer,
  openMigrateDialog,
  handleMigrate,
  migrateDialogVisible,
  migratingItem,
  migrateTargetLedgerId,
  openBatchMigrateDialog,
  handleBatchMigrate,
  batchMigrateVisible,
  batchMigrating,
  batchTargetLedgerId,
  drawerVisible,
  selectedPosition,
  sameTypeLedgers
} = holdings;
const {
  transactionsList,
  transactionsPage,
  transactionsTotal,
  transactionsPageSize,
  loadTransactions,
  openEditTxnDialog,
  handleUpdateTransaction,
  editTxnDialogVisible,
  editTxnForm
} = transactions;
const { pieRef, lineRef, trendPeriod } = charts;

// 鎻愪緵涓婁笅鏂?provide(ledgerDetailContextKey, { core, accountEdit, holdings, transactions, charts });

// ---- 椤堕儴 tab锛堟寔浠?浜ゆ槗 鎳掑姞杞斤級----
const activeTab = ref("holdings");
function onTabChange(name: string) {
  if (name === "holdings" && !holdingsList.value.length) loadHoldings(1);
  if (name === "transactions" && !transactionsList.value.length) loadTransactions(1);
}

// ---- 缁熶竴鍒锋柊锛堜緵 usePageRefresh 淇″彿瑙﹀彂锛?---
function refreshAll() {
  loadSummary();
  loadHoldings(holdingsPage.value);
  loadTransactions(transactionsPage.value);
}

// 鍒濇鍔犺浇 + 璁拌处浜嬩欢鑷姩鍒锋柊锛坆atch1 宸蹭慨澶嶅苟鍙戦槻鎶?bug锛?getLedgersList();
getPortfolioList();
loadSummary();
loadHoldings(1);
loadTransactions(1);
usePageRefresh(refreshAll);

function goBack() {
  core.router.back();
}
</script>

<template>
  <div class="account-detail">
    <!-- 椤舵爮 -->
    <div class="mb-4 flex items-center gap-2">
      <el-button text :icon="ArrowLeft" @click="goBack">杩斿洖</el-button>
      <template v-if="!isUnclassified">
        <el-button @click="openEditDialog">缂栬緫</el-button>
        <el-button @click="openBatchMigrateDialog">鎵归噺杩佺Щ</el-button>
        <el-button type="danger" @click="openDeleteDialog(accountInfo)">鍒犻櫎</el-button>
      </template>
    </div>

    <div v-if="loading" class="py-20 text-center text-gray-400">鍔犺浇涓€?/div>

    <template v-else>
      <!-- 璐︽埛澶?-->
      <div class="mb-6">
        <h2 class="text-2xl font-semibold">{{ accountName }}</h2>
        <el-tag v-if="subTitle" class="mt-1">{{ subTitle }}</el-tag>
      </div>

      <!-- 姒傝鍗＄墖 -->
      <AccountSummaryCards />

      <!-- 鍥捐〃琛岋紙ECharts 鐢熷懡鍛ㄦ湡鐢?useLedgerCharts 缁熶竴绠＄悊锛?->
      <div class="my-4 grid grid-cols-2 gap-4">
        <div class="rounded border p-3">
          <div class="mb-2 font-medium">璧勪骇閰嶇疆</div>
          <div :ref="(el: any) => (pieRef.value = el)" class="h-64"></div>
        </div>
        <div class="rounded border p-3">
          <div class="mb-2 flex items-center justify-between">
            <span class="font-medium">鏀剁泭瓒嬪娍</span>
            <el-radio-group v-model="trendPeriod" size="small">
              <el-radio-button value="day">鏃?/el-radio-button>
              <el-radio-button value="month">鏈?/el-radio-button>
              <el-radio-button value="year">骞?/el-radio-button>
            </el-radio-group>
          </div>
          <div :ref="(el: any) => (lineRef.value = el)" class="h-64"></div>
        </div>
      </div>

      <!-- 鏄庣粏 tabs -->
      <el-card>
        <el-tabs v-model="activeTab" @tab-change="onTabChange">
          <el-tab-pane label="鎸佷粨鏄庣粏" name="holdings">
            <HoldingsTable />
          </el-tab-pane>
          <el-tab-pane label="浜ゆ槗璁板綍" name="transactions">
            <TransactionsTable />
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </template>

    <!-- 缂栬緫璐︽埛 -->
    <el-dialog v-model="showEditDialog" title="缂栬緫璐︽埛">
      <AccountFormFields v-model="editForm" :portfolios="core.portfolioList.value" />
      <template #footer>
        <el-button @click="showEditDialog = false">鍙栨秷</el-button>
        <el-button type="primary" :loading="saving" @click="handleUpdate">淇濆瓨</el-button>
      </template>
    </el-dialog>

    <!-- 鍗曟潯杩佺Щ -->
    <el-dialog v-model="migrateDialogVisible" title="杩佺Щ鎸佷粨">
      <el-select v-model="migrateTargetLedgerId" placeholder="閫夋嫨鐩爣璐︽埛" class="w-full">
        <el-option
          v-for="l in sameTypeLedgers"
          :key="String(l.id)"
          :label="l.name"
          :value="l.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="migrateDialogVisible = false">鍙栨秷</el-button>
        <el-button type="primary" @click="handleMigrate">纭畾</el-button>
      </template>
    </el-dialog>

    <!-- 鎵归噺杩佺Щ -->
    <el-dialog v-model="batchMigrateVisible" title="鎵归噺杩佺Щ鎸佷粨">
      <el-select v-model="batchTargetLedgerId" placeholder="閫夋嫨鐩爣璐︽埛" class="w-full">
        <el-option v-for="l in ledgers" :key="String(l.id)" :label="l.name" :value="l.id" />
      </el-select>
      <template #footer>
        <el-button @click="batchMigrateVisible = false">鍙栨秷</el-button>
        <el-button type="primary" :loading="batchMigrating" @click="handleBatchMigrate">
          纭畾
        </el-button>
      </template>
    </el-dialog>

    <!-- 缂栬緫浜ゆ槗 -->
    <el-dialog v-model="editTxnDialogVisible" title="缂栬緫浜ゆ槗">
      <el-form label-width="64px">
        <el-form-item label="璐圭敤">
          <el-input v-model.number="editTxnForm.fee" />
        </el-form-item>
        <el-form-item label="澶囨敞">
          <el-input v-model="editTxnForm.notes" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editTxnDialogVisible = false">鍙栨秷</el-button>
        <el-button type="primary" @click="handleUpdateTransaction">淇濆瓨</el-button>
      </template>
    </el-dialog>

    <!-- 鍒犻櫎璐︽埛锛堝凡鏈夌粍浠讹紝鑷甫鍒犻櫎纭涓?loading锛?->
    <DeleteLedgerDialog
      v-model:visible="deleteDialogVisible"
      :ledger-id="deletingAccount?.id"
      :ledger-name="deletingAccount?.name"
      :position-count="holdingsList.length"
      @deleted="goBack"
    />
    <!-- 鎸佷粨鎶藉眽锛堝凡鏈夌粍浠讹紝鍐呴儴鎸?positionData.id 鎷夊彇浜ゆ槗锛?->
    <PositionTransactionsDrawer v-model:visible="drawerVisible" :position-data="selectedPosition" />
  </div>
</template>

<style scoped>
.account-detail {
  padding: 16px;
}
</style>
```

## `views/asset/ledgers/components/AccountSummaryCards.vue`

```vue
<script setup lang="ts">
// 璐︽埛姒傝鍗＄墖锛堟娊绂昏嚜 ledgers/detail.vue 椤堕儴 3 寮犲崱鐗囷級
import { computed } from "vue";
import { formatCurrency } from "@/utils/currency";
import { getRiseColor, getFallColor } from "@/composables/echarts/theme";
import { useLedgerDetailContext } from "@/composables/ledger";

const { core } = useLedgerDetailContext();
const { summaryData, accountInfo } = core;

const pnlColor = computed(() =>
  (summaryData.value.position_pnl ?? 0) >= 0 ? getRiseColor() : getFallColor()
);
const isBank = computed(() => accountInfo.value?.type === "bank");
</script>

<template>
  <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
    <div class="rounded border p-4">
      <div class="text-gray-500">鎬昏祫浜?/div>
      <div class="mt-1 text-xl font-semibold">
        {{ formatCurrency(summaryData.total_market_value ?? 0) }}
      </div>
    </div>

    <div class="rounded border p-4">
      <div class="text-gray-500">鎸佷粨鐩堜簭</div>
      <div class="mt-1 text-xl font-semibold" :style="{ color: pnlColor }">
        {{ formatCurrency(summaryData.position_pnl ?? 0) }}
      </div>
    </div>

    <div class="rounded border p-4">
      <div class="text-gray-500">鎸佷粨鏁?/ 鐜伴噾浣欓</div>
      <div class="mt-1 text-xl font-semibold">
        {{ summaryData.holdings_count ?? 0 }} 绗?/
        {{ formatCurrency(summaryData.cash_balance ?? 0) }}
      </div>
      <div v-if="isBank && summaryData.liability" class="mt-1 text-sm text-gray-400">
        鍏宠仈璐熷€猴細{{ formatCurrency(summaryData.liability) }}
      </div>
    </div>
  </div>
</template>
```

## `views/asset/ledgers/components/HoldingsTable.vue`

```vue
<script setup lang="ts">
// 鎸佷粨鏄庣粏琛紙鎶界鑷?ledgers/detail.vue 鐨?holdings tab锛?import ProductDisplay from "@/components/ProductDisplay.vue";
import { useLedgerDetailContext } from "@/composables/ledger";

const { core, holdings } = useLedgerDetailContext();
const {
  holdingsList,
  holdingsPage,
  holdingsTotal,
  holdingsPageSize,
  loadHoldings,
  openPositionDrawer,
  openMigrateDialog,
  confirmDeletePosition
} = holdings;
const { isUnclassified, ledgers, assignMap, handleAssign } = core;
</script>

<template>
  <div>
    <div class="mb-2 flex items-center justify-between">
      <span class="font-medium">鎸佷粨鏄庣粏</span>
      <el-button
        v-if="!isUnclassified"
        size="small"
        type="primary"
        @click="holdings.openBatchMigrateDialog()"
      >
        鎵归噺杩佺Щ
      </el-button>
    </div>

    <el-table :data="holdingsList" row-key="id" @row-click="openPositionDrawer">
      <el-table-column label="浜у搧">
        <template #default="{ row }">
          <ProductDisplay :code="row.code" :name="row.name" />
        </template>
      </el-table-column>
      <el-table-column label="鏁伴噺" prop="quantity" width="100" />
      <el-table-column label="甯傚€? prop="market_value" width="120" />
      <el-table-column label="鐩堜簭" prop="pnl" width="120" />
      <el-table-column label="鎿嶄綔" width="220" fixed="right">
        <template #default="{ row }">
          <el-button text size="small" @click.stop="openPositionDrawer(row)">鏄庣粏</el-button>
          <template v-if="!isUnclassified">
            <el-button text size="small" @click.stop="openMigrateDialog(row)">杩佺Щ</el-button>
            <el-button text size="small" type="danger" @click.stop="confirmDeletePosition(row)">
              鍒犻櫎
            </el-button>
          </template>
          <template v-else>
            <el-select
              v-model="assignMap[row.id]"
              size="small"
              placeholder="鎸囨淳鍒?
              class="w-28"
              @click.stop
              @change="handleAssign(row.id)"
            >
              <el-option v-for="l in ledgers" :key="String(l.id)" :label="l.name" :value="l.id" />
            </el-select>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-3 flex justify-end">
      <el-pagination
        v-model:current-page="holdingsPage"
        :page-size="holdingsPageSize"
        :total="holdingsTotal"
        layout="total, prev, pager, next"
        @current-change="(p: number) => loadHoldings(p)"
      />
    </div>
  </div>
</template>
```

## `views/asset/ledgers/components/TransactionsTable.vue`

```vue
<script setup lang="ts">
// 浜ゆ槗璁板綍琛紙鎶界鑷?ledgers/detail.vue 鐨?transactions tab锛?import { useLedgerDetailContext } from "@/composables/ledger";

const { transactions } = useLedgerDetailContext();
const {
  transactionsList,
  transactionsPage,
  transactionsTotal,
  transactionsPageSize,
  loadTransactions,
  txnTypeLabel,
  getTxnTypeClass,
  openEditTxnDialog,
  confirmDeleteTxn
} = transactions;
</script>

<template>
  <div>
    <div class="mb-2 font-medium">浜ゆ槗璁板綍</div>

    <el-table :data="transactionsList" row-key="id">
      <el-table-column label="绫诲瀷" width="100">
        <template #default="{ row }">
          <span :class="getTxnTypeClass(row.type)">{{ txnTypeLabel(row.type) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="閲戦" prop="amount" width="120" />
      <el-table-column label="璐圭敤" prop="fee" width="100" />
      <el-table-column label="澶囨敞" prop="notes" />
      <el-table-column label="鏃ユ湡" prop="date" width="140" />
      <el-table-column label="鎿嶄綔" width="160" fixed="right">
        <template #default="{ row }">
          <el-button text size="small" @click="openEditTxnDialog(row)">缂栬緫</el-button>
          <el-button text size="small" type="danger" @click="confirmDeleteTxn(row)">
            鍒犻櫎
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-3 flex justify-end">
      <el-pagination
        v-model:current-page="transactionsPage"
        :page-size="transactionsPageSize"
        :total="transactionsTotal"
        layout="total, prev, pager, next"
        @current-change="(p: number) => loadTransactions(p)"
      />
    </div>
  </div>
</template>
```
