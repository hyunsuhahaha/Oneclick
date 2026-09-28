"""Docker 없이 도는 단위 테스트: 감지, 이름 정리, 저장소/롤백 대상 선택."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ["ONECLICK_HOME"] = tempfile.mkdtemp()

from oneclick import detect, source, store  # noqa: E402


def make(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    for name, body in files.items():
        (root / name).write_text(body, encoding="utf-8")
    return root


class DetectTest(unittest.TestCase):
    def test_dockerfile_wins(self):
        p = detect.detect(make({"Dockerfile": "FROM x", "package.json": "{}"}))
        self.assertEqual((p.framework, p.generated), ("dockerfile", False))

    def test_node_with_build(self):
        p = detect.detect(make({"package.json": '{"scripts":{"start":"x","build":"y"}}'}))
        self.assertEqual(p.framework, "node")
        self.assertIn("npm run build", p.dockerfile)

    def test_node_without_start(self):
        with self.assertRaises(detect.DetectError):
            detect.detect(make({"package.json": '{"scripts":{}}'}))

    def test_python_fastapi(self):
        p = detect.detect(make({"requirements.txt": "fastapi", "main.py": "app = FastAPI()"}))
        self.assertEqual(p.framework, "python-fastapi")
        self.assertIn("uvicorn main:app", p.dockerfile)

    def test_python_flask(self):
        p = detect.detect(make({"requirements.txt": "flask", "app.py": "app = Flask(__name__)"}))
        self.assertEqual(p.framework, "python-flask")
        self.assertIn("gunicorn", p.dockerfile)

    def test_static(self):
        self.assertEqual(detect.detect(make({"index.html": "<h1>hi"})).framework, "static")

    def test_unknown(self):
        with self.assertRaises(detect.DetectError):
            detect.detect(make({"README.md": "?"}))

    def test_examples(self):
        root = Path(__file__).parent.parent / "examples"
        self.assertEqual(detect.detect(root / "hello-node").framework, "node")
        self.assertEqual(detect.detect(root / "hello-python").framework, "python-fastapi")


class SourceTest(unittest.TestCase):
    def test_names(self):
        self.assertEqual(source.app_name_from("https://github.com/a/My_App.git"), "my-app")
        self.assertEqual(source.app_name_from("C:\\work\\123web"), "app-123web")
        self.assertTrue(source.is_git_url("git@github.com:a/b.git"))
        self.assertFalse(source.is_git_url("./examples/hello-node"))


class StoreTest(unittest.TestCase):
    def test_rollback_target_skips_current_image(self):
        def ship(image):
            rid = store.create_release("svc", "src")
            did = store.create_deployment(rid, "svc", "local")
            store.update_deployment(did, status=store.LIVE, image=image)
            store.supersede("svc", "local", did)
        ship("img:1")
        ship("img:2")
        self.assertEqual(store.previous_deployment("svc", "local")["image"], "img:1")
        ship("img:1")  # 롤백으로 img:1이 다시 LIVE
        self.assertEqual(store.previous_deployment("svc", "local")["image"], "img:2")

    def test_local_ports_are_stable(self):
        a, b = store.local_port("a"), store.local_port("b")
        self.assertNotEqual(a, b)
        self.assertEqual(store.local_port("a"), a)


if __name__ == "__main__":
    unittest.main()
