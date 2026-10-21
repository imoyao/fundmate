---
title: MCP 接入层设计
---

# MCP 接入层设计

> 状态：**已评审通过**（2026-10-21）。本文只描述设计与落地顺序，实施按 §9 分阶段开卡。
> 适用对象：后续接第三方 MCP 数据服务（Wind、且慢，以及未来的第三家）的开发者。

## 0. 一句话结论

**不新建一套 MCP 客户端**：把 `QiemanFetcher` 里已经跑在生产上的传输实现上提为唯一的
`transport`，用「基类 + 每服务子类」组织服务差异，凭据按 `data_scope` 自动路由到
系统 Token 或用户 Token，故障走显性上报而不是静默降级成空数据。

## 1. 红线（违反即打回）

1. **Token / API Key / Cookie 一律不得出现在文档、代码、注释、提交信息、PR 正文与测试夹具里**，
   只能从环境变量读取（`WIND_MCP_TOKEN` / `QIEMAN_API_KEY` 等）。日志、异常文本、`sync_logs.message`
   一律脱敏（`ak_***`）。示例值一律写 `xxxx`。
   判据：`scripts/guard_no_hardcoded_secrets.py`（源 #2486，并入 `ci.yml` 的 `scripts_test`，阻断；
   边界是「只看工作区里的跟踪文件」——提交信息 / 历史提交 / 运行时拼接不覆盖）。
2. **MCP 故障必须显性**。额度用尽、欠费、鉴权失效不得被 `except Exception: return []` 吞掉后
   渲染成「无数据 / —」——那会让用户误判成我们自己的服务坏了。见 §5。
3. **用户私有数据只能用用户自己的 Token**，不得用系统 Token 代取，也不得跨用户共享。
4. **前端指数 / 基准类只展示近 3~5 年**，全历史仅内部研究使用。见 §7。

第 1、2 两条同时是仓库级约束，已记入团队长期记忆。

## 2. 现状（判据起点）

| 事实 | 证据 |
|---|---|
| 且慢 MCP **已在生产**，每晚抓 111 只投顾组合的持仓 + 概览 | `backend/app/services/adapters/qieman_fetcher.py:11-20` |
| 传输已完整：握手、会话复用、SSE/JSON 双解析、会话失效重握重试 | `:282` `_mcp_post`、`:295` `_mcp_handshake`、`:320` `_call_tool`、`:345` `_ensure_session`、`:375` `_tool_call_once`、`:255` `_McpSessionInvalid` |
| 服务端**不回** `Mcp-Session-Id`（nginx 无状态网关）⇒「已握手」本身要记位 | `:276-279`、`:298-299`（实测 2026-10-20） |
| 凭据走 `os.getenv('QIEMAN_API_KEY')`，散落 **3 处**，缺则 warning + 跳过 | `:461`、`:534`、`:567` |
| 服务地址 / 协议版本 / 工具名硬编码在业务适配器 | `:38-43` |
| Wind MCP 未落地（仅协议探测，零代码） | 仓库内 `git grep -i mcp` 无 Wind 痕迹 |
| 投顾服务已有 Ports & Adapters 先例可对齐 | `services/adapters/advisor_source.py:90-189` |
| 分层方向受守卫约束 | `backend/tests/core/test_layer_direction.py:44-68`（R1–R7，R7 由 S1 新增） |

> **2026-10-21（S1 已落地，`#2488`）**：上表第 2~5 行的实现已搬到 `backend/app/services/mcp/`：
> `transport.py`（握手 / 会话缓存 / 失效重握 / SSE 解析）、`base.py`（`McpProvider` 模板方法）、
> `providers/qieman.py`（服务地址 / 协议版本 / 工具名）、`registry.py`（名字 → provider 实例）。
> `qieman_fetcher.py` 只保留两个入口：`_mcp_post`（HTTP 细节，`:293`）与 `_call_tool`
> （`:309`，测试按名 monkeypatch 它）。
>
> 与 §9 施工单的**两处偏离**，均为「不留没有读者的抽象」（理由写在对应模块 docstring）：
> ① `_mcp_post` 没有搬进 transport，而是作为 `post` 回调注入 —— 它持有适配器的
> `requests.Session` 与鉴权头，搬走就得把连接管理一起搬，且会让测试的替换点失效；
> ② 会话缓存不单独建 `SessionCache` 类，收敛在 `McpTransport` 内部（键 = token 指纹）——
> 单 provider 单实例下多一层对象只剩转发。
> **凭据仍走 `os.getenv('QIEMAN_API_KEY')`，散落 3 处**（`:367` / `:440` / `:473`），
> 凭据路由、记账与 health 段在 S2。
> 上表行号是**搬迁前**的位置，保留它是为了让「为什么这么设计」可追溯。

