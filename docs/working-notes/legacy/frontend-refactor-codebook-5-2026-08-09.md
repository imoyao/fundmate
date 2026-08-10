# batch5 浠ｇ爜鎵嬪唽锛堝彲鐩存帴闃呰鐨勫叏閮ㄦ簮鐮侊級

> 鏈枃浠剁敱 `fundmate-optimization/batch5/` 涓嬪疄闄呬氦浠樻枃浠跺師鏍锋嫾鍚堬紝鐢ㄤ簬鍦ㄤ粎鏀寔 Markdown 鐨勫鎴风閲岄槄璇绘簮鐮併€?
> 鍏?11 涓枃浠躲€?

## `composables/inventory/context.ts`

```ts
// ============================================================================
// inventory 涓婁笅鏂囷細provide / inject 娉ㄥ叆閿?+ 绫诲瀷
// ----------------------------------------------------------------------------
// 澹崇粍浠?InventoryHome.vue 缁勮鍏ㄩ儴 composable 杩斿洖鍊硷紝缁熶竴 provide锛?// 瀛愮粍浠堕€氳繃 useInventoryContext() 娉ㄥ叆锛岄伩鍏?prop 閫忎紶涓庨噸澶嶅疄渚嬪寲銆?// 涓庢壒娆?2/3/4 鍚屼竴濂楁満鍒躲€?// ============================================================================
import { inject } from "vue";
import type { InjectionKey } from "vue";
import type { useInventoryData } from "./useInventoryData";
import type { useAssetEdit } from "./useAssetEdit";
import type { useInventoryStyles } from "./useInventoryStyles";

export interface InventoryContext {
  data: ReturnType<typeof useInventoryData>;
  assetEdit: ReturnType<typeof useAssetEdit>;
  styles: ReturnType<typeof useInventoryStyles>;
}

export const inventoryContextKey: InjectionKey<InventoryContext> = Symbol(
  "inventoryContext"
);

export function useInventoryContext(): InventoryContext {
  const ctx = inject(inventoryContextKey);
  if (!ctx) {
    throw new Error(
      "useInventoryContext() 蹇呴』鍦?InventoryHome.vue 鎻愪緵鐨?inventoryContextKey 涔嬩笅浣跨敤"
    );
  }
  return ctx;
}
```

## `composables/inventory/index.ts`

```ts
// ============================================================================
// inventory composables 缁熶竴鍑哄彛锛坆arrel锛?// ----------------------------------------------------------------------------
// import { useInventoryData, useInventoryContext } from "@/composables/inventory"
// ============================================================================
export * from "./types";
export * from "./useInventoryData";
export * from "./useAssetEdit";
export * from "./useInventoryStyles";
export * from "./context";
```

## `composables/inventory/types.ts`

```ts
// ============================================================================
// 璧勪骇鐩樼偣椤碉紙inventory锛夌被鍨嬪畾涔?// ----------------------------------------------------------------------------
// 鎶界鑷?frontend/src/views/asset/inventory/index.vue锛堝師 30.8KB 鍗曟枃浠剁粍浠讹級銆?// 鍛藉悕涓?@/api/assets銆丂/api/positions 杩斿洖缁撴瀯瀵归綈锛涘瓧娈典互鐪熷疄鍚庣涓哄噯銆?// ============================================================================

/** 璧勪骇澶х被 key锛堜笌 categories 甯搁噺鍙婅矾鐢?query.tab 瀵瑰簲锛?*/
export type CategoryKey =
  | "investment"
  | "cash"
  | "fixed"
  | "liability"
  | "receivable"
  | "insurance";

/** 澶х被 tab 瀹氫箟锛堟潵鑷?@/constants/categories锛岀敱鎵规1鎶藉彇鑴氭湰鐢熸垚锛?*/
export interface CategoryDef {
  key: CategoryKey;
  label: string;
  bgVar: string;
  borderVar: string;
  desc: string;
}

/** 璧勪骇瀛愮被鍨嬶紙鏉ヨ嚜 @/constants/assetTypes 鐨勬煇澶х被涓嬫暟缁勯」锛?*/
export interface AssetTypeDef {
  key: string;
  icon: string;
  label: string;
  color: string;
}

/** 璧勪骇璁板綍 */
export interface Asset {
  id: number;
  major_category?: string;
  amount?: number;
  notes?: string;
  [key: string]: any;
}

/** 鎸佷粨锛堟姇璧勭被锛?*/
export interface Position {
  id: number;
  code?: string;
  name?: string;
  market_value?: number;
  pnl?: number;
  type?: string;
  [key: string]: any;
}
```

