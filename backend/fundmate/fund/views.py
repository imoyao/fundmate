# -*- coding: utf-8 -*-
"""User views."""
import datetime
from typing import Dict, Optional

from apiflask import APIBlueprint, HTTPError, abort, pagination_builder
from apiflask.views import MethodView
from flask import current_app
from flask_praetorian import auth_required, current_user

import pandas as pd
from sqlalchemy import create_engine

from backend.fundmate import settings, utils
from backend.fundmate.database import db, get_table_name
from backend.fundmate.errors import HTTPClientError, HTTPServerError, ServerError, UserInputError
from backend.fundmate.fund.base import FundMiddleWare
from backend.fundmate.fund.models import (
    Fund,
    FundCompany,
    FundPortfolio,
    FundPortfolioAdjustHistory,
    FundPortfolioHoldDetail,
    FundSaleOrg,
    Manager,
)
from backend.fundmate.fund.schemas import (
    FundCompanyPaginationOutSchema,
    FundInSchema,
    FundMgrPaginationOutSchema,
    FundOutSchema,
    FundPaginationOutSchema,
    FundPortfolioDetailOutSchema,
    FundPortfolioInSchema,
    FundPortfolioPatchInSchema,
    FundPortfoliosAdjustOutSchema,
    FundPortfoliosOutSchema,
    FundPortfoliosPaginationSchema,
    FundRatioInSchema,
    FundRatioOutSchema,
    FundSaleOutSchema,
    FundSampleSchema,
    FundSearchKeySchema,
    PortfolioQueryOutSchema,
    PortfolioQuerySchema,
)
from backend.fundmate.libs.pysnowflake import snowflake
from backend.fundmate.schema_ext import CustomPaginationSchema
from backend.fundmate.types import PdDataFrame


bp = APIBlueprint('fund', __name__, url_prefix='/funds')


@bp.get('/')
@bp.input(CustomPaginationSchema, 'query')
@bp.output(FundPaginationOutSchema)
def funds(query: dict):
    """
    获取基金列表信息
    :param query:
    :return:
    """
    page = query.get('page')
    per_page = query.get('per_page')
    pagination = Fund.query.paginate(page=page, per_page=per_page)
    _items = pagination.items
    ret = {'funds': _items, 'pagination': pagination_builder(pagination)}
    return ret


@bp.get('/search/')
@bp.input(FundSearchKeySchema, 'query')
@bp.output(FundSampleSchema(many=True))
def search_fund(search_key):
    """
    通过基金编码，基金名称，基金简拼搜索基金信息
    """
    q = search_key.get('q')
    # 用法参考：https://github.com/greyli/apiflask/blob/fde330b41847727fb1ddeb3963c466f1118dc9db/examples/orm/app.py#L58
    _funds = Fund.search_key(q)
    if _funds:
        return _funds
    raise HTTPError(404, 'Please check your input keywords.')


@bp.route('/companies/')
class FundCompanyView(MethodView):

    @bp.input(CustomPaginationSchema, 'query')
    @bp.output(FundCompanyPaginationOutSchema)
    def get(self, query: dict):
        """
        获取基金公司信息
        """
        page = query.get('page')
        per_page = query.get('per_page')
        pagination = FundCompany.query.paginate(page=page, per_page=per_page)
        _items = pagination.items
        ret = {'companies': _items, 'pagination': pagination_builder(pagination)}
        return ret


@bp.route('/managers/')
class FundMgrView(MethodView):
    """
    获取基金经理信息
    """

    @bp.input(CustomPaginationSchema, 'query')
    @bp.output(FundMgrPaginationOutSchema)
    def get(self, query: dict = None):
        page = query.get('page')
        per_page = query.get('per_page')
        pagination = Manager.query.paginate(page=page, per_page=per_page)
        _items = pagination.items
        ret = {'managers': _items, 'pagination': pagination_builder(pagination)}
        return ret


@bp.route('/ratios')
class FundRatioView(MethodView):
    """
    获取基金费率信息
    """

    @bp.input(FundRatioInSchema, 'query')
    @bp.output(FundRatioOutSchema)
    def get(self, data: dict):
        fund_code = data.get('fund_code')
        fmw = FundMiddleWare()
        purchase_info = fmw.raw_purchase_info(fund_code)
        redeem_info = fmw.raw_redeem_info(fund_code)
        info = {
            'fund_code': fund_code,
            'purchase_info': purchase_info,
            'redeem_info': redeem_info,
        }
        return info