由此得出第一个设计决定：**传输层只能抽取，不能新写**。且慢那 6 个方法已经踩完 SSE、
无会话头、WAF 拦截、非 JSON 等坑，重写等于把已知结论再试错一遍。

## 3. 设计模式：三个，不多不少

| 模式 | 用在哪 | 为什么非它不可 |
|---|---|---|
| **模板方法** | `McpProvider` 固定流程（凭据 → 缓存 → 传输 → 错误分类 → 记账 → 回填），子类只填钩子 | 流程必须唯一；否则每家服务各写一遍缓存与记账，必然漂移 |
| **Ports & Adapters（策略 + 注册表）** | `@register_provider` + `name → 类`，业务层只按 `capability` 取源 | 与 `advisor_source.py` 同构，仓内已有先例，review 成本最低 |
| **适配器** | `WindIndexAdapter` / `QiemanAdvisorAdapter` 把 `McpResult` 翻成项目 canonical | 传输归一化 ≠ 业务模型归一化；混在一起会让「Wind 的表格列名」泄漏进 job |

**明确不用**：工厂 + 建造者（provider 数量是常数）、事件总线（错误上报走既有 job 终态 +
`/api/health`）、异步（仓内是同步 `requests` 栈 + Flask）、官方 `mcp` Python SDK
（会引入 `anyio`/`httpx` 异步栈，而两家服务的同步实现均已实测收口；若将来需要
`resources` / `prompts` / `sampling` 或第三家要求双向流式，再评估）。

## 4. 类结构

### 4.1 分层

```
业务层     services/sync/jobs/*            thermometer/*
                 ↓ 只调 capability（fetch_xxx），不认识 provider
适配层     services/adapters/qieman_*.py   services/adapters/wind_*.py
                 ↓ 组合 provider，不含协议细节
MCP 层     services/mcp/base.py            基类（模板方法）
           services/mcp/providers/*.py     每服务一个子类
           services/mcp/transport.py      唯一 HTTP/SSE/会话/重试实现
           services/mcp/credentials.py    系统 / 用户凭据解析
           services/mcp/registry.py       服务登记
           services/mcp/cache.py          缓存键与 TTL
           services/mcp/budget.py          额度记账
           services/mcp/errors.py          错误模型
                 ↓
基础层     core/cache.py   core/data_sources.py   core/trading_calendar.py
```

**依赖方向硬约束**：`services/mcp/*` **不得** import `services/adapters/*` 或任何 job
家族内部模块（`scripts/guard_layer_direction.py` 的 R5 会咬）。反向 `adapters → mcp` 合法。

### 4.2 基类（流程唯一实现）

```python
class DataScope(StrEnum):
    PUBLIC_MARKET   = 'public_market'    # 指数 / 估值 / 基金净值档案
    PLATFORM_PUBLIC = 'platform_public'  # 平台公开策略组合（且慢投顾组合）
    USER_PRIVATE    = 'user_private'     # 用户自己的账户 / 持仓 / 自选

class McpProvider(ABC):
    name: str            # 'wind' / 'qieman'
    source_label: str    # → core/data_sources.DATA_SOURCE_LABELS
    protocol_version: str

    # ── 子类实现：只回答「这家服务怎么说话」 ──
    @abstractmethod
    def base_url(self) -> str: ...
    @abstractmethod
    def auth_headers(self, token: str) -> dict[str, str]: ...
    @abstractmethod
    def tool_for(self, capability: str) -> str: ...
    @abstractmethod
    def scope_of(self, capability: str) -> DataScope: ...

    def map_args(self, capability: str, **kw) -> dict:   # 参数坑全部收在此
        return kw

    def extract(self, payload) -> McpResult: ...          # 表格 / 文本 → McpResult

    def _wire(self, tool: str, args: dict) -> dict:       # 网关型服务覆盖（Wind）
        return {'tool': tool, 'arguments': args}

    # ── 基类唯一实现：子类不得覆盖，也不得自己发 HTTP ──
    def invoke(self, capability: str, *, user_id: int | None = None, **kw) -> McpResult:
        cred = resolve_token(self, self.scope_of(capability), user_id)
        key = cache_key(self, capability, kw, cred)
        hit = self._cache.get(key)
        if hit is not None:
            self._budget.record(cred, capability, cached=True, ok=True)
            return hit
        try:
            payload = self._transport.call_tool(
                self, cred, self.tool_for(capability), self.map_args(capability, **kw)
            )
        except Exception as e:
            raise self._classify_error(e) from e     # 不吞、不返回空
        out = self.extract(payload)
        self._cache.set(key, out, ttl=self.ttl_of(capability))
        self._budget.record(cred, capability, cached=False, ok=True)
        return out
```