## `composables/inventory/useAssetEdit.ts`

```ts
// ============================================================================
// useAssetEdit 鈥斺€?缂栬緫/鍒犻櫎璧勪骇寮圭獥 composable
// ----------------------------------------------------------------------------
// 鎶界鑷?inventory/index.vue 鐨勩€岀紪杈戣祫浜с€嶅璇濇閫昏緫銆?// 渚濊禆 core锛堝綋鍓嶅ぇ绫汇€佸埛鏂拌祫浜у垪琛?姒傝锛夈€?// ============================================================================
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { updateAsset, deleteAsset } from "@/api/assets";

type Core = ReturnType<typeof import("./useInventoryData").useInventoryData>;

export function useAssetEdit(core: Core) {
  const editAssetDialogVisible = ref(false);
  const savingAsset = ref(false);
  const editAssetForm = ref<{ id: number; amount: number; notes: string }>({
    id: 0,
    amount: 0,
    notes: ""
  });

  function openEditAssetDialog(row: { id: number; amount?: number; notes?: string }) {
    editAssetForm.value = {
      id: row.id,
      amount: row.amount ?? 0,
      notes: row.notes ?? ""
    };
    editAssetDialogVisible.value = true;
  }

  async function saveAssetEdit() {
    savingAsset.value = true;
    try {
      await updateAsset(editAssetForm.value.id, {
        amount: editAssetForm.value.amount,
        notes: editAssetForm.value.notes
      });
      editAssetDialogVisible.value = false;
      // 鍒锋柊褰撳墠鍒嗙被璧勪骇 + 姒傝
      await core.loadCategoryAssets(core.activeCategory.value);
      await core.fetchData();
      ElMessage.success("宸蹭繚瀛?);
    } finally {
      savingAsset.value = false;
    }
  }

  async function confirmDeleteAsset(row: { id: number }) {
    try {
      await ElMessageBox.confirm("纭畾鍒犻櫎璇ヨ祫浜э紵", "鎻愮ず", { type: "warning" });
    } catch {
      return;
    }
    await deleteAsset(row.id);
    await core.loadCategoryAssets(core.activeCategory.value);
    ElMessage.success("宸插垹闄?);
  }

  return {
    editAssetDialogVisible,
    savingAsset,
    editAssetForm,
    openEditAssetDialog,
    saveAssetEdit,
    confirmDeleteAsset
  };
}
```

## `composables/inventory/useInventoryData.ts`

