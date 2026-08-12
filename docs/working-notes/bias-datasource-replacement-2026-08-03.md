# 乖离度数据源替换方案（借鉴 daily_stock_analysis）（2026-08-03）

> 性质：内部备忘（`docs/working-notes/` 屏蔽出构建，不对外）。
> 调研日期：2026-08-03
> 状态：**已实跑验证（本会话内 requests 直连实测，附结果表）**
> 关联：`backend/app/services/bias/calculator.py`（`PriceFetcher`）、`daily_stock_analysis/data_provider/`
> **文档关系**：端点清单与实时状态以 [external-datasource-reference-2026-08-03](./external-datasource-reference-2026-08-03.md) 为准；本文只记录乖离度改造决策与专属代码。通用排查/熔断玩法见 [datasource-priority-plan-2026-08-03](./datasource-priority-plan-2026-08-03.md)。

## 一、阻塞点定位（事实）

`backend/app/services/bias/calculator.py` 的 `PriceFetcher.fetch()`（L146–164）把所有价格获取**硬编进 AKShare**：

| 品种 | 调用 | 取数列 |
|---|---|---|
| 指数 / 申万行业 | `ak.index_zh_a_hist` | 收盘 |
| ETF | `ak.fund_etf_hist_em` | 收盘 |
| 股票 | `ak.stock_zh_a_hist` | 收盘 |
| 场外基金 | `ak.fund_open_fund_info_em` | 单位净值 / 累计净值 |

乖离率**数学本身没问题**（`logbias` / EMA20 / `bias_to_position` 全是纯函数）。**只有"取数通道"坏了**——AKShare 那个具体函数接口不通。

## 二、daily_stock_analysis 里可借鉴的（事实，来自源码）

1. **腾讯直连端点** `data_provider/tencent_fetcher.py`：
   `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sh/sz/bj}{code},day,{start},{end},{bars},qfq`
   **免 token**，返回 qfq 日 K（date/open/close/high/low/volume）。覆盖 A 股 **股票 / ETF / 指数**。这是该仓库的"最终兜底"源（priority=5）。
2. **efinance** `data_provider/efinance_fetcher.py`：包装东方财富 `push2his.eastmoney.com/api/qt/stock/kline/get`，**免 token**，覆盖 **股票 + ETF** 历史（收盘列名为 `收盘`）。但该类的指数只取实时、无历史。
3. **多源故障切换架构** `data_provider/base.py` + `__init__.py`：策略模式 + 优先级有序链 + 异常自动降级 + 熔断。默认优先级（无 TUSHARE_TOKEN）：**efinance(0) → akshare(1) → pytdx(2) → baostock(3) → tencent(5 兜底)**。
4. **关键认知**：AKShare 本质是对 东财 / 腾讯 / 新浪 等公开上游的封装。AKShare 某个函数坏了，**上游往往还能直接调**——腾讯源就是这么做的。

## 三、解决方案：只换"通道"，不动算法（已实跑验证）

保留 `logbias` / `bias_to_position` 全部纯函数，只把 `PriceFetcher.fetch()` 的 transport 换成直连上游。端点细节、Referer 要求与实时状态见 [external-datasource-reference-2026-08-03](./external-datasource-reference-2026-08-03.md) §二.A.③/④，此处仅记分工与实测结论：

- **腾讯直连**：股票 / ETF / 宽基指数（sh/sz/bj 前缀），免 token、极稳。
- **东财 push2his + Referer**：申万一级行业（secid `90.xxxxx`）及全指数兜底；需带 `Referer` 头并对偶发连接中断重试。
- **关键约束**：申万行业腾讯**不覆盖**（实测 0 行），只能走东财 `90.x`。

### 实测结果表（与 external-datasource-reference §一 总览一致；本会话 requests 直连）

| 品种 | 代码 | 腾讯直连 | 东财 push2his(+Referer) |
|---|---|---|---|
| 沪深300 | sh000300 / 1.000300 | ✅ 82 行, 收 4611.08 | ✅ 5242 行, 收 4612.03 |
| 上证指数 | sh000001 / 1.000001 | ✅ 82 行, 收 3831.15 | ✅ 8696 行, 收 3831.68 |
| 贵州茅台 | sh600519 | ✅ 81 行, 收 1358.98 | —(非指数, 不测) |
| 沪深300ETF | sh510300 | ✅ 81 行, 收 4.60 | —(非指数, 不测) |
| 创业板指 | sz399006 / 0.399006 | ✅ 82 行, 收 3501.90 | ✅ 3928 行, 收 3503.99 |
| **申万农林(一级)** | sh801010 / 90.801010 | ❌ 0 行（**腾讯不覆盖**） | ✅ 1180 行, 收 943.90 |

