from kevin.tests.utils import KevinTest


class TestExec(KevinTest):
    def test_exec(self):
        response = self.send_text("/exec print('hi')")
        self.ok(response, message="hi")

    def test_exception(self):
        response = self.send_text("/exec raise ValueError('ooh')")
        self.ok(response, type="error")
