# -*- coding: utf-8 -*-
"""云端每日行业新闻采集脚本（三源融合）
数据源（按可用性自动融合，哪个通用哪个）：
  1. 新浪财经滚动新闻 API（国内/国外均可达，JSON）
  2. Bing 新闻 RSS（GitHub 美国服务器可达，按行业关键词精准检索）
  3. Google News RSS（GitHub 美国服务器可达，按行业关键词精准检索）
逻辑：抓取 → 关键词加权过滤 → 去重 → 取 10 条
可选：配置 DEEPSEEK_API_KEY（或 OPENAI_API_KEY）环境变量后，
     调用大模型对候选新闻精选润色，输出质量与人工整理版一致。
安全写入：当日抓取不足 5 条时保留昨日 news.json（海报版式永不中断）。
输出：data/news.json，格式 [{"title":..,"desc":..} ×10]
"""
import os
import re
import json
import html
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE), "data")
os.makedirs(DATA_DIR, exist_ok=True)
OUT_PATH = os.path.join(DATA_DIR, "news.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 15

# ---------- 检索词（行业定制：钢制家具外贸 + 跨境物流 + 政策） ----------
QUERIES = [
    "钢制家具 出口", "办公家具 外贸", "家具 出口 订单",
    "集装箱 运价", "海运 美线 运价", "港口 拥堵 船期",
    "外贸 出口 政策", "跨境电商 海外仓", "出口 退税",
]

# 行业关键词加权
WEIGHTS = {
    "钢制家具": 5, "储物柜": 5, "文件柜": 5, "工具柜": 5, "更衣柜": 5, "保险柜": 3,
    "办公家具": 4, "家具出口": 5, "家具": 2, "洛阳": 3, "伊滨": 4, "庞村": 5,
    "运价": 4, "集装箱": 4, "SCFI": 5, "海运费": 4, "美线": 3, "美西": 3, "美东": 3,
    "港口": 3, "船期": 3, "拥堵": 3, "巴拿马": 3,
    "外贸": 3, "出口": 2, "退税": 4, "关税": 4, "海外仓": 4, "跨境": 3,
    "亚马逊": 3, "订单": 2, "订舱": 3, "报关": 3,
}

# 噪音标题过滤
NOISE = re.compile(r"彩票|双色球|股票.*涨停|明星|电视剧|游戏|娱乐|健康|养生|房产.*售")


def http_get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_sina(num_per_page=50, pages=2):
    """新浪财经滚动新闻，返回原始条目"""
    items = []
    for page in range(1, pages + 1):
        url = ("https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516"
               "&num=%d&page=%d" % (num_per_page, page))
        try:
            d = json.loads(http_get(url))
            for it in d.get("result", {}).get("data", []):
                title = (it.get("title") or "").strip()
                intro = re.sub(r"<[^>]+>", "", it.get("intro") or "").strip()
                ctime = it.get("ctime")
                pub = ""
                if ctime:
                    try:
                        pub = time.strftime(
                            "%a, %d %b %Y %H:%M:%S GMT",
                            time.gmtime(int(ctime)),
                        )
                    except Exception:
                        pub = ""
                if title:
                    items.append({"title": title, "desc": intro, "link": it.get("url", ""),
                                  "pubDate": pub})
        except Exception as e:
            print("新浪抓取失败:", e)
    return items


def fetch_bing_news(query, limit=15):
    url = "https://www.bing.com/news/search?q=%s&format=RSS" % urllib.parse.quote(query)
    try:
        root = ET.fromstring(http_get(url))
        items = []
        for item in root.iter("item"):
            title = html.unescape((item.findtext("title") or "").strip())
            desc = html.unescape((item.findtext("description") or "").strip())
            desc = re.sub(r"<[^>]+>", "", desc).strip()
            if title:
                items.append({"title": title, "desc": desc,
                              "link": (item.findtext("link") or "").strip(),
                              "pubDate": (item.findtext("pubDate") or "").strip()})
        return items[:limit]
    except Exception as e:
        print("Bing 抓取失败 [%s]: %s" % (query, e))
        return []


def fetch_google_news(query, limit=15):
    url = ("https://news.google.com/rss/search?q=%s&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
           % urllib.parse.quote(query))
    try:
        root = ET.fromstring(http_get(url))
        items = []
        for item in root.iter("item"):
            title = html.unescape((item.findtext("title") or "").strip())
            if title:
                items.append({"title": title, "desc": "",
                              "link": (item.findtext("link") or "").strip(),
                              "pubDate": (item.findtext("pubDate") or "").strip()})
        return items[:limit]
    except Exception as e:
        print("Google 抓取失败 [%s]: %s" % (query, e))
        return []


def score(item):
    text = item["title"] + item["desc"]
    if NOISE.search(text):
        return -100
    s = 0
    for kw, w in WEIGHTS.items():
        if kw in text:
            s += w
        if kw in item["title"]:
            s += w
    # 时效性：36 小时内加分
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(item["pubDate"])
        age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        if age_h <= 36:
            s += 6
        elif age_h <= 72:
            s += 3
        elif age_h > 7 * 24:
            s -= 5
    except Exception:
        pass
    return s


def dedupe(items):
    seen = set()
    out = []
    for it in items:
        key = re.sub(r"\s", "", it["title"])[:24]
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def clean_desc(desc, max_len=90):
    desc = re.sub(r"\s+", " ", desc).strip()
    if len(desc) > max_len:
        desc = desc[: max_len - 1].rstrip("，、；,; ") + "…"
    return desc


def llm_curate(candidates):
    """可选：调用大模型精选 10 条（OpenAI 兼容接口，默认 DeepSeek）"""
    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key or len(candidates) < 12:
        return None
    base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("LLM_MODEL", "deepseek-chat")
    lines = ["%d. [%s] %s" % (i + 1, c["pubDate"][:16], c["title"] + " —— " + c["desc"])
             for i, c in enumerate(candidates[:40])]
    prompt = (
        "你是外贸行业编辑，服务对象是河南一家钢制家具出口企业（主营拆装式钢制储物柜、"
        "工具柜，出口美国日本澳洲，做亚马逊+海外仓分销+独立站）。\n"
        "从下面候选新闻中精选 10 条，优先级：1)家具/钢制家具行业动态 2)海运运价/港口/船期"
        " 3)出口退税/关税/外贸政策 4)跨境电商与海外仓 5)宏观经济外贸数据。\n"
        "每条输出 title（12字内）和 desc（35-50字，客观陈述事实，含具体数字优先）。\n"
        "只输出 JSON 数组，格式 [{\"title\":\"..\",\"desc\":\"..\"}]，不要其他文字。\n\n"
        + "\n".join(lines)
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 2000,
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.load(r)
        content = resp["choices"][0]["message"]["content"]
        content = re.search(r"\[.*\]", content, re.S).group(0)
        news = json.loads(content)
        if isinstance(news, list) and len(news) >= 8:
            news = [{"title": str(n["title"])[:20], "desc": clean_desc(str(n["desc"]), 80)}
                    for n in news[:10]]
            print("已使用大模型精选，共", len(news), "条")
            return news
    except Exception as e:
        print("大模型精选失败，使用规则筛选:", e)
    return None


def rule_curate(candidates):
    picked = sorted(candidates, key=score, reverse=True)[:10]
    return [{"title": it["title"][:20], "desc": clean_desc(it["desc"] or it["title"])}
            for it in picked]


def main():
    # 三源融合
    raw = fetch_sina()
    for q in QUERIES:
        raw.extend(fetch_bing_news(q))
        raw.extend(fetch_google_news(q))
    print("共抓取", len(raw), "条候选")

    candidates = dedupe([dict(it, desc=clean_desc(it["desc"], 200))
                         for it in raw if it["title"]])
    industry = [c for c in candidates if score(c) >= 6]
    pool = industry if len(industry) >= 12 else candidates
    print("过滤后候选", len(pool), "条")

    # 安全写入：抓取不足时保留昨日数据
    if len(pool) < 5:
        keep = os.path.exists(OUT_PATH)
        print("候选不足 5 条，%s" % ("保留昨日 news.json" if keep else "且无历史数据"))
        if keep:
            return

    news = llm_curate(pool) or rule_curate(pool)
    if len(news) < 5 and os.path.exists(OUT_PATH):
        print("筛选结果不足，保留昨日 news.json")
        return

    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=1)
    print("已写入", OUT_PATH, "日期", today, "条数", len(news))
    for n in news:
        print(" -", n["title"])


if __name__ == "__main__":
    main()
