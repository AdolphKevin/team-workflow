"""方案解析使用调用方提供的场景数据，文件选择由调用方负责。"""
import os
import tempfile
import unittest

from test_designs import example
import designs
import plan_fixtures as plans


class DesignLoaderPurityCases(unittest.TestCase):
    def test_load_requires_explicit_scenario_reader(self):
        raw = designs.render(example())
        with self.assertRaisesRegex(TypeError, 'scenario_reader'):
            designs.load(raw)

    def test_explicit_fixture_reader_works_from_an_empty_directory(self):
        expected = example()
        raw = designs.render(expected)
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                self.assertEqual(designs.load(raw, scenario_reader=plans.scenario_reader), expected)
            finally:
                os.chdir(previous)
