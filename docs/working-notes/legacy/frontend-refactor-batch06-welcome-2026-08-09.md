# 鎵规 6 鈥?welcome/index.vue锛?9KB锛夋媶鍒?+ 鎺?useEchartsLifecycle

> 鎶?`frontend/src/views/welcome/index.vue`锛堝師 29KB锛夐噸鏋勪负
> 銆? 鍏变韩鏍?data) + 1 浜や簰灞?widget) + 4 鍥捐〃鍔╂墜 + 澹?+ 7 鍗＄墖缁勪欢銆嶃€?> 鏈壒娆?*涓庢壒娆?1 寮鸿仈鍔?*锛氬師椤甸潰鎵嬪啓 `echarts.init` 脳 4 + 鎵嬪啓 `window.resize` + `onUnmounted` dispose
> 鍏ㄩ儴鏀逛负鎵规 1 鐨?`useEchartsLifecycle`锛屽苟琛ヤ笂 keepAlive 椤靛師鍏堢己澶辩殑 `onActivated` 閲嶇粯銆?
>
## 鏂囦欢娓呭崟锛堟湰鐩綍 14 涓枃浠讹級

```
batch6/
鈹溾攢鈹€ composables/welcome/
鈹?  鈹溾攢鈹€ types.ts              # WelcomeData / WelcomeWidget / WelcomeContext / ChartHandle
鈹?  鈹溾攢鈹€ useWelcomeData.ts     # 鈽?鍏变韩鏍革細summary / portfolioXirr / trendMode / fetchSummary / fetchXirr / getCSSColor / 闈欐€佹暟鎹?鈹?  鈹溾攢鈹€ useWatchlistWidget.ts # 鑷€夊崱鐗囦氦浜掞細showAddWatchlistModal / key / ref / title / onSelect / onChanged
鈹?  鈹溾攢鈹€ useWelcomeCharts.ts   # 鈽?4 涓浘琛ㄥ姪鎵嬶細useDistributionChart / useTrendChart / useRiskChart / useMiniChart锛堝悇鎺?useEchartsLifecycle锛?鈹?  鈹溾攢鈹€ context.ts            # welcomeContextKey + useWelcomeContext()
鈹?  鈹斺攢鈹€ index.ts              # barrel 鍑哄彛
鈹斺攢鈹€ views/welcome/
    鈹溾攢鈹€ WelcomeIndex.vue      # 鈽?閲嶆瀯鍚庣殑澹崇粍浠讹紙鏇挎崲鍘?index.vue锛?    鈹斺攢鈹€ components/
        鈹溾攢鈹€ AssetSummaryCards.vue     # 瀹跺涵璧勪骇鐪嬫澘 + 璧勪骇鏋勬垚鍒嗗竷锛堥ゼ锛?        鈹溾攢鈹€ ReturnTrendCard.vue       # 鏀剁泭瓒嬪娍锛堢嚎锛? 鏈?瀛ｅ垏鎹?+ 椋庨櫓璇勫垎
        鈹溾攢鈹€ XirrCard.vue              # 骞村寲鏀剁泭杩借釜
        鈹溾攢鈹€ WatchlistCard.vue         # 鎸佷粨甯傚€兼渶澶ц祫浜э紙WatchlistWidget锛?        鈹溾攢鈹€ RiskHeatmapCard.vue       # 椋庨櫓鐑姏鍥撅紙鏌憋級
        鈹溾攢鈹€ FinancialBarometerCard.vue# 璐㈠姟鏅撮洦琛?+ 璧勪骇鍙樺姩杩蜂綘鏌?        鈹斺攢鈹€ MentalAccountsCard.vue    # 蹇冪悊璐︽埛杩涘害鏉?```

## 鈽?ECharts 鐢熷懡鍛ㄦ湡淇锛堟牳蹇冩敹鐩婏級

鍘?`index.vue` 鐨勫浘琛ㄧ鐞嗭紙鏍蜂緥锛夛細

```ts
// 鉂?鏃э細鎵嬪啓 init / resize / dispose锛屼笖浠?onMounted 娓叉煋
const charts: echarts.ECharts[] = [];
const initCharts = () => {
  charts.push(echarts.init(distributionChartRef.value!).setOption(pieOption));
  charts.push(echarts.init(trendChartRef.value!).setOption(lineOption));
  // ... 4 涓?};
const handleResize = () => charts.forEach((c) => c.resize());
onMounted(() => {
  fetchSummary().then(() => nextTick(initCharts));
  fetchXirr();
  window.addEventListener("resize", handleResize);
});
onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  charts.forEach((c) => c.dispose());
});
// 鈿?缂哄け onActivated 鈫?keepAlive 椤靛垏鍥炲墠鍙板浘琛ㄤ笉閲嶇粯锛堢┖鐧?涓嶆洿鏂帮級
```

