# 鎵规 4 鈥?ledgers/detail.vue锛?4KB锛夋媶鍒?+ ECharts 鐢熷懡鍛ㄦ湡淇

> 鎶?`frontend/src/views/asset/ledgers/detail.vue`锛堝師 44KB锛夐噸鏋勪负
> 銆? 涓叡浜牳 + 4 涓姛鑳?composable + 3 涓睍绀虹粍浠?+ 1 涓３缁勪欢銆嶃€?> **鏈壒娆＄殑鏍稿績淇**鏄敤鎵规 1 鐨?`useEchartsLifecycle` 鎺ョ涓や釜 ECharts 瀹炰緥鐨勭敓鍛藉懆鏈燂紝
> 浠庢牴涓婃秷闄ゅ師鏂囦欢鐨勬墜鍐?`echarts.init` + **閲嶅娉ㄥ唽鐨?`onBeforeUnmount`** + 鎵嬪啓 window resize 鐩戝惉 + 缂哄け `onActivated` 鍥涚被闂銆?> 鐘舵€佸悕/鍑芥暟鍚嶅潎鏉ヨ嚜瀵规簮鏂囦欢鐨勭粨鏋勫寲鍒嗘瀽锛屼究浜?*鏈烘鎼繍**銆?
>
## 涓轰粈涔堟槸瀹冿紙ROI 鏈€楂?+ 淇鏈€鐥涳級

- 鍏ㄩ」鐩?ECharts 娉勬紡鏈€鍏稿瀷鐨勬枃浠讹細鍘?`onBeforeUnmount` 琚敞鍐屼簡**涓ゆ**锛屽鑷?`dispose` 閲嶅鎵ц銆?  keepAlive 鍒囧洖鍓嶅彴鍥捐〃涓嶉噸缁橈紙鏃?`onActivated`锛夈€佺獥鍙ｇ缉鏀鹃潬鎵嬪啓 `resize` 鐩戝惉 + `resizeTimer` 闃叉姈銆?- 鎵规 0 鐨?`fix-ledgers-detail.py` 宸茬敤鑴氭湰**鏈烘**淇繃閲嶅 `onBeforeUnmount` + `console.log`锛?  鏈壒娆＄敤 `useEchartsLifecycle` **缁撴瀯鎬?*鎺ョ锛屼娇鍏朵笉鍐嶅彲鑳藉嚭鐜拌繖绫绘牱鏉?bug銆?

## 鏂囦欢娓呭崟锛堟湰鐩綍 13 涓枃浠讹級

```
batch4/
鈹溾攢鈹€ composables/ledger/
鈹?  鈹溾攢鈹€ types.ts                # Ledger / LedgerSummary / Position / Transaction / Portfolio
鈹?  鈹溾攢鈹€ useLedgerDetail.ts      # 鈽?鍏变韩鏍革細璺敱瑙ｆ瀽 / 璐︽埛淇℃伅 / 姒傝 / 璐︽埛鍒楄〃 / 鍒犻櫎 / 鏈垎绫绘寚娲?鈹?  鈹溾攢鈹€ useAccountEdit.ts       # 缂栬緫璐︽埛寮圭獥锛堝鐢?AccountFormFields锛?鈹?  鈹溾攢鈹€ useHoldings.ts          # 鎸佷粨鏄庣粏 tab锛氬垎椤?/ 鎶藉眽 / 鍗曟潯+鎵归噺杩佺Щ / 鍒犻櫎
鈹?  鈹溾攢鈹€ useTransactions.ts      # 浜ゆ槗璁板綍 tab锛氬垎椤?/ 绫诲瀷鏍囩 / 缂栬緫 / 鍒犻櫎
鈹?  鈹溾攢鈹€ useLedgerCharts.ts      # 鈽?鍥捐〃鐢熷懡鍛ㄦ湡锛堝寘瑁?useEchartsLifecycle锛屼慨澶嶆牳蹇冿級
鈹?  鈹溾攢鈹€ context.ts              # LedgerDetailContext + ledgerDetailContextKey + useLedgerDetailContext()
鈹?  鈹斺攢鈹€ index.ts                # barrel 鍑哄彛
鈹斺攢鈹€ views/asset/ledgers/
    鈹溾攢鈹€ LedgerDetail.vue        # 鈽?閲嶆瀯鍚庣殑澹崇粍浠讹紙鏇挎崲鍘?detail.vue锛?    鈹斺攢鈹€ components/
        鈹溾攢鈹€ AccountSummaryCards.vue   # 椤堕儴 3 寮犳瑙堝崱鐗?        鈹溾攢鈹€ HoldingsTable.vue         # 鎸佷粨鏄庣粏琛紙鍚湭鍒嗙被鎸囨淳锛?        鈹斺攢鈹€ TransactionsTable.vue     # 浜ゆ槗璁板綍琛?```

