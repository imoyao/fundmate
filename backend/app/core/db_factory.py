# -*- coding: utf-8 -*-
"""数据库连接工厂（多环境 / 多域引擎）。

设计背景（issue #1028 + #894）：
- 前/后端 env 按模式拆分后，后端需要按 APP_ENV 自动切换运行库，避免手动适配。
- 数据库分层（方案 B）：
    * 本地开发：本地 SQLite 运行库（开发用）。
    * 生产运行库：Turso（生产应用读写，市场域/非敏感数据）。
    * 用户核心账本：Supabase Postgres（独立权威库，与运行库各自独立）。
    * Neon：同步 Supabase 数据作灾备/一键切换 —— 延后，此处仅预留接入点。
- 本模块产出「应用运行库」与「用户库」两套独立 engine；业务层后续可按数据域
  经 get_engine(domain) 选库。当前 database.py 的默认 engine 指向应用运行库，
  所有既有调用方（SessionLocal / get_db / init_db）零改动。

切换信号：APP_ENV = development | staging | production，与前端 VITE_APP_ENV 对齐；
FLASK_DEBUG 仅控制调试器，不再混用作环境开关。
"""

from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

from loguru import logger
from sqlalchemy import Engine, create_engine, event, make_url
from sqlalchemy.orm import sessionmaker

# --------------------------------------------------------------------------- #
# 数据域标识：应用运行库 vs 用户核心账本库
# --------------------------------------------------------------------------- #
DOMAIN_APP = 'app'  # 应用运行库（市场域/非敏感数据：净值、指数、温度计、自选种子等）
DOMAIN_USER = 'user'  # 用户核心账本库（Supabase，隐私数据，独立权威）

# 域的「引擎来源」语义别名：market 域对应 DOMAIN_APP 引擎，user 域对应 DOMAIN_USER 引擎。
# 文档与代码统一用 'market' / 'user' 描述数据归属，用 DOMAIN_APP / DOMAIN_USER 描述引擎。
DOMAIN_MARKET = 'market'

_DEFAULT_APP_DB = 'sqlite:///./invest.db'
# development 缺省库：与 app 同文件——本地（含全新克隆、无 .env）只有一个 invest.db，
# 既有数据零迁移。历史曾为独立 `invest.dev.db`，导致无 .env 的克隆另建一个空库、
# 看不到 invest.db 里的存量数据；统一为 invest.db 后该坑消除。
_DEFAULT_DEV_DB = 'sqlite:///./invest.db'


#: 参与「应用运行库」解析的环境变量（按环境不同取其一，见 DatabaseConfig.for_app）。
#: 用于回答两个问题：**解析出的目标是不是「无配置的 cwd 缺省」**，以及
#: **配了变量却在 development 下被忽略**（#2344 实测事故就栽在后者）。
APP_DB_ENV_VARS = (
    'TURSO_DATABASE_URL',
    'STAGING_DATABASE_URL',
    'DATABASE_URL',
    'DEV_DATABASE_URL',
)


def app_database_configured_vars(env: str | None = None) -> list[str]:
    """当前**生效**的 App Env 下，哪些运行库环境变量被配置了（按解析顺序）。

    用途：让「我明明配了库，程序却连到了别处」这类事故在**启动时**就能被看见，
    而不是等某个统计口径偶然暴露（#2344：`DEV_DATABASE_URL` 在 APP_ENV 未设时被
    静默忽略，CLI 连到了 cwd 下的空库，还报 success）。
    """
    env = env or get_app_env()
    if env == 'development':
        candidates = ('DEV_DATABASE_URL',)
    elif env == 'staging':
        candidates = ('STAGING_DATABASE_URL', 'DATABASE_URL')
    else:
        candidates = ('TURSO_DATABASE_URL', 'DATABASE_URL')
    return [name for name in candidates if os.getenv(name)]


def app_database_source_var(env: str | None = None) -> str | None:
    """**实际生效**（解析命中）的库变量名；一个都没配返回 ``None``。

    与 :func:`app_database_configured_vars` 的区别很要紧：production 下
    ``TURSO_DATABASE_URL or DATABASE_URL`` 两者都参与，但只有排在前面的那个生效。
    「配了」不等于「生效」——报告里必须说出赢的那个，否则排查会被带偏。
    """
    configured = app_database_configured_vars(env)
    return configured[0] if configured else None


def ignored_app_db_env_vars(env: str | None = None) -> list[str]:
    """被配置了但在当前 App Env 下**不参与解析**的运行库变量（会被静默忽略的那些）。"""
    env = env or get_app_env()
    participating = set(app_database_configured_vars(env))
    return [name for name in APP_DB_ENV_VARS if os.getenv(name) and name not in participating]


def app_database_url(env: str | None = None) -> str:
    """应用运行库（market 域）URL 的**唯一**解析入口。

    任何需要「当前连的是哪个库」的地方——legacy 符号、CLI 启动日志、备份路径推断、
    测试——都必须走这里。此前 `database.SQLALCHEMY_DATABASE_URL` 自己读了一遍
    `DATABASE_URL`，与引擎真实解析**并行且不一致**（引擎在 development 下压根不看
    `DATABASE_URL`），于是读那个符号的人可能拿到一个根本没在用的库（#2344）。
    """
    return DatabaseConfig.for_app(env or get_app_env()).url


