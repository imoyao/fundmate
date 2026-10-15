/**
 * 主界面类型快捷切换器的「外露类型」偏好（issue #1449，跨设备同步走 #1337 方案 B）。
 *
 * 与 useWatchlistColumnVisibility 同一套路：
 * - **模块级单例**：筛选条与「自定义快捷筛选」弹窗共享同一份外露列表，保存即刷新切换器；
 * - **本地 localforage 先行**：进页先渲染本地缓存，不等网络，避免每次进页闪烁默认值；
 * - **云端 user_preferences 合并**「最近修改时间取胜」（pickNewer，纯函数单测覆盖），
 *   云端较新则覆盖本地，本地较新则单向回传一次（不做同步环）；
 * - 云端不可达 / 未登录（401）/ 数据损坏一律静默回退本地或默认值，
 *   偏好配置不应阻塞自选页。
 */
import { ref, type Ref } from "vue";
import { localForage } from "@/utils/localforage";
import { getUserPreference, putUserPreference } from "@/api/userPreference";
import {
  pickNewer,
  stripStamp,
  type PrefStamp
} from "@/composables/watchlistColumnPrefs";
import {
  QUICK_FILTERS_PREF_KEY,
  defaultQuickFilters,
  normalizeQuickFilters,
  type QuickFiltersSettings
} from "@/composables/watchlistQuickFilters";

/** 模块级单例：筛选条与自定义弹窗共享同一份外露列表 */
const quickFilters: Ref<string[]> = ref(defaultQuickFilters());
let loadStarted = false;

/** 把一份偏好应用到内存状态（本地与云端合并共用；值非法则保持现状） */
function applySettings(saved: QuickFiltersSettings): void {
  const next = normalizeQuickFilters(saved.filters);
  if (next) quickFilters.value = next;
}

/** 本地时钟打点（ms）：updated_at 是本地合并策略的比较依据 */
function stampLocal(filters: string[]): QuickFiltersSettings {
  return { filters: [...filters], updated_at: Date.now() };
}

/** 读本地缓存（不应用，供合并比较）；无值 / 损坏返回 null */
async function readLocal(): Promise<PrefStamp<QuickFiltersSettings> | null> {
  try {
    const saved = await localForage().getItem<QuickFiltersSettings>(
      QUICK_FILTERS_PREF_KEY
    );
    if (saved) {
      const filters = normalizeQuickFilters(saved.filters);
      if (filters) {
        return {
          settings: { ...saved, filters },
          ts: saved.updated_at ?? 0
        };
      }
    }
  } catch {
    /* 读取失败按无偏好处理 */
  }
  return null;
}

/** 上云（fire-and-forget）：剥离本地时钟字段，服务端维护 updated_at */
function pushCloud(settings: QuickFiltersSettings): void {
  putUserPreference(QUICK_FILTERS_PREF_KEY, stripStamp(settings)).catch(() => {
    /* 云端不可达 / 未登录不影响会话内生效（本地已写） */
  });
}

/** 启动时恢复本地偏好并拉云端合并；失败静默回退默认（损坏不应锁死切换器） */
async function loadSync(): Promise<void> {
  const local = await readLocal();
  if (local) applySettings(local.settings);
  try {
    const res = await getUserPreference<QuickFiltersSettings>(
      QUICK_FILTERS_PREF_KEY
    );
    const cloud = res?.data;
    if (!cloud) {
      // 云端无值：本地有则回传一次（首访上云）；没有则维持默认
      if (local) pushCloud(local.settings);
      return;
    }
    const cloudFilters = normalizeQuickFilters(cloud.value?.filters);
    if (!cloudFilters) return; // 云端值损坏：维持已应用的本地 / 默认
    const cloudStamp: PrefStamp<QuickFiltersSettings> = {
      settings: { filters: cloudFilters },
      ts: cloud.updated_at ? Date.parse(cloud.updated_at) : 0
    };
    const winner = pickNewer(local, cloudStamp);
    if (!winner) return;
    applySettings(winner.settings);
    if (winner === cloudStamp) {
      // 云端更新：落到本地（带上云端时间戳，保证下次合并可比）
      localForage()
        .setItem<QuickFiltersSettings>(QUICK_FILTERS_PREF_KEY, {
          ...winner.settings,
          updated_at: cloudStamp.ts
        })
        .catch(() => {
          /* 本地写失败不阻塞 */
        });
    } else if (local && cloudStamp.ts !== local.ts) {
      // 本地更新：回传云端（单向收敛一次，不做同步环）
      pushCloud(local.settings);
    }
  } catch {
    /* 未登录（401）/网络失败：本地配置照常生效 */
  }
}

export interface WatchlistQuickFilters {
  /** 当前外露类型 key 列表（「全部」恒为首项，由渲染层拼接，不入偏好） */
  quickFilters: Ref<string[]>;
  /** 保存外露列表：归一化（去重 / 剔无效 / 空则回默认）后本地 + 云端双写 */
  setQuickFilters: (next: string[]) => void;
}

export function useWatchlistQuickFilters(): WatchlistQuickFilters {
  if (!loadStarted) {
    loadStarted = true;
    void loadSync();
  }

  function setQuickFilters(next: string[]): void {
    const normalized = normalizeQuickFilters(next) ?? defaultQuickFilters();
    quickFilters.value = normalized;
    const stamped = stampLocal(normalized);
    localForage()
      .setItem<QuickFiltersSettings>(QUICK_FILTERS_PREF_KEY, stamped)
      .catch(() => {
        /* 本地写失败不影响会话内生效 */
      });
    pushCloud(stamped);
  }

  return { quickFilters, setQuickFilters };
}
