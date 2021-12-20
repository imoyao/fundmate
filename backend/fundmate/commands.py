# -*- coding: utf-8 -*-
"""Click commands."""
import os
from glob import glob
from pathlib import Path
from subprocess import call

import click

from backend.fundmate.data.eastmoney.base import em

from .database import db

CURRENT_PATH = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_PATH.parent
TEST_PATH = Path(PROJECT_ROOT, "tests")


@click.command()
def test():
    """Run the tests."""
    import pytest
    rv = pytest.main([str(TEST_PATH), "--verbose"])
    exit(rv)


def check_before_create(drop=False):
    """
    创建前先删除
    参阅：[How can I reuse the function that iv made as a command?
    · Issue #330 ·pallets/click](https://github.com/pallets/click/issues/330)
    :param drop:
    :return:
    """
    if drop:
        click.confirm('This operation will delete the database, do you want to continue?', abort=True)
        db.drop_all()
    db.create_all()


@click.command()
@click.option('--drop', default=False, is_flag=True, help='Create databases after drop.')
def init_db(drop):
    """Initialized databases
    """
    check_before_create(drop=drop)


@click.command()
@click.option('--company', default=False, is_flag=True, help='Update/Insert company of company.')
@click.option('--fund', default=False, is_flag=True, help='Update/Insert info of fund.')
@click.option('--mgr', default=False, is_flag=True, help='Update/Insert manger of funds manger.')
def update_db(fund, mgr, company):
    """update data of funds information.更新基金相关表
    [Options — Click Documentation (8.0.x)](https://click.palletsprojects.com/en/8.0.x/options/#boolean-flags)
    需要哪个参数就 `--xx`，如 `flask update-db --mgr`

    注意更新的表顺序：先有基金公司，然后创建基金，最后添加基金经理
    """
    if company:
        em.company(save=True)
    if fund:
        em.fund(save=True, format_='sql')
    if mgr:
        em.mgr(save=True, format_='sql')


@click.command()
@click.option(
    "-f",
    "--fix-imports",
    default=True,
    is_flag=True,
    help="Fix imports using isort, before linting",
)
@click.option(
    "-c",
    "--check",
    default=False,
    is_flag=True,
    help="Don't make any changes to files, just confirm they are formatted correctly",
)
def lint(fix_imports, check):
    """Lint and check code style with flake8 and isort."""
    skip = ["node_modules", "requirements", "migrations", "tests", "__pycache__", "build", "dist", "venv"]
    root_files = glob("*.py")
    root_directories = [name for name in next(os.walk("."))[1] if not name.startswith(".")]
    files_and_directories = [arg for arg in root_files + root_directories if arg not in skip]

    def execute_tool(description, *args):
        """Execute a checking tool with its arguments."""
        command_line = list(args) + files_and_directories
        click.echo(f"{description}: {' '.join(command_line)}")
        rv = call(command_line)
        if rv != 0:
            exit(rv)

    # TODO: isort配置参数应该统一
    isort_args = []
    # black_args = []
    if check:
        isort_args.append("--check")
        # black_args.append("--check")
    if fix_imports:
        execute_tool("Fixing import order", "isort", *isort_args)
    # execute_tool("Formatting style", "black", *black_args)
    execute_tool("Checking code style", "flake8")
