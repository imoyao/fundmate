# batch2 浠ｇ爜鎵嬪唽锛堝彲鐩存帴闃呰鐨勫叏閮ㄦ簮鐮侊級

> 鏈枃浠剁敱 `fundmate-optimization/batch2/` 涓嬪疄闄呬氦浠樻枃浠跺師鏍锋嫾鍚堬紝鐢ㄤ簬鍦ㄤ粎鏀寔 Markdown 鐨勫鎴风閲岄槄璇绘簮鐮併€?
> 鍏?21 涓枃浠躲€?

## `composables/import/context.ts`

```ts
// src/composables/import/context.ts
//
// 瀵煎叆鍚戝鐨勮法缁勪欢鍏变韩涓婁笅鏂囥€傜敱鐖跺３ index.vue 鐢?provide() 娉ㄥ叆鍏ㄩ儴 composable 杩斿洖鍊硷紝
// 鍚勬楠ょ粍浠剁敤 inject() 鍙栫敤锛岄伩鍏?prop 灞傚眰閫忎紶銆佷篃閬垮厤姣忎釜姝ラ鍚勮嚜瀹炰緥鍖栧鑷寸姸鎬佷笉浜掗€氥€?//
import type { InjectionKey } from "vue";
import type { useImportWizard } from "./useImportWizard";
import type { usePreviewData } from "./usePreviewData";
import type { useRowSelection } from "./useRowSelection";
import type { useRowEditing } from "./useRowEditing";
import type { useBatchFix } from "./useBatchFix";
import type { useAllocation } from "./useAllocation";
import type { useDuplicateHandling } from "./useDuplicateHandling";
import type { useFileParser } from "./useFileParser";

/** 鎵€鏈?composable 杩斿洖鍊肩殑骞堕泦 = 姝ラ缁勪欢鍙敤鐨勫畬鏁翠笂涓嬫枃 */
export type ImportContext = ReturnType<typeof useImportWizard> &
  ReturnType<typeof usePreviewData> &
  ReturnType<typeof useRowSelection> &
  ReturnType<typeof useRowEditing> &
  ReturnType<typeof useBatchFix> &
  ReturnType<typeof useAllocation> &
  ReturnType<typeof useDuplicateHandling> &
  ReturnType<typeof useFileParser>;

export const importContextKey: InjectionKey<ImportContext> = Symbol("importContext");
```

## `composables/import/index.ts`

```ts
// src/composables/import/index.ts
//
// 缁熶竴鍑哄彛锛歩mport(瀵煎叆鍚戝) 鐩稿叧鐨?8 涓?composable + 鍏变韩绫诲瀷銆?// index.vue 鍙渶 `import { useImportWizard, usePreviewData, ... } from "@/composables/import"`銆?//
export * from "./types";
export * from "./context";
export * from "./useImportWizard";
export * from "./useFileParser";
export * from "./usePreviewData";
export * from "./useRowSelection";
export * from "./useRowEditing";
export * from "./useBatchFix";
export * from "./useAllocation";
export * from "./useDuplicateHandling";
```

## `composables/import/types.ts`

```ts
// src/composables/import/types.ts
//
// import/index.vue 鎶界 composable 鐨勫叡浜被鍨嬨€?// 瀛楁鍚嶄笌鍘熷缁勪欢瀹屽叏涓€鑷达紙鏉ヨ嚜瀵?95KB 婧愮爜鐨勭粨鏋勫垎鏋愶級锛屼究浜庢満姊版惉杩愩€?// 鈿?鑻ヤ綘鍚庣 preview 琛岀粨鏋勪笌涓嬮潰瀵逛笉榻愶紝浠ュ疄闄?API 杩斿洖涓哄噯锛岃繖閲屼粎浣滃墠绔绾︺€?
/** 瀵煎叆鏍煎紡鏍囪瘑锛堜笌鍘?formatGuides 鐨?key 涓€鑷达級 */
export type ImportFormat =
  | "standard_stock"
  | "ths"
  | "standard_fund"
  | "tiantian_fund"
  | "alipay_pdf"
  | "alipay_fund";

/** 鎵归噺淇鐨勪笁绫婚棶棰橈紙涓庡師 problemCategories 涓€鑷达級 */
export type ProblemCategoryKey = "missingCode" | "missingQtyPrice" | "mismatch";

/** 璐︽埛锛坙edger锛夋潯鐩紝鏉ヨ嚜 @/api/ledger 鐨?getLedgers */
export interface LedgerItem {
  id: number;
  name: string;
  ledger_type: string;
  allocation?: string;
  // 鍏朵綑瀛楁鎸夐渶鎵╁睍
  [key: string]: unknown;
}

/**
 * 棰勮鏁版嵁琛屻€傚瓧娈靛悕 1:1 瀵瑰簲鍘熺粍浠堕噷 row.xxx 鐨勭敤娉曘€? * 甯︿笅鍒掔嚎鍓嶇紑鐨勫瓧娈碉紙_rowKey/_oldValue/...锛変负鍓嶇杩愯鏃堕檮鍔狅紝闈炲悗绔瓧娈点€? */
export interface PreviewRow {
  _rowKey: string | number; // addRowKeys 娉ㄥ叆鐨勫敮涓€閿?  symbol: string;
  name: string;
  quantity: number;
  price: number;
  amount: number;
  fee: number;
  allocation: string;
  account_name: string;
  is_duplicate: boolean;
  error?: string;
  is_cash_transfer: boolean;
  is_calculated: boolean; // 鏅鸿兘濉厖鍚庣疆 true
  isEditingQty?: boolean; // 琛屽唴缂栬緫鎬?  isEditingPrice?: boolean;
  _oldValue?: number; // 缂栬緫鍓嶇紦瀛?  smartFilled?: boolean;
  type?: string;
  display_type?: string;
  op_type?: string;
  op_type_label?: string;
  trade_date?: string;
  notes?: string;
  contract_id?: string;
  net_amount?: number;
  link_group_id?: string | number;
  is_merged?: boolean; // 鍚堝苟琛岋紙绾㈠埄+绋庯級
  children?: PreviewRow[]; // 鏍戣〃瀛愯
  _allocationManual?: boolean;
  _duplicateHandled?: boolean;
  _dataMissing?: boolean;
  [key: string]: unknown;
}

/** 鍒嗛厤鐩爣鍒嗙粍锛堟寜璧勪骇绫诲瀷鑱氬悎锛?*/
export interface AllocationGroup {
  type: string;
  label: string;
  rows: PreviewRow[];
  allocation: string;
}

/** 瀵煎叆缁撴灉姹囨€伙紙姝ラ3锛?*/
export interface ImportResult {
  importedCount: number;
  skippedCount: number;
  orphanCount: number;
  errorCount: number;
  importErrors: ImportErrorItem[];
  nothingImported: boolean;
  showPriceUpdateTip: boolean;
}

export interface ImportErrorItem {
  rowKey: string | number;
  message: string;
}
```

## `composables/import/useAllocation.ts`

```ts
// src/composables/import/useAllocation.ts
//
// 鎶界鑷?import/index.vue 鈥斺€?鍒嗛厤鐩爣绠＄悊锛堣绾?/ 鍒嗙粍绾?/ 鎵归噺锛夈€?// 瀵瑰簲鍘熺粍浠剁姸鎬?鍑芥暟锛歛llocationGroupsByType, currentAllocationGroups,
//   batchSetAllocation, applyAllocationGroupSetting, onRowAllocationChange,
//   newLedgerAllocation, showAllocationGroupPanel, toggleAllocationPanel銆?//
// 渚濊禆娉ㄥ叆锛歱reviewData锛堟潵鑷?usePreviewData锛?//
import { ref, computed, type Ref } from "vue";
import type { PreviewRow, AllocationGroup } from "./types";

export function useAllocation(previewData: Ref<PreviewRow[]>) {
  const showAllocationGroupPanel = ref(false);
  const newLedgerAllocation = ref("longterm");
  const toggleAllocationPanel = () => (showAllocationGroupPanel.value = !showAllocationGroupPanel.value);

  /** 鎸夎祫浜х被鍨嬭仛鍚堜负鍒嗛厤鍒嗙粍锛屾瘡缁勫甫褰撳墠鍒嗛厤鐩爣 */
  const allocationGroupsByType = computed<AllocationGroup[]>(() => {
    const map = new Map<string, AllocationGroup>();
    for (const r of previewData.value) {
      const type = r.type || "unknown";
      if (!map.has(type)) {
        map.set(type, {
          type,
          label: type,
          rows: [],
          allocation: r.allocation || newLedgerAllocation.value,
        });
      }
      map.get(type)!.rows.push(r);
    }
    return [...map.values()];
  });

  const currentAllocationGroups = computed(() => allocationGroupsByType.value);

  /** 琛岀骇鏀瑰垎閰?*/
  const onRowAllocationChange = (row: PreviewRow, allocation: string) => {
    row.allocation = allocation;
    row._allocationManual = true;
  };

  /** 鎵归噺缁欐煇鍒嗙粍璁惧垎閰嶇洰鏍?*/
  const batchSetAllocation = (target: string) => {
    for (const r of previewData.value) r.allocation = target;
  };

  /** 缁欏崟鍒嗙粍璁惧垎閰嶇洰鏍囷紙鍘?applyAllocationGroupSetting锛?*/
  const applyAllocationGroupSetting = (group: AllocationGroup, allocation: string) => {
    group.allocation = allocation;
    for (const r of group.rows) {
      r.allocation = allocation;
      r._allocationManual = true;
    }
  };

  return {
    showAllocationGroupPanel,
    toggleAllocationPanel,
    allocationGroupsByType,
    currentAllocationGroups,
    onRowAllocationChange,
    batchSetAllocation,
    applyAllocationGroupSetting,
  };
}
```

