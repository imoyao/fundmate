"""
天天基金网数据获取
"""
import json
import re
from pathlib import Path
from typing import Union

import dateparser
import requests
from requests import Response
from xalpha.cons import rget

from backend.fundmate.data import utils as dt_utils
from backend.fundmate.fund.models import FundCompany, FundVariety

current_path = Path.cwd()
FUND_FP = f'{str(current_path)}/fund.json'
REQUEST_STR = '''Accept: */*
Accept-Encoding: gzip, deflate
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7
Connection: keep-alive
Cookie: AUTH_FUND.EASTMONEY.COM_GSJZ=AUTH*TTJJ*TOKEN; qgqp_b_id=2fae24fc6356487426dbc8cdfeddb553; searchbar_code=519736; Eastmoney_Fund_Transform=true; Eastmoney_Fund=160222; _qddaz=QD.shtanj.nfcxlq.kpzap3pv; EMFUND0=06-01%2010%3A51%3A26@%23%24%u4EA4%u94F6%u5B9A%u671F%u652F%u4ED8%u53CC%u606F%u5E73%u8861%u6DF7%u5408@%23%24519732; EMFUND1=06-01%2017%3A34%3A55@%23%24%u6C47%u6DFB%u5BCC%u4E2D%u8BC1%u4E3B%u8981%u6D88%u8D39ETF@%23%24159928; EMFUND2=06-01%2017%3A44%3A26@%23%24%u666F%u987A%u957F%u57CE%u7EE9%u4F18%u6210%u957F%u6DF7%u5408@%23%24007412; EMFUND3=06-01%2018%3A02%3A11@%23%24%u56FD%u6CF0%u56FD%u8BC1%u98DF%u54C1%u996E%u6599%u884C%u4E1A%28LOF%29@%23%24160222; EMFUND4=06-02%2016%3A45%3A24@%23%24%u6613%u65B9%u8FBE%u5929%u5929%u7406%u8D22%u8D27%u5E01A@%23%24000009; EMFUND5=06-08%2009%3A56%3A58@%23%24%u5E73%u5B89%u4E2D%u8BC1%u755C%u7267%u517B%u6B96ETF@%23%24516760; EMFUND6=06-08%2009%3A57%3A06@%23%24%u56FD%u6CF0%u4E2D%u8BC1%u755C%u7267%u517B%u6B96ETF@%23%24159865; EMFUND7=06-15%2018%3A30%3A30@%23%24%u534E%u590F%u6210%u957F%u6DF7%u5408@%23%24000001; EMFUND8=06-16%2017%3A27%3A55@%23%24%u94F6%u534E%u65E5%u5229B@%23%24003816; EMFUND9=06-22 13:26:06@#$%u4E2D%u6B27%u65F6%u4EE3%u667A%u6167%u6DF7%u5408A@%23%24005241; cowCookie=true; st_si=01667893795829; st_pvi=80465927611178; st_sp=2021-05-29%2010%3A44%3A08; st_inirUrl=https%3A%2F%2Fwww.baidu.com%2Flink; st_sn=1; st_psi=202106241712486-113300301036-4785882081; st_asi=delete; ASP.NET_SessionId=qndvon01q0acgvbe52lzhu0g
DNT: 1
Host: fund.eastmoney.com
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36 Edg/91.0.864.54
'''