def _development_user_url() -> str:
    """development 下 user 域 URL：显式配置 DEV_USER_DATABASE_URL 优先（独立库，
    本地双库模拟）；未配置时与 market 域同库（DEV_DATABASE_URL，缺省 invest.db）——
    「默认放一起，显式配第二个库才分开」。"""
    return os.getenv('DEV_USER_DATABASE_URL') or os.getenv('DEV_DATABASE_URL') or _DEFAULT_DEV_DB


def turso_auth_token(url: str) -> str | None:
    """取出 Turso 连接串里的 ``authToken``；没有（或为空串）返回 ``None``。

    为什么值得单独一个函数：缺 token 的 Turso 连接串**必然连不上**，
    而服务端的反应是 308 / 401 这类**看不出「压根没配 token」**的状态码——
    排查时极易被带偏。#1490 实测：每日调度连续 25 天全红，根因就是仓库 secret
    里的连接串只有 host、没有 authToken；而当时的诊断文案写的是
    「host 被服务端重定向（旧地址 / 区域变更）」，把排查引到了错误方向，
    白白绕了一圈（上游同族：dependabot 坏锁那次的「空 ≠ 没拿到」）。
    """
    parsed = urllib.parse.urlparse(url)
    qp = urllib.parse.parse_qs(parsed.query)
    token = qp.get('authToken') or qp.get('auth_token')
    if not token or not token[0]:
        return None
    return token[0]


#: 本机地址：本地 sqld 走明文 http 是正常用法，不该被强制 https。
_LOCAL_HOSTS = ('localhost', '127.0.0.1', '::1', '0.0.0.0')


def _needs_secure_transport(scheme: str, netloc: str) -> bool:
    """Turso **云端**连接是否必须走 https。

    为什么必须显式 secure=true：`sqlalchemy-libsql` 0.2.0 的方言默认
    ``secure=False``，连接串里没有 ``secure=true`` 时，客户端会用**明文 http**
    去连 Turso；而 Turso 边缘对明文请求一律回 **308 Permanent Redirect**
    （Location 指向同路径的 https），客户端不自动跟随 ⇒ 每次连接都失败。

    #1490 实测：每日调度自 2026-09-04 起 **25 次全红、零成功**，报错是
    ``Hrana: api error: status=308 Permanent Redirect, body=Redirecting``——
    看上去像「host 被服务端重定向」（原诊断文案正是这么写的，把排查带偏了），
    实际只差一个 ``secure=true``。实测对照：
    ``http://<host>/v3/pipeline`` → 308 → ``https://<host>/v3/pipeline`` → 200。

    本机 sqld（localhost/127.0.0.1）走明文 http 是正常用法，不在此列。
    """
    host = netloc.split('@')[-1].split(':')[0].lower()
    if host in _LOCAL_HOSTS:
        return False
    if scheme in ('turso', 'libsql'):
        return True
    return host.endswith('.turso.io')


def redact_db_url(url: str) -> str:
    """把连接串里的 token 参数打码——给日志用。

    token 出现在日志里就等于泄露：它同时是数据库凭证与（历史上）可读数据的钥匙。
    """
    return re.sub(r'(auth[Tt]oken)=[^&\s]+', r'\1=***', url)


def normalized_app_db_url_preview(env: str | None = None) -> str:
    """归一后的 market 域连接串（token 已打码）——给启动日志看「实际会用哪条 URL 连」。

    #1490：这条日志的价值是让「实际连的是 http 还是 https」一眼可见——
    明文 http 连 Turso 会被服务端 308 跳 https 而失败（见 _needs_secure_transport）。
    """
    url = DatabaseConfig.for_app(env).url
    normalized, _ = _normalize_db_url(url)
    return redact_db_url(normalized)


def _normalize_db_url(url: str) -> tuple[str, Dict]:
    """把 Turso / libSQL 连接串归一为 sqlalchemy-libsql 可解析的 scheme。

    sqlalchemy-libsql 注册的方言是 `libsql` / `sqlite+libsql`，**不**认识裸
    `turso://`、`libsql://` 乃至 `https://*.turso.io`——后者曾导致生产
    `init_db()` 报 `NoSuchModuleError: sqlalchemy.dialects:turso`
    （数据刷新 #7 / #1467）。

    统一重写为 `sqlite+libsql://`，并把 Turso 下发的 `authToken` 从 query
    提取到 connect_args（libsql 驱动要求以 connect arg 传入，而非 URL query）。

    另补一条 **`secure=true`**（#1490）：方言默认 `secure=False` 会让客户端
    走明文 http，Turso 边缘回 308 跳 https ⇒ 每天必挂。Turso 云端一律强制 https；
    本机 sqld 不动；URL 里显式写了 `secure=` 的按它说的算。

    对 SQLite / Postgres 等非 Turso URL 原样返回，connect_args 为空字典。
    本函数幂等：已是 `sqlite+libsql://` 的 URL 只补 `secure`（若缺），其余透传。
    """
    extra_connect_args: Dict = {}
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    original_url = url

    # 判定是否 Turso / libSQL 连接（裸 turso://、libsql://、或 https://*.turso.io）
    is_turso = scheme in ('turso', 'libsql') or (scheme == 'https' and 'turso' in parsed.netloc.lower())
    # 已归一过的 sqlite+libsql://：幂等路径，只允许补 secure
    is_normalized = scheme == 'sqlite+libsql' and bool(parsed.netloc)
    if not (is_turso or is_normalized):
        return url, extra_connect_args

    qp = urllib.parse.parse_qs(parsed.query)
    host_part = parsed.netloc + parsed.path

    if is_normalized:
        if 'secure' not in qp and _needs_secure_transport(scheme, parsed.netloc):
            qp['secure'] = ['true']
            return 'sqlite+libsql://' + host_part + '?' + urllib.parse.urlencode(qp, doseq=True), extra_connect_args
        return url, extra_connect_args

    # scheme 归一为 sqlalchemy-libsql 认识的 `sqlite+libsql://`
    url = 'sqlite+libsql://' + host_part
    # 提取 authToken 到 connect_args，避免 URL 上残留（libsql 要求 connect arg）
    token = turso_auth_token(original_url)
    if token:
        extra_connect_args['auth_token'] = token
    # 非认证参数（如 region=...）一律保留：#1491 评审——原实现只在存在 authToken 时
    # 才把剩余 query 拼回，无 token 的 URL 上其余查询参数会被整体丢弃
    remaining = {k: v for k, v in qp.items() if k not in ('authToken', 'auth_token')}
    if 'secure' not in remaining and _needs_secure_transport(scheme, parsed.netloc):
        remaining['secure'] = ['true']
    if remaining:
        url += '?' + urllib.parse.urlencode(remaining, doseq=True)
    return url, extra_connect_args


