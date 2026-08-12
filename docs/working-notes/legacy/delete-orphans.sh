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
