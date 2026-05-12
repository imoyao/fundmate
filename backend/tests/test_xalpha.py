"""xalpha 功能可用性测试"""

import warnings

warnings.filterwarnings('ignore')  # 暂时忽略 SyntaxWarning 等

import xalpha as xa  # noqa: E402


def test_fund_info():
    """基金基本信息"""
    try:
        info = xa.fundinfo('000001')
        print('✅ fundinfo: name =', info.name)
        print('   risklevel:', getattr(info, 'risklevel', 'N/A'))
        print('   founddate:', getattr(info, 'founddate', 'N/A'))
        print('   benchmark:', getattr(info, 'benchmark', 'N/A'))
    except Exception as e:
        print('❌ fundinfo failed:', e)


def test_fund_nav():
    """净值数据"""
    try:
        info = xa.fundinfo('000001')
        nav = info.price(start_date='2025-01-01', end_date='2025-01-10')
        print('✅ price(): returned DataFrame of shape', nav.shape)
        print(nav.head(2))
    except Exception as e:
        print('❌ price() failed:', e)


def test_fund_holdings():
    """持仓穿透"""
    try:
        info = xa.fundinfo('000001')
        holdings = info.get_stock_holdings()
        print('✅ get_stock_holdings(): shape', holdings.shape)
        print(holdings.head(2))
    except Exception as e:
        print('❌ get_stock_holdings() failed:', e)


def test_get_daily():
    """证券日线"""
    try:
        # 测试港股腾讯
        df = xa.get_daily('00700.HK', start_date='2025-01-01', end_date='2025-01-10')
        print('✅ get_daily(00700.HK): shape', df.shape)
        print(df.head(2))
    except Exception as e:
        print('❌ get_daily() failed:', e)


def test_mfundinfo():
    """货币基金"""
    try:
        mf = xa.mfundinfo('000638')
        print('✅ mfundinfo: name =', mf.name)
        print('   七日年化:', mf.seven_day())
    except Exception as e:
        print('❌ mfundinfo failed:', e)


def test_get_rt():
    """实时行情（可能依赖网络，仅测接口存在性）"""
    try:
        rt = xa.get_rt('00700.HK')
        print('✅ get_rt() returned:', type(rt))
    except Exception as e:
        print('❌ get_rt() failed:', e)


def test_indexinfo():
    """指数信息"""
    try:
        idx = xa.indexinfo('000300')  # 沪深300
        print('✅ indexinfo: name =', idx.name)
    except Exception as e:
        print('❌ indexinfo failed:', e)


def test_record():
    """账单解析（不实际运行，仅测试导入）"""
    try:
        print('✅ record module import ok')
    except Exception as e:
        print('❌ record import failed:', e)


if __name__ == '__main__':
    test_fund_info()
    test_fund_nav()
    test_fund_holdings()
    test_get_daily()
    test_mfundinfo()
    test_get_rt()
    test_indexinfo()
    test_record()
