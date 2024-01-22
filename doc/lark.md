# 飞书kevin机器人接入文档

## 1. 在飞书平台创建机器人

详细文档可以参考飞书[官方文档](https://open.feishu.cn/document/uQjL04CN/uYTMuYTMuYTM)

## 2. 配置kevin需要的环境变量

``` bash
# 飞书相关的配置都可以直接在飞书开放平台你创建的机器人应用里看见

export LARK_APP_ID="" # 飞书APP_ID
export LARK_APP_SECRET="" # 飞书APP_SECRET
export LARK_VERIFY_TOKEN="" # 飞书校验用的TOKE
export LARK_ENCRYPT_KEY=""# 飞书的消息加密密钥
export REDIS_URL="redis://127.0.0.1:6379/1" # 飞书机器人需要判断回调的唯一性，所以需要依赖redis
```

## 3. 启动kevin机器人

### docker 部署

``` bash
TODO
```

### k8s 部署

k8s的部署文件如下

``` yaml
---
kind: Namespace
apiVersion: v1
metadata:
  name: kevin
  labels:
    name: kevin
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  namespace: kevin
spec:
  replicas: 1
  revisionHistoryLimit: 3
  selector:
    matchLabels:
      app: kevin-web
  template:
    metadata:
      labels:
        app: kevin-web
    spec:
      containers:
        - name: web
          image: zaihuidev/kevin:code
          imagePullPolicy: Always
          command: ["python", "manage.py", "runserver", "0.0.0.0:8000"]
          env:
            - name: TZ
              value: "Asia/Shanghai"
            - name: LARK_APP_ID
              value: ""
            - name: LARK_APP_SECRET
              value: ""
            - name: LARK_VERIFY_TOKEN
              value: ""
            - name: LARK_ENCRYPT_KEY
              value: ""
            - name: REDIS_URL
              value: ""
          resources:
            limits:
              memory: 200Mi
            requests:
              memory: 100Mi
          ports:
            - containerPort: 8000
              name: web
---
apiVersion: v1
kind: Service
metadata:
  name: web
  namespace: kevin
spec:
  ports:
    - name: web
      port: 80
      targetPort: 8000
  selector:
    app: kevin-web
```

## 4. 在飞书后台设定机器人 `请求网址URL`

> 飞书后台设置的url就是kevin部署的域名/ip 加上 /endpoints/lark/
> 比如部署的地址是 `http://www.kevin.com`

> 那么在飞书的后台则需要配置成 `http://www.kevin.com/endpoints/lark/`

设置的位置可以参考下图

![lark1](https://user-images.githubusercontent.com/24697284/97655228-8ea17400-1a9f-11eb-93a4-18dd5bcec6b3.png)

## 5. 测试机器人

接下来就可以愉快找机器人玩耍啦

![lark2](https://user-images.githubusercontent.com/24697284/97655586-6a926280-1aa0-11eb-88d3-37d6dd9dee3a.png)
