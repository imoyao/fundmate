# 东财（akshare）反爬 / 不可达 — 调研结论与下一步方案

> 适用：任何人接手「行业拥挤度 / 乖离率 / 任何依赖 akshare 东方财富接口的数据为空」问题时，
> 先读本文，避免重蹈 2026-08-02 排查手册（bias-datasource-troubleshooting.md）的旧结论。
> 创建：2026-08-05 ｜ 状态：根因已定位，baostock 替代源已验证可达，业务切换待做。
>
> ⚠️ 本文位于 `docs/working-notes/`，已被 `docs/.vitepress/config.mjs` 的 `srcExclude` 排除出构建产物，
> 仅仓库源码可见，不对外发布。

---

## 0. 一句话结论（先讲清楚）

akshare 取东方财富数据在本机失败，**有两个叠加的、性质不同的根因**：

1. **【已修复·代码层】系统代理残留**：本机残留边车代理（`127.0.0.1:31181`，代理软件关了但系统代理开关 /
   Winsock 仍把它解析为 https 代理），`requests` 默认 `trust_env=True` 继承系统代理，把东财请求甩到已死本地端口
   → `ProxyError`。**修复**：`backend/app/core/requests_patch.py` 中 `Session` 初始化加
   `self.trust_env = False` + `self.proxies = {'http': None, 'https': None}`，强制直连。
2. **【未解决·网络层】东财出口 IP 封**：即使强制直连、屏蔽代理，`80.push2.eastmoney.com` 与 `push2.eastmoney.com`
   仍直接 `RemoteDisconnected`（远端主动掐断）。判读落在 `diag_em.py` 「A 与 B 都失败（非 Proxy）→ 出口 IP 被封」。
   家庭宽带出口 IP 已被东财按 IP 限流/临时封。**代理开关都试过不行，正是因为这个根因在 IP 层，换不换代理都没用。**

> 旧排查手册（2026-08-02）把根因归结为「东财限流/IP 封 + DevSidecar 代理 TLS 干扰」，其中
> **「DevSidecar TLS 干扰」已被推翻**——今天实测是「系统代理残留（端口 31181）」而非 TLS 干扰，
> 且代理关了残留仍在。请勿再沿「退出 DevSidecar 看是否恢复」这条线排查。

---

## 1. 实证过程（可复现）

所有命令在 `backend/` 目录下用 **PDM 解释器**执行（禁止裸 `python`，否则跑错 venv）：

```bash
# 诊断东财连通性（已升级：先 import app 触发 patch，A/B 测的是「屏蔽系统代理后的真实直连能力」）
pdm run python scripts/diag_em.py

# 单独验证代理残留：裸 requests 在 import app 之前仍会继承系统代理报 ProxyError
pdm run python -c "import os; [print(k,'=',v) for k,v in os.environ.items() if 'PROXY' in k.upper()]"
pdm run python -c "import requests; print(requests.utils.get_environ_proxies('https://push2.eastmoney.com'))"
#   → 输出 https: http://127.0.0.1:31181   ← 这就是残留代理

# 验证 baostock 替代源可达（见 §3）
pdm run python scripts/_baostock_probe.py   # 输出日志 _baostock_probe.log：LOGIN_CODE 0 / success
```

### 1.1 diag_em.py 三段结果（2026-08-05 实测）

| 项 | 内容 | 结果 |
|---|---|---|
| A | `80.push2.eastmoney.com` 直连 | `RemoteDisconnected`（无 ProxyError，说明代理已屏蔽） |
| B | `push2.eastmoney.com` 直连 | `RemoteDisconnected` |
| C | 真实 akshare（patch 后） | `RemoteDisconnected` |

**判读**：A/B 均失败且**非 ProxyError** → 直连也不稳 → 出口 IP 被东财封。**ProxyError 已消失 = 代理残留修复生效**。

### 1.2 代码改动（本次已落地，尚未提交）

| 文件 | 改动 | 作用 |
|---|---|---|
| `backend/app/core/requests_patch.py` | `Session.__init__` 加 `trust_env=False` + `proxies=None` | 屏蔽系统代理残留，强制直连 |
| `backend/app/__init__.py` | `ak.set_option('request_interval', 3)` + `use_thread=False` | 防御性限速，降低频率触发限流 |
| `backend/scripts/diag_em.py` | `import app` 前置、`_get` 走 patched session、补充代理残留判读分支 | 让诊断测真值 |
| `backend/pyproject.toml`（PDM） | `pdm add baostock`（0.9.3） | 引入东财替代源 |

---

## 2. 关于「换数据源」的研判（重要，避免盲动）

你（用户）贴的三套方案中，**「限速 + 重试 + UA 伪装」我们基本已覆盖**（requests_patch 重试 + set_option 限速）；
**「换源」是对的，但要甄别，不要冒险引入未知源**：

- ❌ **westock-data（微信公众号文章的方案）/ AlphaFeed / a-stock-data 等第三方 CLI / 野路子源**：
  - 文章里的 `westock-data` 走腾讯自选股，只能覆盖**申万一级 31 行业**，且**不返历史百分位**，需本地拉 5 年算；
  - 它是**命令行工具**（非 Python 库），backend 要 `subprocess` 调用，进程管理/错误处理/版本依赖脆弱；
  - 上游仓库与长期维护存疑。**与项目「能白嫖就不算 + 不冒险引入未知源」原则冲突，明确不引入。**