## `composables/import/useBatchFix.ts`

```ts
// src/composables/import/useBatchFix.ts
//
// 鎶界鑷?import/index.vue 鈥斺€?鎵归噺淇涓夌被闂 + 鍩洪噾 NAV 鍥炲～銆?// 瀵瑰簲鍘熺粍浠剁姸鎬?鍑芥暟锛歱roblemCategories, getMissingRowsByType, batchFillCode,
//   batchFixAmount, skipCategory, fillNavForRecords, fetchAndFillFundNav,
//   hasFundRecordsForNav, fundRecordsForNav, fundRecordsCount, calculatedCount,
//   missingFundNames銆?//
// 渚濊禆娉ㄥ叆锛歱reviewData锛堟潵鑷?usePreviewData锛夈€乻electedKeys锛堟潵鑷?useRowSelection锛?//   鐢ㄤ簬璺宠繃/鎺掗櫎鏃跺悓姝ユ竻鎺夐€変腑锛?//
import { ref, computed, type Ref } from "vue";
import { calcFundNav } from "@/api/funds";
import type { PreviewRow, ProblemCategoryKey } from "./types";

export function useBatchFix(
  previewData: Ref<PreviewRow[]>,
  selectedKeys?: Ref<Set<string | number>>,
) {
  const enrichingNav = ref(false);

  // 鎵归噺淇闈㈡澘鐨勬樉闅愶紙渚涙楠? 妯℃澘鐨?ctx.toggleBatchFix / ctx.showBatchFix 浣跨敤锛?  const showBatchFix = ref(false);
  const toggleBatchFix = () => (showBatchFix.value = !showBatchFix.value);

  /** 鎸変笁绫婚棶棰樺垎绫诲綋鍓嶉瑙堣 */
  const problemCategories = computed(() => {
    const cats: Record<ProblemCategoryKey, PreviewRow[]> = {
      missingCode: [],
      missingQtyPrice: [],
      mismatch: [],
    };
    for (const r of previewData.value) {
      if (!r.symbol && !r.name) cats.missingCode.push(r);
      else if (r.quantity == null || r.price == null || r.amount == null)
        cats.missingQtyPrice.push(r);
      // TODO: mismatch 鐨勫垽瀹氳鍒欏榻愬師缁勪欢锛堝鏁伴噺*浠锋牸鈮犻噾棰濓級
      else if (Math.abs(r.quantity * r.price - (r.amount ?? 0)) > 0.01)
        cats.mismatch.push(r);
    }
    return cats;
  });

  const getMissingRowsByType = (rows: PreviewRow[], type: string) =>
    rows.filter((r) => r.type === type);

  /** 鎵归噺濉唬鐮侊細鎶?code 鍐欏埌 missingCode 琛?*/
  const batchFillCode = async (rows: PreviewRow[], code: string) => {
    for (const r of rows) {
      r.symbol = code;
      if (!r.name) r.name = code;
    }
  };

  /** 鎵归噺鐢?鏁伴噺*浠锋牸 鍙嶆帹閲戦锛堜慨 missingQtyPrice锛?*/
  const batchFixAmount = (rows: PreviewRow[]) => {
    for (const r of rows) {
      if (r.quantity != null && r.price != null) {
        r.amount = r.quantity * r.price + (r.fee || 0);
        r.is_calculated = true;
      }
    }
  };

  /** 璺宠繃鏌愮被闂琛岋紙浠庡鍏ヤ腑鎺掗櫎锛?*/
  const skipCategory = (rows: PreviewRow[]) => {
    const skip = new Set(rows.map((r) => r._rowKey));
    if (selectedKeys) {
      selectedKeys.value = new Set(
        [...selectedKeys.value].filter((k) => !skip.has(k)),
      );
    }
    // TODO: 瀵归綈鍘?skipCategory 琛屼负锛堟槸鏍囪璺宠繃杩樻槸浠?previewData 绉婚櫎锛?    for (const r of rows) r.error = r.error ?? "宸茶烦杩?;
  };

  // ---------- 鍩洪噾 NAV 鍥炲～ ----------
  const fundRecordsForNav = computed(() =>
    previewData.value.filter((r) => r.is_calculated !== true && !r.price && r.symbol),
  );
  const fundRecordsCount = computed(() => fundRecordsForNav.value.length);
  const hasFundRecordsForNav = computed(() => fundRecordsCount.value > 0);
  const missingFundNames = computed(() =>
    fundRecordsForNav.value.map((r) => r.name || r.symbol),
  );
  const calculatedCount = computed(
    () => previewData.value.filter((r) => r.is_calculated).length,
  );

  const fillNavForRecords = async (rows: PreviewRow[]) => {
    enrichingNav.value = true;
    try {
      for (const r of rows) {
        if (!r.symbol) continue;
        // TODO: 瀵归綈 calcFundNav 鐪熷疄鍏ュ弬/鍑哄弬
        const { data } = await calcFundNav({ symbol: r.symbol } as any);
        r.price = data?.nav ?? data?.price ?? r.price;
      }
    } finally {
      enrichingNav.value = false;
    }
  };

  const fetchAndFillFundNav = async () => {
    await fillNavForRecords(fundRecordsForNav.value);
  };

  return {
    enrichingNav,
    showBatchFix,
    toggleBatchFix,
    problemCategories,
    getMissingRowsByType,
    batchFillCode,
    batchFixAmount,
    skipCategory,
    fundRecordsForNav,
    fundRecordsCount,
    hasFundRecordsForNav,
    missingFundNames,
    calculatedCount,
    fillNavForRecords,
    fetchAndFillFundNav,
  };
}
```

## `composables/import/useDuplicateHandling.ts`

```ts
// src/composables/import/useDuplicateHandling.ts
//
// 鎶界鑷?import/index.vue 鈥斺€?閲嶅琛屾娴嬩笌澶勭悊銆?// 瀵瑰簲鍘熺粍浠剁姸鎬?鍑芥暟锛歞uplicateCount, duplicatesHandled, deselectAllDuplicates锛?//   浠ュ強琛屼笂鐨?is_duplicate / _duplicateHandled锛堝師 getRowClassName 鐨勯噸澶嶆牱寮忓垽瀹?//   鐣欏湪缁勪欢妯℃澘閲岋紝鏈?composable 鎻愪緵 isDuplicateRow 鍒ゅ畾锛夈€?//
// 渚濊禆娉ㄥ叆锛歱reviewData锛堟潵鑷?usePreviewData锛夈€乻electedKeys锛堟潵鑷?useRowSelection锛?//   鍙栨秷閲嶅琛岄€変腑锛?//
import { ref, computed, type Ref } from "vue";
import type { PreviewRow } from "./types";

export function useDuplicateHandling(
  previewData: Ref<PreviewRow[]>,
  selectedKeys?: Ref<Set<string | number>>,
) {
  const duplicateCount = computed(
    () => previewData.value.filter((r) => r.is_duplicate).length,
  );
  const duplicatesHandled = ref(0);

  const isDuplicateRow = (row: PreviewRow): boolean => !!row.is_duplicate;

  /** 鍙栨秷鎵€鏈夐噸澶嶈鐨勯€変腑锛堥伩鍏嶈瀵煎叆閲嶅璁板綍锛?*/
  const deselectAllDuplicates = () => {
    if (!selectedKeys) return;
    const dup = new Set(
      previewData.value.filter((r) => r.is_duplicate).map((r) => r._rowKey),
    );
    selectedKeys.value = new Set(
      [...selectedKeys.value].filter((k) => !dup.has(k)),
    );
    duplicatesHandled.value = duplicateCount.value;
  };

  return {
    duplicateCount,
    duplicatesHandled,
    isDuplicateRow,
    deselectAllDuplicates,
  };
}
```

## `composables/import/useFileParser.ts`

