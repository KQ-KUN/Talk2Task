import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("talk2task", Path(__file__).parents[1] / "backend" / "app.py")
backend = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backend)


class LocalAppSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "instance" / "data.json"
        self.memo = self.data.with_name("memo.json")
        backend.DATA_FILE, backend.MEMO_FILE = str(self.data), str(self.memo)
        self.client = backend.app.test_client()
        self.headers = {"X-Talk2Task-Request": "1"}

    def test_home_serves_same_origin_frontend(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"async function apiFetch", response.data)
        response.close()

    def test_cross_origin_reads_are_denied(self):
        for origin in ["https://attacker.invalid", "null", "http://localhost:8000"]:
            with self.subTest(origin=origin):
                response = self.client.get("/api/history", headers={"Origin": origin})
                self.assertEqual(response.status_code, 403)
                self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_cross_site_fetch_is_denied_without_origin(self):
        for site in ["cross-site", "same-site"]:
            self.assertEqual(self.client.get("/api/history", headers={"Sec-Fetch-Site": site}).status_code, 403)

    def test_same_origin_read_is_allowed(self):
        self.assertEqual(self.client.get("/api/history", headers={"Origin": "http://localhost", "Sec-Fetch-Site": "same-origin"}).status_code, 200)

    def test_dns_rebinding_host_is_denied(self):
        for host in ["attacker.invalid", "127.0.0.1.attacker.invalid", "localhost.attacker.invalid"]:
            self.assertEqual(self.client.get("/api/history", headers={"Host": host}).status_code, 403)

    def test_remote_clients_are_denied(self):
        self.assertEqual(self.client.get("/api/history", environ_overrides={"REMOTE_ADDR": "192.0.2.1"}).status_code, 403)

    def test_cross_origin_write_and_preflight_are_denied(self):
        for method in ["POST", "OPTIONS", "DELETE"]:
            response = self.client.open("/api/memos", method=method, headers={**self.headers, "Origin": "https://attacker.invalid"}, json={"summary": "synthetic"})
            self.assertEqual(response.status_code, 403)
        self.assertFalse(self.memo.exists())

    def test_write_requires_custom_header(self):
        self.assertEqual(self.client.post("/api/memos", json={"summary": "synthetic"}).status_code, 403)
        self.assertEqual(self.client.delete("/api/history").status_code, 403)

    def test_json_shape_and_content_type_are_checked(self):
        self.assertEqual(self.client.post("/api/analyze", data="text=synthetic", headers=self.headers).status_code, 415)
        for body in [[], None, "text", 7]:
            self.assertEqual(self.client.post("/api/analyze", data=json.dumps(body), content_type="application/json", headers=self.headers).status_code, 400)
        self.assertEqual(self.client.post("/api/analyze", json={"text": 7}, headers=self.headers).status_code, 400)

    def test_memo_field_types_are_checked(self):
        for body in [{"summary": 7}, {"summary": "s", "tasks": "bad"}, {"summary": "s", "tasks": [7]}, {"summary": "s", "risks": [7]}]:
            self.assertEqual(self.client.post("/api/memos", json=body, headers=self.headers).status_code, 400)
        self.assertFalse(self.memo.exists())

    def test_request_size_is_bounded(self):
        response = self.client.post("/api/analyze", json={"text": "x" * (1024 * 1024)}, headers=self.headers)
        self.assertEqual(response.status_code, 413)
        self.assertFalse(self.data.exists())

    def test_normal_analyze_update_and_delete(self):
        response = self.client.post("/api/analyze", json={"text": "小明：明天提交测试报告"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        status = self.client.post("/api/tasks/status", json={"record_id": payload["record_id"], "task_id": payload["tasks"][0]["task_id"], "status": "已完成"}, headers=self.headers)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(self.client.get("/api/history").get_json()[0]["result"]["tasks"][0]["status"], "已完成")
        self.assertEqual(self.client.delete("/api/history", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get("/api/history").get_json(), [])

    def test_normal_memo_write_and_delete(self):
        response = self.client.post("/api/memos", json={"summary": "synthetic", "tasks": [], "risks": ["synthetic"]}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/memos").get_json()[0]["summary"], "synthetic")
        self.assertEqual(self.client.delete("/api/memos", headers=self.headers).status_code, 200)

    def test_invalid_status_does_not_modify_records(self):
        response = self.client.post("/api/tasks/status", json={"record_id": 1, "task_id": "synthetic", "status": "invalid"}, headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.data.exists())


if __name__ == "__main__":
    unittest.main()
