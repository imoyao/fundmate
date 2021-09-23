#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/5/31 11:47
"""
基金销售机构信息
"""

from xalpha.cons import rget_json

from backend.fundmate.data import utils as db_utils
from backend.fundmate.fund.models import FundSaleOrg

HEADERS_STR = '''Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9
Accept-Encoding: gzip, deflate, br
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7
Cache-Control: max-age=0
Connection: keep-alive
Cookie: Hm_lvt_a0d0f99af80247cfcb96d30732a5c560=1622256421
DNT: 1
Host: www.amac.org.cn
sec-ch-ua: " Not;A Brand";v="99", "Microsoft Edge";v="91", "Chromium";v="91"
sec-ch-ua-mobile: ?0
Sec-Fetch-Dest: document
Sec-Fetch-Mode: navigate
Sec-Fetch-Site: none
Sec-Fetch-User: ?1
Upgrade-Insecure-Requests: 1
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36 Edg/91.0.864.41
'''

# 对一些常用平台，设置简称，方便用户查找
USUAL_SALE_COMPS = {'1619': '蚂蚁财富（支付宝）', '1615': '天天基金', '1730': '腾讯腾安（理财通）', '1701': '蛋卷基金', '1686': '盈米/且慢'}


def agency_info() -> list:
    """
    获取公募基金销售机构
    :return:
    """
    url = 'https://www.amac.org.cn/portal/front/infopublic/fsAgencyAnno/findFsAgencyAnnos'
    headers = db_utils.parse_headers(HEADERS_STR)
    resp = rget_json(url, headers=headers)
    size = 50
    org_info = list()
    if resp.get('code') == 200:
        data_counts = resp.get('data').get('data').get('total')
        for page, size in db_utils.paginate(data_counts, size=size):
            params = {'pageNo': page, 'pageSize': size}
            resp = rget_json(url, headers=headers, params=params)
            agent_infos = resp.get('data').get('data').get('dataList')
            for org in agent_infos:
                # {"id":1307,"orgName":"中国工商银行","regAddr":"北京市西城区复兴门内大街55号","orgType":"全国性商业银行","checkTime":"2001-08"}
                val = org.values()
                org_id = org.get('id')
                key = ['org_id', 'name', 'addr', 'org_type', 'date']
                info = dict(zip(key, val))
                query_info = {'org_id': org_id}
                # 对一些常见的基金公司进行特殊化处理
                id2str = str(org_id)
                if id2str in USUAL_SALE_COMPS.keys():
                    _known_name = USUAL_SALE_COMPS.get(id2str)
                    info.update({'known_name': _known_name})
                # 插入和更新
                org_info.append(info)
                FundSaleOrg.insert_or_update(query_info, **info)

    return org_info


if __name__ == '__main__':
    agency_info()
