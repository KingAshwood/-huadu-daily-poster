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
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
HISTORY_DAYS = 7

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 15

# ---------- 检索词（宽口径：外贸 + 财经 + 民生 + 国际新闻 + 家具/钢制家具，不限板块条数） ----------
QUERIES = [
    # 家具 / 钢制家具行业
    "钢制家具 出口", "办公家具 外贸", "家具 出口 订单", "家具 展会 出口",
    "家具 产业带", "家居 出口",
    # 跨境电商动态
    "致欧 科技", "乐歌 股份", "跨境电商 上市公司", "亚马逊 卖家 新规",
    "跨境电商 三季报", "亚马逊 家具 类目", "跨境电商 海外仓",
    # 外贸政策与宏观数据
    "外贸 出口 政策", "出口 退税", "中美 关税", "海关总署 进出口 数据",
    "广交会", "人民币 汇率 外贸", "一带一路 贸易", "RCEP",
    # 财经 / 宏观
    "美联储 利率", "全球 经济 增长", "大宗商品 价格", "原油 价格",
    "黄金 价格", "通胀 数据", "财经 要闻",
    # 海运 / 国际物流
    "集装箱 运价", "海运 美线 运价", "港口 船期", "国际 油价 航运",
    # 民生 / 国际新闻
    "台风 预警", "地震 快讯", "国际 局势 制裁", "能源 供应", "极端天气 交通",
]

# 行业关键词加权（宽口径：行业/跨境/物流/财经/民生均计分）
WEIGHTS = {
    "钢制家具": 5, "储物柜": 5, "文件柜": 5, "工具柜": 5, "更衣柜": 5, "保险柜": 3,
    "办公家具": 4, "家具出口": 5, "家具": 2, "洛阳": 3, "伊滨": 4, "庞村": 5,
    "运价": 4, "集装箱": 4, "SCFI": 5, "海运费": 4, "美线": 3, "美西": 3, "美东": 3,
    "港口": 3, "船期": 3, "拥堵": 3, "巴拿马": 3,
    "外贸": 3, "出口": 2, "退税": 4, "关税": 4, "海外仓": 4, "跨境": 3,
    "亚马逊": 3, "订单": 2, "订舱": 3, "报关": 3,
    # 财经 / 宏观
    "美联储": 3, "加息": 2, "降息": 2, "油价": 2, "黄金": 2, "汇率": 3,
    "通胀": 2, "GDP": 2, "大宗商品": 2, "PPI": 2, "CPI": 2,
    # 民生 / 国际
    "台风": 2, "地震": 2, "制裁": 2, "地缘": 2, "能源": 2, "暴雨": 2, "寒潮": 2,
}

# 噪音标题过滤
NOISE = re.compile(r"彩票|双色球|股票.*涨停|明星|电视剧|游戏|娱乐|健康|养生|房产.*售|体育|联赛|球星|综艺")

# 钢制家具优先：当天候选中出现相关新闻时优先选入（最多2条），没有则不硬凑
STEEL_PRIORITY = re.compile(
    r"钢制家具|钢制储物|储物柜|文件柜|工具柜|更衣柜|密集柜|保险柜|"
    r"办公家具|金属家具|庞村|伊滨|偃师")


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
    """整段话、不留省略号尾巴：去来源残留 + 句子边界截断"""
    desc = re.sub(r"\s+", " ", desc).strip()
    # 去掉尾部来源残留：如 "- finance.sina.com.cn" / "- 雨果跨境" / "- 温州新闻"
    desc = re.sub(r"\s*[-–—|]\s*\S{1,30}$", "", desc).strip()
    desc = re.sub(r"[…]+$", "", desc).strip()
    if len(desc) > max_len:
        cut = desc[:max_len]
        # 优先在句号/问号/感叹号处收尾，其次分号/逗号
        m = None
        for pat in ("。", "！", "？", "；", "，"):
            idx = cut.rfind(pat)
            if idx >= max_len // 2:
                m = idx
                break
        desc = (cut[: m + 1] if m else cut).rstrip("，、；,; ")
        if desc and desc[-1] not in "。！？；":
            desc += "。"
    return desc


