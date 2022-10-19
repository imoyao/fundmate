#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/26 14:03
import logging
import secrets
from typing import Dict, List, Union

from xalpha.cons import rpost_json

from backend.fundmate import utils
from backend.fundmate.data.utils import base as dt_utils
from backend.fundmate.excepts import FundQueryError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import Fund


# 屏蔽爬虫库的debug提示
logger_xa = logging.getLogger('xalpha')
logger_xa.setLevel(logging.ERROR)
logger_urllib3 = logging.getLogger('urllib3')
logger_urllib3.setLevel(logging.ERROR)

header_str = '''Accept: application/json, text/plain, */*
Accept-Encoding: gzip, deflate, br
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7
Connection: keep-alive
Content-Length: 310
Content-Type: application/json;charset=UTF-8
DNT: 1
Host: mobile.qiangungun.com
Origin: https://galaxy.qiangungun.com
Referer: https://galaxy.qiangungun.com/
sec-ch-ua: " Not;A Brand";v="99", "Microsoft Edge";v="91", "Chromium";v="91"
sec-ch-ua-mobile: ?0
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-site
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36 Edg/91.0.864.71
'''  # noqa


class QGG:

    @staticmethod
    def headers():
        hd = dt_utils.parse_headers(header_str)
        return hd

    @staticmethod
    def response_data(resp):
        if resp and resp.get('code') == '000000':
            info = resp.get('data')
            return info
        return None

    @staticmethod
    def guid():
        """
        guid:
        https://github.com/yang302/react-router-fetch/blob/0994abf0353a770b03a4e081c7c108e87f2cfc3b/src/fetch/instance.js#L61
        ```javascript
        function guid() {
          let guid = "";
          for (let i = 1; i <= 32; i++) {
            let n = Math.floor(Math.random() * 16.0).toString(16);
            guid += n;
          }
          return guid;
        }
        ```
        """
        return secrets.token_hex(16)


