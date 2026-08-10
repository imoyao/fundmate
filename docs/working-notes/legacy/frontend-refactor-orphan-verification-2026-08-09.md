# 瀛ゅ効鏂囦欢寮曠敤鏌ヨ瘉鎶ュ憡

> 鏌ヨ瘉瀵硅薄锛歚frontend/src/views/asset/` 涓?4 涓湪璺敱琛ㄤ腑鎵句笉鍒版寕杞界偣鐨勬枃浠?> 鏌ヨ瘉鏃ユ湡锛?026-07-17
> 鏌ヨ瘉鏂规硶锛氳矾鐢辫〃浜ゅ弶姣斿 + 鍚庣鍔ㄦ€佽矾鐢辨満鍒舵牳鏌?+ 鏂囦欢婧愮爜瀹氭€у垎鏋?
>
## 缁撹鍏堣

**4 涓枃浠跺叏閮ㄧ‘璁や负瀛ゅ効锛堟浠ｇ爜锛夛紝寤鸿鐩存帴鍒犻櫎銆?* 鍚堣 ~73KB锛屽垹闄ゅ悗鍚屾椂娓呮帀涓€鎵瑰凡鐭?bug 鍜?mock 鏁版嵁銆?
| 鏂囦欢 | 澶у皬 | 鎬ц川 | 澶勭疆 |
|---|---|---|---|
| `asset/Overview.vue` | 40.5KB | 鏃х増 `AssetPanorama` 鍚屽悕缁勪欢锛岃鏂扮増 `AssetPanorama.vue` 鍙栦唬鍚庢湭鍒?| 鉂?鍒犻櫎 |
| `asset/AssetOverview.vue` | 18.2KB | 鏃╂湡绾?mock 鍘熷瀷锛屽叏纭紪鐮佹暟鎹紝鏃?API 璋冪敤 | 鉂?鍒犻櫎 |
| `asset/AssetDetail.vue` | 13.9KB | 鏃╂湡绾?mock 鍘熷瀷锛屽師鐢?HTML 鏍囩 + 纭紪鐮佹紨绀烘暟鎹?| 鉂?鍒犻櫎 |
| `asset/Assets.vue` | 373B | 搴熷純鑴氭墜鏋讹紝寮曠敤 4 涓笉瀛樺湪鐨勭粍浠讹紝`<script setup>` 绌哄３ | 鉂?鍒犻櫎 |

---

## 鏌ヨ瘉璇佹嵁閾?

### 1. 璺敱琛ㄦ牳鏌ワ細鏃犳寕杞界偣

閫愪竴鏍稿浜嗗叏閮?4 涓矾鐢辨ā鍧楃殑 `component` 寮曠敤锛?
| 璺敱妯″潡 | 鎸傝浇鐨?asset/ 涓嬫枃浠?| 鏄惁鍚?4 涓彲鐤戞枃浠?|
|---|---|---|
| `router/modules/home.ts` | `AssetPanorama.vue`/`inventory/index.vue`/`watchlist/index.vue`/`TransactionList.vue` | 鉂?鍚?|
| `router/modules/asset.ts` | `ledgers/*`/`strategies/*`/`investment/*`/`stocks/*`/`funds/*`/`precious/*`/`realestate/*`/`IntelligentAnalysis.vue`/`AssetEntry.vue` | 鉂?鍚?|
| `router/modules/remaining.ts` | `login/`/`error/` | 鉂?鍚?|
| `router/modules/error.ts` / `system.ts` | 閿欒椤?绯荤粺椤?| 鉂?鍚?|

**4 涓枃浠跺湪鎵€鏈夊墠绔矾鐢辫〃涓潎鏃?`component: () => import(...)` 寮曠敤銆?*

### 2. 鍔ㄦ€佽矾鐢辨満鍒舵牳鏌ワ細鍚庣涓嶈繑鍥炶矾鐢?

`router/utils.ts` 鐢?`import.meta.glob("/src/views/**/*.{vue,tsx}")` 鏀堕泦鎵€鏈夎鍥撅紝骞堕€氳繃 `addAsyncRoutes` 鐢ㄥ悗绔繑鍥炵殑 `component` 璺緞鍋?`includes` 鍖归厤鏉ュ姩鎬佹寕杞姐€傚洜姝ょ悊璁轰笂鍚庣鍔ㄦ€佽矾鐢卞彲鑳芥寕杞藉墠绔矾鐢辫〃鏈垪鍑虹殑椤甸潰銆?
**鏍告煡鍚庣**锛歜ackend 鏄函 Flask/APIFlask API 鏈嶅姟锛坄app/domains/*/views.py`鎸変笟鍔″煙鎻愪緵鏁版嵁鎺ュ彛锛夛紝**涓嶅瓨鍦ㄥ悜鍓嶇杩斿洖璺敱/鑿滃崟閰嶇疆鐨?endpoint**銆傚墠绔?`getAsyncRoutes` 鍦?mock 涓彧杩斿洖 `permission`妯″潡锛坄mock/asyncRoutes.ts`锛夛紝鐢熶骇鐜鍚庣鏃犲搴旇矾鐢辨帴鍙ｃ€?
**缁撹锛氳繖 4 涓枃浠朵笉鍙兘閫氳繃鍚庣鍔ㄦ€佽矾鐢辨寕杞姐€?*

### 3. 鏂囦欢婧愮爜瀹氭€э細鍧囦负鏃х増/鍘熷瀷锛岄潪瀛愮粍浠?

#### `Overview.vue` 鈥?鏃х増 AssetPanorama锛堟渶鍗遍櫓锛?

- **`defineOptions({ name: "AssetPanorama" })`** 鈥斺€?涓庢鍦ㄤ娇鐢ㄧ殑 `AssetPanorama.vue` **缁勪欢鍚嶅畬鍏ㄧ浉鍚?*锛屽疄閿ゆ槸鍚岄〉闈㈢殑鏃х増
- 鏃х増鐗瑰緛锛氱‖缂栫爜 `楼1,487,482.95`/`楼2,918,379.83` 缁曡繃 API銆佸弻 `onMounted` 绔炴€併€?+ 姝?ref銆乣sankeyData` computed 绠椾簡涓嶈娑堣垂
- 鏂扮増 `AssetPanorama.vue` 鐗瑰緛锛氱敤 `MoneyDisplay`/`RiseFallText`锛坰pec 寮哄埗缁勪欢锛夈€佽皟 `getSankeyData`/`getLedgers` 鏂?API銆乣defineOptions({ name: "AssetPanorama" })` 鍚屽悕
- **杩欐槸涓€娆℃病鍒犲共鍑€鐨勯〉闈㈤噸鏋?*鈥斺€旀柊鐗堜笂绾垮悗鏃х増閬楃暀锛屽弻浠藉悓鍚嶇粍浠跺叡瀛?

#### `AssetOverview.vue` 鈥?鏃╂湡 mock 鍘熷瀷

- 鏃?`defineOptions`銆佹棤 API 璋冪敤
- 鍥捐〃鏁版嵁鍏ㄧ‖缂栫爜锛坄36.5`/`28.9`/`120,190,170...`锛?- 鐢?`@iconify/vue`鑰岄潪椤圭洰缁熶竴鐨?`@/components/ReIcon`锛堣繚鍙?spec 鍥炬爣浣撶郴绾﹀畾锛?

#### `AssetDetail.vue` 鈥?鏃╂湡 mock 鍘熷瀷

- 鏃?`defineOptions`銆佹棤 API 璋冪敤
- 鐢ㄥ師鐢?`<select>`/`<input>` 鑰岄潪 Element Plus锛堣繚鍙嶉」鐩?UI 缁熶竴绾﹀畾锛?- 纭紪鐮佹紨绀烘暟鎹紙鑵捐鎺ц偂/璐靛窞鑼呭彴/瀹炵墿榛勯噾绛夊啓姝伙級
- 鐢?`@iconify/vue` 鑰岄潪 `@/components/ReIcon`

#### `Assets.vue` 鈥?搴熷純鑴氭墜鏋?

- 浠?373 瀛楄妭锛宍<script setup>`鏄┖澹冲彧鏈夋敞閲?`// 瀵煎叆缁勪欢鍜岄€昏緫`
- 妯℃澘寮曠敤 `Tabs`/`SearchBar`/`Button`/`AssetDetailsTable` 鍥涗釜**鏍规湰涓嶅瓨鍦ㄧ殑缁勪欢**锛堟棤 import锛?- 缂栬瘧鍗虫姤閿欙紝纭浠庢湭琚娇鐢?

---

## 鍒犻櫎鏀剁泭

鍒犻櫎杩?4 涓枃浠朵竴骞舵秷闄や互涓嬮棶棰橈細

| 闂 | 鏉ユ簮鏂囦欢 | 鐘舵€?|
|---|---|---|
| 鍙?`onMounted` 绔炴€侊紙鏁版嵁鑾峰彇/鍥捐〃鍒濆鍖栵級 | `Overview.vue` | 鉁?闅忓垹闄ゆ竻闄?|
| 纭紪鐮?`楼1,487,482.95` 缁曡繃 API | `Overview.vue` | 鉁?闅忓垹闄ゆ竻闄?|
| 6+ 姝?ref锛坄pieChartRef`/`barChartRef` 绛夛級 | `Overview.vue` | 鉁?闅忓垹闄ゆ竻闄?|
| `sankeyData` computed 涓嶈娑堣垂 | `Overview.vue` | 鉁?闅忓垹闄ゆ竻闄?|
| 鍙?waterfall 閲嶅瀹炵幇 | `Overview.vue` | 鉁?闅忓垹闄ゆ竻闄?|
| 4 涓?"Overview" 鍛藉悕鍐茬獊 | 鍏ㄩ儴 | 鉁?鍑忚嚦 2 涓紙`account/Overview.vue` 璺敱澹?+ `account/AccountOverview.vue`锛?|
| 鏃╂湡鍘熷瀷杩濆弽 spec锛堝浘鏍囦綋绯?UI 搴擄級 | `AssetOverview`/`AssetDetail` | 鉁?闅忓垹闄ゆ竻闄?|
| `asset/` 鐩綍鏂囦欢鏁?| 鈥?| 14 鈫?10锛堝惈瀛愮洰褰曪級锛屾竻鐖借澶?|

> **娉?*锛歚account/Overview.vue`锛?.3KB锛夊拰`account/AccountOverview.vue`锛?6KB锛夊睘浜?account 妯″潡涓斿湪鐢紝**涓嶅湪鍒犻櫎鑼冨洿鍐?*锛屽嬁璇垹銆?
>
## 鎵ц寤鸿

鐩存帴 `git rm` 杩?4 涓枃浠跺嵆鍙紝鏃犱换浣曚緷璧栭渶澶勭悊锛堝凡纭鏃?import 寮曠敤銆佹棤璺敱鎸傝浇銆佹棤鍔ㄦ€佽矾鐢憋級銆傚缓璁湪涓€涓嫭绔?commit 瀹屾垚锛宑ommit message 绀轰緥锛?

```
chore(frontend): remove 4 dead view files in asset/

- Overview.vue: 鏃х増 AssetPanorama锛岃 AssetPanorama.vue 鍙栦唬鍚庨仐鐣?- AssetOverview.vue / AssetDetail.vue: 鏃╂湡 mock 鍘熷瀷锛屽叏纭紪鐮佹暟鎹?- Assets.vue: 搴熷純鑴氭墜鏋讹紝寮曠敤涓嶅瓨鍦ㄧ殑缁勪欢

鍧囨棤璺敱鎸傝浇銆佹棤 import 寮曠敤銆佹棤鍔ㄦ€佽矾鐢卞紩鐢紝纭姝讳唬鐮併€?```

杩欎篃鎰忓懗鐫€涓婁竴浠芥姤鍛?鏂规3"鐨勭粨璁哄皹鍩冭惤瀹氾細**`Overview.vue` 鏄垹闄よ€岄潪鎷嗗垎**锛岄偅涓?40KB 甯?bug 鐨勬枃浠舵暣浣撴秷澶憋紝鏄渶鐪佸姏銆佹敹鐩婃渶楂樼殑涓€姝ャ€?
