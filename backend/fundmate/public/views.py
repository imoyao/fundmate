# -*- coding: utf-8 -*-
"""Public section, including homepage and signup."""
from apiflask import APIBlueprint, HTTPError, Schema, abort, input, output
from apiflask.fields import Integer, String
from apiflask.validators import Length, OneOf
from flask import flash, redirect, request, url_for
from flask.views import MethodView

from backend.fundmate import excepts as dt_except
from backend.fundmate.data import danjuan, jsl, yzyx
from backend.fundmate.extensions import login_manager
from backend.fundmate.fund.models import Fund
from backend.fundmate.fund.schemas import FundSampleSchema, FundSearchKeySchema
from backend.fundmate.schema_ext import RegisterSchema
from backend.fundmate.user.models import User

bp = APIBlueprint("public", __name__)


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID."""
    return User.get_by_id(int(user_id))


@bp.route('/')
class Home(MethodView):

    def post(self):
        flash("You are logged in.", "success")
        redirect_url = request.args.get("next") or url_for("user.members")
        return redirect(redirect_url)

    def get(self):
        return {'message': 'Hello,Flask!'}


@bp.route('/register/')
class Register(MethodView):

    @input(RegisterSchema(partial=True))
    def post(self, data):
        User.create(
            username=data.username,
            email=data.email,
            password=data.password,
            active=True,
        )


@bp.route("/logout/")
# @login_required
def logout():
    """Logout."""
    # logout_user()
    flash("You are logged out.", "info")
    return redirect(url_for("public.home"))


@bp.route("/about/")
def about():
    """About page."""
    return 'render_template("public/about.html")'


@bp.get('/thermometers')
def thermometer():
    """
    行情估值信息
    目前包括集思录温度、有知有行温度、蛋卷估值
    """
    try:
        yzyx_info = yzyx.yzyx.last()
    except dt_except.CrawlerException:
        yzyx_info = None
    jsl_info = jsl.jsl.overview()
    dj_info = danjuan.dj.overview()
    info = {'yzyx': yzyx_info, 'jsl': jsl_info, 'dj': dj_info}
    return info


@bp.get('/search/funds/')
@input(FundSearchKeySchema, 'query')
@output(FundSampleSchema(many=True))
def search_fund(search_key):
    """
    通过基金编码，基金名称，基金简拼搜索基金信息
    """
    q = search_key.get('q')
    # 用法参考：https://github.com/greyli/apiflask/blob/fde330b41847727fb1ddeb3963c466f1118dc9db/examples/orm/app.py#L58
    funds = Fund.search_key(q)
    if funds:
        return funds
    raise HTTPError(404, 'Please check your input keywords.')


@bp.get('/search/accounts')
def search_account():
    """
    通过账户名称搜索本人名下账户，在记账选择账本时有用
    """
    pass
