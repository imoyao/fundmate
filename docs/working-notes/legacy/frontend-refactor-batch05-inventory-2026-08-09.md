# 鎵规 5 鈥?inventory/index.vue锛?0.8KB锛夋媶鍒?+ 閰嶇疆鎶藉彇

> 鎶?`frontend/src/views/asset/inventory/index.vue`锛堝師 30.8KB锛夐噸鏋勪负
> 銆? 涓叡浜牳 + 2 涓姛鑳?composable + 1 涓牱寮忓姪鎵?+ 4 涓粍浠?+ 1 涓３缁勪欢銆嶃€?> 鏈壒娆?*涓庢壒娆?1 寮鸿仈鍔?*锛氱敤 `batch1/extract-inventory-config.py` 鎶婂唴鑱旂殑 `categories` / `assetTypeMap`
> 鎶藉埌 `frontend/src/constants/categories.ts` + `assetTypes.ts`锛涘唴鑱?`EXCHANGE_RATES` 鏀逛负寮曠敤鎵规 1 鐨?> `frontend/src/constants/exchangeRates.ts`銆傜姸鎬佸悕/鍑芥暟鍚嶅潎鏉ヨ嚜瀵规簮鏂囦欢鐨勭粨鏋勫寲鍒嗘瀽锛屼究浜?*鏈烘鎼繍**銆?>
> 娉細鍘?inventory 椤甸潰**鏈氨鏃?ECharts**锛堜笌鏃╁墠鈥滄帴 useEchartsLifecycle鈥濈殑鍋囪涓嶅悓锛夛紝鏁呮湰鎵规涓嶉渶瑕佸浘琛ㄥ熀寤猴紝
> 浠峰€煎湪浜?*閰嶇疆鎶藉彇 + 缁勪欢鍒嗚В**銆?
>
## 鏂囦欢娓呭崟锛堟湰鐩綍 12 涓枃浠讹級

```
batch5/
鈹溾攢鈹€ composables/inventory/
鈹?  鈹溾攢鈹€ types.ts                # CategoryKey / CategoryDef / AssetTypeDef / Asset / Position
鈹?  鈹溾攢鈹€ useInventoryData.ts     # 鈽?鍏变韩鏍革細澶х被鐘舵€?/ 姒傝 / 鎸佷粨 / 璧勪骇缂撳瓨 / 鎳掑姞杞?/ 璺敱
鈹?  鈹溾攢鈹€ useAssetEdit.ts         # 缂栬緫/鍒犻櫎璧勪骇寮圭獥锛堝鐢?core 鍒锋柊锛?鈹?  鈹溾攢鈹€ useInventoryStyles.ts   # 鏍峰紡/鏍囩鍔╂墜锛歵ab 楂樹寒 / 閰嶇疆椤归厤鑹?/ CSS 鍙橀噺瑙ｆ瀽
鈹?  鈹溾攢鈹€ context.ts              # InventoryContext + inventoryContextKey + useInventoryContext()
鈹?  鈹斺攢鈹€ index.ts                # barrel 鍑哄彛
鈹斺攢鈹€ views/asset/inventory/
    鈹溾攢鈹€ InventoryHome.vue       # 鈽?閲嶆瀯鍚庣殑澹崇粍浠讹紙鏇挎崲鍘?index.vue锛?    鈹斺攢鈹€ components/
        鈹溾攢鈹€ CategoryTabs.vue         # 6 澶х被 tab 鏍忥紙閲戦鍚堣 + 楂樹寒锛?        鈹溾攢鈹€ InvestmentPanel.vue      # 鎶曡祫绫诲満鏅細鍒嗗竷鍗＄墖 + 蹇嵎鎿嶄綔 + 鎸佷粨琛?        鈹溾攢鈹€ AssetList.vue            # 鍏朵粬绫诲満鏅細瀛愮被鍨嬪揩鎹锋坊鍔?+ 璧勪骇琛?        鈹斺攢鈹€ AssetEditDialog.vue      # 缂栬緫璧勪骇寮圭獥
```

## 鏋舵瀯瑕佺偣锛堜笌鎵规 2/3/4 涓€鑷达級

