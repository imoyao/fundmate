#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/7/23 14:00
"""
基金账本相关
TODO: 用户账户和基金账户容易混淆，可能使用嵌套蓝图更好
"""
from apiflask import APIBlueprint, input, output
from flask.views import MethodView

from backend.fundmate.account.models import Account
from backend.fundmate.account.schemas import AccountOutSchema, CreateAccountSchema
from backend.fundmate.base_scheme import EmptySchema, PaginationSchema
from backend.fundmate.view_ext import paginate_query

bp = APIBlueprint("account", __name__, url_prefix="/accounts")


@bp.route('/<int:user_id>')
class Accounts(MethodView):
    """
    用户名下账号区分
    """

    @input(PaginationSchema, 'query')
    @input(EmptySchema)
    @output(AccountOutSchema(many=True))
    def get(self, query):
        """
        根据类型查询自己名下的账户，账户按照类型区分：
        支持all,stock,fund,bank,
        :param query:
        :return:
        """
        if query:
            ret = paginate_query(Account, query)
        else:
            pass
            ret = None
        return ret


@bp.route('/<int:account_id>')
class AccountsDetail(MethodView):
    """
    获取指定账户的信息
    """

    @output(AccountOutSchema)
    def get(self, pet_id):
        """查询某个账本基本信息
        名称、描述、包含的基金、比例、金额
        """
        pass

    @input(CreateAccountSchema(partial=True))
    @output(AccountOutSchema)
    def patch(self, pet_id, data):
        """更新账户信息
        名称，描述，
        """
        pass