# SQLite(pysqlite) 专有的 connect_args：只有本地文件/内存库接受。
# libSQL(Turso) 与 psycopg2 的 DBAPI 签名不接受 `timeout`，无条件注入会在建连时
# TypeError（#1519）——见 _sqlite_connect_args 与 build() 的兜底闸门。
_SQLITE_ONLY_CONNECT_ARGS = ('check_same_thread', 'timeout')


def _is_local_sqlite(url: str) -> bool:
    """URL 是否指向**本地** SQLite（文件 / 内存），而非远端 libSQL（Turso）。

    `sqlite://`、`sqlite+pysqlite://` 是本地；`sqlite+libsql://`（含由
    `turso://` / `libsql://` / `https://*.turso.io` 归一而来）是远端。
    """
    scheme = urllib.parse.urlparse(url).scheme.lower()
    return scheme in ('sqlite', 'sqlite+pysqlite')


def _sqlite_connect_args(url: str) -> Dict:
    """按 URL 方言给 connect_args：只有本地 SQLite 才需要 SQLite 专有参数。

    为什么必须按方言判断（#1519 / #1514）：`check_same_thread`、`timeout` 是
    **pysqlite 专有**关键字。历史上 app 域在 staging / production 分支无条件注入它们，
    而这两个环境默认指向 Turso（`sqlite+libsql://`）；libSQL 的
    `libsql_experimental.connect()` 不接受 `timeout`，于是**建立连接时**抛
    `TypeError: connect() got an unexpected keyword argument 'timeout'`——
    CI 定时任务因此启动即崩，且报错点离真因很远。

    远端 libSQL 的认证参数（`auth_token`）由 `_normalize_db_url` 单独提供，不在此处。
    """
    if _is_local_sqlite(url):
        return {'check_same_thread': False, 'timeout': 30}
    return {}


def _needs_sqlite_pragmas(url: str) -> bool:
    """仅本地 SQLite（`sqlite://` 文件 / 内存）需要 WAL / 外键 PRAGMA。

    `sqlite+libsql://`（Turso 远端）不应应用本地 PRAGMA，否则会向远端发送
    其不支持的 PRAGMA 语句而失败。
    """
    return _is_local_sqlite(url)


