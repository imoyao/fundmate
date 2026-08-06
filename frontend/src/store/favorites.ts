import { defineStore } from "pinia";
import { getFavorites } from "@/api/watchlist";
import type { FavoriteItem } from "@/types/favorites";

export const useFavoritesStore = defineStore("favorites", {
  state: () => ({
    list: [] as FavoriteItem[],
    loading: false,
    filter: "all" as "all" | "stock" | "fund" | "manager" | "portfolio",
    sort: "updated_at" as "updated_at" | "favorite_at" | "holding_days",
    search: "",
    pagination: {
      page: 1,
      pageSize: 12,
      total: 0
    }
  }),
  getters: {
    filteredList(state): FavoriteItem[] {
      let result = state.list;
      if (state.filter !== "all") {
        result = result.filter(item => item.type === state.filter);
      }
      if (state.search) {
        const kw = state.search.toLowerCase();
        result = result.filter(
          item =>
            item.symbol.toLowerCase().includes(kw) ||
            item.display_name.toLowerCase().includes(kw)
        );
      }
      // 排序
      if (state.sort === "favorite_at") {
        result.sort(
          (a, b) =>
            new Date(b.favorite_at || "").getTime() -
            new Date(a.favorite_at || "").getTime()
        );
      } else if (state.sort === "holding_days") {
        result.sort((a, b) => (b.holding_days || 0) - (a.holding_days || 0));
      } else {
        result.sort(
          (a, b) =>
            new Date(b.updated_at || "").getTime() -
            new Date(a.updated_at || "").getTime()
        );
      }
      return result;
    }
  },
  actions: {
    async fetchList() {
      this.loading = true;
      try {
        const res = await getFavorites();
        this.list = (res as any).data ?? [];
        this.pagination.total = this.list.length;
      } catch (e) {
        console.error(e);
      } finally {
        this.loading = false;
      }
    },
    setFilter(type: "all" | "stock" | "fund" | "manager" | "portfolio") {
      this.filter = type;
    },
    setSort(sort: "updated_at" | "favorite_at" | "holding_days") {
      this.sort = sort;
    },
    setSearch(keyword: string) {
      this.search = keyword;
    }
  }
});
