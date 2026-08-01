# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/23 20:42
# File : views.py
# -*- coding: utf-8 -*-
"""
市场温度 API 路由
"""

from apiflask import APIBlueprint
from flask import jsonify, request

from app.services.thermometer.service import TemperatureService

thermometer_bp = APIBlueprint('temperature', __name__, url_prefix='/api/temperature')


@thermometer_bp.get('/overview')
def get_temperature_overview():
    """
    获取市场温度概览（探市页面使用）

    GET /api/temperature/overview

    Response:
      {
        "data": {
          "updated_at": "2026-07-23 21:30:00",
          "singles": [
            {"source": "eastmoney_volume", "name": "全市场成交额", "value": 12581.48, "label": "温和", "unit": "亿", "collected_at": "2026-07-23 15:00:00"}
          ],
          "composites": {
            "self_calc": {"pe": 12.3, "percent": 45.0, "level": "正常", "collected_at": "2026-07-23 21:00:00"},
            "jisilu_indicator": {"median_pb": 2.35, "median_pb_temperature": 22.75, ...}
          },
          "links": {
            "jisilu": "https://www.jisilu.cn/data/indicator/",
            "jiucaishuo": "https://app.jiucaishuo.com/",
            ...
          }
        },
        "message": "success"
      }
    """
    data = TemperatureService.get_overview()
    return jsonify({'data': data, 'message': 'success'})