鏀逛负锛堜互 `AssetSummaryCards.vue` 涓轰緥锛屽叾浣?3 涓浘琛ㄥ姪鎵嬪悓鏋勶級锛?

```ts
// 鉁?鏂帮細浜ょ粰鎵规 1 鐨?useEchartsLifecycle 缁熶竴鎺ョ
const { chartRef } = useDistributionChart(data);
// useDistributionChart 鍐呴儴锛?//   useEchartsLifecycle([chartRef], [(el) => { const c = echarts.init(el); c.setOption(build()); return c; }],
//     { keepAlive: true, autoRenderOnMount: false });
//   watch(() => data.summary.value, async (s) => { if (s) { await nextTick(); render(); } });
// 鈫?鑷姩澶勭悊 resize / dispose / onActivated 閲嶇粯锛涙暟鎹埌浣嶆墠娓叉煋
```

淇鐐瑰鐓э細

| 闂 | 鏃т唬鐮?| 鏂颁唬鐮?|
|---|---|---|
| 閲嶅 `echarts.init` 鏍锋澘 | 4 澶勬墜鍐?| 姣忎釜鍥捐〃鍔╂墜 1 澶?builder |
| 鎵嬪啓 `window.resize` | `addEventListener` + `handleResize` | `useEchartsLifecycle` 鍐呴儴缁熶竴澶勭悊 |
| 閲嶅 `onUnmounted` dispose | 鎵嬪啓閬嶅巻 dispose | `useEchartsLifecycle` 鍐呴儴缁熶竴澶勭悊 |
| keepAlive 缂?`onActivated` | 鉂?缂哄け | 鉁?`keepAlive: true` 鑷姩 `onActivated` 閲嶇粯 |
| 寮傛鏁版嵁绔炴€?| `fetchSummary().then(nextTick(initCharts))` 涓€娆℃€?| `autoRenderOnMount:false` + `watch(summary)` 鑷姩閲嶆覆鏌?|

## 鏋舵瀯瑕佺偣

- 澹?`WelcomeIndex` `provide(welcomeContextKey, { data, widget })`锛涘崱鐗囩粍浠?`useWelcomeContext()` 娉ㄥ叆銆?- **鍥捐〃 ref 涓嶈繘涓婁笅鏂?*锛氭瘡涓浘琛ㄥ崱鐗囧湪鑷繁鐨?setup 鍐呰皟鐢?`useXxxChart(data)` 鎷垮埌 `chartRef`锛?  鐢?`<div ref="chartRef">`锛堝瓧绗︿覆 ref锛夌粦瀹氣€斺€旇閬裤€岃法缁勪欢浼?Ref 琚ā鏉胯В鍖呫€嶇殑鍧戙€?- 鍔熻兘灞傞€氳繃鍙傛暟娉ㄥ叆 `data`锛堟牳锛夛紝鏃犲惊鐜緷璧栥€?

## 钀藉湴姝ラ

```bash
# 1. 澶嶅埗 composable
cp -r fundmate-optimization/batch6/composables/welcome frontend/src/composables/

# 2. 澶嶅埗澹?+ 鍗＄墖缁勪欢
cp fundmate-optimization/batch6/views/welcome/WelcomeIndex.vue \
   frontend/src/views/welcome/index.vue          # 瑕嗙洊鍘熸枃浠讹紙鍏堝浠斤級
mkdir -p frontend/src/views/welcome/components
cp -r fundmate-optimization/batch6/views/welcome/components/* \
   frontend/src/views/welcome/components/

# 3. 鏈烘鎼繍锛氭妸鍘?index.vue <script setup> 鍚勫潡鎸変笅琛ㄦ惉鍏ュ搴旀枃浠?```

## 鍘熸枃浠?鈫?鏈洰褰?瀵瑰簲鍏崇郴锛堟惉杩愭竻鍗曪級