# --------------------------------------------------------------------------- #
# 表 → 数据域归属注册表（单一事实来源，与 docs/dev/db-data-domain.md 同步）
# --------------------------------------------------------------------------- #
# 规则：每个 ORM 模型对应的 __tablename__ 必须在此登记，且只能归 market / user 之一。
# 未登记的表在 init_db 启动校验时直接 fail（防漏声明导致建错库 / 读错库）。
# 归属判定见 AGENTS.md「多引擎数据域约束」决策树。
#
# 边界先例（已固化，勿凭"公开=Turso"一刀切）：
#  - sales_institutions：公开名录，但被 user 域表 (ledgers) 外键引用 → 随 user 域，
#    避反向跨域 FK。
#  - fund_companies：公司主数据，被 market 域表 (funds/managers) 外键引用 →
#    随 market 域。AMAC 基金管理人公示信息 enrich 进本表（2026-09-10 合并），
#    曾有独立的 fund_management_companies（user 域）——实测零读者/零外键/零接口，
#    已删除。注意别再把它登记回来。
#  - managers / fund_managers：被 market 域表 (funds) 外键引用 → 随 market 域。
#  - manager_tenures（#2239）：与 fund_managers 同源同写方（SyncJob）、同样外键引用
#    funds/managers，且读方是 market 域的经理读服务 → 随 market 域。它是
#    fund_managers 拆出来的任期表，两张表放不同域会制造跨域 FK 与跨域事务。
DATA_DOMAIN_REGISTRY: Dict[str, str] = {
    # ── market 域（Turso）：公开、读多写少、无限膨胀的市场数据 ──
    'funds': DOMAIN_MARKET,
    'fund_companies': DOMAIN_MARKET,
    'fund_varieties': DOMAIN_MARKET,
    'fund_types': DOMAIN_MARKET,
    'fund_sales_orgs': DOMAIN_MARKET,  # 基金维度销售机构（funds 域内）
    'managers': DOMAIN_MARKET,  # 基金管理人（被 funds 引用）
    'fund_managers': DOMAIN_MARKET,  # 基金-经理关联（被 funds 引用）
    'manager_tenures': DOMAIN_MARKET,  # 基金-经理任期分段（#2239 从 fund_managers 拆出）
    'advisor_portfolios': DOMAIN_MARKET,  # 投顾/基金组合公开参照（且慢/蛋卷/天天基金）
    'index_constituents': DOMAIN_MARKET,  # 指数成分股（#1286 品种差异化维度：指数→成分）
    'index_catalog': DOMAIN_MARKET,  # 指数名录（#1286 聚合搜索可搜索的指数条目）
    'index_daily': DOMAIN_MARKET,  # 指数日线点位（#275 基准对比底座，万得全A 经韭圈儿公开接口）
    'index_valuations': DOMAIN_MARKET,  # 指数估值（#1285/#1394：市盈率/股息率，中证官方）
    'index_valuation_baselines': DOMAIN_MARKET,  # 指数估值分位基线（#1407：乐咕月频滚动 PE，近 5 年）
    'market_asset_daily': DOMAIN_MARKET,  # 探市大类资产日频快照（#1460 P1：20 资产，供读库组装）
    'market_bond_yield_daily': DOMAIN_MARKET,  # 探市债券 10Y 收益率日频快照（#1460 P1）
    'channel_links': DOMAIN_MARKET,  # 跨渠道关联（#1285 §3.8：指数↔ETF / ETF↔联接）
    'advisor_holdings': DOMAIN_MARKET,  # 投顾组合当前基金级持仓（#1167）
    'advisor_industry_allocs': DOMAIN_MARKET,  # 投顾组合行业配置（#1167）
    'advisor_adjust_histories': DOMAIN_MARKET,  # 投顾组合历史调仓明细（#1167）
    'fund_holdings': DOMAIN_MARKET,  # 基金持仓明细（#870：报告期快照，前十大与全量并存）
    'fund_industry_allocs': DOMAIN_MARKET,  # 基金行业配置（#870：csrc/gics 双体系分区）
    'convertible_bond_terms': DOMAIN_MARKET,  # 可转债条款（#1285/#1393：强赎/回售/转股）
    'daily_worth': DOMAIN_MARKET,  # 基金净值（最大体积表）
    'fund_valuation_daily': DOMAIN_MARKET,  # 场外基金收盘估值定格（#2141）
    'fund_risk_metrics': DOMAIN_MARKET,  # 基金风险指标派生投影（#167 榜单/详情页；公开净值派生，无家庭私有字段）
    'money_fund_daily_worth': DOMAIN_MARKET,  # 货基净值
    'purchase_rules': DOMAIN_MARKET,
    'redeem_rules': DOMAIN_MARKET,
    'fee_ratios': DOMAIN_MARKET,
    'etf_fee_rates': DOMAIN_MARKET,  # ETF 管理/托管费率缓存小表（#2333：双 HTML 源兜底，etf_compare 读）
    'price_history': DOMAIN_MARKET,  # 历史行情（最大体积表）
    'securities': DOMAIN_MARKET,
    # 个股/可转债 → 行业映射（#1981）。随 securities 同域：公开证券主数据，
    # 无家庭私有字段，且 penetration 读它时要与 securities / price_history 同会话。
    'security_industry_maps': DOMAIN_MARKET,
    'market_single_values': DOMAIN_MARKET,
    'market_composites': DOMAIN_MARKET,
    'market_multi_items': DOMAIN_MARKET,
    'sync_logs': DOMAIN_MARKET,  # 系统同步审计（随市场同步任务）
    # ── user 域（Supabase）：含 family_id/user_id 的用户私有数据 ──
    'families': DOMAIN_USER,
    'users': DOMAIN_USER,
    'user_preferences': DOMAIN_USER,  # 用户私有偏好键值（#1337，按 user_id，非 family）
    'ledgers': DOMAIN_USER,
    'portfolios': DOMAIN_USER,
    'positions': DOMAIN_USER,
    'transactions': DOMAIN_USER,
    'position_import_meta': DOMAIN_USER,  # 导入溯源（含 family_id）
    # 导入侧观察值（基金→基金管理人原始证据，含 family_id）。含 family_id 故归 user 域：
    # 它记录「某家庭导入的样本里出现某基金」，属用户私有数据，不落共享市场库。
    # 消费方是 market 域 job（fund_company_backfill），按 AGENTS.md 规则 3「应用层两步法」
    # 读取（先取键列表再 in_ 批查），不做跨域 JOIN；funds.company_id 仍由 market 域独占写权。
    'fund_company_observations': DOMAIN_USER,
    'assets': DOMAIN_USER,  # 静态资产（含 family_id）
    'sales_institutions': DOMAIN_USER,  # 销售机构名录（被 ledgers 引用，随 user 域）
    'watchlist': DOMAIN_USER,
    'watchlist_groups': DOMAIN_USER,
    'watchlist_item_group': DOMAIN_USER,
    'watchlist_tag_defs': DOMAIN_USER,
    'watchlist_item_tags': DOMAIN_USER,
    'watchlist_alerts': DOMAIN_USER,
    'cleared_positions': DOMAIN_USER,
    'strategy_tags': DOMAIN_USER,
    'position_strategy_tags': DOMAIN_USER,
    'dividend_targets': DOMAIN_USER,  # 家庭股息目标（#872）：用户私有配置，一家庭一条
    'notifications': DOMAIN_USER,  # 站内通知（#2236）：含 family_id，家庭级消息盒
    'target_allocations': DOMAIN_USER,  # 目标配比（#2237）：含 family_id，用户自定的目标占比
    'asset_snapshots': DOMAIN_USER,
    'pnl_daily_snapshots': DOMAIN_USER,  # 收益日历逐日物化快照（#1926）：含 family_id
    'user_usage': DOMAIN_USER,
    'agent_session': DOMAIN_USER,  # 账本精灵会话（#1121 S2：状态/原文/轮次，含 user_id）
    'agent_trace': DOMAIN_USER,  # 账本精灵单轮决策 trace（#1736 S4：回放/评估，经 session_id 同族）
    # ── 统一对账框架三表（#1232 §8.1 / P1）──
    'discrepancies': DOMAIN_USER,  # 活跃对账差异（含 family_id）
    'reconciliation_runs': DOMAIN_USER,  # 对账运行记录
    'adjustment_logs': DOMAIN_USER,  # 对账审计日志（仅用户主动操作）
    'ghost_duplicate_ignores': DOMAIN_USER,  # 幽灵重复忽略（域 D；FamilyScopedMixin 含 family_id）
    'entitlements': DOMAIN_USER,  # 家庭级 Pro 功能权益（含 family_id，随 user 域）
}