> 宸叉湁瀛愮粍浠?`AccountFormFields` / `DeleteLedgerDialog` / `PositionTransactionsDrawer`
> 锛堜綅浜?`frontend/src/views/asset/ledgers/components/`锛夌户缁鐢紝鏈壒娆?*涓嶉噸鍐?*瀹冧滑锛?> 浠呭湪澹崇粍浠朵腑鎸夌湡瀹?props 鎺ョ嚎锛堣涓嬫柟銆屽凡鏍稿鐪熷疄 props銆嶏級銆?
## 鏋舵瀯瑕佺偣锛堜笌鎵规 2/3 涓€鑷达級

- 鍔熻兘 composable 閫氳繃**鍙傛暟娉ㄥ叆 `core`**锛屾棤寰幆渚濊禆銆?- 澹崇粍浠?`provide(ledgerDetailContextKey, ctx)`锛? 涓瓙缁勪欢 `useLedgerDetailContext()` 娉ㄥ叆銆?- 鍏ㄥ眬鍒锋柊娌跨敤鎵规 1 淇杩囩殑 `usePageRefresh(refreshAll)`锛堝交搴曡В鍐冲缁勪欢闃叉姈涓插彴锛夈€?
## 鈽?ECharts 鐢熷懡鍛ㄦ湡淇璇存槑锛堥噸鐐癸級

鍘?detail.vue 鐨勫浘琛ㄦ牱鏉匡紙宸插叏閮ㄧЩ闄わ級锛?
```js
// 鏃э細鎵嬪啓 init + 閲嶅 onBeforeUnmount + 鎵嬪啓 resize
const chartInstance = echarts.init(chartRef.value)
const lineChartInstance = echarts.init(lineChartRef.value)   // 瀹為檯 initLineChart 鏄┖澹?window.addEventListener("resize", handleWindowResize)
onBeforeUnmount(() => { chartInstance?.dispose(); lineChartInstance?.dispose() })  // 娉ㄥ唽浜嗕袱娆?onBeforeUnmount(() => { chartInstance?.dispose(); lineChartInstance?.dispose() })  // 鈫?閲嶅
// 鏃?onActivated 鈫?keepAlive 鍒囧洖鍓嶅彴鍥捐〃绌虹櫧
```

鏂版柟妗堬紙`useLedgerCharts.ts` 鈫?`useEchartsLifecycle`锛夛細

```ts
const { render, resize, charts } = useEchartsLifecycle(
  [pieRef, lineRef],
  [
    (el) => { const c = echarts.init(el); c.setOption(buildPieOption(holdings.value)); return c },
    (el) => { const c = echarts.init(el); c.setOption(buildLineOption()); return c }
  ],
  { keepAlive: true }   // 璐︽埛鏄庣粏涓?keepAlive 缂撳瓨椤?鈫?鍒囧洖鍓嶅彴鑷姩閲嶇粯
)
watch(holdings, () => nextTick(render), { deep: true })  // 鎸佷粨鍙樺寲 鈫?楗煎浘閲嶇粯
```

