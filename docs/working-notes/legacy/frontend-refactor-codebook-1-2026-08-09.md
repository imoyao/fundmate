# batch1 浠ｇ爜鎵嬪唽锛堝彲鐩存帴闃呰鐨勫叏閮ㄦ簮鐮侊級

> 鏈枃浠剁敱 `fundmate-optimization/batch1/` 涓嬪疄闄呬氦浠樻枃浠跺師鏍锋嫾鍚堬紝鐢ㄤ簬鍦ㄤ粎鏀寔 Markdown 鐨勫鎴风閲岄槄璇绘簮鐮併€?
> 鍏?7 涓枃浠躲€?

## `composables/echarts/theme.ts`

```ts
// src/composables/echarts/theme.ts
//
// ECharts 鑹插僵涓庝富棰橀泦涓鐞嗏€斺€斿崟涓€鏁版嵁婧愩€?// 瀵规帴 SPEC.md 鐨勮涔夊寲 CSS 鍙橀噺鍒嗗眰锛氫笟鍔″彧寮曠敤璇箟灞傦紙--color-rise / --color-fall锛夛紝
// 涓嶇洿鎺ュ啓 hex锛涙殫鑹叉ā寮忓垏鎹粎闇€鏇存柊 CSS 鍙橀噺锛屽浘琛ㄩ浂鏀广€?// 鍙栦唬鍚勯〉闈㈤噷 3+ 澶勭嫭绔嬬‖缂栫爜鐨勬定绾㈣穼缁挎槧灏勪笌 getCSSColor 閲嶅瀹炵幇銆?//
import { getComputedStyle } from "vue";

/** 璇箟鍖栧浘琛ㄨ壊锛堝紩鐢?CSS 鍙橀噺锛涜繍琛屾椂鐢?getCssVar 瑙ｆ瀽涓哄疄闄呰壊鍊硷級 */
export const ECHARTS_COLOR = {
  rise: "var(--color-rise)", // 娑?/ 鐩堝埄锛堝浗鍐呬範鎯細绾級
  fall: "var(--color-fall)", // 璺?/ 浜忔崯锛堢豢锛?  danger: "var(--el-color-danger)",
  brand: "var(--brand-primary)",
} as const;

/** 鍦ㄧ函 JS 鐜锛堝 ECharts option锛夐噷浣跨敤瀹為檯鑹插€兼椂鐨勫悗澶囪壊 */
export const ECHARTS_FALLBACK = {
  rise: "#E34F38", // 鍝佺墝鏆栫孩鐝婄憵锛堟定锛?  fall: "#2BA471", // 璺岋紙缁匡級
  danger: "#D4364A",
} as const;

/**
 * 璇诲彇杩愯鏈?CSS 鍙橀噺瀹為檯鍊笺€傛浛鎹㈡棫 getCSSColor锛堣鍑芥暟甯?console.log 璇婃柇锛屽凡娓呴櫎锛夈€? * 鍦?onMounted / 鏁版嵁鍒颁綅鍚庤皟鐢紝纭繚涓婚宸插簲鐢ㄣ€? */
export function getCssVar(name: string, fallback = ""): string {
  if (typeof window === "undefined") return fallback;
  const val = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return val || fallback;
}

/**
 * 鍙栬涔夊寲娑ㄨ穼鑹茬殑瀹為檯鍊硷紙甯﹀悗澶囷級锛屼緵鍥捐〃 option 浣跨敤銆? * 渚嬶細color: [getRiseColor(), getFallColor()]
 */
export function getRiseColor(): string {
  return getCssVar("--color-rise", ECHARTS_FALLBACK.rise);
}
export function getFallColor(): string {
  return getCssVar("--color-fall", ECHARTS_FALLBACK.fall);
}
export function getDangerColor(): string {
  return getCssVar("--el-color-danger", ECHARTS_FALLBACK.danger);
}
```

## `composables/echarts/useEchartsLifecycle.ts`