```ts
// src/composables/import/useFileParser.ts
//
// 鎶界鑷?import/index.vue 鈥斺€?璐熻矗鏂囦欢涓婁紶銆佹牸寮忔牎楠屻€佽В鏋愩€佹牸寮忓紩瀵笺€?// 瀵瑰簲鍘熺粍浠剁姸鎬?鍑芥暟锛歜eforeUpload, handleUpload, handleUploadClick, parsing,
//   uploadError, fileSize, isDragover, formatFileSize, formatGuides(鈫掑父閲?,
//   formatName, uploadAccept銆?//
// 鍏抽敭鏀瑰姩锛氬師 formatGuides(reactive) + beforeUpload/uploadError 鐨?6 濂?if-else
//   鏀逛负鏌ヨ〃 IMPORT_FORMAT_CONFIG锛堣 constants/importFormats.ts锛夛紝鏂板鏍煎紡鍙敼甯搁噺銆?//
// 瑙ｆ瀽缁撴灉閫氳繃 onParsed 鍥炶皟浜ゅ洖 index.vue锛岀敱 usePreviewData 缁熶竴鎸佹湁锛堥伩鍏嶆湰
//   composable 鍙嶅悜渚濊禆棰勮鏁版嵁锛夈€?//
import { ref, computed } from "vue";
import { parseFile } from "@/api/importer";
import {
  IMPORT_FORMAT_CONFIG,
  getFormatConfig,
} from "@/constants/importFormats";
import type { ImportFormat, PreviewRow } from "./types";

export interface UseFileParserOptions {
  /** 瑙ｆ瀽鎴愬姛鍥炶皟锛宺ows 涓哄悗绔繑鍥炵殑鍘熷棰勮琛岋紙鏈粡 addRowKeys锛?*/
  onParsed: (rows: PreviewRow[]) => void;
  /** 褰撳墠閫変腑鐨勫鍏ユ牸寮忥紙鏉ヨ嚜 useImportWizard.selectedFormat锛?*/
  getFormat: () => ImportFormat | "";
  /** 褰撳墠閫変腑鐨勮处鎴?id锛堟潵鑷?useImportWizard.selectedLedgerId锛?*/
  getLedgerId: () => number | null;
}

export function useFileParser(opts: UseFileParserOptions) {
  const parsing = ref(false);
  const uploading = ref(false);
  const uploadError = ref("");
  const fileSize = ref(0);
  const isDragover = ref(false);

  /** 褰撳墠鏍煎紡閰嶇疆锛堟煡琛紝鏇夸唬鍘?formatGuides reactive锛?*/
  const currentConfig = computed(() => {
    const f = opts.getFormat();
    return f ? getFormatConfig(f) : null;
  });
  const formatName = computed(() => currentConfig.value?.label ?? "");
  const uploadAccept = computed(() => currentConfig.value?.accept ?? ".csv,.xls,.xlsx,.pdf");

  /** 瀛楄妭鏍煎紡鍖栦负鍙澶у皬 */
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  };

  /** 涓婁紶鍓嶆牎楠岋細鏍煎紡 + 澶у皬銆傝繑鍥?false 闃绘涓婁紶 */
  const beforeUpload = (file: File): boolean => {
    uploadError.value = "";
    const cfg = currentConfig.value;
    if (!cfg) {
      uploadError.value = "璇峰厛閫夋嫨瀵煎叆鏍煎紡";
      return false;
    }
    // 鎵╁睍鍚嶆牎楠?    const ext = "." + (file.name.split(".").pop() ?? "").toLowerCase();
    const okExt = cfg.accept
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .includes(ext);
    if (!okExt) {
      uploadError.value = `鏂囦欢绫诲瀷涓嶆敮鎸侊紝鏈熸湜 ${cfg.accept}`;
      return false;
    }
    // 澶у皬鏍￠獙
    if (file.size > cfg.maxSize) {
      uploadError.value = `鏂囦欢杩囧ぇ锛?{formatFileSize(file.size)}锛夛紝涓婇檺 ${formatFileSize(cfg.maxSize)}銆?{cfg.troubleshooting}`;
      return false;
    }
    fileSize.value = file.size;
    return true;
  };

  /** 鐐瑰嚮涓婁紶锛堟墦寮€鏂囦欢閫夋嫨锛?*/
  const handleUploadClick = () => {
    uploadError.value = "";
  };

  /** 鐪熸鍙戣捣瑙ｆ瀽锛坋l-upload 鐨?customRequest / 鑷畾涔変笂浼狅級 */
  const handleUpload = async (options: { file: File }) => {
    const format = opts.getFormat();
    const ledgerId = opts.getLedgerId();
    if (!format) {
      uploadError.value = "璇峰厛閫夋嫨瀵煎叆鏍煎紡";
      return;
    }
    if (!ledgerId) {
      uploadError.value = "璇峰厛閫夋嫨璐︽埛";
      return;
    }
    // 澶嶅埗鍘?uploadError 鐨?format-specific 鎺掗敊鏂囨
    const cfg = getFormatConfig(format);
    uploading.value = true;
    parsing.value = true;
    try {
      // TODO: 瀵归綈 parseFile 鐪熷疄鍏ュ弬/鍑哄弬锛堝悗绔彲鑳借繑鍥?{ data: [...] }锛?      const { data } = await parseFile({ file: options.file, format, ledgerId } as any);
      const rows = (data?.data ?? data ?? []) as PreviewRow[];
      opts.onParsed(rows);
      uploadError.value = "";
    } catch (e: any) {
      uploadError.value = `${cfg.troubleshooting}\n${
        e?.response?.data?.message ?? e?.message ?? "瑙ｆ瀽澶辫触"
      }`;
    } finally {
      uploading.value = false;
      parsing.value = false;
    }
  };

  return {
    parsing,
    uploading,
    uploadError,
    fileSize,
    isDragover,
    formatName,
    uploadAccept,
    currentConfig,
    formatFileSize,
    beforeUpload,
    handleUploadClick,
    handleUpload,
  };
}
```

## `composables/import/useImportWizard.ts`

```ts
// src/composables/import/useImportWizard.ts
//
// 鎶界鑷?import/index.vue 鈥斺€?璐熻矗銆? 姝ュ鍏ュ悜瀵笺€嶇殑缂栨帓銆佽处鎴烽€夋嫨銆佸鍏ユ彁浜ゃ€?// 瀵瑰簲鍘熺粍浠剁姸鎬?鍑芥暟锛歝urrentStep, selectedMode/format, ledgers, selectedLedgerId,
//   showCreateLedgerDialog, newLedgerName, newLedgerAllocation, ledgerTouched,
//   fetchLedgers, onAccountSelected, createLedger, confirmImport, importNormalOnly,
//   resetImport, continueImport, reimport, clearImportState, goTo* 瀵艰埅銆?//
// 璺?composable 渚濊禆锛堥€氳繃 deps 娉ㄥ叆锛岀敱 index.vue 缁熶竴鎺ョ嚎锛夛細
//   previewData  鈥斺€?鏉ヨ嚜 usePreviewData
//   selectedKeys 鈥斺€?鏉ヨ嚜 useRowSelection锛堝喅瀹氭彁浜ゅ摢浜涜锛?//
import { ref, computed, type Ref } from "vue";
import { getLedgers, createLedger as createLedgerApi } from "@/api/ledger";
import { confirmImport as confirmImportApi } from "@/api/importer";
import { useRouter } from "vue-router";
import type { ImportFormat, LedgerItem, PreviewRow } from "./types";

export interface UseImportWizardDeps {
  previewData: Ref<PreviewRow[]>;
  selectedKeys: Ref<Set<string | number>>;
}

export function useImportWizard(deps: UseImportWizardDeps) {
  const { previewData, selectedKeys } = deps;
  const router = useRouter();

  // ---------- 姝ラ鐘舵€?----------
  const currentStep = ref(0); // 0 璐︽埛 / 1 涓婁紶 / 2 棰勮淇 / 3 缁撴灉
  const importing = ref(false);
  const goToStep = (n: number) => (currentStep.value = n);

  // ---------- 鏍煎紡锛堝鍏ュ摢绉嶄氦鍓插崟锛?----------
  const selectedFormat = ref<ImportFormat | "">("");
  const isStandardMode = computed(() => selectedFormat.value === "standard_stock");

  // ---------- 璐︽埛锛坙edger锛?----------
  const ledgers = ref<LedgerItem[]>([]);
  const selectedLedgerId = ref<number | null>(null);
  const showCreateLedgerDialog = ref(false);
  const newLedgerName = ref("");
  const newLedgerAllocation = ref("longterm");
  const ledgerTouched = ref(false);

  const fetchLedgers = async () => {
    // TODO: 瀵归綈 getLedgers 鐪熷疄杩斿洖缁撴瀯锛坙ist/data?锛?    const { data } = await getLedgers();
    ledgers.value = (data?.data ?? data ?? []) as LedgerItem[];
  };

  const selectedLedger = computed(() =>
    ledgers.value.find((l) => l.id === selectedLedgerId.value) ?? null,
  );
  const selectedLedgerName = computed(() => selectedLedger.value?.name ?? "");
  const ledgerType = computed(() => selectedLedger.value?.ledger_type ?? "");
  const ledgerTypeLabel = computed(() => {
    const map: Record<string, string> = {
      bank: "閾惰璐︽埛",
      stock: "璇佸埜璐︽埛",
      fund: "鍩洪噾骞冲彴",
      property: "瀹炵墿璧勪骇",
    };
    return map[ledgerType.value] ?? ledgerType.value;
  });

  /** 鎸?ledger_type 鍒嗙粍锛屼緵姝ラ0灞曠ず */
  const ledgerGroups = computed(() => {
    const groups: Record<string, LedgerItem[]> = {};
    for (const l of ledgers.value) {
      (groups[l.ledger_type] ??= []).push(l);
    }
    return groups;
  });

  const onAccountSelected = (ledgerId: number) => {
    selectedLedgerId.value = ledgerId;
    ledgerTouched.value = true;
  };

  const getTemplateKeyForLedger = (ledger: LedgerItem | null): string => {
    if (!ledger) return "default";
    return `${ledger.ledger_type}_${selectedFormat.value || "unknown"}`;
  };

  const createLedger = async () => {
    // TODO: 瀵归綈 createLedgerApi 鍏ュ弬
    await createLedgerApi({
      name: newLedgerName.value,
      ledger_type: ledgerType.value,
      allocation: newLedgerAllocation.value,
    } as any);
    showCreateLedgerDialog.value = false;
    newLedgerName.value = "";
    await fetchLedgers();
  };

  // ---------- 鎻愪氦 ----------
  const confirmImport = async () => {
    importing.value = true;
    try {
      const payload = {
        ledger_id: selectedLedgerId.value,
        format: selectedFormat.value,
        // 鍙彁浜よ閫変腑鐨勮
        rows: previewData.value.filter((r) => selectedKeys.value.has(r._rowKey)),
      };
      // TODO: 瀵归綈 confirmImportApi 鐪熷疄鍏ュ弬涓庤繑鍥烇紙success/skip/orphan/error 姹囨€伙級
      const { data } = await confirmImportApi(payload as any);
      // 灏嗙粨鏋滃啓鍏ユ楠?锛堢敱 useImportWizard 鎸佹湁鎴栫敱 index.vue 涓浆锛?      importResult.value = normalizeResult(data);
      currentStep.value = 3;
    } finally {
      importing.value = false;
    }
  };

  /** 浠呭鍏ャ€屾甯搞€嶈锛堥敊璇璺宠繃锛?*/
  const importNormalOnly = async () => {
    // 鍏堝墧闄?error 琛屽啀鎻愪氦
    const backup = selectedKeys.value;
    selectedKeys.value = new Set(
      previewData.value
        .filter((r) => !r.error && !r.is_duplicate)
        .map((r) => r._rowKey),
    );
    await confirmImport();
    selectedKeys.value = backup;
  };

  // 姝ラ3 缁撴灉锛堜篃鍙斁鍒扮嫭绔?composable锛岃繖閲屾寔鏈変互渚?confirmImport 鐩存帴鍐欙級
  const importResult = ref<any>(null);

  const resetImport = () => {
    clearImportState();
    currentStep.value = 0;
    selectedFormat.value = "";
    selectedLedgerId.value = null;
  };
  const continueImport = () => (currentStep.value = Math.min(currentStep.value + 1, 3));
  const reimport = () => {
    clearImportState();
    currentStep.value = 1;
  };

  const clearImportState = () => {
    previewData.value = [];
    selectedKeys.value.clear();
    importResult.value = null;
    importing.value = false;
  };

  // ---------- 瀵艰埅锛堟楠? 缁撴灉椤佃烦杞級 ----------
  const goToTransactions = () => router.push("/asset/transactions");
  const goToManualEntry = () => router.push("/asset/investment/manual");
  const goToLiabilityForm = () => router.push("/asset/asset-entry");
  const goToImportGuide = () => router.push("/asset/investment/import");

  return {
    // 姝ラ
    currentStep,
    goToStep,
    importing,
    // 鏍煎紡
    selectedFormat,
    isStandardMode,
    // 璐︽埛
    ledgers,
    selectedLedgerId,
    selectedLedgerName,
    ledgerType,
    ledgerTypeLabel,
    ledgerGroups,
    showCreateLedgerDialog,
    newLedgerName,
    newLedgerAllocation,
    ledgerTouched,
    fetchLedgers,
    onAccountSelected,
    getTemplateKeyForLedger,
    createLedger,
    // 鎻愪氦
    confirmImport,
    importNormalOnly,
    importResult,
    resetImport,
    continueImport,
    reimport,
    clearImportState,
    // 瀵艰埅
    goToTransactions,
    goToManualEntry,
    goToLiabilityForm,
    goToImportGuide,
  };
}

/** 鎶婂悗绔繑鍥炲綊涓€鍖栦负姝ラ3 灞曠ず缁撴瀯 */
function normalizeResult(data: any) {
  return {
    importedCount: data?.imported ?? data?.success ?? 0,
    skippedCount: data?.skipped ?? 0,
    orphanCount: data?.orphan ?? 0,
    errorCount: data?.error ?? 0,
    importErrors: data?.errors ?? [],
    nothingImported: (data?.imported ?? 0) === 0,
    showPriceUpdateTip: !!data?.price_updated,
  };
}
```

