# -*- coding: utf-8 -*-
"""Create an application instance."""

from backend.fundmate.app import create_app

app = create_app()


@app.after_request
def after_request(response):
    """
    before_first_request
    在第一次请求时会调用，后续的所有请求都不会在调用该函数，除非重新初始化。

    before_request
    每次处理请求前会调用该函数，包括了第一次请求。

    after_request
    如果请求没有异常，每次请求之后会调用的函数。

    teardown_request
    即使遇到了异常，每次请求之后也会调用的函数。

    teardown_appcontext
    会在应用退出的时候被调用。

    本地开发时，前端运行的端口和后端 API 接口用的端口不一致，为了方便本地开发可以添加一个钩子，利用 CORS 实现跨域请求
    [wechat-admin：Flask使用篇 - 小明明s à domicile](https://www.dongwm.com/post/119/#CORS)
    :param response:
    :return:
    """
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    # response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
    return response