class EastMoney:
    """
    天天基金网数据接口
    """
    headers = dt_utils.parse_headers(REQUEST_STR)

    def match_resp(self, resp: Response, regexp: re.Pattern) -> re.Match:
        """
        对字符进行正则匹配获取匹配结果
        :param resp: 
        :param regexp: 
        :return: 
        """
        ret_str = resp.content.decode('utf-8')
        reg_mat = regexp.match(ret_str)
        return reg_mat

    def company(self, save: bool = False):
        """
        基金公司入库
        原始链接：[基金公司一览表 _ 天天基金网](http://fund.eastmoney.com/company/default.html)
        api: http://fund.eastmoney.com/Data/FundRankScale.aspx
        :return: list,
        编号  基金公司   成立时间   全部基金数  总经理  短拼 全部管理规模(亿元) 天相评级    简称    update_time
        ['80000080', '山西证券股份有限公司', '1988-07-28', '16', '王怡里', 'SXZQ', '', '85.97', '★★★', '山西证券', '', '2021/3/31 0:00:00']
        原始链接：[['80000080', '山西证券股份有限公司', '1988-07-28', '16', '王怡里', 'SXZQ', '', '85.97', '★★★', '山西证券', '', '2021/3/31 0:00:00'], ['80000095', '国都证券股份有限公司', '2001-12-28', '4', '韩本毅', 'GDZQ', '', '3.18', '★★★', '国都证券', '', '2021/3/31 0:00:00']

        """
        fund_comp_url = 'http://fund.eastmoney.com/Data/FundRankScale.aspx'
        resp = requests.get(fund_comp_url, headers=self.headers)
        regex = re.compile(r'.*var.*json.*=.*datas:(.*)}')
        reg_mat = self.match_resp(resp, regex)

        if reg_mat:
            fund_comps_str = reg_mat.groups()[0]
            # print(fund_comps_str)
            '''
            see also:   https://stackoverflow.com/a/50257217
            '''
            p = re.compile('(?<!\\\\)\'')
            load_able_str = p.sub('\"', fund_comps_str)
            comps = json.loads(load_able_str)
            if save:
                for cop in comps:
                    converted_cop = [
                        str(item) or None if isinstance(item, str) else item
                        for item in cop
                    ]
                    comp_info = dict(
                        zip([
                            'code', 'full_name', 'create_date', 'f_counts',
                            'mgr', 'dpy', 'a_un', 'scale', 'tx_eval', 'name',
                            'b_un', 'update_time'
                        ], converted_cop))
                    level_eval = comp_info.get('tx_eval', '')
                    if level_eval:
                        level = len(level_eval)
                    else:
                        level = None

                    comp_info['tx_eval'] = level
                    # 两个不知道含义的暂时pop
                    comp_info.pop('a_un')
                    comp_info.pop('b_un')
                    code = comp_info.get('code')
                    comp = FundCompany()
                    query_info = {'code': code}
                    comp.insert_or_update(query_info, **comp_info)
            return comps

    def fund(self) -> Union[str, None]:
        """
        从网站获取基金信息
        :return:str,[["000001","HXCZHH","华夏成长混合","混合型","HUAXIACHENGZHANGHUNHE"],["000002","HXCZHH","华夏成长混合(后端)","混合型","HUAXIACHENGZHANGHUNHE"],["000003","ZHKZZZQA","中海可转债债券A","债券型","ZHONGHAIKEZHUANZHAIZHAIQUANA",...]]
        """
        fund_code_search_url = 'http://fund.eastmoney.com/js/fundcode_search.js'
        resp = requests.get(fund_code_search_url, headers=self.headers)
        regex = re.compile(r'.+var\s*r\s*=\s*(.+);')
        reg_mat = self.match_resp(resp, regex)

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
        """
        保存到数据库
        TODO:该接口没有完成
        :return:
        """
        funds = em.fund()
        fund_list = json.loads(funds)
        fd_types = self.fund_types(fund_list)
        type_map = dict()
        for ft in fd_types:
            _info = {'name': ft}
            f_tp = FundVariety.create(**_info)
            type_id = f_tp.id
            type_map[ft] = type_id
        # TODO:将基金信息写入fund表
        for f in fund_list:
            # ["000001","HXCZHH","华夏成长混合","混合型","HUAXIACHENGZHANGHUNHE"]
            code, szm, name, f_type_name, qpy = f
            tp_id = type_map.get(f_type_name)
            info = {
                'name': name,
                'qxpy': qpy,
                'fund_code': code,
                'f_var': int(tp_id),
            }

        return 0

    # TODO: 正则可以封装
    def t_days(self, f_code: str):
        """
        获取t+n中的n是几，一般为1
        :param f_code:
        :return:
        """
        resp = rget(
            f'http://fund.eastmoney.com/tools/DataHandler.aspx?t=t&ib=1&fc={f_code}'
        )
        regex = re.compile(r'.*={\s.*:"(\d)"};')
        reg_mat = self.match_resp(resp, regex)
        if reg_mat:
            fund_day = int(reg_mat.groups()[0])
            return fund_day

    def trade_date(self,
                   f_code: Union[str, int],
                   t_num: Union[None, int] = 1,
                   record_date: Union[None, str] = None) -> Union[dict, None]:
        """
        url: http://fund.eastmoney.com/tools/jiaoyiri.html
        api: http://fund.eastmoney.com/tools/DataHandler.aspx?t=confirm&date=2021-06-24&days=1&after=1
        选择交易类型：买基金 卖基金
        选择基金：
        请输入基金代码、名称或简拼
        所选基金的确认日：T+1什么是T日？
        选择交易申请时间：
        :return:
        {'WorkDate': '2021-06-18',
         'Maturity': '2021-06-21',  # 基金确认日
         'deadline': '2021-06-21',
         'is_same': True        #是否与申请日在同一交易日
         }
        """
        if not t_num:
            t_num = self.t_days(f_code)

        parse_ret = dateparser.parse(record_date)
        _date = parse_ret.date()
        # 是否为15:00之后
        after_15_flag = int(parse_ret.hour >= 15)
        resp = rget(
            f'http://fund.eastmoney.com/tools/DataHandler.aspx?t=confirm&date={_date}&days={t_num}&after={after_15_flag}',
            headers=self.headers)
        regex = re.compile(
            r'.*={\s(.*):"(.*)",(.*):"(.*)",(.*):"(.*)",(.*):"(.*)"};')
        reg_mat = self.match_resp(resp, regex)
        if reg_mat:
            info = reg_mat.groups()
            # [python - Pythonic way to turn a list of strings into a dictionary with the odd-indexed strings as keys
            # and even-indexed ones as values? - Stack Overflow](
            # https://stackoverflow.com/questions/3303213/pythonic-way-to-turn-a-list-of-strings-into-a-dictionary
            # -with-the-odd-indexed-st) data = dict(zip(info[::2], info[1::2]))
            '''
            ('WorkDate', '2021-06-18', 'IsSame', '1', 'Maturity', '2021-06-21', 'deadline', '2021/06/21')
            
            {'WorkDate': '2021-06-18', 'IsSame': '1', 'Maturity': '2021-06-21', 'deadline': '2021-06-21', 'is_same': 
            True} 

            '''

            data = dict(zip(*[iter(info)] * 2))
            data['deadline'] = str(
                dateparser.parse(data.get('deadline')).date())
            is_same = data.pop('IsSame')
            data['is_same'] = bool(int(is_same))
            return data


em = EastMoney()

if __name__ == '__main__':
    # ret = em.company(save=True)
    ret = em.trade_date('005491', t_num=None, record_date='2021-06-18')
    print(ret)
