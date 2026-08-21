// 枚举中文标签的单一获取入口。
//
// 为什么存在：持仓来源（Position.source）等枚举的中文 label 只在后端
// app.core.constants 定义（唯一真相源），前端不手抄第二份，避免两边漂移。
// 本 composable 从 GET /api/utils/enums 拉取并全局缓存，组件统一用这里拿 label。
//
// 用法：
//   const { positionSourceLabel } = useEnumLabels();
//   positionSourceLabel('explore'); // => '探市录入'
import { ref } from "vue";
import { http as request } from "@/utils/http";

let cachePromise: Promise<Record<string, Record<string, string>>> | null = null;

async function loadEnums(): Promise<Record<string, Record<string, string>>> {
  if (!cachePromise) {
    cachePromise = request
      .get<{ data: Record<string, Record<string, string>> }, unknown>(
        "/api/utils/enums/"
      )
      .then(res => res.data ?? ({} as Record<string, Record<string, string>>))
      .catch(() => ({}) as Record<string, Record<string, string>>);
  }
  return cachePromise;
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

  return { ensure, enums, positionSourceLabel };
}
