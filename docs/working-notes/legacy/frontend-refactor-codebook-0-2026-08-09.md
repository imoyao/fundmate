# batch0 浠ｇ爜鎵嬪唽锛堝彲鐩存帴闃呰鐨勫叏閮ㄦ簮鐮侊級

> 鏈枃浠剁敱 `fundmate-optimization/batch0/` 涓嬪疄闄呬氦浠樻枃浠跺師鏍锋嫾鍚堬紝鐢ㄤ簬鍦ㄤ粎鏀寔 Markdown 鐨勫鎴风閲岄槄璇绘簮鐮併€?
> 鍏?2 涓枃浠躲€?

## `delete-orphans.sh`

```bash
#!/usr/bin/env bash
#
# batch0.1 鈥?鍒犻櫎 4 涓凡纭鐨勫鍎匡紙姝讳唬鐮侊級鏂囦欢
#
# 鐢ㄦ硶锛堝湪 fundmate 浠撳簱鏍圭洰褰曟墽琛岋級锛?#   bash fundmate-optimization/batch0/delete-orphans.sh
#
# 宸叉煡璇侊細杩?4 涓枃浠跺湪浠讳綍璺敱琛ㄤ腑鏃?component 寮曠敤銆佹棤 import 寮曠敤銆?# 鍚庣涓嶈繑鍥炲墠绔矾鐢憋紝纭姝讳唬鐮併€傚垹闄よ繛甯︽秷闄?Overview.vue 鐨勫叏閮ㄥ凡鐭?bug
# 锛堝弻 onMounted 绔炴€併€佺‖缂栫爜 楼1,487,482.95 缁曡繃 API銆?+ 姝?ref銆佸弻 waterfall锛夈€?#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." 2>/dev/null && pwd)"
# 鑻ヤ笂涓€琛岀畻閿欙紝鍥為€€鍒?CWD锛堣剼鏈簲鍦ㄤ粨搴撳唴杩愯锛?[ -f "$REPO_ROOT/frontend/package.json" ] || REPO_ROOT="$(pwd)"
cd "$REPO_ROOT"

echo "==> 浠撳簱鏍圭洰褰? $REPO_ROOT"

FILES=(
  "frontend/src/views/asset/Overview.vue"
  "frontend/src/views/asset/AssetOverview.vue"
  "frontend/src/views/asset/AssetDetail.vue"
  "frontend/src/views/asset/Assets.vue"
)

echo "==> 鍒犻櫎瀛ゅ効鏂囦欢"
for f in "${FILES[@]}"; do
  if [ -f "$f" ]; then
    git rm "$f"
  else
    echo "  [璺宠繃] 涓嶅瓨鍦? $f"
  fi
done

echo "==> 浜屾纭锛氬叏浠撲笉搴斿啀寮曠敤杩欎簺鏂囦欢"
if grep -rn -E "asset/Overview\.vue|asset/AssetOverview\.vue|asset/AssetDetail\.vue|asset/Assets\.vue" \
        frontend/src 2>/dev/null; then
  echo "  [璀﹀憡] 鍙戠幇娈嬬暀寮曠敤锛岃浜哄伐鏍告煡鍚庡啀 commit"
  exit 1
else
  echo "  [OK] 鏃犳畫鐣欏紩鐢?
fi

echo "==> 鍐掔儫鏋勫缓锛堢被鍨嬫鏌?+ 鏋勫缓锛夛紝澶辫触璇?git restore 鏈鍒犻櫎"
( pnpm --dir frontend type-check && pnpm --dir frontend build ) \
  || echo "  [鎻愮ず] 鏋勫缓鏈€氳繃锛岃妫€鏌ワ紱濡傜‘涓哄鍎垮垹闄ゆ墍鑷达紝git revert 鍗冲彲"

echo "==> 瀹屾垚銆傚缓璁嫭绔?commit锛?
echo "    git commit -m 'chore(frontend): remove 4 dead view files in asset/'"
```

