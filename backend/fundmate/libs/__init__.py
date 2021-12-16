#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Created by imoyao at 2021/1/10 21:56
"""
该目录用于存放一些数据爬取中发现的有用的第三方仓库
基于控制项目空间大小和后期代码维护的目的，对于第三方模块的引入和使用基本遵循下面的规则：
1. 如果项目有可用包`pip install xx`，则直接安装；
2. 尽量不修改源码，如果实在要修改，尽量去源码提交pr；
3. 运行时的垃圾文件不要上传到git，避免仓库过大；
4. 如果必要，使用submodule，关于submodule的使用参考此文：[ submodule的使用方法_THEGREATHXY的博客-CSDN博客_submodule](https://blog.csdn.net/THEGREATHXY/article/details/113880095)
5. 如果时间充足，尽量保证项目经过测试可以跑通；
"""
