# 鎵规 8 鈥?璧勪骇鍏ㄦ櫙 AssetPanorama 鎷嗗垎 + 鐎戝竷鍥炬帴鍏?useEchartsLifecycle

> 鍘熸枃浠讹細`frontend/src/views/asset/AssetPanorama.vue`锛堝崟浣?God Component锛?> 鐩爣锛氭媶涓恒€屽叡浜牳 composable + 澶栧３ + 5 寮犲崱鐗囥€嶏紝骞舵妸鍞竴鐨?ECharts锛堣祫浜х€戝竷鍥撅級鎺ュ叆鎵规 1 鐨?`useEchartsLifecycle`銆?
>
## 涓€銆佹敼鍔ㄦ瑙?

| 缁村害 | 鍘?`AssetPanorama.vue` | 鏈壒娆?|
| --- | --- | --- |
| 缁撴瀯 | 鍗曚綋 SFC锛堟暟鎹?+ 6 computed + 鐎戝竷鍥?init + 妯℃澘鍏ㄥ湪涓€璧凤級 | `usePanoramaData`锛堟暟鎹眰锛? `useWaterfallChart`锛堝浘琛ㄥ姪鎵嬶級+ `AssetPanoramaIndex`锛堝澹筹級+ 5 寮犲崱鐗?|
| 鐘舵€佸叡浜?| 鍏ㄥ湪 `setup` 鍐咃紝鏃犳硶澶嶇敤 | `provide(panoramaContextKey, { data })` / `usePanoramaContext()` |
| 鐎戝竷鍥?| 鎵嬪啓 `echarts.init`銆?*鏃?resize 鐩戝惉 / 鏃?onUnmounted dispose / 鏃?onActivated** | `useEchartsLifecycle(..., { keepAlive: true })` 缁熶竴鎺ョ |
| 閰嶈壊 | 鍐呰仈 `getCSSColor`锛堥噸澶嶅疄鐜?+ 纭紪鐮?CSS 鍙橀噺鍚嶏級 | 鏀圭敤鎵规 1 `getCssVar`锛堣涔夊寲銆佸彲鏆楅粦鍒囨崲锛?|
| 瀛愮粍浠?| 妯℃澘鍐呯敤 `<SankeyChart>` / `<MoneyDisplay>` / `<RiskFallText>` | 鍘熸牱淇濈暀锛堝叏灞€娉ㄥ唽缁勪欢锛?|

## 浜屻€佹枃浠舵竻鍗曪紙1:1 鏄犲皠锛?

```
batch8/
鈹溾攢鈹€ composables/panorama/
鈹?  鈹溾攢鈹€ types.ts              # PanoramaData / PanoramaContext / SankeyDisplayMode / BalanceTab
鈹?  鈹溾攢鈹€ usePanoramaData.ts    # 鍏变韩鏍革細allPositions/allAssets/ledgers/total* / sankey* / balanceTab
鈹?  鈹?                        #        / detailView + fetchData + 6 涓?computed + getCSSColor 绛?鈹?  鈹溾攢鈹€ useWaterfallChart.ts  # 鈽?鐎戝竷鍥炬帴鍏?useEchartsLifecycle锛坘eepAlive 閲嶇粯锛?鈹?  鈹溾攢鈹€ context.ts            # panoramaContextKey + usePanoramaContext()
鈹?  鈹斺攢鈹€ index.ts              # 缁熶竴鍑哄彛
鈹斺攢鈹€ views/asset/panorama/
    鈹溾攢鈹€ AssetPanoramaIndex.vue        # 澶栧３锛歱rovide + onMounted(fetchData) + 鎷艰 5 鍗?    鈹斺攢鈹€ components/
        鈹溾攢鈹€ SummaryCards.vue          # 鎬昏祫浜?鎬昏礋鍊?鎬荤泩浜?+ 鍒锋柊锛堝師椤堕儴 3脳 MoneyDisplay锛?        鈹溾攢鈹€ SankeyCard.vue            # 璧勯噾娴佸悜锛?SankeyChart> + sankeyDisplayMode 鍒囨崲
        鈹溾攢鈹€ WaterfallCard.vue         # 璧勪骇鐎戝竷锛歶seWaterfallChart(data) 鎸佹湁 chartRef
        鈹溾攢鈹€ BalanceCard.vue           # 璧勪骇璐熷€猴細balanceTab + asset/liabilityBalanceRows 琛?        鈹斺攢鈹€ DetailCard.vue            # 璧勪骇鏄庣粏锛歞etailView + currentDetailGroups 鍒楄〃
```

## 涓夈€丒Charts 鐢熷懡鍛ㄦ湡淇锛堟牳蹇冩敹鐩婏級

