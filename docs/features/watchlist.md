---
title: 自选股功能设计
permalink: /watchlists
---
#### 1.1 文档概述

##### 1.1.1 背景与痛点

在个人投资过程中，现有平台的自选功能存在以下问题：

-   多市场代码格式不统一，导入和识别困难
-   无法与个人持仓、交易记录深度关联
-   场内资产（股票/ETF/可转债）与场外基金割裂，需在两个平台或页面分别查看
-   公募基金经理频繁跳槽，甚至从公募转向私募，缺乏对其全投资生涯的追踪工具
-   缺乏投资逻辑的记录和回溯功能
-   广告多，功能冗余，不符合个人使用习惯
-   数据无法自由导出和备份

##### 1.1.2 核心目标

1.  **统一管理**：支持 A 股、港股、美股等多市场场内资产（股票、ETF、可转债）与场外基金的统一代码标准化和一站式管理
2.  **决策辅助**：提供清晰的行情数据、关键指标和异动信息，辅助投资决策
3.  **记账集成**：与简记弹窗和全面盘点页面无缝打通，实现"看盘-决策-交易-记账"的闭环
4.  **逻辑沉淀**：记录每只自选股的关注理由、分析笔记和投资决策过程
5.  **经理追踪**：跨越公募与私募机构，追踪基金经理的全投资生涯，辅助判断其能力与稳定性
6.  **深度关系维护**：对投入大量精力研究或持有过的资产，提供"特别关注"机制，保留私有研究知识
7.  **数据自由**：支持完整的数据导入导出，确保个人数据所有权

##### 1.1.3 与现有系统的关系

本模块并非独立系统，而是 多倍贝 的组成部分：

-   **复用 `positions` 表**：自选股的资产基础信息（代码、名称、市场、类型）与持仓模型完全对齐，消除数据孤岛
-   **复用 `transactions` 表**：清仓状态由交易流水动态推导，不在 `watchlist` 表中冗余存储
-   **状态联动**：持仓状态由交易记录自动驱动（买入即持仓、清仓即从持仓分组移除）
-   **记账入口一致**：自选页面的"快速记账"直接唤起简记弹窗，"复杂操作"跳转至全面盘点页面
-   **扩展追踪对象**：自选对象从"资产"扩展为"资产 + 基金经理"，两者在同一体系下按需切换视图

---

#### 1.2 功能需求总览

| 模块 | 核心功能 | 优先级 |
|------|----------|--------|
| 基础自选管理 | 资产添加/删除/搜索、代码标准化、置顶(Pin) | P0 |
| 分组体系 | 系统分组（动态筛选）+ 自定义分组、颜色标记、排序 | P0 |
| 标签管理 | 多标签、标签颜色、标签筛选 | P0 |
| 自定义显示 | 视图切换（全部/场内/场外）、表头自适应、排序、涨跌高亮 | P0 |
| 行情与数据展示 | 手动价格/净值更新(P0)、自动行情刷新(P1) | 分阶段 |
| 投资记录关联 | 一键唤起简记、交易历史查看、盈亏联动 | P0 |
| 特别关注 | 清仓后保留深度关系、独立视图、复盘提醒 | P0 |
| 清仓分析 | 按时间线/按产品汇总、盈亏统计、基准对比 | P1 |
| 笔记与分析 | 关注理由、投资笔记、决策记录 | P1 |
| 基金经理跟踪 | 经理添加/关注、任职历史、业绩回溯、变更提醒 | P1 |
| 异动提醒 | 涨跌幅阈值设置、页面高亮提醒(P1)、主动推送(P2) | 分阶段 |
| 导入导出 | 批量导入、跨平台迁移、数据备份 | P1 |
| 高级分析 | 分组盈亏、行业分布、估值分析 | P2 |

---

#### 1.3 数据模型设计

> **核心原则**：与 `SPEC.md` 中定义的 `positions` 表完全对齐。自选对象从单纯的资产，扩展为"资产"与"基金经理"两类可追踪实体。**清仓不再作为 `watchlist` 的状态存储，改为从 `transactions` 表动态推导。**

