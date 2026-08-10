# 鎵规 3 鈥?watchlist/index.vue锛?2.6KB锛夌殑銆屼笂甯濈粍浠躲€嶆媶鍒?
>
> 鎶婇」鐩噷**鏈€澶х殑鍗曟枃浠剁粍浠?* `frontend/src/views/asset/watchlist/index.vue`锛堝師 62.6KB锛?> 閲嶆瀯涓恒€? 涓叡浜牳 composable + 5 涓姛鑳?composable + 5 涓睍绀?寮瑰眰瀛愮粍浠?+ 1 涓３缁勪欢銆嶃€?> 鎵€鏈夌姸鎬佸悕/鍑芥暟鍚嶅潎鏉ヨ嚜瀵规簮鏂囦欢鐨勭粨鏋勫寲鍒嗘瀽锛堣涓嬫柟銆屽搴斿叧绯汇€嶏級锛屼究浜?*鏈烘鎼繍**銆?>
> 涓庢壒娆?2 鐨?import 鍚戝閲囩敤**鍚屼竴濂楁満鍒?*锛坈omposable + provide/inject + 鍗曚竴鍒锋柊 watcher锛夛紝
> 淇濇寔鏋舵瀯涓€鑷淬€?
>
## 涓轰粈涔堝厛鎷嗗畠

- 瀹冩槸鍏ㄩ」鐩?*浣撶Н鏈€澶?*鐨勬枃浠讹紙62.6KB锛夛紝ROI 鏈€楂樸€?- 缁撴瀯宸茶緝娓呮櫚锛堟棤 ECharts銆? 涓瓙缁勪欢宸插缃級锛屾娊绂?*椋庨櫓浣庛€佹敹鐩婄洿瑙?*銆?- 涓昏鐥涚偣涓嶆槸鍥捐〃娉勬紡锛岃€屾槸**閫昏緫鍐呰仛搴︿綆**锛氬垎缁?CRUD銆佹爣绛剧鐞嗐€佹壒閲忔搷浣溿€佽繃婊ゃ€佸疄鏃朵及鍊?  鍏ㄩ儴鍫嗗湪涓€涓?`<script setup>` 閲岋紝瀵艰嚧鍗曟枃浠惰噧鑲裤€侀毦浠ュ崟娴嬨€佹槗鍥炲綊銆?

## 鏂囦欢娓呭崟锛堟湰鐩綍 16 涓枃浠讹級

```
batch3/
鈹溾攢鈹€ composables/watchlist/
鈹?  鈹溾攢鈹€ types.ts                # 鍏变韩绫诲瀷锛歐atchlistItem / Group / Tag / FetchParams / Realtime...
鈹?  鈹溾攢鈹€ constants.ts            # SYSTEM_GROUPS / VENUE_FILTER_OPTIONS / PRESET_TAG_COLORS锛堝幓纭紪鐮侊級
鈹?  鈹溾攢鈹€ useWatchlistCore.ts     # 鈽?鍏变韩鏁版嵁婧愶細items/groups/tags/realtime + 鎷夊彇/缃《鏀惰棌/绉婚櫎/瀵煎嚭
鈹?  鈹溾攢鈹€ useWatchlistGroups.ts   # 鍒嗙粍渚ц竟鏍忥細閫夋嫨/鍐呰仈閲嶅懡鍚?鏂板缓/鍒犻櫎
鈹?  鈹溾攢鈹€ useTableFilters.ts      # 杩囨护锛氳鍥?鎼滅储/鍦洪/鏍囩锛堝彧鏀圭姸鎬侊紝涓嶄富鍔ㄨ姹傦級
鈹?  鈹溾攢鈹€ useBatchActions.ts      # 鎵归噺锛氬閫?鎵归噺鍒犻櫎/鎵归噺绉荤粍
鈹?  鈹溾攢鈹€ useTagManager.ts        # 鍏ㄥ眬鏍囩绠＄悊寮圭獥
鈹?  鈹溾攢鈹€ useRowTagEditor.ts      # 鍗曡鏍囩缂栬緫寮圭獥
鈹?  鈹溾攢鈹€ context.ts              # WatchlistContext 绫诲瀷 + watchlistContextKey + useWatchlistContext()
鈹?  鈹斺攢鈹€ index.ts                # barrel 鍑哄彛
鈹斺攢鈹€ views/asset/watchlist/
    鈹溾攢鈹€ WatchlistIndex.vue      # 鈽?閲嶆瀯鍚庣殑澹崇粍浠讹紙鏇挎崲鍘?index.vue锛?    鈹斺攢鈹€ components/
        鈹溾攢鈹€ GroupsSidebar.vue       # 宸︽爮鍒嗙粍锛堝惈鏂板缓鍒嗙粍寮圭獥锛?        鈹溾攢鈹€ RealtimePanel.vue       # 瀹炴椂浼板€奸潰鏉匡紙banner + 鐘舵€?+ 姹囨€?+ 寮€鍏筹級
        鈹溾攢鈹€ BatchToolbar.vue        # 鎵归噺妯″紡宸ュ叿鏍忥紙浠?batchMode 鏃舵覆鏌擄級
        鈹溾攢鈹€ TagManagerDialog.vue    # 鏍囩绠＄悊寮圭獥
        鈹斺攢鈹€ RowTagEditorDialog.vue  # 琛屾爣绛剧紪杈戝脊绐?```

