# -*- coding: utf-8 -*-
"""Create an application instance."""

from backend.fundmate.app import create_app

app = create_app()


@app.after_request
def after_request(response):
    """
    本地开发时，前端运行的端口和后端 API 接口用的端口不一致，为了方便本地开发可以添加一个钩子，利用 CORS 实现跨域请求
    [wechat-admin：Flask使用篇 - 小明明s à domicile](https://www.dongwm.com/post/119/#CORS)
    :param response:
    :return:
    """
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add(
        'Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
    return response