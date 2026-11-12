"""模块边界检查的本地回归测试，不依赖服务或数据库。"""
import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("independence_check.py")
spec = importlib.util.spec_from_file_location("independence_check", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class CrossModuleReferencesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SCRIPT.parent.parent)
        self.root = Path(self.temp.name)
        self.old_root = checker.ROOT
        checker.ROOT = self.root
        self.addCleanup(self.cleanup_root)

    def cleanup_root(self):
        checker.ROOT = self.old_root
        self.temp.cleanup()

    def references(self, module, filename, source):
        path = self.root / module / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return checker.cross_module_references(path, module)

    def test_detects_both_directions_and_reference_forms(self):
        cases = [
            ("zg-tsp-web", "a.ts", "import x from '../zg-tsp-server/app/x';"),
            ("zg-tsp-web", "a.ts", "const x = require('../zg-tsp-server/app/x');"),
            ("zg-tsp-web", "a.ts", "const x = import('../zg-tsp-server/app/x');"),
            ("zg-tsp-web", "a.ts", "const path = '../zg-tsp-server/app/x';"),
            ("zg-tsp-web", "src/a.ts", "import x from '../../zg-tsp-server/app/x';"),
            ("zg-tsp-server", "a.py", "from web.src import thing\n"),
            ("zg-tsp-server", "a.py", "import zg_tsp_web.src\n"),
            ("zg-tsp-server", "a.py", "open('../zg-tsp-web/src/x')\n"),
        ]
        for module, filename, source in cases:
            with self.subTest(source=source):
                self.assertTrue(self.references(module, filename, source))

    def test_ignores_comments_docstrings_and_unrelated_names(self):
        cases = [
            ("zg-tsp-web", "a.ts", "// import x from '../zg-tsp-server/a'\n/*\n import '../zg-tsp-server/a'\n*/\nconst server = '/api';"),
            ("zg-tsp-web", "a.ts", "const url = 'https://example.com/'; // ../zg-tsp-server/a\nconst x = '../zg-tsp-server-extra/a';"),
            ("zg-tsp-server", "a.py", '"""import zg_tsp_web and ../zg-tsp-web/src"""\n# from web import x\nweb = "local"\n'),
            ("zg-tsp-server", "a.py", "from .web import local\n"),
            ("zg-tsp-web", "src/pages/a.ts", "const msg = 'contact zg-tsp-server for help';"),
            ("zg-tsp-web", "src/pages/a.ts", "const url = 'https://example.com/zg-tsp-server/api';"),
            ("zg-tsp-web", "src/pages/a.ts", "import api from '../server/api';"),
        ]
        for module, filename, source in cases:
            with self.subTest(source=source):
                self.assertFalse(self.references(module, filename, source))

    def test_main_reports_cross_module_failure(self):
        fixtures = {
            'zg-tsp-server/requirements.txt': '',
            'zg-tsp-web/package.json': '{}',
            'zg-tsp-server/.env.example': '',
            'zg-tsp-web/.env.production': '',
            'zg-tsp-server/Dockerfile': '',
            'zg-tsp-web/Dockerfile': '',
            'zg-tsp-web/src/api/client.ts': 'ServiceUnavailableError',
            'zg-tsp-server/app/main.py': 'route = "/health"',
            'zg-tsp-web/src/bad.ts': "import '../../zg-tsp-server/app/main';",
        }
        for name, content in fixtures.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        checker.results.clear()
        self.addCleanup(checker.results.clear)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(checker.main(), 1)
        self.assertIn('源码中无跨模块 import / 路径引用', output.getvalue())
        self.assertIn('bad.ts', output.getvalue())

    def test_multiline_import_and_inline_comment(self):
        source = "import {\n  x\n} from '../zg-tsp-server/app'; // explanation\n"
        self.assertTrue(self.references("zg-tsp-web", "a.ts", source))


if __name__ == "__main__":
    unittest.main()