class Strategy(QGG):
    """
    该接口用于从中欧财富网站爬取信息之后写入数据库，api获取组合信息需要从数据库中获取
    https://galaxy.qiangungun.com/galaxy/www/index.html?code=073uKgll2ep0s74nFtnl2jwzS82uKglV&state=wxf6c2bee70e049568#/fund/8100000078/weaveFunds?selectedTab=2
    介绍信息：[超级股票全明星](https://cms.qiangungun.com/zost/113081/index.html)
    """
    _full_desc = '''一键买入全市场明星基金经理王牌产品，风格均衡，动态调整。

以“沪深300”为业绩基准，综合考虑收益、风险、费率等因素，投资于全市场绩优偏股基金。

采用“核心+卫星”策略，控制投资风险，实现收益目标。

核心配置：综合评估基金产品和基金经理，选择长期业绩持续优异型基金作为核心配置

卫星配置：结合基本面、技术面和行业政策等因素适度调仓、持续优化，动态配置大小盘、行业风格的“卫星”基金，力争在不同市场周期下赚取超额回报。
    '''

    def raw_data(self, fof_id: str = '8100000078') -> Union[dict, None]:
        """
                { "code": "000000", "msg": "成功", "realMsg": null, "data": { "fofId": 8100000078, "fofName": "超级股票全明星",
        "productTypeCode": "10", "productTypeDesc": "组合", "fundTypeCode": "31", "fundTypeDesc": "投顾组合",
        "buyStatusCode": "0", "aipStatusCode": "0", "totalRate": "130.52", "dailyRate": "-1.38", "latestWeekRate":
        "0.34", "latestMonthRate": "1.98", "latestQuarterRate": "6.27", "latestHalfYearRate": "1.48",
        "latestYearRate": "25.89", "currentYearRate": "11.96", "historyYearRate": "23.98", "historyYearRate2": null,
        "latestTwoYearRate": "115.83", "latestThreeYearRate": "133.04", "minYield": "-26.41", "maxYield": "60.67",
        "minAnyQuarter": null, "maxAnyQuarter": null, "historyYearWaveRate": "21.77", "indexHistoryRate": "17.13",
        "yield": "--", "maxYearLossRate": "-20.92", "onlineRate": "62.89", "rateIntervalName": "lastYearRate",
        "minPurAmount": "1000.00", "choiceDesc": "全市场精选,集结王牌,核心+卫星", "recommendDesc": "投顾", "riskDesc": "中风险",
        "riskName": "03", "userRiskTestDesc": "C3-平衡型", "strategy":
        "https://static.zocaifu.com/sarli/file/01/1620264653958.jpg", "strategyProvider": "", "tradeDesc": "组合",
        "publishDays": 340, "publishYears": 3, "yearRateList": [ { "year": "2020", "rate": "59.35", "desc": "年度收益" },
        { "year": "2019", "rate": "53.51", "desc": "年度收益" }, { "year": "2018", "rate": "-19.88", "desc": "年度收益" } ],
        "subProductList": [ { "detailTypeDesc": "灵活配置", "fundId": "002685", "productId": "600138", "assetTypeDesc":
        "股票类", "canOpenDetail": "true", "assetTypeName": "0", "productName": "中欧丰泓沪港深A", "ratio": "12.89" },
        { "detailTypeDesc": "绝对收益", "fundId": "166019", "productId": "601008", "assetTypeDesc": "股票类",
        "canOpenDetail": "true", "assetTypeName": "0", "productName": "中欧价值智选A", "ratio": "10.74" },
        { "detailTypeDesc": "混合偏股", "fundId": "166006", "productId": "600058", "assetTypeDesc": "股票类",
        "canOpenDetail": "true", "assetTypeName": "0", "productName": "中欧行业成长A", "ratio": "10.27" },
        { "detailTypeDesc": "混合偏股", "fundId": "005241", "productId": "600419", "assetTypeDesc": "股票类",
        "canOpenDetail": "true", "assetTypeName": "0", "productName": "中欧时代智慧A", "ratio": "9.58" },
        { "detailTypeDesc": "灵活配置", "fundId": "001694", "productId": "600334", "assetTypeDesc": "股票类",
        "canOpenDetail": "true", "assetTypeName": "0", "productName": "华安沪港深外延增长", "ratio": "9.45" },
        { "detailTypeDesc": "混合偏股", "fundId": "100026", "productId": "600393", "assetTypeDesc": "股票类",
        "canOpenDetail": "true", "assetTypeName": "0", "productName": "富国天合稳健优选", "ratio": "9.30" },
        { "detailTypeDesc": "标准股票", "fundId": "005267", "productId": "601178", "assetTypeDesc": "股票类",
        "canOpenDetail": "true", "assetTypeName": "0", "productName": "嘉实价值精选股票", "ratio": "9.14" },
        { "detailTypeDesc": "混合偏股", "fundId": "166009", "productId": "601011", "assetTypeDesc": "股票类",
        "canOpenDetail": "true", "assetTypeName": "0", "productName": "中欧新动力A", "ratio": "9.11" },
        { "detailTypeDesc": "混合偏股", "fundId": "001000", "productId": "600049", "assetTypeDesc": "股票类",
        "canOpenDetail": "true", "assetTypeName": "0", "productName": "中欧明睿新起点", "ratio": "7.05" },
        { "detailTypeDesc": "混合偏股", "fundId": "003096", "productId": "600398", "assetTypeDesc": "股票类",
        "canOpenDetail": "true", "assetTypeName": "0", "productName": "中欧医疗健康C", "ratio": "5.67" },
        { "detailTypeDesc": "标准股票", "fundId": "002621", "productId": "600102", "assetTypeDesc": "股票类",
        "canOpenDetail": "true", "assetTypeName": "0", "productName": "中欧消费主题A", "ratio": "4.94" },
        { "detailTypeDesc": "货币", "fundId": "001211", "productId": "600001", "assetTypeDesc": "货币类", "canOpenDetail":
        "true", "assetTypeName": "4", "productName": "中欧滚钱宝货币", "ratio": "1.86" } ], "pieChartDataList": [ {
        "assetTypeDesc": "股票类", "assetTypeName": "0", "ratio": "98.14" }, { "assetTypeDesc": "货币类", "assetTypeName":
        "4", "ratio": "1.86" } ], "fundRebalanceInfo": { "fundRebalanceList": [ { "targetRatio": "0.00", "fundName":
        "中欧时代先锋股票C", "ratio": "12.56" }, { "targetRatio": "0.00", "fundName": "中欧价值A", "ratio": "10.75" },
        { "targetRatio": "0.00", "fundName": "易方达蓝筹精选混合", "ratio": "10.43" }, { "targetRatio": "10.00", "fundName":
        "富国天合稳健优选", "ratio": "10.38" }, { "targetRatio": "10.00", "fundName": "华安沪港深外延增长", "ratio": "10.17" },
        { "targetRatio": "10.00", "fundName": "中欧行业成长A", "ratio": "10.06" }, { "targetRatio": "10.00", "fundName":
        "中欧新动力A", "ratio": "9.66" }, { "targetRatio": "12.00", "fundName": "中欧丰泓沪港深A", "ratio": "8.11" },
        { "targetRatio": "6.00", "fundName": "中欧明睿新起点", "ratio": "6.02" }, { "targetRatio": "5.00", "fundName":
        "中欧医疗健康C", "ratio": "5.48" }, { "targetRatio": "5.00", "fundName": "中欧消费主题A", "ratio": "4.57" },
        { "targetRatio": "2.00", "fundName": "中欧滚钱宝货币", "ratio": "1.81" }, { "targetRatio": "10.00", "fundName":
        "中欧时代智慧A", "ratio": "0.00" }, { "targetRatio": "10.00", "fundName": "中欧价值智选A", "ratio": "0.00" },
        { "targetRatio": "10.00", "fundName": "嘉实价值精选股票", "ratio": "0.00" } ], "rebalanceDesc":
        ……
        """
        _url = 'https://mobile.qiangungun.com/v2/product/detail'
        hd = self.headers()
        # 注意此处的`{{`必须使用双符号，否则报错ValueError: Invalid format specifier
        _data = f'''{{"productId":{fof_id},"includes":["02","01","03"],"parseType":"01","showReportForever":false,
        "userId":null,"sessionId":null,"source":"H","version":"3.20.0","guid":"39b0d57f1134640daf87ef62d13001e8",
        "phoneModel":null,"fraudTokenId":"e3Y6ICIyLjUuMCIsIG9zOiAid2ViIiwgczogMTk5LCBlOiAianMgbm90IGRvd25sb2FkIn0="}}
        '''  # noqa:W291
        _resp = rpost_json(_url, headers=hd, data=_data)

        info = self.response_data(_resp)
        return info

    def history(self, fof_id: str = '8100000078') -> Union[dict, None]:
        """
        调仓历史
        """
        _url = 'https://mobile.qiangungun.com/v1/product/queryFofRebalanceInfo'
        _data = f'''{{"fofId":{fof_id},"source":"H","guid":"8ce2aa731134640de7b51f77682dcd4a","userId":null,
        "sessionId":null,"version":"3.20.0","appSource":"","appVersion":""}} '''
        hd = self.headers()
        _resp = rpost_json(_url, headers=hd, data=_data)
        info = self.response_data(_resp)
        return info

    def remake_his(self, fof_id: str = '8100000078') -> list:
        """
        返回的数据只有基金名称，必须根据名称转化为fund_code存入数据库
        """
        hist = self.history(fof_id=fof_id)
        if hist:
            re_balance_list = hist.get('fofRebalanceList')
            fof_re_balance_list = list()
            # 调仓信息
            for fund_list_item in re_balance_list:
                fund_list = fund_list_item.get('fundRebalanceList')
                # 单次调仓信息
                _re_balance_list = list()
                for fund_item in fund_list:
                    f_name = fund_item.get('fundName')
                    fund_code_list = Fund.search_name(f_name)
                    if len(fund_code_list) == 1:
                        fund_code = fund_code_list[0]
                    else:
                        logger.error(f'Get fund code error of fund {f_name},we speculate is in {fund_code_list}.')
                        raise FundQueryError(f'Get code of fund {f_name} error!')

                    bf_ratio = fund_item.get('ratio')  # 调仓前
                    aft_ratio = fund_item.get('targetRatio')  # 调仓后
                    info = {
                        'code': fund_code,
                        'name': f_name,
                        'before_ratio': bf_ratio,
                        'after_ratio': aft_ratio,
                    }
                    _re_balance_list.append(info)
                date = fund_list_item.get('rebalanceDate')
                desc = fund_list_item.get('rebalanceDesc')
                balance_data = {
                    'date': date,
                    'desc': desc,
                    're_balance_list': _re_balance_list,
                }
                fof_re_balance_list.append(balance_data)
            return fof_re_balance_list

    def latest_info(self):
        """组合当前信息
        编号
        """
        rd = self.raw_data()
        risk = rd.get('riskName')
        sub_product_list = rd.get('subProductList')
        least_disclosure_day = rd.get('leastDisclosureDay')
        _desc = rd.get('choiceDesc')
        fund_re_balance_info = rd.get('fundRebalanceInfo')
        transfer_date = fund_re_balance_info.get('transferDate')
        product_list = list()
        for fund in sub_product_list:
            f_code = fund['fundId']
            f_name = fund['productName']
            ratio = fund['ratio']
            f_item = {'code': f_code, 'name': f_name, 'ratio': ratio}
            product_list.append(f_item)
        risk_level = int(risk)
        info = {
            'code': rd.get('fofId'),
            'name': rd.get('fofName'),
            'risk_type': risk_level,
            'product_list': product_list,
            'desc': _desc,
            'rich_desc': _desc,
            'transfer_date': transfer_date,
            'last_adjust_date': least_disclosure_day,
        }
        return info


