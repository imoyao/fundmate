#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/15 11:34

# Copyright (c) 2012 Sutoiku, Inc. (MIT License)

# Some algorithms have been ported from Apache OpenOffice:

# /**************************************************************
#  *
#  * Licensed to the Apache Software Foundation (ASF) under one
#  * or more contributor license agreements.  See the NOTICE file
#  * distributed with this work for additional information
#  * regarding copyright ownership.  The ASF licenses this file
#  * to you under the Apache License, Version 2.0 (the
#  * "License"); you may not use this file except in compliance
#  * with the License.  You may obtain a copy of the License at
#  *
#  *   http://www.apache.org/licenses/LICENSE-2.0
#  *
#  * Unless required by applicable law or agreed to in writing,
#  * software distributed under the License is distributed on an
#  * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#  * KIND, either express or implied.  See the License for the
#  * specific language governing permissions and limitations
#  * under the License.
#  *
#  *************************************************************/
"""
see also:
- [Tacombel/XIRR.py: XIRR function for PYTHON](https://github.com/Tacombel/XIRR.py)
- [tarioch/xirr](https://github.com/tarioch/xirr/)
- [peliot/XIRR-and-XNPV: python implementation of Microsoft Excel's XNPV and XIRR](https://github.com/peliot/XIRR-and-XNPV)
- [XIRR: How to calculate your returns](https://www.indiainfoline.com/article/research-articles/xirr-how-to-calculate-your-returns-38115077_1.html)
- [financial python library that has xirr and xnpv function? - Stack Overflow](https://stackoverflow.com/questions/8919718/financial-python-library-that-has-xirr-and-xnpv-function)
- [计算XIRR_喜东东的博客-CSDN博客_xirr计算原理](https://blog.csdn.net/qq_34105362/article/details/89146711)
- [pandas - Calculating XIRR in Python - Stack Overflow](https://stackoverflow.com/questions/46668172/calculating-xirr-in-python)
test:
- [RayDeCampo/nodejs-xirr: Compute the internal rate of return of a sequences of transactions made at irregular periods.](https://github.com/RayDeCampo/nodejs-xirr)

"""


class XIRR:
    """
    Credits: algorithm inspired by Apache OpenOffice
    """

    @staticmethod
    def years_between_dates(date1, date2):
        delta = date2 - date1
        return delta.days / 365

    def irr_result(self, values, dates, rate):
        """

        # Calculates the resulting amount
        :param values:
        :param dates:
        :param rate:
        :return:
        """
        r = rate + 1
        result = values[0]
        for i in range(1, len(values)):
            result = result + values[i] / pow(r, self.years_between_dates(dates[0], dates[i]))
            i += 1
        return result

    def first_derivation(self, values, dates, rate):
        """
        Calculates the first derivation
        :param values:
        :param dates:
        :param rate:
        :return:
        """
        r = rate + 1
        result = 0
        for i in range(1, len(values)):
            frac = self.years_between_dates(dates[0], dates[i])
            result = result - frac * values[i] / pow(r, frac + 1)
            i += 1
        return result

    def xirr(self, values, dates):
        """
        Check that values contains at least one positive value and one negative value
        [pandas - Python IRR Function giving different result than Excel XIRR - Stack Overflow](https://stackoverflow.com/questions/63797804/python-irr-function-giving-different-result-than-excel-xirr)
        :param values:
        :param dates:
        :return:
        """
        positive = False
        negative = False
        for v in values:
            if v > 0:
                positive = True
            if v < 0:
                negative = True

        # Return error if values does not contain at least one positive value and one negative value
        if not (positive and negative):
            return 'Error'
        # Initialize guess and resultRate
        guess = 0.1
        resultRate = guess

        # Set maximum epsilon for end of iteration
        epsMax = 1e-10

        # Set maximum number of iterations
        iterMax = 20

        # Implement Newton's method
        iteration = 0
        contLoop = True
        while contLoop and (iteration < iterMax):
            resultValue = self.irr_result(values, dates, resultRate)
            newRate = resultRate - (resultValue / self.first_derivation(values, dates, resultRate))
            epsRate = abs(newRate - resultRate)
            resultRate = newRate
            if resultRate < -1:
                resultRate = -0.999999999
            contLoop = (epsRate > epsMax) and (abs(resultValue) > epsMax)
            iteration += 1
        if contLoop:
            return epsRate > epsMax, epsRate, 'iterMax'
        return resultRate