# 规划中但尚未建表的域归属（提前登记，防止模型落地时漏声明）。
# 用户操作审计表：含 user_id，按用户数增长，归 user 域，享 RLS，与原操作同引擎。
PENDING_DOMAIN_REGISTRY: Dict[str, str] = {
    'user_audit_log': DOMAIN_USER,
}


# 模型源码位置（仅供孤儿表二次判定用）：业务模型在 app/domains/<域>/models.py；
# 跨域 / 系统级模型在 app/models/ 下（现仅 sync_log，属**被承认的第二类**而非「例外」，
# 见 architecture.md §6「模型位置」）。
_MODEL_SOURCE_GLOBS = ('domains/*/models.py', 'models/*.py')


def _model_source_text() -> Optional[str]:
    """拼接模型源码文本（只读文件，不执行模块代码）。

    WHY：孤儿告警原本以 `metadata.tables` 为唯一判据，而它只含「本进程已 import」的模型——
    CLI / 定时任务只导入所需模型时，已登记且模型仍在的表会被误报成「模型未定义」（#1521）。
    这里改用源码文本做二次判定以区分两种情形；因为不 import，也就不会引入循环导入或
    导入期副作用（导入期建 engine 的教训见 #1513）。

    返回 None 表示无法读取（目录缺失等），调用方须按「未知」处理，
    不得据此断言模型已删除。
    """
    app_dir = Path(__file__).resolve().parents[1]
    chunks = []
    for pattern in _MODEL_SOURCE_GLOBS:
        for path in sorted(app_dir.glob(pattern)):
            try:
                chunks.append(path.read_text(encoding='utf-8'))
            except OSError:
                continue
    return '\n'.join(chunks) if chunks else None


def normalize_table_domain(table_name: str) -> Optional[str]:
    """查表名对应的数据域；未登记返回 None（供启动校验拦截）。"""
    return DATA_DOMAIN_REGISTRY.get(table_name)


def get_app_env() -> str:
    """解析运行环境，默认 production（安全侧）。"""
    env = (os.getenv('APP_ENV') or os.getenv('FLASK_ENV') or '').strip().lower()
    if env in ('development', 'dev', 'local'):
        return 'development'
    if env in ('staging', 'stage', 'test'):
        return 'staging'
    return 'production'


def resolve_app_db(env: Optional[str] = None) -> Tuple[str, str]:
    """解析 market 域运行库 URL，并报告它由哪个环境变量决定（#2344）。

    与 :meth:`DatabaseConfig.for_app` 同一套优先级（本函数是它的「可解释」镜像），
    但额外返回来源变量名——2026-10-18 事故里，使用者在 worktree 设了
    ``DEV_DATABASE_URL``，却因 ``APP_ENV`` 缺省为 production 被静默忽略，
    CLI 连到 cwd 相对的 ``./invest.db`` 空库，批量同步跑成「0 只处理」还报
    success。没有「来源」信息时，这类错配在日志里完全不可见。

    返回 ``(url, source)``：``source`` 为环境变量名；命中内置缺省时为 ``'default'``。
    """
    env = env or get_app_env()
    if env == 'development':
        url = os.getenv('DEV_DATABASE_URL')
        return (url, 'DEV_DATABASE_URL') if url else (_DEFAULT_DEV_DB, 'default')
    if env == 'staging':
        url = os.getenv('STAGING_DATABASE_URL')
        if url:
            return url, 'STAGING_DATABASE_URL'
        url = os.getenv('DATABASE_URL')
        return (url, 'DATABASE_URL') if url else (_DEFAULT_APP_DB, 'default')
    # production：TURSO_DATABASE_URL 优先，回退 DATABASE_URL（与 for_app 一致）
    url = os.getenv('TURSO_DATABASE_URL')
    if url:
        return url, 'TURSO_DATABASE_URL'
    url = os.getenv('DATABASE_URL')
    return (url, 'DATABASE_URL') if url else (_DEFAULT_APP_DB, 'default')


