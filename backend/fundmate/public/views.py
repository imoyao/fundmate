# -*- coding: utf-8 -*-
"""Public section, including homepage and signup."""
from apiflask import APIBlueprint
from apiflask.views import MethodView
from flask import flash, redirect, url_for

from backend.fundmate import excepts
from backend.fundmate.data import danjuan, fundb, jsl, sipf, yzyx, zo
from backend.fundmate.errors import CrawlerError, HTTPServerError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.public.schemas import ThermometerInSchema, ThermometerOutSchema


bp = APIBlueprint('public', __name__)


@bp.route('/')
class Home(MethodView):

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
def sentry_server(numerator, denominator):
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
    return {'info': '我的投资账本！'}


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
    is_minimal = query_args.get('is_minimal')
    follow_api = zo.FollowAip()
    if is_minimal:
        # FIXME: 需要增加接口去获取最简单的数据
        is_full = False
        yzyx_info = yzyx.yzyx.daily_temper(is_minimal=True)
        jq_info = fundb.jq_app.kjtl(is_full=is_full)
        stock_bond_ratio_info = follow_api.stock_bond_ratio(is_minimal=True)
        dj_info = danjuan.dj_evl.valuation(is_full=is_full)
        logger.info(f'{stock_bond_ratio_info}, {dj_info}')
        jq_result = jq_info.get('overview')
        lsd_grade = dj_info.get('lsd').get('data')
        jiucai_data = dj_info.get('jiucai').get('data')
        lsd_grade['title'] = '投资星级'
        jiucai_data['title'] = '股债利差'
        info = {
            'jq': jq_result,
            'yzyx': yzyx_info,
            'fed': jiucai_data,
            'invest_grade': lsd_grade,
            'zo_view': stock_bond_ratio_info,
            'confidence': {},
        }
    else:
        is_full = query_args.get('is_full', False)
        try:
            yzyx_info = yzyx.yzyx.daily_temper(is_full=is_full)
        except excepts.CrawlerException as e:
            error = CrawlerError.THERMOMETER_ERR
            msg = str(e)
            extra_data = {'error_code': error.code, 'docs': ''}
            raise HTTPServerError(message=msg, extra_data=extra_data) from e

        jsl_info = jsl.jsl.qz_info(is_full=is_full)

        dj_info = danjuan.dj_evl.valuation(is_full=is_full)

        jq_info = fundb.jq_app.emotion(is_full=is_full)
        if is_full:
            # 不需要展示最完整信息
            zo_view = follow_api.zo_view(is_minimal=False, is_full=False)
        else:
            zo_view = follow_api.zo_view(is_minimal=False)
        lsd_grade = dj_info.get('lsd').get('data')
        jiucai_data = dj_info.get('jiucai').get('data')
        confidence = sipf.Confidence()
        confidence_result = confidence.latest_info()
        info = {'yzyx': yzyx_info, 'jsl': jsl_info, 'fed': jiucai_data,
                'invest_grade': lsd_grade, 'jq': jq_info, 'zo_view': zo_view,
                'confidence': confidence_result}
    return info


@bp.get('/search/accounts')
def search_account():
    """
    通过账户名称搜索本人名下账户，在记账选择账本时有用
    """
    pass
