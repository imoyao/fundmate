# 鎵规 0 鈥?姝㈣锛堥浂椋庨櫓锛屽綋澶╁彲浜や粯锛?
>
> 绾剼鏈紝灏卞湴淇浠撳簱鐜版湁鏂囦欢锛?*涓嶆柊澧炴簮鐮?*銆傚湪浣犺兘 push 鐨勬湰鍦颁粨搴撴牴鐩綍杩愯銆?
>
## 浜や粯

| 鏂囦欢 | 浣滅敤 | 椋庨櫓 |
|---|---|---|
| `batch0/delete-orphans.sh` | `git rm` 4 涓鍎挎枃浠讹紙Overview / AssetOverview / AssetDetail / Assets锛? 浜屾 grep 纭 + 鍐掔儫鏋勫缓 | 馃煝 闆讹紙宸叉煡璇佹棤寮曠敤锛?|
| `batch0/fix-ledgers-detail.py` | 灏卞湴淇 `ledgers/detail.vue`锛氬垹閲嶅 `onBeforeUnmount`锛堜慨 ECharts/resize 娉勬紡锛? 鍒?`getCSSColor` 鐨?console.log 璋冭瘯浠ｇ爜 | 馃煝 闆讹紙鏂█绮剧‘鍖归厤锛屽箓绛夛紝鑷姩澶囦唤锛?|

## 杩愯鏂瑰紡

```bash
cd <浣犵殑 fundmate 浠撳簱鏍圭洰褰?
bash fundmate-optimization/batch0/delete-orphans.sh
python3 fundmate-optimization/batch0/fix-ledgers-detail.py --dry-run   # 鍏堣瘯璺?python3 fundmate-optimization/batch0/fix-ledgers-detail.py            # 姝ｅ紡淇?```

## 璇存槑

- 杩欐槸銆屽厛姝㈣銆嶆楠わ細娓呮帀姝讳唬鐮併€佷慨鎺夋渶鏄庢樉鐨?ECharts 瀹炰緥娉勬紡涓庤瘖鏂棩蹇楋紝涓嶆敼鍙樹换浣曚笟鍔¤涓恒€?- 鍚庣画鎵规锛?/6/8锛変細鐢ㄧ粨鏋勫寲鐨?`useEchartsLifecycle` 褰诲簳鎺ョ鍥捐〃鐢熷懡鍛ㄦ湡锛屾湰鎵规鍙槸鏈€蹇鏁堢殑涓存椂琛ヤ竵銆?