def app_db_startup_check(*, strict: bool) -> Optional[str]:
    """CLI 启动期：打印 market 域运行库解析结果，并守卫「连到不存在的库」（#2344）。

    两件事：

    1. **启动即打印**：当前连的是哪个库（URL + 决定它的环境变量 + APP_ENV），
       让「连错库」在日志首行即可见，而不是等统计口径偶然暴露；
    2. **分级守卫**：解析出的 SQLite 文件库不存在时——
       - 显式配置了数据库（source != 'default'）但文件不存在：**直接报错**（配置错误，
         非 fresh clone 场景，不应静默新建空库）；
       - ``strict=True``（显式 ``--targets`` / ``--target-file`` / ``--snapshot`` 的批量修复场景）
         且 source == 'default'：返回**错误消息**（调用方应退出）；
       - ``strict=False`` 且 source == 'default'（fresh clone 首跑）：返回**告警消息**
         （调用方记 WARNING 后继续）：fresh clone 首跑本就要就地建库，不能误伤。

    返回 None 表示放行。Turso / Postgres 等非本地文件库无法判存在性，直接放行。
    """
    env = get_app_env()
    url, source = resolve_app_db(env)
    logger.info(f'[DB] APP_ENV={env}，market 域运行库: {url}（解析来源: {source}）')
    if not str(url).startswith('sqlite'):
        return None
    try:
        database = make_url(str(url)).database
    except Exception:  # noqa: BLE001 - URL 解析失败不阻断启动，按放行处理
        return None
    if not database or database == ':memory:':
        return None
    db_path = Path(database)
    if db_path.exists():
        return None
    resolved = db_path.resolve()
    # 显式配置了数据库（source != 'default'）但文件不存在：配置错误，直接报错
    if source != 'default':
        return (
            f'配置的运行库文件不存在（空库）：{resolved}（解析来源: {source}）。'
            '配置的数据库文件不存在，请检查 APP_ENV / DEV_DATABASE_URL / DATABASE_URL / STAGING_DATABASE_URL / '
            'TURSO_DATABASE_URL / DATABASE_URL 后重试。'
        )
    # source == 'default'：fresh clone 场景，按 strict 分级
    if strict:
        return (
            f'配置的运行库文件不存在（空库）：{resolved}（解析来源: {source}）。'
            '对着不存在的库跑显式目标同步/快照导出，只会静默新建空库后全部跳过（#2344 事故形态）；'
            '如本意是连既有库，请检查 APP_ENV / DEV_DATABASE_URL / DATABASE_URL 后重试。'
        )
    return (
        f'运行库目标文件不存在，将就地新建空库: {resolved}（解析来源: {source}）。'
        '若你本意是连既有库（如在 worktree / 非 backend 目录下运行），'
        '请检查 APP_ENV / DEV_DATABASE_URL / DATABASE_URL（#2344）。'
    )


@dataclass
class DatabaseConfig:
    """单一 engine 的连接配置。

    未来接入 Neon 灾备时，可在此扩展（如 standby_url / failover 策略），
    不必改动工厂主流程。
    """

    name: str  # 数据域：DOMAIN_APP / DOMAIN_USER
    url: str  # SQLAlchemy URL（或待构建的 URL 参数）
    connect_args: Dict = field(default_factory=dict)
    pool_pre_ping: bool = True
    echo: bool = False

    @classmethod
    def for_app(cls, env: str) -> 'DatabaseConfig':
        """应用运行库配置：dev 用本地 SQLite，prod 用 Turso（可回退 DATABASE_URL）。"""
        if env == 'development':
            url = os.getenv('DEV_DATABASE_URL', _DEFAULT_DEV_DB)
            return cls(name=DOMAIN_APP, url=url, connect_args=_sqlite_connect_args(url), pool_pre_ping=False)

        if env == 'staging':
            url = os.getenv('STAGING_DATABASE_URL') or os.getenv('DATABASE_URL', _DEFAULT_APP_DB)
            return cls(name=DOMAIN_APP, url=url, connect_args=_sqlite_connect_args(url), pool_pre_ping=False)

        # production：优先 Turso 运行库，回退到通用 DATABASE_URL（便于过渡期）
        url = os.getenv('TURSO_DATABASE_URL') or os.getenv('DATABASE_URL', _DEFAULT_APP_DB)
        # 方言决定 connect_args：Turso(libSQL) 不认识 SQLite 专有的 timeout（#1519）
        return cls(name=DOMAIN_APP, url=url, connect_args=_sqlite_connect_args(url), pool_pre_ping=True)

    @classmethod
    def for_user(cls, env: str) -> 'DatabaseConfig':
        """用户核心账本库配置：Supabase Postgres（独立）。

        优先级（「默认同库，显式配第二个库才分开」）：
        1. 显式配置 SUPABASE_DATABASE_URL → 真 Supabase（生产 / 最终验证）。
           注：development 下需同时设 DEV_FORCE_SUPABASE=1 才走本分支（见实现），
           否则仍按第 2 条本地回退。
        2. development 且未走真库：显式配置 DEV_USER_DATABASE_URL → 独立
           本地文件（本地双库模拟）；否则与 market 域共用 DEV_DATABASE_URL 同库
           （默认单库，本地既有 invest.db 数据立即可见，零迁移）。
        3. 其余环境（staging/production）未配 Supabase → 回退 USER_DATABASE_URL
           （缺省与 DATABASE_URL 同库）。

        设计要点：本方法永不返回 None（除非显式 force_none），因此 user 会话
        入口不再因「未配 Supabase」而抛错——这是单库/双库统一可用的关键。
        """
        if env == 'development' and not os.getenv('DEV_FORCE_SUPABASE'):
            url = _development_user_url()
            return cls(name=DOMAIN_USER, url=url, connect_args=_sqlite_connect_args(url), pool_pre_ping=False)
        url = os.getenv('SUPABASE_DATABASE_URL')
        if url:
            # Postgres 不需要 SQLite 专用 connect_args
            return cls(name=DOMAIN_USER, url=url, connect_args={}, pool_pre_ping=True)

        # 本地回退：development 未走 Supabase 时默认与 market 同库（防再次
        # 「默认拆开导致本地既有数据不可见」）；prod/staging 回退到通用 DATABASE_URL 同库
        if env == 'development':
            fallback = _development_user_url()
        else:
            fallback = os.getenv('USER_DATABASE_URL', _DEFAULT_APP_DB)
        return cls(
            name=DOMAIN_USER,
            url=fallback,
            connect_args=_sqlite_connect_args(fallback),
            pool_pre_ping=False,
        )


