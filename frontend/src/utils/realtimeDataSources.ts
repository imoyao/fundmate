// 数据源函数：JSONP 封装、超时、并发、降级
import { formatDate, formatDateTime } from "./date";

const JSONP_TIMEOUT = 5000;
const HISTORY_TIMEOUT = 8000; // 历史净值序列较大，单独放宽超时
// 行情批量并发：每批 5 个、批间 500ms。#808 设计稿写 3，实测 5 稳定无风控拦截，
// 经 #821 P2-8 裁决以实运行为准收敛为 5（留档见 docs/working-notes/explore-issue808-status-2026-08-19.md）。
const BATCH_SIZE = 5;
const BATCH_DELAY = 500; // ms

// 纯文本 GET（带超时），用于 pingzhongdata 这类「JS 变量赋值」接口（非标准 JSONP 回调）。
async function fetchTextWithTimeout(
  url: string,
  timeout = JSONP_TIMEOUT
): Promise<string> {
  const controller = new AbortController();
  const tid = setTimeout(() => controller.abort(), timeout);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.text();
  } finally {
    clearTimeout(tid);
  }
}

export interface Quote {
  symbol: string;
  type: "stock" | "fund";
  currentPrice: number;
  changePct: number;
  updateTime: string;
  source: "tiantian" | "sina" | "tencent" | "tiantian-batch";
  /** 基金名称（批量估值接口返回，可选；用于阶段 B 展示） */
  name?: string;
}

/**
 * 将内部标准化代码转为腾讯/新浪接口所需格式
 * 内部：SH600519, SZ000001, 000001 (基金)
 * 腾讯/新浪：sh600519, sz000001, jj000001
 */
function toExternalCode(symbol: string, type: "stock" | "fund"): string {
  if (type === "fund") {
    // 基金前缀需要加 jj
    return "jj" + symbol.replace(/^(SH|SZ)/i, "");
  }
  // 股票
  const upper = symbol.toUpperCase();
  if (upper.startsWith("SH")) {
    return "sh" + symbol.substring(2);
  } else if (upper.startsWith("SZ")) {
    return "sz" + symbol.substring(2);
  }
  // 没有前缀的数字代码，根据首位判断
  return (symbol.startsWith("6") ? "sh" : "sz") + symbol;
}

// 解析腾讯行情原始字符串（v_xxx 全局变量内容，~ 分隔）。
// 基金与股票字段索引不同，统一在此处理，供单只/批量两个入口复用。
function parseTencentQuote(
  raw: string | undefined,
  symbol: string,
  type: "stock" | "fund"
): Quote | null {
  if (!raw) return null;
  const parts = raw.split("~");
  if (type === "fund") {
    // 基金格式：代码~名称~...~当前净值~累计净值~涨跌幅~日期
    if (parts.length >= 8) {
      const price = parseFloat(parts[5]);
      const changePct = parseFloat(parts[7]);
      if (!isNaN(price)) {
        return {
          symbol,
          type: "fund",
          currentPrice: price,
          changePct: !isNaN(changePct) ? changePct : 0,
          updateTime: parts[8] || formatDate(new Date()) + " 00:00",
          source: "tencent"
        };
      }
    }
  } else {
    // 股票格式：52 个字段，索引 3=当前价，32=涨跌幅，30=时间
    if (parts.length > 33) {
      const price = parseFloat(parts[3]);
      const changePct = parseFloat(parts[32]);
      if (!isNaN(price)) {
        const timeStr = parts[30] || "";
        // 腾讯时间戳 YYYYMMDDHHMMSS：统一取 HH:mm（不带秒），与全站日期时间规范一致
        const timeFormatted =
          timeStr.length >= 14
            ? timeStr.slice(8, 10) + ":" + timeStr.slice(10, 12)
            : "";
        return {
          symbol,
          type: "stock",
          currentPrice: price,
          changePct: !isNaN(changePct) ? changePct : 0,
          updateTime: timeFormatted
            ? // 日期用本地时区（toISOString 取 UTC 日期凌晨会跨日），时间不带秒
              formatDate(new Date()) + " " + timeFormatted
            : formatDateTime(new Date()),
          source: "tencent"
        };
      }
    }
  }
  return null;
}