## `composables/import/usePreviewData.ts`

```ts
// src/composables/import/usePreviewData.ts
//
// 鎶界鑷?import/index.vue 鈥斺€?棰勮鏁版嵁鐨勬寔鏈夈€佽閿敞鍏ャ€佺瓫閫変笌鍒嗛〉銆?// 瀵瑰簲鍘熺粍浠剁姸鎬?鍑芥暟锛歱reviewData, addRowKeys, filteredPagedData, filteredTotal,
//   currentPage, pageSize, totalRows, handleSizeChange, handlePageChange,
//   tableFilterKeyword, tableTypeFilter, tableStatusFilter, showProblemOnly,
//   activeCategoryFilter, filterByCategory銆?//
// 鈿?淇鍘?DRY 闂锛氬師 filteredPagedData 涓?filteredTotal 涓や釜 computed 鍑犱箮瀹屽叏
//   閲嶅銆傝繖閲屾敼涓哄崟涓€ filteredRows computed锛屽垎椤?鎬绘暟閮戒粠瀹冩淳鐢熴€?//
import { ref, computed, type Ref } from "vue";
import type { PreviewRow } from "./types";

let rowKeySeq = 0;

export function usePreviewData() {
  const previewData = ref<PreviewRow[]>([]);
  const currentPage = ref(1);
  const pageSize = ref(20);
  const totalRows = ref(0);

  // 绛涢€夋潯浠?  const tableFilterKeyword = ref("");
  const tableTypeFilter = ref("");
  const tableStatusFilter = ref("");
  const showProblemOnly = ref(false);
  const activeCategoryFilter = ref("");

  /** 娉ㄥ叆鍞竴琛岄敭锛堝師 addRowKeys锛?*/
  const addRowKeys = (data: PreviewRow[]) => {
    previewData.value = data.map((r) => ({
      ...r,
      _rowKey: r._rowKey ?? `${rowKeySeq++}`,
    }));
    totalRows.value = previewData.value.length;
    currentPage.value = 1;
  };

  /** 鍗曚竴绛涢€夋簮锛氭墍鏈夌瓫閫夋潯浠跺湪姝ゅ悎骞朵竴娆?*/
  const filteredRows = computed<PreviewRow[]>(() => {
    let rows = previewData.value;
    if (tableFilterKeyword.value) {
      const kw = tableFilterKeyword.value.toLowerCase();
      rows = rows.filter(
        (r) =>
          r.symbol?.toLowerCase().includes(kw) ||
          r.name?.toLowerCase().includes(kw),
      );
    }
    if (tableTypeFilter.value) {
      rows = rows.filter((r) => r.type === tableTypeFilter.value);
    }
    if (tableStatusFilter.value) {
      rows = rows.filter((r) => (r.error ? "error" : "ok") === tableStatusFilter.value);
    }
    if (showProblemOnly.value) {
      rows = rows.filter((r) => !!r.error);
    }
    if (activeCategoryFilter.value) {
      rows = rows.filter((r) => r.type === activeCategoryFilter.value);
    }
    return rows;
  });

  /** 鍒嗛〉鍚庣殑鏁版嵁锛堟淳鐢熻嚜 filteredRows锛屼笉鍐嶉噸澶嶅疄鐜扮瓫閫夛級 */
  const filteredPagedData = computed<PreviewRow[]>(() => {
    const start = (currentPage.value - 1) * pageSize.value;
    return filteredRows.value.slice(start, start + pageSize.value);
  });

  /** 绛涢€夊悗鎬绘暟锛堟淳鐢熻嚜 filteredRows锛屼慨澶嶅師 DRY 閲嶅锛?*/
  const filteredTotal = computed(() => filteredRows.value.length);

  const handleSizeChange = (val: number) => {
    pageSize.value = val;
    currentPage.value = 1;
  };
  const handlePageChange = (val: number) => {
    currentPage.value = val;
  };
  const filterByCategory = (key: string) => {
    activeCategoryFilter.value = activeCategoryFilter.value === key ? "" : key;
    currentPage.value = 1;
  };

  return {
    previewData,
    currentPage,
    pageSize,
    totalRows,
    tableFilterKeyword,
    tableTypeFilter,
    tableStatusFilter,
    showProblemOnly,
    activeCategoryFilter,
    addRowKeys,
    filteredRows,
    filteredPagedData,
    filteredTotal,
    handleSizeChange,
    handlePageChange,
    filterByCategory,
  };
}
```

## `composables/import/useRowEditing.ts`

```ts
// src/composables/import/useRowEditing.ts
//
// 鎶界鑷?import/index.vue 鈥斺€?棰勮琛ㄥ唴鑱旂紪杈戯紙popover 缂栬緫鏁伴噺/浠锋牸锛夈€?// 瀵瑰簲鍘熺粍浠剁姸鎬?鍑芥暟锛歟ditingRowKey, startEdit, finishEdit, cancelEdit, smartFill,
//   saveAllEditingRows, closeAllEditing锛屼互鍙婅涓婄殑 isEditingQty/isEditingPrice/
//   _oldValue/smartFilled/is_calculated/_dataMissing銆?//
// 渚濊禆娉ㄥ叆锛歱reviewData锛堟潵鑷?usePreviewData锛?//
import { ref, type Ref } from "vue";
import type { PreviewRow } from "./types";

export function useRowEditing(previewData: Ref<PreviewRow[]>) {
  const editingRowKey = ref<string | number | null>(null);

  const findRow = (key: string | number) =>
    previewData.value.find((r) => r._rowKey === key);

  /** 杩涘叆鏌愯鏌愬瓧娈电殑缂栬緫鎬侊紝缂撳瓨鏃у€?*/
  const startEdit = (row: PreviewRow, field: "quantity" | "price") => {
    row._oldValue = row[field];
    if (field === "quantity") row.isEditingQty = true;
    else row.isEditingPrice = true;
    editingRowKey.value = row._rowKey;
  };

  /** 瀹屾垚缂栬緫锛歴ave=true 鍐欏洖锛宖alse 杩樺師 */
  const finishEdit = (row: PreviewRow, field: "quantity" | "price", save = true) => {
    if (!save) {
      row[field] = row._oldValue ?? row[field];
    }
    // 鏍囪宸茬紪杈戯紙闈炴櫤鑳藉～鍏咃級
    if (field === "quantity") row.isEditingQty = false;
    else row.isEditingPrice = false;
    if (editingRowKey.value === row._rowKey) editingRowKey.value = null;
  };

  const cancelEdit = (row: PreviewRow, field: "quantity" | "price") => {
    finishEdit(row, field, false);
  };

  /**
   * 鏅鸿兘濉厖锛氱敱 amount/quantity 鍙嶆帹 price锛堟垨鍙嶄箣锛夈€?   * 鍘?smartFill 鐨勯€昏緫锛氬凡鐭ヤ袱椤瑰彲绠楃涓夐」銆傝繖閲岀粰鍑洪€氱敤瀹炵幇锛?   * 瀹為檯鍏紡浠ヤ綘鐨勪笟鍔￠€昏緫涓哄噯锛堥噾棰?鏁伴噺*浠锋牸卤璐癸級銆?   */
  const smartFill = (row: PreviewRow, field: "quantity" | "price" | "amount") => {
    const { quantity, price, amount, fee } = row;
    if (field === "price" && quantity && amount != null) {
      row.price = quantity ? (amount - (fee || 0)) / quantity : 0;
    } else if (field === "quantity" && price && amount != null) {
      row.quantity = price ? (amount - (fee || 0)) / price : 0;
    } else if (field === "amount" && quantity && price) {
      row.amount = quantity * price + (fee || 0);
    }
    row.is_calculated = true;
    row.smartFilled = true;
    row._dataMissing = false;
  };

  /** 淇濆瓨鎵€鏈夊浜庣紪杈戞€佺殑琛岋紙鎵归噺纭锛?*/
  const saveAllEditingRows = () => {
    for (const row of previewData.value) {
      if (row.isEditingQty) finishEdit(row, "quantity", true);
      if (row.isEditingPrice) finishEdit(row, "price", true);
    }
    editingRowKey.value = null;
  };

  const closeAllEditing = () => {
    for (const row of previewData.value) {
      row.isEditingQty = false;
      row.isEditingPrice = false;
    }
    editingRowKey.value = null;
  };

  return {
    editingRowKey,
    startEdit,
    finishEdit,
    cancelEdit,
    smartFill,
    saveAllEditingRows,
    closeAllEditing,
  };
}
```