def _apply_sqlite_pragmas(engine: Engine) -> None:
    """SQLite 专用 PRAGMA：WAL 提升并发、开启外键约束（兜底防悬空引用）。"""

    @event.listens_for(engine, 'connect')
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA foreign_keys=ON;')
        cursor.close()


class DatabaseFactory:
    """按数据域构建并缓存 engine 的工厂。

    用法：
        engine = DatabaseFactory.create(DOMAIN_APP)         # 应用运行库
        user_engine = DatabaseFactory.create(DOMAIN_USER)   # 用户库（未配置则返回 None）
    或经 database.get_engine(domain) 取已缓存实例。
    """

    _engines: Dict[str, Optional[Engine]] = {}

    @classmethod
    def build(cls, domain: str, env: Optional[str] = None) -> Engine:
        """构建指定数据域的 engine（不缓存，供测试 mock）。

        user 域在未配置 SUPABASE_DATABASE_URL 时自动回退本地 SQLite 文件，
        因此本方法对任一域都保证返回可用引擎（永不返回 None）。
        """
        env = env or get_app_env()
        if domain == DOMAIN_USER:
            cfg = DatabaseConfig.for_user(env)
        else:
            cfg = DatabaseConfig.for_app(env)

        assert cfg is not None, f'数据域 {domain} 无法解析连接配置'

        url, extra_connect_args = _normalize_db_url(cfg.url)
        connect_args = {**cfg.connect_args, **extra_connect_args}
        # 兜底闸门（#1519）：方言不是本地 SQLite 时，剔除 SQLite 专有 connect_args。
        # 配置层（for_app / for_user）已按方言取值，此处再拦一道，防止将来新增分支
        # 又无条件注入 `timeout` / `check_same_thread`——它们只有 pysqlite 接受，
        # 传给 libSQL / psycopg2 会在**建立连接时**抛 TypeError，报错点离真因极远。
        if not _is_local_sqlite(url):
            leaked = [k for k in _SQLITE_ONLY_CONNECT_ARGS if k in connect_args]
            if leaked:
                for k in leaked:
                    connect_args.pop(k, None)
                logger.warning(
                    '方言 {} 不支持 SQLite 专有 connect_args {}，已剔除（#1519）',
                    url.split('://', 1)[0],
                    leaked,
                )
        engine = create_engine(
            url,
            connect_args=connect_args,
            pool_pre_ping=cfg.pool_pre_ping,
            echo=cfg.echo,
        )
        # 仅本地 SQLite 需要 PRAGMA（按 URL 判断，避免 libsql / Postgres 误用）
        if _needs_sqlite_pragmas(url):
            _apply_sqlite_pragmas(engine)
        return engine

    @classmethod
    def create(cls, domain: str, env: Optional[str] = None) -> Engine:
        """取（或构建并缓存）指定数据域的 engine。

        任一域都保证返回可用引擎：user 域未配 Supabase 时自动回退本地 SQLite，
        因此本地开发 / 测试零配置即可双库模拟。
        """
        if domain not in cls._engines:
            cls._engines[domain] = cls.build(domain, env)
        return cls._engines[domain]

    @classmethod
    def reset(cls) -> None:
        """清空缓存（测试用）。"""
        cls._engines.clear()

    @classmethod
    def tables_by_domain(cls, metadata) -> Dict[str, list]:
        """按数据域把 metadata 中的表分组。

        返回 {'market': [Table...], 'user': [Table...]}。
        校验：凡 metadata 中的表必须已在 DATA_DOMAIN_REGISTRY 登记，否则抛 ValueError
        （防漏声明导致建错库 / 读错库）。

        注意：本方法**不**判断注册表孤儿项——metadata 只含本进程已 import 的模型，
        在这里判孤儿会把「未导入」误报成「模型已删除」，孤儿判定见
        `classify_registry_orphans()` / `validate_domain_labels()`（#1521）。
        """
        from sqlalchemy import MetaData

        if metadata is None:
            metadata = MetaData()
        result = {DOMAIN_MARKET: [], DOMAIN_USER: []}
        registry_keys = set(DATA_DOMAIN_REGISTRY)
        model_tables = set(metadata.tables.keys())

        # 1) 模型表必须全部登记；未登记的立即 fail
        unregistered = sorted(model_tables - registry_keys)
        if unregistered:
            raise ValueError(
                '以下表未在 DATA_DOMAIN_REGISTRY 声明数据域，禁止建库（防建错库）：'
                f' {unregistered}。请在 db_factory.DATA_DOMAIN_REGISTRY 补登记，'
                '判定规则见 AGENTS.md「多引擎数据域约束」。'
            )

        for table in metadata.tables.values():
            domain = DATA_DOMAIN_REGISTRY[table.name]
            result[domain].append(table)
        return result

    @classmethod
    def classify_registry_orphans(cls, metadata, source_text: Optional[str] = None) -> Tuple[list, list]:
        """把「已登记但不在 metadata 中」的表分成两类。

        返回 `(not_imported, missing_in_source)`：
        - `not_imported`：源码里能找到该表名的定义 → 只是本进程没 import，属正常现象；
        - `missing_in_source`：源码里也找不到 → 疑似模型已删除（注册表 / 文档漂移），需处理。

        `source_text` 无法取得（None）时全部归入 `not_imported`：宁可不报，也不把
        「没读到源码」错报成「模型已删除」——后者会把排查引向完全错误的方向（#1521）。
        """
        registry_keys = set(DATA_DOMAIN_REGISTRY)
        model_tables = set(metadata.tables.keys()) if metadata is not None else set()
        orphan = sorted(registry_keys - model_tables - set(PENDING_DOMAIN_REGISTRY))
        if not orphan:
            return [], []

        if source_text is None:
            source_text = _model_source_text()
        if source_text is None:
            return orphan, []

        declared = [name for name in orphan if f"'{name}'" in source_text or f'"{name}"' in source_text]
        missing = [name for name in orphan if name not in declared]
        return declared, missing

    @classmethod
    def validate_domain_labels(cls, metadata) -> None:
        """启动期断言：每个表都已声明合法数据域（供 init_db 调用）。

        除致命校验（漏登记）外，额外检查注册表孤儿项。孤儿分两类、措辞分开（#1521）：
        本进程未 import 的表只记 info（CLI / 定时任务只导入所需模型属正常，旧版把它
        报成「模型未定义」曾误导排查），只有源码里也找不到的才记 warning。
        """
        grouped = cls.tables_by_domain(metadata)
        not_imported, missing = cls.classify_registry_orphans(metadata)

        if not_imported:
            logger.info(
                '以下表已登记、源码中也有模型定义，但本进程未 import（共 {} 张）：{}。'
                '这不是错误——CLI / 定时任务只导入所需模型属正常现象，无需处理。',
                len(not_imported),
                not_imported,
            )
        if missing:
            logger.warning(
                'DATA_DOMAIN_REGISTRY 存在孤儿表（已登记但源码中找不到定义，疑为模型已删除）：{}。'
                '请同步 db_factory.DATA_DOMAIN_REGISTRY 与 docs/dev/db-data-domain.md；'
                '排查：rg -n "{}" backend/app/domains backend/app/models --glob "*.py"',
                missing,
                '|'.join(missing),
            )
        return grouped