##### 1.3.1 自选资产关注表 `watchlist`

```sql
CREATE TABLE watchlist (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL COMMENT '标准化代码，与 positions.symbol 对齐',
    market VARCHAR(10) NOT NULL COMMENT '市场代码',
    type VARCHAR(20) COMMENT '资产类型：STOCK/ETF/FUND/CB/INDEX',
    venue VARCHAR(10) DEFAULT 'EXCHANGE' COMMENT '交易场所：EXCHANGE(场内) / OTC(场外)',

    -- 状态：仅保留两个值，已清仓由前端动态推导
    status VARCHAR(20) DEFAULT 'HOLDING' COMMENT 'HOLDING(持仓中) / WATCHING(观察中)。CLEARED 不存储，由前端根据 positions+transactions 推导',

    -- 特别关注：清仓后保留深度关系的资产
    favorite BOOLEAN DEFAULT FALSE COMMENT '特别关注标记。清仓后保留的深度研究资产',
    favorite_at DATE COMMENT '设为特别关注的日期',
    source_cycle_id INT COMMENT '关联的清仓周期ID，指向 cleared_cycles.id。NULL 表示非清仓保留',

    -- 置顶
    is_pinned BOOLEAN DEFAULT FALSE COMMENT '是否置顶',
    pinned_at TIMESTAMP COMMENT '置顶时间',

    -- 笔记与理由
    add_reason TEXT COMMENT '添加自选时的关注理由',
    notes TEXT COMMENT '投资笔记/交易手札（Markdown）',

    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uk_symbol_market_venue (symbol, market, venue)
);
```

**关键设计决策**：

-   **`status` 只有两个值**：`HOLDING`（持仓中）和 `WATCHING`（观察中）。"已清仓"不作为状态存储，而是由前端根据以下条件动态推导：`positions` 表中无持仓 + `transactions` 表中有买入+卖出记录。
-   **唯一键**采用 `(symbol, market, venue)` 组合，防止不同市场相同数字代码冲突（如 `000001` 既是深交所平安银行也是华夏成长混合）。
-   **移除 `cleared_at` 字段**：最后一次清仓时间改为从 `transactions` 表动态查询最后一条 `sell` 记录，避免多次清仓覆盖和不一致风险。
-   **`venue` 手动修正**：系统自动推断后，用户可通过界面手动修改。正确的修正结果反馈到标准化模块。
-   **`bookmarked` 标记**：清仓后用户主动保留的深度研究资产。这些资产在特别关注页面（`/starred`）中展示，与普通自选页面分离。

##### 1.3.2 分组表 `watchlist_groups`

```sql
CREATE TABLE watchlist_groups (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL COMMENT '分组名称',
    color VARCHAR(7) COMMENT '分组颜色（预设色盘取值）',
    sort_order INT DEFAULT 0 COMMENT '排序顺序',
    is_system BOOLEAN DEFAULT FALSE COMMENT '是否系统默认分组',
    is_visible BOOLEAN DEFAULT TRUE COMMENT '用户是否开启显示（仅默认可选分组可用）',
    entity_type VARCHAR(20) DEFAULT 'ASSET' COMMENT 'ASSET(资产) / MANAGER(经理)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

##### 1.3.3 自选资产-分组关联表 `watchlist_group_link`

```sql
CREATE TABLE watchlist_group_link (
    id INT AUTO_INCREMENT PRIMARY KEY,
    watchlist_id INT NOT NULL,
    group_id INT NOT NULL,
    FOREIGN KEY (watchlist_id) REFERENCES watchlist(id),
    FOREIGN KEY (group_id) REFERENCES watchlist_groups(id),
    UNIQUE KEY uk_watchlist_group (watchlist_id, group_id)
);
```

**关键设计决策**：

-   此表**仅存储用户自定义分组**和系统分组中"持仓""已清仓""组合"的关联。
-   **"场内资产""场外基金""海外""指数""货基""债基"等系统分组不再写入此表**，由前端根据 `market`、`venue`、`type` 字段动态筛选渲染，消除数据冗余和同步负担。

##### 1.3.4 标签表与关联表

```sql
CREATE TABLE tags (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL COMMENT '标签名称',
    color VARCHAR(7) COMMENT '标签颜色（预设色盘取值）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE watchlist_tags (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    tag_id INT NOT NULL,

    FOREIGN KEY (symbol) REFERENCES watchlist(symbol),
    FOREIGN KEY (tag_id) REFERENCES tags(id),
    UNIQUE KEY uk_symbol_tag (symbol, tag_id)
);
```

##### 1.3.5 异动提醒表 `alerts`

```sql
CREATE TABLE alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    alert_type VARCHAR(20) NOT NULL COMMENT 'PRICE_UP/PRICE_DOWN/CHANGE_PCT',
    threshold_value DECIMAL(15,4) COMMENT '阈值',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    last_triggered_at TIMESTAMP COMMENT '上次触发时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

