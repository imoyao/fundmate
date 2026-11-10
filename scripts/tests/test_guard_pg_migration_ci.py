#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归网：``scripts/guard_pg_migration_ci.py``（CI 真 PG 迁移验证接线守卫）。

覆盖：真实仓库接线成立、``--self-test`` 4 态变异自检自身通过、五类结构化变异必红、
输入不可信（ci.yml 缺失 / 用例缺失）必为 exit 2。

变异一律走 YAML 结构化改写再 dump，不依赖缩进文本；每个探针先断言「变异真的落盘」
（基线 check 为空且变异后非空），避免 #2739「变异没应用、用例全绿」的假象。
"""

from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARD = REPO / 'scripts' / 'guard_pg_migration_ci.py'
CI_REL = '.github/workflows/ci.yml'
PG_TEST_REL = 'backend/tests/core/test_migrations_positions_state_check_pg.py'


def _load_guard():
    spec = importlib.util.spec_from_file_location('guard_pg_migration_ci_under_test', GUARD)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GuardOnRealRepoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.guard = _load_guard()

    def test_real_repo_passes(self) -> None:
        self.assertEqual(self.guard.check(REPO), [])
        self.assertEqual(self.guard.run(REPO), 0)

    def test_self_test_passes(self) -> None:
        self.assertEqual(self.guard.self_test(), 0)


class MutationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.guard = _load_guard()
        cls.ci_text = (REPO / CI_REL).read_text(encoding='utf-8')
        cls.test_text = (REPO / PG_TEST_REL).read_text(encoding='utf-8')

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, data: dict, *, test_text: str | None = None, comment: str = '') -> None:
        (self.root / '.github' / 'workflows').mkdir(parents=True, exist_ok=True)
        (self.root / 'backend' / 'tests' / 'core').mkdir(parents=True, exist_ok=True)
        rendered = yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + comment
        (self.root / CI_REL).write_text(rendered, encoding='utf-8')
        (self.root / PG_TEST_REL).write_text(test_text if test_text is not None else self.test_text, encoding='utf-8')

    def _baseline_data(self) -> dict:
        return yaml.safe_load(self.ci_text)

    def _probe(self, mutate, *, test_text: str | None = None, comment: str = '') -> None:
        data = self._baseline_data()
        mutate(data['jobs']['backend'])
        self._write(data, test_text=test_text, comment=comment)
        errors = self.guard.check(self.root)
        self.assertTrue(errors, '变异后守卫仍绿：接线被删/被掏空却没咬住')

    def test_clone_baseline_is_green(self) -> None:
        self._write(self._baseline_data())
        self.assertEqual(self.guard.check(self.root), [], '最小克隆本身要先绿')

    def test_drop_postgres_service_is_red(self) -> None:
        self._probe(lambda job: job.pop('services', None))

    def test_comment_cannot_impersonate_service(self) -> None:
        self._probe(
            lambda job: job.pop('services', None),
            comment='# services:\n#   postgres:\n#     image: postgres:16-alpine\n',
        )

    def test_drop_pg_step_is_red(self) -> None:
        self._probe(
            lambda job: job.update(
                steps=[s for s in job['steps'] if self.guard.PG_TEST_NAME not in str(s.get('run', ''))]
            )
        )

    def test_gutted_pg_test_is_red(self) -> None:
        self._probe(
            lambda job: None,
            test_text='# create_engine / IntegrityError / get_check_constraints 只写在注释里\n',
        )

    def test_module_level_unconditional_skip_is_red(self) -> None:
        self._probe(lambda job: None, test_text=self.test_text + "\npytest.skip('always')\n")

    def test_url_moved_to_job_level_is_red(self) -> None:
        """URL 挂到 job 级会让常规 -n auto 分片并发跑真 PG 用例。"""

        def move(job):
            for step in job['steps']:
                if self.guard.PG_TEST_NAME in str(step.get('run', '')):
                    url = (step.pop('env', None) or {}).get('TEST_POSTGRES_URL', '')
                    job['env'] = {'TEST_POSTGRES_URL': url}
                    break

        self._probe(move)

    def test_missing_ci_is_exit2(self) -> None:
        (self.root / '.github' / 'workflows').mkdir(parents=True, exist_ok=True)
        (self.root / 'backend' / 'tests' / 'core').mkdir(parents=True, exist_ok=True)
        (self.root / PG_TEST_REL).write_text(self.test_text, encoding='utf-8')
        self.assertEqual(self.guard.run(self.root), 2)

    def test_missing_pg_test_is_red(self) -> None:
        self._write(self._baseline_data())
        (self.root / PG_TEST_REL).unlink()
        self.assertTrue(self.guard.check(self.root))


if __name__ == '__main__':
    unittest.main()