def market_session_factory() -> sessionmaker:
    """market 域会话工厂（Turso / 开发期本地 SQLite 替身）。

    业务层读取市场数据（净值/行情/温度/基金资料）必须且只能经此入口，
    禁止与 user 域会话混用。引擎未配置时抛 RuntimeError（开发期必须配置 APP 库）。
    """
    eng = DatabaseFactory.create(DOMAIN_APP)
    if eng is None:
        raise RuntimeError('market 域引擎未配置，无法创建会话（检查 APP_ENV / DATABASE_URL）。')
    return sessionmaker(autocommit=False, autoflush=False, bind=eng)


def user_session_factory() -> sessionmaker:
    """user 域会话工厂（Supabase / 本地 SQLite 回退）。

    业务层读写用户账本（账户/持仓/交易/自选/审计）必须且只能经此入口，
    禁止与 market 域会话混用。

    单库/双库统一可用：
    - 配置了 SUPABASE_DATABASE_URL → 真 Supabase（最终验证 / 生产）。
    - 未配置 → development 下**默认与 market 域同库**（DEV_DATABASE_URL，缺省
      invest.db，即本地单库）；只有显式配 DEV_USER_DATABASE_URL 才落到独立文件
      （如 invest.user.dev.db，本地双库模拟）。业务代码无需任何分支判断。
    """
    eng = DatabaseFactory.create(DOMAIN_USER)
    return sessionmaker(autocommit=False, autoflush=False, bind=eng)
