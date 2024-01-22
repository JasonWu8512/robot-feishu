import requests
from django.conf import settings

from kevin.core import Kevin
from kevin.events import CommandEvent


@Kevin.command(Kevin("music").arg("keyword"))
def search_music(event: CommandEvent):
    """从网易云搜歌"""
    keyword = event.options.keyword
    url = "http://music.163.com/api/search/get/web"
    response = requests.post(
        url,
        data={"s": keyword, "type": "1", "offset": 0, "limit": 2, "total": "false"},
        headers={
            "Accept": "*/*",
            "Accept-Encoding": "gzip,deflate,sdch",
            "Accept-Language": "zh-CN,zh;q=0.8,gl;q=0.6,zh-TW;q=0.4",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "music.163.com",
            "Referer": "http://music.163.com/search/",
            "User-Agent": settings.KEVIN_USER_AGENT,
        },
    )
    songs = response.json()["result"]["songs"]
    if not songs:
        return event.error(f"没有找到关于 {keyword} 的歌")
    song = songs[0]
    song_id, name, artist, album = song["id"], song["name"], song["artists"][0]["name"], song["album"]["name"]
    return event.reply_text(f"请欣赏{artist}给大家带来一首《{name}》\n（来自专辑：《{album}》）\nhttps://music.163.com/#/song?id={song_id}")
