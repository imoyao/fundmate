/**
 * 统一基金净值获取服务
 *
 * 所有页面统一调用此接口，不要在各自组件里单独封装。
 *
 * 策略：
 *   1. 先调后端 /api/funds/nav/（后端自身有 xalpha 兜底）
 *   2. 后端失败 / 无数据 → JSONP 调天天基金 lsjz 公开接口
 *   3. 都失败 → 返回 null，前端不阻塞（当天未出净值时正常）
 */

import { calcFundNav, getFundNavByDate } from "@/api/funds";
import type { FundNavPoint, FundNavResult } from "@/api/types";

/**
 * 获取指定基金在指定日期的单位净值。
 *
 * @param fundCode 基金代码，如 "005827"
 * @param targetDate 目标日期 YYYY-MM-DD
 * @returns 净值结果，无数据时返回 null
 */
export async function fetchFundNav(
  fundCode: string,
  targetDate: string,
): Promise<FundNavResult | null> {
  if (!fundCode || !targetDate) return null;

  // 1. 尝试后端 API（#948：改用 GET /api/funds/{code}/nav/?date= 单只接口，与契约一致）
  try {
    const res = await getFundNavByDate(fundCode, targetDate);
    const point = res?.data ?? null;
    if (point?.unit_nav && point.unit_nav > 0) {
      return {
        unit_nav: point.unit_nav,
        date: point.date || targetDate,
        source: "backend",
      };
    }
  } catch (e) {
    console.warn("[fundNav] 后端获取失败，尝试公开接口:", e);
  }

  // 2. 尝试天天基金公开接口（JSONP）
  try {
    const publicResult = await fetchFromEastmoney(fundCode, targetDate);
    if (publicResult) {
      return { ...publicResult, source: "eastmoney" };
    }
  } catch (e) {
    console.warn("[fundNav] 公开接口获取失败:", e);
  }

  // 3. 都失败（当天未出净值 / 非交易日 / 网络问题）
  return null;
}

/* ─────────────── 批量版本 ─────────────── */

/**
 * 批量获取多只基金在指定日期的净值。
 *
 * 后端批量优先，后端未返回的基金逐个走天天基金 JSONP 兜底。
 * 返回 { fund_code: unit_nav } 映射，拿不到的基金不在 map 中。
 *
 * @param fundCodes 基金代码数组，如 ["005827", "110011"]
 * @param targetDate 目标日期 YYYY-MM-DD
 * @returns { fund_code: unit_nav }
 */
export async function fetchFundNavBatch(
  fundCodes: string[],
  targetDate: string,
): Promise<Record<string, number>> {
  const navMap: Record<string, number> = {};
  if (!fundCodes.length || !targetDate) return navMap;

  // 1. 批量调后端
  const backendFound = new Set<string>();
  try {
    const res = await calcFundNav(fundCodes, targetDate);
    const list = res?.data ?? [];
    if (Array.isArray(list)) {
      list.forEach((item) => {
        if (item.unit_nav && item.unit_nav > 0 && item.fund_code) {
          navMap[item.fund_code] = Number(item.unit_nav);
          backendFound.add(item.fund_code);
        }
      });
    }
  } catch (e) {
    console.warn("[fundNav] 后端批量获取失败:", e);
  }

  // 2. 后端未返回的基金，逐个走天天基金 JSONP 兜底（3 个一批并发）
  const missing = fundCodes.filter((code) => !backendFound.has(code));
  for (let i = 0; i < missing.length; i += 3) {
    const batch = missing.slice(i, i + 3);
    await Promise.all(
      batch.map(async (code) => {
        try {
          const result = await fetchFromEastmoney(code, targetDate);
          if (result) {
            navMap[code] = result.unit_nav;
          }
        } catch {
          // 单个失败不阻塞
        }
      }),
    );
  }

  return navMap;
}

/* ─────────────── 天天基金 JSONP 兜底 ─────────────── */

/**
 * JSONP 调用天天基金历史净值接口。
 *
 * 接口：api.fund.eastmoney.com/f10/lsjz
 * 返回 { Data: { LSJZList: [{ FSRQ, DWJZ, LJJZ, ... }] } }
 */
/** 东方财富净值接口返回结构（外部 JSONP：仅对已知字段做最小类型约束） */
interface EastmoneyNavItem {
  FSRQ: string;
  DWJZ: string;
  LJJZ?: string;
}
interface EastmoneyNavResponse {
  Data?: { LSJZList?: EastmoneyNavItem[] };
}

function fetchFromEastmoney(
  fundCode: string,
  targetDate: string,
): Promise<{ unit_nav: number; date: string } | null> {
  return new Promise((resolve) => {
    const callbackName = `__fundNavCb_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
    const dateStr = targetDate.replace(/-/g, "");
    const url =
      `https://api.fund.eastmoney.com/f10/lsjz` +
      `?callback=${callbackName}` +
      `&fund_code=${encodeURIComponent(fundCode)}` +
      `&pageIndex=1&pageSize=1` +
      `&start_date=${dateStr}&end_date=${dateStr}`;

    const script = document.createElement("script");
    let settled = false;

    const cleanup = () => {
      delete (window as any)[callbackName];
      if (script.parentNode) script.parentNode.removeChild(script);
    };

    (window as any)[callbackName] = (data: EastmoneyNavResponse) => {
      if (settled) return;
      settled = true;
      cleanup();

      const list = data?.Data?.LSJZList;
      if (Array.isArray(list) && list.length > 0) {
        const item = list[0];
        const nav = parseFloat(item.DWJZ);
        if (nav && nav > 0) {
          resolve({
            unit_nav: nav,
            date: item.FSRQ || targetDate,
          });
          return;
        }
      }
      resolve(null);
    };

    script.src = url;
    script.onerror = () => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(null);
    };

    // 10 秒超时
    setTimeout(() => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(null);
    }, 10000);

    document.body.appendChild(script);
  });
}
