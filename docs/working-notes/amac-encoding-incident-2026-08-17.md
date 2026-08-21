# AMAC 名录乱码事故复盘与编码纪律（2026-08-17）

## 事故经过

`amac_institution` 同步 job 首次验证时，库中 AMAC 销售机构（394 条）/ 公募基金管理人（165 条）的中文名称全部为乱码：

```
「中国建设银行」→「涓�鍥藉缓璁鹃摱琛�」
```

## 根因

AMAC 接口响应头为 `application/json;charset=UTF-8`（实测 apparent_encoding=utf-8），
而 job 里硬编码了 `resp.encoding = 'gbk'`，导致 **UTF-8 字节被 GBK 错误解码** 后写入数据库。

关键证据链：

- `resp.content` 原始字节为 `e4 b8 ad e5 9b bd...`（中国建设银行的 UTF-8 编码）
- 按 GBK 解码 → `涓�鍥藉缓璁鹃摱琛�`（含 U+FFFD 替换符）
- 两次验证脚本 LIMIT 1 取到不同记录（建设银行 / 桂林银行），但乱码模式完全一致

## 排查中的两个误区（勿再犯）

1. **「job 写入的库和验证读取的库不是同一个」是错误推断**：
   本项目只有一个数据库 `backend/invest.db`。job 日志 `success=559` 但库总数不变，
   并非写入失败或库不一致，而是 `base.py` 的 `stats['success'] = len(new_data)` 统计的是
   **处理记录数而非新增数**；且乱码与乱码完全相等，559 条全部命中 upsert 的 update 分支。
   排查时应先读代码确认统计语义，再下「多库」结论。
2. **没有在写入前校验数据质量**：入库守卫缺失，乱码直接落库污染数据。

## 处置（已落地）

1. 删除 `resp.encoding = 'gbk'` 硬编码，依赖响应头 charset 自动解码（requests 默认行为）。
2. `_validate_data` 增加编码守卫：名称含 U+FFFD（�）即丢弃并告警，**绝不入库**。
3. 清空两张表污染数据（备份 `invest.db.bak-isactive-20260817`）后重跑：
   394 + 165 条，0 乱码，中文名称、别名、is_active 全部验证通过。
4. 别名表 `BUILTIN_ALIASES` 校准：key 必须与 AMAC 实际权威全称一致；
   基金管理人（house 表）无 `display_name` 列，不在此登记别名。

## 编码纪律（强制）

- **抓取外部数据时禁止猜测编码**：先看响应头 charset / `apparent_encoding`，依赖标准解码。
- **入库前必须校验**：名称/文本类字段含 U+FFFD 替换符即判定解码失败，拒绝写入。
- **写库后立即抽查验证**：抽样真实中文（如「中国建设银行」）确认 UTF-8 正确，再汇报完成。
- 全仓库只有一个数据库 `backend/invest.db`，排查数据问题不得臆测多库。

## 关联

- 代码：`backend/app/services/sync/jobs/amac_institution_job.py`
  （`_fetch_paged` 编码注释、`_validate_data` 乱码守卫、`BUILTIN_ALIASES` 校准注释均已在代码内留存）
- 数据表：`sales_institutions`（销售机构 394）、`fund_management_companies`（基金管理人 165）