```ts
// src/composables/echarts/useEchartsLifecycle.ts
//
// 缁熶竴绠＄悊涓€缁?ECharts 瀹炰緥鐨?init / resize / dispose / keepAlive 閲嶇粯銆?// 瑙ｅ喅鏁ｈ惤鍦?6+ 鏂囦欢锛圓ssetPanorama / ledgers/detail / inventory / welcome /
// watchlist / portfolio/detail锛夌殑閲嶅鏍锋澘锛屽苟淇 keepAlive 椤电己 onActivated
// 瀵艰嚧鍒囧洖鍓嶅彴鍥捐〃涓嶉噸缁樼殑闂锛堝 /panorama 鏍囪 keepAlive 鍗存棤 onActivated锛夈€?//
// 鐢ㄦ硶锛?//   const { render } = useEchartsLifecycle(
//     [pieRef, lineRef],
//     [
//       (el) => { const c = echarts.init(el); c.setOption(pieOption); return c },
//       (el) => { const c = echarts.init(el); c.setOption(lineOption); return c },
//     ],
//     { keepAlive: true }   // 浠?keepAlive 缂撳瓨椤甸渶瑕?//   )
//   // 鏁版嵁鍒颁綅鍚庯細await nextTick(); render()
//
import { onMounted, onActivated, onBeforeUnmount, nextTick, type Ref } from "vue";
import * as echarts from "echarts";

export interface EchartsLifecycleOptions {
  /** 璺敱 meta.keepAlive 涓?true 鐨勯〉闈㈠繀椤讳紶 true锛屽惁鍒欏垏鍥炲墠鍙板浘琛ㄤ笉閲嶇粯 */
  keepAlive?: boolean;
  /** 鏄惁鍦ㄩ娆℃寕杞藉悗鑷姩娓叉煋锛堥粯璁?true锛夈€傝嫢鍥捐〃渚濊禆寮傛鏁版嵁锛岃 false 骞跺湪鏁版嵁鍒颁綅鍚庢墜鍔?render() */
  autoRenderOnMount?: boolean;
}

/**
 * 鏀舵暃 ECharts 鐢熷懡鍛ㄦ湡銆? * @param refs 妯℃澘 ref 鏁扮粍锛圚TMLElement | null锛? * @param builders 姣忎釜 ref 瀵瑰簲鐨勬瀯寤哄嚱鏁帮紝鎺ユ敹 DOM 鍏冪礌锛岃繑鍥?echarts 瀹炰緥
 * @param opts 閫夐」
 * @returns { render, resize, charts } 鎵嬪姩閲嶇粯鍑芥暟 / 鍗曞浘琛?resize / 瀹炰緥鏁扮粍
 */
export function useEchartsLifecycle(
  refs: Ref<HTMLElement | null>[],
  builders: ((el: HTMLElement) => echarts.ECharts)[],
  opts: EchartsLifecycleOptions = {},
) {
  const { keepAlive = false, autoRenderOnMount = true } = opts;
  const charts: echarts.ECharts[] = [];

  const render = () => {
    // 鍏堥噴鏀炬棫瀹炰緥锛岄伩鍏嶉噸澶?init 鍙犲姞
    charts.forEach((c) => c.dispose());
    charts.length = 0;
    refs.forEach((r, i) => {
      if (r.value && builders[i]) {
        charts.push(builders[i](r.value));
      }
    });
  };

  const resize = () => charts.forEach((c) => c.resize());

  if (autoRenderOnMount) {
    onMounted(() => nextTick(render));
  }
  if (keepAlive) {
    // 淇锛歬eepAlive 椤靛垏鍥炲墠鍙版椂閲嶇粯锛堟棫浠ｇ爜鏅亶缂哄け 鈫?鍥捐〃绌虹櫧/涓嶆洿鏂帮級
    onActivated(() => nextTick(render));
  }

  window.addEventListener("resize", resize);

  onBeforeUnmount(() => {
    window.removeEventListener("resize", resize);
    charts.forEach((c) => c.dispose());
    charts.length = 0;
  });

  return { render, resize, charts };
}
```

## `constants/exchangeRates.ts`

```ts
// src/constants/exchangeRates.ts
//
// 姹囩巼鍗曚竴鏁版嵁婧愩€傚彇浠?inventory/index.vue 涓?AssetPanorama.vue 鍚勫唴鑱斾竴浠?// EXCHANGE_RATES 鐨勬暎钀藉啓娉曪紙鍘熷€兼潵鑷?AssetPanorama锛欳NY:1, USD:7.25, HKD:0.92锛夈€?// 娉ㄦ剰锛氭眹鐜囦細鍙樺姩锛屽缓璁悗缁帴鍚庣閰嶇疆鎺ュ彛锛涘湪姝や箣鍓嶆敼杩欓噷鍗冲彲鍏ㄥ眬鐢熸晥銆?//
export const EXCHANGE_RATES: Record<string, number> = {
  CNY: 1,
  USD: 7.25,
  HKD: 0.92,
};

/** 鏀寔璁′环鐨勮揣甯佹竻鍗?*/
export const SUPPORTED_CURRENCIES = Object.keys(EXCHANGE_RATES) as Array<
  keyof typeof EXCHANGE_RATES
>;

/** 鍙栨煇甯佺瀵逛汉姘戝竵鐨勬眹鐜囷紝鏈煡甯佺榛樿 1 */
export function getRate(currency: string): number {
  return EXCHANGE_RATES[currency] ?? 1;
}
```

