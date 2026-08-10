# 鎵规 1 鈥?鍏变韩鍩哄缓锛堢函鏂板锛屾渶楂樻潬鏉嗭級

> 钀藉湴 `frontend/src/` 涓嬬殑**鏂板鏂囦欢 + 鏈烘杩佺Щ鑴氭湰**銆傝繖鏄悗缁墍鏈夋媶鍒嗘壒娆＄殑渚濊禆鍩哄骇銆?
>
## 浜や粯

| 鏂囦欢 | 浣滅敤 |
|---|---|
| `batch1/composables/echarts/useEchartsLifecycle.ts` | 鏀舵暃 6+ 鏂囦欢鐨?ECharts init/resize/dispose/keepAlive 閲嶇粯锛?*鍚庣画鎵规 4/6/8 鍧囨帴绠″埌杩欓噷**锛?|
| `batch1/composables/echarts/theme.ts` | 鍥捐〃鑹插僵鍗曚竴鏁版嵁婧愶紙瀵规帴 spec 璇箟鍖?CSS 鍙橀噺锛夛紝鏇夸唬 3+ 澶勭‖缂栫爜娑ㄧ孩璺岀豢锛涙彁渚?`getCssVar` |
| `batch1/constants/exchangeRates.ts` | 姹囩巼鍗曚竴鏁版嵁婧愶紙鏇夸唬 inventory / AssetPanorama 鍚勫唴鑱斾竴浠斤級 |
| `batch1/utils/currency.ts` | `toCNY` / `fromCNY` / `formatCurrency` 璐у竵鎹㈢畻 |
| `batch1/extract-inventory-config.py` | 浠?`inventory/index.vue` 鑷姩鎶藉彇 `categories`/`assetTypeMap` 鍒?`constants/` |
| `batch1/usePageRefresh.fixed.ts` | 淇 `usePageRefresh` 骞跺彂闃叉姈 bug锛堝叏灞€ timeoutId 鈫?灞€閮級 |
| `batch1/move-layout-hooks.sh` | `layout/hooks/*` 鈫?`composables/layout/*` 鏈烘杩佺Щ + import 鏀瑰啓 |

## 钀藉湴鏂瑰紡

```bash
cd <浣犵殑 fundmate 浠撳簱鏍圭洰褰?
cp fundmate-optimization/batch1/composables/echarts/*.ts frontend/src/composables/echarts/
python3 fundmate-optimization/batch1/extract-inventory-config.py --dry-run
python3 fundmate-optimization/batch1/extract-inventory-config.py
cp fundmate-optimization/batch1/constants/exchangeRates.ts frontend/src/constants/
cp fundmate-optimization/batch1/utils/currency.ts            frontend/src/utils/
cp fundmate-optimization/batch1/usePageRefresh.fixed.ts      frontend/src/composables/usePageRefresh.ts
bash fundmate-optimization/batch1/move-layout-hooks.sh --dry-run
bash fundmate-optimization/batch1/move-layout-hooks.sh
cd frontend && pnpm type-check && pnpm build
```

## 璇存槑

- `useEchartsLifecycle` 鏄湰鏂规鐨勬牳蹇冨熀寤猴細缁熶竴澶勭悊 `onMounted` / `onActivated` 閲嶇粯銆乣resize`鐩戝惉銆乣onBeforeUnmount` dispose锛屼粠鏍逛笂娑堥櫎鍚勯〉鎵嬪啓鍥捐〃鐨勫洓绫绘牱鏉?bug銆?- 鍚浘琛ㄧ殑椤甸潰锛坵elcome / ledgers / panorama锛夊湪鎵规 4 / 6 / 8 涓垎鍒帴鍏ワ紱inventory 涓?portfolio/detail 缁忛獙璇?*鏃?ECharts**锛屼粎鍋氱粍浠舵媶鍒嗐€?
