#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by Andy at 2021/12/10 17:36
from apiflask import HTTPError


class PetNotFound(HTTPError):
    """
    这是一个测试示例，还需要进一步改进
    """
    status_code = 404
    message = 'This pet is missing.'
    extra_data = {'error_code': '2323', 'error_docs': 'https://example.com/docs/missing'}
