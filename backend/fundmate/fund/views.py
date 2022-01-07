# -*- coding: utf-8 -*-
"""User views."""
import datetime

from apiflask import APIBlueprint, abort, doc, input, output, pagination_builder
from flask import current_app
from flask.views import MethodView

import pandas as pd
from sqlalchemy import create_engine

from backend.fundmate import utils
from backend.fundmate.database import db, get_table_name
from backend.fundmate.errors import NotHundredPercentSumPortion, PatchWithEmptyData
from backend.fundmate.fund.models import (
    Fund,
    FundCompany,
    FundMgr,
    FundPortfolio,
    FundPortfolioAdjustHistory,
    FundPortfolioHoldDetail,
    FundSaleOrg,
)
from backend.fundmate.fund.schemas import (
    FundCompanyOutSchema,
    FundInSchema,
    FundOutSchema,
    FundPaginationOutSchema,
    FundPortfolioDetailOutSchema,
    FundPortfolioInSchema,
    FundPortfolioPatchInSchema,
    FundPortfoliosOutSchema,
    FundPortfoliosPaginationSchema,
    FundSaleOutSchema,
)
from backend.fundmate.libs.pysnowflake import snowflake
from backend.fundmate.schema_ext import CustomPaginationSchema, EmptySchema
from backend.fundmate.view_ext import paginate_query

bp = APIBlueprint("fund", __name__, url_prefix="/funds")


@bp.get('/')
@input(CustomPaginationSchema, 'query')
# @input(EmptySchema, 'query')
@output(FundPaginationOutSchema)  # 注意此处不适用`many=True`
# @output(FundSampleSchema(many=True))
def funds(query):
    """
    获取基金信息
    :param query:
    :return:
    """
    if query:
        pagination = paginate_query(Fund, query)
        _items = pagination.items
        ret = {'funds': _items, 'pagination': pagination_builder(pagination)}
    else:
        # FIXME: not work
        ret = Fund.query.order_by(Fund.fund_code.desc()).all()
        print(ret)
    return ret


@bp.route('/companies/')
class FundCompanyView(MethodView):

    @input(CustomPaginationSchema, 'query')
    @input(EmptySchema)
    @output(FundCompanyOutSchema(many=True))
    def get(self, query: dict = None):
        """
        获取基金公司信息
        """
        if query:
            ret = paginate_query(FundCompany, query)
        else:
            ret = FundCompany.query.order_by(FundCompany.scale.desc()).all()
        return ret


@bp.route('/managers/')
class FundMgrView(MethodView):

    @input(CustomPaginationSchema, 'query')
    @input(EmptySchema)
    @output(FundOutSchema)
    def get(self, query: dict = None):
        if query:
            ret = paginate_query(FundMgr, query)
        else:
            ret = FundMgr.query.all()
        return ret


@bp.route('/sale_channels/')
class FundSalesView(MethodView):
    """
    基金销售机构
    """

    @output(FundSaleOutSchema)
    def get(self):
        """
        获取基金的销售渠道
        分为热门渠道和所有渠道

        TODO：根据账本信息获取曾购买渠道
        :return:
        """
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

    @output(FundOutSchema)
    def get(self, fund_code: str):
        """获取指定基金信息"""
        user_obj = Fund.filter_by_code(fund_code)
        return user_obj

    # def post(self):
    #     """
    #     新建基金
    #     """
    #     return {'message': 'Hello,User!'}

    @input(FundInSchema(partial=True))
    @output(FundOutSchema)
    def patch(self, fund_code, data):
        """更新指定基金信息"""
        _user_obj = Fund.filter_by_code(fund_code)
        if _user_obj:
            abort(404)
        user = Fund.save(data)
        return user


@bp.route('/<string:fund_code>/followers')
class FundFavor(MethodView):
    """
    某支基金的关注者
    """

    @output(FundOutSchema)
    def get(self, fund_code: str):
        """获取指定基金信息"""
        pass


@bp.route('/portfolios')
class FundCombination(MethodView):
    """
    基金组合
    """

    @input(FundPortfoliosPaginationSchema, 'query')
    @output(FundPortfoliosOutSchema)
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

    @input(FundPortfolioInSchema)
    @output(FundPortfolioDetailOutSchema, 201)
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
            comp_df['portion'] = comp_df.portion.apply(lambda x: x / 100)
            total = comp_df['portion'].sum()
            if total != 1.0:
                raise NotHundredPercentSumPortion

            portfolio_code = FundPortfolio.gen_portfolio_code()
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

    @output(FundPortfolioDetailOutSchema)
    @doc(summary='单个组合详情概览', description='该接口用于获取特定组合的详情信息')
    def get(self, portfolio_code: str):
        """获取指定基金组合信息"""
        fpo = FundPortfolio.query.filter_by(portfolio_code=portfolio_code).one_or_none()
        if fpo is not None:
            return fpo
        abort(404)

    # TODO: 需要进行用户鉴权
    @output({}, 204)
    @doc(summary='删除指定基金组合', description='该接口用于删除特定组合，需要给出组合编码')
    def delete(self, portfolio_code: str):
        """
        删除回测组合
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

    @input(FundPortfolioPatchInSchema(partial=True))
    @output(FundPortfolioDetailOutSchema)
    @doc(summary='部分更新指定基金组合', description='该接口用于更新特定组合（如：名称、风险等级、描述、可见性、投资理念），需要给出组合编码')
    def patch(self, portfolio_code: str, data: dict):
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
            raise PatchWithEmptyData

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
            comp_df['portion'] = comp_df.portion.apply(lambda x: x / 100)
            total = comp_df['portion'].sum()
            if total != 1.0:
                raise NotHundredPercentSumPortion

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
