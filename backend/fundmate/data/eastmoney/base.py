"""
天天基金网数据获取
"""
import json
import re
from pathlib import Path
from typing import Union

import dateparser
import pyjson5
import requests
from requests import Response
from xalpha.cons import rget

from backend.fundmate.data import utils as dt_utils
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import Fund, FundCompany, FundType, FundVariety

current_path = Path.cwd()
REQUEST_STR = '''Accept: */*
Accept-Encoding: gzip, deflate
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7
Connection: keep-alive
Cookie: AUTH_FUND.EASTMONEY.COM_GSJZ=AUTH*TTJJ*TOKEN; qgqp_b_id=2fae24fc6356487426dbc8cdfeddb553; searchbar_code=519736; Eastmoney_Fund_Transform=true; Eastmoney_Fund=160222; _qddaz=QD.shtanj.nfcxlq.kpzap3pv; EMFUND0=06-01%2010%3A51%3A26@%23%24%u4EA4%u94F6%u5B9A%u671F%u652F%u4ED8%u53CC%u606F%u5E73%u8861%u6DF7%u5408@%23%24519732; EMFUND1=06-01%2017%3A34%3A55@%23%24%u6C47%u6DFB%u5BCC%u4E2D%u8BC1%u4E3B%u8981%u6D88%u8D39ETF@%23%24159928; EMFUND2=06-01%2017%3A44%3A26@%23%24%u666F%u987A%u957F%u57CE%u7EE9%u4F18%u6210%u957F%u6DF7%u5408@%23%24007412; EMFUND3=06-01%2018%3A02%3A11@%23%24%u56FD%u6CF0%u56FD%u8BC1%u98DF%u54C1%u996E%u6599%u884C%u4E1A%28LOF%29@%23%24160222; EMFUND4=06-02%2016%3A45%3A24@%23%24%u6613%u65B9%u8FBE%u5929%u5929%u7406%u8D22%u8D27%u5E01A@%23%24000009; EMFUND5=06-08%2009%3A56%3A58@%23%24%u5E73%u5B89%u4E2D%u8BC1%u755C%u7267%u517B%u6B96ETF@%23%24516760; EMFUND6=06-08%2009%3A57%3A06@%23%24%u56FD%u6CF0%u4E2D%u8BC1%u755C%u7267%u517B%u6B96ETF@%23%24159865; EMFUND7=06-15%2018%3A30%3A30@%23%24%u534E%u590F%u6210%u957F%u6DF7%u5408@%23%24000001; EMFUND8=06-16%2017%3A27%3A55@%23%24%u94F6%u534E%u65E5%u5229B@%23%24003816; EMFUND9=06-22 13:26:06@#$%u4E2D%u6B27%u65F6%u4EE3%u667A%u6167%u6DF7%u5408A@%23%24005241; cowCookie=true; st_si=01667893795829; st_pvi=80465927611178; st_sp=2021-05-29%2010%3A44%3A08; st_inirUrl=https%3A%2F%2Fwww.baidu.com%2Flink; st_sn=1; st_psi=202106241712486-113300301036-4785882081; st_asi=delete; ASP.NET_SessionId=qndvon01q0acgvbe52lzhu0g
DNT: 1
Host: fund.eastmoney.com
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36 Edg/91.0.864.54
'''  # noqa: F501


