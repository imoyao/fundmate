# -*- coding: utf-8 -*-
"""
@Time ： 2022/9/27 14:23
@File ：test_command.py
@IDE ：PyCharm
参阅：https://github.com/pallets/flask/blob/main/tests/test_cli.py
"""

import pytest

from backend.fundmate.commands import init_db


@pytest.mark.parametrize('is_drop,is_confirm', [('--drop', 'n'), ('--drop', 'y'), (None, 'y'), (None, 'n')])
def test_init_db(runner, is_drop, is_confirm):
    """
    FIXME:如何引入app使 assert result.exit_code == 0
    """
    if is_drop:
        is_drop_args = [is_drop]
    else:
        is_drop_args = None
    result = runner.invoke(init_db, is_drop_args, input=is_confirm)
    if is_drop:
        if is_confirm == 'n':
            assert result.output.endswith('Aborted!\n')
        assert 'This operation will delete the database' in result.output
    else:
        assert result.output == ''
