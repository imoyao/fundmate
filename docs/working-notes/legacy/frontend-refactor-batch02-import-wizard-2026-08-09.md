# 鎵规 2.1 鈥?import/index.vue 鐨?8 涓?composable锛堝彲钀藉湴鐨勬娊绂婚鏋讹級

> 鏈洰褰曟妸 95KB 鐨?`import/index.vue` 鎷嗘垚 8 涓?composable + 鍏变韩绫诲瀷 + 鏍煎紡閰嶇疆甯搁噺銆?> 鎵€鏈夌姸鎬佸悕/鍑芥暟鍚?瀛楁鍚?*1:1 瀵瑰簲鍘熺粍浠?*锛堝熀浜庢簮鐮佺粨鏋勫垎鏋愭姄鍙栫殑鐪熷疄鍚嶇О锛夛紝
> 浣犲湪鏈湴鎶婂師 `<script setup>` 閲岀殑瀵瑰簲鍧?*鏈烘鎼繍**杩涘搴?composable 鍗冲彲锛屽嚑涔庢棤闇€鏀瑰悕銆?
>
## 鏂囦欢娓呭崟

```
composables/import/
鈹溾攢鈹€ types.ts                    # 鍏变韩绫诲瀷锛歅reviewRow / ImportFormat / ProblemCategoryKey / AllocationGroup / ImportResult
鈹溾攢鈹€ index.ts                    # barrel 鍑哄彛
鈹溾攢鈹€ useImportWizard.ts          # 姝ラ缂栨帓 + 璐︽埛閫夋嫨 + 瀵煎叆鎻愪氦
鈹溾攢鈹€ useFileParser.ts            # 涓婁紶 / 鏍煎紡鏍￠獙 / 瑙ｆ瀽锛? 鏍煎紡鏀规煡琛紝鍘?if-else锛?鈹溾攢鈹€ usePreviewData.ts           # 棰勮鏁版嵁鎸佹湁 + 琛岄敭 + 绛涢€夊垎椤碉紙淇鍘?filteredPagedData/filteredTotal DRY锛?鈹溾攢鈹€ useRowSelection.ts          # 琛岄€夋嫨鐘舵€佹満锛堝叏閫?鍗婇€?鎺掗櫎闃绘柇琛屼笌閲嶅琛岋級
鈹溾攢鈹€ useRowEditing.ts            # 琛屽唴缂栬緫锛堟暟閲?浠锋牸 popover锛? 鏅鸿兘濉厖
鈹溾攢鈹€ useBatchFix.ts              # 涓夌被闂鎵归噺淇 + 鍩洪噾 NAV 鍥炲～
鈹溾攢鈹€ useAllocation.ts            # 鍒嗛厤鐩爣绠＄悊锛堣绾?鍒嗙粍绾?鎵归噺锛?鈹斺攢鈹€ useDuplicateHandling.ts     # 閲嶅琛屾娴嬩笌鍙栨秷閫変腑

constants/
鈹斺攢鈹€ importFormats.ts            # IMPORT_FORMAT_CONFIG锛? 绉嶆牸寮忕殑閰嶇疆椹卞姩琛紙鏇夸唬鍘?formatGuides + if-else 鍒嗘敮锛?```

## 钀藉湴姝ラ

### 1. 澶嶅埗鏂囦欢鍒颁粨搴?```bash
cp -r fundmate-optimization/batch2/composables/import frontend/src/composables/
cp     fundmate-optimization/batch2/constants/importFormats.ts frontend/src/constants/
```

### 2. 鍦?`index.vue` 閲屾帴绾匡紙椤堕儴 `<script setup>`锛?```ts

import { useImportWizard, usePreviewData, useRowSelection, useRowEditing,
         useBatchFix, useAllocation, useDuplicateHandling, useFileParser } from "@/composables/import";

// 鍏堝缓鏁版嵁搴曞骇
const { previewData, addRowKeys, filteredPagedData, filteredTotal, /*...*/ } = usePreviewData();

