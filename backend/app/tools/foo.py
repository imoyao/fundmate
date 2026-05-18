# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 13:14
# File : foo.py
# 将以下代码保存为 check_encoding.py，放在 backend/ 目录下
from charset_normalizer import detect

file_path = input('请输入文件的完整路径（可直接拖拽文件到此处）: ').strip().strip('"')
try:
    with open(file_path, 'rb') as f:
        raw_data = f.read()
    result = detect(raw_data)
    print(f'自动检测结果: {result}')
except Exception as e:
    print(f'读取失败: {e}')
