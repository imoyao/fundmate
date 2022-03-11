"""
天天基金网数据获取
"""
import json
import re
from pathlib import Path
from typing import Dict, Optional, Union

import numpy as np
import pandas as pd
import pyjson5
import requests
from requests import Response
from sqlalchemy.orm.exc import FlushError
from xalpha.cons import rget

from backend.fundmate import utils
from backend.fundmate.data.dkhs import jcb
from backend.fundmate.data.utils import base as dt_utils
from backend.fundmate.data.utils.base import data_parser
from backend.fundmate.database import db
from backend.fundmate.excepts import UnexpectedArgsError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import Fund, FundCompany, FundMgr, FundType, FundVariety, Mgr
from backend.fundmate.libs import convert

current_path = Path.cwd()  # TODO: 会保存到项目的根目录
REQUEST_STR = '''Accept: */*
Accept-Encoding: gzip, deflate
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7
Connection: keep-alive
Cookie: AUTH_FUND.EASTMONEY.COM_GSJZ=AUTH*TTJJ*TOKEN; qgqp_b_id=2fae24fc6356487426dbc8cdfeddb553; searchbar_code=519736; Eastmoney_Fund_Transform=true; Eastmoney_Fund=160222; _qddaz=QD.shtanj.nfcxlq.kpzap3pv; EMFUND0=06-01%2010%3A51%3A26@%23%24%u4EA4%u94F6%u5B9A%u671F%u652F%u4ED8%u53CC%u606F%u5E73%u8861%u6DF7%u5408@%23%24519732; EMFUND1=06-01%2017%3A34%3A55@%23%24%u6C47%u6DFB%u5BCC%u4E2D%u8BC1%u4E3B%u8981%u6D88%u8D39ETF@%23%24159928; EMFUND2=06-01%2017%3A44%3A26@%23%24%u666F%u987A%u957F%u57CE%u7EE9%u4F18%u6210%u957F%u6DF7%u5408@%23%24007412; EMFUND3=06-01%2018%3A02%3A11@%23%24%u56FD%u6CF0%u56FD%u8BC1%u98DF%u54C1%u996E%u6599%u884C%u4E1A%28LOF%29@%23%24160222; EMFUND4=06-02%2016%3A45%3A24@%23%24%u6613%u65B9%u8FBE%u5929%u5929%u7406%u8D22%u8D27%u5E01A@%23%24000009; EMFUND5=06-08%2009%3A56%3A58@%23%24%u5E73%u5B89%u4E2D%u8BC1%u755C%u7267%u517B%u6B96ETF@%23%24516760; EMFUND6=06-08%2009%3A57%3A06@%23%24%u56FD%u6CF0%u4E2D%u8BC1%u755C%u7267%u517B%u6B96ETF@%23%24159865; EMFUND7=06-15%2018%3A30%3A30@%23%24%u534E%u590F%u6210%u957F%u6DF7%u5408@%23%24000001; EMFUND8=06-16%2017%3A27%3A55@%23%24%u94F6%u534E%u65E5%u5229B@%23%24003816; EMFUND9=06-22 13:26:06@#$%u4E2D%u6B27%u65F6%u4EE3%u667A%u6167%u6DF7%u5408A@%23%24005241; cowCookie=true; st_si=01667893795829; st_pvi=80465927611178; st_sp=2021-05-29%2010%3A44%3A08; st_inirUrl=https%3A%2F%2Fwww.baidu.com%2Flink; st_sn=1; st_psi=202106241712486-113300301036-4785882081; st_asi=delete; ASP.NET_SessionId=qndvon01q0acgvbe52lzhu0g
DNT: 1
Host: fund.eastmoney.com
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36 Edg/91.0.864.54
'''  # noqa: E501


class BaseParse:

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