```ts
// ============================================================================
// useInventoryData 鈥斺€?璧勪骇鐩樼偣椤点€屽叡浜牳銆峜omposable
// ----------------------------------------------------------------------------
// 鎶界鑷?inventory/index.vue 鐨勬暟鎹笌澶х被鍒囨崲閫昏緫锛?//   澶х被鐘舵€併€佹瑙堟眹鎬汇€佹姇璧勬寔浠撱€佸悇鍒嗙被璧勪骇缂撳瓨銆佹噿鍔犺浇銆佽矾鐢辫烦杞€?// 鍘熷唴鑱旂殑 categories / assetTypeMap 甯搁噺鏀逛负浠庢壒娆?鎶藉彇鐨勫父閲忔枃浠跺鍏?// 锛園/constants/categories銆丂/constants/assetTypes锛夛紱FX 鐩稿叧瑙佷笅鏂?TODO銆?// 鍔熻兘 composable锛堢紪杈戣祫浜с€佹牱寮忓姪鎵嬶級閫氳繃鍙傛暟娉ㄥ叆鏈牳锛岄伩鍏嶅惊鐜緷璧栥€?// ============================================================================
import { ref, computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { getAssets, getAssetsSummary } from "@/api/assets";
import { getPositions } from "@/api/positions";
// 鎵规1鎶藉彇鑴氭湰鐢熸垚鐨勫父閲忥紙鏇夸唬鍘熷唴鑱?categories / assetTypeMap锛?import { categories } from "@/constants/categories";
import { assetTypeMap } from "@/constants/assetTypes";
import type { CategoryKey, CategoryDef, AssetTypeDef, Asset, Position } from "./types";

export function useInventoryData() {
  const route = useRoute();
  const router = useRouter();

  // 鍒濆澶х被锛氫紭鍏堝彇璺敱 query.tab
  const activeCategory = ref<CategoryKey>((route.query.tab as CategoryKey) || "investment");

  // 鏁版嵁
  const assetsSummary = ref<Record<string, number>>({});
  const assetCache = ref<Record<string, Asset[]>>({});
  const currentAssets = ref<Asset[]>([]);
  const allPositions = ref<Position[]>([]);
  const investmentPage = ref(1);
  const pageSize = 10;
  const loading = ref(false);

  // 娲剧敓
  const activeCategoryDesc = computed(
    () => categories.find((c) => c.key === activeCategory.value)?.desc ?? ""
  );
  const activeAssetTypes = computed<AssetTypeDef[]>(
    () => assetTypeMap[activeCategory.value as CategoryKey] || []
  );
  // 鎶曡祫鎸佷粨鎸夌被鍨嬪垎缁勬眹鎬伙紙鎶曡祫鍒嗗竷鍗＄墖锛?  const investmentGroups = computed(() => {
    const map = new Map<string, { label: string; total: number }>();
    for (const p of allPositions.value) {
      const k = p.type || "other";
      const cur = map.get(k) || { label: k, total: 0 };
      cur.total += p.market_value || 0;
      map.set(k, cur);
    }
    return Array.from(map.values());
  });
  const paginatedInvestments = computed(() => {
    const start = (investmentPage.value - 1) * pageSize;
    return allPositions.value.slice(start, start + pageSize);
  });

  // 鍚?tab 鐨勯噾棰濆悎璁?  function getCategoryTotal(key: CategoryKey): number {
    if (key === "investment") {
      return allPositions.value.reduce((s, p) => s + (p.market_value || 0), 0);
    }
    return assetsSummary.value[key] ?? 0;
  }

  function getMajorCategoryLabel(key: CategoryKey): string {
    return categories.find((c) => c.key === key)?.label ?? key;
  }

  // 骞惰鎷夊彇鎸佷粨 + 姒傝
  async function fetchData() {
    loading.value = true;
    try {
      const [positions, summary] = await Promise.all([
        getPositions({ per_page: 9999 }),
        getAssetsSummary()
      ]);
      allPositions.value = positions?.items ?? positions?.data ?? positions?.list ?? [];
      assetsSummary.value = summary ?? {};
    } finally {
      loading.value = false;
    }
  }

  // 鎳掑姞杞介潪鎶曡祫绫昏祫浜э紙鎶曡祫绫昏蛋 positions锛屼笉鍦ㄦ鍔犺浇锛?  async function loadCategoryAssets(category: CategoryKey) {
    if (category === "investment") return;
    if (assetCache.value[category]) {
      if (category === activeCategory.value) currentAssets.value = assetCache.value[category];
      return;
    }
    const res = await getAssets({ major_category: category, per_page: 9999 });
    const list: Asset[] = res?.items ?? res?.data ?? res?.list ?? [];
    assetCache.value[category] = list;
    if (category === activeCategory.value) currentAssets.value = list;
  }

  function handleAddType(typeKey: string) {
    router.push({ path: "/asset/asset-entry", query: { type: typeKey } });
  }

  // 鍒囨崲澶х被锛氶噸缃姇璧勫垎椤?+ 鎳掑姞杞介潪鎶曡祫绫昏祫浜?  watch(activeCategory, (cat) => {
    investmentPage.value = 1;
    if (cat !== "investment") loadCategoryAssets(cat);
  });

  return {
    // 甯搁噺锛堟浛浠ｅ師鍐呰仈 categories / assetTypeMap锛?    categories,
    assetTypeMap,
    // 鐘舵€?    activeCategory,
    assetsSummary,
    assetCache,
    currentAssets,
    allPositions,
    investmentPage,
    pageSize,
    loading,
    // 娲剧敓
    activeCategoryDesc,
    activeAssetTypes,
    investmentGroups,
    paginatedInvestments,
    // 鍔ㄤ綔
    getCategoryTotal,
    getMajorCategoryLabel,
    fetchData,
    loadCategoryAssets,
    handleAddType
  };
}
```

## `composables/inventory/useInventoryStyles.ts`

