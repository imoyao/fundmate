/**
 * useNavCache —— 前端净值缓存 composable（#1133）。
 *
 * 设计目标：
 * 1. **localStorage 持久化缓存**：净值日更（收盘后一次），缓存收益极高。
 *    关闭浏览器后数据仍在，下次打开直接命中，无需网络请求。
 * 2. **TTL 分级**：历史日期的净值永不变（长 TTL），当天净值短 TTL（10 分钟）。
 * 3. **批量优先**：所有公开方法接受符号列表，内部一次请求，
 *    禁止调用方循环单条请求（消除 N+1）。
 * 4. **降级链路**：本地缓存 → 天天基金 JSONP（直连）→ null（不阻塞）。
 *    **不走后端** `/api/funds/nav/`：该接口在基金数量多时会同步拉取远程，
 *    曾导致前端 10s 超时；JSONP 直连东财为纯前端行为，无后端阻塞风险。
 *
 * ## 使用方式
 *
 * ```ts
 * const { getNavs, getNav, loading } = useNavCache();
 *
 * // 批量获取（推荐）
 * const navMap = await getNavs(['005827', '110011'], '2026-08-28');
 * // { '005827': 2.03, '110011': 1.34 }
 *
 * // 单只获取（便捷封装）
 * const nav = await getNav('005827', '2026-08-28');
 * // 2.03 或 null
 * ```
 *
 * ## 与其他模块的关系
 *
 * - **后端 NavService** (`backend/app/services/nav_service.py`)：服务端统一入口，
 *   本 composable 是其前端对应物。两者共同构成「净值获取」的全链路统一。
 * - **api/fundNav.ts**：底层取数实现（JSONP 直连东财），
 *   本 composable 在上层加缓存编排，不重复实现取数逻辑。
 *
 * ## 缓存键格式
 *
 * `nav:${fundCode}:${date}` → `{ unit_nav: number, source: string, cached_at: number }`
 */

import { ref } from "vue";
import { fetchNavBatchFromEastmoney } from "@/api/fundNav";

// ──────────────────────────────────────────────
// 常量
// ──────────────────────────────────────────────

/** localStorage 键前缀 */
const CACHE_PREFIX = "nav:";

/**
 * TTL 配置（毫秒）。
 * - 历史净值：7 天（历史数据不变，长缓存安全）
 * - 当天净值：10 分钟（交易日盘中可能更新，但实际只在收盘后变一次）
 */
const TTL_HISTORY_MS = 7 * 24 * 60 * 60 * 1000; // 7 天
const TTL_TODAY_MS = 10 * 60 * 1000; // 10 分钟

// ──────────────────────────────────────────────
// 类型
// ──────────────────────────────────────────────

export interface NavCacheEntry {
  unit_nav: number;
  /** "backend" | "eastmoney" */
  source: string;
  /** 写入时间戳（Date.now()），用于 TTL 判定 */
  cached_at: number;
}

// ──────────────────────────────────────────────
// 内部工具
// ──────────────────────────────────────────────

function cacheKey(fundCode: string, date: string): string {
  return `${CACHE_PREFIX}${fundCode}:${date}`;
}

/** 判断目标日期是否为"今天"或"昨天"（需要短 TTL） */
function isRecent(dateStr: string): boolean {
  if (!dateStr) return true;
  const d = new Date(dateStr + "T00:00:00");
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = diffMs / (24 * 60 * 60 * 1000);
  return diffDays <= 2; // 今天或昨天视为"近期"
}

function getTTL(dateStr: string): number {
  return isRecent(dateStr) ? TTL_TODAY_MS : TTL_HISTORY_MS;
}

/** 从 localStorage 读取缓存（返回 null 表示未命中或已过期） */
function readCache(fundCode: string, date: string): NavCacheEntry | null {
  try {
    const raw = localStorage.getItem(cacheKey(fundCode, date));
    if (!raw) return null;
    const entry: NavCacheEntry = JSON.parse(raw);
    const ttl = getTTL(date);
    if (Date.now() - entry.cached_at > ttl) {
      // 过期，清理
      localStorage.removeItem(cacheKey(fundCode, date));
      return null;
    }
    return entry;
  } catch {
    return null;
  }
}