### 4.3 两个子类

```python
@register_provider
class QiemanProvider(McpProvider):          # 直调型：工具名已知
    name, source_label = 'qieman', 'qieman'
    protocol_version = '2024-11-05'
    TOOLS = {'latest_quotations': 'GetLatestQuotations',
             'strategy_details': 'GetStrategyDetails',
             'strategy_composition': 'BatchGetStrategiesComposition'}
    def base_url(self): return 'https://stargate.yingmi.com/mcp/v2'
    def auth_headers(self, token):
        return {'x-api-key': token, 'Origin': self.base_url(), 'Referer': self.base_url() + '/'}
    def scope_of(self, cap): return DataScope.PLATFORM_PUBLIC

@register_provider
class WindProvider(McpProvider):            # 网关型：先检索再调用
    name, source_label = 'wind', 'wind'
    protocol_version = '2025-06-18'
    def base_url(self): return os.getenv('WIND_MCP_URL') or WIND_DEFAULT_URL
    def auth_headers(self, token): return {'Authorization': f'Bearer {token}'}
    def _wire(self, tool, args):
        return {'toolName': tool, 'arguments': json.dumps(args)}
    def map_args(self, cap, **kw):
        ...   # 见 §6.2 的四个实测坑
    def scope_of(self, cap): return DataScope.PUBLIC_MARKET
```

**继承与组合的分工**：继承承载「每服务一套元信息」，组合承载「传输只有一份」。
让 Wind 继承且慢的传输代码是最糟的选择——那正是把两个服务耦在一起。

## 5. 凭据路由与错误上报

### 5.1 由 `data_scope()` 决定，不由 if/else 决定

| capability 类别 | scope | 取谁 | 例子 |
|---|---|---|---|
| 公开市场行情 | `PUBLIC_MARKET` | 系统 Token | 指数点位、估值分位、基金净值 / 档案、成分权重 |
| 平台公开策略 | `PLATFORM_PUBLIC` | 系统 Token，取一次共享 | 且慢投顾组合概览 / 持仓（现有 111 只） |
| 用户私有 | `USER_PRIVATE` | **必须**用户 Token | 用户账户、持仓、自选、个人额度 |
| 归属未知 | — | **默认 `USER_PRIVATE`** | 新接 MCP 判断不了时保守处理，不许误用系统额度 |

```python
def resolve_token(provider, scope, user_id):
    if scope is DataScope.USER_PRIVATE:
        cred = load_user_credential(provider, user_id)
        if cred is None:
            raise McpUserTokenMissing(provider)   # 绝不回退系统 Token
        return cred
    return system_credential(provider)            # env；缺失 → McpSystemTokenMissing
```

这一处替换掉现在散在 `qieman_fetcher.py:461/:534/:567` 的三处 `os.getenv`。
「用户没配 Token 就不提供该功能」在这里是**类型级保证**，不是注释级约定。

### 5.2 错误模型

```python
class McpError(Exception):
    kind: str            # 见下表
    provider: str
    retryable: bool
    action: str          # 'configure_token' | 'wait' | 'contact' | 'report'
    user_message: str    # 中文人话，已脱敏
```

| 子类 | 触发 | 可重试 | `action` | 用户可见文案（示例） |
|---|---|---|---|---|
| `McpAuthError` | 401 / 403 | 否 | `configure_token` | Wind 授权已失效，请更新 Token |
| `McpQuotaExceeded` | 额度用尽 / 429 配额语义 | 否 | `wait`（或改用自有 Token） | Wind 今日调用额度已用尽，数据暂停更新 |
| `McpBillingError` | 欠费 / 未订阅 / 到期 | 否 | `contact` | Wind 账户欠费或服务已到期 |
| `McpRateLimited` | 频控 429 | 是（退避） | `wait` | 调用过于频繁，稍后自动重试 |
| `McpUnavailable` | 5xx / 超时 / 网络 | 是 | `wait` | Wind 服务暂时不可用 |
| `McpBadResponse` | 结构不符 / 空结果 | 否 | `report` | 返回结构异常，已记录 |

