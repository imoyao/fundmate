# -*- coding: utf-8 -*-
"""User views."""
from apiflask import APIBlueprint, abort, input, output, pagination_builder
from flask.views import MethodView

from backend.fundmate.base_scheme import EmptySchema, PaginationSchema
from backend.fundmate.fund.models import Fund, FundCompany, FundMgr, FundSaleOrg
from backend.fundmate.fund.schemas import (
    FundCompanyOutSchema,
    FundInSchema,
    FundOutSchema,
    FundPaginationOutSchema,
    FundSaleOutSchema,
    FundSampleSchema,
)
from backend.fundmate.view_ext import paginate_query

bp = APIBlueprint("fund", __name__, url_prefix="/funds")


@bp.get('/')
@input(PaginationSchema, 'query')
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

    @input(PaginationSchema, 'query')
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

    @input(PaginationSchema, 'query')
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

    @input(PaginationSchema, 'query')
    @input(EmptySchema)
    @output(FundSaleOutSchema)
    def get(self, query: dict = None):
        if query:
            ret = paginate_query(FundSaleOrg, query)
        else:
            ret = FundSaleOrg.query.groupby(FundSaleOrg.org_type)
        return ret

    # @input(EmptySchema)
    # @output(FundSaleOutSchema)
    # def get(self):
    #     ret = FundSaleOrg.query.groupby(FundSaleOrg.org_type)
    #     return ret


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


@bp.route('/combinations')
class FundCombination(MethodView):
    """
    基金组合
    """

    @output(FundOutSchema)
    def get(self):
        """获取组合列表"""
        pass


@bp.route('/combinations')
class CombinationDetail(MethodView):
    """
    单个基金组合详情
    """

    @output(FundOutSchema)
    def get(self, comb_id: str):
        """获取指定基金组合信息"""
        pass

    @input(FundOutSchema)
    def post(self, comb_id: str):
        """获取指定基金组合信息"""
        pass