##### 1.3.6 清仓周期快照表 `cleared_cycles`

此表用于缓存清仓计算结果，支撑清仓分析页面和特别关注功能。可纯从 `transactions` 表实时计算，但为性能考虑做快照缓存。

```sql
CREATE TABLE cleared_cycles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    cycle_number INT NOT NULL COMMENT '第几次清仓（按时间排序，从1开始）',
    first_buy_date DATE NOT NULL COMMENT '本轮首次买入日期',
    last_sell_date DATE NOT NULL COMMENT '本轮最后卖出日期',
    total_buy_amount DECIMAL(15,2) COMMENT '买入总金额（本币）',
    total_sell_amount DECIMAL(15,2) COMMENT '卖出总金额（本币）',
    total_fee DECIMAL(15,2) COMMENT '总费用',
    realized_pnl DECIMAL(15,2) COMMENT '已实现盈亏（卖出-买入-费用）',
    realized_pnl_pct DECIMAL(10,4) COMMENT '盈亏率（%）',
    holding_days INT COMMENT '持仓天数',
    trade_count INT COMMENT '交易笔数（买入+卖出）',
    benchmark_return DECIMAL(10,4) COMMENT '同期基准涨跌幅（%）',
    next_review_date DATE COMMENT '下次复盘提醒日期（用户可设置）',
    review_notes TEXT COMMENT '复盘笔记',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_symbol (symbol),
    INDEX idx_last_sell_date (last_sell_date)
);
```

##### 1.3.7 基金经理信息表 `fund_managers`