- 鍔熻兘 composable 閫氳繃**鍙傛暟娉ㄥ叆 `data`**锛堟牳锛夛紝鏃犲惊鐜緷璧栥€?- 澹崇粍浠?`provide(inventoryContextKey, ctx)`锛? 涓瓙缁勪欢 `useInventoryContext()` 娉ㄥ叆銆?

## 鈽?閰嶇疆鎶藉彇锛堜笌鎵规 1 鑱斿姩锛屽叧閿級

鍘?`index.vue` 鍐呰仈浜嗕袱鍧楀ぇ甯搁噺锛屽凡鐢ㄦ壒娆?1 鑴氭湰缁撴瀯鍖栨娊鍙栵紙鎷彿閰嶅钩锛屼笉鎵嬫妱锛夛細

```bash
# 鍦?fundmate 浠撳簱鏍圭洰褰曟墽琛岋紙鍏?dry-run 纭锛?python3 fundmate-optimization/batch1/extract-inventory-config.py --dry-run
python3 fundmate-optimization/batch1/extract-inventory-config.py
```

鐢熸垚锛?- `frontend/src/constants/categories.ts`   鈫?`export const categories = [...]`

- `frontend/src/constants/assetTypes.ts`   鈫?`export const assetTypeMap = {...}`

閲嶆瀯鍚?`useInventoryData` 鏀逛负 `import { categories } from "@/constants/categories"` /
`import { assetTypeMap } from "@/constants/assetTypes"`锛屽師鍐呰仈甯搁噺鏁存鍒犻櫎銆?鍐呰仈 `EXCHANGE_RATES` 鏀逛负寮曠敤鎵规 1 鐨?`@/constants/exchangeRates`锛堣涓嬫柟 TODO锛夈€?

## 钀藉湴姝ラ

### 1. 鍏堟娊鍙栧父閲忥紙鎵规 1 鑴氭湰锛?```bash

python3 fundmate-optimization/batch1/extract-inventory-config.py

```

### 2. 澶嶅埗 composable 涓庡瓙缁勪欢
```bash
cp -r fundmate-optimization/batch5/composables/inventory frontend/src/composables/
cp -r fundmate-optimization/batch5/views/asset/inventory/components \
      frontend/src/views/asset/inventory/
```

### 3. 鐢ㄥ３缁勪欢鏇挎崲鍘?index.vue

```bash
mv frontend/src/views/asset/inventory/index.vue \
   frontend/src/views/asset/inventory/index.legacy.vue
cp fundmate-optimization/batch5/views/asset/inventory/InventoryHome.vue \
   frontend/src/views/asset/inventory/index.vue