## 鏋舵瀯瑕佺偣

### 1. 鍏变韩鏍?+ 鍔熻兘 composable锛堜緷璧栨敞鍏ワ紝閬垮厤寰幆锛?- `useWatchlistCore()` 鎷ユ湁**璺ㄥ姛鑳藉叡浜?*鐨勭姸鎬侊紙items / groups / tags / realtime锛変笌妯垏鍔ㄤ綔
  锛坒etchData / togglePin / toggleFavorite / executeRemove / exportData锛夈€?- 鍚勫姛鑳?composable锛坄useWatchlistGroups(core)`銆乣useTableFilters(core)`銆佲€︼級閫氳繃**鍙傛暟娉ㄥ叆 core**锛?  鎿嶄綔 core 鏆撮湶鐨?ref锛沜ore 涓嶅弽鍚戜緷璧栦换浣曞姛鑳?composable 鈫?鏃犲惊鐜緷璧栥€?- 杩欎笌鎵规 2銆宍<child>(previewData)` 娉ㄥ叆鍏变韩婧愩€嶇殑妯″紡瀹屽叏涓€鑷淬€?
### 2. provide / inject 涓婁笅鏂?- 澹崇粍浠?`WatchlistIndex.vue` 缁勮鍏ㄩ儴 composable 杩斿洖鍊?鈫?`provide(watchlistContextKey, ctx)`銆?- 5 涓瓙缁勪欢鐢?`useWatchlistContext()` 娉ㄥ叆锛岀洿鎺ヨ `ctx.xxx`銆佽皟 `ctx.yyy()`锛?  **鏃犻渶 prop 閫忎紶銆佷笉浼氬悇鑷疄渚嬪寲**锛堝惁鍒欏垎缁?鏍囩鐘舵€佷細鍑虹幇澶氫唤銆佷簰鐩镐笉鍚屾锛夈€?
### 3. 鍗曚竴鍒锋柊 watcher锛堝叧閿害瀹氾紝閬垮厤閲嶅璇锋眰锛?- `useTableFilters` / `useWatchlistGroups` **鍙敼鐘舵€侊紝涓嶈皟鐢?fetchData**銆?- 澹崇粍浠跺缓绔?*鍞竴** watcher锛岀洃鍚?`core.activeGroup` 涓?`filters.fetchParams`锛?  ```ts
  watch(
    [() => core.activeGroup.value, () => filters.fetchParams.value],
    () => core.fetchData({ ...filters.fetchParams.value, group: core.activeGroup.value }),
    { deep: true }
  );
  ```

- 鍥犳銆屽垏鍒嗙粍銆嶃€屽垏鍦洪銆嶃€屾悳鍏抽敭璇嶃€嶃€屾敼鏍囩杩囨护銆?*鍏ㄩ儴姹囪仛鍒颁竴澶勫埛鏂?*锛?  涓嶄細鍐嶅嚭鐜般€屽垎缁勫垏鎹?+ 杩囨护鍙樺寲銆嶅彔鍔犲鑷寸殑涓ゆ璇锋眰銆?

## 钀藉湴姝ラ

### 1. 澶嶅埗 composable 涓庡瓙缁勪欢

```bash
cp -r fundmate-optimization/batch3/composables/watchlist \
      frontend/src/composables/

