# 钀藉湴鎸囧崡锛堟寜鎵规搴旂敤锛?
>
> 鎶?`batchN/` 涓嬬殑浜や粯鏂囦欢钀藉湴鍒颁綘鏈湴 `fundmate/frontend` 浠撳簱鐨勫叿浣撴楠ゃ€?> 姣忔閮藉彲鐙珛浜や粯銆佺嫭绔嬮獙璇侊紱鍏堝熀寤哄悗鎷嗗ぇ浠躲€?
>
## 鎬昏

| 椤哄簭 | 鎵规 | 钀藉湴鐐癸紙`frontend/src/`锛?| 鍏抽敭鍔ㄤ綔 |
|---|---|---|---|
| 1 | 0 姝㈣ | 浠撳簱鏍癸紙鑴氭湰灏卞湴杩愯锛?| 鍒犲鍎挎枃浠讹紱淇?`ledgers/detail` 鍙?`onBeforeUnmount` + `console.log` |
| 2 | 1 鍏变韩鍩哄缓 | `composables/echarts/`銆乣constants/`銆乣utils/`銆乣composables/usePageRefresh.ts` | 寤?`useEchartsLifecycle` + 涓婚锛涘绉绘眹鐜?璐у竵锛涗慨 `usePageRefresh` 闃叉姈 |
| 3 | 2 import 鍚戝 | `composables/import/`銆乣views/asset/investment/import/` | 8 composable + 鐖跺３ + 8 缁勪欢 |
| 4 | 3 watchlist | `composables/watchlist/`銆乣views/asset/watchlist/` | 1 鏍?+ 5 鍔熻兘 composable + 5 缁勪欢 + 澹?|
| 5 | 4 ledgers/detail | `composables/ledger/`銆乣views/asset/ledgers/` | 1 鏍?+ 4 鍔熻兘 composable + 澹?+ 3 缁勪欢锛涘弻鍥捐〃鎺?`useEchartsLifecycle` |
| 6 | 5 inventory | `composables/inventory/`銆乣views/asset/inventory/` | 1 鏍?+ 2 鍔熻兘 composable + 1 鏍峰紡鍔╂墜 + 澹?+ 4 缁勪欢锛涢厤缃绉?|
| 7 | 6 welcome | `composables/welcome/`銆乣views/welcome/` | 1 鏍?+ 1 浜や簰灞?+ 4 鍥捐〃鍔╂墜 + 澹?+ 7 鍗＄墖锛? 鍥捐〃鎺?`useEchartsLifecycle` |
| 8 | 7 Buy/Sell | `composables/trade/`銆乣components/QuickEntry/` | 鍏变韩 `useTradeForm` + `BaseTradeForm(mode)`锛涘師涓ゆ枃浠跺彉钖勫３ |
| 9 | 8 AssetPanorama | `composables/panorama/`銆乣views/asset/panorama/` | 1 鏍?+ 鐎戝竷鍥惧姪鎵?+ 澹?+ 5 鍗＄墖锛涚€戝竷鍥炬帴 `useEchartsLifecycle` |
| 10 | 9 portfolio/detail | `composables/portfolio/`銆乣views/asset/portfolio/` | 1 鏍?+ 澹?+ 6 缁勪欢锛堟棤 ECharts锛屽凡鍕樿锛?|

## 閫氱敤姝ラ锛堟瘡涓壒娆★級

1. **澶嶅埗鏂板鏂囦欢**锛歚batchN/composables/*`鈫?`frontend/src/composables/*`锛沗batchN/views/*` 鈫?`frontend/src/views/*`锛堢洰褰曞悕宸插榻愶紝澶嶅埗鍗宠惤浣嶏級銆?2. **鎺ュ熀寤猴紙鎵规 鈮?锛?*锛氳嫢椤甸潰鍚?ECharts锛屾妸鍘熸墜鍐?`echarts.init`/`resize`/`dispose` 鏀逛负璋冪敤 `useEchartsLifecycle`锛堣瑙?`docs/guides/ECharts鏀舵暃璇存槑.md`锛夈€?3. **鏈烘鎼繍鍘熼€昏緫**锛氭墦寮€鍘?God Component锛屾妸 `<script setup>` 閲屽搴旂殑鐘舵€?鍑芥暟鍧楁惉鍏ラ鏋堕噷鍚屽悕 composable锛涘垹闄ゅ師鏂囦欢閲岃鎶借蛋鐨勫潡銆?4. **鎺ョ嚎**锛氬３缁勪欢宸?`provide` 涓婁笅鏂囷紝瀛愮粍浠?`useXxxContext()` 娑堣垂锛涜矾鐢辨寚鍚戞柊澹筹紝鍒犻櫎鏃у崟浣撴枃浠躲€?5. **鏍￠獙**锛歚pnpm type-check` + `pnpm build`锛涢噸鐐圭湅 keepAlive 椤靛垏鍥炲墠鍙板浘琛ㄦ槸鍚﹂噸缁樸€丏evTools 鏃?ECharts 瀹炰緥绱Н銆?

## 娉ㄦ剰浜嬮」

- **涓嶈瑕嗙洊鐜版湁鏂囦欢**锛氭湰浜や粯鐗╁潎涓烘柊澧烇紱鍘?God Component 鍦ㄤ綘鏈湴鍒犳棫鏂囦欢锛屼笉鍦ㄦ湰鍖呭唴鍒犻櫎銆?- **TODO 鏍囪 = 寰呮惉杩愮偣**锛氶鏋堕噷 `// TODO` 澶勫嵆闇€濉叆鍘熼€昏緫鐨勪綅缃紙濡?`usePanoramaData` 鐨?6 涓?computed銆乣useWaterfallChart`鐨?`start/changes`娲剧敓锛夈€?- **鍏ㄥ眬缁勪欢**锛歚MoneyDisplay`/`SankeyChart`/`RiseFallText`/`IconifyIconOffline` 涓洪」鐩叏灞€娉ㄥ唽锛岄鏋剁洿鎺ュ紩鐢紝鏃犻渶鏂板娉ㄥ唽銆?- 鎵规闂存棤寮鸿€﹀悎锛氬彲鍗曠嫭鎸戞煇涓€鎵规钀藉湴锛堝鍙仛鎵规 8 鐨勭€戝竷鍥炬敹鏁涳級銆?