class EastMoney:
    """
    天天基金网数据接口
    """
    headers = dt_utils.parse_headers(REQUEST_STR)

    @staticmethod
    def match_resp(resp: Response, regexp: re.Pattern) -> re.Match:
        """
        对字符进行正则匹配获取匹配结果
        :param resp:
        :param regexp:
        :return:
        """
        ret_str = resp.content.decode('utf-8')
        reg_mat = regexp.match(ret_str)
        return reg_mat

    def fetch_mgr(self, fund_mgr_url: str) -> Union[dict, None]:
        resp = rget(url=fund_mgr_url, headers=self.headers)
        regex = re.compile(r'var\s*returnjson\s*=\s*(.+)')
        reg_mat = self.match_resp(resp, regex)
        if reg_mat:
            _fund_mgr_info = reg_mat.groups()[0]
            fund_mgr_info = pyjson5.loads(_fund_mgr_info)

            return fund_mgr_info

    def left_page_data(self, fund_mgr_info):
        """
        从第二页开始，for循环爬取信息
        """
        page_size = fund_mgr_info.get('pages')
        pages_data = fund_mgr_info.get('data')
        for page in range(2, page_size):
            _fund_mgr_url = f'http://fund.eastmoney.com/Data/FundDataPortfolio_Interface.aspx?dt=14&mc=returnjson&ft=all&pn=50&pi={page}&sc=abbname&st=asc'
            resp = self.fetch_mgr(_fund_mgr_url)
            per_page_data = resp.get('data')
            pages_data.extend(per_page_data)

        return pages_data

    def remove_specific_str(self, percent_str: str, replace_str: str) -> float:
        """
        删除多余的描述符，只保存有意义的数字
        88% -> 88.00
        88亿元 -> 88.00
        """
        assert percent_str.endswith(replace_str)
        return float(f'{percent_str.replace(replace_str, ""):.2f}')

    def mgr(self,
            save: bool = False,
            format_: str = 'sql') -> Union[str, None]:
        """
        获取基金经理信息
        数据来源：[基金经理 _ 天天基金网](http://fund.eastmoney.com/manager/default.html#dt14;mcreturnjson;ftall;pn50;pi2;scabbname;stasc)
        """
        fund_mgr_url = 'http://fund.eastmoney.com/Data/FundDataPortfolio_Interface.aspx?dt=14&mc=returnjson&ft=all&pn=50&pi=1&sc=abbname&st=asc'
        first_page_info = self.fetch_mgr(fund_mgr_url)
        fund_mgr_info = self.left_page_data(first_page_info)
        '''
        基金经理编码 姓名	公司编码 公司名称 现任基金编码 现任基金名称	累计从业时间（天） 现任基金最佳回报 基金编码 基金名称 现任基金资产总规模
        ['30634044', '艾定飞', '80053204', '华商基金', '007685,007853', '华商电子行业量化股票,华商计算机行业量化股票', '981', '105.41%', '007685', '华商电子行业量化股票', '5.74亿元', '105.41%']
        '''
        for mgr_item in fund_mgr_info:
            mgr_id, mgr_name, cmp_id, _, mgr_fd, _, work_days, _best_rt, best_fd, _, _sum_scale, _ = mgr_item
            mgr_fd_list = mgr_fd.split(',')
            best_rt = self.remove_specific_str(_best_rt, "%")
            sum_scale = self.remove_specific_str(_sum_scale, "亿元")
            for f_code in mgr_fd_list:
                fund_id = Fund.id_by_code(f_code)
                # TODO: 保存基金经理对应关系
        if save:
            pass

        return fund_mgr_info


