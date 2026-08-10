# 鎵规 9 鈥?portfolio/detail.vue 缁勪欢鎷嗗垎锛堥潪 ECharts锛?
>
> 鍘熸枃浠讹細`frontend/src/views/asset/portfolio/detail.vue`锛堢害 18.9KB锛屽崟浣擄級
> 鐩爣锛氭媶涓恒€屽叡浜牳 composable + 澶栧３ + 5 鍗＄墖 + 1 缂栬緫寮圭獥銆嶏紝鐘舵€佷笅娌夈€佺粍浠跺鐢ㄣ€?
>
## 涓€銆侀噸瑕佹洿姝ｏ紙瀵规壒娆?1 鐨勫嫎璇級

鎵规 1 鐨勬敞閲婃浘鎶?`portfolio/detail` 鍒椾负 **ECharts 娉勬紡鐐?*涔嬩竴銆傜粡瀵规簮鐮侀€愯鏍稿锛?
> `portfolio/detail.vue` **涓嶅惈浠讳綍 ECharts 瀹炰緥**銆傚叾妯℃澘浠呯敱 Element Plus
> 锛坋l-card / el-table / el-dialog / el-form 鈥︼級涓庡叏灞€鍥炬爣缁勪欢 `IconifyIconOffline` 鏋勬垚锛?> XIRR 鏁版嵁閫氳繃 `http.request("get", "/api/performance/xirr/", ...)` 鐩村彇銆?
鍥犳鏈壒娆?*涓嶅仛 ECharts 鐢熷懡鍛ㄦ湡鏀舵暃**锛堟棤鍥惧彲鎺ワ級锛屼粎鍋氱粍浠舵媶鍒嗏€斺€斾笌 ledgers/detail
锛堟壒娆?4锛夌粨鏋勪竴鑷达紝浣嗙渷鍘?`useXxxCharts` 涓€灞傘€傛壒娆?1 鐨?`useEchartsLifecycle` 瑕嗙洊娓呭崟涓簲
灏?`portfolio/detail` 鍓旈櫎锛堝凡鍦ㄦ牴 README銆孍Charts 鏀舵暃瑕嗙洊銆嶆鏇存锛夈€?

## 浜屻€佹枃浠舵竻鍗曪紙1:1 鏄犲皠锛?

```
batch9/
鈹溾攢鈹€ composables/portfolio/
鈹?  鈹溾攢鈹€ types.ts                  # PortfolioDetailData / PortfolioDetailContext / EditForm / SortOrder
鈹?  鈹溾攢鈹€ usePortfolioDetail.ts     # 鈽?鍏变韩鏍革細ref/reactive/2 computed + 鍔犺浇/缂栬緫/鍒犻櫎/鎺掑簭/鍒嗛〉
鈹?  鈹溾攢鈹€ context.ts                # portfolioDetailContextKey + usePortfolioDetailContext()
鈹?  鈹斺攢鈹€ index.ts                  # 缁熶竴鍑哄彛
鈹斺攢鈹€ views/asset/portfolio/
    鈹溾攢鈹€ PortfolioDetailIndex.vue         # 澶栧３锛歱rovide + onMounted(refreshAll) + 鎷艰
    鈹斺攢鈹€ components/
        鈹溾攢鈹€ PortfolioHeader.vue          # 杩斿洖 + 缁勫悎鍚?鐢ㄩ€?+ 缂栬緫/鍒犻櫎(popconfirm)
        鈹溾攢鈹€ PortfolioInfoCards.vue       # 鍏宠仈璐︽埛/鐩爣鏀剁泭鐜?鍩哄噯鎸囨暟
        鈹溾攢鈹€ XirrCard.vue                 # 缁勫悎鏀剁泭(XIRR) + 鍒锋柊
        鈹溾攢鈹€ HoldingsTable.vue            # 鎸佷粨鏄庣粏琛?+ sort + 鍒嗛〉
        鈹溾攢鈹€ LinkedLedgersCard.vue        # 鍏宠仈璐︽埛琛?+ 鏌ョ湅
        鈹斺攢鈹€ EditPortfolioDialog.vue      # 缂栬緫寮圭獥锛堝惈鍏宠仈璐︽埛澶氶€夛級
```