鍘熺€戝竷鍥撅細鍦?`fetchData()` 鐨?`finally` 閲屾墜鍔?`initWaterfallChart()`锛屼粎 `if (waterfallChart) waterfallChart.dispose()`銆?缂哄け椤癸細

- 鏃?`window.resize` 鐩戝惉 鈫?绐楀彛缂╂斁鍥捐〃涓嶈嚜閫傚簲锛?- 鏃?`onBeforeUnmount` dispose 鈫?绂诲紑椤甸潰瀹炰緥娉勬紡锛?- `/panorama` 璺敱鏍囪 `keepAlive` 鍗?*鏃?`onActivated`** 鈫?浠庡叾浠栭〉闈㈠垏鍥炲墠鍙板浘琛ㄧ┖鐧?涓嶆洿鏂般€?
鏀归€犲悗锛坄useWaterfallChart`锛夛細

```ts
const { render } = useEchartsLifecycle(
  [chartRef],
  [(el) => { const c = echarts.init(el); c.setOption(build()); return c; }],
  { keepAlive: true, autoRenderOnMount: false },   // keepAlive 椤靛繀椤?true
);

// 鏁版嵁鍒颁綅鍚庨噸缁橈紙鍘熷畧鍗細allPositions 涓虹┖璺宠繃锛?watch(
  [() => data.allPositions.value.length, () => data.totalAssets.value,
   () => data.totalLiabilities.value, () => data.totalPnl.value],
  async () => {
    if (data.allPositions.value.length > 0 || data.totalAssets.value > 0) {
      await nextTick();
      render();
    }
  },
);
```

`useEchartsLifecycle` 鍐呴儴缁熶竴澶勭悊 `onMounted` / `onActivated` 閲嶇粯銆乣resize`鐩戝惉銆乣onBeforeUnmount` dispose銆?

## 鍥涖€佽縼绉荤姸鎬?

| 椤?| 鐘舵€?| 璇存槑 |
| --- | --- | --- |
| 鏂囦欢楠ㄦ灦 + 绫诲瀷 | 鉁?| `types.ts` / `context.ts` / `index.ts` / 澶栧３ / 5 鍗?鍏ㄩ儴灏辩华 |
| 鐎戝竷鍥炬帴 `useEchartsLifecycle` | 鉁?| 缁撴瀯瀹屾暣锛沗build()` 鏆傜敤鍘?*纭紪鐮佺ず渚?* start/changes |
| fetchData + 5 API 骞惰 | 鈿狅笍 | 宸叉惌 `Promise.all` 楠ㄦ灦锛屾暟缁勫綊涓€鍖栧緟琛ワ紙瑙?`usePanoramaData.ts` TODO锛?|
| 6 涓?computed 閫昏緫 | 鈿狅笍 | `assetBalanceRows` / `liabilityBalanceRows` / `type` / `account` / `allocation` / `currentDetailGroups` 鏆傝繑鍥?`[]`锛岄渶鎼繍鍘熸槧灏?|
| 鐎戝竷鍥炬暟鎹淳鐢?| 鈿狅笍 | TODO锛氫粠 `assetBalanceRows` / `totalLiabilities` / `totalPnl` 璁＄畻 start/changes锛屾浛鎹㈢‖缂栫爜 |
| EXCHANGE_RATES | 鈿狅笍 | 鐜颁负鍐呰仈甯搁噺锛屽缓璁敼寮曟壒娆?1 `@/constants/exchangeRates` |
| esbuild 璇硶鏍￠獙 | 鉁?| 鍏ㄩ儴 `.ts` / `.vue` 閫氳繃锛堣鏍?README銆屾牎楠屻€嶏級 |

## 浜斻€佹帴鍏ユ柟寮?

鏇挎崲鍘熷崟浣撴枃浠跺彧闇€涓ゆ锛?

1. 璺敱 `meta.keepAlive` 椤甸潰鎸囧悜 `AssetPanoramaIndex.vue`锛?2. 鍒犻櫎鏃?`AssetPanorama.vue`銆?
澶栧３宸?`provide(panoramaContextKey, { data })`锛屾墍鏈夊崱鐗囬€氳繃 `usePanoramaContext()` 娑堣垂锛屾棤闇€ props 閫忎紶銆?

## 鍏€侀浂琛屼负鐮村潖鎬?

- 椤甸潰鏃?`props` / `emits`锛堝師缁勪欢鍗虫棤瀵瑰鎺ュ彛锛夛紝鎷嗗崱鍚庤矾鐢辫皟鐢ㄦ柟寮忎笉鍙橈紱
- 鍏ㄥ眬缁勪欢 `<SankeyChart>` / `<MoneyDisplay>` / `<RiseFallText>` 鍘熸牱寮曠敤锛屾棤闇€鏂板娉ㄥ唽銆?