class FollowAip(QGG):
    """
    中欧带你投行业跟投计划
    行业景气度追踪I纪律化投资|每周三发信号
    ref：https://galaxy.qiangungun.com/galaxy/share-react/build/index.html#/followAip/guideIndex
    """
    _BASE_URL = 'https://mobile.qiangungun.com/v1/guide/'
    ENDPOINT_LIST = [
        'latest_signal',
        'worth_investing',
        'query_industry_param',
        'this_week_view'
    ]

    def req_body(self):
        """
        """
        guid = self.guid()
        return {
            "primitive": False,
            "source": "H",
            "guid": guid,
            "userId": None,
            "sessionId": None,
            "version": "4.5.0",
            "appSource": "",
            "appVersion": ""
        }

    def view_result(self, endpoint: str = 'this_week_view') -> Dict:
        """
        返回接口结果
        :type endpoint: str
        """
        camel_endpoint = utils.to_camelcase(endpoint)
        _url = self._BASE_URL + camel_endpoint
        _data = self.req_body()
        headers = self.headers()
        _resp = rpost_json(_url, headers=headers, json=_data)
        info = self.response_data(_resp)
        return info

    def sample_view(self) -> Dict:
        """
        精简观点
        :return:
        """
        info = dict()
        for endpoint in self.ENDPOINT_LIST:
            item = self.view_result(endpoint)
            info[endpoint] = item
        return info

    @staticmethod
    def parse_industry(industry_info: Dict) -> Dict:
        """
        解析信息
        :param industry_info:
        :return:
        """
        industry_view_vo = industry_info.get('industryViewVo')
        if industry_view_vo:
            industry_view = {
                # 'industry_code': industry_view_vo.get('industryCode'),
                'industry_name': industry_view_vo.get('industryName'),
                'issue_industry_reason': industry_view_vo.get('issueIndustryReason'),
                'total_score': industry_view_vo.get('totalScore'),
                'investment_advice': industry_view_vo.get('investmentAdvice'),
                'recommended_operation': industry_view_vo.get('recommendedOperation'),
            }
        else:
            industry_view = None
        product_info = {
            'product_id': industry_info.get('productId'),
            'product_name': industry_info.get('productName'),
            # 'fund_name_list': industry_info.get('fundNameList')
        }
        result_info = {
            'industry_view': industry_view,
            'product_info': product_info,
        }
        return result_info

    def simplify_worth_investing(self, view_info: Dict) -> Dict:
        """
        返回信息太冗长了，此处简化信息
        :param view_info:
        :return:
        """

        def enumerate_industry(week_industry: List) -> List:
            """
            解析每个品类，只取最重要的部分
            :param week_industry:
            :return:
            """
            industry_list = list()
            if week_industry:
                for _industry_info in week_industry:
                    _parsed_info = self.parse_industry(_industry_info)
                    industry_list.append(_parsed_info)
            return industry_list

        this_week_industry = view_info.get('thisWeekIndustry')
        other_industry = view_info.get('otherIndustry')
        this_week_industry_list = enumerate_industry(this_week_industry)
        other_week_industry_list = enumerate_industry(other_industry)
        _result = {
            'this_week_industry': this_week_industry_list,
            'other_industry': other_week_industry_list,
        }
        return _result

    @staticmethod
    def key_to_snakecase(camel_case_dict):
        """
        字典key转为snakecase
        :param camel_case_dict:
        :return:
        """
        _result = dict()
        for key, value in camel_case_dict.items():
            snakecase_key = utils.to_snakecase(key)
            _result[snakecase_key] = value
        return _result

    def simplify_latest_signal(self, latest_signal):
        _result = self.key_to_snakecase(latest_signal)
        return _result

    @staticmethod
    def simplify_query_industry_param(query_industry_info):
        return query_industry_info

    @staticmethod
    def parse_week_industry(industry_view_vo):
        """
        每周观点信息
        :param industry_view_vo:
        :return:
        """
        industry_view = {
            # 'industry_code': industry_view_vo.get('industryCode'),
            'industry_name': industry_view_vo.get('industryName'),
            'issue_industry_reason': industry_view_vo.get('issueIndustryReason'),
            'total_score': industry_view_vo.get('totalScore'),
            'investment_advice': industry_view_vo.get('investmentAdvice'),
            'recommended_operation': industry_view_vo.get('recommendedOperation'),
        }
        product_info = {
            'product_id': industry_view_vo.get('productId'),
            'product_name': industry_view_vo.get('productName'),
            # 'fund_name_list': industry_view_vo.get('fundNameList')
        }
        result_info = {
            'industry_view': industry_view,
            'product_info': product_info,
        }
        return result_info

    def simplify_this_week_view(self, week_view_info):
        cp_week_view_info = week_view_info.copy()
        cp_week_view_info.pop('issueSynthesizeView')
        industry_view_vos = cp_week_view_info.get('industryViewVos')
        sample_vol_list = list()
        for industry_view_vol in industry_view_vos:
            item = self.parse_week_industry(industry_view_vol)
            sample_vol_list.append(item)
        cp_week_view_info['industryViewVos'] = sample_vol_list
        week_view = self.key_to_snakecase(cp_week_view_info)
        return week_view

    def simplify_view(self) -> Dict:
        info = dict()
        for endpoint in self.ENDPOINT_LIST:
            # 此参数在简略信息中无必要展示
            if endpoint == 'query_industry_param':
                continue
            item = self.view_result(endpoint)
            func_name = 'simplify_' + endpoint
            item_view = getattr(self, func_name)(item)
            info[endpoint] = item_view
        return info

    def minimal_view(self) -> Dict:
        """
        最简单化信息展示
        :return:
        """
        this_week_view = self.view_result('this_week_view')
        simplify_week_view_info = self.simplify_this_week_view(this_week_view)
        industry_view_vos = simplify_week_view_info.get('industry_view_vos')
        for item in industry_view_vos:
            item.pop('product_info')
        simplify_week_view_info['industry_view_vos'] = industry_view_vos
        latest_signal_view = self.view_result('latest_signal')
        latest_signal_view_info = self.simplify_latest_signal(latest_signal_view)
        minimal_view_result = {
            'latest_signal': latest_signal_view_info,
            'this_week_view': simplify_week_view_info,
        }
        return minimal_view_result

    def full_view(self) -> Dict:
        """
        完整观点
        :return:
        """
        info = dict()
        for endpoint in self.ENDPOINT_LIST:
            item = self.view_result(endpoint)
            camel_case = utils.to_camelcase(endpoint)
            info[camel_case] = item
        return info

    def zo_view(self, is_full: bool = True, is_minimal: bool = True) -> Dict:
        if is_full:
            return self.full_view()
        else:
            if is_minimal:
                return self.minimal_view()
            return self.simplify_view()


if __name__ == '__main__':
    zo = Strategy()
    print(zo.latest_info())
    follow_api = FollowAip()
    result = follow_api.zo_view(is_full=False)
    result1 = follow_api.zo_view(is_full=True)
    print(result, result1)
