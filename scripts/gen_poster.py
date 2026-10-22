# -*- coding: utf-8 -*-
"""华都 · 每日行业资讯海报生成脚本（云端版，Pillow，两列布局）
与本地版版式完全一致，改动点：
1. 字体走仓库内 fonts/ 相对路径（微软雅黑已随仓库打包）
2. 输出文件名按当天日期动态生成：docs/行业新闻海报_YYYY-MM-DD.png
3. 同时输出 docs/latest.png（固定链接，手机收藏这一张即可）
新闻数据读取 data/news.json，不存在时使用内置默认数据。
"""
import os
import re
import json
from datetime import datetime, timezone, timedelta

from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 仓库根目录
NEWS_JSON = os.path.join(BASE, "data", "news.json")
DOCS_DIR = os.path.join(BASE, "docs")
os.makedirs(DOCS_DIR, exist_ok=True)

# ---------- 基础配置 ----------
W = 750
MARGIN = 48
COL_GAP = 20
COL_W = (W - MARGIN * 2 - COL_GAP) // 2      # 单列宽 317

DEEP_BLUE = (24, 46, 80)
GOLD = (201, 168, 106)
WHITE = (255, 255, 255)
TEXT_DARK = (40, 46, 58)
TEXT_GRAY = (110, 117, 130)
CARD_BG = (246, 248, 251)

F_BOLD = os.path.join(BASE, "fonts", "msyhbd.ttc")
F_REG = os.path.join(BASE, "fonts", "msyh.ttc")

def font(size, bold=False):
    return ImageFont.truetype(F_BOLD if bold else F_REG, size)

# ---------- 新闻数据 ----------
DEFAULT_NEWS = [
    ("庞村：中国钢制家具之都",
     "伊滨区庞村镇聚集600多家钢制家具企业、3000余家配套商户，年产值破百亿，产品远销120多国；亚马逊钢制家具前20店铺七成来自伊滨区。"),
    ("洛阳合丰海外订单排满",
     "合丰办公家具海外订单持续饱和，引入自动化机械臂、智能喷涂生产线，产能品质双提升，产品经跨境电商远销欧美市场。"),
    ("钢制家具专项赛在洛阳举办",
     "河南省工业设计大赛「浩德杯」钢制家具专项赛落地洛阳，高校师生与数十家企业双选结对，近200件作品参赛，总奖金9万元。"),
    ("偃师新上8万套钢制家具项目",
     "河南凯瑞智能家具年产8万套钢制家具项目拟审批，落地偃师岳滩片区，采用激光切割、数控折弯、静电喷塑工艺。"),
    ("SCFI运价连续两周上涨",
     "上海出口集装箱运价指数报3679.58点，地中海线大涨8.3%至3250美元/TEU；美西7525、美东10405美元/FEU仍居高位。"),
    ("美线运价高位震荡",
     "美西现货约8250美元/FEU、美东约11000美元；巴拿马运河水位偏低叠加港口拥堵，业内预计10月底前美线运价仍有支撑。"),
    ("超强台风「蔷琵」逼近华东",
     "今年第30号台风蔷琵中心最大风力17级，宁波沿海已启动Ⅲ级防台响应，华东港口船期或受影响，年底备货需预留缓冲。"),
    ("全球港口拥堵结构分化",
     "上海港七日平均等泊2.61天，宁波舟山已恢复约1天；远东至欧洲准班率仅4%、平均延误9.9天，跳港与舱位紧张仍需警惕。"),
    ("工具柜出口龙头加速扩产",
     "巨星科技旗下中山基龙工业启动年产61万件工具柜、工具车项目，近期密集获批工具柜、工作柜等多项实用新型专利。"),
    ("家具行业进入价值竞争时代",
     "大批家具厂洗牌出清，洛阳钢制家具集群正转型智能专用家具，公检法、档案馆、实验室等高门槛赛道成新增长点。"),
]

if os.path.exists(NEWS_JSON):
    try:
        with open(NEWS_JSON, encoding="utf-8") as f:
            _data = json.load(f)
        news = [(it["title"], it["desc"]) for it in _data]
        print("已从 news.json 读取", len(news), "条新闻")
    except Exception as e:
        print("news.json 读取失败，使用默认数据:", e)
        news = DEFAULT_NEWS
else:
    news = DEFAULT_NEWS

def tokenize(text):
    return re.findall(r"[A-Za-z0-9/%.]+|.", text)

PUNCT = "，。、；：）」』！？％"

def wrap_text(draw, text, f, max_w):
    lines = []
    line = ""
    for tok in tokenize(text):
        candidate = line + tok
        if not line or draw.textlength(candidate, font=f) <= max_w:
            line = candidate
        else:
            lines.append(line)
            line = tok
    if line:
        lines.append(line)
    # 避头点：下一行以标点开头时，挂回上一行
    for i in range(1, len(lines)):
        guard = 0
        while lines[i] and lines[i][0] in PUNCT and guard < 3:
            lines[i - 1] += lines[i][0]
            lines[i] = lines[i][1:]
            guard += 1
    lines = [ln for ln in lines if ln]
    if len(lines) >= 2:
        prev, last = lines[-2], lines[-1]
        if len(last) <= 2 and len(prev) >= 3 and ord(prev[-1]) > 0x2E80:
            lines[-2] = prev[:-1]
            lines[-1] = prev[-1] + last
    return lines

# ---------- 字体与预计算 ----------
d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
TITLE_F = font(52, True)
N_TITLE_F = font(22, True)
N_NUM_F = font(19, True)
N_DESC_F = font(19)
SEC_F = font(24, True)

