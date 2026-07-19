// frontend/src/composables/useAssetSearch.ts
import { ref } from "vue";
import { searchSecurities } from "@/api/securities";
import { searchFunds } from "@/api/funds";

export function useAssetSearch() {
  const loading = ref(false);
  const results = ref<any[]>([]);
  let timer: ReturnType<typeof setTimeout> | null = null;

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

        results.value = items;
        callback?.(items);
      } catch {
        results.value = [];
        callback?.([]);
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
