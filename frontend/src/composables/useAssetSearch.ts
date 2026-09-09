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
  // 防抖被新输入打断时，必须把上一个未 settle 的 Promise 结算掉，
  // 否则 await 该 Promise 的调用方会永久挂起（#1362 评审 [主要]）。
  let pendingResolve: ((items: AssetSearchItem[]) => void) | null = null;
  // 请求序号：晚到的旧响应直接丢弃，避免覆盖新结果（#1362 评审 [次要]）。
  let seq = 0;

  /** 结算上一个 pending Promise（对已 settle 的 Promise 重复 resolve 无副作用） */
  const settlePending = (items: AssetSearchItem[]) => {
    if (pendingResolve) {
      const resolve = pendingResolve;
      pendingResolve = null;
      resolve(items);
    }
  };

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
    if (timer) clearTimeout(timer);
    // 上一次等待被新输入打断：先结算它的 Promise，避免调用方永久挂起
    settlePending([]);

    if (!query || query.length < 1) {
      results.value = [];
      callback?.([]);
      return Promise.resolve([]);
    }

    return new Promise<AssetSearchItem[]>(resolve => {
      pendingResolve = resolve;
      const mySeq = ++seq;
      timer = setTimeout(async () => {
        loading.value = true;
        try {
          const res = await searchAssets(query);
          // 已有更新的请求发出，本次结果过期 → 直接丢弃，不回写结果
          if (mySeq !== seq) return;
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
          if (mySeq !== seq) return; // 过期请求：不提示、不覆盖结果
          // 失败时不再静默清空语义由空数组 + 节流提示承担，
          // 避免用户误以为「系统里没有这只标的」（见 #821 P0-1 复盘）。
          results.value = [];
          callback?.([]);
          toastSearchError("资产搜索暂时不可用，请检查网络或稍后重试");
          resolve([]);
        } finally {
          if (pendingResolve === resolve) pendingResolve = null;
          // 仅最新请求收 loading，避免旧响应把新请求的 loading 提前置 false
          if (mySeq === seq) loading.value = false;
        }
      }, 300);
    });
  };

  const clear = () => {
    if (timer) clearTimeout(timer);
    settlePending([]);
    results.value = [];
  };

  return { loading, results, search, clear };
}
