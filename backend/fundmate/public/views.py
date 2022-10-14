# -*- coding: utf-8 -*-
"""Public section, including homepage and signup."""
from apiflask import APIBlueprint, HTTPError
from flask import flash, redirect, request, url_for
from flask.views import MethodView

from backend.fundmate import excepts
from backend.fundmate.data import danjuan, fundb, jsl, yzyx, zo
from backend.fundmate.errors import ThermometerError
from backend.fundmate.fund.models import Fund
from backend.fundmate.fund.schemas import FundSampleSchema, FundSearchKeySchema
from backend.fundmate.public.schemas import ThermometerInSchema, ThermometerOutSchema


bp = APIBlueprint('public', __name__)


@bp.route('/')
class Home(MethodView):

    def post(self):
        flash('You are logged in.', 'success')
        redirect_url = request.args.get('next') or url_for('user.members')
        return redirect(redirect_url)

    def get(self):
        fund_mate_str = r'''
              ___      ___         ___        _____                  ___         ___                 ___
             /  /\    /__/\       /__/\      /  /::\                /__/\       /  /\        ___    /  /\
            /  /:/_   \  \:\      \  \:\    /  /:/\:\              |  |::\     /  /::\      /  /\  /  /:/_
           /  /:/ /\   \  \:\      \  \:\  /  /:/  \:\             |  |:|:\   /  /:/\:\    /  /:/ /  /:/ /\
          /  /:/ /:___  \  \:\ _____\__\:\/__/:/ \__\:|          __|__|:|\:\ /  /:/~/::\  /  /:/ /  /:/ /:/_
         /__/:/ /:/__/\  \__\:/__/::::::::\  \:\ /  /:/         /__/::::| \:/__/:/ /:/\:\/  /::\/__/:/ /:/ /\
         \  \:\/:/\  \:\ /  /:\  \:\~~\~~\/\  \:\  /:/          \  \:\~~\__\\  \:\/:/__\/__/:/\:\  \:\/:/ /:/
          \  \::/  \  \:\  /:/ \  \:\  ~~~  \  \:\/:/            \  \:\      \  \::/    \__\/  \:\  \::/ /:/
           \  \:\   \  \:\/:/   \  \:\       \  \::/              \  \:\      \  \:\         \  \:\  \:\/:/
            \  \:\   \  \::/     \  \:\       \__\/                \  \:\      \  \:\         \__\/\  \::/
             \__\/    \__\/       \__\/                             \__\/       \__\/               \__\/
        '''
        index_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Hello,Fund Mate!</title>
</head>
<body class="fund-mate">
<main>
    <div style="margin-left: 20%;">

        <h1>🎈Hello,There!</h1>
        <div>
            <pre>{fund_mate_str}</pre>
        </div>
        <div>
            <p>Please click 👉 <a target="_blank" href="/docs">here</a> to visit API Document!</p>
            <p>请点击 👉 <a target="_blank" href="/docs">此处</a> 访问 API 文档！</p>
        </div>
    </div>


</main>

</body>
<style>

    .fund-mate{{
        position: relative;
        display: -webkit-box;
        display: -ms-flexbox;
        display: flex;
        -webkit-box-align: start;
        -ms-flex-align: start;
        align-items: flex-start;
        width: 1000px;
        padding: 0 16px;
        margin: 10px auto;
    }}

</style>
</html>
        """  # noqa: W605
        return index_html


@bp.route('/logout/')
def logout():
    """Logout."""
    # logout_user()
    flash('You are logged out.', 'info')
    return redirect(url_for('public.home'))


@bp.route('/sentry/<int:numerator>/divide/<int:denominator>/')
def test_sentry(numerator, denominator):
    """
    测试 sentry 是否正常运行
    """
    answer = numerator / denominator
    data = {
        'numerator': numerator,
        'denominator': denominator,
        'answer': answer,
    }
    result = {'detail': data, 'msg': f'{numerator} can be divided by {denominator} with {answer} times.'}
    return result


@bp.route('/about/')
def about():
    """About page."""
    return 'render_template("public/about.html")'


@bp.get('/investment_and_service/')
@bp.input(ThermometerInSchema, 'query')
def investment_and_service(query_args):
    """
    短期信号，展示投顾服务信息
    :return:
    """
    is_full = query_args.get('is_full')
    follow_api = zo.FollowAip()
    zo_info = follow_api.zo_view(is_full=is_full)
    return zo_info


@bp.get('/thermometers')
@bp.input(ThermometerInSchema, 'query')
@bp.output(ThermometerOutSchema)
def thermometer(query_args):
    """行情估值信息
    目前包括集思录温度、有知有行温度、蛋卷估值
    """
    is_full = query_args.get('is_full')
    try:
        yzyx_info = yzyx.yzyx.daily_temper(is_full=is_full)
    except excepts.CrawlerException:
        raise ThermometerError from excepts.CrawlerException

    jsl_info = jsl.jsl.qz_info(is_full=is_full)

    dj_info = danjuan.dj_evl.valuation(is_full=is_full)

    jq_info = fundb.jq_app.kjtl(is_full=is_full)

    follow_api = zo.FollowAip()
    if is_full:
        # 不需要展示最完整信息
        zo_view = follow_api.zo_view(is_full=False, is_minimal=False)
    else:
        zo_view = follow_api.zo_view(is_minimal=False)
    info = {'yzyx': yzyx_info, 'jsl': jsl_info, 'dj': dj_info, 'jq': jq_info, 'zo_view': zo_view}
    return info


@bp.get('/search/funds/')
@bp.input(FundSearchKeySchema, 'query')
@bp.output(FundSampleSchema(many=True))
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