// ──────────────────────────────────────────────
// 修复 1：天天基金（加入队列避免 window.jsonpgz 被覆盖）
// ──────────────────────────────────────────────
let tiantianQueue: (() => void) | null = null;
async function fetchTiantian(code: string): Promise<Quote | null> {
  return new Promise(resolve => {
    const checkQueue = () => {
      if (tiantianQueue !== null) {
        // 如果队列正在占用，10ms 后重试
        setTimeout(checkQueue, 10);
        return;
      }
      // 锁定队列
      tiantianQueue = () => {};

      const script = document.createElement("script");
      const timeoutId = setTimeout(() => {
        cleanup();
        tiantianQueue = null;
        resolve(null);
      }, JSONP_TIMEOUT);

      function cleanup() {
        clearTimeout(timeoutId);
        delete (window as any).jsonpgz;
        if (script.parentNode) script.parentNode.removeChild(script);
      }

      // 注册天天基金固定全局回调
      (window as any).jsonpgz = (data: any) => {
        cleanup();
        tiantianQueue = null; // 释放队列
        if (data && data.fundcode && data.gsz) {
          resolve({
            symbol: code,
            type: "fund",
            currentPrice: parseFloat(data.gsz),
            changePct: parseFloat(data.gszzl || 0),
            updateTime: data.gztime,
            source: "tiantian"
          });
        } else {
          resolve(null);
        }
      };

      script.src = `https://fundgz.1234567.com.cn/js/${code}.js?rt=${Date.now()}`;
      script.onerror = () => {
        cleanup();
        tiantianQueue = null;
        resolve(null);
      };
      document.body.appendChild(script);
    };
    checkQueue();
  });
}

// ──────────────────────────────────────────────
// 修复 2：腾讯财经（改用 `<script>` 注入 + 读取全局变量 `v_xxx`）
// ──────────────────────────────────────────────
// ─── 腾讯财经 (备用) ───
async function fetchTencentData(
  code: string,
  type: "stock" | "fund"
): Promise<Quote | null> {
  return new Promise(resolve => {
    const fullCode = toExternalCode(code, type);
    const varName = `v_${fullCode}`;
    const script = document.createElement("script");
    const timeoutId = setTimeout(() => {
      cleanup();
      resolve(null);
    }, JSONP_TIMEOUT);

    function cleanup() {
      clearTimeout(timeoutId);
      // 移除 DOM
      if (script.parentNode) script.parentNode.removeChild(script);
      // 释放全局变量（注意：不能污染后续的请求，但必须在读取完后删）
      delete (window as any)[varName];
    }

    script.onload = () => {
      // 首先立刻读取全局挂载的变量，再清理 DOM 和全局变量
      const raw = (window as any)[varName];
      cleanup();
      resolve(parseTencentQuote(raw, code, type));
    };

    script.onerror = () => {
      cleanup();
      resolve(null);
    };
    script.src = `https://qt.gtimg.cn/q=${fullCode}`;
    document.body.appendChild(script);
  });
}

// ──────────────────────────────────────────────
// 修复 3：统一请求（优化优先级）
// ──────────────────────────────────────────────
// ──────────────────────────────────────────────
// 阶段 A（#990）：批量数据源（来自 jigu 复盘，见 docs/spec/realtime-data-source-switching.md）
// ──────────────────────────────────────────────

// 腾讯多 code 批量：一次请求拿全部（qt.gtimg.cn/q=sh600519,sz000001,...）
// 返回 Map<symbol, Quote>，未命中的不进 map（由调用方决定降级）。
async function fetchTencentBatch(
  symbols: string[],
  type: "stock" | "fund"
): Promise<Map<string, Quote>> {
  const result = new Map<string, Quote>();
  const valid = symbols
    .map(s => ({ symbol: s, full: toExternalCode(s, type) }))
    .filter(x => x.full);
  if (valid.length === 0) return result;

  return new Promise(resolve => {
    const varNames = valid.map(x => `v_${x.full}`);
    const script = document.createElement("script");
    const timeoutId = setTimeout(() => {
      cleanup();
      resolve(result);
    }, JSONP_TIMEOUT);

    function cleanup() {
      clearTimeout(timeoutId);
      if (script.parentNode) script.parentNode.removeChild(script);
      varNames.forEach(n => delete (window as any)[n]);
    }

    script.onload = () => {
      valid.forEach(({ symbol, full }) => {
        const raw = (window as any)[`v_${full}`];
        const q = parseTencentQuote(raw, symbol, type);
        if (q) result.set(symbol, q);
      });
      cleanup();
      resolve(result);
    };

    script.onerror = () => {
      cleanup();
      resolve(result);
    };
    script.src = `https://qt.gtimg.cn/q=${valid.map(x => x.full).join(",")}`;
    document.body.appendChild(script);
  });
}