> 结论：**腾讯覆盖 A 股股票/ETF/宽基；申万行业腾讯为空，只能走东财 push2his(secid 90.x)**。东财偶发 `RemoteDisconnected` 连接中断，加 Referer + 2 秒退避重试（≤4 次）即可稳定取数。

### 可直接粘贴的 transport 代码

```python
import time, requests

_TENCENT = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
_EASTMONEY = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_HEAD_T = {"User-Agent": "Mozilla/5.0"}
_HEAD_E = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
           "Referer": "https://quote.eastmoney.com/"}


def _tencent_symbol(code: str) -> str:
    code = code.strip()
    if code.startswith(("sh", "sz", "bj")):
        return code
    return "sh" + code if code[0] in ("6", "5", "9") else "sz" + code


def fetch_close_tencent(symbol: str, days: int = 90) -> list[float] | None:
    """股票 / ETF / 宽基指数。返回收盘价序列(最新在末位)；失败 None。"""
    import datetime
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days + 10)
    sym = _tencent_symbol(symbol)
    param = f"{sym},day,{start:%Y-%m-%d},{end:%Y-%m-%d},800,qfq"
    try:
        r = requests.get(_TENCENT, params={"param": param},
                         headers=_HEAD_T, timeout=8)
        item = r.json().get("data", {}).get(sym, {})
        rows = item.get("qfqday") or item.get("day") or []
        return [float(x[2]) for x in rows if isinstance(x, list) and len(x) >= 3] or None
    except Exception:
        return None


def fetch_close_eastmoney(secid: str, days: int = 90) -> list[float] | None:
    """指数兜底 / 申万行业(secid="90.xxxxx")。带 Referer + 退避重试。"""
    params = {"secid": secid, "fields1": "f1,f2,f3", "fields2": "f51,f53",
              "klt": "101", "fqt": "1", "beg": "0", "end": "20500101"}
    for _ in range(4):
        try:
            r = requests.get(_EASTMONEY, params=params,
                             headers=_HEAD_E, timeout=8)
            kl = (r.json().get("data") or {}).get("klines") or []
            closes = [float(x.split(",")[1]) for x in kl if "," in x]
            if closes:
                return closes[-days:] or closes
        except Exception:
            time.sleep(2)
    return None
```

> 场内（ETF/股票/宽基）优先 `fetch_close_tencent`；申万行业走 `fetch_close_eastmoney("90." + code)`；东财失败时腾讯可作宽基兜底。

## 四、缺口处理（已对应解法）

- **申万一级行业**：已由东财 `push2his` secid `90.xxxxx` 实测解决（90.801010 = 1180 行）。腾讯不覆盖，勿走腾讯。
- **场外基金净值**：腾讯/东财历史均**不含基金净值**。复用多多贝已有的 `DailyWorth` 同步（xalpha 拉取的单位净值），不碰 AKShare 基金函数。乖离度对场外基金若需日频净值，单独接东财基金净值端点（或等 DailyWorth 补齐）。
- **稳定性**：腾讯极稳；东财偶发连接中断，已用"Referer + 最多 4 次 2 秒退避"兜底。建议后续把取数升级为"腾讯主 / 东财兜底"的优先级链 + 简单熔断，彻底消除单点故障。

## 五、推荐落地步骤

1. `PriceFetcher` 股票/ETF/宽基分支 → `fetch_close_tencent`（解除 ~80% 阻塞，含持仓/自选）。
2. 申万行业分支 → `fetch_close_eastmoney("90." + code)`。
3. 场外基金分支 → 改用 `DailyWorth` 已同步净值，删除 AKShare 基金函数。
4. （可选）加"优先级链 + 熔断"：腾讯主、东财兜底，告别单点全挂。

## 六、边界

- **事实**：`PriceFetcher` 阻塞点是 AKShare 硬编码；腾讯直连免 token 覆盖股票/ETF/宽基（实测 5/6 通过）；东财 push2his + Referer 覆盖全部指数含申万（实测通过）；申万腾讯侧为空。**以上均为本会话 requests 实跑结果。**
- **推断**：AKShare 崩的函数其上游（腾讯/东财）仍可用，故直连可解；东财连接中断为限速/反爬，退避重试可破。
- **未知**：部署环境（海外免费机）出网是否被墙、是否需代理；端点长期稳定性；场外基金日频净值的东财端点细节。
