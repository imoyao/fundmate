# -*- coding: utf-8 -*-
"""User views."""
from apiflask import APIBlueprint, abort, doc, input, output, pagination_builder
from flask.views import MethodView

from backend.fundmate.fund.models import Fund, FundCompany, FundMgr, FundPortfolio, FundPortfolioMgr, FundSaleOrg
from backend.fundmate.fund.schemas import (
    FundCompanyOutSchema,
    FundInSchema,
    FundOutSchema,
    FundPaginationOutSchema,
    FundPortfolioDetailOutSchema,
    FundPortfoliosOutSchema,
    FundPortfoliosPaginationSchema,
    FundSaleOutSchema,
)
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


@bp.route('/mgrs/')
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


@bp.route('/sales/')
class FundSalesView(MethodView):
    """
    基金销售机构
    """

    # @input(CustomPaginationSchema, 'query')
    @output(FundSaleOutSchema)
    def get(self):
        # 一些常用的销售渠道，在前面列出来
        hot_market_place = FundSaleOrg.query.filter(FundSaleOrg.known_name.isnot(None)).all()
        all_market_place = FundSaleOrg.query.all()
        hot_places = {'label': '热门渠道', 'options': hot_market_place}
        all_places = {'label': '所有渠道', 'options': all_market_place}
        all_options = [hot_places, all_places]
        market_place = {'options': all_options}
        return market_place


@bp.route('/<int:fund_id>')
class FundDetail(MethodView):
    """
    基金详情
    """

    @output(FundOutSchema)
    def get(self, fund_id: str):
        """获取指定基金信息"""
        user_obj = Fund.get_by_id(int(fund_id))
        return user_obj

    def post(self):
        """
        新建基金
        """
        return {'message': 'Hello,User!'}

    @input(FundInSchema(partial=True))
    @output(FundOutSchema)
    def patch(self, fund_id, data):
        """更新指定基金信息"""
        _user_obj = Fund.get_by_id(int(fund_id))
        if _user_obj:
            abort(404)
        user = Fund.save(data)
        return user


@bp.route('/<int:fund_id>/followers')
class FundFavor(MethodView):
    """
    某支基金的关注者
    """

    @output(FundOutSchema)
    def get(self, fund_id: str):
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
            mgr_code = fpo.mgr_code
            mgr_inst = FundPortfolioMgr.query.filter_by(code=mgr_code).one_or_none()
            fpo_info = dict()
            fpo_info['manager'] = mgr_inst
            # TODO: 对于需要联表查询的对象，是否有更加优雅的处理办法（如果不想将字段联表查询）
            fpo_info.update(fpo.__dict__)
            return fpo_info
        abort(404)
