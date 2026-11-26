/**
 * 「常用能力」的记忆：按最近点击排序，不足时用默认项补齐。
 *
 * 为什么值得单独一个文件：这是本页唯一的跨会话本地状态（写 localStorage），
 * 混在 AgentHero 里会把「怎么呈现」和「记住什么」缠在一起——后者要处理
 * 存储不可用、脏数据、上限截断三件事，放在展示组件里最容易被后来的改动绕过。
 *
 * 口径：
 * - 只记**非主入口**的点击。主入口永远是那张大卡，记进来会和它自己重复。
 * - 上限 {@link MAX_RECENT} 与「常用」位的槽数一致：记多了没有位置放，
 *   而且会让「最近用过」退化成第二份全量清单。
 * - 存储不可用（隐私模式 / 禁用 cookie）时**不抛错、不降级成空**：本次会话内
 *   仍然按记录顺序排，只是下次进来回到默认。记录本身是一次排序偏好，
 *   丢失的代价远小于让页面崩掉。
 */

import { computed, ref } from "vue";

/** 与 AgentHero 的「常用」槽数一致；改这里必须同步那三个位置 */
const MAX_RECENT = 3;

const STORAGE_KEY = "fm.agent.recentCapabilities";

function readStored(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((x): x is string => typeof x === "string")
      .slice(0, MAX_RECENT);
  } catch {
    return []; // 脏数据 / 无存储权限：当没记录过
  }
}

export function useRecentCapabilities(defaultKeys: readonly string[]) {
  const recent = ref<string[]>(readStored());

  /** 记一次点击：置顶去重，超出上限截断 */
  function record(key: string): void {
    const next = [key, ...recent.value.filter(k => k !== key)].slice(
      0,
      MAX_RECENT
    );
    recent.value = next;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // 写失败只影响「下次进来」的顺序，本次会话内已生效
    }
  }

  /**
   * 常用位的最终 key 序列：最近点过的在前，不足的按 defaultKeys 补齐。
   * 补齐要跳过已出现的 key，否则同一项会占两个槽。
   */
  const pinned = computed<string[]>(() => {
    const out = [...recent.value];
    for (const key of defaultKeys) {
      if (out.length >= MAX_RECENT) break;
      if (!out.includes(key)) out.push(key);
    }
    return out.slice(0, MAX_RECENT);
  });

  return { pinned, record };
}