```

> 璺敱琛?`asset.ts` 涓?inventory 鐨?component 鏃犻渶鏀癸紙浠嶆寚鍚?`index.vue`锛夈€?
>
### 4. 鏈烘鎼繍鍘熼€昏緫

鎶婂師 `index.vue` `<script setup>` 鍚勫潡**鎸変笅琛?*鎼叆瀵瑰簲 composable锛涙ā鏉挎媶鍒嗕负澹?+ 4 涓粍浠躲€?

## 鍘熸枃浠?鈫?鏈洰褰?瀵瑰簲鍏崇郴锛堟惉杩愭竻鍗曪級

| 鍘?index.vue 涓殑鍧?| 鎼埌鍝噷 |
|---|---|
| `categories` / `assetTypeMap` 鍐呰仈甯搁噺 | 鎵规1鑴氭湰 鈫?`@/constants/categories.ts` + `assetTypes.ts`锛堝垹鍐呰仈锛?|
| `EXCHANGE_RATES` 鍐呰仈 | 鏀瑰紩鐢?`@/constants/exchangeRates`锛堟壒娆?宸插锛?|
| `activeCategory` / `assetsSummary` / `assetCache` / `currentAssets` / `loading` + `fetchData` / `loadCategoryAssets` | `useInventoryData` |
| `allPositions` / `investmentPage` / `pageSize` + `investmentGroups` / `paginatedInvestments` / `getCategoryTotal` | `useInventoryData` |
| `activeCategoryDesc` / `activeAssetTypes` / `getMajorCategoryLabel` / `handleAddType` / `watch(activeCategory)` | `useInventoryData` |
| `editAssetDialogVisible` / `savingAsset` / `editAssetForm` / `openEditAssetDialog` / `saveAssetEdit` / `confirmDeleteAsset` | `useAssetEdit` |
| `getCategoryTabStyle` / `getAllocLabel` / `getAllocColor` / `getAllocBgColor` / `resolveCSSVar` / `getColorWithAlpha` | `useInventoryStyles` |
| 椤堕儴鍒嗙被 tab 鏍?| `CategoryTabs.vue` |
| 鎶曡祫绫诲満鏅紙鍒嗗竷/鎿嶄綔/鎸佷粨琛級 | `InvestmentPanel.vue` |
| 鍏朵粬绫诲満鏅紙瀛愮被鍨嬫坊鍔?璧勪骇琛級 | `AssetList.vue` |
| 缂栬緫璧勪骇寮圭獥 | `AssetEditDialog.vue` |
| 椤靛ご / 鎻忚堪鍗?/ v-if 鍦烘櫙鍒囨崲 | `InventoryHome.vue` 澹冲唴 |

## 鈿?闇€浣犳湰鍦板榻愮殑 TODO锛堜唬鐮佸唴宸叉爣娉級

1. **API 妯″潡璺緞**锛氭湰楠ㄦ灦浠?`@/api/assets`锛坄getAssets` / `getAssetsSummary` / `updateAsset` / `deleteAsset`锛夈€?`@/api/positions`锛坄getPositions`锛夊鍏ャ€傝鎸夐」鐩湡瀹?api 鏂囦欢鍚嶈皟鏁淬€?2. **杩斿洖缁撴瀯**锛歚getPositions` / `getAssets` 宸插仛 `items/data/list`鍏煎锛屼互鐪熷疄涓哄噯銆?3. **`ALLOCATION_OPTIONS`褰㈢姸**锛歚useInventoryStyles` 鍋囧畾 `{ value, label, colorVar }[]`锛屾寜鐪熷疄甯搁噺璋冩暣銆?4. **`EXCHANGE_RATES` 鐪熷疄鐢ㄦ硶**锛氬師 `fetchData` 涓嫢鐢ㄦ眹鐜囧仛甯佺褰掍竴锛岃淇濈暀瀵瑰簲鎹㈢畻閫昏緫锛堟湰楠ㄦ灦鏈鍒伙紝閬垮厤鑷嗘祴锛夈€?5. **缁勪欢璺緞**锛歚MoneyDisplay` / `ProductDisplay` / `AssetTypeBadge` / `RiseFallText`鐢ㄧ洰褰曞舰寮?`@/components/MoneyDisplay` 绛夛紙瀵瑰簲 `index.vue`锛屾瘮`.vue`鎵╁睍鍚嶅舰寮忔洿绋筹級锛沗IconifyIconOffline` 鏉ヨ嚜 `@/components/ReIcon`銆?   璇风‘璁よ繖浜涘叏灞€缁勪欢鐪熷疄瀛樺湪涓?props 涓€鑷淬€?6. **`handleAddType` 璺敱**锛氳烦 `/asset/asset-entry?type=...`锛屾寜鐪熷疄褰曞叆椤佃矾鐢辫皟鏁淬€?

## 楠岃瘉娓呭崟

- [ ] `pnpm type-check` 閫氳繃锛堝厛琛ヤ笂杩?API 绫诲瀷锛?- [ ] 6 涓ぇ绫?tab 鍒囨崲姝ｅ父锛岄噾棰濆悎璁℃樉绀烘纭紝楂樹寒鏍峰紡姝ｇ‘
- [ ] 鎶曡祫绫伙細鍒嗗竷鍗＄墖 / 鎸佷粨琛ㄥ垎椤?/ 蹇嵎鎿嶄綔璺宠浆姝ｅ父
- [ ] 鍏朵粬绫伙細瀛愮被鍨嬪揩鎹锋坊鍔犺烦杞€佽祫浜ц〃缂栬緫/鍒犻櫎姝ｅ父
- [ ] 缂栬緫璧勪骇淇濆瓨鍚庡綋鍓嶅垎绫讳笌姒傝鍚屾鍒锋柊
- [ ] 鍘熷唴鑱?`categories` / `assetTypeMap` / `EXCHANGE_RATES` 宸插垹闄わ紝鏀圭敤甯搁噺鏂囦欢锛堟棤閲嶅瀹氫箟銆佹棤纭紪鐮侊級