## `composables/import/useRowSelection.ts`

```ts
// src/composables/import/useRowSelection.ts
//
// 鎶界鑷?import/index.vue 鈥斺€?琛岄€夋嫨鐘舵€佹満锛堝叏閫?鍗婇€?鎺掗櫎闃绘柇琛屼笌閲嶅琛岋級銆?// 瀵瑰簲鍘熺粍浠剁姸鎬?鍑芥暟锛歴electedKeys, isAllSelected, isIndeterminate, isRowSelected,
//   isRowBlocked, handleRowCheckboxChange, handleHeaderCheckboxChange, selectAllValid,
//   clearAllSelection, updateSelectAllState, recalcValidRowsCount, selectedCount,
//   blockedCount, validRowsCount銆?//
// 渚濊禆娉ㄥ叆锛歱reviewData锛堟潵鑷?usePreviewData锛?//
import { ref, computed, type Ref } from "vue";
import type { PreviewRow } from "./types";

export function useRowSelection(previewData: Ref<PreviewRow[]>) {
  const selectedKeys = ref<Set<string | number>>(new Set());

  /** 琚樆鏂殑琛屼笉鍙€夛紙鍘?isRowBlocked锛?*/
  const isRowBlocked = (row: PreviewRow): boolean => {
    // TODO: 瀵归綈鍘?isRowBlocked 鍒ゅ畾锛堝缂哄叧閿瓧娈点€佺被鍨嬩笉鏀寔绛夛級
    return !row.symbol && !row.name;
  };

  const isRowSelected = (row: PreviewRow): boolean =>
    selectedKeys.value.has(row._rowKey);

  /** 鏈夋晥琛?= 鏈樆鏂笖鏈噸澶?*/
  const validRows = computed(() =>
    previewData.value.filter((r) => !isRowBlocked(r) && !r.is_duplicate),
  );
  const validRowsCount = computed(() => validRows.value.length);
  const blockedCount = computed(
    () => previewData.value.filter((r) => isRowBlocked(r)).length,
  );
  const selectedCount = computed(() => selectedKeys.value.size);

  /** 鍏ㄩ€夋€侊細鏈夋晥琛屽叏閫?true锛岄儴鍒嗛€?鍗婇€夛紝鏃犻€?false */
  const isAllSelected = computed(
    () =>
      validRowsCount.value > 0 &&
      validRows.value.every((r) => selectedKeys.value.has(r._rowKey)),
  );
  const isIndeterminate = computed(
    () =>
      selectedKeys.value.size > 0 && !isAllSelected.value,
  );

  const handleRowCheckboxChange = (row: PreviewRow, checked: boolean) => {
    if (checked) selectedKeys.value.add(row._rowKey);
    else selectedKeys.value.delete(row._rowKey);
    // Set 鏄紩鐢ㄧ被鍨嬶紝trigger 鍝嶅簲寮?    selectedKeys.value = new Set(selectedKeys.value);
    updateSelectAllState();
  };

  const handleHeaderCheckboxChange = (checked: boolean) => {
    if (checked) selectAllValid();
    else clearAllSelection();
  };

  const selectAllValid = () => {
    selectedKeys.value = new Set(validRows.value.map((r) => r._rowKey));
  };

  const clearAllSelection = () => {
    selectedKeys.value = new Set();
  };

  /** 閲嶆柊璁＄畻閫変腑缁熻锛堝師 recalcValidRowsCount锛屼緵澶栭儴鎵嬪姩瑙﹀彂锛?*/
  const recalcValidRowsCount = () => {
    // 娓呴櫎宸蹭笉瀛樺湪鐨勮閿?    const live = new Set(previewData.value.map((r) => r._rowKey));
    selectedKeys.value = new Set(
      [...selectedKeys.value].filter((k) => live.has(k)),
    );
  };

  const updateSelectAllState = () => {
    // 鍗婇€?鍏ㄩ€夌敱 computed 娲剧敓锛岃繖閲屼粎闇€淇濊瘉 selectedKeys 鏄渶鏂板紩鐢?    selectedKeys.value = new Set(selectedKeys.value);
  };

  return {
    selectedKeys,
    isRowBlocked,
    isRowSelected,
    validRowsCount,
    blockedCount,
    selectedCount,
    isAllSelected,
    isIndeterminate,
    handleRowCheckboxChange,
    handleHeaderCheckboxChange,
    selectAllValid,
    clearAllSelection,
    recalcValidRowsCount,
    updateSelectAllState,
  };
}
```

## `views/investment/import/ImportWizard.vue`

```vue
<script setup lang="ts">
// 瀵煎叆鍚戝鐖跺３锛堟媶鍒嗗悗 import/index.vue 鐨勭洰鏍囧舰鎬侊紝绾?120 琛岋級
// 鑱岃矗浠呭墿锛氬疄渚嬪寲鍏ㄩ儴 composable 鈫?缁勮 ImportContext 鈫?provide 鈫?鎸夋楠ゅ垏鎹€?// 鎵€鏈変笟鍔￠€昏緫宸插湪 composables/import/* 涓紝鎵€鏈夊竷灞€宸插湪 components/* 涓€?import { provide, onMounted } from "vue";
import {
  importContextKey,
  type ImportContext,
} from "@/composables/import/context";
import {
  useImportWizard,
  usePreviewData,
  useRowSelection,
  useRowEditing,
  useBatchFix,
  useAllocation,
  useDuplicateHandling,
  useFileParser,
} from "@/composables/import";
import AccountSelectionStep from "./components/AccountSelectionStep.vue";
import FileUploadStep from "./components/FileUploadStep.vue";
import PreviewTable from "./components/PreviewTable.vue";
import ImportResult from "./components/ImportResult.vue";

// 1) 鏁版嵁搴曞骇
const preview = usePreviewData();
const selection = useRowSelection(preview.previewData);
const editing = useRowEditing(preview.previewData);
const batchFix = useBatchFix(preview.previewData, selection.selectedKeys);
const allocation = useAllocation(preview.previewData);
const dup = useDuplicateHandling(preview.previewData, selection.selectedKeys);

// 2) 鍚戝缂栨帓锛堜緷璧?previewData + selectedKeys锛?const wizard = useImportWizard({
  previewData: preview.previewData,
  selectedKeys: selection.selectedKeys,
});

// 3) 鏂囦欢瑙ｆ瀽锛堣В鏋愮粨鏋滃洖璋冩帴 addRowKeys锛?const fileParser = useFileParser({
  getFormat: () => wizard.selectedFormat.value,
  getLedgerId: () => wizard.selectedLedgerId.value,
  onParsed: (rows) => preview.addRowKeys(rows),
});

// 4) 缁勮涓婁笅鏂囧苟 provide锛堟楠ょ粍浠堕€氳繃 inject 鍙栫敤锛岀姸鎬佸叏杩為€氾級
const ctx: ImportContext = {
  ...wizard,
  ...preview,
  ...selection,
  ...editing,
  ...batchFix,
  ...allocation,
  ...dup,
  ...fileParser,
};
provide(importContextKey, ctx);

onMounted(() => wizard.fetchLedgers());
</script>

<template>
  <div class="import-wizard p-4">
    <el-steps :active="wizard.currentStep.value" align-center class="mb-6">
      <el-step title="閫夋嫨璐︽埛" />
      <el-step title="涓婁紶瀵硅处鍗? />
      <el-step title="棰勮淇" />
      <el-step title="瀵煎叆缁撴灉" />
    </el-steps>

    <AccountSelectionStep
      v-if="wizard.currentStep.value === 0"
      @next="wizard.continueImport"
    />
    <FileUploadStep
      v-else-if="wizard.currentStep.value === 1"
      @next="wizard.continueImport"
      @prev="wizard.currentStep.value = 0"
    />
    <PreviewTable
      v-else-if="wizard.currentStep.value === 2"
      @next="wizard.continueImport"
      @prev="wizard.currentStep.value = 1"
    />
    <ImportResult
      v-else
      @prev="wizard.currentStep.value = 2"
    />
  </div>
</template>
```

## `views/investment/import/components/AccountSelectionStep.vue`