// 天天基金批量估值（FundValuationLast）：一次最多 50 个 FCODES，带 10s 内存缓存去重，
// 避免同一轮并发重复请求。未返回的 code 通过 missing 暴露给调用方做降级（missing 不缓存）。
const FUND_VALUATION_LAST_BATCH_SIZE = 50;
const VALUATION_CACHE_TTL = 10000;
interface CachedValuation {
  time: number;
  map: Map<string, Quote>;
}
const valuationBatchCache = new Map<string, CachedValuation>();

export async function fetchFundValuationLastBatch(
  codes: string[]
): Promise<{ map: Map<string, Quote>; missing: string[] }> {
  const sorted = [...new Set(codes.map(c => c.toUpperCase()))].sort();
  const key = sorted.join(",");
  const cached = valuationBatchCache.get(key);
  if (cached && Date.now() - cached.time < VALUATION_CACHE_TTL) {
    // 命中缓存只复用成功结果；missing 不缓存（避免临时网络抖动把码误判为永久缺失），
    // 由调用方降级通道按限流重试。
    return { map: cached.map, missing: [] };
  }

  const result = new Map<string, Quote>();
  const missing = new Set<string>();
  const batches: string[][] = [];
  for (let i = 0; i < sorted.length; i += FUND_VALUATION_LAST_BATCH_SIZE) {
    batches.push(sorted.slice(i, i + FUND_VALUATION_LAST_BATCH_SIZE));
  }

  await Promise.all(
    batches.map(
      batch =>
        new Promise<void>(resolve => {
          const fcodes = batch.join(",");
          const cb = "__ttjjVal" + Math.random().toString(36).slice(2);
          const url = `https://fundcomapi.tiantianfunds.com/mm/newCore/FundValuationLast?FCODES=${fcodes}&FIELDS=FCODE,SHORTNAME,GSZZL,GZTIME,GSZ,NAV,PDATE&_=${Date.now()}`;
          const script = document.createElement("script");
          const timeoutId = setTimeout(() => {
            cleanup();
            batch.forEach(c => missing.add(c));
            resolve();
          }, JSONP_TIMEOUT);

          function cleanup() {
            clearTimeout(timeoutId);
            if (script.parentNode) script.parentNode.removeChild(script);
            delete (window as any)[cb];
          }

          (window as any)[cb] = (json: any) => {
            cleanup();
            const list: any[] = json?.data ?? [];
            const got = new Set<string>();
            for (const it of list) {
              const code = String(it.FCODE || "").toUpperCase();
              if (!code) continue;
              got.add(code);
              const price = parseFloat(it.GSZ);
              const changePct = parseFloat(it.GSZZL);
              if (!isNaN(price)) {
                result.set(code, {
                  symbol: code,
                  type: "fund",
                  currentPrice: price,
                  changePct: !isNaN(changePct) ? changePct : 0,
                  updateTime: it.GZTIME || formatDate(new Date()) + " 00:00",
                  source: "tiantian-batch",
                  name: it.SHORTNAME
                });
              }
            }
            batch.forEach(c => {
              if (!got.has(c.toUpperCase())) missing.add(c);
            });
            resolve();
          };

          script.onerror = () => {
            cleanup();
            batch.forEach(c => missing.add(c));
            resolve();
          };
          script.src = `${url}&callback=${cb}`;
          document.body.appendChild(script);
        })
    )
  );

  valuationBatchCache.set(key, { time: Date.now(), map: result });
  return { map: result, missing: [...missing] };
}

// 历史净值走势（pingzhongdata / 东方财富底层）：统一 Sparkline 历史源，
// 替代「前端本地轮询累积缓存」（用户久未登录/换设备会丢数据）。
// 返回按时间升序的净值序列，调用方按 rangeDays 切片。
const historyCache = new Map<string, { time: number; points: number[] }>();
const HISTORY_CACHE_TTL = 5 * 60 * 1000;

export async function fetchFundHistory(
  code: string,
  rangeDays = 30
): Promise<number[]> {
  const cached = historyCache.get(code);
  if (cached && Date.now() - cached.time < HISTORY_CACHE_TTL) {
    return cached.points;
  }
  const url = `https://fundgz.1234567.com.cn/pingzhongdata/${code}.js?_=${Date.now()}`;
  try {
    const text = await fetchTextWithTimeout(url, HISTORY_TIMEOUT);
    const m = text.match(/Data_netWorthTrend\s*=\s*(\[[\s\S]*?\]);/);
    if (!m) return [];
    const arr = JSON.parse(m[1]) as { y: number }[];
    const all = arr
      .map(p => Number(p.y))
      .filter(v => !isNaN(v))
      .reverse(); // 接口返回按时间降序，转升序
    const points = all.slice(0, rangeDays);
    historyCache.set(code, { time: Date.now(), points });
    return points;
  } catch (e) {
    console.warn("[realtime] 历史净值获取失败:", code, e);
    return [];
  }
}