> ⚠️ Wind 的「额度用尽 / 欠费」真实报文形态**尚未采样**（探测阶段未触发限额）。
> S3 的探针必须把第一次真实报文的 `status + body` 落到 `mcp_call_logs.error_kind` 映射表，
> 不得凭猜写分类。

### 5.3 上报链（五段，缺一段就不算「让用户感知」）

1. `mcp_call_logs` 落库：`provider / capability / scope / user_id / ok / error_kind / http_status / duration_ms / cached`；
2. job 终态：全挂 → `FAILED`（复用 `job_base._decide_final_status`），部分成功 → `SUCCESS` + `stats['degraded']`；
3. `sync_logs.message` 写人话（脱敏）；
4. `/api/health`（`backend/app/domains/health.py:32` 已有 db / scheduler / llm 三段）增 `mcp` 段：
   每 provider 的 `status`、`last_error_kind`、`quota_used / quota_limit`；
5. 前端：该数据区块顶部提示「数据可能不是最新：Wind 额度已用尽（YYYY-MM-DD）」，
   **不允许**渲染成 `—` 后无任何提示。

**回归判据**：注入 `McpQuotaExceeded` ⇒ job 带 `degraded` 计数、health 转 `degraded`；
若实现变成「成功 + 空列表」，用例必须红。

## 6. 数据分级与 Wind 接入要点

### 6.1 三层（登记时回答一次，不在每个 job 各判一次）

| 层 | 判据（同时满足） | 落点 | 举例 |
|---|---|---|---|
| **P 持久化** | 高价值 + 日更或获取成本高 | 入库，可回溯 | 885xxx 点位、业绩比较基准、指数估值分位 |
| **C 缓存** | 高频重复读 + 可重取 + 公开数据 | `core.cache.CacheService`，键含交易日 | 指数快照、基金档案、筛选结果 |
| **O 按需** | 低频长尾 + 单次便宜 | 现查，仅进程内短 TTL | 某只基金某季持仓明细 |

capability 声明 `tier`，`invoke()` 据此决定落库 / TTL / 是否记账。

### 6.2 Wind 的四个实测坑（全部收在 `map_args`）

| 坑 | 处理 |
|---|---|
| `period` 必须是 `"10"`（日 K），传 `"D"` 直接 `Invalid value` | adapter 内映射，不暴露给业务 |
| `get_index_fundamentals` 认名称（`沪深300`）不认代码（`000300.SH`） | 维护 `code → 查询名` 映射 |
| 批量参数是逗号分隔字符串，不是数组 | adapter 归一化 |
| 返回是 `{columnNames, rows}` 多块表格 | `extract()` 按列名取，缺列显式 `None` |

### 6.3 生产链路不做自然语言检索

`market_search_tools` 每次 1–2s 且结果依赖语义。**工具名走 registry 静态映射**；
检索只留给人工探针（`pdm run mcp-probe "<问题>"`）。否则线上会出现「同一份代码今天取不到、
明天又好了」的不可复现故障。

## 7. 展示窗口：3~5 年，在后端截断

```python
# services/index/display_policy.py
DISPLAY_YEARS = 5            # 对外展示窗口；内部研究不受限

def clamp_since(since: date, *, allow_full: bool = False) -> date: ...
```

- **截断在 API 层**，不是前端：前端截断意味着全量数据已经出网，等于没管；
- 内部工具（CLI / 研究脚本）显式 `allow_full=True` 才可越界，**默认 5 年**；
- 两条测试钉住：API 默认不返回 >5 年；CLI 显式允许时可返回全量。

## 8. 接口预留：本地 / SaaS 一键切换

本次只支持「填 Token」，但预留三个口子：

| 预留点 | 现在 | SaaS 时 |
|---|---|---|
| 服务地址 | registry 默认官方地址 + `WIND_MCP_URL` env 覆盖（本地可指 `127.0.0.1`） | 换网关地址，**只改 env / registry** |
| 凭据来源 | `resolve_token()`：env / 库内密文 | 换租户级配置（表留 `key_version`），**不动 adapter 与 job** |
| 用户输入 | `user_mcp_credentials(user_id, provider, cipher_text)`，**表里没有 url 列** | 加 URL 必须改表 + 加 SSRF 白名单，是一次显式决策 |

「表结构里不给这一列」比「UI 上禁止填写」可靠：前者是硬约束，后者只是一个表单。

加密：`MCP_CREDENTIAL_KEY`（env）→ Fernet。注意 `cryptography` 目前只是
`backend/pdm.lock` 里的传递依赖，直接 import 前必须在 `pyproject.toml` 显式声明。

