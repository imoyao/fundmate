# -*- coding: utf-8 -*-
"""导入协调器·持仓快照与 E 账户对账 Mixin（#1370 拆分）。

职责：持仓文件解析预览 → commit_holdings → E 账户影子记录对账/归因/覆盖。
设计依据 e-account-reconciliation-design-2026-08-16（§12 v1.1.1）。
与解析（orchestrator_parse.ParsingMixin）、交易落库（orchestrator_commit.CommitMixin）
经 ImportOrchestrator 组合复用；方法体自原 orchestrator.py 逐字搬运，逻辑零改动。
"""

import json
from datetime import date, datetime
from typing import List, Optional, Tuple

from loguru import logger
from sqlalchemy import func

from app.core.constants import PositionSource
from app.core.exceptions import ErrorCode, SBException
from app.core.money import Money
from app.domains.ledgers.constants import map_org_type_to_channel_category
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import (
    Position,
    PositionImportMeta,
    SalesInstitution,
    resolve_sales_institution_id,
)
from app.services.importer.records import (
    SBImportError,
    StandardHoldingRecord,
    compute_position_hash,
)
from app.services.importer.registry import get_holding_parser
from app.services.position_service import PositionService


class HoldingsMixin:
    """持仓快照导入与 E 账户对账归因。"""

    # ── 持仓分支（#1012，与交易分支完全并行，落 positions 不建流水）──

    E_ACCOUNT_LEDGER_NAME = '基金E账户'

    def get_or_create_e_account_ledger(self) -> Ledger:
        """获取或创建「基金E账户」聚合账户（ledger_type='e_account'）。

        语义：E账户是「全平台公募基金持仓的汇总视图」，不是资金实体，
        因此不映射到用户某个真实基金账户，而是独立聚合账户承载快照。
        """
        ledger = (
            self.db.query(Ledger)
            .filter_by(ledger_type='e_account', family_id=self.family_id)
            .order_by(Ledger.id.asc())
            .first()
        )
        if ledger:
            return ledger
        ledger = Ledger(
            name=self.E_ACCOUNT_LEDGER_NAME,
            ledger_type='e_account',
            default_allocation='longterm',
            family_id=self.family_id,
            is_aggregation=True,
        )
        self.db.add(ledger)
        self.db.flush()
        logger.info(f'已自动创建基金E账户聚合账户: id={ledger.id}')
        return ledger

    def parse_and_preview_holdings(
        self, file_bytes: bytes, source: str, frontend_account: str = '', ledger_id: Optional[int] = None
    ) -> dict:
        """解析持仓文件并返回预览数据（含去重信息）。

        ledger_id 未指定时自动创建/复用「基金E账户」聚合账户并回填。
        与 parse_and_preview（交易）完全并行，互不干扰。
        """
        parser = get_holding_parser(source)
        if parser is None:
            raise SBException(ErrorCode.UNSUPPORTED_FILE_FORMAT.code, f'不支持的持仓导入来源: {source}')

        records, errors = parser.parse(file_bytes)
        if errors and not records:
            raise SBException(ErrorCode.FILE_PARSE_ERROR.code, errors[0].message)

        valid, validation_errors = parser.validate(records)
        all_errors = errors + validation_errors

        # 未指定目标账户 → 自动创建/复用聚合账户（E账户是汇总视图，不映射真实账户）
        if not ledger_id:
            ledger = self.get_or_create_e_account_ledger()
            ledger_id = ledger.id
            if not frontend_account:
                frontend_account = ledger.name

        return self._holding_rows_from_records(valid, parser, frontend_account, ledger_id, all_errors)

    def _holding_rows_from_records(
        self,
        records: List[StandardHoldingRecord],
        parser,
        frontend_account: str,
        ledger_id: Optional[int],
        errors: List[SBImportError],
    ) -> dict:
        """持仓记录 → 前端预览行（回填账户 + 生成 import_hash + 去重标记）。"""
        for rec in records:
            rec.ledger_id = ledger_id
            if not rec.account_name and frontend_account:
                rec.account_name = frontend_account
            if not rec.import_hash:
                rec.import_hash = parser.compute_holding_hash(rec)

        rows = []
        for rec in records:
            rows.append(
                {
                    'symbol': rec.symbol,
                    'name': rec.name,
                    'type': rec.asset_type,
                    'quantity': float(rec.shares) if rec.shares else 0,
                    'price': float(rec.nav) if rec.nav else 0,
                    'amount': float(rec.market_value) if rec.market_value else 0,
                    'snapshot_date': rec.snapshot_date.isoformat() if rec.snapshot_date else '',
                    'currency': rec.currency,
                    'account_name': rec.account_name,
                    'ledger_id': rec.ledger_id,
                    'source_broker': rec.source_broker,
                    'fund_manager': rec.fund_manager,
                    'share_class': rec.share_class,
                    'fund_account': rec.fund_account,
                    'trade_account': rec.trade_account,
                    'dividend_preference': rec.dividend_preference,
                    'error': rec.error or None,
                    'import_hash': rec.import_hash,
                    'is_duplicate': False,
                    'source': rec.source,
                }
            )

        # 去重检查：与已有 positions.import_hash 比对（幂等拦截，撞 key 标重不写）
        hashes = [r['import_hash'] for r in rows if r.get('import_hash')]
        existing_hashes = set()
        if hashes:
            existing_hashes = set(
                h[0]
                for h in self.db.query(Position.import_hash)
                .filter(Position.import_hash.in_(hashes), Position.family_id == self.family_id)
                .all()
            )
        for row in rows:
            if row.get('import_hash') and row['import_hash'] in existing_hashes:
                row['is_duplicate'] = True

        error_count = sum(1 for r in rows if r.get('error')) + len(errors)
        duplicate_count = sum(1 for r in rows if r.get('is_duplicate'))

        return {
            'rows': rows,
            'total': len(rows),
            'error_count': error_count,
            'duplicate_count': duplicate_count,
            'ledger_id': ledger_id,
            'ledger_name': frontend_account,
        }

    def preview_holding_records(
        self,
        records: List[StandardHoldingRecord],
        frontend_account: str = '',
        ledger_id: Optional[int] = None,
        source: str = PositionSource.AI_HOLDING.value,
    ) -> dict:
        """AI 持仓识别结果（已 enrich 的 StandardHoldingRecord 列表）→ 预览行。

        与 parse_and_preview_holdings（文件通道）完全并行，仅来源是 AI 而非文件解析器。
        ledger_id 未指定时复用「基金E账户」聚合账户（与文件通道口径一致）。
        直接复用 _holding_rows_from_records 的行构建 + 去重逻辑，避免重复实现。
        """
        if not ledger_id:
            ledger = self.get_or_create_e_account_ledger()
            ledger_id = ledger.id
            if not frontend_account:
                frontend_account = ledger.name

        # 回填 ledger_id / account_name，并为缺省 import_hash 的记录补算（无需文件解析器）
        for rec in records:
            rec.ledger_id = ledger_id
            if not rec.account_name and frontend_account:
                rec.account_name = frontend_account
            if not rec.import_hash:
                rec.import_hash = compute_position_hash(source, ledger_id, rec.symbol, rec.snapshot_date)

        return self._holding_rows_from_records(
            records, parser=None, frontend_account=frontend_account, ledger_id=ledger_id, errors=[]
        )

    def commit_holdings(self, raw_rows: list) -> dict:
        """接收前端提交的持仓行，过滤后经 upsert_from_holding 落库（不建流水）。

        与 commit_from_preview（交易）完全并行。返回统计字典。
        接口契约冻结（请求/响应格式不变）：内部仅增加 E账户防复活过滤——
        source='e_account_holding' 的记录若已归因/已忽略（is_attributed/is_ignored），
        直接跳过，避免旧调用方经快照全量 SET 复活已归因持仓（§1.2 原则 4）。
        其他 source 的记录 meta 三元组为 NULL，查询天然不命中，不受影响。
        """
        valid_rows = [r for r in raw_rows if not r.get('is_duplicate') and not r.get('error')]
        filter_skipped = len(raw_rows) - len(valid_rows)

        if not valid_rows:
            return {'imported': 0, 'skipped': len(raw_rows), 'errors': []}

        imported = 0
        commit_errors = []
        for row in valid_rows:
            try:
                # 防复活（§12.3）：E账户记录已归因/已忽略 → 跳过，不重建冲突
                if row.get('source') == 'e_account_holding':
                    meta = self._find_shadow_meta(row.get('symbol'), row.get('source_broker'), row.get('fund_manager'))
                    if meta and (meta.is_attributed or meta.is_ignored):
                        filter_skipped += 1
                        continue
                data = self._build_holding_data(row)
                PositionService.upsert_from_holding(self.db, data)
                imported += 1
            except Exception as e:
                logger.exception(f'持仓落库单条失败: symbol={row.get("symbol")}')
                commit_errors.append({'symbol': row.get('symbol'), 'name': row.get('name'), 'error': str(e)})

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f'持仓入库提交失败: {e}')
            raise

        logger.info(f'持仓入库完成: 导入={imported}, 跳过={filter_skipped}, 错误={len(commit_errors)}')
        return {'imported': imported, 'skipped': filter_skipped, 'errors': commit_errors}

    def _build_holding_data(self, row: dict) -> dict:
        """前端预览行 → upsert_from_holding 数据字典（含溯源 meta）。"""
        snapshot_date = None
        snap_str = row.get('snapshot_date', '')
        if snap_str:
            try:
                snapshot_date = datetime.strptime(snap_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                snapshot_date = date.today()

        price = float(row.get('price', 0) or 0)
        return {
            'symbol': row['symbol'],
            'name': row.get('name', ''),
            'asset_type': row.get('type', 'fund'),
            'ledger_id': row.get('ledger_id'),
            'account_name': row.get('account_name', ''),
            'quantity': float(row.get('quantity', 0) or 0),
            # 成本均价：E账户样本无成本字段，用快照日净值近似（用户已确认）
            'avg_price': price,
            'current_price': price,
            'snapshot_date': snapshot_date,
            'currency': row.get('currency', 'CNY'),
            'source': row.get('source', 'e_account_holding'),
            'source_broker': row.get('source_broker'),
            'source_import_id': row.get('source_import_id'),
            'family_id': self.family_id,
            'meta': {
                'fund_manager': row.get('fund_manager'),
                'share_class': row.get('share_class'),
                'fund_account': row.get('fund_account'),
                'trade_account': row.get('trade_account'),
                'dividend_preference': row.get('dividend_preference'),
                'market_value': row.get('amount'),
            },
        }

    # ── E账户对账与归因（设计文档 e-account-reconciliation-design-2026-08-16，§12 v1.1.1 修正）──

    @staticmethod
    def _parse_snapshot_date(snap_str) -> date:
        """解析快照日期；缺失/非法降级为落库当日（与 _build_holding_data 口径一致）。

        E3 修复：解析器可能直接产出 datetime/date 对象（非字符串），
        先判类型再 strptime，避免对 date 对象调用 strptime 抛 TypeError。
        """
        if not snap_str:
            return date.today()
        if isinstance(snap_str, datetime):
            return snap_str.date()
        if isinstance(snap_str, date):
            return snap_str
        try:
            return datetime.strptime(snap_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return date.today()

    def _find_shadow_meta(self, symbol, source_broker, fund_manager) -> Optional[PositionImportMeta]:
        """按 (symbol, source_broker, fund_manager) 三元组查影子记录 meta（§12.2 专用匹配键）。

        影子记录 meta 的 source_broker/fund_manager 非空（渠道 meta 恒为 NULL），
        三元组查询天然只命中影子记录；再叠加 ownership_status='shadow' 双保险，
        防止 source_broker 为 NULL 的异常行误命中渠道 meta。
        """
        return (
            self.db.query(PositionImportMeta)
            .join(Position, Position.id == PositionImportMeta.position_id)
            .filter(
                PositionImportMeta.symbol == symbol,
                PositionImportMeta.source_broker == source_broker,
                PositionImportMeta.fund_manager == fund_manager,
                PositionImportMeta.family_id == self.family_id,
                Position.ownership_status == 'shadow',
            )
            .first()
        )

    def _upsert_shadow_holding(self, row: dict) -> Tuple[Position, PositionImportMeta]:
        """影子记录专用 upsert：按 (symbol, source_broker, fund_manager) 匹配（§12.2）。

        与通用 upsert_from_holding 的 (ledger_id, symbol) 匹配不同——多渠道同 symbol
        会合并，这里必须按三元组匹配，保证同一基金经不同销售机构各自成记录（§12.1 修复）。
        影子记录 ledger_id 恒为 NULL（不挂任何 Ledger，SQLite UNIQUE 对 NULL 宽松）。

        E5 修复：返回 (position, meta) 二元组，调用方不再二次查询 meta；
        E4 修复：价格缺失（净值/成本均为 0）不再抛错拒绝，照常落记录并把
        meta.import_error 置 True（P6 数据不缺失；avg_price 列不可空，用 0 占位）。
        """
        symbol = row['symbol']
        source_broker = row.get('source_broker')
        fund_manager = row.get('fund_manager')
        snapshot_date = self._parse_snapshot_date(row.get('snapshot_date', ''))

        qty = float(row.get('quantity', 0) or 0)
        price = float(row.get('price', 0) or 0)
        if qty <= 0:
            raise ValueError('数量必须大于 0')
        missing_price = price <= 0
        price_units = Money.yuan_to_price_units(price) if not missing_price else 0

        qty_units = Money.shares_to_min_unit(qty)
        src = row.get('source', 'e_account_holding')
        # 哈希含 source_broker 维度：多渠道同 symbol 同日期 hash 不同（§12.1 修复）
        import_hash = compute_position_hash(src, None, symbol, snapshot_date, source_broker)

        meta = self._find_shadow_meta(symbol, source_broker, fund_manager)
        if meta:
            position = self.db.query(Position).filter_by(id=meta.position_id, family_id=self.family_id).first()
            if position is None:
                raise ValueError('影子记录 meta 存在但 Position 缺失，数据异常')
            # 命中：更新份额/市值/快照日（SET 语义，保留溯源）
            position.quantity = qty_units
            position.avg_price = price_units
            position.current_price = price_units
            position.confirm_date = snapshot_date
            position.name = row.get('name') or position.name
            position.import_hash = import_hash
            meta.snapshot_date = snapshot_date
            meta.market_value = Money.yuan_to_cents(row['amount']) if row.get('amount') else None
            meta.source_import_id = row.get('source_import_id')
        else:
            position = Position(
                symbol=symbol,
                name=row.get('name') or symbol,
                market='CN_A',
                asset_type=row.get('type', 'fund'),
                ledger_id=None,  # §12.2：影子记录不挂任何 Ledger
                account_name=row.get('account_name', ''),
                quantity=qty_units,
                avg_price=price_units,
                current_price=price_units,
                currency=row.get('currency', 'CNY'),
                confirm_date=snapshot_date,
                allocation='longterm',
                import_hash=import_hash,
                source=src,
                source_broker=source_broker,
                ownership_status='shadow',
                family_id=self.family_id,
            )
            self.db.add(position)
            self.db.flush()
            meta = PositionImportMeta(
                position_id=position.id,
                symbol=symbol,
                ledger_id=None,
                snapshot_date=snapshot_date,
                source=src,
                source_import_id=row.get('source_import_id'),
                source_broker=source_broker,
                sales_institution_id=resolve_sales_institution_id(self.db, source_broker),
                fund_manager=fund_manager,
                share_class=row.get('share_class'),
                fund_account=row.get('fund_account'),
                trade_account=row.get('trade_account'),
                dividend_preference=row.get('dividend_preference'),
                market_value=Money.yuan_to_cents(row['amount']) if row.get('amount') else None,
                family_id=self.family_id,
            )
            self.db.add(meta)
        if missing_price:
            meta.import_error = True
        self.db.flush()
        return position, meta

    def _get_or_create_channel_ledger(self, source_broker: str, external_account_code: str = 'MAIN') -> Ledger:
        """按销售机构匹配渠道 Ledger（ledger_type='fund'）；找不到则自动创建（§3.3）。

        资金账户维度（#1100/#1101）：external_account_code 区分同一机构下的不同资金账户
        （普通/两融等），默认 'MAIN'。查/建键为 (family_id, sales_institution_id, external_account_code)，
        与权威设计文档 §2.5/§6 一致。

        匹配链路（2026-08-17 重构，AMAC 权威名录为唯一基准）：
        1. source_broker → SalesInstitution 匹配（org_name 等值 → display_name 等值）；
        2. 命中机构 → 查 Ledger.sales_institution_id == 机构.id：
           - 找到 → 返回该 Ledger（name 为用户创建时的名字，权威名仅存后台不展示）；
           - 未找到 → 自动创建 Ledger（name=可读展示名）+ 自动关联 sales_institution_id；
        3. 名录未命中 → 回退：按 source_broker 原文查/建 Ledger（不关联机构，记 warning）。

        注意：Ledger.name 永远是用户输入/可读展示名，权威 org_name 不进前台任何字段。
        """
        institution = (
            self.db.query(SalesInstitution)
            .filter(SalesInstitution.is_active.is_(True), SalesInstitution.org_name == source_broker)
            .first()
        )
        if institution is None:
            institution = (
                self.db.query(SalesInstitution)
                .filter(
                    SalesInstitution.is_active.is_(True),
                    SalesInstitution.display_name == source_broker,
                )
                .first()
            )

        # 名录命中：按机构关联找/建渠道 Ledger
        if institution is not None:
            # 1) 精确命中（同机构 + 同外部资金账户）
            ledger = (
                self.db.query(Ledger)
                .filter_by(
                    sales_institution_id=institution.id,
                    ledger_type='fund',
                    family_id=self.family_id,
                    external_account_code=external_account_code,
                )
                .first()
            )
            if ledger:
                return ledger
            # 2) 存量「主账户」升级：本机构仅有一个 external_account_code='MAIN' 的旧账本，
            #    视为同一物理账户，将其外部账号补正为该笔导入真实资金账号，避免重复建账（#1100）。
            if external_account_code != 'MAIN':
                legacy = (
                    self.db.query(Ledger)
                    .filter_by(
                        sales_institution_id=institution.id,
                        ledger_type='fund',
                        family_id=self.family_id,
                        external_account_code='MAIN',
                    )
                    .all()
                )
                if len(legacy) == 1:
                    legacy[0].external_account_code = external_account_code
                    self.db.flush()
                    return legacy[0]
            # 3) 确无匹配 → 新建（含真实外部资金账号）
            display_name = institution.display_name or institution.org_name
            # 渠道分类（#1101 重设计，铁律见设计文档 §2.3）：命中销售机构时，
            # channel_category 由 org_type 映射写入（权威），与 ledger_type(资产类) 正交。
            # 例：微众银行 org_type=商业银行 → channel_category=bank，ledger_type 仍为 fund。
            ledger = Ledger(
                name=display_name,
                ledger_type='fund',
                default_allocation='longterm',
                family_id=self.family_id,
                sales_institution_id=institution.id,
                external_account_code=external_account_code,
                channel_category=map_org_type_to_channel_category(institution.org_type),
            )
            self.db.add(ledger)
            self.db.flush()
            logger.info(
                f'对账自动创建渠道账户: name={display_name} (机构={institution.org_name}, '
                f'id={institution.id}, 外部账号={external_account_code})'
            )
            return ledger

        # 名录未命中：回退原文（历史行为，不关联机构）
        ledger = (
            self.db.query(Ledger)
            .filter_by(
                name=source_broker,
                ledger_type='fund',
                family_id=self.family_id,
                external_account_code=external_account_code,
            )
            .first()
        )
        if ledger:
            return ledger
        ledger = Ledger(
            name=source_broker,
            ledger_type='fund',
            default_allocation='longterm',
            family_id=self.family_id,
            external_account_code=external_account_code,
        )
        self.db.add(ledger)
        self.db.flush()
        logger.warning(f'对账自动创建渠道账户（未命中 AMAC 名录）: name={source_broker}')
        return ledger

    def _auto_attribute(
        self, shadow_pos: Position, shadow_meta: PositionImportMeta, ledger: Ledger, row: dict
    ) -> Position:
        """自动归因：渠道 Ledger 下无该 symbol 持仓 → 用 E账户快照数据新建 active Position。

        渠道 meta 的 source_broker/fund_manager 必须为 NULL（§3.2 防唯一索引冲突）；
        影子记录标记 is_attributed=True + attributed_to_ledger_id（防复活 + 追溯）。
        """
        data = {
            'symbol': shadow_pos.symbol,
            'name': shadow_pos.name,
            'asset_type': shadow_pos.asset_type or 'fund',
            'ledger_id': ledger.id,
            'account_name': ledger.name,
            'quantity': Money.min_unit_to_shares(shadow_pos.quantity),
            'avg_price': Money.price_units_to_yuan(shadow_pos.avg_price),
            'current_price': Money.price_units_to_yuan(shadow_pos.current_price),
            'snapshot_date': shadow_pos.confirm_date,
            'currency': shadow_pos.currency or 'CNY',
            'source': shadow_pos.source,
            'source_broker': None,  # 渠道 meta 必须为 NULL
            'source_import_id': shadow_meta.source_import_id,
            'family_id': self.family_id,
            'meta': {
                'fund_manager': None,
                'share_class': shadow_meta.share_class,
                'fund_account': shadow_meta.fund_account,
                'trade_account': shadow_meta.trade_account,
                'dividend_preference': shadow_meta.dividend_preference,
                'market_value': Money.cents_to_yuan(shadow_meta.market_value) if shadow_meta.market_value else None,
            },
        }
        channel_pos = PositionService.upsert_from_holding(self.db, data, ownership_status='active')
        shadow_meta.is_attributed = True
        shadow_meta.attributed_at = datetime.now()
        shadow_meta.attributed_to_ledger_id = ledger.id
        self.db.flush()
        return channel_pos

    def _build_conflict_item(self, shadow_pos: Position, shadow_meta: PositionImportMeta, ledger, channel_pos) -> dict:
        """构造冲突列表项（§5.2 conflict_list 格式）。"""
        item = {
            'record_id': shadow_pos.id,
            'symbol': shadow_pos.symbol,
            'name': shadow_pos.name,
            'source_broker': shadow_meta.source_broker,
            'fund_manager': shadow_meta.fund_manager,
            'target_ledger_id': ledger.id if ledger else None,
            'target_ledger_name': ledger.name if ledger else None,
            'eaccount_quantity': Money.min_unit_to_shares(shadow_pos.quantity),
            'eaccount_cost': Money.price_units_to_yuan(shadow_pos.avg_price) if shadow_pos.avg_price else None,
        }
        if channel_pos is not None:
            item['current_quantity'] = Money.min_unit_to_shares(channel_pos.quantity)
            item['current_cost'] = Money.price_units_to_yuan(channel_pos.avg_price) if channel_pos.avg_price else None
            item['diff_quantity'] = round(item['eaccount_quantity'] - item['current_quantity'], 4)
        else:
            item['current_quantity'] = 0
            item['current_cost'] = None
            item['diff_quantity'] = item['eaccount_quantity']
        return item

    def reconcile_holdings(self, rows: list) -> dict:
        """E账户对账并落库（§4.1 + §12 v1.1.1 修正）：逐条处理 parse 端点输出的 holding 行。

        流程：
        1. 防复活检查：按三元组查影子 meta，is_attributed/is_ignored → 跳过并计数；
        2. 影子记录专用 upsert（ledger_id=NULL, ownership_status='shadow'）；
        3. 渠道匹配：source_broker → SalesInstitution（is_active，org_name/display_name 等值）→
           按 sales_institution_id 查/建 Ledger(fund)（name=display_name or org_name，自动关联机构）；
           名录未命中回退按 name=source_broker 查/建（不关联机构，记 warning）；
        4. 三分支判定（§4.2 只看份额，min_unit 整数比较，0.001 份 = 10 min_unit）：
           - 渠道无该 symbol → 自动归因（渠道新建 active + 影子 is_attributed=True）；
           - 有且份额差 ≤10 min_unit → 已核对（渠道不动 + 影子 is_attributed=True）；
           - 有且份额差 >10 min_unit → 冲突（渠道不动 + 影子 is_attributed=False）；
        5. 返回摘要（§5.2）。
        """
        summary = {
            'auto_attributed': 0,
            'verified': 0,
            'conflicts': 0,
            'ignored_skipped': 0,
            'attributed_skipped': 0,
            'failed_rows': [],
            'conflict_list': [],
        }

        for idx, row in enumerate(rows):
            line = idx + 2  # 表头占第 1 行（与 parse 端点行号口径一致）
            symbol = row.get('symbol', '')
            source_broker = row.get('source_broker')
            fund_manager = row.get('fund_manager')
            try:
                if not symbol:
                    summary['failed_rows'].append({'line': line, 'symbol': symbol, 'reason': '基金代码为空'})
                    continue

                # E6 修复：单行处理包在 SAVEPOINT 内，失败回滚该行已 flush 的中间写入，
                # 避免半截数据残留到最终 commit、污染后续行（与 §7.1 cover 单条事务同口径）。
                with self.db.begin_nested():
                    # 1. 防复活检查
                    meta = self._find_shadow_meta(symbol, source_broker, fund_manager)
                    if meta:
                        if meta.is_attributed:
                            summary['attributed_skipped'] += 1
                            continue
                        if meta.is_ignored:
                            summary['ignored_skipped'] += 1
                            continue

                    # 2. 影子记录专用 upsert（先落影子，保证 E账户侧数据永不缺失，P6）
                    #    E5 修复：返回 (position, meta)，不再二次查询 meta
                    shadow_pos, shadow_meta = self._upsert_shadow_holding(row)
                    if shadow_meta.import_error:
                        # E4 修复：无净值/成本行照常落库（avg_price=0 + import_error 标记），
                        # 仅计数提示，不中断后续渠道匹配
                        summary['failed_rows'].append(
                            {'line': line, 'symbol': symbol, 'reason': '成本均价与当前净值均缺失，无法确定价格'}
                        )

                    # 3. 渠道匹配（无销售机构 → 无法匹配渠道，落影子记录待处理）
                    if not source_broker:
                        summary['conflicts'] += 1
                        summary['conflict_list'].append(self._build_conflict_item(shadow_pos, shadow_meta, None, None))
                        continue
                    ledger = self._get_or_create_channel_ledger(
                        source_broker,
                        external_account_code=shadow_meta.trade_account or shadow_meta.fund_account or 'MAIN',
                    )

                    # 4. 三分支判定（只看份额，min_unit 整数比较）
                    channel_pos = (
                        self.db.query(Position)
                        .filter_by(symbol=symbol, ledger_id=ledger.id, family_id=self.family_id)
                        .first()
                    )
                    if channel_pos is None:
                        # 自动归因：渠道新建 active Position（E账户快照数据）
                        self._auto_attribute(shadow_pos, shadow_meta, ledger, row)
                        summary['auto_attributed'] += 1
                    else:
                        diff = abs(channel_pos.quantity - shadow_pos.quantity)
                        if diff <= 10:  # 0.001 份 = 10 min_unit（§4.2）
                            shadow_meta.is_attributed = True
                            shadow_meta.attributed_at = datetime.now()
                            summary['verified'] += 1
                        else:
                            shadow_meta.is_attributed = False
                            summary['conflicts'] += 1
                            summary['conflict_list'].append(
                                self._build_conflict_item(shadow_pos, shadow_meta, ledger, channel_pos)
                            )
            except Exception as e:
                logger.exception(f'E账户对账单条失败: symbol={symbol}')
                # 行级意外异常不回传原始详情：str(e) 含 SQL/表结构，会泄露数据库细节给前端。
                # 原始异常已由 logger.exception 记入服务端日志，前端只展示友好文案。
                summary['failed_rows'].append({'line': line, 'symbol': symbol, 'reason': '该行处理失败，详见系统日志'})

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f'E账户对账提交失败: {e}')
            raise
        logger.info(
            f'E账户对账完成: 自动归因={summary["auto_attributed"]}, 已核对={summary["verified"]}, '
            f'冲突={summary["conflicts"]}, 忽略跳过={summary["ignored_skipped"]}, '
            f'归因跳过={summary["attributed_skipped"]}'
        )
        return summary

    def _execute_cover(self, meta: PositionImportMeta) -> Position:
        """归因覆盖（单条事务内执行，§4.3 + §12.3）：
        1. 定位影子记录与渠道 Ledger；
        2. 删除目标 Ledger 下该 symbol 旧 Position（连带 meta）；
        3. 新建 active Position（E账户快照数据）；
        4. 影子记录 is_attributed=True + attributed_at + attributed_to_ledger_id；
        5. 渠道新 meta 记 attributed_from_eaccount（source_broker/fund_manager 为 NULL）。
        """
        shadow_pos = self.db.query(Position).filter_by(id=meta.position_id, family_id=self.family_id).first()
        if shadow_pos is None:
            raise ValueError('影子记录对应的持仓不存在')

        # 目标渠道 Ledger：优先用影子记录已归因目标；否则按 source_broker 匹配
        ledger = None
        if meta.attributed_to_ledger_id:
            ledger = self.db.query(Ledger).filter_by(id=meta.attributed_to_ledger_id, family_id=self.family_id).first()
        if ledger is None and meta.source_broker:
            ledger = self._get_or_create_channel_ledger(
                meta.source_broker,
                external_account_code=meta.trade_account or meta.fund_account or 'MAIN',
            )
        if ledger is None:
            raise ValueError('目标账户不存在，请重新选择')

        # 删除目标 Ledger 下同 symbol 旧 Position（连带 meta）
        old_pos = (
            self.db.query(Position)
            .filter_by(symbol=shadow_pos.symbol, ledger_id=ledger.id, family_id=self.family_id)
            .first()
        )
        if old_pos:
            old_meta = self.db.query(PositionImportMeta).filter_by(position_id=old_pos.id).first()
            if old_meta:
                self.db.delete(old_meta)
            self.db.delete(old_pos)
            self.db.flush()

        # 新建 active Position（E账户快照数据）；哈希用渠道维度（不含 source_broker），
        # 与影子记录哈希区分，避免撞 uq_positions_import_hash
        snapshot_date = shadow_pos.confirm_date or date.today()
        channel_hash = compute_position_hash(shadow_pos.source, ledger.id, shadow_pos.symbol, snapshot_date)
        new_pos = Position(
            symbol=shadow_pos.symbol,
            name=shadow_pos.name,
            market=shadow_pos.market or 'CN_A',
            asset_type=shadow_pos.asset_type or 'fund',
            ledger_id=ledger.id,
            account_name=ledger.name,
            quantity=shadow_pos.quantity,
            avg_price=shadow_pos.avg_price,
            current_price=shadow_pos.current_price,
            currency=shadow_pos.currency or 'CNY',
            confirm_date=snapshot_date,
            allocation=shadow_pos.allocation or 'longterm',
            import_hash=channel_hash,
            source=shadow_pos.source,
            source_broker=None,
            ownership_status='active',
            family_id=self.family_id,
        )
        self.db.add(new_pos)
        self.db.flush()

        # 渠道新 meta：source_broker/fund_manager 必须为 NULL（§3.2 防唯一索引冲突）
        new_meta = PositionImportMeta(
            position_id=new_pos.id,
            symbol=new_pos.symbol,
            ledger_id=ledger.id,
            snapshot_date=snapshot_date,
            source=new_pos.source,
            source_broker=None,
            sales_institution_id=ledger.sales_institution_id,
            fund_manager=None,
            share_class=meta.share_class,
            fund_account=meta.fund_account,
            trade_account=meta.trade_account,
            dividend_preference=meta.dividend_preference,
            market_value=meta.market_value,
            raw_extra=json.dumps(
                {'attributed_from_eaccount': True, 'attributed_at': datetime.now().isoformat()},
                ensure_ascii=False,
            ),
            family_id=self.family_id,
        )
        self.db.add(new_meta)

        # 影子记录标记归因（防复活 + 追溯）
        meta.is_attributed = True
        meta.attributed_at = datetime.now()
        meta.attributed_to_ledger_id = ledger.id
        self.db.flush()
        return new_pos

    def _find_channel_position_id(self, meta: PositionImportMeta) -> Optional[int]:
        """幂等 cover 查询：已归因时返回目标 Ledger 下该 symbol 的 active Position id。"""
        if not meta.attributed_to_ledger_id:
            return None
        pos = (
            self.db.query(Position)
            .filter_by(
                symbol=meta.symbol,
                ledger_id=meta.attributed_to_ledger_id,
                family_id=self.family_id,
                ownership_status='active',
            )
            .first()
        )
        return pos.id if pos else None

    def attribute_holdings(self, decisions: list) -> dict:
        """处理对账冲突（§5.3）：cover 归因覆盖 / ignore 忽略，幂等。

        decisions: [{symbol, source_broker, fund_manager, action}]，action ∈ cover/ignore。
        - cover：单条事务——删除目标 Ledger 旧 Position（连带 meta）→ 新建 active Position
          （E账户快照数据）→ 影子记录 is_attributed=True + attributed_at + attributed_to_ledger_id；
        - ignore：影子记录 is_ignored=True；
        - 幂等：重复 cover/ignore 返回当前状态（HTTP 200），不报错、不重复执行（P4）。
        """
        results = []
        success = 0
        failed = 0

        for decision in decisions:
            symbol = decision.get('symbol', '')
            source_broker = decision.get('source_broker')
            fund_manager = decision.get('fund_manager')
            action = decision.get('action', '')
            try:
                meta = self._find_shadow_meta(symbol, source_broker, fund_manager)
                if meta is None:
                    raise ValueError('影子记录不存在，请重新对账')

                if action == 'ignore':
                    meta.is_ignored = True
                    # E1 修复：ignore 立即 commit，避免后续 cover 失败 rollback 把忽略标记一起回滚
                    try:
                        self.db.commit()
                    except Exception as e:
                        self.db.rollback()
                        logger.exception(f'忽略标记提交失败: symbol={symbol}')
                        failed += 1
                        results.append(
                            {
                                'symbol': symbol,
                                'source_broker': source_broker,
                                'fund_manager': fund_manager,
                                'action': 'ignore',
                                'status': 'failed',
                                'error': str(e),
                            }
                        )
                    else:
                        results.append(
                            {
                                'symbol': symbol,
                                'source_broker': source_broker,
                                'fund_manager': fund_manager,
                                'action': 'ignore',
                                'status': 'ignored',
                            }
                        )
                        success += 1
                elif action == 'cover':
                    # 幂等：已归因直接返回当前状态，不重复建（P4）
                    if meta.is_attributed:
                        results.append(
                            {
                                'symbol': symbol,
                                'source_broker': source_broker,
                                'fund_manager': fund_manager,
                                'action': 'cover',
                                'status': 'covered',
                                'new_position_id': self._find_channel_position_id(meta),
                            }
                        )
                        success += 1
                        continue
                    # 单条事务：失败回滚该条，不影响其他决策（§7.1）
                    try:
                        new_pos = self._execute_cover(meta)
                        self.db.commit()
                        results.append(
                            {
                                'symbol': symbol,
                                'source_broker': source_broker,
                                'fund_manager': fund_manager,
                                'action': 'cover',
                                'status': 'covered',
                                'new_position_id': new_pos.id,
                            }
                        )
                        success += 1
                    except Exception as e:
                        self.db.rollback()
                        logger.exception(f'归因覆盖失败: symbol={symbol}')
                        failed += 1
                        results.append(
                            {
                                'symbol': symbol,
                                'source_broker': source_broker,
                                'fund_manager': fund_manager,
                                'action': 'cover',
                                'status': 'failed',
                                'error': str(e),
                            }
                        )
                else:
                    raise ValueError(f'不支持的 action: {action}')
            except Exception as e:
                failed += 1
                results.append(
                    {
                        'symbol': symbol,
                        'source_broker': source_broker,
                        'fund_manager': fund_manager,
                        'action': action,
                        'status': 'failed',
                        'error': str(e),
                    }
                )

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f'E账户归因提交失败: {e}')
            raise

        return {'success': success, 'failed': failed, 'details': results}

    def get_reconciliation(self) -> dict:
        """对账中心（§5.4）：查询所有影子记录（ownership_status='shadow'），推导状态。

        status 推导（P1 锁定）：
        - is_attributed=True + attributed_to_ledger_id 非空 → attributed（用户/自动归因）
        - is_attributed=True + attributed_to_ledger_id 为空 → verified（自动核对一致）
        - is_ignored=True → ignored
        - 其余 → pending（未归因冲突）
        同时返回系统侧 active Position 按 symbol 汇总份额（min_unit 转份）。
        data_date = 影子记录 max(updated_at) 的日期（P2 数据新鲜度标注）。
        """
        shadow_positions = (
            self.db.query(Position)
            .filter(Position.family_id == self.family_id, Position.ownership_status == 'shadow')
            .order_by(Position.updated_at.desc())
            .all()
        )

        # 系统侧：active Position 按 symbol 汇总份额（min_unit 整数求和后转份）
        active_rows = (
            self.db.query(Position.symbol, func.sum(Position.quantity))
            .filter(Position.family_id == self.family_id, Position.ownership_status == 'active')
            .group_by(Position.symbol)
            .all()
        )
        system_quantity = {symbol: Money.min_unit_to_shares(qty) for symbol, qty in active_rows}

        # E账户侧：shadow 记录按 symbol 汇总份额（E2 修复——多渠道同 symbol 各自成记录，
        # 单条记录只代表自身渠道，diff 必须用 symbol 级汇总对比系统侧，否则多渠道路径恒为偏差）
        shadow_rows = (
            self.db.query(Position.symbol, func.sum(Position.quantity))
            .filter(Position.family_id == self.family_id, Position.ownership_status == 'shadow')
            .group_by(Position.symbol)
            .all()
        )
        eaccount_total = {symbol: Money.min_unit_to_shares(qty) for symbol, qty in shadow_rows}

        items = []
        data_date = None
        for pos in shadow_positions:
            meta = self.db.query(PositionImportMeta).filter_by(position_id=pos.id).first()
            is_attributed = bool(meta and meta.is_attributed)
            is_ignored = bool(meta and meta.is_ignored)
            attributed_to_ledger_id = meta.attributed_to_ledger_id if meta else None

            if is_attributed and attributed_to_ledger_id:
                status = 'attributed'
            elif is_attributed:
                status = 'verified'
            elif is_ignored:
                status = 'ignored'
            else:
                status = 'pending'

            attributed_to = None
            if attributed_to_ledger_id:
                ledger = self.db.query(Ledger).filter_by(id=attributed_to_ledger_id).first()
                attributed_to = ledger.name if ledger else None

            eaccount_qty = Money.min_unit_to_shares(pos.quantity)
            total_qty = eaccount_total.get(pos.symbol, eaccount_qty)
            system_qty = system_quantity.get(pos.symbol, 0.0)
            items.append(
                {
                    'record_id': pos.id,
                    'symbol': pos.symbol,
                    'name': pos.name,
                    'source_broker': meta.source_broker if meta else None,
                    'fund_manager': meta.fund_manager if meta else None,
                    'eaccount_quantity': eaccount_qty,
                    'eaccount_total': round(total_qty, 4),
                    'system_quantity': system_qty,
                    'diff': round(total_qty - system_qty, 4),
                    'status': status,
                    'attributed_to': attributed_to,
                    'is_ignored': is_ignored,
                }
            )
            if pos.updated_at and (data_date is None or pos.updated_at.date() > data_date):
                data_date = pos.updated_at.date()

        summary = {
            'pending_count': sum(1 for i in items if i['status'] == 'pending'),
            'attributed_count': sum(1 for i in items if i['status'] == 'attributed'),
            'ignored_count': sum(1 for i in items if i['status'] == 'ignored'),
            'verified_count': sum(1 for i in items if i['status'] == 'verified'),
        }

        return {
            'data_date': data_date.isoformat() if data_date else None,
            'items': items,
            'summary': summary,
        }