```vue
<script setup lang="ts">
// 姝ラ0锛氳处鎴烽€夋嫨 + 鏂板缓璐︽埛
// 瀵瑰簲鍘?import/index.vue 姝ラ0 妯℃澘 + onAccountSelected/createLedger 绛夈€?// 閫氳繃 inject(importContextKey) 鍙栫敤鐖跺３娉ㄥ叆鐨勫叡浜姸鎬併€?import { inject } from "vue";
import { importContextKey } from "@/composables/import/context";
import CreateLedgerDialog from "./CreateLedgerDialog.vue";

const ctx = inject(importContextKey)!;
const emit = defineEmits<{ next: [] }>();
</script>

<template>
  <div class="account-selection-step">
    <h3 class="mb-4 text-base font-medium">閫夋嫨瀵煎叆璐︽埛</h3>

    <!-- 鎸?ledger_type 鍒嗙粍鐨勮处鎴烽€夋嫨 -->
    <div class="ledger-groups flex flex-col gap-4">
      <div v-for="(items, type) in ctx.ledgerGroups.value" :key="type" class="ledger-group">
        <div class="mb-2 text-sm text-gray-500">{{ type }}</div>
        <el-radio-group :model-value="ctx.selectedLedgerId.value" @change="ctx.onAccountSelected">
          <el-radio-button v-for="l in items" :key="l.id" :value="l.id">
            {{ l.name }}
          </el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- 鏃犺处鎴锋椂寮曞鏂板缓 -->
    <div v-if="!ctx.ledgerGroups.value || Object.keys(ctx.ledgerGroups.value).length === 0"
         class="mt-4">
      <el-button type="primary" @click="ctx.showCreateLedgerDialog.value = true">
        鏂板缓璐︽埛
      </el-button>
    </div>

    <CreateLedgerDialog v-model="ctx.showCreateLedgerDialog.value" />

    <div class="mt-6 flex justify-end">
      <el-button type="primary" :disabled="!ctx.selectedLedgerId.value"
                 @click="emit('next')">
        涓嬩竴姝?      </el-button>
    </div>
  </div>
</template>
```

## `views/investment/import/components/AllocationPanel.vue`

```vue
<script setup lang="ts">
// 姝ラ2 渚ф爮锛氬垎閰嶇洰鏍囩鐞嗛潰鏉?// 瀵瑰簲鍘?import/index.vue 鐨?allocation-group-panel + batchSetAllocation/applyAllocationGroupSetting銆?import { inject } from "vue";
import { importContextKey } from "@/composables/import/context";

const ctx = inject(importContextKey)!;

const allocationOptions = [
  { label: "娲婚挶", value: "liquid" },
  { label: "绋冲仴搴曚粨", value: "stable" },
  { label: "闀挎湡澧炲€?, value: "longterm" },
  { label: "楂橀闄╁崥寮?, value: "speculative" },
  { label: "淇濋櫓淇濋殰", value: "security" },
];
</script>

<template>
  <div class="allocation-panel">
    <h4 class="font-medium mb-2">鍒嗛厤鐩爣</h4>

    <!-- 鎵归噺璁剧疆 -->
    <div class="mb-3">
      <div class="text-sm mb-1">鍏ㄩ儴璁句负</div>
      <el-select :model-value="''" placeholder="閫夋嫨鍒嗛厤鐩爣" size="small"
                 @change="ctx.batchSetAllocation($event)">
        <el-option v-for="o in allocationOptions" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
    </div>

    <el-divider />

    <!-- 鎸夊垎缁勮缃?-->
    <div v-for="g in ctx.allocationGroupsByType.value" :key="g.type" class="group-block mb-3">
      <div class="text-sm mb-1">{{ g.label }}锛坽{ g.rows.length }}锛?/div>
      <el-select :model-value="g.allocation" size="small"
                 @change="(v: string) => ctx.applyAllocationGroupSetting(g, v)">
        <el-option v-for="o in allocationOptions" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
    </div>
  </div>
</template>
```

## `views/investment/import/components/BatchFixPanel.vue`

```vue
<script setup lang="ts">
// 姝ラ2 渚ф爮锛氫笁绫婚棶棰樻壒閲忎慨澶嶉潰鏉?// 瀵瑰簲鍘?import/index.vue 鐨?batchFixPanel + batchFillCode/batchFixAmount/skipCategory/fillNavForRecords銆?import { inject, ref } from "vue";
import { importContextKey } from "@/composables/import/context";

const ctx = inject(importContextKey)!;
const batchCodeInput = ref("");

const runFillCode = () => {
  ctx.batchFillCode(ctx.problemCategories.value.missingCode, batchCodeInput.value);
  batchCodeInput.value = "";
};
const runFixAmount = () => ctx.batchFixAmount(ctx.problemCategories.value.missingQtyPrice);
const runSkip = () => ctx.skipCategory([
  ...ctx.problemCategories.value.missingCode,
  ...ctx.problemCategories.value.missingQtyPrice,
  ...ctx.problemCategories.value.mismatch,
]);
</script>

<template>
  <div class="batch-fix-panel">
    <h4 class="font-medium mb-2">鎵归噺淇</h4>

    <div class="problem-block mb-3">
      <div class="text-sm">缂哄け浠ｇ爜 ({{ ctx.problemCategories.value.missingCode.length }})</div>
      <el-input v-model="batchCodeInput" size="small" placeholder="濉叆鍩洪噾浠ｇ爜" class="mt-1" />
      <el-button size="small" class="mt-1" @click="runFillCode">鎵归噺濉唬鐮?/el-button>
    </div>

    <div class="problem-block mb-3">
      <div class="text-sm">缂哄け鏁伴噺/浠锋牸 ({{ ctx.problemCategories.value.missingQtyPrice.length }})</div>
      <el-button size="small" class="mt-1" @click="runFixAmount">鎸?鏁伴噺脳浠锋牸 琛ラ噾棰?/el-button>
    </div>

    <div class="problem-block mb-3">
      <div class="text-sm">鏁版嵁涓嶄竴鑷?({{ ctx.problemCategories.value.mismatch.length }})</div>
    </div>

    <el-divider />

    <div v-if="ctx.hasFundRecordsForNav.value" class="mb-2 text-sm text-gray-500">
      闇€鍥炲～ {{ ctx.fundRecordsCount.value }} 鏉″熀閲戝噣鍊?    </div>
    <el-button size="small" :loading="ctx.enrichingNav.value"
               :disabled="!ctx.hasFundRecordsForNav.value"
               @click="ctx.fetchAndFillFundNav()">
      鑷姩鍥炲～鍑€鍊?    </el-button>

    <el-button size="small" class="mt-2" @click="runSkip">璺宠繃浠ヤ笂闂琛?/el-button>
  </div>
</template>
```

## `views/investment/import/components/CreateLedgerDialog.vue`

```vue
<script setup lang="ts">
// 鏂板缓璐︽埛瀵硅瘽妗嗭紙姝ラ0 瀛愮粍浠讹級
// 瀵瑰簲鍘?import/index.vue 鐨?el-dialog + createLedger銆?import { computed, inject } from "vue";
import { importContextKey } from "@/composables/import/context";

const ctx = inject(importContextKey)!;

// v-model 鍙屽悜缁戝畾瀵硅瘽妗嗗彲瑙佹€?const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ "update:modelValue": [boolean] }>();
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});
</script>

<template>
  <el-dialog v-model="visible" title="鏂板缓璐︽埛" width="420px">
    <el-form label-width="80px">
      <el-form-item label="璐︽埛鍚?>
        <el-input v-model="ctx.newLedgerName.value" placeholder="濡傦細鎷涘晢璇佸埜" />
      </el-form-item>
      <el-form-item label="璐︽埛绫诲瀷">
        <el-select :model-value="ctx.ledgerType.value" disabled>
          <el-option :label="ctx.ledgerTypeLabel.value" :value="ctx.ledgerType.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="鍒嗛厤鐩爣">
        <el-select v-model="ctx.newLedgerAllocation.value">
          <el-option label="娲婚挶" value="liquid" />
          <el-option label="绋冲仴搴曚粨" value="stable" />
          <el-option label="闀挎湡澧炲€? value="longterm" />
          <el-option label="楂橀闄╁崥寮? value="speculative" />
          <el-option label="淇濋櫓淇濋殰" value="security" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">鍙栨秷</el-button>
      <el-button type="primary" :disabled="!ctx.newLedgerName.value"
                 @click="ctx.createLedger()">
        鍒涘缓
      </el-button>
    </template>
  </el-dialog>
</template>
```

## `views/investment/import/components/FileUploadStep.vue`

