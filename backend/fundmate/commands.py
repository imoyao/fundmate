# -*- coding: utf-8 -*-
"""Click commands."""
import os
from glob import glob
from pathlib import Path
from subprocess import call

import click

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
    see also:[How can I reuse the function that iv made as a command? · Issue #330 · pallets/click](https://github.com/pallets/click/issues/330) # noqa: F501
    :param drop:
    :return:
    """
    if drop:
        click.confirm(
            'This operation will delete the database, do you want to continue?',
            abort=True)
        db.drop_all()
    db.create_all()


@click.command()
@click.option('--drop',
              default=False,
              is_flag=True,
              help='Create databases after drop.')
def init_db(drop):
    """Initialized databases
    """
    check_before_create(drop=drop)


@click.command()
@click.option('--fund', default=True, help='Insert info of funds.')
@click.option('--mgr', default=True, help='Insert manger of funds.')
@click.option('--company', default=True, help='Insert company of funds.')
def create_db(fund, mgr, company):
    """Create data."""
    check_before_create(drop=True)


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
    help=
    "Don't make any changes to files, just confirm they are formatted correctly",
)
def lint(fix_imports, check):
    """Lint and check code style with black, flake8 and isort."""
    skip = [
        "node_modules", "requirements", "migrations", "tests", "__pycache__",
        "build", "dist", "venv"
    ]
    root_files = glob("*.py")
    root_directories = [
        name for name in next(os.walk("."))[1] if not name.startswith(".")
    ]
    files_and_directories = [
        arg for arg in root_files + root_directories if arg not in skip
    ]

    def execute_tool(description, *args):
        """Execute a checking tool with its arguments."""
        command_line = list(args) + files_and_directories
        click.echo(f"{description}: {' '.join(command_line)}")
        rv = call(command_line)
        if rv != 0:
            exit(rv)

    # TODO: 配置参数应该统一
    isort_args = []
    # black_args = []
    if check:
        isort_args.append("--check")
        # black_args.append("--check")
    if fix_imports:
        execute_tool("Fixing import order", "isort", *isort_args)
    # execute_tool("Formatting style", "black", *black_args)
    execute_tool("Checking code style", "flake8")