```sql
CREATE TABLE fund_managers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL COMMENT '经理姓名',
    avatar_url VARCHAR(255) COMMENT '照片链接',
    gender CHAR(1) COMMENT '性别',
    education TEXT COMMENT '学历背景',
    bio TEXT COMMENT '个人简介（从业经历摘要）',
    first_active_date DATE COMMENT '首次任职日期（投资生涯起点）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

##### 1.3.8 基金经理任职记录表 `manager_tenures`

```sql
CREATE TABLE manager_tenures (
    id INT AUTO_INCREMENT PRIMARY KEY,
    manager_id INT NOT NULL,
    fund_symbol VARCHAR(50) NOT NULL COMMENT '基金标准化代码',
    fund_name VARCHAR(100) COMMENT '基金名称',
    fund_type VARCHAR(20) COMMENT '基金类型',
    institution_name VARCHAR(100) COMMENT '所在机构（公募/私募）',
    start_date DATE NOT NULL COMMENT '任职起始',
    end_date DATE COMMENT '离任日期（空表示至今）',
    return_rate DECIMAL(10,4) COMMENT '任职回报（%）',
    annual_return DECIMAL(10,4) COMMENT '年化回报（%）',
    benchmark_return DECIMAL(10,4) COMMENT '同期基准回报',

    FOREIGN KEY (manager_id) REFERENCES fund_managers(id),
    INDEX idx_manager (manager_id),
    INDEX idx_fund (fund_symbol)
);
```

##### 1.3.9 基金经理关注表 `watchlist_managers`

```sql
CREATE TABLE watchlist_managers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    manager_id INT NOT NULL,
    group_id INT COMMENT '分组ID（可选）',
    is_pinned BOOLEAN DEFAULT FALSE COMMENT '是否置顶',
    notes TEXT COMMENT '关注理由/笔记',
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (manager_id) REFERENCES fund_managers(id),
    FOREIGN KEY (group_id) REFERENCES watchlist_groups(id)
);
```

##### 1.3.10 基准指数缓存表 `benchmark_indices`

```sql
CREATE TABLE benchmark_indices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    index_code VARCHAR(20) NOT NULL COMMENT '如 000300（沪深300）',
    trade_date DATE NOT NULL,
    close_price DECIMAL(10,4) NOT NULL,
    UNIQUE KEY uk_code_date (index_code, trade_date)
);
```

##### 1.3.11 价格历史表 `price_history`

```sql
CREATE TABLE price_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    trade_date DATE NOT NULL,
    close_price DECIMAL(10,4) COMMENT '收盘价/单位净值',
    source VARCHAR(20) DEFAULT 'MANUAL' COMMENT 'MANUAL / AUTO',

    UNIQUE KEY uk_symbol_date (symbol, trade_date),
    INDEX idx_date (trade_date)
);
```

---

#### 1.4 状态推导与数据流

**`status` 字段推导逻辑（伪代码）**：

```plain
function deriveAssetState(symbol):
    position = SELECT * FROM positions WHERE symbol = ?
    transactions = SELECT COUNT(*) FROM transactions WHERE symbol = ? AND type IN ('BUY','SELL')

    if position exists AND position.quantity > 0:
        return 'HOLDING'      // 持仓中

    if inWatchlist(symbol):
        if hasTransactions(symbol) AND hasBuyAndSell(symbol):
            return 'CLEARED'  // 前端显示用，不存表
        else:
            return 'WATCHING' // 观察中（从未买入或只有买入未清仓）

    return null               // 不在自选列表
