# 鏁存敼璁″垝涓庝紭鍏堢骇锛堣儗鏅弬鑰冿級

> 鍚堝苟鑷€婂墠绔暣鏀?绉戝瀹炴柦鏂规銆嬩笌銆婂墠绔暣鏀规竻鍗曪細鎸夋敹鐩婃渶澶у寲鎺掑簭銆嬨€?> 杩欐槸鏁存敼鍓嶇殑**璁″垝涓?ROI 鎺掑簭**锛涘疄闄呰惤鍦拌 `docs/batches/` 鍚勬壒娆¤鏄庝笌鏍?`README.md`锛堟壒娆?0鈥? 宸插叏閮ㄥ嚭楠ㄦ灦锛夈€?
>
## 鎺掑簭鍘熷垯

鎸?鎶曞叆浜у嚭姣?脳 椋庨櫓"鍒嗘闃燂紝姣忔壒鐙珛浜や粯銆佺嫭绔嬮獙璇侊紱鎷嗗垎鏃堕『鎵嬩慨璇ユ枃浠跺凡鐭?bug锛堝弻閽╁瓙/姝讳唬鐮?纭紪鐮侊級锛沜omposable 涓€鏃﹁惤鍦板氨榧撳姳鍏ㄩ」鐩鐢ㄣ€?

## 鎵规鏄犲皠锛堣鍒?鈫?钀藉湴锛?

| 鎵规 | 鐩爣 | 鏍稿績鍔ㄤ綔 | ROI |
|---|---|---|---|
| 0 姝㈣ | 娓呮浠ｇ爜 + 淇硠婕?| 鍒?4 瀛ゅ効鏂囦欢锛涗慨 `ledgers/detail` 鍙?`onBeforeUnmount`銆佸垹 `getCSSColor` 鐨?`console.log` | 猸愨瓙猸愨瓙猸?|
| 1 鍏变韩鍩哄缓 | 琛ュ熀纭€璁炬柦 | 寤?`useEchartsLifecycle` + 涓婚/鑹插僵甯搁噺锛沗constants/` 鎸夊煙鎷?+ 澶栫Щ `EXCHANGE_RATES`锛沗utils/currency.ts`锛涚粺涓€ `composables`/`layout/hooks`锛涗慨 `usePageRefresh` 骞跺彂闃叉姈 | 猸愨瓙猸愨瓙猸?|
| 2 import 鍚戝 | 鎷嗘渶澶т欢 | 8 composable + 鐖跺３ + 8 缁勪欢锛堥厤缃┍鍔?6 绉嶆牸寮忥級 | 猸愨瓙猸愨瓙 |
| 3 watchlist | 鎷嗗ぇ浠?| 1 鏍?+ 5 鍔熻兘 composable + 5 缁勪欢 + 澹?| 猸愨瓙猸愨瓙 |
| 4 ledgers/detail | 鎷?+ 淇?| 1 鏍?+ 4 鍔熻兘 composable + 澹?+ 3 缁勪欢锛沗useLedgerCharts` 鎺ョ鍙屽浘琛紝淇硠婕?鏃ュ織/涓夊鍒锋柊 | 猸愨瓙猸愨瓙 |
| 5 inventory | 鎷?+ 鎶介厤缃?| 1 鏍?+ 2 鍔熻兘 composable + 1 鏍峰紡鍔╂墜 + 澹?+ 4 缁勪欢锛沗categories`/`assetTypes` 澶栫Щ | 猸愨瓙猸?|
| 6 welcome | 鎷?+ 鎺ュ浘琛?| 1 鏍?+ 1 浜や簰灞?+ 4 鍥捐〃鍔╂墜 + 澹?+ 7 鍗＄墖锛? 鍥捐〃鎺?`useEchartsLifecycle` | 猸愨瓙猸愨瓙 |
| 7 Buy/Sell 鍚堝苟 | 鍘婚噸 | 鍏变韩 `useTradeForm` + `BaseTradeForm(mode)`锛涘師涓ゆ枃浠跺彉钖勫３锛宍manual/index.vue` 闆舵敼鍔?| 猸愨瓙猸愨瓙 |
| 8 AssetPanorama | 鎷?+ 鎺ュ浘琛?| 1 鏍?+ 鐎戝竷鍥惧姪鎵?+ 澹?+ 5 鍗＄墖锛涚€戝竷鍥炬帴 `useEchartsLifecycle`锛堜慨 keepAlive 绌虹櫧锛?| 猸愨瓙猸愨瓙 |
| 9 portfolio/detail | 鎷嗭紙鏃犲浘琛級 | 1 鏍?+ 澹?+ 6 缁勪欢锛?*鍕樿**锛氬師璇垪涓?ECharts 娉勬紡鐐癸紝缁忛獙璇佹棤鍥捐〃 | 猸愨瓙猸?|

## 鍏抽敭鍘熷垯

- **鍏堣ˉ鍩哄缓锛屽啀鎷嗗ぇ浠?*锛歚useEchartsLifecycle` / 甯搁噺澶栫Щ / composable 涔犳儻鏄媶鍒嗙殑鏀偣銆?-**姣忔壒鐙珛浜や粯銆佺嫭绔嬮獙璇?*锛氶伩鍏嶄竴娆℃€уぇ鏀归毦浠ュ洖婊氥€?- **椤烘墜淇?bug**锛氭媶鍒嗘椂涓€骞跺鐞嗗弻鐢熷懡鍛ㄦ湡閽╁瓙銆佹浠ｇ爜銆佺‖缂栫爜鍊笺€?- **composable 鍏ㄩ」鐩鐢?*锛氶伩鍏嶅啀娆″唴鑱斻€?

## 鎵ц鏃堕棿绾匡紙璁炬兂锛?

鏌ヨ瘉瀛ゅ効 鈫?姝㈣+鍩哄缓 鈫?鎷嗘渶澶?3 涓紙import / ledgers / watchlist锛夆啋 鍘婚噸+鏀跺熬锛圔uy/Sell 鍚堝苟銆佸懡鍚嶄笌 path 淇銆乧omposables 缁熶竴锛夈€?