## `extract-inventory-config.py`

```python
#!/usr/bin/env python3
#
# batch1.2 鈥?浠?inventory/index.vue 鎶藉彇 categories / assetTypeMap 鍒板父閲忔枃浠?#
# 鏇夸唬鎵嬪伐鎼繍锛堥伩鍏嶆墜鎶勫嚭閿欙級锛岀敤鎷彿閰嶅钩鎵弿鎻愬彇椤跺眰 const 瀵硅薄/鏁扮粍瀛楅潰閲忋€?# 鐢熸垚锛?#   frontend/src/constants/categories.ts
#   frontend/src/constants/assetTypes.ts
#
# 鐢ㄦ硶锛堝湪 fundmate 浠撳簱鏍圭洰褰曟墽琛岋級锛?#   python3 fundmate-optimization/batch1/extract-inventory-config.py
#   python3 fundmate-optimization/batch1/extract-inventory-config.py --dry-run
#
import sys, os, argparse, datetime, shutil

SRC = "frontend/src/views/asset/inventory/index.vue"
OUT_CATEGORIES = "frontend/src/constants/categories.ts"
OUT_ASSET_TYPES = "frontend/src/constants/assetTypes.ts"


def extract_balanced(src: str, start: int) -> str:
    """浠?start锛?=' 涔嬪悗锛夊紑濮嬶紝鎸夋嫭鍙烽厤骞虫埅鍙栧埌瀛楅潰閲忕粨鏉燂紙鍚湯灏?;锛?""
    i = start
    n = len(src)
    # 璺宠繃绌虹櫧涓?=
    while i < n and src[i] in " =\t":
        i += 1
    open_ch = src[i]
    if open_ch not in "[{":
        raise ValueError(f"鏈熸湜 [ 鎴?{{锛屽疄闄?'{open_ch}' @ {i}")
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    j = i
    while j < n:
        c = src[j]
        if c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            if depth == 0 and c == close_ch:
                # 鍖呭惈鍒版澶勶紝鍐嶅悆鎺夊彲鑳界殑 ;
                k = j + 1
                while k < n and src[k] in ";\t\n ":
                    if src[k] == ";":
                        k += 1
                        break
                    k += 1
                return src[i:k]
        j += 1
    raise ValueError("鎷彿鏈厤骞?)


def find_const_block(src: str, name: str):
    # 鍖归厤 `const categories =` 鎴?`const assetTypeMap =`
    marker = f"const {name} ="
    idx = src.find(marker)
    if idx < 0:
        return None
    eq = src.find("=", idx)
    return extract_balanced(src, eq + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--src", default=SRC)
    args = ap.parse_args()

    if not os.path.isfile(args.src):
        alt = os.path.join(os.getcwd(), args.src)
        if os.path.isfile(alt):
            args.src = alt
        else:
            print(f"[閿欒] 鎵句笉鍒版簮鏂囦欢: {args.src}", file=sys.stderr)
            sys.exit(2)

    src = open(args.src, encoding="utf-8").read()

    cats = find_const_block(src, "categories")
    types = find_const_block(src, "assetTypeMap")

    if cats is None:
        print("[璀﹀憡] 鏈壘鍒?`const categories =`锛岃浜哄伐鏍稿 inventory/index.vue", file=sys.stderr)
    if types is None:
        print("[璀﹀憡] 鏈壘鍒?`const assetTypeMap =`锛岃浜哄伐鏍稿 inventory/index.vue", file=sys.stderr)

    cat_file = (
        "// src/constants/categories.ts\n"
        "// 鐢?batch1/extract-inventory-config.py 浠?inventory/index.vue 鑷姩鎶藉彇銆俓n"
        "// 璧勪骇澶х被锛堟姇璧勭悊璐?娴佸姩璧勯噾/鍥哄畾璧勪骇/璐熷€?搴旀敹娆?淇濋櫓椤圭洰锛夌殑灞曠ず閰嶇疆銆俓n\n"
        f"export const categories = {cats if cats else '/* TODO: 浜哄伐绮樿创 inventory 鐨?categories 瀵硅薄 */'}\n"
    )
    type_file = (
        "// src/constants/assetTypes.ts\n"
        "// 鐢?batch1/extract-inventory-config.py 浠?inventory/index.vue 鑷姩鎶藉彇銆俓n"
        "// 璧勪骇澶х被 -> 瀛愮被鍨?鏄犲皠锛堝浘鏍?鏍囩/棰滆壊锛夈€俓n\n"
        f"export const assetTypeMap = {types if types else '/* TODO: 浜哄伐绮樿创 inventory 鐨?assetTypeMap 瀵硅薄 */'}\n"
    )

    if args.dry_run:
        print("[dry-run] categories.ts 灏嗗啓鍏ワ細\n", cat_file[:400], "...")
        print("[dry-run] assetTypes.ts 灏嗗啓鍏ワ細\n", type_file[:400], "...")
        return

    for path, content in [(OUT_CATEGORIES, cat_file), (OUT_ASSET_TYPES, type_file)]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.isfile(path):
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            shutil.copy2(path, f"{path}.bak.{ts}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[瀹屾垚] 宸茬敓鎴?{path}")

    print("\n鍚庣画锛氬湪 inventory/index.vue 鍒犻櫎鍐呰仈鐨?categories / assetTypeMap锛?
          "鏀逛负 `import { categories } from '@/constants/categories'` 绛夛紝骞惰窇 pnpm type-check銆?)


if __name__ == "__main__":
    main()
```