cp -r fundmate-optimization/batch3/views/asset/watchlist/components \
      frontend/src/views/asset/watchlist/
```

### 2. 鐢ㄥ３缁勪欢鏇挎崲鍘?index.vue

```bash
# 寤鸿鍏堟敼鍚嶅浠斤紝鍐嶈鐩?mv frontend/src/views/asset/watchlist/index.vue \
   frontend/src/views/asset/watchlist/index.legacy.vue
cp fundmate-optimization/batch3/views/asset/watchlist/WatchlistIndex.vue \
   frontend/src/views/asset/watchlist/index.vue
```

> 璺敱琛?`asset.ts` 涓?watchlist 鐨?component 鏃犻渶鏀癸紙浠嶆寚鍚?`index.vue`锛夈€?
>
### 3. 鏈烘鎼繍鍘熼€昏緫

鎶婂師 `index.vue` `<script setup>` 涓悇鍧?*鎸変笅鏂瑰搴斿叧绯?*鎼繘瀵瑰簲 composable锛?妯℃澘鎷嗗垎涓哄３ + 5 涓瓙缁勪欢锛堟ā鏉跨粨鏋勫凡鍦ㄦ湰鐩綍缁欏嚭锛屽熀鏈槸 1:1 杩樺師锛夈€?

## 鍘熸枃浠?鈫?鏈洰褰?瀵瑰簲鍏崇郴锛堟惉杩愭竻鍗曪級

| 鍘?index.vue 涓殑鍧?| 鎼埌鍝噷 |
|---|---|
| `items/loading/currentPage/pageSize/totalItems` | `useWatchlistCore` |
| `activeGroup/allGroups/customGroups` + `fetchGroups` | `useWatchlistCore` + `useWatchlistGroups` |
| `allTags` + `fetchTags` + `getTagName/getTagColor` | `useWatchlistCore` |
| `realtime = useRealtimeQuotes(...)` + `toggleBtnText` + `getValuationItem/getHoldings/getStaticPrice` | `useWatchlistCore` |
| `showAddModal/showSettingsDrawer/removeDialogVisible/removingItem/removeScope` + `executeRemove/exportData` | `useWatchlistCore` |
| `togglePin/toggleFavorite` | `useWatchlistCore` |
| `selectGroup/startEditGroup/saveEditGroup/deleteGroupConfirm/handleAddGroup/createGroup` + `editingGroupId/editGroupName/showGroupDialog/newGroupName` | `useWatchlistGroups` |
| `currentView/searchKeyword/currentVenueFilter/selectedFilterTagIds` + `setVenueFilter/debounceSearch/handleViewChange/resetFilters` + `venueStats/fetchParams` | `useTableFilters` |
| `batchMode/selectedItems/batchMoveGroupId` + `toggleBatchMode/handleSelectionChange/handleBatchDelete/handleBatchMoveToGroup` | `useBatchActions` |
| `showTagManager/editingTagId/editTagName/editTagColor/...` + `selectTagForEdit/addNewTagInManager/saveEditTag/deleteTag` | `useTagManager` |
| `showTagEditor/editingItem/editingItemNewTagIds/...` + `openTagEditor/saveTagChanges/createTagInEditor/...` | `useRowTagEditor` |
| 妯℃澘锛氬乏鏍忓垎缁勫垪琛?| `GroupsSidebar.vue` |
| 妯℃澘锛氬疄鏃朵及鍊煎尯鍧?| `RealtimePanel.vue` |
| 妯℃澘锛氭壒閲忓伐鍏锋爮 | `BatchToolbar.vue` |
| 妯℃澘锛氭爣绛剧鐞嗗脊绐?| `TagManagerDialog.vue` |
| 妯℃澘锛氳鏍囩缂栬緫寮圭獥 | `RowTagEditorDialog.vue` |
| 妯℃澘锛氬墿浣欙紙椤舵爮/琛ㄦ牸/鍒嗛〉/绉婚櫎纭锛?| `WatchlistIndex.vue` 澹冲唴 |

## 鈿?闇€浣犳湰鍦板榻愮殑 TODO锛堜唬鐮佸唴宸叉爣娉級

1. **`useRealtimeQuotes` 瀵煎叆璺緞**锛氭湰楠ㄦ灦鍐欑殑鏄?   `@/composables/realtime/useRealtimeQuotes`锛岃鎸夐」鐩疄闄呬綅缃皟鏁淬€?2. **瀹炴椂瀹炰緥瀛楁**锛歚realtime.enabled / status / lastUpdateTime / items / summary / toggle()`
   涓烘寜鍘熸枃鎺ㄦ柇鐨勫舰鐘讹紝闇€瀵圭収鐪熷疄 composable 鏍″噯锛沗getValuationItem` 绛夌殑鍙栧€奸€昏緫浠ョ湡瀹炰负鍑嗐€?3. **`@/api/watchlist` 杩斿洖缁撴瀯**锛歚getWatchlistItems`宸插仛澶?shape 鍏煎
   锛坄items/data/list/results` + `total`锛夛紝鍏朵綑鎺ュ彛鍏ュ弬/鍑哄弬浠ョ湡瀹?`api/watchlist.ts` 涓哄噯銆?4. **宸叉湁瀛愮粍浠惰矾寰?*锛歚AssetTypeBadge / MoneyDisplay / RiseFallText / ProductDisplay /
   AddToWatchlistModal / SettingsDrawer / RealtimeWarningBanner / RealtimeStatusIndicator`
   娌跨敤鍘?`@/components/...` 璺緞锛岃纭杩欎簺缁勪欢纭疄瀛樺湪涓?props 涓€鑷淬€?5. **鍒嗙粍銆屽満澶?鍦哄唴銆嶄笌 `currentView`鐨勮仈鍔ㄨ涔?*锛歚handleViewChange` 灏?`activeGroup`
   鍚屾涓?`all/exchange/otc`锛岃嫢鍘熶笟鍔¤涔変笉鍚岃璋冩暣銆?

## 楠岃瘉娓呭崟

- [ ] `pnpm type-check` 閫氳繃锛堝厛琛ヤ笂杩?TODO 鐨勭湡瀹炵被鍨嬶級
- [ ] 鍒囧垎缁?/ 鍒囧満棣?/ 鎼滅储 / 鏍囩杩囨护锛氬垪琛ㄦ纭埛鏂帮紝涓?Network 涓瘡绉嶆搷浣?*浠?1 娆¤姹?*
- [ ] 鍒嗙粍鍐呰仈閲嶅懡鍚嶃€佹柊寤恒€佸垹闄ゅ悗宸︿晶鍒楄〃鍗虫椂鏇存柊
- [ ] 鏍囩绠＄悊寮圭獥锛氭柊寤?鏀瑰悕/鏀硅壊/鍒犻櫎鐢熸晥锛屼笖琛屾爣绛剧紪杈戦噷鐨勫彲閫夋爣绛惧悓姝?- [ ] 鎵归噺妯″紡锛氬閫?鈫?鎵归噺鍒犻櫎 / 鎵归噺绉荤粍姝ｅ父
- [ ] 瀹炴椂浼板€煎紑鍏炽€佹眹鎬绘暟鍊兼樉绀烘甯?- [ ] 鍗曟祴鍙拡瀵?`useTableFilters` / `useBatchActions` 绛夌函閫昏緫 composable 鐙珛缂栧啓锛堝凡瑙ｈ€?API锛?- [ ] 鏋勫缓浣撶Н锛氬師 `index.vue` 62.6KB 琚媶鏁ｏ紝鏃犻€昏緫涓㈠け

## 鏀剁泭鎬荤粨

- **鍗曟枃浠?62.6KB 鈫?澹崇害 6KB + 10 涓?.ts锛堝叡 ~1.4KB 绾э級 + 5 涓槮缁勪欢**锛屽彲缁存姢鎬т笌鍙祴璇曟€ф樉钁楁彁鍗囥€?- 鍔熻兘閫昏緫锛堝垎缁?鏍囩/鎵归噺/杩囨护/瀹炴椂锛夊彲鐙珛鍗曟祴锛屼笉鍐嶈 1500 琛岀粍浠剁粦鏋躲€?- 鏂板銆屽鍑恒€嶃€屾壒閲忕Щ缁勩€嶇瓑鍔熻兘鏃讹紝鏀瑰姩琚檺鍒跺湪瀵瑰簲 composable锛屼笉鍐嶇壍涓€鍙戝姩鍏ㄨ韩銆?