| 鍘?index.vue 涓殑鍧?| 鎼埌鍝噷 |
|---|---|
| `summary` / `portfolioXirr` / `trendMode` + `fetchSummary` / `fetchXirr` | `useWelcomeData` |
| `getCSSColor` | `useWelcomeData` |
| `financialMetrics` / `mentalAccounts` 鍐呰仈闈欐€佹暟缁?| `useWelcomeData`锛堜繚鎸佹暟缁勫父閲忥級 |
| `showAddWatchlistModal` / `watchlistWidgetKey` / `watchlistWidgetRef` / `watchlistTitle` / `onWatchlistSelect` / `onWatchlistChanged` | `useWatchlistWidget` |
| `distributionChartRef`/`trendChartRef`/`riskHeatmapRef`/`miniAssetChartRef` + `initCharts`/`handleResize` + 4 涓?`setOption({...})` | 鎷嗗埌 4 涓?`useXxxChart` 鍔╂墜锛坥ption 閰嶇疆鎼繘鍚勮嚜 `build()`锛?|
| 椤堕儴娆㈣繋璇?/ 鏁翠綋鏍呮牸甯冨眬 / `AddToWatchlistModal` 寮圭獥 | `WelcomeIndex.vue` 澹?|
| 瀹跺涵璧勪骇鐪嬫澘 + 楗煎浘 | `AssetSummaryCards.vue` |
| 鏀剁泭瓒嬪娍 + 鏈?瀛ｅ垏鎹?+ 椋庨櫓璇勫垎 | `ReturnTrendCard.vue` |
| 骞村寲鏀剁泭杩借釜 | `XirrCard.vue` |
| 鎸佷粨甯傚€兼渶澶ц祫浜э紙WatchlistWidget锛?| `WatchlistCard.vue` |
| 椋庨櫓鐑姏鍥?| `RiskHeatmapCard.vue` |
| 璐㈠姟鏅撮洦琛?+ 杩蜂綘鏌?| `FinancialBarometerCard.vue` |
| 蹇冪悊璐︽埛 | `MentalAccountsCard.vue` |

## 鈿?闇€浣犳湰鍦板榻愮殑 TODO锛堜唬鐮佸唴宸叉爣娉級

1. **`SummaryData` / `PortfolioXirr` 瀛楁鍚?*锛氬崱鐗囬噷鍐欑殑 `total_assets`/`total_profit`/`monthly_change`/`xirr`/`current_value`/`total_invested`
   鏄崰浣嶏紝璇蜂互 `@/api/types` 鐪熷疄缁撴瀯涓哄噯锛堟敼妯℃澘缁戝畾鍗冲彲锛夈€?2. **4 涓浘琛ㄧ殑 `build()` option**锛氶鏋剁暀绌?`{}`锛岄渶鎶婂師 `initCharts` 閲?4 娈?`setOption({...})` 閰嶇疆鎼叆瀵瑰簲鍔╂墜锛?   閰嶈壊鏀瑰紩鐢ㄦ壒娆?1 鐨?`ECHARTS_COLOR`锛屽垹纭紪鐮佹定绾㈣穼缁裤€?3. **`AddToWatchlistModal` 鐨?v-model prop**锛氶鏋剁敤 `v-model`锛岃嫢缁勪欢鏄?`visible` prop 璇锋敼涓?`v-model:visible`锛?   鎴愬姛浜嬩欢鐢?`@added`锛岃嫢鐪熷疄浜嬩欢鍚嶄笉鍚岋紙濡?`@success`锛夎璋冩暣銆?4. **`financialMetrics` / `mentalAccounts` 闈欐€佹暟鎹?*锛氭妸鍘熸暟缁勫師鏍锋惉鍏?`useWelcomeData`銆?5. **`onWatchlistSelect` 閫昏緫**锛氶鏋舵湭瀹炵幇锛屾惉鍘熼€昏緫銆?
## 楠岃瘉娓呭崟

- [ ] `pnpm type-check` 閫氳繃锛堝厛琛ヤ笂杩板瓧娈?绫诲瀷锛?- [ ] 4 涓浘琛ㄦ甯告覆鏌擄紝閰嶈壊鏉ヨ嚜 `ECHARTS_COLOR`
- [ ] 鏈?瀛ｅ垏鎹㈠悗瓒嬪娍鍥鹃噸缁?- [ ] keepAlive 鍒囧洖鍓嶅彴锛?welcome锛夊浘琛ㄩ噸缁橈紝鏃犲疄渚嬬疮绉€佹棤 console 鎶ラ敊
- [ ] 绐楀彛 resize 鍥捐〃鑷€傚簲
- [ ] 鍔犺嚜閫夊脊绐椾繚瀛樺悗鍒楄〃鍒锋柊锛坘ey 鑷锛?