// 琛岄€夋嫨渚濊禆 previewData
const { selectedKeys, isAllSelected, isIndeterminate, /*...*/ } = useRowSelection(previewData);

// 缂栬緫 / 鎵归噺淇 / 鍒嗛厤 / 閲嶅 閮戒緷璧?previewData锛堟壒閲忎慨澶嶄笌閲嶅杩橀渶 selectedKeys锛?const { startEdit, finishEdit, smartFill, /*... */ } = useRowEditing(previewData);
const { problemCategories, batchFixAmount, fetchAndFillFundNav, /* ... */ } = useBatchFix(previewData, selectedKeys);
const { allocationGroupsByType, batchSetAllocation, /* ...*/ } = useAllocation(previewData);
const { duplicateCount, deselectAllDuplicates } = useDuplicateHandling(previewData, selectedKeys);

// 鍚戝缂栨帓渚濊禆 previewData + selectedKeys
const wizard = useImportWizard({ previewData, selectedKeys });

// 鏂囦欢瑙ｆ瀽锛氳В鏋愮粨鏋滃洖璋冩帴 addRowKeys锛涙牸寮?璐︽埛鏉ヨ嚜 wizard
const { parsing, uploadError, beforeUpload, handleUpload, /*...*/ } = useFileParser({
  getFormat: () => wizard.selectedFormat.value,
  getLedgerId: () => wizard.selectedLedgerId.value,
  onParsed: (rows) => addRowKeys(rows),
});

```

### 3. 妯℃澘鏀?`v-if` 鍥涘甯冨眬 鈫?4 涓楠ょ粍浠?鎶?4 濂?`v-if/v-else-if` 椤甸潰甯冨眬鍒嗗埆鎶藉埌锛?```
views/asset/investment/import/components/
鈹溾攢鈹€ AccountSelectionStep.vue   # 姝ラ0锛氳处鎴烽€夋嫨 + 鏂板缓璐︽埛
鈹溾攢鈹€ FileUploadStep.vue         # 姝ラ1锛氫笂浼?+ 鏍煎紡閫夋嫨 + 妯℃澘涓嬭浇
鈹溾攢鈹€ PreviewTable.vue           # 姝ラ2锛氳〃鏍?+ 鍐呰仈缂栬緫 + 鎵归噺淇 + 鍒嗛厤闈㈡澘
鈹斺攢鈹€ ImportResult.vue           # 姝ラ3锛氱粨鏋滄眹鎬?```
鐖跺３鐢?`:current-step="wizard.currentStep.value"` 鍒囨崲銆傛楠ょ粍浠堕€氳繃 props/emits 涓庝笂闈㈢殑 composable 浜や簰銆?
### 4. 鍒犲師鏂囦欢閲屽凡琚娊璧扮殑鍧?- `<script setup>` 涓搴斿嚱鏁?鐘舵€佸垹闄わ紝鏀逛负涓婇潰鐨?composable 寮曠敤
- `formatGuides` reactive 鍒犻櫎锛屾ā鏉块噷 `formatGuides[xxx]` 鏀逛负 `IMPORT_FORMAT_CONFIG[xxx]`锛堟潵鑷?`@/constants/importFormats`锛?- `beforeUpload`/`uploadError` 閲岀殑 6 濂楁牸寮忓垎鏀垹闄わ紙宸茬敱 `useFileParser` 鏌ヨ〃澶勭悊锛?
## 宸查『甯︿慨澶嶇殑闂
- **DRY锛堟柟妗堢15椤癸級**锛歚filteredPagedData` 涓?`filteredTotal` 鍘熼噸澶嶅疄鐜?鈫?鐜扮粺涓€娲剧敓鑷崟涓€ `filteredRows`銆?- **鏍煎紡 if-else锛堟柟妗堢8椤癸級**锛? 濂楃‖缂栫爜鍒嗘敮 鈫?`IMPORT_FORMAT_CONFIG` 閰嶇疆椹卞姩銆?
## 鈿?闇€浣犳湰鍦板榻愮殑 TODO锛堝凡鍦ㄤ唬鐮佸唴鏍囨敞锛?- `parseFile` / `confirmImport` / `calcFundNav` / `getLedgers` / `createLedger` 鐨勭湡瀹炲叆鍙?鍑哄弬缁撴瀯锛堜唬鐮侀噷鐢?`as any` 鍗犱綅锛夈€?- `isRowBlocked` 鐨勫垽瀹氳鍒欍€乣skipCategory` 鐨勭‘鍒囪涓猴紙鏍囪璺宠繃 vs 绉婚櫎锛夈€乣mismatch` 鐨勫垎绫婚槇鍊笺€?- `PreviewRow` 瀛楁鑻ヤ笌鍚庣瀹為檯杩斿洖涓嶄竴鑷达紝浠ョ湡瀹炵粨鏋勪负鍑嗐€?
## 楠岃瘉娓呭崟
- [ ] `pnpm type-check` 閫氳繃锛堝厛琛?TODO 鐨?API 绫诲瀷锛?- [ ] 4 姝ュ悜瀵煎叏娴佺▼锛氶€夎处鎴?鈫?涓婁紶 鈫?棰勮淇锛堢瓫閫?鍒嗛〉/鍐呰仈缂栬緫/鎵归噺淇/鍒嗛厤/閲嶅鍙栨秷锛夆啋 缁撴灉
- [ ] 鎵归噺淇涓夌被闂鍚?`filteredTotal` 涓?`filteredPagedData` 鏁伴噺涓€鑷达紙DRY 淇楠岃瘉锛?- [ ] 鍒囨崲瀵煎叆鏍煎紡鏃?accept/澶у皬闄愬埗/鎺掗敊鏂囨姝ｇ‘锛堥厤缃┍鍔ㄩ獙璇侊級

---

## 姝ラ缁勪欢 + 鐖跺３锛堟湰鐩綍宸蹭竴骞剁敓鎴愶級

```

