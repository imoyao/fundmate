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

import { calcFundNav } from "@/api/funds";

export interface FundNavResult {
  /** 单位净值 */
  unit_nav: number;
  /** 净值日期 YYYY-MM-DD */
  date: string;
  /** 数据来源 */
  source: "backend" | "eastmoney";
}

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

  // 1. 尝试后端 API
  try {
    const res = await calcFundNav([fundCode], targetDate);
    const list = (res as any)?.data ?? res;
    if (Array.isArray(list) && list.length > 0) {
      const item = list[0];
      if (item.unit_nav && item.unit_nav > 0) {
        return {
          unit_nav: Number(item.unit_nav),
          date: item.date || targetDate,
          source: "backend",
        };
      }
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

/* ─────────────── 天天基金 JSONP 兜底 ─────────────── */

/**
 * JSONP 调用天天基金历史净值接口。
 *
 * 接口：api.fund.eastmoney.com/f10/lsjz
 * 返回 { Data: { LSJZList: [{ FSRQ, DWJZ, LJJZ, ... }] } }
 */
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

    (window as any)[callbackName] = (data: any) => {
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
