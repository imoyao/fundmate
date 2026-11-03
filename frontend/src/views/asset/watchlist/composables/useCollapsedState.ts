/**
 * 折叠偏好（#watchlist 顶栏块）：默认折叠（省首屏版面），但记忆用户最近一次
 * 的展开/收起选择，下次进入沿用。
 *
 * 仅本机 localforage（不接云端）：纯视图偏好，与账号/设备无关，
 * 不需要 useWatchlistColumnVisibility 那套云端同步。
 *
 * hydration 完成前不回写，避免「挂载瞬间默认 false 覆盖已持久化的 true」。
 */
import { ref, watch, type Ref } from "vue";
import { localForage } from "@/utils/localforage";

const PREFIX = "watchlist-collapsed:";

export function useCollapsedState(storageKey: string): {
  expanded: Ref<boolean>;
} {
  const expanded = ref(false);
  const key = PREFIX + storageKey;
  let hydrated = false;

  localForage()
    .getItem<boolean>(key)
    .then(v => {
      if (typeof v === "boolean") expanded.value = v;
      hydrated = true;
    })
    .catch(() => {
      hydrated = true;
    });

  watch(expanded, next => {
    if (!hydrated) return;
    localForage()
      .setItem<boolean>(key, next)
      .catch(() => {
        /* 本地写失败不阻塞交互 */
      });
  });

  return { expanded };
}
