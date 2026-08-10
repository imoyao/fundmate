# 鎵规 7 鈥?鍚堝苟 BuyForm / SellForm锛堣法鏂囦欢鍘婚噸锛?
>
> 鎶?`frontend/src/components/QuickEntry/BuyForm.vue` 涓?`SellForm.vue` 閲嶅鐨勭害 60% 閫昏緫
> 鎶藉埌鍏变韩 `useTradeForm` composable + 閫氱敤 `TradeForm.vue`锛岃涔板叆/鍗栧嚭閫氳繃 `mode` 鍙傛暟澶嶇敤銆?> 鍘?`BuyForm.vue` / `SellForm.vue` 鏀逛负**钖勫３**锛堜繚鎸佸師 props / emits / `defineExpose`锛夛紝
> 鍥犳璋冪敤鏂?`frontend/src/views/asset/investment/manual/index.vue` **闆舵敼鍔?*鍗冲彲鍙楃泭銆?
>
## 閲嶅鐐瑰垎鏋愶紙鏉ヨ嚜婧愮爜 1:1 鎻愬彇锛?

| 鍧?| BuyForm | SellForm | 澶勭悊 |
|---|---|---|---|
| props | `ledgers / hideAccountSelect? / defaultLedgerId?` | 鍚屽乏 | 鍏变韩 `TradeFormProps` |
| 璐︽埛涓嬫媺 + 蹇嵎寤鸿处 | `showQuickAdd/newAccountName/newAccountType/creatingAccount/quickAddTypeOptions/quickCreateAccount/resetQuickAdd` | 鍚屽乏锛堝瓧娈典竴鑷达級 | 鈫?`useTradeForm` |
| 褰撳墠璐︽埛璁＄畻 | `currentLedger/selectableLedgers/accountName` | 鍚屽乏 | 鈫?`useTradeForm` |
| 鍩洪噾鍑€鍊兼棩鏈?| `confirmDate/actualNavDate` + `fetchConfirmDate` | 鍚屽乏锛? `fetchTradingDay`锛?| 鈫?`useTradeForm` |
| `disabledDate` | 鏈?| 鏈?| 鈫?`useTradeForm` |
| `formRef / handleSubmit / resetForm` | 鏍￠獙 + `createPosition` | 鏍￠獙 + `createPosition`(+`getPositions`/`validateTradeOrder`) | 鈫?`useTradeForm` |
| `defineExpose({handleSubmit,resetForm})` | 鏈?| 鏈?| 钖勫３閫忎紶 |
| 琛ㄥ崟瀛楁 | `ledger_id/symbol/name/market/type/price/trade_date/isAfter15/notes/currency/fee` + `buyAmount/shares/allocation` | 鍚屽熀纭€瀛楁 + `positionId/quantity` | 鍚堝苟涓?`TradeFormModel`锛堝苟闆嗭級 |
| **宸紓** | 璇佸埜鎼滅储(`searchSecurities/searchFunds`)銆侀噾棰濃啋浠介銆乣allocation`銆佽垂鐜囨姌鎵?| 鎸佷粨鏌ヨ(`getPositions`)銆乣quantity`(鑷畾涔夋牎楠?銆佽祹鍥炶垂鐜?`estimateRedeemFee/syncFundFees`)銆乣SELL_QUICK_RATIOS` | 鐣欏湪 `TradeForm.vue` 鐨?`mode` 鏉′欢鍧?|

鎻愪氦锛氫袱鑰呮渶缁堥兘璋冪敤 `createPosition`锛堜拱鍏ュ缓浠撱€佸崠鍑哄钩浠擄級锛屾晠鍏变韩 `handleSubmit` 缁熶竴 `validate 鈫?createPosition(buildPayload()) 鈫?emit('submit-success')`锛宍buildPayload`鎸?`mode` 鎷艰銆?

## 鏂囦欢娓呭崟锛堟湰鐩綍 7 涓枃浠讹級

