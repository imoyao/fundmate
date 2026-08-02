# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/23 20:42
# File : views.py
# -*- coding: utf-8 -*-
"""
市场温度 API 路由
"""

from datetime import datetime

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
            "self_calc": {"pe": 12.3, "percent": 45.0, "level": "适中", "collected_at": "2026-07-23 21:00:00"},
            "jisilu_indicator": {"median_pb": 2.35, "median_pb_temperature": 22.75, "median_pb_level": "偏低", ...},
            "temperature_bands": {
              "short": {"name": "短期情绪", "value": 30.8, "level": "偏低"},
              "medium": {"name": "中期温度", "value": 49.0, "level": "适中"},
              "long": {"name": "长期估值", "value": 44.0, "level": "适中"}
            }
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


# backend/app/apis/temperature/views.py

# 在现有代码后追加


@thermometer_bp.get('/history')
def get_temperature_history():
    """
    获取综合温度历史趋势（薄视图，业务逻辑委托给 TemperatureService）

    Query Parameters:
        days: 获取最近多少天的数据，默认 90
        source: 指标来源，默认 composite_temperature（综合温度）
    """
    days = request.args.get('days', 90, type=int)
    source = request.args.get('source', 'composite_temperature')

    try:
        data = TemperatureService.get_history(source, days)
        return jsonify({'data': data, 'message': 'success'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@thermometer_bp.get('/multi')
def get_multi_items():
    """获取多维列表数据（薄视图，业务逻辑委托给 TemperatureService）"""
    source = request.args.get('source')
    date_str = request.args.get('date')

    if not source:
        return jsonify({'message': 'source 参数必填'}), 400

    target_date = None
    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    try:
        data = TemperatureService.get_multi_items(source, target_date)
        return jsonify({'data': data, 'message': 'success'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500
