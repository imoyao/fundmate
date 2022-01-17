# -*- coding: utf-8 -*-
"""Public section, including homepage and signup."""
from apiflask import APIBlueprint, HTTPError, input, output
from flask import flash, redirect, request, url_for
from flask.views import MethodView

from backend.fundmate import excepts as dt_except
from backend.fundmate.data import danjuan, fundb, jsl, yzyx
from backend.fundmate.fund.models import Fund
from backend.fundmate.fund.schemas import FundSampleSchema, FundSearchKeySchema
from backend.fundmate.public.schemas import ThermometerInSchema, ThermometerOutSchema

bp = APIBlueprint("public", __name__)


@bp.route('/')
class Home(MethodView):

    def post(self):
        flash("You are logged in.", "success")
        redirect_url = request.args.get("next") or url_for("user.members")
        return redirect(redirect_url)

    def get(self):
        return {'message': 'Hello,Flask!'}


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
@input(ThermometerInSchema, 'query')
@output(ThermometerOutSchema)
def thermometer(query_args):
    """
    行情估值信息
    目前包括集思录温度、有知有行温度、蛋卷估值
    """
    is_full = query_args.get('is_full')
    try:
        yzyx_info = yzyx.yzyx.daily_temper(is_full=is_full)
    except dt_except.CrawlerException:
        yzyx_info = None
    jsl_info = jsl.jsl.qz_info(is_full=is_full)
    dj_info = danjuan.dj_evl.valuation(is_full=is_full)
    jq_info = fundb.jq_app.kjtl(is_full=is_full)
    info = {'yzyx': yzyx_info, 'jsl': jsl_info, 'dj': dj_info, 'jq': jq_info}
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