```
batch7/
鈹溾攢鈹€ composables/trade/
鈹?  鈹溾攢鈹€ types.ts          # TradeMode / TradeFormModel锛堝瓧娈靛苟闆嗭級/ TradeFormProps
鈹?  鈹溾攢鈹€ useTradeForm.ts   # 鈽?鍏变韩閫昏緫锛氳处鎴?蹇嵎寤鸿处/鍑€鍊兼棩鏈?disabledDate/鏍￠獙/鎻愪氦/閲嶇疆
鈹?  鈹斺攢鈹€ index.ts          # barrel
鈹斺攢鈹€ components/QuickEntry/
    鈹溾攢鈹€ TradeForm.vue     # 鈽?鍏变韩琛ㄥ崟锛坢ode 鏉′欢娓叉煋 涔板叆/鍗栧嚭 宸紓鍧楋級锛涚洰鏍囷細frontend/src/components/QuickEntry/TradeForm.vue锛堟柊澧烇級
    鈹溾攢鈹€ BuyForm.vue       # 钖勫３锛堟浛鎹㈠師鏂囦欢锛宮ode="buy"锛?    鈹斺攢鈹€ SellForm.vue      # 钖勫３锛堟浛鎹㈠師鏂囦欢锛宮ode="sell"锛?```

## 鏋舵瀯瑕佺偣

- `useTradeForm(props, emit, mode)` 鎸佹湁鍏变韩鐘舵€?+ 鍔ㄤ綔锛岄€氳繃鍙傛暟娉ㄥ叆 `props/emit`锛屾棤寰幆渚濊禆銆?- 妯″紡鐩稿叧 API/澶勭悊鍣紙璇佸埜鎼滅储銆佹寔浠撴煡璇€佽祹鍥炶垂鐜囩瓑锛変繚鐣欏湪 `TradeForm.vue` 缁勪欢灞傦紝閬垮厤 composable 鑶ㄨ儉锛?  鍏叡閮ㄥ垎锛堣处鎴枫€佹棩鏈熴€佹彁浜わ級鐢?composable 鎻愪緵銆?- 钖勫３ `BuyForm`/`SellForm` 鐢?`ref` 鎷垮埌 `TradeForm` 瀹炰緥锛宍defineExpose` 閫忎紶 `handleSubmit/resetForm`锛?  骞惰浆鍙?emits 鈥斺€?缁存寔 `manual/index.vue` 鐜版湁鐢ㄦ硶涓嶅彉銆?
## 钀藉湴姝ラ

```bash
# 1. 澶嶅埗鍏变韩 composable
cp -r fundmate-optimization/batch7/composables/trade frontend/src/composables/

# 2. 鏂板鍏变韩琛ㄥ崟缁勪欢
cp fundmate-optimization/batch7/components/QuickEntry/TradeForm.vue \
   frontend/src/components/QuickEntry/TradeForm.vue

# 3. 鐢ㄨ杽澹宠鐩栧師 BuyForm / SellForm锛堝厛澶囦唤锛乵anual/index.vue 鏃犻渶鏀癸級
cp fundmate-optimization/batch7/components/QuickEntry/BuyForm.vue \
   frontend/src/components/QuickEntry/BuyForm.vue
cp fundmate-optimization/batch7/components/QuickEntry/SellForm.vue \
   frontend/src/components/QuickEntry/SellForm.vue

# 4. 鏈烘鎼繍
#    - 鎶婂師 BuyForm/SellForm 閲屻€屽叡浜儴鍒嗐€嶅垹鎺夛紙宸插湪 useTradeForm/TradeForm 瀹炵幇锛?#    - 鎶婂師 BuyForm 鐨勮瘉鍒告悳绱?閲戦浠介/閰嶇疆 閫昏緫鎼繘 TradeForm.vue 鐨?mode==='buy' 鍧?#    - 鎶婂師 SellForm 鐨勬寔浠撴煡璇?鏁伴噺鏍￠獙/璧庡洖璐圭巼 閫昏緫鎼繘 mode==='sell' 鍧?```

## 鍘熸枃浠?鈫?鏈洰褰?瀵瑰簲鍏崇郴锛堟惉杩愭竻鍗曪級