// ─── 统一获取行情（支持智能类型重试降级） ───
export async function fetchQuote(
  code: string,
  type: "stock" | "fund"
): Promise<Quote | null> {
  // 1. 先尝试用户给定的 type
  if (type === "fund") {
    // 主：天天基金
    const tiantian = await fetchTiantian(code);
    if (tiantian && isToday(tiantian.updateTime)) return tiantian;
    // 备：腾讯基金
    const tencent = await fetchTencentData(code, type);
    if (tencent) return tencent;

    // 🔥【关键降级】如果基金接口没拿到，且代码以 SZ/SH 开头，尝试转换为股票抓取！
    if (/^(SZ|SH)/i.test(code)) {
      const tencentStock = await fetchTencentData(code, "stock");
      if (tencentStock) return tencentStock;
    }
  } else {
    // 主：腾讯股票
    const tencent = await fetchTencentData(code, type);
    if (tencent) return tencent;

    // 🔥【关键降级】如果股票接口没拿到，且代码是纯数字（没有前缀），尝试转换为基金抓取！
    if (!/^[A-Za-z]/.test(code)) {
      const tencentFund = await fetchTencentData(code, "fund");
      if (tencentFund) return tencentFund;
    }
  }

  return null; // 完全失败，由调用方降级到静态数据
}

// ─── 判断是否今日（本地时区；用 toISOString 取 UTC 日期在凌晨会跨日误判） ───
function isToday(timeStr: string): boolean {
  if (!timeStr) return false;
  const dateStr = timeStr.split(" ")[0];
  const now = new Date();
  const localDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(
    2,
    "0"
  )}-${String(now.getDate()).padStart(2, "0")}`;
  return dateStr === localDate;
}

// ─── 批量请求（阶段 A：分流批量源） ───
// 基金：优先天天批量估值（FundValuationLast，一次 50 个），未命中降级到单只 fundgz；
// 股票：腾讯多 code 批量（一次请求全部）。两类各只发 1~⌈N/50⌉ 次请求，远少于逐个抓取。
export async function batchFetchQuotes(
  codes: { symbol: string; type: "stock" | "fund" }[]
): Promise<Map<string, Quote>> {
  const results = new Map<string, Quote>();
  if (codes.length === 0) return results;

  const funds = codes.filter(c => c.type === "fund").map(c => c.symbol);
  const stocks = codes.filter(c => c.type === "stock").map(c => c.symbol);

  if (funds.length > 0) {
    const { map: fundMap, missing } = await fetchFundValuationLastBatch(funds);
    fundMap.forEach((q, sym) => results.set(sym, q));
    if (missing.length > 0) {
      // 降级：逐个走原 fetchQuote（fundgz 队列 + 腾讯基金/股票转换重试）
      const fb = await batchFetchQuotesFallback(
        missing.map(s => ({ symbol: s, type: "fund" as const }))
      );
      fb.forEach((q, sym) => {
        if (!results.has(sym)) results.set(sym, q);
      });
    }
  }

  if (stocks.length > 0) {
    const stockMap = await fetchTencentBatch(stocks, "stock");
    stockMap.forEach((q, sym) => results.set(sym, q));
  }

  return results;
}

// 原逐个抓取逻辑（保留作基金批量未命中的降级通道）。含基金→股票的智能类型重试。
async function batchFetchQuotesFallback(
  codes: { symbol: string; type: "stock" | "fund" }[]
): Promise<Map<string, Quote>> {
  const results = new Map<string, Quote>();
  for (let i = 0; i < codes.length; i += BATCH_SIZE) {
    const batch = codes.slice(i, i + BATCH_SIZE);
    const promises = batch.map(({ symbol, type }) =>
      fetchQuote(symbol, type).then(quote => {
        if (quote) results.set(symbol, quote);
      })
    );
    await Promise.allSettled(promises);
    if (i + BATCH_SIZE < codes.length) {
      await new Promise(resolve => setTimeout(resolve, BATCH_DELAY));
    }
  }
  return results;
}