## `move-layout-hooks.sh`

```bash
#!/usr/bin/env bash
#
# batch1.4 鈥?缁熶竴 composables 鐩綍锛氭妸 layout/hooks/* 杩佺Щ鍒?composables/layout/*
#
# 鍘熼」鐩粍鍚堝紡鍑芥暟鍒嗘暎涓ゅ锛坈omposables/ 浠?涓紝layout/hooks/ 鏈?涓級锛屽懡鍚嶄笉涓€鑷达紝
# 瀵艰嚧寮€鍙戣€呮棤澶勫缃€昏緫銆佽杩妸閫昏緫濉炶繘 .vue锛堝崟鏂囦欢鑶ㄨ儉鐨勬牴鍥犱箣涓€锛夈€?# 鏈剼鏈満姊拌縼绉诲苟鎵归噺鏀瑰啓 import 璺緞锛岄浂閫昏緫鍙樻洿銆?#
# 鐢ㄦ硶锛堝湪 fundmate 浠撳簱鏍圭洰褰曟墽琛岋級锛?#   bash fundmate-optimization/batch1/move-layout-hooks.sh
#   bash fundmate-optimization/batch1/move-layout-hooks.sh --dry-run
#
set -euo pipefail

DRY=""
[ "${1:-}" = "--dry-run" ] && DRY="--dry-run"

SRC_DIR="frontend/src/layout/hooks"
DST_DIR="frontend/src/composables/layout"

# 寰呰縼绉荤殑鏂囦欢锛堟潵鑷竷灞€ hooks锛?FILES=(useBoolean.ts useDataThemeChange.ts useLayout.ts useMultiFrame.ts useNav.ts useTag.ts)

cd "$(pwd)"
[ -d "$SRC_DIR" ] || { echo "[閿欒] 鎵句笉鍒?$SRC_DIR锛岃纭鍦ㄤ粨搴撴牴鐩綍鎵ц"; exit 2; }

echo "==> 杩佺Щ $SRC_DIR -> $DST_DIR"
if [ -n "$DRY" ]; then
  echo "  [dry-run] 灏?git mv 浠ヤ笅鏂囦欢锛?
  for f in "${FILES[@]}"; do [ -f "$SRC_DIR/$f" ] && echo "    $SRC_DIR/$f"; done
else
  mkdir -p "$DST_DIR"
  for f in "${FILES[@]}"; do
    if [ -f "$SRC_DIR/$f" ]; then
      git mv "$SRC_DIR/$f" "$DST_DIR/$f"
      echo "    moved $f"
    fi
  done
fi

# 鎵归噺鏀瑰啓 import 璺緞锛?@/layout/hooks/xxx -> @/composables/layout/xxx
echo "==> 鏀瑰啓鍏ㄤ粨 import 璺緞锛欯/layout/hooks/ -> @/composables/layout/"
if [ -n "$DRY" ]; then
  grep -rln "@/layout/hooks/" frontend/src 2>/dev/null || echo "  [dry-run] 鏈彂鐜板紩鐢?
else
  # 鐢?perl 鍘熷湴鏇挎崲锛坢ac/linux 閫氱敤锛?  grep -rln "@/layout/hooks/" frontend/src 2>/dev/null | while read -r file; do
    perl -i -pe 's{\@/layout/hooks/}{\@/composables/layout/}g' "$file"
    echo "    patched $file"
  done
fi

if [ -z "$DRY" ]; then
  echo "==> 鍐掔儫锛氱被鍨嬫鏌?+ 鏋勫缓"
  ( pnpm --dir frontend type-check && pnpm --dir frontend build ) \
    || echo "  [鎻愮ず] 鏋勫缓鏈€氳繃锛岃妫€鏌?import 璺緞锛沢it checkout 鍙洖婊氭湰鑴氭湰鏀瑰姩"
  echo "==> 瀹屾垚銆傚缓璁嫭绔?commit锛?
  echo "    git commit -m 'refactor(frontend): move layout/hooks into composables/layout'"
fi
```