## 涓夈€佹媶鍒嗗鐓?

| 鍘?detail.vue 鍖哄潡 | 鐜板綊灞?|
| --- | --- |
| `loading` 鍔犺浇鎬?| 澶栧３ `v-if="loading"` |
| 杩斿洖鎸夐挳 + header锛坣ame/purpose/edit/delete锛?| `PortfolioHeader.vue` |
| 鍩虹淇℃伅涓夊崱锛堝叧鑱旇处鎴?鐩爣鏀剁泭鐜?鍩哄噯鎸囨暟锛?| `PortfolioInfoCards.vue` |
| XIRR 鍗＄墖锛堝埛鏂?骞村寲/甯傚€?鎶曞叆/鏀剁泭锛?| `XirrCard.vue` |
| 鎸佷粨鏄庣粏琛紙sort + 鍒嗛〉锛?| `HoldingsTable.vue` |
| 鍏宠仈璐︽埛琛紙鏌ョ湅锛?| `LinkedLedgersCard.vue` |
| 缂栬緫寮圭獥 + 鍏宠仈璐︽埛澶氶€?| `EditPortfolioDialog.vue` |
| 鍏ㄩ儴 ref/computed/鏂规硶 | `usePortfolioDetail.ts`锛堝叡浜牳锛?|

## 鍥涖€佹灦鏋勮鐐癸紙涓庢壒娆?2鈥? 涓€鑷达級

- 鍏变韩鏍?`usePortfolioDetail()` 鎸佹湁鍏ㄩ儴鐘舵€佷笌琛屼负锛涘３缁勪欢 `provide(portfolioDetailContextKey, { data })`銆?- 6 涓瓙缁勪欢鍧?`usePortfolioDetailContext()` 娉ㄥ叆锛屾棤 props 閫忎紶銆?- 椤跺眰 ref 鍦ㄧ粍浠跺唴瑙ｆ瀯浠ヤ究妯℃澘鑷姩瑙ｅ寘锛坄v-model` 鐩存帴缁戝畾锛夈€?- 璺敱杈撳叆鏉ヨ嚜 `route.params.id`锛堝師缁勪欢鍗虫棤 props/emits锛夛紝鎷嗗垎鍚庝笉鍙樸€?

## 浜斻€佽縼绉荤姸鎬?

| 椤?| 鐘舵€?| 璇存槑 |
| --- | --- | --- |
| 鏂囦欢楠ㄦ灦 + 绫诲瀷 | 鉁?| 鍏ㄥ氨缁?|
| 鍏变韩鏍搁€昏緫 | 鉁?| ref/computed/鏂规硶宸叉寜鍘熺鍚嶆惉杩愶紱fetch 鏁扮粍褰掍竴鍖栦繚鐣?`?.data ?? res` 鍏滃簳 |
| XIRR 鍙栨暟 | 鈿狅笍 | 浠嶈蛋 `http.request`锛汿ODO 杩佺Щ涓?typed api锛堝 `getPortfolioXirr`锛?|
| 瀛愮粍浠跺瓧娈?| 鈿狅笍 | 鍗＄墖鍐呭瓧娈垫寜甯歌缁勫悎瀛楁鍛藉悕锛坣ame/symbol/market_value/pnl/weight 绛夛級锛屽疄闄呭瓧娈靛悕浠ユ帴鍙ｄ负鍑?|
| esbuild 璇硶鏍￠獙 | 鉁?| 鍏ㄩ儴 `.ts` / `.vue` 閫氳繃 |

## 鍏€佹帴鍏ユ柟寮?

1. 璺敱鎸囧悜 `PortfolioDetailIndex.vue`锛?2. 鍒犻櫎鏃?`portfolio/detail.vue`銆?
椤甸潰鏃犲澶?props/emits锛岃矾鐢辫皟鐢ㄦ柟寮忎笉鍙橈紱鍏ㄥ眬缁勪欢 `IconifyIconOffline` / `MoneyDisplay` /
`RiseFallText` 鍘熸牱寮曠敤锛屾棤闇€鏂板娉ㄥ唽銆?
