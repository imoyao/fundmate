# -*- coding: utf-8 -*-
# app/services/sync/company_resolver.py
"""
基金公司 code 解析与回填（#1168 P1）。

数据源：天天基金基金公司列表 http://fund.eastmoney.com/js/jjjz_gs.js
实测返回：var gs={op:[["80163340","安信基金"],["81608035","安联基金"],...]}
即 [code(8位), name(简称)] 数组。

为什么单独成模块：akshare 全链路只给公司"名"不给"code"，导致 fund_companies
表大量 code==name 占位。本模块集中负责"名→真值 code"的解析，供各 Job 与
backfill 脚本复用，避免逻辑散落。

名称匹配难点：akshare 的 基金管理人 是全称（"易方达基金管理有限公司"），而
jjjz_gs.js 是简称（"易方达基金"），精确匹配会大量失配。故先做后缀归一化再匹配；
仍未命中则查手动映射 _MANUAL_MAPPING；最后保留 code=name 占位并打 warning
（设计文档明确接受的回退）。

手动映射适用场景：东财 jjjz_gs.js 使用简称（如"国泰海通资管"），与
fund_companies 全称（"上海国泰海通证券资产管理有限公司"）无法通过后缀
归一化匹配。已实测确认可映射的公司列入 _MANUAL_MAPPING。
"""

import json
import re
from typing import Dict, List, Optional

import requests
from loguru import logger
from sqlalchemy.orm import Session

from app.domains.funds.models import FundCompany

_EASTMONEY_COMPANY_URL = 'http://fund.eastmoney.com/js/jjjz_gs.js'
# 归一化时剥除的常见法人主体后缀（只剥一层最长的匹配）
_COMPANY_SUFFIXES = (
    '基金管理有限公司',
    '基金管理公司',
    '资产管理有限公司',
    '资产管理公司',
    '基金管理',
    '资产管理',
    '有限公司',
    '有限责任公司',
    '股份有限公司',
    '基金',
    '资管',
    '证券',
)

_cache: Optional[Dict[str, str]] = None  # name(归一化) -> code

# 手动映射：东财 jjjz_gs.js 使用简称，与 fund_companies 全称无法通过后缀归一化匹配。
# 仅收录已实测确认可映射的公司（地名前缀剥离后能对上东财简称）。
_MANUAL_MAPPING: Dict[str, str] = {
    '上海国泰海通证券资产管理有限公司': '80156175',
    '浙江浙商证券资产管理有限公司': '80403111',
    '新疆前海联合基金管理有限公司': '80468996',
    '中国人保资产管理有限公司': '80061431',
    '财通证券资产管理有限公司': '80404701',
}


def _normalize_company_name(name: str) -> str:
    """剥除常见法人主体后缀，保留品牌核心词用于匹配。"""
    if not name:
        return ''
    n = name.strip()
    for suffix in _COMPANY_SUFFIXES:
        if n.endswith(suffix) and len(n) > len(suffix):
            return n[: -len(suffix)]
    return n


def fetch_fund_company_list() -> List[Dict[str, str]]:
    """抓取并解析天天基金基金公司列表，返回 [{code, name}, ...]。"""
    resp = requests.get(_EASTMONEY_COMPANY_URL, timeout=15)
    resp.encoding = 'utf-8'
    text = resp.text
    m = re.search(r'op:(\[.*?\])\s*}', text, re.DOTALL)
    if not m:
        logger.warning('解析基金公司列表失败：未找到 op 数组')
        return []
    arr = json.loads(m.group(1))
    return [{'code': str(row[0]), 'name': str(row[1])} for row in arr if len(row) >= 2]


def get_company_code_by_name(name: str) -> Optional[str]:
    """按公司名解析真值 code；手动映射优先，其次精确/归一化匹配；未命中返回 None。"""
    if name in _MANUAL_MAPPING:
        return _MANUAL_MAPPING[name]
    global _cache
    if _cache is None:
        try:
            companies = fetch_fund_company_list()
        except Exception as e:  # 网络/解析失败不应阻断同步主流程
            logger.warning(f'获取基金公司列表失败，跳过 code 解析: {e}')
            _cache = {}
            return None
        _cache = {}
        for c in companies:
            norm = _normalize_company_name(c['name'])
            # 精确名与归一化名都建索引，提高命中率
            _cache.setdefault(c['name'], c['code'])
            if norm:
                _cache.setdefault(norm, c['code'])
    if not name:
        return None
    exact = _cache.get(name)
    if exact:
        return exact
    return _cache.get(_normalize_company_name(name))


def backfill_fund_company_codes(db: Session, dry_run: bool = True) -> List[dict]:
    """
    回填 fund_companies 表中 code==name 的占位行（幂等）。

    仅处理 code 仍等于 name 的行；按名解析真值 code，命中则更新 code（并顺带把
    name 修正为 jjjz_gs 的简称，便于后续一致匹配）。若真值 code 已被别的行占用，
    跳过并告警（避免唯一约束冲突）。dry_run=True 只返回待变更清单不落库。
    """
    placeholders = db.query(FundCompany).filter(FundCompany.code == FundCompany.name).all()
    # 已存在的真值 code 集合，用于冲突检测
    taken_codes = {row[0] for row in db.query(FundCompany.code).all()}
    changes: List[dict] = []
    for inst in placeholders:
        real_code = get_company_code_by_name(inst.name)
        if not real_code:
            logger.warning(f'基金公司「{inst.name}」未匹配到权威 code，保留占位')
            continue
        if real_code in taken_codes and real_code != inst.code:
            logger.warning(f'真值 code {real_code} 已被占用，跳过「{inst.name}」')
            continue
        changes.append({'id': inst.id, 'name': inst.name, 'old_code': inst.code, 'new_code': real_code})
        if not dry_run:
            inst.code = real_code
            taken_codes.add(real_code)
    if not dry_run and changes:
        db.commit()
        logger.info(f'回填 {len(changes)} 条基金公司 code')
    return changes