```vue
<script setup lang="ts">
// 姝ラ1锛氭枃浠朵笂浼?+ 鏍煎紡閫夋嫨 + 妯℃澘涓嬭浇
// 瀵瑰簲鍘?import/index.vue 姝ラ1 妯℃澘 + beforeUpload/handleUpload/handleDownloadTemplate銆?import { inject, computed } from "vue";
import { importContextKey } from "@/composables/import/context";
import { IMPORT_FORMAT_CONFIG, IMPORT_FORMAT_KEYS } from "@/constants/importFormats";
import type { ImportFormat } from "@/composables/import/types";

const ctx = inject(importContextKey)!;
const emit = defineEmits<{ next: []; prev: [] }>();

const formats = IMPORT_FORMAT_CONFIG;
const formatList = IMPORT_FORMAT_KEYS;

// 妯℃澘涓嬭浇锛氭寜褰撳墠鏍煎紡鍙栨ā鏉垮悕锛堝疄闄呬笅杞藉湴鍧€/鎺ュ彛闇€瀵归綈锛?const handleDownloadTemplate = () => {
  const f = ctx.selectedFormat.value as ImportFormat;
  if (!f) return;
  // TODO: 瀵归綈妯℃澘涓嬭浇瀹炵幇锛堥潤鎬佽祫婧愭垨鍚庣鎺ュ彛锛夈€傝繖閲屼粎鎵撳嵃妯℃澘鍚嶅崰浣嶃€?  const name = formats[f].templateName;
  // 渚嬶細window.open(`/templates/${name}`) 鎴栬皟鐢ㄤ笅杞?API
  console.info("[妯℃澘涓嬭浇] 鏈熸湜妯℃澘锛?, name);
};

const canNext = computed(() => ctx.previewData.value.length > 0);
</script>

<template>
  <div class="file-upload-step">
    <h3 class="mb-4 text-base font-medium">閫夋嫨鏍煎紡骞朵笂浼犲璐﹀崟</h3>

    <!-- 鏍煎紡閫夋嫨锛堝崱鐗?鍗曢€夛級 -->
    <div class="format-list flex flex-wrap gap-3 mb-4">
      <div v-for="key in formatList" :key="key"
           class="format-card border rounded-lg p-3 cursor-pointer"
           :class="{ 'border-brand': ctx.selectedFormat.value === key }"
           @click="ctx.selectedFormat.value = key">
        <div class="font-medium">{{ formats[key].label }}</div>
        <div class="text-xs text-gray-400 mt-1">{{ formats[key].guide }}</div>
      </div>
    </div>

    <!-- 涓婁紶鍖?-->
    <el-upload
      drag
      :accept="ctx.uploadAccept.value"
      :before-upload="ctx.beforeUpload"
      :http-request="ctx.handleUpload"
      :show-file-list="false"
    >
      <i class="el-icon--upload"><el-icon><UploadFilled /></el-icon></i>
      <div class="el-upload__text">灏嗘枃浠舵嫋鍒版澶勶紝鎴?em>鐐瑰嚮涓婁紶</em></div>
      <template #tip>
        <div class="text-xs text-gray-400 mt-1">
          鏀寔 {{ ctx.uploadAccept.value }}锛屽綋鍓嶆牸寮忥細{{ ctx.formatName.value }}
        </div>
      </template>
    </el-upload>

    <!-- 瑙ｆ瀽涓?/ 閿欒 / 澶у皬 -->
    <div v-if="ctx.parsing.value" class="mt-2 text-sm text-gray-500">
      <el-icon class="is-loading"><Loading /></el-icon> 瑙ｆ瀽涓€?    </div>
    <div v-if="ctx.uploadError.value" class="mt-2 text-sm text-red-500 whitespace-pre-line">
      {{ ctx.uploadError.value }}
    </div>
    <div v-if="ctx.fileSize.value" class="mt-1 text-xs text-gray-400">
      鏂囦欢澶у皬锛歿{ (ctx.fileSize.value / 1024).toFixed(1) }} KB
    </div>

    <!-- 妯℃澘涓嬭浇 -->
    <div class="mt-3">
      <el-button link type="primary" :disabled="!ctx.selectedFormat.value"
                 @click="handleDownloadTemplate">
        涓嬭浇 {{ ctx.formatName.value }} 妯℃澘
      </el-button>
    </div>

    <div class="mt-6 flex justify-between">
      <el-button @click="emit('prev')">涓婁竴姝?/el-button>
      <el-button type="primary" :disabled="!canNext" @click="emit('next')">
        涓嬩竴姝ワ紙鍏?{{ ctx.previewData.value.length }} 鏉★級
      </el-button>
    </div>
  </div>
</template>
```

## `views/investment/import/components/ImportResult.vue`

```vue
<script setup lang="ts">
// 姝ラ3锛氬鍏ョ粨鏋滄眹鎬?// 瀵瑰簲鍘?import/index.vue 姝ラ3 妯℃澘 + errorSummary/nothingImported/showPriceUpdateTip銆?import { inject, computed } from "vue";
import { importContextKey } from "@/composables/import/context";

const ctx = inject(importContextKey)!;

// importResult 鐢?useImportWizard.confirmImport 鍐欏叆
const result = computed(() => ctx.importResult.value ?? null);
const counts = computed(() => ({
  imported: result.value?.importedCount ?? 0,
  skipped: result.value?.skippedCount ?? 0,
  orphan: result.value?.orphanCount ?? 0,
  error: result.value?.errorCount ?? 0,
}));
const errors = computed<any[]>(() => result.value?.importErrors ?? []);
const nothingImported = computed(() => !!result.value?.nothingImported);
const showPriceTip = computed(() => !!result.value?.showPriceUpdateTip);

const emit = defineEmits<{ prev: [] }>();
</script>

<template>
  <div class="import-result-step">
    <el-result v-if="nothingImported" icon="warning" title="娌℃湁浠讳綍璁板綍琚鍏?
               sub-title="璇锋鏌ョ瓫閫?閫夋嫨鎴栬繑鍥炰笂涓€姝ラ噸鏂拌В鏋? />

    <template v-else>
      <h3 class="mb-4 text-base font-medium">瀵煎叆瀹屾垚</h3>
      <div class="grid grid-cols-4 gap-3 mb-4">
        <el-card shadow="never"><template #header><span class="text-green-600">鎴愬姛</span></template>
          <div class="text-2xl font-bold">{{ counts.imported }}</div></el-card>
        <el-card shadow="never"><template #header>璺宠繃</template>
          <div class="text-2xl font-bold">{{ counts.skipped }}</div></el-card>
        <el-card shadow="never"><template #header>瀛ゅ効</template>
          <div class="text-2xl font-bold">{{ counts.orphan }}</div></el-card>
        <el-card shadow="never"><template #header><span class="text-red-500">澶辫触</span></template>
          <div class="text-2xl font-bold">{{ counts.error }}</div></el-card>
      </div>

      <el-alert v-if="showPriceTip" type="info" :closable="false" class="mb-3"
                title="閮ㄥ垎璁板綍鐨勪环鏍煎凡鎸夋渶鏂板噣鍊兼洿鏂? />

      <el-collapse v-if="errors.length" class="mb-3">
        <el-collapse-item title="澶辫触鏄庣粏" name="err">
          <ul class="text-sm text-red-500">
            <li v-for="(e, i) in errors" :key="i">{{ e.message }}</li>
          </ul>
        </el-collapse-item>
      </el-collapse>
    </template>

    <div class="mt-6 flex justify-between">
      <el-button @click="emit('prev')">涓婁竴姝?/el-button>
      <div class="flex gap-2">
        <el-button @click="ctx.goToTransactions()">鏌ョ湅浜ゆ槗娴佹按</el-button>
        <el-button @click="ctx.goToManualEntry()">鍘绘墜鍔ㄨ璐?/el-button>
        <el-button type="primary" @click="ctx.reimport()">鍐嶅鍏ヤ竴绗?/el-button>
      </div>
    </div>
  </div>
</template>
```

## `views/investment/import/components/PreviewTable.vue`

```vue
<script setup lang="ts">
// 姝ラ2锛氶瑙堣〃鏍硷紙鍒嗛〉/绛涢€?鎺掑簭 + 鍐呰仈缂栬緫 + 鎵归噺淇 + 鍒嗛厤 + 閲嶅澶勭悊锛?// 瀵瑰簲鍘?import/index.vue 姝ラ2 妯℃澘銆傝鎶借蛋鐨勯€昏緫宸插湪 composables/import/* 涓€?import { inject } from "vue";
import { importContextKey } from "@/composables/import/context";
import SummaryCards from "./SummaryCards.vue";
import BatchFixPanel from "./BatchFixPanel.vue";
import AllocationPanel from "./AllocationPanel.vue";

const ctx = inject(importContextKey)!;
const emit = defineEmits<{ next: []; prev: [] }>();
</script>

<template>
  <div class="preview-table-step">
    <SummaryCards />

    <div class="toolbar flex items-center gap-3 mb-3">
      <el-input v-model="ctx.tableFilterKeyword.value" size="small" placeholder="鎼滅储浠ｇ爜/鍚嶇О" clearable style="width: 200px" />
      <el-select v-model="ctx.tableStatusFilter.value" size="small" placeholder="鐘舵€? clearable style="width: 120px">
        <el-option label="姝ｅ父" value="ok" />
        <el-option label="鏈夐敊璇? value="error" />
      </el-select>
      <el-checkbox v-model="ctx.showProblemOnly.value">浠呯湅闂</el-checkbox>
      <el-button size="small" @click="ctx.deselectAllDuplicates()">
        鍙栨秷閲嶅琛岄€変腑锛坽{ ctx.duplicateCount.value }}锛?      </el-button>
      <div class="ml-auto">
        <el-button size="small" @click="ctx.toggleBatchFix()">鎵归噺淇</el-button>
        <el-button size="small" @click="ctx.toggleAllocationPanel()">鍒嗛厤鐩爣</el-button>
      </div>
    </div>

    <el-row :gutter="12">
      <el-col :span="ctx.showBatchFix.value || ctx.showAllocationGroupPanel.value ? 18 : 24">
        <el-table :data="ctx.filteredPagedData.value" border size="small" row-key="_rowKey">
          <el-table-column type="selection" :selectable="(r: any) => !ctx.isRowBlocked(r) && !r.is_duplicate"
                           width="48" />
          <el-table-column prop="symbol" label="浠ｇ爜" width="110" />
          <el-table-column prop="name" label="鍚嶇О" min-width="140" />
          <el-table-column prop="type" label="绫诲瀷" width="90" />
          <el-table-column label="鏁伴噺" width="120">
            <template #default="{ row }">
              <span v-if="!row.isEditingQty">{{ row.quantity }}</span>
              <el-input v-else v-model.number="row.quantity" size="small" @blur="ctx.finishEdit(row, 'quantity')" />
            </template>
          </el-table-column>
          <el-table-column label="浠锋牸" width="120">
            <template #default="{ row }">
              <span v-if="!row.isEditingPrice">{{ row.price }}</span>
              <el-input v-else v-model.number="row.price" size="small" @blur="ctx.finishEdit(row, 'price')" />
            </template>
          </el-table-column>
          <el-table-column prop="amount" label="閲戦" width="120" />
          <el-table-column prop="allocation" label="鍒嗛厤" width="100" />
          <el-table-column label="鎿嶄綔" width="160" fixed="right">
            <template #default="{ row }">
              <el-button link size="small" @click="ctx.startEdit(row, 'quantity')">鏀规暟閲?/el-button>
              <el-button link size="small" @click="ctx.startEdit(row, 'price')">鏀逛环鏍?/el-button>
              <el-button link size="small" @click="ctx.smartFill(row, 'amount')">鏅鸿兘濉厖</el-button>
            </template>
          </el-table-column>
          <el-table-column v-if="ctx.showProblemOnly.value" prop="error" label="闂" min-width="160" />

          <template #append v-if="row.is_duplicate">
            <!-- 鍚堝苟琛岋紙绾㈠埄+绋庯級灞曠ず锛屽叿浣撶粨鏋勬寜鍘?is_merged/children 瀹炵幇 -->
          </template>
        </el-table>

        <el-pagination class="mt-3 justify-end"
                       :current-page="ctx.currentPage.value"
                       :page-size="ctx.pageSize.value"
                       :total="ctx.filteredTotal.value"
                       layout="prev, pager, next, sizes, total"
                       @current-change="ctx.handlePageChange"
                       @size-change="ctx.handleSizeChange" />
      </el-col>

      <el-col v-if="ctx.showBatchFix.value || ctx.showAllocationGroupPanel.value" :span="6">
        <BatchFixPanel v-if="ctx.showBatchFix.value" class="mb-3" />
        <AllocationPanel v-if="ctx.showAllocationGroupPanel.value" />
      </el-col>
    </el-row>

    <div class="mt-6 flex justify-between">
      <el-button @click="emit('prev')">涓婁竴姝?/el-button>
      <el-button type="primary" @click="ctx.confirmImport()">纭瀵煎叆</el-button>
      <el-button @click="emit('next')">鏌ョ湅缁撴灉</el-button>
    </div>
  </div>
</template>
```

