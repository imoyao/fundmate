// 数据源函数：JSONP 封装、超时、并发、降级
const JSONP_TIMEOUT = 5000;
const BATCH_SIZE = 5;
const BATCH_DELAY = 500; // ms

export interface Quote {
  symbol: string;
  type: "stock" | "fund";
  currentPrice: number;
  changePct: number;
  updateTime: string;
  source: "tiantian" | "sina" | "tencent";
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
      // ✅ 1. 首先立刻读取全局挂载的变量
      const raw = (window as any)[varName];

      // ✅ 2. 读取之后再清理 DOM 和全局变量
      cleanup();

      // ✅ 3. 开始解析数据
      if (!raw) {
        resolve(null);
        return;
      }

      const parts = raw.split("~");
      if (type === "fund") {
        // 基金格式：代码~名称~...~当前净值~累计净值~涨跌幅~日期
        if (parts.length >= 8) {
          const price = parseFloat(parts[5]); // 当前净值
          const changePct = parseFloat(parts[7]); // 涨跌幅
          if (!isNaN(price)) {
            resolve({
              symbol: code,
              type: "fund",
              currentPrice: price,
              changePct: !isNaN(changePct) ? changePct : 0,
              updateTime:
                parts[8] || new Date().toISOString().slice(0, 10) + " 00:00",
              source: "tencent"
            });
            return;
          }
        }
      } else {
        // 股票格式：52个字段，索引 3=当前价，32=涨跌幅，30=时间
        if (parts.length > 33) {
          const price = parseFloat(parts[3]);
          const changePct = parseFloat(parts[32]);
          if (!isNaN(price)) {
            const timeStr = parts[30] || "";
            const timeFormatted =
              timeStr.length >= 14
                ? timeStr.slice(8, 10) +
                  ":" +
                  timeStr.slice(10, 12) +
                  ":" +
                  timeStr.slice(12, 14)
                : "";
            resolve({
              symbol: code,
              type: "stock",
              currentPrice: price,
              changePct: !isNaN(changePct) ? changePct : 0,
              updateTime: timeFormatted
                ? new Date().toISOString().slice(0, 10) + " " + timeFormatted
                : new Date().toISOString(),
              source: "tencent"
            });
            return;
          }
        }
      }
      resolve(null);
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

// ─── 判断是否今日 ───
function isToday(timeStr: string): boolean {
  if (!timeStr) return false;
  const dateStr = timeStr.split(" ")[0];
  const today = new Date().toISOString().slice(0, 10);
  return dateStr === today;
}

// ─── 批量请求（并发控制） ───
export async function batchFetchQuotes(
  codes: { symbol: string; type: "stock" | "fund" }[]
): Promise<Map<string, Quote>> {
  const results = new Map<string, Quote>();
  // 注意：Promise.all 依然并发执行，但 fetchTiantian 内部已经有了队列排队机制，所以无惧并发覆盖。
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
