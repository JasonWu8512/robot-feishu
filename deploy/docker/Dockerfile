FROM harbor.jlgltech.com/qa/python3.8:latest

LABEL Name="ace"

ENV prod true

EXPOSE 8000

WORKDIR /home/deploy/ace

RUN pip install pipenv -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

COPY Pipfile Pipfile.lock ./

RUN pipenv install --system --deploy

COPY . .

LABEL Name="ace"
