// frontend/src/composables/useAssetSearch.ts
// 全局资产搜索唯一消费入口（#1286）：自选添加弹窗、探市添加区、未来组合购买
// 录入均经本 composable 调用后端聚合端点 /api/search/assets/，
// 页面组件禁止直调搜索 API（接口集中在 src/api/）。
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { searchAssets, type AssetSearchExtra } from "@/api/search";

/** 统一搜索结果项：code 与 symbol 同值（symbol 兼容既有以 symbol 取码的消费方） */
export interface AssetSearchItem {
  code: string;
  symbol: string;
  name: string;
  type: string;
  market: string;
  venue: string;
  extra?: AssetSearchExtra;
}

export function useAssetSearch() {
  const loading = ref(false);
  const results = ref<AssetSearchItem[]>([]);
  // 轻提示节流：异常态（如持续 401）会每 300ms 触发一次搜索，避免提示刷屏
  let lastErrorToastAt = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const toastSearchError = (msg: string) => {
    const now = Date.now();
    if (now - lastErrorToastAt > 5000) {
      lastErrorToastAt = now;
      ElMessage.warning(msg);
    }
  };

  /**
   * 防抖搜索（300ms），Promise resolve 后 results 已更新；
   * 兼容 el-autocomplete 的回调式消费（callback 可选）。
   */
  const search = (
    query: string,
    callback?: (items: AssetSearchItem[]) => void
  ): Promise<AssetSearchItem[]> => {
    if (!query || query.length < 1) {
      results.value = [];
      callback?.([]);
      return Promise.resolve([]);
    }

    if (timer) clearTimeout(timer);

    return new Promise(resolve => {
      timer = setTimeout(async () => {
        loading.value = true;
        try {
          const res = await searchAssets(query);
          const data = res?.data ?? [];
          const items: AssetSearchItem[] = data.map(d => ({
            code: d.code,
            symbol: d.code,
            name: d.name,
            type: d.asset_type,
            market: d.market ?? "",
            venue: d.venue ?? "",
            extra: d.extra
          }));
          results.value = items;
          callback?.(items);
          resolve(items);
        } catch {
          // 失败时不再静默清空语义由空数组 + 节流提示承担，
          // 避免用户误以为「系统里没有这只标的」（见 #821 P0-1 复盘）。
          results.value = [];
          callback?.([]);
          toastSearchError("资产搜索暂时不可用，请检查网络或稍后重试");
          resolve([]);
        } finally {
          loading.value = false;
        }
      }, 300);
    });
  };

  const clear = () => {
    if (timer) clearTimeout(timer);
    results.value = [];
  };

  return { loading, results, search, clear };
}