frontend/src/views/asset/investment/import/
鈹溾攢鈹€ ImportWizard.vue              # 鈽?鐖跺３锛堟浛鎹㈠師 index.vue锛夛細缁勮涓婁笅鏂?+ 鎸夋楠ゅ垏鎹?鈹斺攢鈹€ components/
    鈹溾攢鈹€ AccountSelectionStep.vue  # 姝ラ0锛氳处鎴烽€夋嫨 + 鏂板缓璐︽埛锛堝唴宓?CreateLedgerDialog锛?    鈹溾攢鈹€ FileUploadStep.vue        # 姝ラ1锛氭牸寮忛€夋嫨 + 涓婁紶 + 妯℃澘涓嬭浇
    鈹溾攢鈹€ PreviewTable.vue          # 姝ラ2锛氳〃鏍?+ 绛涢€夊垎椤?+ 鍐呰仈缂栬緫锛堝唴宓屼笅闈?涓級
    鈹溾攢鈹€ ImportResult.vue          # 姝ラ3锛氱粨鏋滄眹鎬?+ 璺宠浆
    鈹溾攢鈹€ SummaryCards.vue          # 姝ラ2 椤堕儴姹囨€诲崱鐗囷紙宸查€?寰呬慨澶?閲嶅锛?    鈹溾攢鈹€ BatchFixPanel.vue         # 姝ラ2 渚ф爮锛氫笁绫婚棶棰樻壒閲忎慨澶?+ 鍑€鍊煎洖濉?    鈹溾攢鈹€ AllocationPanel.vue       # 姝ラ2 渚ф爮锛氬垎閰嶇洰鏍囩鐞?    鈹斺攢鈹€ CreateLedgerDialog.vue    # 鏂板缓璐︽埛瀵硅瘽妗?```

### 鐘舵€佸叡浜満鍒讹細provide / inject

8 涓?composable 鐨勫疄渚嬪繀椤诲湪**鍚屼竴涓粍浠跺疄渚?*閲屽垱寤烘墠鑳藉叡浜姸鎬併€傚洜姝わ細

