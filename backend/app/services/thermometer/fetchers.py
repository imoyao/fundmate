# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/23 20:37
# File : fetchers.py
# -*- coding: utf-8 -*-
"""
市场温度数据获取器

各数据源独立 fetch 函数，单源失败优雅降级（返回 None）
符合总纲 §6 "可插拔降级" 原则
"""

import logging
import os
import time
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
TIMEOUT = 15


# ─── 集思录：可转债温度 ───
def fetch_jisilu_cb_temperature() -> Optional[Dict[str, Any]]:
    """
    集思录可转债温度
    GET /data/indicator/get_cb_temperature/
    返回: {"cb_temperature": "73.56"} → 温度值
    """
    try:
        url = 'https://www.jisilu.cn/data/indicator/get_cb_temperature/'
        headers = {
            'User-Agent': UA,
            'Referer': 'https://www.jisilu.cn/data/indicator/',
        }
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        temp_str = data.get('cb_temperature')
        if temp_str is None:
            return None
        value = float(temp_str)
        return {
            'value': value,
            'label': '偏高' if value > 70 else ('适中' if value > 40 else '偏低'),
            'unit': '%',
            'raw': data,
        }
    except Exception as e:
        logger.error(f'集思录可转债温度获取失败: {e}')
        return None


# ─── 集思录：估值指标 ───
def fetch_jisilu_indicator() -> Optional[Dict[str, Any]]:
    """
    集思录市场估值指标
    GET /data/indicator/get_last_indicator/
    返回: {median_pb, median_pb_temperature, median_pe, median_pe_temperature, ...}
    """
    try:
        url = 'https://www.jisilu.cn/data/indicator/get_last_indicator/'
        headers = {
            'User-Agent': UA,
            'Referer': 'https://www.jisilu.cn/data/indicator/',
        }
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        # 解析数值
        result = {
            'price_dt': data.get('price_dt'),
            'median_pb': float(data.get('median_pb', 0)),
            'median_pb_temperature': float(data.get('median_pb_temperature', 0)),
            'median_pe': float(data.get('median_pe', 0)),
            'median_pe_temperature': float(data.get('median_pe_temperature', 0)),
            'stock_count': float(data.get('stock_count', 0)),
            'ipo_count': float(data.get('IPO_count', 0)),
            'st_count': float(data.get('st_count', 0)),
            'index_point': float(data.get('index_point', 0)),
        }
        return {'data': result, 'raw': data}
    except Exception as e:
        logger.error(f'集思录估值指标获取失败: {e}')
        return None


# ─── 东财：全市场成交额 ───
# backend/app/services/temperature/fetchers.py


def fetch_eastmoney_volume() -> Optional[Dict[str, Any]]:
    """东财全市场成交额（上证 + 深证 + 北证）"""
    boards = {
        '上证': '1.000001',
        '深证': '0.399001',
        '北证': '0.899050',
    }

    # 尝试多个域名
    hosts = ['push2.eastmoney.com', 'push2delay.eastmoney.com']

    total = 0.0
    parts = {}

    session = requests.Session()
    session.headers.update(
        {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com/',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
        }
    )

    for name, secid in boards.items():
        success = False
        for host in hosts:
            for attempt in range(3):
                try:
                    url = f'https://{host}/api/qt/stock/get?secid={secid}&fields=f48'
                    resp = session.get(url, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        amt = data.get('data', {}).get('f48', 0) / 1e8
                        total += amt
                        parts[name] = round(amt, 1)
                        success = True
                        break
                except Exception as e:
                    if attempt == 2:
                        logger.debug(f'东财 {name} {host} 失败: {e}')
                    else:
                        time.sleep(0.5)
            if success:
                break
        if not success:
            logger.warning(f'东财 {name} 成交额获取失败（所有域名重试3次）')
            return None

    if total == 0:
        return None

    label = '放量' if total > 12000 else ('缩量' if total < 8000 else '温和')
    return {
        'value': round(total, 1),
        'label': label,
        'unit': '亿',
        'raw': {'parts': parts},
    }


# ─── 且慢：市场温度（MCP） ───
def fetch_qieman() -> Optional[Dict[str, Any]]:
    """
    且慢 MCP 调用（优化版）
    """
    api_key = os.getenv('QIEMAN_API_KEY')
    if not api_key:
        logger.warning('QIEMAN_API_KEY 未配置，跳过且慢温度')
        return None

    try:
        # 使用更长的超时时间（MCP 握手需要时间）
        with requests.Session() as session:
            # 1. 建立 SSE 连接
            resp = session.get(
                'https://stargate.yingmi.com/mcp/sse',
                params={'apiKey': api_key},
                headers={'Accept': 'text/event-stream'},
                timeout=30,  # 增加超时
                stream=True,
            )
            # ... 后续 MCP 握手逻辑
    except requests.exceptions.Timeout:
        logger.warning('且慢 MCP 连接超时，跳过')
        return None
    except Exception as e:
        logger.error(f'且慢 MCP 调用失败: {e}')
        return None


# ─── 有知有行：全市场温度（网页 SSR） ───
def fetch_youzhiyouxing() -> Optional[Dict[str, Any]]:
    """
    有知有行全市场温度（网页 SSR 解析）
    公开可抓，零维护
    """
    import re

    try:
        url = 'https://youzhiyouxing.cn/thermometer'
        resp = requests.get(url, headers={'User-Agent': UA}, timeout=TIMEOUT)
        html = resp.text

        m = re.search(r'(\d+)°(?:<[^>]*>|\s)*([一-龥]{2})(?:<[^>]*>|\s)*温度下降', html)
        if not m:
            return None
        temp = int(m.group(1))
        label = m.group(2)

        # 提取更新时间
        t = re.search(r'温度更新时间：([0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日 [0-9]{1,2}:[0-9]{2})', html)
        updated = t.group(1) if t else ''

        # 提取各指数温度
        idx_codes = {'沪深300': '000300.SH', '中证500': '000905.SH', '上证50': '000016.SH'}
        idx = {}
        for name, code in idx_codes.items():
            im = re.search(re.escape(code) + r'.*?(\d+)°', html, re.S)
            if im:
                idx[name] = int(im.group(1))

        return {
            'value': float(temp),
            'label': label,
            'unit': '%',
            'raw': {'updated': updated, 'indices': idx},
        }
    except Exception as e:
        logger.error(f'有知有行温度获取失败: {e}')
        return None


# ─── 韭圈儿：恐惧贪婪 + 中长期温度（Playwright） ───
def fetch_jiucaishuo() -> Optional[Dict[str, Any]]:
    """
    韭圈儿：恐惧贪婪指数 + 中长期温度
    需要 playwright 依赖
    """
    import re

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning('playwright 未安装，跳过韭圈儿数据')
        return None

    result = {'fear': None, 'medium': None}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            page = browser.new_page(user_agent=UA)
            page.goto('https://app.jiucaishuo.com/', wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(2500)
            txt = page.inner_text('body') or ''
            browser.close()

            # 短期情绪
            m = re.search(r'短期情绪\s*(\d{1,3})\s*([一-龥]+)', txt)
            if m:
                result['fear'] = {'value': int(m.group(1)), 'label': m.group(2)}

            # 中长期温度
            m = re.search(r'中长期温度\s*(\d{1,3})\s*℃\s*([一-龥]+)', txt)
            if m:
                result['medium'] = {'value': int(m.group(1)), 'label': m.group(2)}

            return result
    except Exception as e:
        logger.error(f'韭圈儿数据获取失败: {e}')
        return None
