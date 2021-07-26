#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/7/26 14:03
from typing import Union

from xalpha.cons import rpost_json

from backend.fundmate.data import utils as dt_utils
from backend.fundmate.excepts import FundQueryError
from backend.fundmate.exts.flask_loguru import logger
from backend.fundmate.fund.models import Fund

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
    """
    该接口用于从中欧财富网站爬取信息之后写入数据库，api获取组合信息需要从数据库中获取
    https://galaxy.qiangungun.com/galaxy/www/index.html?code=073uKgll2ep0s74nFtnl2jwzS82uKglV&state=wxf6c2bee70e049568#/fund/8100000078/weaveFunds?selectedTab=2
    [超级股票全明星](https://cms.qiangungun.com/zost/113081/index.html)
    """
    _full_desc = '''一键买入全市场明星基金经理王牌产品，风格均衡，动态调整。

以“沪深300”为业绩基准，综合考虑收益、风险、费率等因素，投资于全市场绩优偏股基金。

采用“核心+卫星”策略，控制投资风险，实现收益目标。

核心配置：综合评估基金产品和基金经理，选择长期业绩持续优异型基金作为核心配置

卫星配置：结合基本面、技术面和行业政策等因素适度调仓、持续优化，动态配置大小盘、行业风格的“卫星”基金，力争在不同市场周期下赚取超额回报。
    '''

    @staticmethod
    def hearders():
        hd = dt_utils.parse_headers(header_str)
        return hd

    def raw_data(self, fof_id: str = '8100000078') -> Union[dict, None]:
        """
        {
            "code": "000000",
            "msg": "成功",
            "realMsg": null,
            "data": {
                "fofId": 8100000078,
                "fofName": "超级股票全明星",
                "productTypeCode": "10",
                "productTypeDesc": "组合",
                "fundTypeCode": "31",
                "fundTypeDesc": "投顾组合",
                "buyStatusCode": "0",
                "aipStatusCode": "0",
                "totalRate": "130.52",
                "dailyRate": "-1.38",
                "latestWeekRate": "0.34",
                "latestMonthRate": "1.98",
                "latestQuarterRate": "6.27",
                "latestHalfYearRate": "1.48",
                "latestYearRate": "25.89",
                "currentYearRate": "11.96",
                "historyYearRate": "23.98",
                "historyYearRate2": null,
                "latestTwoYearRate": "115.83",
                "latestThreeYearRate": "133.04",
                "minYield": "-26.41",
                "maxYield": "60.67",
                "minAnyQuarter": null,
                "maxAnyQuarter": null,
                "historyYearWaveRate": "21.77",
                "indexHistoryRate": "17.13",
                "yield": "--",
                "maxYearLossRate": "-20.92",
                "onlineRate": "62.89",
                "rateIntervalName": "lastYearRate",
                "minPurAmount": "1000.00",
                "choiceDesc": "全市场精选,集结王牌,核心+卫星",
                "recommendDesc": "投顾",
                "riskDesc": "中风险",
                "riskName": "03",
                "userRiskTestDesc": "C3-平衡型",
                "strategy": "https://static.zocaifu.com/sarli/file/01/1620264653958.jpg",
                "strategyProvider": "",
                "tradeDesc": "组合",
                "publishDays": 340,
                "publishYears": 3,
                "yearRateList": [
                    {
                        "year": "2020",
                        "rate": "59.35",
                        "desc": "年度收益"
                    },
                    {
                        "year": "2019",
                        "rate": "53.51",
                        "desc": "年度收益"
                    },
                    {
                        "year": "2018",
                        "rate": "-19.88",
                        "desc": "年度收益"
                    }
                ],
                "subProductList": [
                    {
                        "detailTypeDesc": "灵活配置",
                        "fundId": "002685",
                        "productId": "600138",
                        "assetTypeDesc": "股票类",
                        "canOpenDetail": "true",
                        "assetTypeName": "0",
                        "productName": "中欧丰泓沪港深A",
                        "ratio": "12.89"
                    },
                    {
                        "detailTypeDesc": "绝对收益",
                        "fundId": "166019",
                        "productId": "601008",
                        "assetTypeDesc": "股票类",
                        "canOpenDetail": "true",
                        "assetTypeName": "0",
                        "productName": "中欧价值智选A",
                        "ratio": "10.74"
                    },
                    {
                        "detailTypeDesc": "混合偏股",
                        "fundId": "166006",
                        "productId": "600058",
                        "assetTypeDesc": "股票类",
                        "canOpenDetail": "true",
                        "assetTypeName": "0",
                        "productName": "中欧行业成长A",
                        "ratio": "10.27"
                    },
                    {
                        "detailTypeDesc": "混合偏股",
                        "fundId": "005241",
                        "productId": "600419",
                        "assetTypeDesc": "股票类",
                        "canOpenDetail": "true",
                        "assetTypeName": "0",
                        "productName": "中欧时代智慧A",
                        "ratio": "9.58"
                    },
                    {
                        "detailTypeDesc": "灵活配置",
                        "fundId": "001694",
                        "productId": "600334",
                        "assetTypeDesc": "股票类",
                        "canOpenDetail": "true",
                        "assetTypeName": "0",
                        "productName": "华安沪港深外延增长",
                        "ratio": "9.45"
                    },
                    {
                        "detailTypeDesc": "混合偏股",
                        "fundId": "100026",
                        "productId": "600393",
                        "assetTypeDesc": "股票类",
                        "canOpenDetail": "true",
                        "assetTypeName": "0",
                        "productName": "富国天合稳健优选",
                        "ratio": "9.30"
                    },
                    {
                        "detailTypeDesc": "标准股票",
                        "fundId": "005267",
                        "productId": "601178",
                        "assetTypeDesc": "股票类",
                        "canOpenDetail": "true",
                        "assetTypeName": "0",
                        "productName": "嘉实价值精选股票",
                        "ratio": "9.14"
                    },
                    {
                        "detailTypeDesc": "混合偏股",
                        "fundId": "166009",
                        "productId": "601011",
                        "assetTypeDesc": "股票类",
                        "canOpenDetail": "true",
                        "assetTypeName": "0",
                        "productName": "中欧新动力A",
                        "ratio": "9.11"
                    },
                    {
                        "detailTypeDesc": "混合偏股",
                        "fundId": "001000",
                        "productId": "600049",
                        "assetTypeDesc": "股票类",
                        "canOpenDetail": "true",
                        "assetTypeName": "0",
                        "productName": "中欧明睿新起点",
                        "ratio": "7.05"
                    },
                    {
                        "detailTypeDesc": "混合偏股",
                        "fundId": "003096",
                        "productId": "600398",
                        "assetTypeDesc": "股票类",
                        "canOpenDetail": "true",
                        "assetTypeName": "0",
                        "productName": "中欧医疗健康C",
                        "ratio": "5.67"
                    },
                    {
                        "detailTypeDesc": "标准股票",
                        "fundId": "002621",
                        "productId": "600102",
                        "assetTypeDesc": "股票类",
                        "canOpenDetail": "true",
                        "assetTypeName": "0",
                        "productName": "中欧消费主题A",
                        "ratio": "4.94"
                    },
                    {
                        "detailTypeDesc": "货币",
                        "fundId": "001211",
                        "productId": "600001",
                        "assetTypeDesc": "货币类",
                        "canOpenDetail": "true",
                        "assetTypeName": "4",
                        "productName": "中欧滚钱宝货币",
                        "ratio": "1.86"
                    }
                ],
                "pieChartDataList": [
                    {
                        "assetTypeDesc": "股票类",
                        "assetTypeName": "0",
                        "ratio": "98.14"
                    },
                    {
                        "assetTypeDesc": "货币类",
                        "assetTypeName": "4",
                        "ratio": "1.86"
                    }
                ],
                "fundRebalanceInfo": {
                    "fundRebalanceList": [
                        {
                            "targetRatio": "0.00",
                            "fundName": "中欧时代先锋股票C",
                            "ratio": "12.56"
                        },
                        {
                            "targetRatio": "0.00",
                            "fundName": "中欧价值A",
                            "ratio": "10.75"
                        },
                        {
                            "targetRatio": "0.00",
                            "fundName": "易方达蓝筹精选混合",
                            "ratio": "10.43"
                        },
                        {
                            "targetRatio": "10.00",
                            "fundName": "富国天合稳健优选",
                            "ratio": "10.38"
                        },
                        {
                            "targetRatio": "10.00",
                            "fundName": "华安沪港深外延增长",
                            "ratio": "10.17"
                        },
                        {
                            "targetRatio": "10.00",
                            "fundName": "中欧行业成长A",
                            "ratio": "10.06"
                        },
                        {
                            "targetRatio": "10.00",
                            "fundName": "中欧新动力A",
                            "ratio": "9.66"
                        },
                        {
                            "targetRatio": "12.00",
                            "fundName": "中欧丰泓沪港深A",
                            "ratio": "8.11"
                        },
                        {
                            "targetRatio": "6.00",
                            "fundName": "中欧明睿新起点",
                            "ratio": "6.02"
                        },
                        {
                            "targetRatio": "5.00",
                            "fundName": "中欧医疗健康C",
                            "ratio": "5.48"
                        },
                        {
                            "targetRatio": "5.00",
                            "fundName": "中欧消费主题A",
                            "ratio": "4.57"
                        },
                        {
                            "targetRatio": "2.00",
                            "fundName": "中欧滚钱宝货币",
                            "ratio": "1.81"
                        },
                        {
                            "targetRatio": "10.00",
                            "fundName": "中欧时代智慧A",
                            "ratio": "0.00"
                        },
                        {
                            "targetRatio": "10.00",
                            "fundName": "中欧价值智选A",
                            "ratio": "0.00"
                        },
                        {
                            "targetRatio": "10.00",
                            "fundName": "嘉实价值精选股票",
                            "ratio": "0.00"
                        }
                    ],
                    "rebalanceDesc": "开年以来，A股市场处于国内经济复苏叠加货币政策回归中性的宏观背景下。市场整体表现较好，但风格开始切换。以必选消费和科技为代表的高估值板块受到紧货币的影响开始逐步调整，而前期滞涨的周期、金融、制造等顺周期行业在全球“再通胀”的背景下出现明显的估值修复。预计在美国财政刺激实质性落地和海外疫情实现有效控制之前，全球经济修复叠加货币政策宽松的交易环境不会发生变化。A股市场运行的主要矛盾在未来1-2个季度仍将持续，我们预计顺周期行业在以上宏观背景下仍有投资机会，同时价值类品种相对成长类的品种会有显著的估值修复行情。因此本次调仓我们会适当降低必选消费科技等前期涨幅过大的高估值板块配置，加大顺周期行业暴露，在压低估值的同时使得组合在行业分布上更为均衡。",
                    "fofReportInfo": null,
                    "transferDate": "20210301"
                },
                "feeTypeName": "Percent",
                "discount": "0.1000",
                "realDiscount": "0.1",
                "fee": "1.50",
                "aipFeeType": "Percent",
                "aipDiscount": "0.1000",
                "aipRealDiscount": "0.1",
                "aipFee": "1.50",
                "tieredRate": "0.75",
                "publishTimes": "3年340天",
                "fofMaxAPI": "68194200.00",
                "fofMinAPI": "1000.00",
                "fofStrategy": "https://static.zocaifu.com/sarli/file/01/1620264653958.jpg",
                "fofRealDiscount": null,
                "fofDiscount": null,
                "fofPurIncrease": "0.01",
                "fofDate": "20210723",
                "fofFileJson": "{\"基金投资组合策略说明书（超级股票全明星策略）\":\"https://static.qiangungun.com/sarli/product/FofProduct/A003_a5/rebalanceFileJson/基金投资组合策略说明书（超级股票全明星策略）.pdf\"}",
                "fofPurRealDiscount": "0.0",
                "fofPurDiscount": "0.0",
                "fofAipRealDiscount": "0.0",
                "fofAipDiscount": "0.0",
                "fofOperateDate": "",
                "fofOperateFileInfos": [],
                "wechatTitle": "超级股票全明星，甄选绩优股基，力争长期超越市场！\r\n",
                "wechatDesc": "甄选具备超额能力的主动基金，结合市场风格动态调整。",
                "fofAdvantage": null,
                "holdingYear": "2年以上",
                "profitUnit": null,
                "currencyFof": false,
                "fofTypeCode": "04",
                "fofTypeDesc": "投顾",
                "analogAmount": "10000",
                "analogRevenue": "2398.00",
                "simulatedLoss": "-2092.00",
                "seqNo": null,
                "navDate": "20210723",
                "fofPublish": "20200522",
                "fofGqbPurRealDiscount": "0.0",
                "fofGqbAipRealDiscount": "0.0",
                "showTypeDesc": null,
                "showTypeInfo": null,
                "showTypeNum": null,
                "showTypeUnit": null,
                "deadlineDesc": "建议持有2年以上",
                "strategyConcept": "投资目标：通过优选基金管理人并结合一定风格、行业轮动，争取高于市场的超额回报。\r\n投资策略：主要投资主动偏股基金，依托中欧主动管理的出色能力，结合市场风格精选优秀管理人，并适时用全市场其他优选基金进行补充。\r\n适合人群：能承受较高波动的积极投资者\r\n建议持有时长：2年以上",
                "waveLevel": 8,
                "waveLevel2": null,
                "newHoldingYear": "2年以上",
                "rateIntervalName2": "lastMonthRate",
                "fofReportInfo": null,
                "fofRiskIndexList": [
                    {
                        "indexIntervalName": "total",
                        "indexIntervalDesc": null,
                        "fofRiskIndexInfoVo": {
                            "drawdown": "-25.36",
                            "waveRate": "21.16",
                            "sharpeRatio": "1.13",
                            "positiveYield": "100.00",
                            "positiveYieldTypeCode": "lastTwoYearPositiveYield",
                            "positiveYieldTypeDesc": "2年正收益情况",
                            "aboveStandard": "98.57",
                            "minIntervalRate": "--",
                            "maxIntervalRate": "--"
                        }
                    },
                    {
                        "indexIntervalName": "totalIndex",
                        "indexIntervalDesc": null,
                        "fofRiskIndexInfoVo": {
                            "drawdown": "-42.27",
                            "waveRate": "21.77",
                            "sharpeRatio": "0.79",
                            "positiveYield": "83.00",
                            "positiveYieldTypeCode": "lastTwoYearPositiveYield",
                            "positiveYieldTypeDesc": "2年正收益情况",
                            "aboveStandard": "--",
                            "minIntervalRate": "--",
                            "maxIntervalRate": "--"
                        }
                    }
                ],
                "subAckDays": 1,
                "redAckDays": 1,
                "subDays": 0,
                "redDays": 3,
                "fofStrategyTypeCode": "06",
                "processTypeCode": "",
                "holdingTimeCode": "06",
                "subAgrVersion": "20201225111555",
                "subAgrUrl": "https://static.qiangungun.com/sarli/product/FofProduct/A003_a5/rebalanceFileJson/基金投资组合策略说明书（超级股票全明星策略）.pdf",
                "fofRiskIndexList2": [
                    {
                        "holdingTimeCode": "05",
                        "holdingTimeDesc": "1年以上",
                        "holdingTimeDesc2": "1年",
                        "fofRiskIndexInfoVo": {
                            "drawdown": "-42.27",
                            "waveRate": "21.77",
                            "sharpeRatio": "0.79",
                            "positiveYield": "77.14",
                            "positiveYieldTypeCode": "",
                            "positiveYieldTypeDesc": "",
                            "aboveStandard": "--",
                            "minIntervalRate": "-34.07",
                            "maxIntervalRate": "122.34"
                        }
                    },
                    {
                        "holdingTimeCode": "06",
                        "holdingTimeDesc": "2年以上",
                        "holdingTimeDesc2": "2年",
                        "fofRiskIndexInfoVo": {
                            "drawdown": "-42.27",
                            "waveRate": "21.77",
                            "sharpeRatio": "0.79",
                            "positiveYield": "83.00",
                            "positiveYieldTypeCode": "",
                            "positiveYieldTypeDesc": "",
                            "aboveStandard": "--",
                            "minIntervalRate": "-30.65",
                            "maxIntervalRate": "144.28"
                        }
                    },
                    {
                        "holdingTimeCode": "07",
                        "holdingTimeDesc": "3年以上",
                        "holdingTimeDesc2": "3年",
                        "fofRiskIndexInfoVo": {
                            "drawdown": "-42.27",
                            "waveRate": "21.77",
                            "sharpeRatio": "0.79",
                            "positiveYield": "86.20",
                            "positiveYieldTypeCode": "",
                            "positiveYieldTypeDesc": "",
                            "aboveStandard": "--",
                            "minIntervalRate": "-24.57",
                            "maxIntervalRate": "116.50"
                        }
                    }
                ],
                "adFee": "0.75",
                "adRealFee": "0.750000",
                "adFeediscount": null,
                "adFeeDesc": "根据投资者授权，中欧财富可通过中欧财富平台或由中欧财富至指定销售平台开立交易账户并代为发起或办理基金交易业务。\r\n\r\n投顾服务费\r\n投顾服务费率0.75%/年，按持有资产总额每日计算，每半年收取；不满半年的，在赎回时收取。\r\n\r\n交易费用\r\n1.\t通过中欧财富平台申购成分基金，按中欧财富平台申赎费减免规则收取相应成分基金申购费（含调仓交易）：中欧旗下产品不收取申购费。调仓赎回时，中欧旗下产品不再收取计入基金财产之外的赎回费用。若持有投顾组合小于7天，部分成分基金将收取1.5%的惩罚性赎回费。\r\n2.\t通过指定平台申购成分基金，由指定平台按其规则收取相应成分基金申赎费（含调仓交易）。\r\n",
                "strategyPosition": "全市场严选股基，让明星经理为你打工",
                "frequencyDesc": "季度",
                "leastDisclosureDay": "20210630",
                "expectYield": "",
                "indexStandardDesc": "Wind货币市场基金指数、Wind偏股混合型基金指数",
                "buyers": 100,
                "relateLabel": null,
                "exclusivePensionFlag": false,
                "productRefUrl": null,
                "strategyAdvantage": "https://static.qiangungun.com/sarli/product/FofProduct/A003_a5/strategyAdvantage/财富+3@2x.png",
                "featureService": "https://static.qiangungun.com/sarli/product/FofProduct/A003_a5/featureService/特色服务@2x.png",
                "teamIntroduction": "https://static.qiangungun.com/sarli/product/FofProduct/A003_a5/teamIntroduce/团队介绍@2x.png",
                "showAdRiskFlag": true,
                "recommendVos": [],
                "recommendDrawdown": null,
                "attentionFlag": false,
                "suggestHoldingDay": 730,
                "fofSubStrategyTypeCode": "",
                "fofTargetStrategyStatusCode": "",
                "fofTargetStrategyStatusDesc": "",
                "fofSaleStartTime": null,
                "fofSaleEndTime": null,
                "fofTargetOperateDate": null,
                "fofObserDate": null,
                "fofOperateExpireDate": null,
                "fofObserDays": null,
                "fofMaxOperateDays": null,
                "operationDays": null,
                "fofObserMonths": null,
                "fofMaxOperateMonths": null,
                "fofTargetRate": "--",
                "fofResBuyStatuscode": "",
                "fofSeriesNo": null,
                "fofSeriesVo": null,
                "currentTime": null
            },
            "busAddData": null
        }

        """
        _url = 'https://mobile.qiangungun.com/v2/product/detail'
        hd = self.hearders()
        # 注意此处的`{{`必须使用双符号，否则报错ValueError: Invalid format specifier
        _data = f'''{{"productId":{fof_id},"includes":["02","01","03"],"parseType":"01","showReportForever":false,
        "userId":null,"sessionId":null,"source":"H","version":"3.20.0","guid":"39b0d57f1134640daf87ef62d13001e8",
        "phoneModel":null,"fraudTokenId":"e3Y6ICIyLjUuMCIsIG9zOiAid2ViIiwgczogMTk5LCBlOiAianMgbm90IGRvd25sb2FkIn0="}} 
        '''
        _resp = rpost_json(_url, headers=hd, data=_data)

        if _resp and _resp.get('code') == '000000':
            info = _resp.get('data')
            return info

    def history(self, fof_id: str = '8100000078') -> Union[dict, None]:
        """
        调仓历史
        """
        _url = 'https://mobile.qiangungun.com/v1/product/queryFofRebalanceInfo'
        _data = f'''{{"fofId":{fof_id},"source":"H","guid":"8ce2aa731134640de7b51f77682dcd4a","userId":null,
        "sessionId":null,"version":"3.20.0","appSource":"","appVersion":""}} '''
        hd = self.hearders()
        _resp = rpost_json(_url, headers=hd, data=_data)
        if _resp and _resp.get('code') == '000000':
            info = _resp.get('data')
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
                    fund_code_list = Fund.code_by_name(f_name)
                    if len(fund_code_list) == 1:
                        fund_code = fund_code_list[0]
                    else:
                        logger.error(
                            f'Get fund code error of fund {f_name},we speculate is in {fund_code_list}.'
                        )
                        raise FundQueryError(
                            f'Get code of fund {f_name} error!')

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

    def data(self):
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
            'id': rd.get('fofId'),
            'name': rd.get('fofName'),
            'risk_level': risk_level,
            'product_list': product_list,
            'desc': _desc,
            'full_desc': _desc,
            'transfer_date': transfer_date,
            'last_disclosure_date': least_disclosure_day,
        }
        return info


if __name__ == '__main__':
    zo = QGG()
    print(zo.data())