HEADER_H = 250
SECTION_H = 70
CARD_PAD = 14
NUM_W = 26
TITLE_LH = 32
DESC_LH = 28
TITLE_GAP = 8

title_avail = COL_W - CARD_PAD * 2 - NUM_W
desc_avail = COL_W - CARD_PAD * 2

def item_h(title, desc):
    tl = wrap_text(d, title, N_TITLE_F, title_avail)
    dl = wrap_text(d, desc, N_DESC_F, desc_avail)
    return CARD_PAD * 2 + len(tl) * TITLE_LH + TITLE_GAP + len(dl) * DESC_LH

col_left = news[:5]
col_right = news[5:]
ROW_GAP = 16

def col_height(items):
    return sum(item_h(t, de) for t, de in items) + ROW_GAP * (len(items) - 1)

news_h = max(col_height(col_left), col_height(col_right))

FOOTER_H = 104
TOTAL_H = HEADER_H + SECTION_H + news_h + FOOTER_H

# ---------- 创建画布 ----------
img = Image.new("RGB", (W, TOTAL_H), WHITE)
draw = ImageDraw.Draw(img)

# ---------- 顶部横幅 ----------
draw.rectangle([0, 0, W, HEADER_H], fill=DEEP_BLUE)
draw.rectangle([0, 0, W, 6], fill=GOLD)

# logo：裁掉透明边框取实际图案，放大到与主标题文字同高，左边缘与标题对齐
logo_raw = Image.open(os.path.join(BASE, "assets", "logo_white.png")).convert("RGBA")
bbox = logo_raw.getbbox()          # 按 alpha 通道取实际图案边界
logo_art = logo_raw.crop(bbox) if bbox else logo_raw
_title_l, _title_t, _title_r, _title_b = draw.textbbox((0, 0), "每日行业资讯", font=TITLE_F)
TITLE_TEXT_H = _title_b - _title_t
_scale = TITLE_TEXT_H / logo_art.height
logo = logo_art.resize((max(1, round(logo_art.width * _scale)), TITLE_TEXT_H), Image.LANCZOS)
img.paste(logo, (MARGIN, 36), logo)

now = datetime.now(timezone(timedelta(hours=8)))
date_str = now.strftime("%Y年%m月%d日")
week = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
date_text = date_str + " · " + week
dw = draw.textlength(date_text, font=font(20))
draw.text((W - MARGIN - dw, 54), date_text, font=font(20), fill=(210, 220, 235))

draw.text((MARGIN, 148), "每日行业资讯", font=TITLE_F, fill=WHITE)
draw.text((MARGIN, 214), "DAILY INDUSTRY BRIEFING", font=font(19), fill=GOLD)
tag = "每日精选 · 专人整理"
tag_w = draw.textlength(tag, font=font(20))
draw.text((W - MARGIN - tag_w, 213), tag, font=font(20), fill=(210, 220, 235))

# ---------- 新闻区（两列） ----------
y0 = HEADER_H
draw.text((MARGIN, y0 + 22), "今日要闻", font=SEC_F, fill=DEEP_BLUE)
draw.rectangle([MARGIN, y0 + 58, MARGIN + 40, y0 + 62], fill=GOLD)
y0 += SECTION_H

def draw_col(x0, items, y_start, offset):
    y = y_start
    for i, (title, desc) in enumerate(items):
        n = i + offset
        tl = wrap_text(d, title, N_TITLE_F, title_avail)
        dl = wrap_text(d, desc, N_DESC_F, desc_avail)
        h = CARD_PAD * 2 + len(tl) * TITLE_LH + TITLE_GAP + len(dl) * DESC_LH
        draw.rounded_rectangle([x0, y, x0 + COL_W, y + h], radius=12, fill=CARD_BG)
        num = "%02d" % n
        draw.text((x0 + CARD_PAD, y + CARD_PAD + 2), num, font=N_NUM_F, fill=GOLD)
        ty = y + CARD_PAD
        for ln in tl:
            draw.text((x0 + CARD_PAD + NUM_W, ty), ln, font=N_TITLE_F, fill=TEXT_DARK)
            ty += TITLE_LH
        dy = ty + TITLE_GAP
        for ln in dl:
            draw.text((x0 + CARD_PAD, dy), ln, font=N_DESC_F, fill=TEXT_GRAY)
            dy += DESC_LH
        if n < offset + len(items) - 1:
            y += h + ROW_GAP
        else:
            y += h
    return y

draw_col(MARGIN, col_left, y0, 1)
draw_col(MARGIN + COL_W + COL_GAP, col_right, y0, 6)

# ---------- 页尾 ----------
foot_y = TOTAL_H - FOOTER_H
draw.rectangle([0, foot_y, W, TOTAL_H], fill=DEEP_BLUE)
draw.rectangle([0, foot_y, W, foot_y + 4], fill=GOLD)
f1 = "河南华都柜业集团有限公司"
ff1 = font(26, True)
fw1 = draw.textlength(f1, font=ff1)
draw.text(((W - fw1) / 2, foot_y + 20), f1, font=ff1, fill=WHITE)
f2 = "专注钢制家具 35 年"
ff2 = font(20)
fw2 = draw.textlength(f2, font=ff2)
draw.text(((W - fw2) / 2, foot_y + 62), f2, font=ff2, fill=GOLD)

# ---------- 保存（动态日期 + 固定 latest） ----------
today = now.strftime("%Y-%m-%d")
out_path = os.path.join(DOCS_DIR, "行业新闻海报_%s.png" % today)
img.save(out_path, "PNG")
img.save(os.path.join(DOCS_DIR, "latest.png"), "PNG")
print("已生成：", out_path)
print("尺寸：", img.size)