## `usePageRefresh.fixed.ts`

```ts
// src/composables/usePageRefresh.ts
//
// 鍏ㄥ眬鍒锋柊 composable锛氬熀浜?mitt 浜嬩欢鎬荤嚎锛岃璐︽垚鍔熷悗鑷姩鍒锋柊鍏宠仈椤甸潰銆?// 缁勪欢閿€姣佹椂锛坥nUnmounted锛夎嚜鍔ㄨВ缁戠洃鍚€?//
// 鈿?淇锛氬師瀹炵幇鎶?`let timeoutId` 鏀惧湪妯″潡椤剁骇锛堝叏灞€鍙橀噺锛夛紝澶氫釜缁勪欢鍚屾椂
//     mount 鏃跺悇鑷殑闃叉姈璁℃椂鍣ㄤ細浜掔浉 clearTimeout + 瑕嗙洊锛屽鑷村埛鏂拌鍚?涓插彴銆?//     鐜板凡鏀逛负銆愬嚱鏁板唴灞€閮ㄥ彉閲忋€戯紝姣忎釜璋冪敤鏂圭嫭绔嬫寔鏈夐槻鎶栬鏃跺櫒銆?//
import { onUnmounted } from "vue";
import { emitter } from "@/utils/mitt";

const REFRESH_EVENT = "refresh-ledger-data";

export function usePageRefresh(callback: () => void, debounceDelay: number = 300) {
  // 姣忎釜璋冪敤鏂圭嫭绔嬫寔鏈夐槻鎶栬鏃跺櫒锛岄伩鍏嶅缁勪欢浜掔浉鎵撴柇锛堝師瀹炵幇涓哄叏灞€鍙橀噺锛屽瓨鍦ㄥ苟鍙?bug锛?  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  // 灏佽甯﹂槻鎶栫殑鍥炶皟
  const handler = () => {
    if (timeoutId) clearTimeout(timeoutId);
    timeoutId = setTimeout(() => {
      callback();
      timeoutId = null;
    }, debounceDelay);
  };

  // 缁戝畾鍏ㄥ眬浜嬩欢
  emitter.on(REFRESH_EVENT, handler);

  // 鑷姩娓呯悊
  onUnmounted(() => {
    if (timeoutId) clearTimeout(timeoutId);
    emitter.off(REFRESH_EVENT, handler);
  });
}
```

## `utils/currency.ts`

```ts
// src/utils/currency.ts
//
// 璐у竵鎹㈢畻宸ュ叿銆傛秷璐?constants/exchangeRates锛屽彇浠ｅ悇椤甸潰鍐呰仈鐨?// `marketValue * EXCHANGE_RATES[currency]` 鏁ｈ惤鍐欐硶锛岀粺涓€鎹㈢畻鍙ｅ緞銆?//
import { getRate } from "@/constants/exchangeRates";

/** 灏嗘寚瀹氬竵绉嶉噾棰濇崲绠椾负浜烘皯甯侊紙鍏冿級 */
export function toCNY(amount: number, currency = "CNY"): number {
  return amount * getRate(currency);
}

/** 灏嗕汉姘戝竵閲戦鎹㈢畻涓虹洰鏍囧竵绉?*/
export function fromCNY(amountCNY: number, currency: string): number {
  const rate = getRate(currency);
  return rate === 0 ? 0 : amountCNY / rate;
}

/**
 * 鍗冨垎浣嶆牸寮忓寲锛堟暣鏁板垎瀛樺偍鍦烘櫙璇风敤鍚庣 Money 宸ュ叿绫昏浆鎹㈠悗鍐嶄紶鍏ワ級銆? * @param value 鏁板€? * @param fractionDigits 灏忔暟浣嶏紝榛樿 2
 * @param symbol 璐у竵绗﹀彿锛岄粯璁?楼
 */
export function formatCurrency(
  value: number,
  fractionDigits = 2,
  symbol = "楼",
): string {
  const n = Number.isFinite(value) ? value : 0;
  const text = n.toLocaleString("zh-CN", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
  return `${symbol}${text}`;
}
```