```

**前端分组展示逻辑**：

| 显示的组 | 筛选条件 | 页面 |
|----------|----------|------|
| 持仓 | `status = HOLDING` + `positions` 有持仓 | 普通自选页面 |
| 观察中 | `status = WATCHING` + `bookmarked = FALSE` | 普通自选页面 |
| 已清仓 | 有交易记录 + 无持仓 + 清仓日期距今 ≤ 30 天 + `bookmarked = FALSE` | 普通自选页面（临时分组） |
| 特别关注 | `bookmarked = TRUE` | 特别关注页面 `/starred` |

**清仓后 30 天自动移除规则**：

-   资产清仓后，自动出现在"已清仓"分组
-   30 天内，用户可操作：点击"特别关注"按钮 → `bookmarked = TRUE`，资产移至特别关注页面
-   30 天后未标记特别关注的资产：自动从自选列表移除。数据完整保留在 `transactions` 和 `cleared_cycles` 表中，清仓分析页面不受影响

**特别关注标记触发条件**：

-   **手动触发**：用户在"已清仓"分组中点击"特别关注"按钮
-   **智能提示**：系统根据以下条件，在清仓时自动提示"是否设为特别关注？"
    -   持有天数 > 180 天
    -   交易笔数 > 6 次
    -   `watchlist.notes` 非空（写过交易手札）
    -   累计买入金额超过用户设置的门槛
    -   盈亏率极端（亏损 > 20% 或 盈利 > 50%）

---

#### 1.5 功能详述

##### 1.5.1 基础自选管理（P0）

**资产添加**

-   **支持的全部资产类型**：场内（股票、ETF、LOF、可转债、场内货基/债基）、场外（开放式基金、场外货基/债基）、指数
-   **自动识别场内/外**：系统根据代码规则自动判定 `venue`，用户可在添加时手动修正
-   **多格式代码输入**，自动标准化：
    -   港股：`HK00700`、`00700.HK`、`00700`、`700` → `HK.00700`
    -   A 股：`SH600519`、`600519.SH`、`600519` → `SH.600519`
    -   美股：`AAPL`、`US.AAPL`、`AAPL.US` → `US.AAPL`
    -   场外基金：前缀 `OF.` → `OF.012708`
-   **名称搜索**：支持名称、简称、拼音首字母搜索
-   **快速批量添加**：文本域一行一个代码，批量解析后预览确认
-   **重复检测**：基于唯一键 `(symbol, market, venue)` 检测
-   **添加确认弹窗**：展示资产全称、市场、类型、场内/场外标签

**`venue` 手动修正**

-   资产添加后，用户在自选列表可手动修改 `venue` 字段
-   正确的修正结果反馈到标准化模块，记录样本以优化自动推断规则

**资产删除**

-   单个/批量删除
-   如有持仓，提示用户先清仓或确认强制移除

**搜索与筛选**

-   全局搜索（资产 + 经理）：代码、名称、拼音
-   市场筛选：A 股 / 港股 / 美股 / 全部
-   类型筛选：股票 / ETF / 可转债 / 场外基金 / 指数
-   场内/场外快速筛选
-   状态筛选：观察中 / 持仓中
-   分组筛选：点击左侧分组树筛选
-   标签筛选：点击标签筛选

**置顶功能（Pin）**

-   **设计参考**：GitHub 首页项目置顶
-   **置顶区位置**：列表顶部，与下方分隔
-   **置顶数量**：资产上限 6 个，经理上限 3 个（可配置）
-   **置顶操作**：右键菜单或拖拽
-   **置顶区内部**：支持拖拽排序

##### 1.5.2 分组体系（P0）

**分组总览**

| 类型 | 分组名 | 能否关闭显示 | 能否删除 | 对象来源 | 实体类型 |
|------|--------|:-----------:|:-------:|----------|----------|
| **系统（不可关闭）** | 持仓 | ✗ | ✗ | `positions` 表中有持仓的资产 | 资产 |
| | 已清仓 | ✗ | ✗ | 清仓后 30 天内 + 无持仓 + `bookmarked = FALSE` | 资产 |
| **系统（可关闭）** | 场内资产 | ✓ | ✗ | 动态筛选：`venue=EXCHANGE` | 资产 |
| | 场外基金 | ✓ | ✗ | 动态筛选：`venue=OTC` | 资产 |
| | 海外 | ✓ | ✗ | 动态筛选：非 A 股市场 | 资产 |
| | 组合 | ✓ | ✗ | 手动拖入自建组合 | 资产 |
| | 指数 | ✓ | ✗ | 动态筛选：`type=INDEX` | 资产 |
| | 货基 | ✓ | ✗ | 动态筛选：货币基金 | 资产 |
| | 债基 | ✓ | ✗ | 动态筛选：债券基金 | 资产 |
| | 特别关注 | ✓ | ✗ | `bookmarked = TRUE` | 资产 |
| | 关注的经理 | ✓ | ✗ | 用户关注的经理 | 经理 |
| **用户自定义** | 任意名称 | ✓ | ✓ | 手动添加/移出 | 资产或经理 |

**系统分组动态渲染规则**

-   "持仓"：`positions` 表中有持仓且在 `watchlist` 中 → 自动显示
-   "已清仓"：清仓后 ≤ 30 天 + `bookmarked = FALSE` → 自动显示。**30 天后未标记特别关注的资产自动从自选列表移除**
-   "场内资产"：`venue = EXCHANGE` → 动态筛选
-   "场外基金"：`venue = OTC` → 动态筛选
-   "海外"：`market` 非 `SH`、`SZ` → 动态筛选
-   "指数"：`type = INDEX` → 动态筛选
-   "货基"、"债基"：按 `type` 筛选
-   "特别关注"：`bookmarked = TRUE` → 包含持仓中、观察中、已清仓但保留的所有特别关注资产
-   **以上基于单字段的系统分组不写入 `watchlist_group_link` 表**，避免数据冗余

**分组管理**

-   仅自定义分组可创建/删除/重命名
-   分组颜色：预设 6 个低饱和度色盘（`#E8D5C4` 杏、`#B5C4B1` 鼠尾草绿、`#C4C8D0` 雾蓝、`#D4C5C7` 藕粉、`#A3B5C7` 灰蓝、`#C5C9B8` 橄榄灰）
-   分组支持拖拽排序；组内资产支持拖拽排序

