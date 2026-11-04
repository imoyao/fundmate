/**
 * 「折叠时滚动展示」偏好（#watchlist 指数个性化设置里的开关）。
 *
 * 模块级单例：弹窗里改，顶栏即时生效，无需事件回传（与 useIndexBarSelection 同形）。
 * 默认开启；仅本机 localforage，不上云——纯视图偏好，与账号无关。
 *
 * 关掉后折叠态不做动画，退回「可横向滚动的静态条」。注意系统级的
 * `prefers-reduced-motion` 仍然独立生效（本 composable 不覆盖它）：
 * 系统要求减弱动效时，即使这里开着也不滚动。
 */
import { ref, watch, type Ref } from "vue";
import { localForage } from "@/utils/localforage";

const STORAGE_KEY = "watchlist-index-bar-motion";

const enabled = ref(true);
let loadStarted = false;
let hydrated = false;
let watchStarted = false;

function load(): void {
  if (loadStarted) return;
  loadStarted = true;
  localForage()
    .getItem<boolean>(STORAGE_KEY)
    .then(v => {
      if (typeof v === "boolean") enabled.value = v;
      hydrated = true;
    })
    .catch(() => {
      hydrated = true;
    });
}

function ensureWatch(): void {
  if (watchStarted) return;
  watchStarted = true;
  watch(enabled, next => {
    // 加载完成前不回写，避免「挂载瞬间默认 true 覆盖已持久化的 false」
    if (!hydrated) return;
    localForage()
      .setItem<boolean>(STORAGE_KEY, next)
      .catch(() => {
        /* 本地写失败不阻塞交互 */
      });
  });
}

export function useIndexBarMotionPref(): { enabled: Ref<boolean> } {
  load();
  ensureWatch();
  return { enabled };
}
