# -*- coding: utf-8 -*-
"""海报生成后推送到钉钉群机器人（可选）
环境变量：
  DINGTALK_WEBHOOK  群机器人 Webhook 地址（必填才推送）
  DINGTALK_SECRET   加签密钥（机器人选了「加签」安全设置时必填）
  PAGES_BASE_URL    Pages 固定链接（可选，默认按仓库名推算）
消息含关键词「行业资讯」，兼容机器人「自定义关键词」安全设置。
"""
import os
import sys
import json
import time
import hmac
import hashlib
import base64
import urllib.parse
import urllib.request

REPO = os.environ.get("REPO", "")
WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "").strip()
SECRET = os.environ.get("DINGTALK_SECRET", "").strip()

owner = REPO.split("/")[0] if REPO else "kingashwood"
repo_name = REPO.split("/")[1] if "/" in REPO else "-huadu-daily-poster"
BASE = os.environ.get("PAGES_BASE_URL",
                      "https://%s.github.io/%s" % (owner.lower(), repo_name)).rstrip("/")
IMG_URL = BASE + "/latest.png"
PAGE_URL = BASE + "/"

if not WEBHOOK:
    print("未配置 DINGTALK_WEBHOOK，跳过钉钉推送")
    sys.exit(0)

url = WEBHOOK
if SECRET:
    ts = str(round(time.time() * 1000))
    sign_str = "%s\n%s" % (ts, SECRET)
    sign = base64.b64encode(hmac.new(SECRET.encode(), sign_str.encode(),
                                     hashlib.sha256).digest())
    url += "&timestamp=%s&sign=%s" % (ts, urllib.parse.quote_plus(sign))

md = ("### 华都 · 每日行业资讯已更新\n\n"
      "![今日海报](%s)\n\n"
      "手机端点开图片可长按保存转发；固定链接：%s\n\n"
      "—— 每日行业资讯 · 河南华都柜业集团" % (IMG_URL, PAGE_URL))

body = json.dumps({
    "msgtype": "markdown",
    "markdown": {"title": "行业资讯海报已更新", "text": md},
}).encode("utf-8")

req = urllib.request.Request(url, data=body,
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        resp = json.load(r)
    if resp.get("errcode") == 0:
        print("钉钉推送成功")
    else:
        print("钉钉返回异常:", resp)
        sys.exit(1)
except Exception as e:
    print("钉钉推送失败:", e)
    sys.exit(1)