鏀剁泭锛氬崟瀹炰緥銆佸崟澶?`resize`/`dispose`銆乣keepAlive` 閲嶇粯銆佹暟鎹┍鍔ㄩ噸缁樷€斺€?*鍥涚被鑰侀棶棰樹竴娆℃€ф秷闄?*銆?

## 宸叉牳瀵圭湡瀹?props锛堥伩鍏嶆偓绌哄紩鐢級

鎶撳彇骞舵牳瀵逛簡椤圭洰宸叉湁鐨勪袱涓粍浠讹紝澹崇粍浠跺凡鎸夌湡瀹炵鍚嶆帴绾匡細

| 缁勪欢 | 鐪熷疄 props | 澹崇粍浠剁敤娉?|
|---|---|---|
| `DeleteLedgerDialog` | `visible` / `ledgerId` / `ledgerName` / `positionCount`锛沞mit `deleted` | `v-model:visible` + `:ledger-id` / `:ledger-name` / `:position-count` + `@deleted="goBack"` |
| `PositionTransactionsDrawer` | `visible` / `positionData`锛堟寜 `positionData.id` 鍐呴儴鎷変氦鏄擄級 | `v-model:visible` + `:position-data` |

> 娉ㄦ剰锛氬師 `deleteDialogVisible` 鍙渶 `visible`锛涘垹闄ゅ姩浣滅敱 `DeleteLedgerDialog` 鑷甫锛堝畠璋?`deleteLedgerWithOptions`锛夛紝
> 澹崇粍浠堕€氳繃 `@deleted` 鍦ㄥ垹闄ゆ垚鍔熷悗杩斿洖鍒楄〃椤点€?
>
## 钀藉湴姝ラ

### 1. 鍏堢‘淇濇壒娆?1 鍩哄缓灏变綅

`useEchartsLifecycle`锛坄@/composables/echarts/useEchartsLifecycle`锛変笌`theme.ts`锛坄ECHARTS_COLOR` / `getRiseColor` / `getFallColor`锛夈€?`usePageRefresh`锛坄@/composables/usePageRefresh`锛夈€乣currency.ts`锛坄formatCurrency`锛夊繀椤诲凡钀藉埌`frontend/src`銆?

### 2. 澶嶅埗 composable 涓庡瓙缁勪欢

```bash
cp -r fundmate-optimization/batch4/composables/ledger frontend/src/composables/

cp -r fundmate-optimization/batch4/views/asset/ledgers/components \
      frontend/src/views/asset/ledgers/
```

### 3. 鐢ㄥ３缁勪欢鏇挎崲鍘?detail.vue

```bash
mv frontend/src/views/asset/ledgers/detail.vue \
   frontend/src/views/asset/ledgers/detail.legacy.vue
cp fundmate-optimization/batch4/views/asset/ledgers/LedgerDetail.vue \
   frontend/src/views/asset/ledgers/detail.vue
```

> 璺敱琛?`asset.ts` 涓?ledger 璇︽儏鐨?component 鏃犻渶鏀癸紙浠嶆寚鍚?`detail.vue`锛夈€?
>
### 4. 鏈烘鎼繍鍘熼€昏緫

鎶婂師 `detail.vue` `<script setup>` 鍚勫潡**鎸変笅琛?*鎼叆瀵瑰簲 composable锛涙ā鏉挎媶鍒嗕负澹?+ 3 涓瓙缁勪欢銆?

## 鍘熸枃浠?鈫?鏈洰褰?瀵瑰簲鍏崇郴锛堟惉杩愭竻鍗曪級

| 鍘?detail.vue 涓殑鍧?| 鎼埌鍝噷 |
|---|---|
| `route.params.id` / `isUnclassified` / `targetAccountName` / `ledgerId` | `useLedgerDetail` |
| `ledgers` / `portfolioList` / `accountInfo` / `accountName` / `subTitle` / `cashLedgers` / `sameTypeLedgers` | `useLedgerDetail` |
| `loading` / `summaryData` + `loadSummary` | `useLedgerDetail` |
| `deleteDialogVisible` / `deletingAccount` / `openDeleteDialog` | `useLedgerDetail` |
| `handleAssign`锛堟湭鍒嗙被鎸囨淳锛?| `useLedgerDetail` |
| `showEditDialog` / `editForm` / `saving` / `openEditDialog` / `handleUpdate` | `useAccountEdit` |
| `holdingsList` / `holdingsPage` / `holdingsTotal` + `loadHoldings` / `openPositionDrawer` / `openMigrateDialog` / `handleMigrate` / `openBatchMigrateDialog` / `handleBatchMigrate` / `confirmDeletePosition` | `useHoldings` |
| `transactionsList` / `transactionsPage` / `transactionsTotal` + `loadTransactions` / `txnTypeLabel` / `getTxnTypeClass` / `openEditTxnDialog` / `handleUpdateTransaction` / `confirmDeleteTxn` | `useTransactions` |
| `chartRef` / `lineChartRef` / `chartInstance` / `lineChartInstance` / `renderPieChart` / `initLineChart` / `handleWindowResize` / `trendPeriod` + 鏃?onBeforeUnmount 脳2 | `useLedgerCharts`锛堚啋 `useEchartsLifecycle`锛?*鏁存鍒犻櫎鎵嬪啓鏍锋澘**锛?|
| 姒傝 3 鍗＄墖 | `AccountSummaryCards.vue` |
| 鎸佷粨琛?| `HoldingsTable.vue` |
| 浜ゆ槗琛?| `TransactionsTable.vue` |
| 椤舵爮 / 鍥捐〃 DOM / tabs / 鍚?dialog锛堢紪杈?杩佺Щ/浜ゆ槗缂栬緫锛? DeleteLedgerDialog / PositionTransactionsDrawer | `LedgerDetail.vue` 澹冲唴 |

