# -*- coding: utf-8 -*-
"""
@Time ： 2022/12/14 9:19
@File ：products.py
@IDE ：PyCharm
https://github.com/scuthls/XiaoAn/blob/master/KnowledgeGraph/product_crawler.py
理财产品数据爬取
ref：https://www.chinawealth.com.cn/zzlc/jsp/lccp.jsp
"""
from typing import Optional

import pandas as pd
from xalpha.cons import rget_json

from backend.fundmate.data.utils import base as dt_utils
from backend.fundmate.types import PdDataFrame


header_str = '''Accept: application/json, text/javascript, */*; q=0.01
Accept-Encoding: gzip, deflate, br
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6
Connection: keep-alive
Content-Type: application/x-www-form-urlencoded; charset=utf-8
Cookie: BIGipServerPool_SuperFusion_LiCai_Nginx_8080=!9fIxmrUnfd0zjdsiAKtAGV98KdD1h8XCUTw2ahBgt/Vuh8ORwP4ttVoTyOB\
9O54xgreEWk+eIFS68hU=; BIGipServerPool_SuperFusion_LiCai_fe_8080=2751725846.36895.0000; \
_pk_id.3.8bc7=8827e4f04ea558fb.1670939625.1.1670939632.1670939625.; \
JSESSIONID=DF7063EEFD1E13BFF1B241A202B3F75B; _pk_id.12.8bc7=9d630d359c09735f.1670939633.3.1671002096.1671002096.;\
 _pk_ses.12.8bc7=*; count=1
DNT: 1
Host: www.chinawealth.com.cn
Referer: https://www.chinawealth.com.cn/zzlc/jsp/lccp.jsp
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 \
Safari/537.36 Edg/108.0.1462.46
X-Requested-With: XMLHttpRequest
sec-ch-ua: "Not?A_Brand";v="8", "Chromium";v="108", "Microsoft Edge";v="108"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "Windows"
'''


class ChinaWealth:
    base_url = 'https://www.chinawealth.com.cn/LcSolrSearch.go'
    dept_url = 'https://www.chinawealth.com.cn/dmmsQuery.go?code=0'

    def agencies(self) -> Optional[PdDataFrame]:
        """
        理财产品发行机构
        :return:
        """
        hd = dt_utils.parse_headers(header_str)
        resp = rget_json(self.dept_url, headers=hd)
        if resp:
            _result = pd.DataFrame(resp)
        else:
            _result = None
        return _result

    def products(self):
        """
        理财产品
        :return:
        """
        # FIXME: 需要兼容
        '''

        (['03', '05', '01', '02', '04'],
          ['一般个人客户', '高资产净值客户',
           '私人银行客户专属', '机构客户专属',
           '金融同业客户专属'])
           (['01', '02', '03', '04', '05', '06', '10'],
      ['国有银行', '股份制银行', '城商行', '外资银行',
       '农村合作金融机构', '理财子公司', '其他'])

       areadata = {"": [{'name': '全国', 'code': '000000'}, {'name': '不限', 'code': 'NA'}],
                    "A-F": [{'name': '澳门', 'code': '820000'}, {'name': '安徽', 'code': '340000'},
                            {'name': '北京', 'code': '110000'}, {'name': '重庆', 'code': '500000'},
                            {'name': '大连', 'code': '210200'}, {'name': '福建', 'code': '350000'}],
                    "G": [{'name': '甘肃', 'code': '620000'}, {'name': '广东', 'code': '440000'},
                          {'name': '广西', 'code': '450000'}, {'name': '贵州', 'code': '520000'}],
                    "H": [{'name': '河南', 'code': '410000'}, {'name': '河北', 'code': '130000'},
                          {'name': '湖南', 'code': '430000'}, {'name': '湖北', 'code': '420000'},
                          {'name': '黑龙江', 'code': '230000'}, {'name': '海南', 'code': '460000'}],
                    "J-N": [{'name': '吉林', 'code': '220000'}, {'name': '辽宁', 'code': '210000'},
                            {'name': '江苏', 'code': '320000'}, {'name': '江西', 'code': '360000'},
                            {'name': '宁波', 'code': '330200'}, {'name': '内蒙古', 'code': '150000'},
                            {'name': '宁夏', 'code': '640000'}],
                    "Q-S": [{'name': '上海', 'code': '310000'}, {'name': '山东', 'code': '370000'},
                            {'name': '山西', 'code': '140000'}, {'name': '深圳', 'code': '440300'},
                            {'name': '四川', 'code': '510000'}, {'name': '青岛', 'code': '370200'},
                            {'name': '青海', 'code': '630000'}, {'name': '陕西', 'code': '610000'},
                            {'name': '其他国家或地区', 'code': '900000'}],
                    "T-Z": [{'name': '天津', 'code': '120000'}, {'name': '台湾', 'code': '710000'},
                            {'name': '浙江', 'code': '330000'}, {'name': '厦门', 'code': '350200'},
                            {'name': '云南', 'code': '530000'}, {'name': '新疆', 'code': '650000'},
                            {'name': '香港', 'code': '810000'}, {'name': '西藏', 'code': '540000'}]}
        '''
        rename_columns = {
            'cpdjbm': '登记编码',
            'cpid': '产品ID',
            'cpms': '产品名称',
            'qxms': '期限模式',
            'cplxms': '运作模式',
            'qxdm': '期限代码',
            'mjjsrq': '募集结算日期',
            'yjbjjzlast': '业绩比较基准最新',
            'cptzxzms': '投资性质',
            'yjbjjzxx': '业绩比较基准下限',
            'yjbjjz': '业绩比较基准',
            'yjbjjzsx': '业绩比较基准上限',
            'yjbjjzsm': '业绩比较基准说明',
            'cptssx': '产品特殊属性',
            'cptzxz': '投资性质编号',
            'fxjgms': '发行机构',
            'fxjgdm': '发行机构代码',
            'mjfsms': '募集方式',
            'cpyzmsms': '运作模式',
            'tzzlxdm': '产品类别代码',
            'mjbz': '募集币种',
            'cpfxdj': '风险等级编号',
            'fxdjms': '风险等级',
            'mjqsrq': '募集起始日期',
            'cpqsrq': '产品起始日期',
            'cpyjzzrq': '产品终止日期',
            'cpztms': '产品状态',
            'cpzt': '产品状态编号',
            'kfzqqsr': '业务起始日',
            'kfzqjsr': '业务结束日',
            'cpqx': '实际天数',
            'csjz': '初始净值',
            'cpjz': '产品净值',
            'ljjz': '累计净值',
            'syl': '最近一次兑付收益率',
            'cpsylxms': '收益类型',
            'tzlxms': '投资资产类型',
            'yjkhzgnsyl': '预期最高收益率',
            'yjkhzdnsyl': '预期最低收益率',
            'cpxsqy': '产品销售区域',
            'cpjglb': '机构类别',
            'qdxsjef': '认购价格'}
        hd = dt_utils.parse_headers(header_str)
        resp = rget_json(self.base_url, headers=hd)
        if resp:
            resp_list = resp.get('List')
            if isinstance(resp_list, list):
                _result = pd.DataFrame(resp_list)
                _result.drop(columns='copy', inplace=True)
                _result.rename(columns=rename_columns, inplace=True)
                _result.to_excel('product.xlsx', index=False)
            else:
                _result = None
        else:
            _result = None
        return _result


if __name__ == '__main__':
    cw = ChinaWealth()
    result = cw.agencies()
    result_prod = cw.products()
    print(result)
    print(result_prod)
