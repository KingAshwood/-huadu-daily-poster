# -*- coding: utf-8 -*-
"""华都 · 每日行业资讯网页生成脚本（云端版，海报 + 新闻合一页，手机优先）
读取 data/news.json（[{"title","desc","source","url"} ×10]，source/url 可选），
结合 docs/latest.png 生成：
  docs/index.html      —— 始终指向最新一天（手机收藏这个链接即可）
  docs/YYYY-MM-DD.html —— 当日存档页
页面结构：头部 → 今日海报（长按可保存）→ 10 条新闻卡片（有链接的带「阅读原文」）→ 页脚。
用法：python scripts/gen_news_page.py [YYYY-MM-DD]  （缺省用北京时间当天日期）
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 仓库根目录
NEWS_JSON = os.path.join(BASE, "data", "news.json")
DOCS_DIR = os.path.join(BASE, "docs")
os.makedirs(DOCS_DIR, exist_ok=True)

DEEP_BLUE = "#182E50"
GOLD = "#C9A86A"
TEXT_DARK = "#282E3A"
TEXT_GRAY = "#6E7582"
CARD_BG = "#F6F8FB"

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;
       background:#EEF1F5; color:%(dark)s; -webkit-font-smoothing:antialiased; }
.header { background:%(blue)s; padding:34px 20px 26px; border-bottom:4px solid %(gold)s; }
.header h1 { color:#fff; font-size:26px; letter-spacing:1px; }
.header .sub { color:%(gold)s; font-size:12px; letter-spacing:3px; margin-top:6px; }
.header .date { color:#D2DCEB; font-size:13px; margin-top:14px; }
.wrap { max-width:640px; margin:0 auto; }
.poster { padding:16px 14px 4px; }
.poster .tip { text-align:center; font-size:13px; color:%(gold)s; font-weight:600;
               background:#fff; border:1px dashed %(gold)s; border-radius:10px;
               padding:9px 10px; margin-bottom:10px; }
.poster img { display:block; width:100%%; height:auto; border-radius:12px;
              box-shadow:0 2px 8px rgba(24,46,80,.15); }
.list { padding:16px 14px 8px; }
.sect { font-size:18px; font-weight:700; color:%(blue)s; padding:6px 2px 10px; }
.card { background:#fff; border-radius:12px; padding:16px 16px 14px; margin-bottom:12px;
        box-shadow:0 1px 3px rgba(24,46,80,.08); }
.card .no { display:inline-block; color:%(gold)s; font-weight:700; font-size:14px; }
.card h2 { font-size:17px; line-height:1.45; margin:4px 0 8px; }
.card p { font-size:14px; line-height:1.75; color:%(gray)s; }
.card .meta { margin-top:10px; display:flex; justify-content:space-between; align-items:center; }
.card .src { font-size:12px; color:%(gray)s; background:%(cardbg)s; padding:3px 10px; border-radius:10px; }
.card a { font-size:13px; color:%(blue)s; font-weight:600; text-decoration:none; }
.tip { text-align:center; font-size:12px; color:%(gray)s; padding:4px 0 18px; }
.footer { background:%(blue)s; color:#fff; text-align:center; padding:22px 16px 26px; border-top:4px solid %(gold)s; }
.footer .co { font-size:15px; font-weight:700; }
.footer .slogan { color:%(gold)s; font-size:12px; margin-top:6px; letter-spacing:2px; }
""" % {"blue": DEEP_BLUE, "gold": GOLD, "dark": TEXT_DARK, "gray": TEXT_GRAY, "cardbg": CARD_BG}


def render(news, date_str, week):
    items = []
    for i, it in enumerate(news, 1):
        if it.get("url"):
            link = '<a href="%s" target="_blank" rel="noopener">阅读原文 →</a>' % it["url"]
        else:
            link = ""
        src_tag = ('<span class="src">%s</span>' % it["source"]) if it.get("source") else ""
        items.append(
            '<div class="card"><span class="no">%02d</span>'
            '<h2>%s</h2><p>%s</p>'
            '<div class="meta">%s%s</div></div>'
            % (i, it["title"], it["desc"], src_tag, link))
    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>华都每日行业资讯 · %s</title>
<style>%s</style></head><body>
<div class="header"><div class="wrap">
<h1>每日行业资讯</h1><div class="sub">DAILY INDUSTRY BRIEFING</div>
<div class="date">%s · %s · 每日精选 专人整理</div>
</div></div>
<div class="poster wrap">
<div class="tip">👇 今日海报（长按图片即可保存 / 转发同事群）</div>
<img src="latest.png" alt="今日行业资讯海报">
</div>
<div class="list wrap"><div class="sect">今日要闻</div>%s</div>
<div class="tip">点击「阅读原文」查看各家媒体报道全文</div>
<div class="footer"><div class="co">河南华都柜业集团有限公司</div>
<div class="slogan">专注钢制家具 35 年</div></div>
</body></html>""" % (date_str, CSS, date_str, week, "".join(items))


def main():
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
    else:
        date_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    week = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
        datetime.strptime(date_str, "%Y-%m-%d").weekday()]
    with open(NEWS_JSON, encoding="utf-8") as f:
        news = json.load(f)
    html = render(news, date_str, week)
    day_path = os.path.join(DOCS_DIR, "%s.html" % date_str)
    with open(day_path, "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("已生成：%s" % day_path)
    print("已生成：docs/index.html（%s 版）" % date_str)


if __name__ == "__main__":
    main()