```ts
// ============================================================================
// useInventoryStyles 鈥斺€?鐩樼偣椤垫牱寮?鏍囩鍔╂墜 composable
// ----------------------------------------------------------------------------
// 鎶界鑷?inventory/index.vue 鐨勭函灞曠ず鍨嬪姪鎵嬶細
//   getCategoryTabStyle锛坱ab 楂樹寒锛? getAllocLabel路Color路BgColor锛堥厤缃」閰嶈壊锛?
//   resolveCSSVar / getColorWithAlpha銆?// 浠呬緷璧?core.activeCategory锛堥珮浜垽鏂級涓?@/constants 鐨?ALLOCATION_OPTIONS锛?// 涓嶈Е纰颁换浣?API銆傜粍浠堕€氳繃 useInventoryContext().styles 璋冪敤銆?// ============================================================================
import { ALLOCATION_OPTIONS } from "@/constants";
import type { CategoryKey } from "./types";

type Core = ReturnType<typeof import("./useInventoryData").useInventoryData>;

// ALLOCATION_OPTIONS 褰㈠ { value, label, colorVar }[]锛堜互鐪熷疄甯搁噺瀹氫箟涓哄噯锛?interface AllocOption {
  value: string;
  label: string;
  colorVar?: string;
}

export function useInventoryStyles(core: Core) {
  function resolveCSSVar(name: string): string {
    if (typeof document === "undefined") return "";
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function getColorWithAlpha(colorVar: string, alpha: number): string {
    const varName = colorVar.replace(/^var\(/, "").replace(/\)$/, "");
    const hex = resolveCSSVar(varName);
    if (!/^#[0-9a-fA-F]{6}$/.test(hex)) return colorVar;
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function getCategoryTabStyle(key: CategoryKey) {
    const active = core.activeCategory.value === key;
    const def = core.categories.find((c) => c.key === key);
    return {
      background: active && def ? `var(${def.bgVar})` : "transparent",
      borderColor: active && def ? `var(${def.borderVar})` : "var(--el-border-color)",
      color: active ? "var(--el-color-primary)" : "inherit",
      fontWeight: active ? 600 : 400
    };
  }

  function getAllocOption(key: string): AllocOption | undefined {
    return (ALLOCATION_OPTIONS as AllocOption[]).find((o) => o.value === key);
  }
  function getAllocLabel(key: string): string {
    return getAllocOption(key)?.label ?? key;
  }
  function getAllocColor(key: string): string {
    const o = getAllocOption(key);
    return o?.colorVar ? `var(${o.colorVar})` : "var(--el-color-primary)";
  }
  function getAllocBgColor(key: string): string {
    return getColorWithAlpha(getAllocColor(key), 0.12);
  }

  return {
    resolveCSSVar,
    getColorWithAlpha,
    getCategoryTabStyle,
    getAllocLabel,
    getAllocColor,
    getAllocBgColor
  };
}
```

## `views/asset/inventory/InventoryHome.vue`