def company(self, save: bool = False):
    """
    获取基金公司信息

    原始链接：[基金公司一览表 _ 天天基金网](http://fund.eastmoney.com/company/default.html) api:
    http://fund.eastmoney.com/Data/FundRankScale.aspx
    :return: list, 编号  基金公司   成立时间   全部基金数  总经理  短拼 全部管理规模(亿元)
    天相评级    简称    update_time ['80000080', '山西证券股份有限公司', '1988-07-28', '16', '王怡里', 'SXZQ', '', '85.97', '★★★',
    '山西证券', '', '2021/3/31 0:00:00'] 原始链接：[['80000080', '山西证券股份有限公司', '1988-07-28', '16', '王怡里', 'SXZQ', '',
    '85.97', '★★★', '山西证券', '', '2021/3/31 0:00:00'], ['80000095', '国都证券股份有限公司', '2001-12-28', '4', '韩本毅',
    'GDZQ', '', '3.18', '★★★', '国都证券', '', '2021/3/31 0:00:00']

    """
    fund_comp_url = 'http://fund.eastmoney.com/Data/FundRankScale.aspx'
    resp = requests.get(fund_comp_url, headers=self.headers)
    regex = re.compile(r'.*var.*json.*=.*datas:(.*)}')
    reg_mat = self.match_resp(resp, regex)

    if reg_mat:
        fund_comps_str = reg_mat.groups()[0]
        '''
        see also:   https://stackoverflow.com/a/50257217
        '''
        p = re.compile('(?<!\\\\)\'')
        load_able_str = p.sub('\"', fund_comps_str)
        comps = self.be_json(load_able_str)
        if save:
            for cop in comps:
                converted_cop = [
                    str(item) or None if isinstance(item, str) else item
                    for item in cop
                ]
                comp_info = dict(
                    zip([
                        'code', 'full_name', 'create_date', 'f_counts', 'mgr',
                        'dpy', 'a_un', 'scale', 'tx_eval', 'name', 'b_un',
                        'update_time'
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


def fund(self, save: bool = False, format_: str = 'sql') -> Union[str, None]:
    """
    获取基金信息

    :return:[["000001","HXCZHH","华夏成长混合","混合型","HUAXIACHENGZHANGHUNHE"],["000002","HXCZHH","华夏成长混合(后端)","混合型","HUAXIACHENGZHANGHUNHE"],["000003","ZHKZZZQA","中海可转债债券A","债券型","ZHONGHAIKEZHUANZHAIZHAIQUANA",...]]
    """
    fund_code_search_url = 'http://fund.eastmoney.com/js/fundcode_search.js'
    resp = rget(fund_code_search_url, headers=self.headers)
    regex = re.compile(r'.+var\s*r\s*=\s*(.+);')
    reg_mat = self.match_resp(resp, regex)

    if reg_mat:
        fund_info = reg_mat.groups()[0]
        ct = self.counts(fund_info)
        logger.info(f'Get {ct} funds from remote……')
        # 保存数据
        if save:
            _ret = self.do_save_action(format_, fund_info)
            # assert format_ in ['sql', 'json']
            # if format_ == 'sql':
            #     self.save_to_db(fund_info)
            # elif format_ == 'json':
            #     self.save_to_json(fund_info)

        return fund_info


def do_save_action(self, format_, save_data, suffix=None):
    """
    FIXME: 保存基金、基金经理、基金公司应该使用不同的前/后缀
    """
    assert format_ in ['sql', 'json']
    if format_ == 'sql':
        # TODO: 每个数据保存在不同的数据表中
        self.save_to_db(save_data)
    elif format_ == 'json':
        self.save_to_json(save_data, suffix=suffix)
    return 0


@staticmethod
def save_to_json(fund_info: str, suffix: Union[str, None] = None) -> int:
    """
    将获取数据保存为json
    :return:
    """
    ret_code = 1
    if fund_info:
        if suffix:
            f_name = '_'.join(['fund', suffix])
        else:
            f_name = 'fund'

        file_save_fp = f'{str(current_path)}/{f_name}.json'
        with open(file_save_fp, 'w') as f:
            json.dump(fund_info, f, ensure_ascii=False)
            ret_code = 0
    return ret_code


@staticmethod
def fund_types(fund_list: list) -> set:  # see also:NewDB.fund_type
    """
    获取所有基金类别 :return:set, {'货币型', 'QDII', '股票-FOF', 'ETF-场内', 'QDII-指数', '股票指数', '混合型', '债券型', '理财型', '混合-FOF',
    '股票型', '联接基金', 'QDII-ETF', '债券指数', '定开债券'}
    """
    fund_type_set = set()
    for f in fund_list:
        fund_type_set.add(f[3])
    return fund_type_set


@staticmethod
def be_json(_funds: str) -> list:
    """
    转为json
    """
    return json.loads(_funds, ensure_ascii=False)


def counts(self, funds_info: str) -> int:
    _fund_lists = self.be_json(funds_info)
    _count = len(_fund_lists)
    return _count


@staticmethod
def _split_fvt(f_vt_str: str) -> tuple:
    """
    >>> avt = '债券型-混合债'
    >>> avt.split('-')
    ['债券型', '混合债']
    """
    _ft = None
    if '-' in f_vt_str:
        _fv, _ft = f_vt_str.split('-')
    else:
        _fv = f_vt_str
    return _fv, _ft


def save_to_db(self, _funds: str) -> int:
    """
    保存fund信息到数据库
    :return:
    """

    if _funds:
        _fund_list = self.be_json(_funds)

        # 将基金信息更新/写入funds表
        type_map = dict()
        cache_fv_map = dict()
        _count = 0
        for f in _fund_list:
            # ["000001","HUZZAH","华夏成长混合","混合型","HUAXIACHENGZHANGHUNHE"]
            code, szm, name, _f_temp, qpy = f
            fv, ft = self._split_fvt(_f_temp)
            # 基金大类处理
            '''
            如果大类名称在缓存字典中，则直接获取，不去查数据库；
            否则，查询数据库，如果没有查到则创建，并更新缓存字典
            '''
            _fv_info = {'name': fv}
            if fv in cache_fv_map:
                _fv_id = cache_fv_map.get(fv)
            else:
                _fv_id = FundVariety.id_by_name(name=fv)
                if not _fv_id:
                    f_tp = FundVariety.create(**_fv_info)
                    _fv_id = f_tp.id
                cache_fv_map[fv] = _fv_id

            # 基金小类处理
            _ft_id = None
            if ft:
                _ft_info = {'name': ft}
                if ft in type_map:
                    _ft_id = type_map.get(ft)
                else:
                    _ft_id = FundType.id_by_name(ft)
                    # 父类关联写入
                    _ft_info['var_id'] = _fv_id
                    if not _ft_id:
                        f_tp = FundType.create(**_ft_info)
                        _ft_id = f_tp.id
                    type_map[ft] = _ft_id
            info = {
                'name': name,
                'sxszm': szm,
                'qxpy': qpy,
                'fund_code': code,
                'f_type': _ft_id if _ft_id else None,
                'f_var': _fv_id,
            }
            query_info = {'fund_code': code}
            _ret = Fund.insert_or_update(query_info, **info)
            logger.info(f'{_ret} create successful.')
            _count += 1
        fetch_count = len(_fund_list)
        if fetch_count == _count:
            logger.success(f'Update {fetch_count} of funds successful.')
        else:
            fail_count = fetch_count - _count
            logger.warning(f'Update {fail_count} of funds failed.')
        return 0
    else:
        logger.warning(
            'Get fund info error,can you connect to `http://fund.eastmoney.com/`?'
        )
        return 1


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
               t_num: Union[None, int] = None,
               record_date: Union[None, str] = None) -> Union[dict, None]:
    """
    交易日
    url: http://fund.eastmoney.com/tools/jiaoyiri.html
    api: http://fund.eastmoney.com/tools/DataHandler.aspx?t=confirm&date=2021-06-24&days=1&after=1
    :param f_code:基金编码
    :param t_num:基金为T+几
    :param record_date:记录日期，应该含有H:M:S,没有的话则认为是15点之前发起操作行为
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
        f'http://fund.eastmoney.com/tools/DataHandler.aspx?t=confirm&date={_date}&days={t_num}&after='
        f'{after_15_flag}',
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
        data['deadline'] = str(dateparser.parse(data.get('deadline')).date())
        is_same = data.pop('IsSame')
        data['is_same'] = bool(int(is_same))
        return data


def hold_split(self):
    """
    TODO:基金持有时间过短会收取高额的赎回费，所以我们需要增加功能以对持有进行分类
    [Python-Pandas之日期分组（将日期按照设定的组分为不同类型）_苏小败在路上-CSDN博客_pandas根据时间分组数据](https://blog.csdn.net/pz789as/article/details/106136141)
    :return:
    """
    pass


em = EastMoney()

if __name__ == '__main__':
    print(em.mgr())
    # funds = em.fund()
    # count = 0
    # if funds:
    #     fund_list = em.be_json(funds)
    #     print(fund_list, '===fund_list====')
    #     count = em.counts(funds)
    # print(funds, count)