## `views/investment/import/components/SummaryCards.vue`

```vue
<script setup lang="ts">
// 姝ラ2 椤堕儴姹囨€诲崱鐗囷紙success / warning / danger锛?// 绾睍绀猴紝鏁版嵁鏉ヨ嚜鍏变韩涓婁笅鏂囥€?import { inject, computed } from "vue";
import { importContextKey } from "@/composables/import/context";

const ctx = inject(importContextKey)!;

const selected = computed(() => ctx.selectedCount.value);
const problems = computed(() => {
  const c = ctx.problemCategories.value;
  return (c.missingCode?.length ?? 0) + (c.missingQtyPrice?.length ?? 0) + (c.mismatch?.length ?? 0);
});
const duplicates = computed(() => ctx.duplicateCount.value);
</script>

<template>
  <div class="summary-cards grid grid-cols-3 gap-3 mb-4">
    <el-card shadow="never">
      <template #header><span class="text-green-600">宸查€夊彲瀵煎叆</span></template>
      <div class="text-2xl font-bold">{{ selected }}</div>
    </el-card>
    <el-card shadow="never">
      <template #header><span class="text-amber-500">寰呬慨澶嶉棶棰?/span></template>
      <div class="text-2xl font-bold">{{ problems }}</div>
    </el-card>
    <el-card shadow="never">
      <template #header><span class="text-red-500">閲嶅璁板綍</span></template>
      <div class="text-2xl font-bold">{{ duplicates }}</div>
    </el-card>
  </div>
</template>
```

## `constants/importFormats.ts`

```ts
// src/constants/importFormats.ts
//
// 6 绉嶅鍏ユ牸寮忕殑閰嶇疆椹卞姩琛ㄣ€傚彇浠ｅ師 import/index.vue 閲屾暎钀藉湪
// formatGuides锛坮eactive锛? beforeUpload / uploadError 鐨?6 濂?if-else 鍒嗘敮銆?// 鎶界鍚庯細鏂板鏍煎紡鍙敼杩欓噷锛岀粍浠堕€昏緫闆舵敼鍔ㄣ€?//
import type { ImportFormat } from "@/composables/import/types";

export interface ImportFormatGuide {
  /** 鏍煎紡鏍囪瘑锛屼笌鍘?formatGuides 鐨?key 涓€鑷?*/
  key: ImportFormat;
  /** 灞曠ず鍚?*/
  label: string;
  /** el-upload 鐨?accept锛堝喅瀹氬彲閫夋嫨鐨勬枃浠剁被鍨嬶級 */
  accept: string;
  /** 鍗曟枃浠跺ぇ灏忎笂闄愶紙瀛楄妭锛夈€侾DF 閫氬父鏇村ぇ */
  maxSize: number;
  /** 鏄惁鍩洪噾绫伙紙鍐冲畾鏄惁璧?calcFundNav / 璐圭巼锛?*/
  isFund: boolean;
  /** 寮曞闈㈡澘鏂囨锛堝師 formatGuides[xxx].guide锛?*/
  guide: string;
  /** 妯℃澘鏂囦欢鍚嶏紙鍘?handleDownloadTemplate 鎸夋牸寮忓彇锛?*/
  templateName: string;
  /** 鍏煎/鎺掗敊鎻愮ず锛堝師 uploadError 鍒嗘敮閲岀殑 format-specific 鎻愮ず锛?*/
  troubleshooting: string;
}

export const IMPORT_FORMAT_CONFIG: Record<ImportFormat, ImportFormatGuide> = {
  standard_stock: {
    key: "standard_stock",
    label: "鏍囧噯鑲＄エ浜ゅ壊鍗?,
    accept: ".csv,.xls,.xlsx",
    maxSize: 5 * 1024 * 1024,
    isFund: false,
    guide: "閫傜敤浜庡埜鍟嗗鍑虹殑鏍囧噯鑲＄エ浜ゅ壊鍗曪紙CSV/Excel锛夈€?,
    templateName: "stock_template.csv",
    troubleshooting: "璇风‘璁ゅ鍑虹殑鏄€庝氦鍓插崟銆忚€岄潪銆庡璐﹀崟銆忥紱缂栫爜涓?UTF-8銆?,
  },
  ths: {
    key: "ths",
    label: "鍚岃姳椤轰氦鍓插崟",
    accept: ".csv,.xls,.xlsx",
    maxSize: 5 * 1024 * 1024,
    isFund: false,
    guide: "閫傜敤浜庡悓鑺遍『瀵煎嚭鐨勪氦鍓插崟锛屽垪椤哄簭涓庢爣鍑嗙増鐣ユ湁宸紓銆?,
    templateName: "ths_template.csv",
    troubleshooting: "鍚岃姳椤洪儴鍒嗙増鏈鍑哄惈鍚堝苟琛ㄥご锛岃鍏堟媶鎴愬崟琛岃〃澶村啀瀵煎叆銆?,
  },
  standard_fund: {
    key: "standard_fund",
    label: "鏍囧噯鍩洪噾浜ゅ壊鍗?,
    accept: ".csv,.xls,.xlsx",
    maxSize: 5 * 1024 * 1024,
    isFund: true,
    guide: "閫傜敤浜庡熀閲戝钩鍙板鍑虹殑鏍囧噯浜ゅ壊鍗曘€?,
    templateName: "fund_template.csv",
    troubleshooting: "鍩洪噾浠ｇ爜闇€涓?6 浣嶏紝缂哄け璇疯蛋銆庡熀閲戜唬鐮佸尮閰嶃€忋€?,
  },
  tiantian_fund: {
    key: "tiantian_fund",
    label: "澶╁ぉ鍩洪噾",
    accept: ".csv,.xls,.xlsx",
    maxSize: 5 * 1024 * 1024,
    isFund: true,
    guide: "閫傜敤浜庡ぉ澶╁熀閲戝鍑虹殑鎸佷粨/浜ゆ槗鏄庣粏銆?,
    templateName: "fund_template.csv",
    troubleshooting: "澶╁ぉ鍩洪噾瀵煎嚭甯稿惈鍒嗙孩璁板綍锛岀郴缁熶細鑷姩鍚堝苟绾㈠埄涓庣◣銆?,
  },
  alipay_pdf: {
    key: "alipay_pdf",
    label: "鏀粯瀹?PDF",
    accept: ".pdf",
    maxSize: 10 * 1024 * 1024,
    isFund: true,
    guide: "閫傜敤浜庢敮浠樺疂銆岃祫浜ц瘉鏄?/ 鍩洪噾璐﹀崟銆峆DF銆?,
    templateName: "fund_template.csv",
    troubleshooting: "PDF 鎵弿浠堕渶娓呮櫚锛涜嫢涓哄浘鐗囧瀷 PDF 鍙兘鏃犳硶瑙ｆ瀽锛岃鏀圭敤 CSV銆?,
  },
  alipay_fund: {
    key: "alipay_fund",
    label: "鏀粯瀹濆熀閲?CSV",
    accept: ".csv,.xls,.xlsx",
    maxSize: 5 * 1024 * 1024,
    isFund: true,
    guide: "閫傜敤浜庢敮浠樺疂瀵煎嚭鐨勫熀閲?CSV銆?,
    templateName: "fund_template.csv",
    troubleshooting: "鏀粯瀹?CSV 閲戦鍒楀彲鑳藉惈閫楀彿鍗冨垎浣嶏紝绯荤粺浼氳嚜鍔ㄦ竻娲椼€?,
  },
};

/** 鎵€鏈夋牸寮?key 鍒楄〃锛堢敤浜庨亶鍘?鏍￠獙锛?*/
export const IMPORT_FORMAT_KEYS = Object.keys(IMPORT_FORMAT_CONFIG) as ImportFormat[];

/** 鍙栨煇鏍煎紡閰嶇疆锛涙湭鐭ヨ繑鍥?undefined锛堣皟鐢ㄦ柟闇€鍏滃簳锛?*/
export function getFormatConfig(key: ImportFormat): ImportFormatGuide {
  return IMPORT_FORMAT_CONFIG[key];
}
```