def llm_curate(candidates, history):
    """可选：调用大模型精选 10 条（OpenAI 兼容接口，默认 DeepSeek）"""
    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key or len(candidates) < 12:
        return None
    base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("LLM_MODEL", "deepseek-chat")
    lines = ["%d. [%s] %s" % (i + 1, c["pubDate"][:16], c["title"] + " —— " + c["desc"])
             for i, c in enumerate(candidates[:40])]
    seen = "\n".join("- %s（%s）" % (h["title"], h["date"]) for h in history[-40:])
    prompt = (
        "你是外贸行业编辑，服务对象是河南一家钢制家具出口企业（主营拆装式钢制储物柜、"
        "工具柜，出口美国日本澳洲，做亚马逊+海外仓分销+独立站）。\n"
        "从下面候选新闻中精选 10 条。选题范围放宽：外贸、财经、国内国际民生、"
        "国际新闻、家具/钢制家具行业均可，不设板块、不设条数配额，每天自由组稿。\n"
        "硬性要求：\n"
        "0) 【钢制家具优先】若候选中有钢制家具/储物柜/办公家具/洛阳产业带相关新闻，"
        "优先选入最多 2 条；当天没有相关新闻就不要硬凑、不要拿旧闻充数；\n"
        "1) 10 条题材尽量分散在不同领域，同一话题（如都是运价、都是关税、都是台风）"
        "最多 3 条，宁缺毋滥；\n"
        "2) 彼此不得是同一事实或相似事件——同一公司同一事件、同一份数据的"
        "不同报道都算重复，相似的也不要；\n"
        "3) 优先具体事实与具体数字，优先近 36 小时内的新鲜新闻。\n"
        "【去重硬规则】下方列出近7天已发新闻，严禁选取与其为同一事实的候选——"
        "同一公司同一事件、或标题含相同关键数字（如同一份运价/同一份海关数据）都算重复；"
        "数据类新闻必须换新数据、新口径。\n"
        "近7天已发：\n" + (seen if seen else "（无）") + "\n\n"
        "每条输出 title（12字内）和 desc（35-50字整段话，客观陈述事实，含具体数字优先，"
        "必须是完整句子，结尾用句号，绝对不要省略号或残句）。\n"
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


def bigrams(text):
    """中英文通用的二元组集合，用于相似度计算"""
    t = re.sub(r"[\s，。、；：（）()「」『』《》\"'\-—·！？!?%+.]", "", text)
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) >= 2 else {t} if t else set()