##### 1.5.3 标签管理（P0）

-   自定义标签，与分组共用同一预设色盘
-   一只资产可绑定多个标签
-   点击标签筛选资产

##### 1.5.4 视图切换与自定义显示（P0 / P2）

**视图切换器**（列表上方）

-   **全部** / **场内** / **场外**，三个按钮切换
-   切换时表格列集合自动变化

**默认列表头**

**全部视图**：代码 | 名称 | 场内/场外标签 | 最新价/净值 | 涨跌幅/估算涨幅 | 持仓市值 | 浮动盈亏 | 盈亏比例 | 经理（场外显示）

**场内视图**：代码 | 名称 | 最新价 | 涨跌幅 | 涨跌额 | 持仓数量 | 持仓市值 | 浮动盈亏 | 盈亏比例

**场外视图**：代码 | 名称 | 单位净值 | 累计净值 | 日涨幅(估算) | 持仓份额 | 持仓市值 | 浮动盈亏 | 基金经理

**自定义表头**（P2，低优先级）

-   每个视图可单独配置显示列、列宽、列顺序

**涨跌视觉**

-   上涨：红色；下跌：绿色；平盘：灰色
-   持仓资产行：左侧细微色条标记

##### 1.5.5 行情与数据展示（分阶段）

-   **P0**：手动更新价格/净值。双击单元格直接输入。同步更新 `positions.current_price`
-   **P1**：接入 `xalpha` 或同类合规数据源自动刷新。设计数据源适配层方便切换
-   分组概览：组名旁显示资产数量、平均涨跌幅

##### 1.5.6 投资记录关联（P0）

-   **快速记账**：右键 → 唤起简记弹窗，自动填入代码、名称、场内/场外属性
-   **复杂记账**：右键 → 跳转全面盘点页面，预筛选该资产
-   **交易历史**：侧边抽屉展示全部交易记录
-   **盈亏联动**：持仓列数据实时来自 `positions` 表
-   **状态自动同步**：买入→进入"持仓"分组；清仓→进入"已清仓"分组

##### 1.5.7 未竟之蹊（P0）

> 此功能解决的核心问题：用户对某些资产投入了大量研究精力或持有多年，清仓后不希望这些私有知识随资产一起"消失"。通过特别关注机制，保留深度关系，提供独立的回顾和复盘视图。

**用户这样描述自己对这个页面的理解：我认为归档或者复盘是对我们特别耗费精力的事情，我们并不会对所有投资过的产品去认真复盘，就好像我们每天走在路上遇到好多人，但是你只会把那些你**在乎的朋友**放在心上牵挂……**

**页面路由**：`/the-road-not-taken`

**页面定位**：与普通自选页面完全不同的视图。普通自选关注"实时数据"（价格、涨跌、盈亏），特别关注页面关注"私有思考 + 资产变迁"。

**展示形式**：卡片流而非表格行。每张卡片展示一个特别关注资产。

**卡片内容设计**：

