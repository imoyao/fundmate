/**
 * 「折叠时滚动展示」偏好（#watchlist 指数个性化设置里的开关）。
 *
 * 模块级单例：弹窗里改，顶栏即时生效，无需事件回传（与 useIndexBarSelection 同形）。
 * 默认开启；仅本机 localforage，不上云——纯视图偏好，与账号无关。
 *
 * 关掉后折叠态不做动画，退回「可横向滚动的静态条」。注意系统级的
 * `prefers-reduced-motion` 仍然独立生效（本 composable 不覆盖它）：
 * 系统要求减弱动效时，即使这里开着也不滚动。
 *
 * ## 写盘为什么改成显式 setter（2026-11-09）
 *
 * 旧版写盘是 `watch(enabled, …)`，而该 watcher 在**组件 setup() 里**创建 ⇒ 绑在调用方
 * （IndexBarMotionToggle）的 effect scope 上，弹窗所在页面一卸载就跟着 stop；模块级的
 * `watchStarted` 又挡住了重建 ⇒ 此后开关**改得动、存不住**。与
 * `useIndexBarSelection` 是同一个根因，故一并改成「用户动作里直接落盘」。
 *
 * `enabled` 保持**只读**暴露，写入走 `setEnabled`：这样「改值」只有一个入口，
 * 也就只有一个写盘点，不会再有第三个写入者。
 */
import { ref, type Ref } from "vue";
import { localForage } from "@/utils/localforage";

const STORAGE_KEY = "watchlist-index-bar-motion";

const enabled = ref(true);
let loadStarted = false;
/** 用户是否已在本会话内改过：读盘（可能迟到）不得覆盖用户刚做的选择 */
let userTouched = false;

function load(): void {
  if (loadStarted) return;
  loadStarted = true;
  localForage()
    .getItem<boolean>(STORAGE_KEY)
    .then(v => {
      if (userTouched) return;
      if (typeof v === "boolean") enabled.value = v;
    })
    .catch((err: unknown) => {
      // 读失败保持默认 true（仅显示），不写盘——写盘会把默认值固化成用户选择
      console.warn("[index-bar] 滚动开关读取失败，本次按默认开启处理", err);
    });
}

/** 唯一的写入口：改内存 + 落盘，与组件是否挂载无关 */
function setEnabled(next: boolean): void {
  userTouched = true;
  enabled.value = next;
  localForage()
    .setItem<boolean>(STORAGE_KEY, next)
    .catch((err: unknown) => {
      console.warn("[index-bar] 滚动开关落盘失败", err);
    });
}

export function useIndexBarMotionPref(): {
  enabled: Ref<boolean>;
  setEnabled: (next: boolean) => void;
} {
  load();
  return { enabled, setEnabled };
}