| 鍘?BuyForm 鍧?| 鎼埌鍝噷 |
|---|---|
| `form`(buyAmount/shares/allocation 绛? + `defaultForm` | `useTradeForm` 鐨?`TradeFormModel` / `defaultForm` |
| `showQuickAdd/newAccountName/newAccountType/creatingAccount/quickAddTypeOptions/quickCreateAccount/resetQuickAdd` | `useTradeForm` |
| `currentLedger/selectableLedgers/accountName` | `useTradeForm` |
| `confirmDate/actualNavDate/fetchConfirmDate/fetchTradingDay/disabledDate` | `useTradeForm` |
| `formRef/handleSubmit/resetForm/rules`(buy 閮ㄥ垎) | `useTradeForm`锛坮ules 鎸?mode 鍒嗘敮锛?|
| `remoteSearch/onSecuritySelected/applyFeePreset/onFeeModeChange/onFundFeeDiscountChange` + 璇佸埜鎼滅储妯℃澘 | `TradeForm.vue` 鐨?`mode==='buy'` 鍧楋紙API: searchSecurities/searchFunds/calcFundNav/getFundFeeRates/DEFAULT_SUB_RATE锛?|
| `defineExpose` | 钖勫３ `BuyForm.vue` 閫忎紶 |

| 鍘?SellForm 鍧?| 鎼埌鍝噷 |
|---|---|
| `form`(positionId/quantity 绛? + `defaultForm` | `useTradeForm` 鐨?`TradeFormModel` / `defaultForm` |
| 璐︽埛/鍑€鍊兼棩鏈?disabledDate/`formRef/handleSubmit/resetForm/rules`(sell 閮ㄥ垎) | `useTradeForm` |
| `fetchPositionsByAccount/onAccountChange/onPositionSelect/fetchFundFeeRules/calculateFeeAndRate/openFeeRateDialog/applySellQuickRatio/validateQuantity` + 鎸佷粨妯℃澘 | `TradeForm.vue` 鐨?`mode==='sell'` 鍧楋紙API: getPositions/validateTradeOrder/estimateRedeemFee/syncFundFees/SELL_QUICK_RATIOS/getStep锛?|
| `defineExpose` | 钖勫３ `SellForm.vue` 閫忎紶 |

## 鈿?闇€浣犳湰鍦板榻愮殑 TODO锛堜唬鐮佸唴宸叉爣娉級

1. **`disabledDate` / `showIsAfter15` / `validateQuantity`**锛氶鏋朵负鍗犱綅锛屾惉鍘熼€昏緫銆?2. **`quickCreateAccount`**锛氭惉鍘熷缓璐﹂€昏緫锛坈reateLedgerApi锛夛紝鎴愬姛鍚?`emit("accounts-changed")`銆?3. **`fetchTradingDay` / `fetchConfirmDate`**锛氭惉鍘?checkTradingDay / calcFundConfirmDate 璋冪敤銆?4. **`buildPayload` 瀛楁鍚?*锛氫互 `@/api/positions.createPosition` 鐪熷疄鍏ュ弬涓哄噯寰皟銆?5. **妯″紡鐩稿叧澶勭悊鍣?*锛氫拱鍏ョ殑杩滅▼鎼滅储/璐圭巼鎶樻墸銆佸崠鍑虹殑鎸佷粨鏌ヨ/璧庡洖璐圭巼锛屾妸鍘熼€昏緫鎼繘 `TradeForm.vue` 瀵瑰簲鍧椼€?6. **`LEDGER_TYPE_SHORT` / `getLedgerColor` / `bgFromColor`**锛氬師涓よ〃鍗曞鍏ヤ絾鏈湪鎻愬彇閫昏緫涓紩鐢紝鎸夌湡瀹炵敤閫斿喅瀹氭槸鍚︿繚鐣欍€?
## 楠岃瘉娓呭崟

- [ ] `pnpm type-check` 閫氳繃
- [ ] `manual/index.vue` 涔板叆/鍗栧嚭鍒囨崲銆佹彁浜ゃ€侀噸缃潎姝ｅ父锛堣杽澹抽€忎紶鏃犺锛?- [ ] 璐︽埛涓嬫媺 + 蹇嵎寤鸿处鍦ㄤ袱涓ā寮忛兘鍙敤
- [ ] 涔板叆锛氳瘉鍒告悳绱?閲戦/浠介/閰嶇疆 鏍￠獙涓庢彁浜ゆ纭?- [ ] 鍗栧嚭锛氭寔浠撴煡璇?鏁伴噺鏍￠獙/璧庡洖璐圭巼 鏍￠獙涓庢彁浜ゆ纭?- [ ] 鍒犻櫎浜嗗師涓ゆ枃浠堕噷琚娊璧扮殑閲嶅鍧楋紝鏃犻噸澶嶅畾涔?