```plain
┌─────────────────────────────────────────┐
│ ⭐ 贵州茅台  SH.600519                   │
│                                          │
│ 持有 687 天，清仓 2 次，2025-03-12 标记  │
│                                          │
│ 💬 最近笔记（2025-03-12）：               │
│  "茅台估值已回到合理区间，但消费复苏      │
│   不及预期，暂不买入"                     │
│                                          │
│ ─────────────────────────────────────── │
│ 清仓后至今：-12.3%                        │
│ 同期白酒指数：-8.7%                       │
│ 你跑赢了 3.6%                             │
│                                          │
│ [查看清仓分析] [写笔记] [移回自选]        │
│ ⏰ 下次复盘：2025-06-12                   │
└─────────────────────────────────────────┘
```

**卡片排序**：默认按"最近更新时间"排序（有新手札的在上方）。也支持按标记时间、持有天数排序。

**添加方式**：

-   **手动添加**：在"已清仓"分组中，点击资产行右侧的"特别关注"按钮
    -   弹出气泡：已加入特别关注。你希望什么时候提醒复盘？选项：1 个月后 / 3 个月后 / 暂不提醒
-   **智能提示**：资产清仓时，若满足以下条件之一，系统自动弹出提示"是否设为特别关注？"
    -   持有天数 > 180 天
    -   交易笔数 > 6 次
    -   `watchlist.notes` 非空（写过交易手札）
    -   累计买入金额超过用户设置的门槛
    -   盈亏率极端（亏损 > 20% 或 盈利 > 50%）

**特别关注页面与普通自选页面的区别**：

| 维度 | 普通自选 | 特别关注 |
|------|----------|----------|
| 关注点 | 实时数据 | 私有思考 + 资产变迁 |
| 展示 | 表格行 | 卡片流 |
| 核心信息 | 最新价、涨跌幅、盈亏 | 笔记摘要、清仓后走势、复盘提醒 |
| 排序 | 涨跌幅/盈亏 | 最近笔记时间/标记时间 |
| 操作 | 快速记账、查看行情 | 查看分析、写笔记、设置提醒 |

##### 1.5.8 清仓分析（P1）

**功能定位**

清仓分析是复盘模块的子页面，专门分析**已完成交易**（清仓）的投资绩效。这是从"持仓盈亏"到"实现盈亏"的关键视角转换。

**页面路由**：`/review/cleared`

**入口**：

-   **轻量入口**（自选列表"已清仓"分组内部顶部）：

    ```plain
    📊 清仓分析（快捷）
    近30天清仓：3只  |  总实现盈亏：+1,234.56元
                     |  盈利 2只 / 亏损 1只
    [查看完整分析 →]
    ```

-   **完整页面入口**：侧边栏"已清仓"分组旁按钮；资产复盘页面顶部导航

**视图切换**

页面顶部两个标签页切换：

| 视图 | 说明 |
|------|------|
| **按时间线** | 以清仓日期为序，展示每一笔清仓周期的盈亏 |
| **按产品汇总** | 以资产（同一代码多次交易）为维度，汇总多次清仓的累计表现 |

两个标签页内部各有"场内"和"场外"子筛选器。

**按时间线视图表头**：

| 列名 | 说明 | 计算方式 |
|------|------|----------|
| 清仓日期 | 最后卖出日期 | 从 `cleared_cycles.last_sell_date` |
| 代码 | | |
| 名称 | | |
| 场内/场外 | | |
| 持仓天数 | 首次买入到最后卖出 | `cleared_cycles.holding_days` |
| 盈亏金额(元) | 已实现盈亏，人民币 | `realized_pnl` |
| 盈亏率(%) | | `realized_pnl_pct` |
| 年化收益(%) | | `(1+盈亏率)^(365/持仓天数)-1` |
| 同期基准涨幅(%) | | `benchmark_return` |
| 清仓后 N 日涨幅(%) | P2 启用，需 `price_history` | |
| 交易次数 | | `trade_count` |

**按产品汇总视图表头**：

| 列名 | 说明 |
|------|------|
| 代码 | |
| 名称 | |
| 场内/场外 | |
| 清仓次数 | |
| 累计盈亏金额(元) | |
| 胜率(%) | 盈利次数 / 总清仓次数（按盈亏金额正负判定） |
| 平均盈亏率(%) | |
| 加权平均年化(%) | |
| 平均持仓天数 | |
| 总持仓天数 | |
| 同期基准平均涨幅(%) | |