```vue
<script setup lang="ts">
// ============================================================================
// 璧勪骇鐩樼偣椤碉紙閲嶆瀯鍚庣殑澹崇粍浠讹級
// ----------------------------------------------------------------------------
// 鐢?30.8KB 鐨?inventory/index.vue 閲嶆瀯鑰屾潵锛?//   - 鏁版嵁 / 澶х被鍒囨崲       鈫?useInventoryData锛坈ategories/assetTypeMap 鏀逛粠甯搁噺瀵煎叆锛?//   - 缂栬緫/鍒犻櫎璧勪骇寮圭獥     鈫?useAssetEdit
//   - 鏍峰紡/鏍囩鍔╂墜          鈫?useInventoryStyles
// 鍏ㄩ儴 composable 杩斿洖鍊肩粍瑁呬负 InventoryContext 鍚?provide锛?// 瀛愮粍浠堕€氳繃 useInventoryContext() 娉ㄥ叆锛岄伩鍏?prop 閫忎紶涓庨噸澶嶅疄渚嬪寲銆?// 娉ㄦ剰锛氭湰椤垫棤 ECharts锛堝師鏂囦欢鏈氨鏃犲浘琛級锛屾棤闇€ useEchartsLifecycle銆?// ============================================================================
import { onMounted, provide } from "vue";
import { InfoFilled } from "@element-plus/icons-vue";
import {
  useInventoryData,
  useAssetEdit,
  useInventoryStyles,
  inventoryContextKey
} from "@/composables/inventory";
import CategoryTabs from "./components/CategoryTabs.vue";
import InvestmentPanel from "./components/InvestmentPanel.vue";
import AssetList from "./components/AssetList.vue";
import AssetEditDialog from "./components/AssetEditDialog.vue";

const data = useInventoryData();
const assetEdit = useAssetEdit(data);
const styles = useInventoryStyles(data);

const { activeCategory, activeCategoryDesc } = data;

provide(inventoryContextKey, { data, assetEdit, styles });

onMounted(async () => {
  await data.fetchData();
  if (data.activeCategory.value !== "investment") {
    await data.loadCategoryAssets(data.activeCategory.value);
  }
});
</script>

<template>
  <div class="inventory-home">
    <!-- 椤靛ご -->
    <div class="mb-10">
      <h1 class="text-2xl font-semibold">鍏ㄩ潰鐩樼偣</h1>
      <p class="text-gray-500">閫夋嫨璧勪骇澶х被锛屽揩閫熷綍鍏ユ垨瀵煎叆</p>
    </div>

    <!-- 澶х被 tab -->
    <CategoryTabs />

    <!-- 澶х被鎻忚堪 -->
    <div
      v-if="activeCategoryDesc"
      class="mt-4 flex items-center gap-2 rounded border border-dashed p-3 text-sm text-gray-500"
    >
      <el-icon><InfoFilled /></el-icon>
      <span>{{ activeCategoryDesc }}</span>
    </div>

    <!-- 鍐呭鍖猴細鎶曡祫绫?/ 鍏朵粬绫?涓ょ鍦烘櫙 -->
    <div class="content-area mt-6">
      <InvestmentPanel v-if="activeCategory === 'investment'" />
      <AssetList v-else />
    </div>

    <!-- 缂栬緫璧勪骇寮圭獥 -->
    <AssetEditDialog />
  </div>
</template>

<style scoped>
.inventory-home {
  padding: 16px;
}
</style>
```

## `views/asset/inventory/components/AssetEditDialog.vue`

```vue
<script setup lang="ts">
// 缂栬緫璧勪骇寮圭獥锛堟娊绂昏嚜 inventory/index.vue 鐨勭紪杈戣祫浜у璇濇锛?import { useInventoryContext } from "@/composables/inventory";

const { assetEdit } = useInventoryContext();
const { editAssetDialogVisible, savingAsset, editAssetForm, saveAssetEdit } = assetEdit;
</script>

<template>
  <el-dialog v-model="editAssetDialogVisible" title="缂栬緫璧勪骇">
    <el-form label-width="64px">
      <el-form-item label="閲戦">
        <el-input-number v-model="editAssetForm.amount" :min="0" class="w-full" />
      </el-form-item>
      <el-form-item label="澶囨敞">
        <el-input v-model="editAssetForm.notes" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="editAssetDialogVisible = false">鍙栨秷</el-button>
      <el-button type="primary" :loading="savingAsset" @click="saveAssetEdit">淇濆瓨</el-button>
    </template>
  </el-dialog>
</template>
```

## `views/asset/inventory/components/AssetList.vue`

```vue
<script setup lang="ts">
// 閫氱敤璧勪骇鍒楄〃闈㈡澘锛堟娊绂昏嚜 inventory/index.vue 鐨?Scenario B锛?import IconifyIconOffline from "@/components/ReIcon";
import { useInventoryContext } from "@/composables/inventory";

const { data, assetEdit } = useInventoryContext();
const { currentAssets, activeAssetTypes, handleAddType } = data;
const { openEditAssetDialog, confirmDeleteAsset } = assetEdit;
</script>

<template>
  <div>
    <!-- 蹇嵎鎿嶄綔锛氭寜褰撳墠澶х被鐨勮祫浜у瓙绫诲瀷娣诲姞 -->
    <h3 class="mb-2 mt-4 text-base font-medium">蹇嵎鎿嶄綔</h3>
    <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
      <div
        v-for="t in activeAssetTypes"
        :key="t.key"
        class="flex cursor-pointer items-center gap-2 rounded border p-3 hover:border-primary"
        @click="handleAddType(t.key)"
      >
        <IconifyIconOffline :icon="t.icon" />
        <span>{{ t.label }}</span>
      </div>
    </div>

    <!-- 璧勪骇鏄庣粏 -->
    <h3 class="mb-2 mt-4 text-base font-medium">璧勪骇鏄庣粏</h3>
    <el-table :data="currentAssets">
      <el-table-column label="鍚嶇О" prop="name" />
      <el-table-column label="閲戦" prop="amount" width="160" />
      <el-table-column label="澶囨敞" prop="notes" />
      <el-table-column label="鎿嶄綔" width="160" fixed="right">
        <template #default="{ row }">
          <el-button text size="small" @click="openEditAssetDialog(row)">缂栬緫</el-button>
          <el-button text size="small" type="danger" @click="confirmDeleteAsset(row)">
            鍒犻櫎
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!currentAssets.length" description="鏆傛棤璧勪骇璁板綍" />
  </div>
</template>
```