/** 写入 localStorage */
function writeCache(
  fundCode: string,
  date: string,
  unit_nav: number,
  source: string
): void {
  try {
    const entry: NavCacheEntry = {
      unit_nav,
      source,
      cached_at: Date.now()
    };
    localStorage.setItem(cacheKey(fundCode, date), JSON.stringify(entry));
  } catch {
    // localStorage 满了或其他异常，静默失败不阻塞
  }
}

// ──────────────────────────────────────────────
// Composable
// ──────────────────────────────────────────────

/**
 * 净值缓存 composable 实例。
 *
 * 注意：本 composable **无响应式状态依赖**（不需要 watch/computed），
 * 因为净值缓存是全局单例行为，与组件生命周期无关。
 * 返回的 `loading` 仅用于 UI 展示加载态。
 */
export function useNavCache() {
  const loading = ref(false);

  /**
   * 批量获取多只基金在指定日期的单位净值。
   *
   * 查询链路：localStorage 缓存 → 后端批量 API → 天天基金 JSONP 兜底
   *
   * @param fundCodes 基金代码列表
   * @param targetDate 目标日期 YYYY-MM-DD
   * @returns { fund_code: unit_nav } 映射，无数据的基金不在结果中
   */
  async function getNavs(
    fundCodes: string[],
    targetDate: string
  ): Promise<Record<string, number>> {
    const result: Record<string, number> = {};

    if (!fundCodes.length || !targetDate) return result;

    // 1. 先从缓存批量命中
    const missingCodes: string[] = [];
    for (const code of fundCodes) {
      const cached = readCache(code, targetDate);
      if (cached) {
        result[code] = cached.unit_nav;
      } else {
        missingCodes.push(code);
      }
    }

    // 2. 全部命中，直接返回
    if (missingCodes.length === 0) return result;

    // 3. 未命中的经 JSONP 直连东财（不经后端，避免阻塞）
    loading.value = true;
    try {
      const remoteMap = await fetchNavBatchFromEastmoney(
        missingCodes,
        targetDate
      );

      // 4. 取到的结果写回缓存（取不到的保持缺失，下次再试）
      for (const [code, nav] of Object.entries(remoteMap)) {
        result[code] = nav;
        writeCache(code, targetDate, nav, "eastmoney");
      }
    } catch (e) {
      console.warn("[useNavCache] JSONP 获取净值失败:", e);
    } finally {
      loading.value = false;
    }

    return result;
  }

  /**
   * 获取单只基金在指定日期的单位净值（便捷封装）。
   * 内部走批量路径，仅用于确实只有单只的场景。
   */
  async function getNav(
    fundCode: string,
    targetDate: string
  ): Promise<number | null> {
    const map = await getNavs([fundCode], targetDate);
    return map[fundCode] ?? null;
  }

  /**
   * 清除指定基金的所有缓存（用于手动刷新 / 数据修正场景）。
   * 不传参数则清除全部净值缓存。
   */
  function clearCache(fundCode?: string): void {
    try {
      if (fundCode) {
        // 清除该基金的所有日期缓存
        const keysToRemove: string[] = [];
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          if (key?.startsWith(`${CACHE_PREFIX}${fundCode}:`)) {
            keysToRemove.push(key);
          }
        }
        keysToRemove.forEach(k => localStorage.removeItem(k));
      } else {
        // 清除全部净值缓存
        const keysToRemove: string[] = [];
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          if (key?.startsWith(CACHE_PREFIX)) {
            keysToRemove.push(key);
          }
        }
        keysToRemove.forEach(k => localStorage.removeItem(k));
      }
    } catch {
      // 静默失败
    }
  }

  return { getNavs, getNav, clearCache, loading };
}

/**
 * 全局单例实例（供非组件上下文使用，如 utils / stores）。
 * 组件内请用 `useNavCache()` 获取新实例（Vue 会自动管理生命周期）。
 */
export const navCache = useNavCache();
