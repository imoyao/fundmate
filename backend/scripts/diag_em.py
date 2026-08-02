# -*- coding: utf-8 -*-
# File : diag_em.py
# 本机诊断：判断东方财富 clist 接口到底被什么挡住、host 重写补丁是否生效。
#
# 用法（在 backend/ 目录下）:
#     pdm run python scripts/diag_em.py
#
# 历史坑：akshare index_zh_a_hist 第一步打 `80.push2.eastmoney.com/api/qt/clist/get`
# 解析行业指数 secid，该 `80.` 子域从部分网络直连即被 RST（RemoteDisconnected），
# 而同接口的 `push2.eastmoney.com`（无前缀）可通。本诊断直接对比二者。
import os
import sys

# 让脚本能 import 项目包（backend 在 sys.path[0]）
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# 真实出错的那一步：行业指数 secid 解析（clist）
CLIST_PARAMS = {
    'pn': '1',
    'pz': '5',
    'po': '1',
    'np': '1',
    'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
    'fltt': '2',
    'invt': '2',
    'fid': 'f3',
    'fs': 'b:MK0010,m:1+t:1,m:0 t:5,m:1+s:3,m:0+t:5,m:2',
    'fields': 'f12,f13',
}
TIMEOUT = 20


def _get(url):
    import requests

    try:
        r = requests.get(url, params=CLIST_PARAMS, timeout=TIMEOUT)
        return f'OK  status={r.status_code} len={len(r.text)}'
    except Exception as e:
        return f'FAIL {type(e).__name__}: {e}'


def test_clist_80():
    """A) 出问题的 host：80.push2.eastmoney.com（akshare index_zh_em.py 实际用的）"""
    return _get('https://80.push2.eastmoney.com/api/qt/clist/get')


def test_clist_push2():
    """B) 候选修复 host：push2.eastmoney.com（无前缀，akshare 多数函数本就用它）"""
    return _get('https://push2.eastmoney.com/api/qt/clist/get')


def test_akshare_with_patch():
    """C) 真实 akshare 调用（import app 后全局补丁已把 80.push2 重写为 push2）"""
    import akshare as ak

    try:
        df = ak.index_zh_a_hist(symbol='000300', period='daily', start_date='20260101', end_date='20260801')
        return f'OK  rows={len(df)}'
    except Exception as e:
        return f'FAIL {type(e).__name__}: {e}'


def main():
    print('=' * 60)
    print('东方财富 clist 接口连通性诊断（host 差异）')
    print('=' * 60)

    print('\n[A] 80.push2.eastmoney.com（出问题的子域）:')
    print(f'    -> {test_clist_80()}')

    print('\n[B] push2.eastmoney.com（无前缀，候选修复）:')
    print(f'    -> {test_clist_push2()}')

    # 此后 import app 会安装全局补丁（含 host 重写）
    import app  # noqa: F401  (触发 install_requests_patch)

    print('\n[C] 真实 akshare（全局 host 重写生效后）:')
    print(f'    -> {test_akshare_with_patch()}')

    print('\n' + '=' * 60)
    print('判读:')
    print('  - A 失败 / B 成功  -> 确认是 80.push2 子域问题；全局补丁已重写，C 应转 OK')
    print('  - A 与 B 都失败    -> 不是子域问题，是出口 IP 被东财按 IP 封（含代理也不行），')
    print('                        需代理轮转或更换数据源（akshare 官方建议采购东财 Choice 等）')
    print('=' * 60)


if __name__ == '__main__':
    main()
