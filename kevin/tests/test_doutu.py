import pook

from kevin.tests.utils import KevinTest


class TestDoutu(KevinTest):
    def test_no_image(self):
        with pook.get("https://www.52doutu.cn/search/hello/"):
            response = self.send_text("/doutu hello")
        self.ok(response, message="Error:\n没有找到相关的表情包噢")

    def test_random_image(self):
        image_url = "https://somepic.sogoucdn.com/example.png"
        with pook.get(
            "https://www.52doutu.cn/search/hello/",
            response_body=f'<a href="{image_url}" />',
        ):
            response = self.send_text("/doutu hello")
        self.ok(response, message=image_url)
