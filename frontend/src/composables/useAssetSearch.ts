// frontend/src/composables/useAssetSearch.ts
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { searchSecurities } from "@/api/securities";
import { searchFunds } from "@/api/funds";

export function useAssetSearch() {
  const loading = ref(false);
  const results = ref<any[]>([]);
  let timer: ReturnType<typeof setTimeout> | null = null;
  // 轻提示节流：异常态（如持续 401）会每 300ms 触发一次搜索，避免提示刷屏
  let lastErrorToastAt = 0;

  const toastSearchError = (msg: string) => {
    const now = Date.now();
    if (now - lastErrorToastAt > 5000) {
      lastErrorToastAt = now;
      ElMessage.warning(msg);
    }
  };

  const search = (query: string, callback?: (items: any[]) => void) => {
    if (!query || query.length < 1) {
      results.value = [];
      callback?.([]);
      return;
    }

    if (timer) clearTimeout(timer);

    timer = setTimeout(async () => {
      loading.value = true;
      try {
        const [secRes, fundRes] = await Promise.allSettled([
          searchSecurities(query),
          searchFunds(query)
        ]);

        const items: any[] = [];

        if (secRes.status === "fulfilled") {
          const data = (secRes.value as any)?.data ?? [];
          items.push(
            ...data.map((s: any) => ({
              code: s.symbol,
              name: s.name,
              type: s.type || "stock",
              market: s.market,
              venue: s.venue || "EXCHANGE"
            }))
          );
        }

        if (fundRes.status === "fulfilled") {
          const data = (fundRes.value as any)?.data ?? [];
          items.push(
            ...data.map((f: any) => ({
              code: f.code,
              name: f.name,
              type: "fund",
              market: "CN_A",
              venue: "OTC"
            }))
          );
        }

        // 两个数据源都失败（多为未登录/网络异常/后端 5xx）时，不再静默清空——
        // 否则用户只会看到空白下拉，误以为「系统里没有这只标的」（见 #821 P0-1 复盘）。
        // 仅部分失败时保留可用源结果，不弹提示以免打扰。
        if (secRes.status === "rejected" && fundRes.status === "rejected") {
          toastSearchError("资产搜索暂时不可用，请检查网络或稍后重试");
        }

        results.value = items;
        callback?.(items);
      } catch {
        results.value = [];
        callback?.([]);
        toastSearchError("资产搜索出错，请稍后重试");
      } finally {
        loading.value = false;
      }
    }, 300);
  };

  const clear = () => {
    if (timer) clearTimeout(timer);
    results.value = [];
  };

  return { loading, results, search, clear };
}
