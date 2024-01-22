# -*- coding: utf-8 -*-
# @Time    : 2020/10/27 3:59 下午
# @Author  : zoey
# @File    : fibfile.py
# @Software: PyCharm
from fabric.api import *

# 配置远程服务器
env.hosts = ["172.31.112.8"]
# 端口
env.port = "22"
# 用户
env.user = "deploy"
# 密码
env.password = "niuniuniu168"


@task
def deploy():
    run("uname -s")
    # run('echo niuniuniu168| sudo -S docker network create --gateway 172.16.1.1 --subnet 172.16.1.0/24 app_bridge')
    run("echo niuniuniu168| sudo -S docker pull harbor.jlgltech.com/qa/ace:latest")
    run("echo niuniuniu168| sudo -S docker stop $(sudo -S docker ps -a |grep ace |awk '{print $1}')")
    run("echo niuniuniu168| sudo -S docker rm -f $(sudo -S docker ps -a |grep ace |awk '{print $1}')")
    run(
        "echo niuniuniu168| sudo -S docker run --restart unless-stopped --network=host -v /home/deploy/log/ace:/home/deploy/log/ace -v /home/deploy/.ssh:/root/.ssh --name ace_server -p 8000:8000 -d harbor.jlgltech.com/qa/ace:latest /bin/bash deploy/deploy_server.sh"
    )
    run(
        "echo niuniuniu168| sudo -S docker run --restart unless-stopped --network=host -v /home/deploy/log/ace:/home/deploy/log/ace --name ace_worker -d harbor.jlgltech.com/qa/ace:latest /bin/bash deploy/deploy_worker.sh"
    )
    run(
        "echo niuniuniu168| sudo -S docker run --restart unless-stopped --network=host -v /home/deploy/log/ace:/home/deploy/log/ace --name ace_beat -d harbor.jlgltech.com/qa/ace:latest /bin/bash deploy/deploy_beat.sh"
    )
    run(
        "echo niuniuniu168| sudo -S docker run --restart unless-stopped --network=host -v /home/deploy/log/ace:/home/deploy/log/ace --name ace_flower -p 5555:5555 -d harbor.jlgltech.com/qa/ace:latest /bin/bash deploy/deploy_flower.sh"
    )
    run("echo niuniuniu168| sudo -S docker rmi $(sudo -S docker images |grep none |awk '{print $3}')")