- ✅ **baostock（已装、已验证可达）**：免费、Python 库、覆盖全 A 股行业分类与行情，**服务器非东财**，可绕开 IP 封；
  这是代码里 `industry_crowding.py` 早已预留的 `BENCHMARK_SOURCES` 之一（之前只是没装依赖，分支走不到）。
- ✅ **tushare Pro**：需 token，免费版限次，代码已支持 `TUSHARE_TOKEN` 环境变量切换（沙箱网络不可达时降级）。

---

## 3. baostock 验证结果（下一步方案的支点）

```text
# scripts/_baostock_probe.py 输出（_baostock_probe.log）
START
IMPORT_OK 00.9.30
LOGIN_CODE 0
LOGIN_MSG success
ROW True
ROW True
ROW True
BAOSTOCK_OK rows=3
```

**结论：baostock 在当前网络下登录成功、行业查询正常返回，可作东财替代源。**

### 3.1 关键差异（决定下一步怎么写代码）

baostock 解决「东财被封」，但**不直接等价于替换现有东财接口**：

| 需求 | 现有东财接口 | baostock 对应能力 | 落地成本 |
|---|---|---|---|
| 行业指数 PE/PB（文章诉求） | `ak.stock_a_industry_pe_ratio` 等 | baostock 无现成行业指数估值；需 `query_history_k_data_plus` 拉成分股自算 | 中 |
| **行业拥挤度分母 = 全 A 中位 PB** | `ak.stock_a_all_pb()`（legulegu）+ 东财兜底 | baostock `query_stock_industry` 给个股行业分类（申万一二三级），**非行业 PB** | 需用成分股行情自算中位 PB |
| 个股/指数行情 | `ak.*_em` | baostock `query_history_k_data_plus` | 低 |

即：baostock 是可靠的**底层源**，但「行业 PB / 全 A 中位 PB」要补一段「用成分股算 PB」的自算逻辑，
不能直接替换 `stock_a_all_pb` 那条。

---

## 4. 下一步方案（给后人认领）

### 方案主线：用 baostock 替换东财兜底 / 主源（绕开 IP 封）

1. **行业拥挤度分母切换**（优先级高，对应 tech-debt 第 63 条同一链路）：
   - 在 `backend/app/services/thermometer/industry_crowding.py` 的 `BENCHMARK_SOURCES` 中，
     把 `baostock` 从「预留」提升为**可用默认源**：实现「baostock 成分股 → 算全 A 中位 PB」的取数函数，
     替代东财 `push2.eastmoney.com` 实时 PB 兜底（该兜底现已因 IP 封失效）。
   - 保留 legulegu `stock_a_all_pb()` 为第一优先级（免费、非东财），东财退为最后兜底且已知失效可降级。
2. **bias / 乖离率主源**：当前 `index_zh_a_hist` 等强依赖东财。评估改用 baostock
   `query_history_k_data_plus`（日线）替代东财日线抓取；腾讯/新浪源（`stock_zh_a_hist_tx` 等）
   可作次级备选，但需退出代理实网验证（旧手册方向 C）。
3. **容灾缓存**：`scripts/prefetch_all_pb.py` 落盘 `cache/all_pb.csv` 已在，baostock 数据同样应预取缓存，
   减少实时请求频次（既降东财压力，也降低对单一源的依赖）。

### 不做的（明确排除）

- ❌ 不引入 westock-data / AlphaFeed 等未知 CLI 源。
- ❌ 不靠「退出代理」解决（代理已屏蔽残留，且 IP 封与代理无关）。
- ❌ 不依赖东财官方付费 API（Choice 等），除非用户后续拍板。

### 验收标准

- `industry_crowding` 在屏蔽系统代理 + 东财 IP 封闭的当前网络下，仍能产出 `crowding_pct`（baostock 兜底生效）。
- `diag_em.py` 的 ProxyError 分支永久消除（代理残留已根治）。
- 新增 baostock 取数逻辑有单元测试覆盖（mock 登录 + 成分股，不依赖实时网络）。

---

## 5. 相关文件索引

| 文件 | 角色 |
|---|---|
| `backend/app/core/requests_patch.py` | 全局请求补丁（host 重写 + 重试 + **trust_env/proxies 强制直连**） |
| `backend/app/__init__.py` | 启动限速 `ak.set_option('request_interval', 3)` |
| `backend/scripts/diag_em.py` | 东财连通性诊断（已升级为测真值） |
| `backend/scripts/_baostock_probe.py` | baostock 可达性探针（临时验证脚本，用完删） |
| `backend/app/services/thermometer/industry_crowding.py` | 行业拥挤度（含 BENCHMARK_SOURCES，baostock 预留） |
| `docs/bias-datasource-troubleshooting.md` | 乖离率排查手册（**2026-08-02 旧结论部分过时，见 §0 修正**） |
| `docs/spec/tech-debt.md` | 第 63 条「行业拥挤度分母」已修复（legulegu 403 根因，与本文件 IP 封根因为两条线） |

---

## 6. 参考

- akshare issue #7027（80.push2 子域被封）：https://github.com/akfamily/akshare/issues/7027
- akshare issue #7099（RemoteDisconnected 频发）：https://github.com/akfamily/akshare/issues/7099
- baostock 文档：http://baostock.com
- 申万行业数据替代方案（微信公众号，westock-data，本文**不采纳**）：https://mp.weixin.qq.com/s/z4BKwHHe_j7HqT3_MP503Q