class EastMoney(BaseParse):
    """
    天天基金网数据接口
    """
    headers = dt_utils.parse_headers(REQUEST_STR)

    def fetch_mgr(self, fund_mgr_url: str) -> Union[object, dict, None]:
        resp = rget(url=fund_mgr_url, headers=self.headers)
        regex = re.compile(r'var\s*returnjson\s*=\s*(.+)')
        reg_mat = self.match_resp(resp, regex)
        if reg_mat:
            _fund_mgr_info = reg_mat.groups()[0]
            # 读取速度更快
            fund_mgr_info = pyjson5.loads(_fund_mgr_info)

            return fund_mgr_info

    def left_page_data(self, fund_mgr_info):
        """
        从第二页开始，for循环爬取信息
        """
        page_size = fund_mgr_info.get('pages')
        pages_data = fund_mgr_info.get('data')
        for page in range(2, page_size):
            _fund_mgr_url = f'http://fund.eastmoney.com/Data/FundDataPortfolio_Interface.aspx?dt=14&mc=returnjson&ft=all&pn=50&pi={page}&sc=abbname&st=asc'  # noqa: E501
            resp = self.fetch_mgr(_fund_mgr_url)
            per_page_data = resp.get('data')
            pages_data.extend(per_page_data)

        return pages_data

    @staticmethod
    def remove_specific_str(raw_str: str, replace_str: str) -> Union[float, None]:
        """
        删除多余的描述符，只保存有意义的数字
        88% -> 88.00
        88亿元 -> 88.00
        """
        try:
            assert raw_str.endswith(replace_str)
        except AssertionError:
            logger.warning(f'Please check your data:RAW_STR:{raw_str}, REPLACE_STR:{replace_str}.')
            if raw_str == '--':
                return None
        return float(f'{float(raw_str.replace(replace_str, "")):.2f}')

    def mgr(self, save: bool = False, format_: str = 'sql') -> Union[str, None]:
        """
        获取基金经理信息

        数据来源：[基金经理 _ 天天基金网](http://fund.eastmoney.com/manager/default.html#dt14;mcreturnjson;ftall;pn50;pi2;scabbname;stasc)
        """  # noqa: E501
        fund_mgr_url = 'http://fund.eastmoney.com/Data/FundDataPortfolio_Interface.aspx?dt=14&mc=returnjson&ft=all&pn=50&pi=1&sc=abbname&st=asc'  # noqa: E501
        first_page_info = self.fetch_mgr(fund_mgr_url)
        fund_mgr_info = self.left_page_data(first_page_info)
        '''
        基金经理编码 姓名	公司编码 公司名称 现任基金编码 现任基金名称	累计从业时间（天） 现任基金最佳回报 基金编码 基金名称 现任基金资产总规模
        ['30634044', '艾定飞', '80053204', '华商基金', '007685,007853', '华商电子行业量化股票,华商计算机行业量化股票', '981', '105.41%', '007685', '华商电子行业量化股票', '5.74亿元', '105.41%']
        '''  # noqa: E501
        if fund_mgr_info:
            if save:
                if format_ == 'sql':
                    ret = self.save_mgr_2db(fund_mgr_info)
                else:
                    # json或者csv保存
                    ret = self.do_save_action(format_, fund_mgr_info, suffix='mgr')
                if ret == 0:
                    logger.success(f'The fund mgr of {format_} format has been saved finished.')

        return fund_mgr_info

    def no_fresh_save_mgr(self):
        """
        从json文件中读取并直接存数据库
        """
        file_save_fp = f'{str(current_path)}/fund_mgr.json'
        fp = Path(file_save_fp)
        if fp.exists():
            mgr_data = data_parser.get_data_from_json(file_save_fp)
            self.save_mgr_2db(mgr_data)

    @staticmethod
    def subscription_period_fund(code: str, name: str) -> Fund:
        """
        TODO: 单独获取（新发）基金信息并保存
        """
        sample_fund = Fund.create(fund_code=code, name=name)
        return sample_fund

    def save_mgr_2db(self, fund_mgr_info: list):  # noqa: C901
        """
        将基金经理信息存入数据表MGRS,此外，还会将基金与基金经理关联起来，信息存入FUND_MGR中间表
        FIXME: 需要注意的是：有一部分基金是新发基金，这个时候funds表中是没有数据的，此时关联基金经理会报错：`FlushError: Can't flush None value found in collection Mgr.funds`，目前的解决方案是直接continue跳过这个数据的写入，后期可能需要优化流程，添加新发基金的信息爬取
        """  # noqa: E501
        for mgr_item in fund_mgr_info:
            mgr_code, mgr_name, cmp_code, cmp_name, mgr_fd, mgr_fn, work_days, \
            _best_rt, best_fd, _, _sum_scale, _ = mgr_item
            mgr_fd_list = mgr_fd.split(',')
            mgr_fn_list = mgr_fn.split(',')
            mgr_fd_map = dict(zip(mgr_fd_list, mgr_fn_list))
            best_rt = self.remove_specific_str(_best_rt, "%")
            sum_scale = self.remove_specific_str(_sum_scale, "亿元")

            mgr_query_info = {'mgr_code': mgr_code}
            cmp_id = FundCompany.filter_by_code(cmp_code)
            if not cmp_id:
                logger.error(f'Cannot find the FundCompany of code:{cmp_code},name:{cmp_name}')
            mgr_info = {
                'mgr_code': mgr_code,
                'name': mgr_name,
                'company_id': cmp_id,
                'work_days': int(work_days),
                'sum_scale': sum_scale,
                'best_rt': best_rt,
            }
            # 更新或插入基金经理信息
            Mgr.insert_or_update(mgr_query_info, do_log_flag=True, **mgr_info)
            # 重新查一次
            mgr_ins = Mgr.filter_by_code(mgr_code)
            if mgr_ins:
                mgr_id = mgr_ins.id
            else:
                logger.error(f'Cannot find fund manager of code:<{mgr_code}>.')
                continue
            fund_objs_of_mgr = Mgr.get_by_id(mgr_id).funds
            # 在管基金
            fund_lists_of_mgr = [f.fund_code for f in fund_objs_of_mgr]
            # 查询到的列表不在现有的中
            patch_funds = set(mgr_fd_list) - set(fund_lists_of_mgr)
            if patch_funds:
                for fund_code in patch_funds:
                    fund_inst = None
                    try:
                        fund_inst = Fund.filter_by_code(fund_code)
                    except FlushError as e:
                        if fund_inst is None:
                            logger.error(
                                f'Error:{e},Fund info of {fund_code} get error,maybe a new fund in subscription period?'
                            )
                            continue
                    # 重新查，否则报错
                    fund_inst = Fund.filter_by_code(fund_code)
                    if not fund_inst:
                        # 根据已有信息创建一个，后期自动更新
                        logger.error(
                            f'Query Fund info of {fund_code} error,maybe is a new fund in subscription period? '
                            f'we will try to create it with minimum info.')
                        # 最简创建
                        fund_name = mgr_fd_map.get(fund_code)
                        fund_inst = self.subscription_period_fund(fund_code, fund_name)
                        logger.info(f'The fund in subscription period created as {fund_inst}')

                    _mgr_ins = Mgr.filter_by_code(mgr_code)
                    _mgr_ins.funds.append(fund_inst)
                    db.session.add(_mgr_ins)
                '''
                ~~注意每一次都必须commit，否则query查询不到~~
                see also:[python - SQLAlchemy: What's the difference between flush() and commit()? - Stack Overflow]
                (https://stackoverflow.com/questions/4201455/sqlalchemy-whats-the-difference-between-flush-and-commit)
                '''
                db.session.commit()

                # 不再管理的，~~移除掉？~~ TODO: 可能是历史管理基金（如：基金经理跳槽了）
                # remove_funds = set(fund_lists_of_mgr) - set(mgr_fd_list)
                # for fund_code in remove_funds:
                #     fund_inst = Fund.query.filter_by(fund_code=fund_code).first()
                #     mgr_ins.funds.remove(fund_inst)
                # db.session.commit()

            for f_code in mgr_fd_list:
                fund_inst = Fund.filter_by_code(f_code)
                if fund_inst is None:
                    logger.error(f'Fund info of {f_code} get error,maybe a new fund in subscription period? '
                                 f'Just create the instance and try again.')
                    continue

                fund_id = fund_inst.id
                fund_mgr_inst = FundMgr.query.filter_by(fund_id=fund_id, mgr_id=mgr_id, end_date=None).first()
                if f_code == best_fd:
                    # 更新基金经理的代表作
                    fund_mgr_inst.update(is_classic=True)
                    # 假定一个经理只有一个代表作
                    break
        return 0

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
                    converted_cop = [str(item) or None if isinstance(item, str) else item for item in cop]
                    comp_info = dict(
                        zip([
                            'code', 'full_name', 'create_date', 'f_counts', 'mgr', 'dpy', 'a_un', 'scale', 'tx_eval',
                            'name', 'b_un', 'update_time'
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

    def set_first_row_to_columns(self, df):
        arr = df.values
        df = pd.DataFrame(arr[1:, 1:], index=arr[1:, 0], columns=arr[0, 1:])
        df.index.name = arr[0, 0]
        df.reset_index(inplace=True)
        return df

    def _nan_to_none(self, nan_str: Union[str, float]) -> Optional[str]:
        if nan_str == 'nan' or nan_str is np.nan:
            return None
        return nan_str

    @staticmethod
    def match_charge_mode(charge_mode_str: str) -> bool:
        regex = re.compile(r'\d*\w+（(.*)）')
        reg_mat = regex.match(charge_mode_str)
        if reg_mat:
            mode = reg_mat.groups()[0]
            if mode:
                return mode == '前端'
        return True

    def _fund_variety_id(self, fv_name: Optional[str]) -> Optional[int]:
        """
        根据名称查询指定的基金大类，如果没有则创建，否则返回id
        :param fv_name:
        :return:
        """
        fv_name = self._nan_to_none(fv_name)
        if fv_name is not None:
            _fv_id = FundVariety.id_by_name(name=fv_name)
            if not _fv_id:
                _fv_info = {'name': fv_name}
                f_tp = FundVariety.create(**_fv_info)
                _fv_id = f_tp.id
            return _fv_id

    def _fund_type_id(self, ft_name: Optional[str]) -> Optional[int]:
        """
        根据名称查询指定的基金大类，如果没有则创建，否则返回id
        :param ft_name:
        :return:
        """
        not_nan_ft_name = self._nan_to_none(ft_name)
        if not_nan_ft_name is not None:
            _ft_id = FundType.id_by_name(name=not_nan_ft_name)
            if not _ft_id:
                _ft_info = {'name': not_nan_ft_name}
                f_tp = FundType.create(**_ft_info)
                _ft_id = f_tp.id
            return _ft_id

    def fund_base_info(self, fund_code: str) -> Optional[Dict]:
        """
        更新基金指定字段：
        全称、名称、成立日期、申购收费方式
        :param fund_code:
        :return:
        """
        raw_columns = [
            '基金全称', '基金代码', '发行日期', '资产规模', '基金管理人', '基金经理人', '管理费率', '销售服务费率', '业绩比较基准', '基金简称', '基金类型', '成立日期/规模',
            '份额规模', '基金托管人', '成立来分红', '托管费率', '最高认购费率', '跟踪标的'
        ]
        repr_cols = [
            'full_name', 'fund_code_with_end_style', 'issuing_date', 'assert_scale', 'company', 'mgr', 'mgr_fee_rate',
            'sale_serve_rate', 'perf_comp_base', 'name', 'f_var_type_name', 'found_date_with_scale', 'share_scale',
            'trustee', 'bound_times', 'trustee_rate', 'top_subscribe_rate', 'track_mark'
        ]
        rename_dict = dict(zip(raw_columns, repr_cols))
        tb = pd.read_html(f'http://fundf10.eastmoney.com/jbgk_{fund_code}.html')
        raw_info = tb[1]
        if not raw_info.empty:
            if raw_info.shape[1] == 4:
                left_tb = raw_info[[0, 1]].T
                right_tb = raw_info[[2, 3]].T
                left_new_col_df = self.set_first_row_to_columns(left_tb)
                right_new_col_df = self.set_first_row_to_columns(right_tb)
                raw_result_df = left_new_col_df.join(right_new_col_df)
                raw_result_df.rename(columns=rename_dict, inplace=True)
                useful_df = raw_result_df[[
                    'full_name', 'fund_code_with_end_style', 'name', 'perf_comp_base', 'found_date_with_scale',
                    'f_var_type_name', 'company'
                ]]
                # 替换np.nan
                useful_df.replace({np.nan: None}, inplace=True)
                # 一列拆分为两列
                useful_df[['create_time', 'start_scale']] = useful_df['found_date_with_scale'].str.split('/',
                                                                                                         2,
                                                                                                         expand=True)
                useful_df[['f_var_name',
                           'f_type_name']] = useful_df.apply(lambda row: self._split_fvt(row['f_var_type_name']),
                                                             axis=1,
                                                             result_type='expand')

                useful_df['create_time'] = useful_df.create_time.apply(lambda x: str(convert.try_parse_date(x)))
                useful_df['is_fe_charge_mode'] = useful_df.fund_code_with_end_style.apply(
                    lambda x: self.match_charge_mode(x))
                useful_df['f_var'] = useful_df.f_var_name.apply(lambda x: self._fund_variety_id(x))
                useful_df['f_type'] = useful_df.f_type_name.apply(lambda x: self._fund_type_id(x))
                useful_df['co_id'] = useful_df.company.apply(lambda company_name: FundCompany.id_by_name(company_name))
                useful_df.drop(
                    columns=['start_scale', 'found_date_with_scale', 'fund_code_with_end_style', 'f_var_type_name'],
                    inplace=True)
                fund_info = useful_df.to_dict(orient='records')
                return fund_info[0]

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
            logger.info(f'Get {ct} funds from east money……')
            # 保存数据
            if save:
                _ret = self.do_save_action(format_, fund_info)
                if _ret == 0:
                    logger.info('Save Fund info successful.')
                else:
                    logger.error('Save Fund info failed.')

            return fund_info

    def do_save_action(self, format_, save_data, suffix=None):
        """
        FIXME: 保存基金、基金经理、基金公司应该使用不同的前/后缀
        """
        assert format_ in ['sql', 'json']
        if format_ == 'sql':
            # TODO: 每个数据保存在不同的数据表中
            self.save_fund_to_db(save_data)
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
            logger.info(f'Data saved to {file_save_fp}.')
            utils.write_json_data(fund_info, file_save_fp)
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
        return json.loads(_funds)

    def counts(self, funds_info: str) -> int:
        _fund_lists = self.be_json(funds_info)
        _count = len(_fund_lists)
        return _count

    @staticmethod
    def _split_fvt(f_vt_str: Optional[str]) -> tuple:
        """
        >>> em = EastMoney()
        >>> avt = '债券型-混合债'
        >>> em._split_fvt(avt)
        ('债券型', '混合债')
        >>> b = '股票型'
        >>> em._split_fvt(b)
        ('股票型', None)
        >>> c = None
        >>> em._split_fvt(c)
        (None, None)
        """
        _ft = None
        if f_vt_str is not None:
            if '-' in f_vt_str:
                _fv, _ft = f_vt_str.split('-')
            else:
                _fv = f_vt_str
        else:
            _fv = None
        return _fv, _ft

    def save_fund_to_db(self, _funds: str) -> int:  # noqa: C901
        """
        保存fund信息到数据库
        :param _funds:
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
                    _fv_id = self._fund_variety_id(fv)
                    cache_fv_map[fv] = _fv_id

                # 基金小类处理
                _ft_id = None
                if ft:
                    _ft_info = {'name': ft}
                    if ft in type_map:
                        _ft_id = type_map.get(ft)
                    else:
                        _ft_id = self._fund_type_id(ft)
                        type_map[ft] = _ft_id
                try:
                    symbol = jcb.search_symbol(code)
                except (UnexpectedArgsError, ValueError):
                    symbol = 'UN'
                if not symbol:
                    symbol = 'UN'
                info = {
                    'name': name,
                    'sxszm': szm,
                    'qxpy': qpy,
                    'symbol_prefix': symbol,
                    'fund_code': code,
                    'f_type': _ft_id if _ft_id else None,
                    'f_var': _fv_id,
                }
                query_info = {'fund_code': code}
                Fund.insert_or_update(query_info, do_log_flag=True, **info)
                _count += 1
            fetch_count = len(_fund_list)
            if fetch_count == _count:
                logger.success(f'Update {fetch_count} of funds successful.')
            else:
                fail_count = fetch_count - _count
                logger.warning(f'Update {fail_count} of funds failed.')
            return 0
        else:
            logger.warning('Get fund info error,can you connect to `http://fund.eastmoney.com/`?')
            return 1

    def hold_split(self):
        """
        TODO:基金持有时间过短会收取高额的赎回费，所以我们需要增加功能以对持有进行分类
        [Python-Pandas之日期分组（将日期按照设定的组分为不同类型）_苏小败在路上-CSDN博客_pandas根据时间分组数据](https://blog.csdn.net/pz789as/article/details/106136141)
        :return:
        """
        pass


em = EastMoney()

if __name__ == '__main__':
    print(em.mgr(save=True, format_='json'))
    # funds = em.fund()
    # count = 0
    # if funds:
    #     fund_list = em.be_json(funds)
    #     count = em.counts(funds)
    # print(funds, count)