点击行展开，下方列出该资产的每一次清仓明细。

**基准选择器**：页面顶部，默认沪深 300。可选：上证指数、创业板指、恒生指数、标普 500。

**清仓后涨幅列**：P1 阶段灰色显示"需要价格历史数据"，引导用户补充数据。

**导出**：两个视图均支持导出 Excel/CSV。

##### 1.5.9 笔记与分析（P1）

-   关注理由：添加自选时填写；悬停资产行显示摘要
-   投资笔记：Markdown 编辑器，自动记录编辑时间线
-   决策记录：与交易记录关联，复盘可追溯

##### 1.5.10 异动提醒（分阶段）

-   **P1**：设置单日涨跌幅阈值。打开/刷新页面时高亮提醒触发资产
-   **P2**：浏览器通知等主动推送

##### 1.5.11 导入导出（P1）

-   **导入**：P1 阶段支持 多倍贝 自有格式和纯文本代码列表。东方财富、同花顺、雪球等跨平台模板放 P2 按需支持
-   **导出**：自选资产列表、经理关注列表及任职记录、完整备份

##### 1.5.12 基金经理跟踪（P1）

**数据范围**（P1 阶段降级）

-   P1 阶段仅包含：经理姓名、简介、手动关联的基金列表（无任职回报等专业数据）
-   任职回报、年化回报等业绩数据延后到 P2
-   P2 优先从用户本地基金净值数据反推经理业绩，而非依赖外部数据源

**功能**

-   经理搜索（本地库），无结果则创建新经理
-   创建时可关联已自选的基金
-   经理列表：姓名、当前管理基金数、代表基金、最新变更
-   经理详情面板：基本资料、职业生涯时间轴（公募/私募用颜色区分）、任职基金列表
-   变更提醒：系统启动或手动触发检测任职变更，红点通知

##### 1.5.13 高级分析（P2）

-   分组盈亏分析、行业分布、估值分析、收益曲线

---

#### 1.6 开发优先级

| 阶段 | 周数 | 交付内容 |
|------|------|----------|
| **P0** | 2-3 周 | 数据模型建表；资产添加/删除/搜索/批量（含场内/场外自动识别+手动修正）；代码标准化；分组体系（系统分组动态渲染+自定义分组）；标签管理；置顶；拖拽排序；手动价格/净值更新；视图切换及自适应表头；持仓盈亏联动；简记弹窗唤起；特别关注标记与页面 |
| **P1** | 2-3 周 | 自动行情/净值数据源；清仓分析页面（按时间线+按产品汇总）；基金经理基础信息与关联；经理详情面板；变更提醒（页面内）；关注理由与投资笔记；异动提醒（页面内高亮）；导入导出（自有格式+纯文本列表）；清仓后 30 天自动移除；深色模式 |
| **P2** | 后续 | 自定义表头；高级分析模块；经理业绩数据（优先从本地反推）；跨平台导入；清仓后涨幅；主动推送提醒；移动端适配 |


### 附录：全局设计原则

1.  **数据模型统一**：自选资产、交易记录、持仓模型深度整合。不自建新资产主表
2.  **动态优先于存储**：能用单字段筛选的不建关联表，能计算的不存储冗余状态
3.  **状态自动驱动**：持仓由 `positions` 驱动；清仓由 `transactions` 推导；特别关注由用户选择
4.  **清仓后默认不保留**：30 天后自动移除，只有用户主动标记的才留在"特别关注"
5.  **渐进式复杂度**：先手动后自动，先基础后高级，承认数据局限性
6.  **一个体系，两种视图**：场内场外通过视图切换和动态筛选管理
7.  **视觉克制**：颜色仅限预设低饱和莫兰迪色系色盘
8.  **入口一致性**：简记和全面盘点是唯一记账入口