@bp.route('/sale_channels/')
class FundSalesView(MethodView):
    """
    基金销售渠道
    """

    @bp.output(FundSaleOutSchema)
    def get(self):
        """
        获取基金的销售渠道
        分为热门渠道和所有渠道
        :return:
        """
        # TODO：根据账本信息获取曾购买渠道
        # 一些常用的销售渠道，在前面列出来
        hot_market_place = FundSaleOrg.query.filter(FundSaleOrg.known_name.isnot(None)).all()
        all_market_place = FundSaleOrg.query.all()
        hot_places = {'label': '热门渠道', 'options': hot_market_place}
        all_places = {'label': '所有渠道', 'options': all_market_place}
        all_options = [hot_places, all_places]
        market_place = {'options': all_options}
        return market_place


@bp.route('/<string:fund_code>')
class FundDetail(MethodView):
    """
    基金详情
    """

    @bp.output(FundOutSchema)
    def get(self, fund_code: str):
        """获取指定基金信息"""
        fund_obj = Fund.filter_by_code(fund_code)
        return fund_obj

    @bp.input(FundInSchema(partial=True))
    @bp.output(FundOutSchema)
    def patch(self, fund_code, data):
        """更新指定基金信息"""
        _user_obj = Fund.filter_by_code(fund_code)
        if _user_obj:
            abort(404)
        fund_obj = Fund.save(data)
        return fund_obj


@bp.route('/<string:fund_code>/followers')
class FundFavor(MethodView):
    """
    某支基金的关注者
    """

    @bp.output(FundOutSchema)
    def get(self, fund_code: str):
        """获取指定基金信息"""
        pass


def check_sum_compositions(compositions: PdDataFrame) -> bool:
    """
    检查组合合计为1
    :param compositions:
    :return:
    """
    comp_df = pd.DataFrame(compositions)
    comp_df['portion'] = comp_df.portion.apply(lambda x: x / 100)
    total = comp_df['portion'].sum()
    return total == 1.0


@bp.route('/portfolios')
class FundCombination(MethodView):
    """
    基金组合
    """

    @bp.input(FundPortfoliosPaginationSchema, 'query')
    @bp.output(FundPortfoliosOutSchema)
    def get(self, query):
        """获取组合列表"""
        risk_type = query.get('risk_type')
        page = query.get('page')
        per_page = query.get('per_page')
        if risk_type:
            pagination = FundPortfolio.query.filter_by(risk_type=risk_type).paginate(page=page, per_page=per_page)
        else:
            pagination = FundPortfolio.query.paginate(page=page, per_page=per_page)

        portfolios = pagination.items
        return {'portfolios': portfolios, 'pagination': pagination_builder(pagination)}

    @auth_required
    @bp.input(FundPortfolioInSchema)
    @bp.output(FundPortfolioDetailOutSchema, 201)
    def post(self, data):
        """
        平台用户创建组合
        :param data:
        :return:
        """
        compositions = data.pop('compositions')
        if compositions:
            '''
            同花顺账本：必须大于0，对于没有分配的，后台用现金（000000）填充
            好买： 必须选择分配完所有比例才可以提交
            韭圈儿：没有分配的用现金填充
            '''
            comp_df = pd.DataFrame(compositions)
            is_sum_ok = check_sum_compositions(comp_df)

            if not is_sum_ok:
                error = UserInputError.NOT_HUNDRED_PERCENT_SUM_PORTION_ERR
                extra_data = {'error_code': error.code, 'docs': ''}
                raise HTTPServerError(message=error.msg, extra_data=extra_data)

            user = current_user()
            if not user:
                error = ServerError.CURRENT_USER_INFO_ERR
                extra_data = {'error_code': error.code, 'docs': ''}
                raise HTTPServerError(message=error.msg, extra_data=extra_data)
            portfolio_code = FundPortfolio.gen_portfolio_code()
            data['mgr_code'] = user.id
            data['portfolio_code'] = portfolio_code
            update_time = datetime.datetime.now()
            last_adjust_date = utils.today()
            data['update_time'] = update_time
            data['found_date'] = last_adjust_date
            data['is_visible'] = int(data.get('is_visible'))
            data['last_adjust_date'] = last_adjust_date
            data['synchronize_session'] = False
            # 写入数据库
            fpo = FundPortfolio.create(**data)
            # 将组合描述作为建仓时的观点
            desc = data.get('desc')
            fund_portfolio_adjust(portfolio_code, desc, comp_df)
            # TODO:需要计算组合信息 如：年化收益，夏普比率，波动率，回撤率之后返回
            return fpo


