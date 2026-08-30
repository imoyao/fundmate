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
仍未命中则保留 code=name 占位并打 warning（设计文档明确接受的回退）。
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


def _normalize_company_name(name: str) -> str:
    """剥除常见法人主体后缀，保留品牌核心词用于匹配。

    采用迭代剥离：单次剥离会把「股份有限公司」+「证券」这类组合后缀拆成多级，
    必须反复剥到不再变化（如「银华基金管理股份有限公司」→「银华基金」→「银华」），
    才能与天天基金列表简称（「银华基金」归一化后为「银华」）对齐。同时去掉
    「(中国)」这类属地括号，避免其阻断后缀剥离（#1199 实测失配样本归因）。
    """
    if not name:
        return ''
    n = name.strip()
    # 去掉法人属地括号，如「(中国)」「（中国）」
    n = re.sub(r'[（(][^（）()]*[）)]', '', n)
    changed = True
    while changed:
        changed = False
        # 每轮选最长的可剥后缀，避免「有限公司」先于「股份有限公司」被误剥
        # （如「银华基金管理股份有限公司」应剥「股份有限公司」而非「有限公司」）
        best = None
        for suffix in _COMPANY_SUFFIXES:
            if n.endswith(suffix) and len(n) > len(suffix):
                if best is None or len(suffix) > len(best):
                    best = suffix
        if best:
            n = n[: -len(best)]
            changed = True
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
    """按公司名解析真值 code；精确匹配优先，否则归一化匹配；未命中返回 None。"""
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


def backfill_fund_company_codes(db: Session, dry_run: bool = True) -> Dict[str, object]:
    """
    回填 fund_companies 表中 code==name 的占位行（幂等）。

    仅处理 code 仍等于 name 的行；按名解析真值 code，命中则更新 code（并顺带把
    name 修正为 jjjz_gs 的简称，便于后续一致匹配）。若真值 code 已被别的行占用，
    跳过并告警（避免唯一约束冲突）。dry_run=True 只统计不落库。

    返回结构化结果（#1199 用于实测命中率并留档）：
        {
            'total_placeholders': int,                       # code==name 占位总行数
            'matched':  [{'id','name','old_code','new_code'}, ...],  # 命中待回填
            'unmatched':[{'id','name','code'}, ...],          # 失配/冲突跳过，仍保留占位
        }
    hit_rate = len(matched) / total_placeholders。
    """
    placeholders = db.query(FundCompany).filter(FundCompany.code == FundCompany.name).all()
    # 已存在的真值 code 集合，用于冲突检测
    taken_codes = {row[0] for row in db.query(FundCompany.code).all()}
    matched: List[dict] = []
    unmatched: List[dict] = []
    for inst in placeholders:
        real_code = get_company_code_by_name(inst.name)
        if not real_code:
            unmatched.append({'id': inst.id, 'name': inst.name, 'code': inst.code})
            logger.warning(f'基金公司「{inst.name}」未匹配到权威 code，保留占位')
            continue
        if real_code in taken_codes and real_code != inst.code:
            unmatched.append({'id': inst.id, 'name': inst.name, 'code': inst.code})
            logger.warning(f'真值 code {real_code} 已被占用，跳过「{inst.name}」')
            continue
        matched.append({'id': inst.id, 'name': inst.name, 'old_code': inst.code, 'new_code': real_code})
        if not dry_run:
            inst.code = real_code
            taken_codes.add(real_code)
    if not dry_run and matched:
        db.commit()
        logger.info(f'回填 {len(matched)} 条基金公司 code')
    return {'total_placeholders': len(placeholders), 'matched': matched, 'unmatched': unmatched}