## 鈿?闇€浣犳湰鍦板榻愮殑 TODO锛堜唬鐮佸唴宸叉爣娉級

1. **API 妯″潡璺緞**锛氭湰楠ㄦ灦浠?`@/api/ledger` 瀵煎叆锛坄getLedgers` / `getLedgerSummary` / `getLedgerPositions` /
   `getLedgerTransactions` / `updateLedger` / `updateLedgerPosition` / `deleteLedgerPosition` /
   `migrateLedgerPositions` / `updateLedgerTransaction` / `deleteLedgerTransaction` / `getPortfolios` / `updateAsset`锛夈€?   璇锋寜椤圭洰鐪熷疄鐨?api 鏂囦欢鍚嶈皟鏁达紙鍙兘鏄?`@/api/asset`鎴栨媶鍒嗘洿缁嗙殑妯″潡锛夈€?2. **`getLedgerPositions` / `getLedgerTransactions`杩斿洖缁撴瀯**锛氬凡鍋?`items/data/list` + `total`鍏煎锛屼互鐪熷疄涓哄噯銆?3. **`buildLineOption` 鏄姌绾垮崰浣?*锛氭敹鐩婅秼鍔挎帴鍙ｈ嫢灏辩华锛屽湪 `useLedgerCharts`鐨?`trendPeriod` watch 閲岄噸鎷夋暟鎹苟濉厖 `series.data`銆?4. **楗煎浘閰嶈壊**锛氱敤鎵规 1 鐨?`ECHARTS_COLOR`璋冭壊鏉匡紱濡傞渶鎸夎祫浜х被鍨嬭涔夌潃鑹插彲鏀?`buildPieOption`銆?5. **`keepAlive: true`**锛氳嫢璐︽埛璇︽儏璺敱瀹為檯鏈紑 keepAlive锛屼紶 true 涔熸棤瀹筹紙`onActivated` 涓嶄細瑙﹀彂锛夛紱鑻ュ凡寮€鍒欒嚜鍔ㄨ幏寰楀垏鍥為噸缁樸€?

## 楠岃瘉娓呭崟

- [ ] `pnpm type-check` 閫氳繃锛堝厛琛ヤ笂杩?API 绫诲瀷锛?- [ ] 杩涘叆璐︽埛璇︽儏锛氭瑙堝崱鐗?/ 楗煎浘 / 鎸佷粨琛?/ 浜ゆ槗琛ㄦ暟鎹樉绀烘甯?- [ ] **鍙嶅杩涘叆/閫€鍑鸿 keepAlive 椤?*锛欴evTools 涓?ECharts 瀹炰緥涓嶇疮绉紙姣忔搴旀槸銆屽厛 dispose 鍐?init銆嶏級锛屽浘琛ㄦ甯搁噸缁?- [ ] 鏀瑰彉绐楀彛澶у皬锛氶ゼ鍥?鎶樼嚎闅忓鍣?resize锛堟棤鎶ラ敊銆佹棤閲嶅鐩戝惉锛?- [ ] 鎸佷粨鍙樺寲锛堣縼绉?鍒犻櫎/鎸囨淳锛夊悗楗煎浘鑷姩閲嶇粯
- [ ] 椤堕儴 tab 鍒囨崲锛氭寔浠?浜ゆ槗鎳掑姞杞藉悇瑙﹀彂涓€娆?- [ ] 缂栬緫/鎵归噺杩佺Щ/鍒犻櫎璐︽埛/缂栬緫浜ゆ槗鍏ㄩ摼璺彲鐢?- [ ] 璁拌处鎴愬姛鍚庯紙mitt `refresh-ledger-data` 浜嬩欢锛夐〉闈㈣嚜鍔ㄥ埛鏂颁竴娆★紙usePageRefresh 闃叉姈楠岃瘉锛?
