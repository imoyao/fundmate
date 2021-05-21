"""
天天基金网数据获取
"""
# from xalpha.cons import rget
import re
import json
import requests
from pathlib import Path
from typing import Union

from backend.fundmate.fund.models import FundVariety,FundCompany

current_path = Path.cwd()
FUND_FP = f'{str(current_path)}/fund.json'


class EastMoney:
    """
    天天基金网数据接口
    """
    headers = {
        'Host': 'fund.eastmoney.com',
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
        'DNT': '1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36 Edg/90.0.818.62',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7',
        'Cookie': r'''EMFUND1=null; EMFUND2=null; EMFUND3=null; AUTH_FUND.EASTMONEY.COM_GSJZ=AUTH*TTJJ*TOKEN; qgqp_b_id=2fae24fc6356487426dbc8cdfeddb553; searchbar_code=519736; st_si=23873780538141; st_asi=delete; ASP.NET_SessionId=dv5gulrkndic0z0ip0b4wdd4; EMFUND0=null; EMFUND4=04-16%2013%3A25%3A53@%23%24%u6613%u65B9%u8FBE%u5B89%u5FC3%u56DE%u9988%u6DF7%u5408@%23%24001182; EMFUND5=04-30%2013%3A29%3A08@%23%24%u4E2D%u6B27%u6210%u957F%u4F18%u9009%u6DF7%u5408A@%23%24166020; EMFUND6=05-10%2014%3A57%3A45@%23%24%u6CD3%u5FB7%u81F4%u8FDC%u6DF7%u5408A@%23%24004965; EMFUND7=05-14%2011%3A20%3A28@%23%24%u4EA4%u94F6%u5B9A%u671F%u652F%u4ED8%u53CC%u606F%u5E73%u8861%u6DF7%u5408@%23%24519732; EMFUND8=05-14%2011%3A29%3A03@%23%24%u4EA4%u94F6%u65B0%u6210%u957F%u6DF7%u5408@%23%24519736; EMFUND9=05-19 17:03:21@#$%u4EA4%u94F6%u65B0%u751F%u6D3B%u529B%u7075%u6D3B%u914D%u7F6E%u6DF7%u5408@%23%24519772; st_pvi=35721327938445; st_sp=2021-04-16%2013%3A25%3A56; st_inirUrl=https%3A%2F%2Fcn.bing.com%2F; st_sn=10; st_psi=20210521133742304-112200312945-5083695404''',
        'If-None-Match': "60a5b2d7-133df4"
    }

    def company(self, save: bool = False):
        """
        原始链接：[基金公司一览表 _ 天天基金网](http://fund.eastmoney.com/company/default.html)
        api: http://fund.eastmoney.com/Data/FundRankScale.aspx
        :return: list,
        编号  基金公司   成立时间   全部基金数  总经理  短拼 全部管理规模(亿元) 天相评级    简称    update_time
        ['80000080', '山西证券股份有限公司', '1988-07-28', '16', '王怡里', 'SXZQ', '', '85.97', '★★★', '山西证券', '', '2021/3/31 0:00:00']
        原始链接：[['80000080', '山西证券股份有限公司', '1988-07-28', '16', '王怡里', 'SXZQ', '', '85.97', '★★★', '山西证券', '', '2021/3/31 0:00:00'], ['80000095', '国都证券股份有限公司', '2001-12-28', '4', '韩本毅', 'GDZQ', '', '3.18', '★★★', '国都证券', '', '2021/3/31 0:00:00']

        """
        fund_comp_url = 'http://fund.eastmoney.com/Data/FundRankScale.aspx'
        resp = requests.get(fund_comp_url, headers=self.headers)
        ret_str = resp.content.decode('utf-8')
        regex = re.compile(r'.*var.*json.*=.*datas:(.*)}')
        reg_mat = regex.match(ret_str)

        if reg_mat:
            fund_comps_str = reg_mat.groups()[0]
            # print(fund_comps_str)
            '''
            see also:   https://stackoverflow.com/a/50257217
            '''
            p = re.compile('(?<!\\\\)\'')
            load_able_str = p.sub('\"', fund_comps_str)
            # print(load_able_str,'====1111=====')
            comps = json.loads(load_able_str)
            if save:
                for cop in comps:
                    comp_info = dict(
                        zip(['code', 'full_name', 'create_date', 'f_counts', 'mgr', 'dpy', 'a_un', 'scale', 'tx_eval',
                             'name', 'b_un', 'update_time'], cop))
                    level = len(comp_info.get('tx_eval'))
                    comp_info['tx_eval'] = level
                    comp_info.pop('a_un')
                    comp_info.pop('b_un')
                    FundCompany.create(**comp_info)

            return comps

    def fund(self) -> Union[str, None]:
        """
        从网站获取基金信息
        :return:str,[["000001","HXCZHH","华夏成长混合","混合型","HUAXIACHENGZHANGHUNHE"],["000002","HXCZHH","华夏成长混合(后端)","混合型","HUAXIACHENGZHANGHUNHE"],["000003","ZHKZZZQA","中海可转债债券A","债券型","ZHONGHAIKEZHUANZHAIZHAIQUANA",...]]
        """
        fund_code_search_url = 'http://fund.eastmoney.com/js/fundcode_search.js'
        resp = requests.get(fund_code_search_url, headers=self.headers)
        ret_str = resp.content.decode('utf-8')
        regex = re.compile(r'.+var\s*r\s*=\s*(.+);')
        reg_mat = regex.match(ret_str)

        if reg_mat:
            fund_info = reg_mat.groups()[0]
            return fund_info

    def save_to_json(self):
        """
        将获取数据保存为json
        :return:
        """
        ret_code = 1
        _info = self.fund()
        if _info:
            with open(FUND_FP, 'w') as f:
                json.dump(_info, f)
                ret_code = 0
        return ret_code

    def fund_types(self, fund_list: list) -> set:
        """
        获取所有基金类别
        :return:set, {'货币型', 'QDII', '股票-FOF', 'ETF-场内', 'QDII-指数', '股票指数', '混合型', '债券型', '理财型', '混合-FOF', '股票型', '联接基金', 'QDII-ETF', '债券指数', '定开债券'}
        """
        fund_type_set = set()
        for f in fund_list:
            fund_type_set.add(f[3])
        return fund_type_set

    def save_to_db(self):
        funds = em.fund()
        fund_list = json.loads(funds)
        fd_types = self.fund_types(fund_list)
        type_map = dict()
        for ft in fd_types:
            _info = {'name': ft}
            f_tp = FundVariety.create(**_info)
            type_id = f_tp.id
            type_map[ft] = type_id
        for f in fund_list:
            # ["000001","HXCZHH","华夏成长混合","混合型","HUAXIACHENGZHANGHUNHE"]
            code, szm, name, f_type_name, qpy = f
            tp_id = type_map.get(f_type_name)
            info = {'name': name, 'qxpy': qpy, 'fund_code': code, 'f_var': int(tp_id), }

        return 0


em = EastMoney()

if __name__ == '__main__':
    ret = em.company(save=True)
    print(ret)
