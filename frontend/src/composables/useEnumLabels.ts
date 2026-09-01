// 枚举中文标签的单一获取入口。
//
// 为什么存在：持仓来源（Position.source）等枚举的中文 label 只在后端
// app.core.constants / app.core.asset_types 定义（唯一真相源），前端不手抄第二份，避免两边漂移。
// 本 composable 从 GET /api/utils/enums 拉取并全局缓存，组件统一用这里拿 label。
//
// 资产类型（asset_type）与资产大类（major_category）的 label 同样来自后端 /enums/
// （asset_type / asset_category 两张映射），前端禁止硬编码第二份、禁止显示英文原键。
// 前端镜像见 frontend/src/constants/assetType.ts，仅在枚举未拉取时作同步回退。
//
// 用法：
//   const { positionSourceLabel, assetTypeLabel } = useEnumLabels();
//   positionSourceLabel('explore'); // => '探市录入'
//   assetTypeLabel('bond');         // => '可转债'（后端实时来源，回退镜像）
import { ref } from "vue";
import { http as request } from "@/utils/http";
import {
  ASSET_TYPE_LABELS,
  ASSET_CATEGORY_LABELS
} from "@/constants/assetType";

let cachePromise: Promise<Record<string, Record<string, string>>> | null = null;
// 模块级已解析缓存：即使组件未触发 fetch，也能回退到前端镜像避免显示英文原键
let resolvedCache: Record<string, Record<string, string>> = {};

async function loadEnums(): Promise<Record<string, Record<string, string>>> {
  if (!cachePromise) {
    cachePromise = request
      .get<{ data: Record<string, Record<string, string>> }, unknown>(
        "/api/utils/enums/"
      )
      .then(res => {
        resolvedCache =
          res.data ?? ({} as Record<string, Record<string, string>>);
        return resolvedCache;
      })
      .catch(() => ({}) as Record<string, Record<string, string>>);
  }
  return cachePromise;
}

/** 资产类型 → 中文 label（后端 /enums/asset_type 为唯一真相源，未拉取时回退前端镜像）。未知值回退镜像/原值。 */
export function assetTypeLabel(type: string | undefined | null): string {
  if (!type) return "";
  return resolvedCache?.asset_type?.[type] ?? ASSET_TYPE_LABELS[type] ?? type;
}

/** 资产大类 → 中文 label（后端 /enums/asset_category 为唯一真相源，未拉取时回退前端镜像）。未知值回退镜像/原值。 */
export function assetCategoryLabel(
  category: string | undefined | null
): string {
  if (!category) return "";
  return (
    resolvedCache?.asset_category?.[category] ??
    ASSET_CATEGORY_LABELS[category] ??
    category
  );
}

export function useEnumLabels() {
  const enums = ref<Record<string, Record<string, string>>>({});

  async function ensure() {
    if (!Object.keys(enums.value).length) {
      enums.value = await loadEnums();
    }
    return enums.value;
  }

  /** 取持仓来源中文 label；未知值原样返回，避免展示空 */
  function positionSourceLabel(source: string | undefined | null): string {
    if (!source) return "";
    return enums.value?.position_source?.[source] ?? source;
  }

  return {
    ensure,
    enums,
    positionSourceLabel,
    assetTypeLabel,
    assetCategoryLabel
  };
}
