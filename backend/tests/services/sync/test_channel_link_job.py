# -*- coding: utf-8 -*-
"""测试跨渠道关联（#1285 §3.8）：白名单匹配规则 + 落库 + 保护人工关联。"""

from app.domains.funds.models import ChannelLink
from app.services.sync.jobs.channel_link_job import ChannelLinkSyncJob, match_index_for_etf


def test_match_longest_keyword_wins():
    """「中证100」不得吞掉「中证1000」——取最长命中关键词。"""
    assert match_index_for_etf('中证1000ETF')[0] == '000852'
    assert match_index_for_etf('中证100ETF')[0] == '000903'


def test_match_various_names():
    assert match_index_for_etf('沪深300ETF华泰柏瑞')[0] == '000300'
    assert match_index_for_etf('创业板ETF')[0] == '399006'
    assert match_index_for_etf('科创50ETF')[0] == '000688'
    assert match_index_for_etf('A500ETF基金')[0] == '000510'


def test_match_no_hit():
    assert match_index_for_etf('某某主题ETF') is None


class _FakeAdapter:
    def fetch_etf_list(self):
        return [
            {'code': '510300', 'name': '沪深300ETF华泰柏瑞'},
            {'code': '159915', 'name': '创业板ETF'},
            {'code': '588000', 'name': '科创50ETF'},
            {'code': '512999', 'name': '某某主题ETF'},  # 无命中，应被丢弃
        ]


def test_channel_link_job_builds_links(db):
    job = ChannelLinkSyncJob(_FakeAdapter(), db)
    result = job.run()
    assert result['status'] == 'success'

    rows = db.query(ChannelLink).all()
    assert len(rows) == 3  # 无命中的 ETF 不入库
    link = next(r for r in rows if r.to_symbol == '510300')
    assert link.from_symbol == '000300'
    assert link.from_name == '沪深300'
    assert link.link_type == 'index_etf'


def test_channel_link_job_preserves_manual_links(db):
    """覆盖式重建只能清 auto 行——人工维护的关联不能被任务抹掉。"""
    db.add(
        ChannelLink(
            link_type='index_etf',
            from_symbol='000300',
            to_symbol='999999',
            match_type='manual',
            source='manual',
        )
    )
    db.commit()

    job = ChannelLinkSyncJob(_FakeAdapter(), db)
    job.run()

    manual = db.query(ChannelLink).filter_by(source='manual').all()
    assert len(manual) == 1
    assert db.query(ChannelLink).filter_by(source='auto').count() == 3