def _lcs_len(a, b):
    """最长公共子串长度（标题级短文本，O(n*m) 可接受）"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _strip_dates(text):
    """去掉日期串，避免不同新闻同日期开头被判相似"""
    return re.sub(r"20\d{2}年|\d{1,2}月\d{1,2}[日号]", "", text)


def is_similar(text_a, text_b):
    """两条新闻是否为同一事实/相似报道：
    特征数字重合≥2 / 标题二元组重合度高 / 去日期后最长公共子串≥4字"""
    fa, fb = figure_keys(text_a), figure_keys(text_b)
    if fa and fb and len(fa & fb) >= 2:
        return True
    ba, bb = bigrams(text_a), bigrams(text_b)
    if ba and bb and len(ba & bb) / len(ba | bb) >= 0.42:
        return True
    ta = re.sub(r"[\s，。、；：（）()「」『』《》\"'\-—·！？!?%+./]", "", _strip_dates(text_a))
    tb = re.sub(r"[\s，。、；：（）()「」『』《》\"'\-—·！？!?%+./]", "", _strip_dates(text_b))
    return _lcs_len(ta, tb) >= 4


def _greedy_pick(candidates, strict, steel_first=True):
    """按分数贪心选 10 条。strict=True 时剔除相似新闻；
    strict=False 时仅剔除标题指纹完全相同的（凑数兜底）。
    steel_first=True 时优先选入钢制家具相关新闻（最多2条，须为正分）"""
    picked = []
    if steel_first:
        steel = [c for c in candidates
                 if STEEL_PRIORITY.search(c["title"] + " " + (c["desc"] or ""))
                 and score(c) > 0]
        for c in sorted(steel, key=score, reverse=True)[:2]:
            picked.append(c)
    for c in sorted(candidates, key=score, reverse=True):
        if len(picked) >= 10:
            break
        if c in picked:
            continue
        if score(c) < 0:
            continue
        if strict and any(is_similar(c["title"] + " " + (c["desc"] or ""),
                                     p["title"] + " " + (p["desc"] or ""))
                          for p in picked):
            continue
        if not strict and any(title_key(c["title"]) == title_key(p["title"])
                              for p in picked):
            continue
        picked.append(c)
    return picked


def rule_curate(candidates):
    """兜底：无板块配额，宽口径按分数贪心取 10 条，批内相似剔除；
    严格模式凑不满时降级为仅剔除完全同标题"""
    picked = _greedy_pick(candidates, strict=True)
    if len(picked) < 10:
        print("严格相似剔除仅得 %d 条，降级为仅同标题去重" % len(picked))
        picked = _greedy_pick(candidates, strict=False)
    return [{"title": it["title"][:20], "desc": clean_desc(it["desc"] or it["title"])}
            for it in picked]


def title_key(text):
    """标题归一化指纹（去空白与标点后取前18字）"""
    return re.sub(r"[\s，。、；：（）()「」『』《》\"'\-—·！？!?%+.]", "", text)[:18]


_FIG_UNITS = (r"(?:万亿|亿|万|千|美元|元|点|标箱|TEU|FEU|箱|吨|艘|级|人|家|国|"
              r"票|款|件|套|个|列|班|架|个百分点|%|％)")


def figure_keys(text):
    """提取带单位的特征数字，用于识别『同一份数据/同一事实』的重复"""
    return set(re.findall(r"\d+(?:\.\d+)?\s*" + _FIG_UNITS, text, re.I))


def load_history():
    """读取近 HISTORY_DAYS 天已发新闻，用于跨天去重"""
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        cutoff = (datetime.now(timezone(timedelta(hours=8)))
                  - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
        return [h for h in data if str(h.get("date", "")) >= cutoff]
    except Exception:
        return []


def is_dup(item, history):
    """与近7天已发新闻：标题指纹相同，或特征数字重合≥2个，均视为重复"""
    key = title_key(item["title"])
    figs = figure_keys(item["title"] + " " + item["desc"])
    for h in history:
        if key and h.get("key") == key:
            return True
        if figs and len(figs & set(h.get("figs", []))) >= 2:
            return True
    return False


def save_history(history, news):
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    history = [h for h in history if h.get("date") != today]
    for it in news:
        history.append({"date": today, "title": it["title"],
                        "key": title_key(it["title"]),
                        "figs": sorted(figure_keys(it["title"] + " " + it["desc"]))})
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=1)


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

    # 跨天去重：剔除与近7天已发相同事实的新闻
    history = load_history()
    if history:
        fresh = [c for c in pool if not is_dup(c, history)]
        if len(fresh) >= 5:
            print("跨天去重：剔除", len(pool) - len(fresh), "条，剩", len(fresh), "条")
            pool = fresh
        else:
            # 去重后候选不足时，仅按标题指纹去重（保留更多候选兜底）
            keys = {h.get("key") for h in history}
            pool = [c for c in pool if title_key(c["title"]) not in keys]
            print("去重后候选不足，降级为仅标题去重，剩", len(pool), "条")

    # 安全写入：抓取不足时保留昨日数据
    if len(pool) < 5:
        keep = os.path.exists(OUT_PATH)
        print("候选不足 5 条，%s" % ("保留昨日 news.json" if keep else "且无历史数据"))
        if keep:
            return

    news = llm_curate(pool, history) or rule_curate(pool)
    if len(news) < 5 and os.path.exists(OUT_PATH):
        print("筛选结果不足，保留昨日 news.json")
        return

    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=1)
    save_history(history, news)
    print("已写入", OUT_PATH, "日期", today, "条数", len(news))
    for n in news:
        print(" -", n["title"])


if __name__ == "__main__":
    main()
