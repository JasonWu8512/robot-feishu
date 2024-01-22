import json
import statistics
from calendar import monthrange
from datetime import datetime
from time import gmtime, strftime

import redis
from django.conf import settings
from pandas import to_datetime

from kevin.core import Kevin
from kevin.events import CommandEvent


@Kevin.command(
    Kevin("clock", intro="记录打卡时间")
    .arg("insert_clock", nargs="*", default=[], help="插入指定日期格式 Y-m-d H:M:S ; 插入今日格式 H:M:S ")
    .arg("--month", "-m", nargs="+", default=[], help="查询指定月份打卡时间格式 Y-m")
    .arg("--current_month", "-cm", action="store_true", help="查询当前月份打卡时间")
    .arg("--remove", "-r", nargs="+", default=[], help="移除指定日期格式 Y-m-d H:M:S ; 移除今日格式 H:M:S ")
)
def clock_in_work_hours(event: CommandEvent):
    """ 记录打卡时间 """
    insert_clock = " ".join(event.options.insert_clock)
    month = " ".join(event.options.month)
    current_month = event.options.current_month
    remove_clock = " ".join(event.options.remove)

    redis_client = redis.from_url(settings.REDIS_URL)
    filter_date = datetime.now().strftime("%Y-%m") if current_month else month
    if filter_date:
        datetime.strptime(filter_date, "%Y-%m")  # 日期校验
        redis_key = f"{event.open_id}_{filter_date}"
        work_hours = json.loads(redis_client.get(redis_key) or "{}")
        msg = ""
        valid_hours = []
        for day in range(monthrange(*[int(i) for i in filter_date.split("-")])[1] + 1)[1:]:
            date = f"{filter_date}-{'%02d' % day}"
            hours = work_hours.get(date)
            if not hours:
                continue
            start_time, end_time = datetime.strptime(hours[0], "%H:%M:%S"), datetime.strptime(hours[-1], "%H:%M:%S")
            hour = (end_time - start_time).seconds
            if start_time == end_time:
                msg += f"{date}: 一条上/下班记录{hours[0]}，可手动补充上/下班时间\n"
            else:
                msg += f"{date}: 上班: {hours[0]}, 下班: {hours[-1]}, 时长: {strftime('%Hh%Mm%Ss', gmtime(hour))}\n"
                valid_hours.append(hour)
        if valid_hours:
            msg += f"\n当月有效记录上班天数为{len(valid_hours)}天，平均工时{round(statistics.fmean(valid_hours)/3600, 2)}小时"
        else:
            msg += f"当月暂无有效工时"
    elif remove_clock:
        remove_clock = to_datetime(remove_clock)  # 日期校验
        redis_key = f"{event.open_id}_{remove_clock.strftime('%Y-%m')}"
        work_hours = json.loads(redis_client.get(redis_key) or "{}")
        remove_day = remove_clock.strftime("%Y-%m-%d")
        remove_data = work_hours.get(remove_day, [])
        try:
            remove_data.remove(remove_clock.strftime("%H:%M:%S"))
        except ValueError:
            pass
        remove_data.sort()
        work_hours.update({remove_day: remove_data})
        redis_client.set(redis_key, json.dumps(work_hours))
        msg = f"移除成功! {remove_day}现记录{remove_data}时间点"
    else:
        insert_clock = to_datetime(insert_clock) if insert_clock else datetime.now()
        redis_key = f"{event.open_id}_{insert_clock.strftime('%Y-%m')}"
        work_hours = json.loads(redis_client.get(redis_key) or "{}")
        insert_day = insert_clock.strftime("%Y-%m-%d")
        insert_data = work_hours.get(insert_day, [])
        insert_data.append(insert_clock.strftime("%H:%M:%S"))
        insert_data.sort()
        work_hours.update({insert_day: insert_data})
        redis_client.set(redis_key, json.dumps(work_hours))
        msg = f"记录成功! {insert_day} {insert_clock.strftime('%H:%M:%S')}"
    return event.reply_text(msg)
