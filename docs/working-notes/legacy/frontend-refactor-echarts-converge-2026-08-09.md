# ECharts 鐢熷懡鍛ㄦ湡鏀舵暃璇存槑

> 瑙ｉ噴 `useEchartsLifecycle` 瑙ｅ喅浜嗕粈涔堛€佹€庝箞鐢ㄣ€佽鐩栧摢浜涢〉闈€?
>
## 鑳屾櫙锛氭暎钀界殑鍥捐〃鏍锋澘

鏁存敼鍓嶏紝澶氫釜椤甸潰鍚勮嚜鎵嬪啓 ECharts 鐢熷懡鍛ㄦ湡锛岄噸澶嶄笖鏄撻敊锛?

```js
// 鏃э細姣忎釜鍚浘琛ㄧ殑椤甸潰閮介噸澶嶈繖濂?const c = echarts.init(ref.value)
window.addEventListener("resize", handleResize)   // 鎵嬪啓 resize
onBeforeUnmount(() => c.dispose())                 // 鎵嬪啓 dispose
// 鉂?缂?onActivated 鈫?keepAlive 椤靛垏鍥炲墠鍙板浘琛ㄧ┖鐧?// 鉂?ledgers/detail 鐢氳嚦鎶?onBeforeUnmount 娉ㄥ唽浜嗕袱娆★紙dispose 閲嶅/娉勬紡锛?// 鉂?getCSSColor 閲屾畫鐣?console.log 璇婃柇浠ｇ爜
```

## 瑙ｆ硶锛歚useEchartsLifecycle`

鎵规 1 鎻愪緵缁熶竴灏佽锛坄composables/echarts/useEchartsLifecycle.ts`锛夛細

```ts
const { render, resize, charts } = useEchartsLifecycle(
  [pieRef, lineRef],                      // 妯℃澘 ref 鏁扮粍
  [(el) => { const c = echarts.init(el); c.setOption(opt); return c }], // 鏋勫缓鍣?  { keepAlive: true, autoRenderOnMount: false },  // keepAlive 椤靛繀椤?true
)
// 鏁版嵁鍒颁綅鍚庯細await nextTick(); render()
```

鍐呴儴缁熶竴澶勭悊锛?- `onMounted` 鑷姩娓叉煋锛坄autoRenderOnMount` 榛樿 true锛涘紓姝ユ暟鎹 false锛屾暟鎹埌浣嶅悗鎵嬪姩 `render()`锛?-`onActivated` 閲嶇粯锛堜慨澶?keepAlive 椤靛垏鍥炲墠鍙扮┖鐧斤級

- `window.resize` 鐩戝惉
- `onBeforeUnmount` 缁熶竴 `dispose`

閰嶈壊鏀圭敤 `composables/echarts/theme.ts` 鐨?`getCssVar`锛堣涔夊寲 CSS 鍙橀噺锛屽幓纭紪鐮佹定绾㈣穼缁匡級銆?

## 鐢ㄦ硶妯″紡锛堟瘡涓浘琛ㄥ崱鐗囷級

```ts
export function useXxxChart(data: XxxData): ChartHandle {
  const chartRef = ref<HTMLElement | null>(null)
  const { render } = useEchartsLifecycle(
    [chartRef],
    [(el) => { const c = echarts.init(el); c.setOption(build()); return c }],
    { keepAlive: true, autoRenderOnMount: false },
  )
  // 鏁版嵁鍙樺寲 鈫?閲嶇粯锛坈hartRef 鐢卞悇鍗＄墖鑷鎸佹湁锛屼笉杩涗笂涓嬫枃锛岄伩鍏嶈法缁勪欢浼?Ref 瑙ｅ寘鍧戯級
  watch(() => data.summary.value, async (s) => {
    if (s) { await nextTick(); render() }
  })
  return { chartRef, render }
}
```

> 鍥捐〃 ref 鐢?*鍗＄墖缁勪欢鑷韩**`useXxxChart(data)` 鎸佹湁骞剁粦瀹?`<div ref="chartRef">`锛堝瓧绗︿覆 ref锛夛紝**涓嶆斁鍏?provide/inject 涓婁笅鏂?*鈥斺€旇法缁勪欢浼?`Ref` 浼氳 props 鑷姩瑙ｅ寘锛岀粦涓嶅埌妯℃澘 ref銆?
>
## 瑕嗙洊鎯呭喌锛堝嫎璇悗锛?

| 椤甸潰 | 鍥捐〃鏁?| 鐘舵€?| 鎵规 |
|---|---|---|---|
| welcome | 4 | 宸叉帴 `useEchartsLifecycle` | 6 |
| ledgers/detail | 2 | 宸叉帴锛堜慨鍙?onBeforeUnmount/鏃ュ織/涓夊鍒锋柊锛?| 4 |
| AssetPanorama | 1锛堢€戝竷鍥撅級 | 宸叉帴锛堜慨 keepAlive 绌虹櫧锛?| 8 |
| inventory | 0 | 缁忛獙璇佹棤鍥捐〃锛屾棤闇€鏀舵暃 | 5 |
| portfolio/detail | 0 | **鍕樿**锛氭壒娆?1 璇垪涓烘硠婕忕偣锛岀粡楠岃瘉鏃犲浘琛?| 9 |

## 鏈湴钀藉湴妫€鏌ユ竻鍗?

- [ ] 鍚浘椤甸潰鏀硅皟 `useEchartsLifecycle`锛屽垹闄ゆ墜鍐?`init`/`resize`/`dispose`
- [ ] keepAlive 椤碉紙panorama / ledgers-detail / watchlist / welcome锛夊垏鍥炲墠鍙板浘琛ㄦ纭噸缁?- [ ] DevTools 鏃?ECharts 瀹炰緥绱Н銆佹棤 `console.log` 棰滆壊璇婃柇
- [ ] 閰嶈壊寮曠敤 `getCssVar`锛堣涔夊眰锛夛紝涓嶇洿鎺ュ啓 hex