- **鐖跺３ `ImportWizard.vue`** 瀹炰緥鍖栧叏閮?composable锛岀粍瑁呮垚 `ImportContext` 骞堕泦锛岀敤 `provide(importContextKey, ctx)` 娉ㄥ叆銆?- **鍚勬楠ょ粍浠?* 鐢?`inject(importContextKey)` 鍙栫敤锛岀洿鎺ヨ `ctx.xxx.value`銆佽皟 `ctx.yyy()`锛?*鏃犻渶 prop 閫忎紶銆佷笉浼氬悇鑷疄渚嬪寲**銆?

### 钀藉湴姝ラ锛堢画涓婃枃锛?4. 澶嶅埗鐖跺３涓庢楠ょ粍浠跺埌浠撳簱锛?   ```bash

   cp fundmate-optimization/batch2/views/investment/import/ImportWizard.vue \
      frontend/src/views/asset/investment/import/IndexWizard.vue   # 鎴栬鐩?index.vue
   cp -r fundmate-optimization/batch2/views/investment/import/components \
        frontend/src/views/asset/investment/import/

   ```
5. 璺敱琛?`asset.ts` 閲?`InvestmentImport` 鐨?component 鏀逛负鎸囧悜鏂扮埗澹筹紙鑻ユ枃浠跺悕鏀逛负 IndexWizard.vue锛夈€?6. 鍘?`import/index.vue` 鍒犻櫎鎴栭噸鍛藉悕涓虹埗澹筹紱鍏?`<script setup>` 閲屽凡琚娊璧扮殑閫昏緫鏁存鍒犻櫎銆?
### 妯℃澘閲屽 ctx 鐨勫紩鐢ㄧ害瀹?- 鎵€鏈夊搷搴斿紡鍊肩敤 `ctx.xxx.value`锛堝湪妯℃澘涓?`ctx` 鏄敞鍏ュ璞★紝鍏跺睘鎬ф槸 ref锛夈€?  渚嬶細`ctx.selectedLedgerId.value`銆乣ctx.filteredPagedData.value`銆乣ctx.showBatchFix.value`銆?- 鎵€鏈夋柟娉曠洿鎺ヨ皟锛歚ctx.onAccountSelected(...)`銆乣ctx.confirmImport()`銆乣ctx.startEdit(row,'quantity')`銆?- 浜嬩欢鍚戜笂鐢?`defineEmits`锛堟湰楠ㄦ灦鐢?`@next`/`@prev` 椹卞姩鐖跺３姝ラ鍒囨崲锛夈€?
### 宸茬煡鍗犱綅 / TODO锛堜笌 composable 鍚屾簮锛?- `el-upload` 鐨?`http-request` 瀵规帴 `ctx.handleUpload`锛屽叾鍏ュ弬 `{ file }` 宸插榻?Element Plus銆?- `handleDownloadTemplate` 浠呮墦鍗版ā鏉垮悕锛屽疄闄呬笅杞藉湴鍧€/鎺ュ彛闇€瀵归綈銆?- 鍚堝苟琛岋紙绾㈠埄+绋?`is_merged`/`children`锛夊睍绀哄尯涓哄崰浣嶏紝鎸夊師缁勪欢閫昏緫琛ュ叏銆?- `ImportContext` 绫诲瀷鐢?8 涓?composable 杩斿洖鍊?`&` 骞堕泦鐢熸垚锛屾柊澧炲瓧娈佃嚜鍔ㄧ撼鍏ャ€?
## 鐩綍鎬昏锛堟湰鎵规浜や粯锛?```
batch2/
鈹溾攢鈹€ composables/import/   # 8 composable + types + context + index锛堢函閫昏緫锛?鈹溾攢鈹€ constants/
鈹?  鈹斺攢鈹€ importFormats.ts  # 6 鏍煎紡閰嶇疆椹卞姩琛?鈹斺攢鈹€ views/asset/investment/import/
    鈹溾攢鈹€ ImportWizard.vue  # 鐖跺３
    鈹斺攢鈹€ components/       # 8 涓?.vue 姝ラ/灞曠ず缁勪欢
```
