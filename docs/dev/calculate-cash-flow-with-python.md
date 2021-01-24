---
title: 使用 Python 计算你的现金流收益率
tag:
- IRR
- XIRR
---
> ——听说你理财了？
>
> ——巴菲特水平也就一般吧。
>
> ——听说你去年理财了？
>
> ——我他妈哪年不理财？查理·芒格书写得还行。
>
> ——听说你理财赚钱了？
>
> ——理了！你不想知道我的年化收益吗？
>
> ——对啊，多，多少呢？
>
> ——一个韭菜，碰上牛市，什么收益都能有！
>
> ——嘘……你这个不知道天高地厚的赌徒、小韭菜！
>
> ——你说什么？
>
> ——赌徒、韭菜！就是数据不够，要不然我非给你算明白了。
>
> ——好啊，来呀，看看你怎么算！你就只剩下一张嘴，写几行烂代码的臭码农！
>
> ——让韭菜飞


## 概念
> 注意: 现金流指定为负值、正值或零值。 使用这些函数时，请特别注意如何处理第一期开始时发生的即时现金流以及期初发生的所有其他现金流。

| 函数语法                  | 适用范围        | 备注   |
|------------------------------------|---------------------------------|-----------------------------------------------|
| NPV(rate,value1,[value2],...)   | 适用于定期（例如每月或每年）发生的现金流确定净现值。                          | 每个现金流（指定为`value`）都发生在一个周期的末尾。如果第一期开始时有额外的现金流，应添加到 NPV 函数返回的值。|
| XNPV(rate, values, dates) | 适用于以不规则时间间隔发生的现金流确定净现值。                             | 每个现金流（指定为`value`）在计划的付款日期发生。                                                                                                                                                                                                                                         |
| IRR(values,[guess])                     | 适用于定期（例如每月或每年）发生的现金流确定内部收益率。                        | 每个现金流（指定为`value`）都发生在一个周期的末尾。IRR 通过迭代搜索过程计算，该过程从 IRR 的估计开始（指定为猜测值）然后反复改变该值，直到达到正确的 IRR。 指定 guess 参数 是可选的;Excel 使用 10% 作为默认值。如果存在多个可接受的答案，则 IRR 函数仅返回找到的第一个答案。 如果 IRR 找不到任何答案，则返回#NUM！ 错误值。 如果出现错误或结果不是预期结果，请对 guess 使用不同的值。注意：如果存在多个可能的内部收益率，则不同的猜测可能会返回不同的结果。       |
| XIRR(values,dates,[guess])                 | 适用于以不规则时间间隔发生的现金流确定内部收益率。                           | 每个现金流（指定为`value`）在计划的付款日期发生。XIRR 通过迭代搜索过程计算，该过程以 IRR 的估计值开始（指定为 猜测 值）然后反复改变该值，直到达到正确的 XIRR。 指定 guess 参数 是可选的;Excel 使用 10% 作为默认值。如果存在多个可接受的答案，则 XIRR 函数仅返回找到的第一个答案。 如果 XIRR 找不到任何答案，则返回#NUM！ 错误值。 如果出现错误或结果不是预期结果，请对 guess 使用不同的值。注意：如果存在多个可能的内部收益率，则不同的猜测可能会返回不同的结果。 |
| MIRR(values,finance_rate,reinvest_rate) | 适用于定期发生的现金流（如每月或每年）确定修改的内部收益率，并考虑投资成本和在再投资现金时收到的利息。 | 每个指定为值的现金流都发生在一个期末，但第一个现金流除外，该现金流指定期初的值。在现金流中使用的资金所支付利率在finance_rate。 在现金流上重新投资时收到的利率在reinvest_rate。                                                                                                                                                            |

### IRR(Internal Rate of Return)

内部回报率（英文：internal rate of return，缩写：IRR）是一种投资的评估方法，也就是找出资产潜在的回报率，其原理是利用内部回报率折现，投资的净现值恰好等于零。内部收益率（IRR）衡量投资的收益率。 “内部”一词是指内部利率不包括外部因素，如通货膨胀，资本成本或各种金融风险。

#### 计算公式
![IRR](https://cdn.jsdelivr.net/gh/masantu/statics/images/mathpix 2021-01-23 10-49-56.png)



### XIRR 

返回一组不一定定期发生的现金流的内部收益率。

#### 计算公式

![XIRR](https://cdn.jsdelivr.net/gh/masantu/statics/images/mathpix 2021-01-23 10-51-09.png)

其中：

di = 第 i 个或最后一个支付日期。

d1 = 第 0 个支付日期。

Pi = 第 i 个或最后一个支付金额。
参见：[XIRR 函数 - Office 支持](https://support.microsoft.com/zh-cn/office/xirr-%E5%87%BD%E6%95%B0-de1242ec-6477-445b-b11b-a303ad9adc9d)

### NPV（Net Present Value）

## 参考链接
- [内部回报率 - 维基百科，自由的百科全书](https://zh.wikipedia.org/wiki/%E5%85%A7%E9%83%A8%E5%A0%B1%E9%85%AC%E7%8E%87)
-  [Go with the cash flow: Calculate NPV and IRR in Excel - Excel](https://support.microsoft.com/en-us/office/go-with-the-cash-flow-calculate-npv-and-irr-in-excel-9e3d78bb-f1de-4f8e-a20e-b8955851690c)
- [采用现金流：在 Excel 中计算 NPV 和 IRR - Excel](https://support.microsoft.com/zh-cn/office/%E9%87%87%E7%94%A8%E7%8E%B0%E9%87%91%E6%B5%81%EF%BC%9A%E5%9C%A8-excel-%E4%B8%AD%E8%AE%A1%E7%AE%97-npv-%E5%92%8C-irr-9e3d78bb-f1de-4f8e-a20e-b8955851690c)
- [Tacombel/XIRR.py: XIRR function for PYTHON](https://github.com/Tacombel/XIRR.py)
- [tarioch/xirr](https://github.com/tarioch/xirr/)
- [peliot/XIRR-and-XNPV: python implementation of Microsoft Excel's XNPV and XIRR](https://github.com/peliot/XIRR-and-XNPV)
- [XIRR: How to calculate your returns](https://www.indiainfoline.com/article/research-articles/xirr-how-to-calculate-your-returns-38115077_1.html)
- [financial python library that has xirr and xnpv function? - Stack Overflow](https://stackoverflow.com/questions/8919718/financial-python-library-that-has-xirr-and-xnpv-function)
- [计算XIRR_喜东东的博客-CSDN博客_xirr计算原理](https://blog.csdn.net/qq_34105362/article/details/89146711)
- [pandas - Calculating XIRR in Python - Stack Overflow](https://stackoverflow.com/questions/46668172/calculating-xirr-in-python)
- [RayDeCampo/nodejs-xirr: Compute the internal rate of return of a sequences of transactions made at irregular periods.](https://github.com/RayDeCampo/nodejs-xirr)
- [做时间的朋友，必须知道收益咋算 | Python技术](http://www.justdopython.com/2021/01/04/python-rate-of-return/)
- [Python数据分析_Numpy中的金融函数 - 简书](https://www.jianshu.com/p/9ad131856078)