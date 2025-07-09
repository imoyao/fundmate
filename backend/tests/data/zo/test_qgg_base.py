# -*- coding: utf-8 -*-
"""
@Time ： 2022/10/12 11:54
@File ：test_qgg_base.py
@IDE ：PyCharm
"""
import pytest

from backend.fundmate.data.zo.base import FollowAip, Strategy


class TestStrategy:
    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_sty = Strategy()

    def test_latest_info(self):
        result = self.test_sty.latest_info()
        assert result
        assert result.get('name') == '超级股票全明星'


class TestFundFollowAip:
    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.test_fa = FollowAip()

    @pytest.mark.parametrize('endpoint',
                             FollowAip.ENDPOINT_LIST)
    def test_view_result(self, endpoint):
        """
        测试费率获取功能
        :param endpoint:
        :return:
        """
        assert self.test_fa.view_result(endpoint)

    @pytest.mark.parametrize('view_info,expected',
                             [({'thisWeekIndustry': [{'industryViewVo': {'industryCode': '628e227fa20f621aae7d4f4e',
                                                                         'industryName': '国防军工', 'productId': '',
                                                                         'channelFofId': None, 'productName': None,
                                                                         'issueIndustryView': "",
                                                                         'issueIndustryReason': '消息面利好',
                                                                         'totalScore': '73', 'investmentAdvice': '看好',
                                                                         'recommendedOperation': '增加投入',
                                                                         'tagList': ['低估值'], 'industryRuntime': '17',
                                                                         'investmentRatio': '1.5',
                                                                         'totalInputCount': '25.0',
                                                                         'beginTime': '20221012',
                                                                         'riseAndFallType': '01',
                                                                         'valuationMultiple': '45.0'},
                                                      'productId': '8100000282', 'productName': '中欧带你投国防军工',
                                                      'topThreeFundNameList': ['易方达国防军工混合', '交银启明混合A',
                                                                               '华安大安全C'],
                                                      'fundNameList': ['易方达国防军工混合', '交银启明混合A',
                                                                       '华安大安全C', '景顺科技创新混合',
                                                                       '华夏创新前沿股票', '富国军工主题混合A',
                                                                       '富国互联科技股票型C',
                                                                       '中欧电子信息沪港深C', '中邮科技创新C',
                                                                       '大摩科技领先C', '中欧滚钱宝货币']},
                                                     {'industryViewVo': {'industryCode': '628e093fa20f621aae7d4f4b',
                                                                         'industryName': '碳中和', 'productId': '',
                                                                         'channelFofId': None, 'productName': None,
                                                                         'issueIndustryView': "",
                                                                         'issueIndustryReason': '基本面非常有确定性',
                                                                         'totalScore': '70', 'investmentAdvice': '看好',
                                                                         'recommendedOperation': '增加投入',
                                                                         'tagList': ['低估值', '高景气'],
                                                                         'industryRuntime': '17',
                                                                         'investmentRatio': '1.5',
                                                                         'totalInputCount': '19.0',
                                                                         'beginTime': '20221012',
                                                                         'riseAndFallType': '01',
                                                                         'valuationMultiple': '25.2'},
                                                      'productId': '8100000192', 'productName': '中欧带你投碳中和',
                                                      'topThreeFundNameList': ['富国转型机遇混合', '长城中小盘',
                                                                               '海富通改革驱动混合'],
                                                      'fundNameList': ['富国转型机遇混合', '长城中小盘',
                                                                       '海富通改革驱动混合', '南方转型增长A',
                                                                       '国富深化价值混合', '金鹰改革', '信达新能源',
                                                                       '中欧明睿新常态C',
                                                                       '中欧先进制造A', '中欧明睿新起点',
                                                                       '中欧滚钱宝货币']}, {
                                                         'industryViewVo': {'industryCode': '628e0a5ca20f621aae7d4f4c',
                                                                            'industryName': '硬科技', 'productId': '',
                                                                            'channelFofId': None, 'productName': None,
                                                                            'issueIndustryView': "",
                                                                            'issueIndustryReason': '景气度延续高位',
                                                                            'totalScore': '69',
                                                                            'investmentAdvice': '看好',
                                                                            'recommendedOperation': '增加投入',
                                                                            'tagList': ['低估值'],
                                                                            'industryRuntime': '17',
                                                                            'investmentRatio': '1.5',
                                                                            'totalInputCount': '19.0',
                                                                            'beginTime': '20221012',
                                                                            'riseAndFallType': '01',
                                                                            'valuationMultiple': '29.1'},
                                                         'productId': '8100000215', 'productName': '中欧带你投硬科技',
                                                         'topThreeFundNameList': ['金鹰改革', '银华心怡',
                                                                                  '中欧明睿新起点'],
                                                         'fundNameList': ['金鹰改革', '银华心怡', '中欧明睿新起点',
                                                                          '银华盛利', '景顺科技创新',
                                                                          '富国互联科技C', '工银医药C', '信达智造',
                                                                          '东方科技',
                                                                          '易方达国防军工混合', '中欧电子信息沪港深C',
                                                                          '中欧滚钱宝货币']}],
                                'otherIndustry': [{'industryViewVo': {'industryCode': '628e215fa20f621aae7d4f4d',
                                                                      'industryName': '医疗健康', 'productId': '',
                                                                      'channelFofId': None, 'productName': None,
                                                                      'issueIndustryView': "",
                                                                      'issueIndustryReason': '情绪面得分已经处在相当高的位置',
                                                                      'totalScore': '69', 'investmentAdvice': '看好',
                                                                      'recommendedOperation': '增加投入',
                                                                      'tagList': ['低估值'], 'industryRuntime': '17',
                                                                      'investmentRatio': '1.5',
                                                                      'totalInputCount': '19.0',
                                                                      'beginTime': '20221012', 'riseAndFallType': '01',
                                                                      'valuationMultiple': '21.1'},
                                                   'productId': '8100000218', 'productName': '中欧带你投医疗健康',
                                                   'topThreeFundNameList': ['工银医药A', '中欧医疗创新A',
                                                                            '交银医药创新混合'],
                                                   'fundNameList': ['工银医药A', '中欧医疗创新A', '交银医药创新混合',
                                                                    '浦银医疗A', '融通健康C',
                                                                    '广发医疗保健股票A', '安信医药健康C', '长城医疗',
                                                                    '中欧滚钱宝货币']},
                                                  {'industryViewVo': {'industryCode': '628e0422a20f621aae7d4f4a',
                                                                      'industryName': '中国智造', 'productId': '',
                                                                      'channelFofId': None, 'productName': None,
                                                                      'issueIndustryView': '',
                                                                      'issueIndustryReason': '电新板块利润增长加速',
                                                                      'totalScore': '64', 'investmentAdvice': '中性',
                                                                      'recommendedOperation': '正常投入',
                                                                      'tagList': [],
                                                                      'industryRuntime': '17',
                                                                      'investmentRatio': '1.0',
                                                                      'totalInputCount': '18.0',
                                                                      'beginTime': '20221012',
                                                                      'riseAndFallType': '01',
                                                                      'valuationMultiple': '28.1'},
                                                   'productId': '8100000236', 'productName': '中欧带你投中国智造',
                                                   'topThreeFundNameList': ['易方达国防军工混合', '华安制造A',
                                                                            '汇丰低碳'],
                                                   'fundNameList': ['易方达国防军工混合', '华安制造A', '汇丰低碳',
                                                                    '景顺科技创新混合', '华商高端',
                                                                    '中邮科技创新C', '中欧先进制造A', '东方科技',
                                                                    '工银医药A',
                                                                    '富国军工主题混合A', '中欧滚钱宝货币']}, {
                                                      'industryViewVo': {'industryCode': '628eee6ca20f62261e5b4cb1',
                                                                         'industryName': '新消费', 'productId': '',
                                                                         'channelFofId': None, 'productName': None,
                                                                         'issueIndustryView': "",
                                                                         'issueIndustryReason': '密切关注疫情发展与二十大',
                                                                         'totalScore': '59', 'investmentAdvice': '中性',
                                                                         'recommendedOperation': '正常投入',
                                                                         'tagList': [],
                                                                         'industryRuntime': '17',
                                                                         'investmentRatio': '1.0',
                                                                         'totalInputCount': '17.0',
                                                                         'beginTime': '20221012',
                                                                         'riseAndFallType': '01',
                                                                         'valuationMultiple': '27.4'},
                                                      'productId': '8100000237', 'productName': '中欧带你投新消费',
                                                      'topThreeFundNameList': ['中欧时代智慧A', '南方转型增长',
                                                                               '银华心诚'],
                                                      'fundNameList': ['中欧时代智慧A', '南方转型增长', '银华心诚',
                                                                       '中欧丰泓沪港深A',
                                                                       '富国消费主题混合A', '交银新驱动', '景顺绩优',
                                                                       '银华农业', '华安优质生活混合',
                                                                       '工银医药A', '广发汽车C', '中欧滚钱宝货币']}]},
                               {'other_industry': [{'industry_view': {'industry_name': '医疗健康',
                                                                      'investment_advice': '看好',
                                                                      'issue_industry_reason': '情绪面得分已经处在相当高的位置',
                                                                      'recommended_operation': '增加投入',
                                                                      'total_score': '69'},
                                                    'product_info': {'product_id': '8100000218',
                                                                     'product_name': '中欧带你投医疗健康'}},
                                                   {'industry_view': {'industry_name': '中国智造',
                                                                      'investment_advice': '中性',
                                                                      'issue_industry_reason': '电新板块利润增长加速',
                                                                      'recommended_operation': '正常投入',
                                                                      'total_score': '64'},
                                                    'product_info': {'product_id': '8100000236',
                                                                     'product_name': '中欧带你投中国智造'}},
                                                   {'industry_view': {'industry_name': '新消费',
                                                                      'investment_advice': '中性',
                                                                      'issue_industry_reason': '密切关注疫情发展与二十大',
                                                                      'recommended_operation': '正常投入',
                                                                      'total_score': '59'},
                                                    'product_info': {'product_id': '8100000237',
                                                                     'product_name': '中欧带你投新消费'}}],
                                'this_week_industry': [{'industry_view': {'industry_name': '国防军工',
                                                                          'investment_advice': '看好',
                                                                          'issue_industry_reason': '消息面利好',
                                                                          'recommended_operation': '增加投入',
                                                                          'total_score': '73'},
                                                        'product_info': {'product_id': '8100000282',
                                                                         'product_name': '中欧带你投国防军工'}},
                                                       {'industry_view': {'industry_name': '碳中和',
                                                                          'investment_advice': '看好',
                                                                          'issue_industry_reason': '基本面非常有确定性',
                                                                          'recommended_operation': '增加投入',
                                                                          'total_score': '70'},
                                                        'product_info': {'product_id': '8100000192',
                                                                         'product_name': '中欧带你投碳中和'}},
                                                       {'industry_view': {'industry_name': '硬科技',
                                                                          'investment_advice': '看好',
                                                                          'issue_industry_reason': '景气度延续高位',
                                                                          'recommended_operation': '增加投入',
                                                                          'total_score': '69'},
                                                        'product_info': {'product_id': '8100000215',
                                                                         'product_name': '中欧带你投硬科技'}}]}),
                              ])
    def test_simplify_worth_investing(self, view_info, expected):
        assert self.test_fa.simplify_worth_investing(view_info) == expected

    @pytest.mark.parametrize('view_info,expected', [
        ({'departureDate': '20221012', 'currentWorkDay': '20221014', 'endDate': '20221018',
          'title': '新能源估值及基本面优势明显',
          'abstractDesc': '前期交易过热的新能源赛道的估值及情绪都得到了较为充分的释放',
          'issueSynthesizeView': ''},
         {'abstract_desc': '前期交易过热的新能源赛道的估值及情绪都得到了较为充分的释放',
          'current_work_day': '20221014',
          'departure_date': '20221012',
          'end_date': '20221018',
          'issue_synthesize_view': '',
          'title': '新能源估值及基本面优势明显'})])
    def test_simplify_latest_signal(self, view_info, expected):
        result = self.test_fa.simplify_latest_signal(view_info)
        assert result == expected
        if result:
            for key in ['abstract_desc', 'current_work_day', 'departure_date', 'end_date', 'issue_synthesize_view',
                        'title']:
                assert key in list(result.keys())

    @pytest.mark.parametrize('view_info,expected',
                             [({"title": "新能源估值及基本面优势明显",
                                "issueSummary": "前期交易过热的新能源赛道的估值及情绪都得到了较为充分的释放",
                                "modifyTime": "20221012",
                                "endDate": "20221018",
                                "issueSynthesizeView": "",
                                "industryViewVos": [
                                    {
                                        "industryCode": "628e0422a20f621aae7d4f4a",
                                        "industryName": "中国智造",
                                        "productId": "8100000236",
                                        "channelFofId": "None",
                                        "productName": "中欧带你投中国智造",
                                        'issueIndustryView': "",
                                        "issueIndustryReason": "电新板块利润增长加速",
                                        "totalScore": "64",
                                        "investmentAdvice": "中性",
                                        "recommendedOperation": "正常投入",
                                        "tagList": [],
                                        "industryRuntime": "17",
                                        "investmentRatio": "1.0",
                                        "totalInputCount": "18.0",
                                        "beginTime": "20221012",
                                        "riseAndFallType": "01",
                                        "valuationMultiple": "28.1"
                                    },
                                    {
                                        "industryCode": "628e215fa20f621aae7d4f4d",
                                        "industryName": "医疗健康",
                                        "productId": "8100000218",
                                        "channelFofId": "None",
                                        "productName": "中欧带你投医疗健康",
                                        'issueIndustryView': "",
                                        "issueIndustryReason": "情绪面得分已经处在相当高的位置",
                                        "totalScore": "69",
                                        "investmentAdvice": "看好",
                                        "recommendedOperation": "增加投入",
                                        "tagList": [
                                            "低估值"
                                        ],
                                        "industryRuntime": "17",
                                        "investmentRatio": "1.5",
                                        "totalInputCount": "19.0",
                                        "beginTime": "20221012",
                                        "riseAndFallType": "01",
                                        "valuationMultiple": "21.1"
                                    },
                                    {
                                        "industryCode": "628e227fa20f621aae7d4f4e",
                                        "industryName": "国防军工",
                                        "productId": "8100000282",
                                        "channelFofId": "None",
                                        "productName": "中欧带你投国防军工",
                                        'issueIndustryView': "",
                                        "issueIndustryReason": "消息面利好",
                                        "totalScore": "73",
                                        "investmentAdvice": "看好",
                                        "recommendedOperation": "增加投入",
                                        "tagList": [
                                            "低估值"
                                        ],
                                        "industryRuntime": "17",
                                        "investmentRatio": "1.5",
                                        "totalInputCount": "25.0",
                                        "beginTime": "20221012",
                                        "riseAndFallType": "01",
                                        "valuationMultiple": "45.0"
                                    },
                                    {
                                        "industryCode": "628eee6ca20f62261e5b4cb1",
                                        "industryName": "新消费",
                                        "productId": "8100000237",
                                        "channelFofId": "None",
                                        "productName": "中欧带你投新消费",
                                        'issueIndustryView': "",
                                        "issueIndustryReason": "密切关注疫情发展与二十大",
                                        "totalScore": "59",
                                        "investmentAdvice": "中性",
                                        "recommendedOperation": "正常投入",
                                        "tagList": [],
                                        "industryRuntime": "17",
                                        "investmentRatio": "1.0",
                                        "totalInputCount": "17.0",
                                        "beginTime": "20221012",
                                        "riseAndFallType": "01",
                                        "valuationMultiple": "27.4"
                                    },
                                    {
                                        "industryCode": "628e0a5ca20f621aae7d4f4c",
                                        "industryName": "硬科技",
                                        "productId": "8100000215",
                                        "channelFofId": "None",
                                        "productName": "中欧带你投硬科技",
                                        'issueIndustryView': "",
                                        "issueIndustryReason": "景气度延续高位",
                                        "totalScore": "69",
                                        "investmentAdvice": "看好",
                                        "recommendedOperation": "增加投入",
                                        "tagList": [
                                            "低估值"
                                        ],
                                        "industryRuntime": "17",
                                        "investmentRatio": "1.5",
                                        "totalInputCount": "19.0",
                                        "beginTime": "20221012",
                                        "riseAndFallType": "01",
                                        "valuationMultiple": "29.1"
                                    },
                                    {
                                        "industryCode": "628e093fa20f621aae7d4f4b",
                                        "industryName": "碳中和",
                                        "productId": "8100000192",
                                        "channelFofId": "None",
                                        "productName": "中欧带你投碳中和",
                                        "issueIndustryView": "",
                                        "issueIndustryReason": "基本面非常有确定性",
                                        "totalScore": "70",
                                        "investmentAdvice": "看好",
                                        "recommendedOperation": "增加投入",
                                        "tagList": [
                                            "低估值",
                                            "高景气"
                                        ],
                                        "industryRuntime": "17",
                                        "investmentRatio": "1.5",
                                        "totalInputCount": "19.0",
                                        "beginTime": "20221012",
                                        "riseAndFallType": "01",
                                        "valuationMultiple": "25.2"
                                    }
                                ]
                                }, {'end_date': '20221018',
                                    'industry_view_vos': [{'industry_view': {'industry_name': '中国智造',
                                                                             'investment_advice': '中性',
                                                                             'issue_industry_reason': '电新板块利润增长加速',
                                                                             'recommended_operation': '正常投入',
                                                                             'total_score': '64'},
                                                           'product_info': {'product_id': '8100000236',
                                                                            'product_name': '中欧带你投中国智造'}},
                                                          {'industry_view': {'industry_name': '医疗健康',
                                                                             'investment_advice': '看好',
                                                                             'issue_industry_reason': '情绪面得分已经处在相当高的位置',
                                                                             'recommended_operation': '增加投入',
                                                                             'total_score': '69'},
                                                           'product_info': {'product_id': '8100000218',
                                                                            'product_name': '中欧带你投医疗健康'}},
                                                          {'industry_view': {'industry_name': '国防军工',
                                                                             'investment_advice': '看好',
                                                                             'issue_industry_reason': '消息面利好',
                                                                             'recommended_operation': '增加投入',
                                                                             'total_score': '73'},
                                                           'product_info': {'product_id': '8100000282',
                                                                            'product_name': '中欧带你投国防军工'}},
                                                          {'industry_view': {'industry_name': '新消费',
                                                                             'investment_advice': '中性',
                                                                             'issue_industry_reason': '密切关注疫情发展与二十大',
                                                                             'recommended_operation': '正常投入',
                                                                             'total_score': '59'},
                                                           'product_info': {'product_id': '8100000237',
                                                                            'product_name': '中欧带你投新消费'}},
                                                          {'industry_view': {'industry_name': '硬科技',
                                                                             'investment_advice': '看好',
                                                                             'issue_industry_reason': '景气度延续高位',
                                                                             'recommended_operation': '增加投入',
                                                                             'total_score': '69'},
                                                           'product_info': {'product_id': '8100000215',
                                                                            'product_name': '中欧带你投硬科技'}},
                                                          {'industry_view': {'industry_name': '碳中和',
                                                                             'investment_advice': '看好',
                                                                             'issue_industry_reason': '基本面非常有确定性',
                                                                             'recommended_operation': '增加投入',
                                                                             'total_score': '70'},
                                                           'product_info': {'product_id': '8100000192',
                                                                            'product_name': '中欧带你投碳中和'}}],
                                    'issue_summary': '前期交易过热的新能源赛道的估值及情绪都得到了较为充分的释放',
                                    'modify_time': '20221012',
                                    'title': '新能源估值及基本面优势明显'})])
    def test_simplify_this_week_view(self, view_info, expected):
        result = self.test_fa.simplify_this_week_view(view_info)
        assert result == expected

    def test_minimal_view(self):
        result = self.test_fa.minimal_view()
        assert result
        assert 'latest_signal' in result and 'this_week_view' in result

    @pytest.mark.parametrize('is_full,is_minimal', [
        (True, False),
        (True, True),
        (False, True),
        (False, False),
    ])
    def test_zo_view(self, is_full, is_minimal):
        result = self.test_fa.zo_view(is_full=is_full, is_minimal=is_minimal)
        assert result
        assert isinstance(result, dict)

    @pytest.mark.parametrize('is_full,is_minimal', [
        (True, False),
        (True, True),
        (False, True),
        (False, False),
    ])
    def test_stock_bond_ratio(self, is_full, is_minimal):
        result = self.test_fa.stock_bond_ratio(is_full=is_full, is_minimal=is_minimal)
        assert result
        assert isinstance(result, dict)
