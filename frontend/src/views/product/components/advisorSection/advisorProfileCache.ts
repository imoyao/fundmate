import { getAdvisorProfile, type AdvisorProfileResult } from "@/api/products";

/**
 * 投顾档案的**页内单次取数**（缓存 + in-flight 去重）。
 *
 * ## 为什么需要
 *
 * 重设计把「投顾组合」从一张卡拆成六个区块，其中 **概览**要提到走势之前
 * （结论先行），其余五块仍在页面下部。两处都需要同一份档案（名称 / 平台 / 机构 /
 * 净值 / 指标 / 策略 / 来源链接），而它们是**同一页面上的两个挂载点**——
 * 各自取数就是同一次浏览发两次 `advisor-profile` 请求。
 *
 * ## 边界
 *
 * - 只缓存 `advisor-profile`：它是**平台档案**（组合名称、机构、成立日、指标），
 *   一次浏览期间不会变；用户自己的持仓 / 对比数据**不在此列**，那些每次都取——
 *   用户可能刚在别处改过持仓，缓存它们会给出过期结论。
 * - 失败**不缓存**：一次网络抖动不该让「稍后再看」也看不到。
 * - 没有 TTL：缓存随页面模块存活，刷新页面即清空。给档案加 TTL 只会在
 *   「停留很久后切回另一个组合再切回来」时多打一次无意义的请求。
 */

const cache = new Map<string, AdvisorProfileResult>();
const inflight = new Map<string, Promise<AdvisorProfileResult>>();

/** 取档案（命中缓存直接返回；并发调用共用同一个在途请求） */
export function fetchAdvisorProfile(
  code: string
): Promise<AdvisorProfileResult> {
  const hit = cache.get(code);
  if (hit) return Promise.resolve(hit);
  const running = inflight.get(code);
  if (running) return running;

  const request = getAdvisorProfile({ code })
    .then(res => {
      cache.set(code, res.data);
      return res.data;
    })
    .finally(() => {
      inflight.delete(code);
    });
  inflight.set(code, request);
  return request;
}

/** 仅测试用：清空缓存，避免用例之间互相污染 */
export function resetAdvisorProfileCache() {
  cache.clear();
  inflight.clear();
}