## 9. 落地顺序（每步可独立合并 / 回滚）

| 阶段 | 内容 | 完成判据 |
|---|---|---|
| **S0** | 新增 `scripts/guard_no_hardcoded_secrets.py` 并入 `ci.yml` 的 `scripts_test`；登记 `RULE_REGISTRY`；`AGENTS.md` 落一条带判据的红线 | 守卫在真实仓库跑出 0 命中；回退探针（把假 Token 写进真实文件）必须转红；拿不到输入退 2 |
| **S1** | 抽 `transport` + `base` + `QiemanProvider`，且慢切过去 | `tests/services/thermometer/test_qieman_fetcher.py`、`test_qieman_batch_transport.py` 全绿；握手仍只 1 次；请求数不增 |
| **S2** | `credentials` + `errors` + `cache` + `budget` 接入 | 注入额度异常 ⇒ health 转 `degraded`（不是「成功 + 空」） |
| **S3** | `WindProvider` + 只读探针 + 真实错误报文采样 | 接第二家（Wind）**不改 `transport.py`** |
| **S4** | 第一个 Wind job（业绩比较基准回填）+ 展示窗口策略 | API 默认 ≤5 年；基准数据与 Wind 一致 |
| **S5** | `user_mcp_credentials` + `PRO_FEATURES` 门禁 | 用户无 Token ⇒ 明确提示，不回退系统 Token |

> **S0 收窄过（2026-10-21，源 #2486）**：S0 原本还包含「`WIND_MCP_TOKEN` / `WIND_MCP_URL`
> 写进 `backend/.env.example`」与「`DATA_SOURCE_LABELS` 补 `qieman` / `wind`」。两者都被
> **推后**，理由是同一个——**没有读者的配置与常量就是在攒垃圾**：
> Wind 的 env 要到 S3 有 provider 才有人读；`DATA_SOURCE_LABELS` 的读者只有
> `fund_holdings_detail` / `product_trend` / `stock_profile`，投顾与温度计链路目前不读它
> （`qieman_fetcher.source = 'qieman'` 写进的是库里的 `source` 列，不上屏）。
> 等哪个页面真的要带来源脚注时再加——`docs/spec/data-strategy.md` 的准入四问第一条
> 「谁在用」答不出来，就不该加。

方法搬移清单（S1 的施工单）：

| 现位置（`qieman_fetcher.py`） | 去向 |
|---|---|
| `_mcp_post` | `transport._post`（`Origin/Referer` 移入 `auth_headers`） |
| `_mcp_handshake` + `notifications/initialized` | `transport._initialize` |
| `_ensure_session` / `_reset_session` | `transport.SessionCache`，键改为 `(provider, token_fingerprint)` |
| `_tool_call_once` | `transport._call_once`（SSE 解析、非 JSON ⇒ 会话失效原样保留） |
| `_call_tool`（重握重试一次） | `transport.call_tool`（不无限重试、不吞错） |
| `_McpSessionInvalid` | `transport.McpSessionInvalid` |
| `QIEMAN_MCP_URL` / `QIEMAN_PROTOCOL_VERSION` / `QIEMAN_CLIENT_INFO` / 三个工具名 | `registry` / `QiemanProvider` |
| **保留在 fetcher** | `source/name/unit` + 4 个 `fetch_*` 业务方法与中文键归一化 |

## 10. 判定「抽象是否成立」的三条

1. 接 Wind 时**没有**修改 `transport.py`（只新增 registry 条目 + 子类 + adapter）；
2. 接 Wind 时业务 job 里**没有**出现 `provider` 字样（只认 capability）；
3. 系统 Token 与用户 Token 的差异，收敛在 `resolve_token` 一个函数里，`invoke()` 之下无分叉。

## 11. 已知不做

- 不做 MCP 服务端；
- 不引入官方 `mcp` SDK（理由见 §3）；
- 不允许用户自带 MCP URL（SSRF 面；表结构不提供该列）；
- 不做全市场历史回填（属重活，需用户 Token 或不做）。

## 12. 待办与已知缺口

- Wind 的额度 / 欠费报文形态待采样（S3）；
- `backend/app/services/thermometer/README.md:337` 称 `QIEMAN_API_KEY` 缺省「用内置 key」，
  与代码 `:461/:534/:567`（缺则 warning + 跳过）冲突，需确认后拉平；
- `core/data_sources.DATA_SOURCE_LABELS` 暂无 `qieman`，若且慢数据上屏带来源脚注需补登。