def fund_portfolio_adjust(portfolio_code: str, adjust_comment: str, comp_df: pd.DataFrame):
    """
    组合调仓
    :param portfolio_code:
    :param adjust_comment:
    :param comp_df:
    :return:
    """
    sf = snowflake.generator()
    adjust_id = next(sf)
    adjust_info = {
        'portfolio_code': portfolio_code,
        'adjust_id': adjust_id,
        'update_date': datetime.datetime.now(),
        'desc': adjust_comment,
        'synchronize_session': False
    }
    FundPortfolioAdjustHistory.create(**adjust_info)

    comp_df['adjust_id'] = adjust_id
    tb_name = get_table_name(FundPortfolioHoldDetail)
    config = current_app.config
    sqlalchemy_database_uri = config.get('SQLALCHEMY_DATABASE_URI')
    engine = create_engine(sqlalchemy_database_uri)
    comp_df.to_sql(name=tb_name, con=engine, if_exists='append', index=False)
    # 最后提交
    db.session.commit()
    return 0


@bp.route('/portfolios/<string:portfolio_code>')
class CombinationDetail(MethodView):
    """
    单个基金组合详情
    """

    @auth_required
    @bp.output(FundPortfolioDetailOutSchema)
    @bp.doc(summary='单个组合详情概览', description='该接口用于获取特定组合的详情信息')
    def get(self, portfolio_code: str):
        """获取指定基金组合信息"""
        fpo = FundPortfolio.query.filter_by(portfolio_code=portfolio_code).one_or_none()
        if fpo is not None:
            return fpo
        abort(404)

    @auth_required
    @bp.output({}, 204)
    @bp.doc(summary='删除指定基金组合', description='该接口用于删除特定组合，需要给出组合编码')
    def delete(self, portfolio_code: str):
        """
        删除回测组合

        # FIXME:
        1. 必须是经过认证的用户
        2. 是否为操作者本人？如果是才可以删除，否则报错403
        3. 如果不是，操作者是否为系统管理员？如果是，且为自有组合，允许删除，否则报错不允许删除外部组合

        """
        # 注意：删除组合时，必须删除历史持仓信息和调仓信息
        fpo_adjust_history = FundPortfolioAdjustHistory.query.filter_by(portfolio_code=portfolio_code)
        '''synchronize_session see also:[delete - sqlalchemy - Python documentation - Kite](
        https://www.kite.com/python/docs/sqlalchemy.orm.Query.delete)

        chooses the strategy for the removal of matched objects from the session. Valid values are:

        False - don’t synchronize the session. This option is the most efficient and is reliable once the session is
        expired, which typically occurs after a commit(), or explicitly using expire_all(). Before the expiration,
        objects may still remain in the session which were in fact deleted which can lead to confusing results if
        they are accessed via get() or already loaded collections.

        'fetch' - performs a select query before the delete to find objects that are matched by the delete query and
        need to be removed from the session. Matched objects are removed from the session.

        'evaluate' - Evaluate the query’s criteria in Python straight on the objects in the session. If evaluation of
        the criteria isn’t implemented, an error is raised.

        The expression evaluator currently doesn't account for differing string collations between the database and
        Python. '''
        fpo_adjust_history.delete(synchronize_session=False)  # 显式commit之后真正删除
        for fah_item in fpo_adjust_history:
            adjust_id = fah_item.adjust_id
            fp_hold_details = FundPortfolioHoldDetail.query.filter_by(adjust_id=adjust_id)
            fp_hold_details.delete(synchronize_session=False)
        fpo = FundPortfolio.query.filter_by(portfolio_code=portfolio_code)
        fpo.delete(synchronize_session=False)
        db.session.commit()
        return ''

    @auth_required
    @bp.input(FundPortfolioPatchInSchema(partial=True))
    @bp.output(FundPortfolioDetailOutSchema)
    @bp.doc(summary='部分更新指定基金组合',
            description='该接口用于更新特定组合（如：名称、风险等级、描述、可见性、投资理念），需要给出组合编码')
    def patch(self, portfolio_code: str, data: Dict):
        """
        更新组合可以更新的字段包括：
        名称、风险、描述、可见性、rich_desc
        :param portfolio_code:
        :param data:
        :return:
        """
        fpo = FundPortfolio.query.filter_by(portfolio_code=portfolio_code).one_or_none()
        if fpo is None:
            abort(404)

        if not data:
            error = UserInputError.PATCH_WITH_EMPTY_DATA_ERR
            extra_data = {'error_code': error.code, 'docs': ''}
            raise HTTPClientError(message=error.msg, extra_data=extra_data)

        update_time = datetime.datetime.now()
        last_adjust_date = utils.today()
        # 如果用户提交，才更新该字段
        is_visible = data.get('is_visible')
        if is_visible is not None:
            query_is_visible = fpo.is_visible
            if query_is_visible != query_is_visible:
                data['is_visible'] = int(is_visible)

        data['update_time'] = update_time
        data['last_adjust_date'] = last_adjust_date
        compositions = data.get('compositions')
        if compositions:
            # pop出来，传递到更新数据里会报错
            data.pop('compositions')
            # 组合调仓
            comp_df = pd.DataFrame(compositions)
            is_sum_ok = check_sum_compositions(comp_df)
            if not is_sum_ok:
                error = UserInputError.NOT_HUNDRED_PERCENT_SUM_PORTION_ERR
                extra_data = {'error_code': error.code, 'docs': ''}
                raise HTTPServerError(message=error.msg, extra_data=extra_data)

            data['synchronize_session'] = False
            # 调仓说明
            adjust_comment = data.get('adjust_comment')
            if adjust_comment:
                data.pop('adjust_comment')

            fpo = fpo.update(**data)
            fund_portfolio_adjust(portfolio_code, adjust_comment, comp_df)
        else:
            # 只更新组合基本信息
            fpo = fpo.update(**data)
        return fpo