## `fix-ledgers-detail.py`

```python
#!/usr/bin/env python3
#
# batch0.2 鈥?灏卞湴淇 ledgers/detail.vue 鐨勪袱涓棶棰橈紙闆堕闄┿€佸箓绛夈€佸彲鍥炴粴锛?#
#   1) 鍙?onBeforeUnmount 璧勬簮娉勬紡锛?#      婧愮爜涓湁涓や釜銆愬畬鍏ㄤ竴鏍枫€戠殑 onBeforeUnmount 鍧楋紝绗簩涓潤榛樿鐩栫涓€涓殑
#      娓呯悊閫昏緫 鈫?ECharts 瀹炰緥 / resize 鐩戝惉娉勬紡銆傚垹闄ょ浜屼釜閲嶅鍧楀嵆鍙€?#   2) 鐢熶骇璺緞娈嬬暀璋冭瘯浠ｇ爜锛?#      getCSSColor() 鍐呮湁 console.log("[ECharts棰滆壊] 璇诲彇 ...") 璇婃柇杈撳嚭锛屽垹闄よ琛屻€?#
# 鐢ㄦ硶锛堝湪 fundmate 浠撳簱鏍圭洰褰曟墽琛岋級锛?#   python3 fundmate-optimization/batch0/fix-ledgers-detail.py
#   python3 fundmate-optimization/batch0/fix-ledgers-detail.py --dry-run   # 鍙鏌ヤ笉鏀瑰姩
#   python3 fundmate-optimization/batch0/fix-ledgers-detail.py --path <缁濆璺緞>
#
# 瀹夊叏鎬э細
#   - 鍏堟柇瑷€涓や釜 onBeforeUnmount 鍧椼€愰€愬瓧绗︾浉鍚屻€戜笖鎭板ソ鍑虹幇 2 娆★紝鍚﹀垯鎶ラ敊閫€鍑猴紙涓嶅仛鐚滄祴鎬т慨鏀癸級
#   - console.log 鍧楃敤瀹屾暣澶氳瀛楃涓茬簿纭尮閰嶏紝鍖归厤涓嶅埌涔熸姤閿欓€€鍑?#   - 鏀瑰姩鍓嶈嚜鍔ㄥ浠戒负 <file>.bak.<timestamp>
#   - 骞傜瓑锛氳嫢宸叉槸淇鍚庣姸鎬侊紙鍧楀彧鍑虹幇 1 娆?/ console.log 宸蹭笉瀛樺湪锛夛紝鐩存帴璺宠繃
#
import sys, os, re, shutil, argparse, datetime

DEFAULT_PATH = "frontend/src/views/asset/ledgers/detail.vue"

# 涓や釜瀹屽叏涓€鏍风殑 onBeforeUnmount 鍧楋紙浠庢簮鐮佺簿纭彁鍙栵級
ON_BEFORE_UNMOUNT_BLOCK = """onBeforeUnmount(() => {
  window.removeEventListener("resize", handleWindowResize);
  chartInstance?.dispose();
  lineChartInstance?.dispose();
});"""

# getCSSColor 鍐呯殑 console.log 璋冭瘯鍧楋紙绮剧‘鍖归厤锛?CONSOLE_LOG_BLOCK = """  console.log(
    `[ECharts棰滆壊] 璇诲彇 ${varName}锛岀粨鏋滐細`,
    val || `鉂?娌¤鍒帮紒浣跨敤鍚庡鑹?${fallback}`
  );"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=DEFAULT_PATH)
    ap.add_argument("--dry-run", action="store_true", help="鍙鏌ヤ笉鏀瑰姩")
    args = ap.parse_args()

    path = args.path
    if not os.path.isfile(path):
        # 灏濊瘯浠撳簱鏍圭洰褰曠浉瀵硅矾寰?        alt = os.path.join(os.getcwd(), path)
        if os.path.isfile(alt):
            path = alt
        else:
            print(f"[閿欒] 鎵句笉鍒版枃浠? {path}", file=sys.stderr)
            sys.exit(2)

    with open(path, encoding="utf-8") as f:
        src = f.read()

    changes = []

    # ---- 1) 鍙?onBeforeUnmount ----
    count = src.count(ON_BEFORE_UNMOUNT_BLOCK)
    if count == 0:
        print("[妫€鏌 鏈壘鍒?onBeforeUnmount 鍧楋紙鍙兘宸查噸鏋?璺緞涓嶅锛夛紝璺宠繃")
    elif count == 1:
        print("[妫€鏌 onBeforeUnmount 浠?1 澶勶紝宸蹭慨澶嶏紝璺宠繃")
    elif count == 2:
        # 绉婚櫎绗簩涓嚭鐜帮紙淇濈暀绗竴涓級
        first = src.find(ON_BEFORE_UNMOUNT_BLOCK)
        second = src.find(ON_BEFORE_UNMOUNT_BLOCK, first + 1)
        src = src[:second] + src[second + len(ON_BEFORE_UNMOUNT_BLOCK):]
        changes.append("鍒犻櫎閲嶅鐨勭浜屼釜 onBeforeUnmount 鍧楋紙淇 ECharts/resize 鐩戝惉娉勬紡锛?)
        print("[灏嗕慨鏀筣 鍙?onBeforeUnmount 鈫?1锛堝垹闄ょ浜屼釜锛?)
    else:
        print(f"[閿欒] onBeforeUnmount 鍧楀嚭鐜?{count} 娆★紙棰勬湡 0/1/2锛夛紝"
              "涓洪伩鍏嶈鏀硅浜哄伐鏍告煡", file=sys.stderr)
        sys.exit(3)

    # ---- 2) console.log 璋冭瘯浠ｇ爜 ----
    if CONSOLE_LOG_BLOCK in src:
        src = src.replace(CONSOLE_LOG_BLOCK, "")
        changes.append("鍒犻櫎 getCSSColor 鍐?console.log 璇婃柇杈撳嚭锛堢Щ鍑虹敓浜ц矾寰勶級")
        print("[灏嗕慨鏀筣 鍒犻櫎 getCSSColor 鐨?console.log 璋冭瘯鍧?)
    else:
        # 鍏煎锛氳嫢宸叉槸鍗曡 console.log锛屼篃灏濊瘯鍒?        if "console.log(" in src and "璇诲彇" in src:
            print("[妫€鏌 瀛樺湪 console.log 浣嗘牸寮忎笉鍖归厤锛岃浜哄伐鏍告煡", file=sys.stderr)
        else:
            print("[妫€鏌 console.log 璋冭瘯鍧椾笉瀛樺湪锛岃烦杩?)

    if not changes:
        print("\n[缁撹] 鏂囦欢宸叉槸淇鍚庣姸鎬侊紝鏃犻渶鏀瑰姩 鉁?)
        return

    if args.dry_run:
        print(f"\n[dry-run] 灏嗗仛 {len(changes)} 澶勪慨鏀癸紝鏈啓鍏ユ枃浠讹細")
        for c in changes:
            print("  -", c)
        return

    # 澶囦唤 + 鍐欏叆
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    bak = f"{path}.bak.{ts}"
    shutil.copy2(path, bak)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)

    print(f"\n[瀹屾垚] 宸插啓鍏?{path}")
    print(f"[澶囦唤] {bak}")
    for c in changes:
        print("  鉁?, c)
    print("\n寤鸿楠岃瘉锛氬湪璐︽埛璇︽儏椤靛弽澶嶈繘鍏?閫€鍑猴紝DevTools 涓棤鍥捐〃瀹炰緥绱Н銆乧onsole 鏃?ECharts 棰滆壊璇婃柇杈撳嚭銆?)


if __name__ == "__main__":
    main()
```