## `views/asset/inventory/components/CategoryTabs.vue`

```vue
<script setup lang="ts">
// 璧勪骇澶х被 tab 鏍忥紙鎶界鑷?inventory/index.vue 椤堕儴鍒嗙被鍒囨崲锛?import MoneyDisplay from "@/components/MoneyDisplay";
import { useInventoryContext } from "@/composables/inventory";

const { data, styles } = useInventoryContext();
const { categories, activeCategory, getCategoryTotal } = data;
const { getCategoryTabStyle } = styles;
</script>

<template>
  <div class="grid grid-cols-3 gap-4 md:grid-cols-6">
    <div
      v-for="cat in categories"
      :key="cat.key"
      class="category-tab cursor-pointer rounded border p-3 text-center transition"
      :style="getCategoryTabStyle(cat.key)"
      @click="activeCategory = cat.key"
    >
      <div class="text-sm">{{ cat.label }}</div>
      <div class="mt-1 text-lg font-semibold">
        <MoneyDisplay :value="getCategoryTotal(cat.key)" />
      </div>
      <div v-if="activeCategory === cat.key" class="mt-1 text-xs">鈻?/div>
    </div>
  </div>
</template>

<style scoped>
.category-tab:hover {
  border-color: var(--el-color-primary);
}
</style>
```

## `views/asset/inventory/components/InvestmentPanel.vue`

```vue
<script setup lang="ts">
// 鎶曡祫绫诲唴瀹归潰鏉匡紙鎶界鑷?inventory/index.vue 鐨?Scenario A锛?import { useRouter } from "vue-router";
import MoneyDisplay from "@/components/MoneyDisplay";
import ProductDisplay from "@/components/ProductDisplay";
import { useInventoryContext } from "@/composables/inventory";

const router = useRouter();
const { data } = useInventoryContext();
const { allPositions, investmentGroups, paginatedInvestments, investmentPage, pageSize } = data;

function goManual() {
  router.push("/investment/manual");
}
function goImport() {
  router.push("/inventory/investment/import");
}
</script>

<template>
  <div>
    <!-- 鎶曡祫鍒嗗竷 -->
    <h3 class="mb-2 mt-4 text-base font-medium">鎶曡祫鍒嗗竷</h3>
    <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
      <div v-for="g in investmentGroups" :key="g.label" class="rounded border p-3">
        <div class="text-gray-500">{{ g.label }}</div>
        <div class="mt-1 font-semibold">
          <MoneyDisplay :value="g.total" />
        </div>
      </div>
    </div>

    <!-- 蹇嵎鎿嶄綔 -->
    <h3 class="mb-2 mt-4 text-base font-medium">蹇嵎鎿嶄綔</h3>
    <div class="grid grid-cols-2 gap-3">
      <div class="cursor-pointer rounded border p-4 text-center hover:border-primary" @click="goManual">
        鎵嬪姩璁拌处
      </div>
      <div class="cursor-pointer rounded border p-4 text-center hover:border-primary" @click="goImport">
        瀵煎叆瀵硅处
      </div>
    </div>

    <!-- 鎸佷粨鏄庣粏 -->
    <h3 class="mb-2 mt-4 text-base font-medium">鎸佷粨鏄庣粏</h3>
    <el-table :data="paginatedInvestments" height="400">
      <el-table-column label="浜у搧">
        <template #default="{ row }">
          <ProductDisplay :code="row.code" :name="row.name" />
        </template>
      </el-table-column>
      <el-table-column label="甯傚€? prop="market_value" width="140" />
      <el-table-column label="鐩堜簭" prop="pnl" width="140" />
    </el-table>
    <div class="mt-3 flex justify-end">
      <el-pagination
        v-model:current-page="investmentPage"
        :page-size="pageSize"
        :total="allPositions.length"
        layout="total, prev, pager, next"
      />
    </div>
  </div>
</template>
```