@bp.get('/portfolios/options')
@bp.input(PortfolioQuerySchema, 'query')
@bp.output(PortfolioQueryOutSchema)
def get_portfolios_select_options(query: Optional[Dict]):
    """
    组合下拉框的显示

    **注意** 由于组合管理员的特殊设计，所以此处查询管理员类型时需要特殊处理，对于平台和未知组合，一律定义类型为“个人”

    :param query:
    :return:
    """
    if not query:
        plat_options = settings.PlatTypeEnum.names()
        risk_options = settings.RiskTypeEnum.names()
        mgr_options = settings.ZHMgrTypeEnum.names()
        return {
            'plat_options': plat_options,
            'risk_options': risk_options,
            'mgr_options': mgr_options,
        }
    else:
        mgr_option = query.pop('mgr_type', None)

        fpos = FundPortfolio.query.filter_by(**query).distinct(FundPortfolio.platform, FundPortfolio.risk_type,
                                                               FundPortfolio.mgr_code).all()
        if fpos:
            own_or_undefined_lists = [settings.PlatTypeEnum.own.dk_name, settings.PlatTypeEnum.un.dk_name]
            if mgr_option:
                comb_list = list()
                for comb in fpos:
                    # 第三方平台
                    comb_plat_type = comb.platform.dk_name
                    if comb_plat_type not in own_or_undefined_lists:
                        comb_mgr_type = comb.manager.mgr_type.dk_name
                        if comb_mgr_type == mgr_option:
                            comb_list.append(comb)
                    else:  # 自有或未知
                        fpo_mgr_type = settings.ZHMgrTypeEnum.personal.dk_name
                        if fpo_mgr_type == mgr_option:
                            comb_list.append(comb)

                fpos = comb_list.copy()

            plat_options = set()
            risk_options = set()
            mgr_options = set()
            for comb_item in fpos:
                comb_plat_type = comb_item.platform.dk_name
                plat_options.add(comb_plat_type)
                risk_options.add(comb_item.risk_type.dk_name)

                if comb_plat_type not in own_or_undefined_lists:
                    mgr_type = comb_item.manager.mgr_type.dk_name
                else:
                    mgr_type = settings.ZHMgrTypeEnum.personal.dk_name

                mgr_options.add(mgr_type)

            results = {
                'plat_options': plat_options,
                'risk_options': risk_options,
                'mgr_options': mgr_options,
            }
            return results
        else:
            abort(404)


@bp.route('/portfolios/<string:portfolio_code>/adjustments')
class PortfoliosAdjust(MethodView):
    """
    单一组合调仓信息
    """

    @bp.input(CustomPaginationSchema, 'query')
    @bp.output(FundPortfoliosAdjustOutSchema)
    def get(self, portfolio_code: str, query: dict):
        """获取组合调仓历史"""
        page = query.get('page')
        per_page = query.get('per_page')
        pagination = FundPortfolioAdjustHistory.query.filter_by(portfolio_code=portfolio_code).order_by(
            FundPortfolioAdjustHistory.update_date.desc()).paginate(page=page, per_page=per_page)

        portfolios = pagination.items

        return {'adjusts': portfolios, 'pagination': pagination_builder(pagination, portfolio_code=portfolio_code)}
