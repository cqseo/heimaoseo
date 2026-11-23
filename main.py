#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量生成繁體中文 SEO 靜態頁面，發布到 GitHub Pages
目標網站：https://yuexia.app/
"""

import os
import sys
import json
import time
import random
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from openai import OpenAI

# ─────────────────────────────────────────────
# 環境變數配置
# ─────────────────────────────────────────────
OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
MODEL_NAME      = os.environ.get("MODEL_NAME", "deepseek-chat")
BATCH_SIZE      = int(os.environ.get("BATCH_SIZE", "50"))

# 站點配置（可透過環境變數覆蓋）
SITE_DOMAIN  = os.environ.get("SITE_DOMAIN", "cqseo.github.io/heimaoseo")
SITE_BASE    = f"https://{SITE_DOMAIN}"
TARGET_URL   = "https://yuexia.app/"
SITE_NAME    = "月下"
SITE_DESC    = "專業感情占卜、星座運勢、塔羅解析，幫助你找到感情答案"

# 輸出目錄
DOCS_DIR   = Path("docs")
DONE_FILE  = "done_titles.txt"
URLS_FILE  = "published_urls.txt"

# ─────────────────────────────────────────────
# 1,026 頁詞庫矩陣
# ─────────────────────────────────────────────

def build_corpus() -> list[dict]:
    corpus = []

    # ── A. 月老靈籤 300 頁 ──────────────────────
    yuelao_points = [
        ("感情復合解析", "復合", "感情復合"),
        ("單身求正緣指引", "正緣", "單身求緣"),
        ("曖昧暗戀白話解籤", "暗戀", "曖昧感情"),
    ]
    for n in range(1, 101):
        for point, kw, scene in yuelao_points:
            title = f"月老靈籤第{n}籤｜{point}"
            slug  = f"yuelao-{n}-{['fuhe','zhengyu','aimei'][yuelao_points.index((point,kw,scene))]}"
            corpus.append({
                "title": title, "slug": slug,
                "utm": "yuelao", "category": "月老靈籤",
                "keywords": f"月老靈籤第{n}籤,{kw},{scene},感情占卜",
                "desc": f"月老靈籤第{n}籤完整解析，針對{scene}給出具體指引，幫助你解開感情困惑。",
                "prompt": (
                    f"請用道地台灣繁體中文，以「月老靈籤第{n}籤」為主題，"
                    f"針對「{point}」寫一篇1000字以上的感情諮詢文章。"
                    f"格式要求：\n"
                    f"1. para1：400字，深入解析籤意與情感意涵，引用籤詩意境\n"
                    f"2. para2：400字，給出具體可執行的行動建議，包含時機判斷\n"
                    f"3. faq：3組FAQ（Q約25字、A約100字），涵蓋最常見疑問\n"
                    f"4. tips：3條實用小提醒（每條30字內）\n"
                    f"語氣親切、口語化，符合台灣用語，不要出現簡體字。\n"
                    f"以JSON回傳：{{\"para1\":\"...\",\"para2\":\"...\","
                    f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}],"
                    f"\"tips\":[\"...\",\"...\",\"...\"]}}"
                ),
            })

    # ── B. 12 星座 × 男女 × 15 痛點 = 360 頁 ──
    zodiacs = ["牡羊座","金牛座","雙子座","巨蟹座","獅子座","處女座",
               "天秤座","天蠍座","射手座","摩羯座","水瓶座","雙魚座"]
    zodiac_en = ["aries","taurus","gemini","cancer","leo","virgo",
                 "libra","scorpio","sagittarius","capricorn","aquarius","pisces"]
    genders = [("男生","male"), ("女生","female")]
    love_points = [
        ("他心裡還有我嗎","還有我嗎"),
        ("我們會復合嗎","會復合嗎"),
        ("冷戰中他在想什麼","冷戰想法"),
        ("他為什麼突然消失","突然消失"),
        ("怎麼讓他主動聯絡我","主動聯絡"),
        ("他對我是認真的嗎","是否認真"),
        ("我要怎麼挽回他","如何挽回"),
        ("分手後還有機會嗎","分手後機會"),
        ("他喜歡我還是把我當備胎","備胎判斷"),
        ("曖昧期要怎麼確認關係","確認關係"),
        ("他說需要時間是什麼意思","需要時間"),
        ("異地戀還有未來嗎","異地戀未來"),
        ("他劈腿後我該原諒嗎","外遇原諒"),
        ("單身多久才能遇到正緣","正緣時機"),
        ("今年桃花運什麼時候來","桃花運"),
    ]
    for zi, ze in zip(zodiacs, zodiac_en):
        for gname, gen in genders:
            for point, kw in love_points:
                title = f"{zi}{gname}感情｜{point}"
                slug  = f"{ze}-{gen}-{kw.replace('嗎','').replace('什麼','')[:6]}"
                slug  = re.sub(r'[^\w-]', '', slug.replace(' ','-'))
                corpus.append({
                    "title": title, "slug": slug,
                    "utm": "zodiac", "category": "星座感情",
                    "keywords": f"{zi},{gname}感情,{point},{kw}",
                    "desc": f"{zi}{gname}感情分析：{point}？深度解析星座特質，給你最真實的感情建議。",
                    "prompt": (
                        f"請用道地台灣繁體中文，針對「{zi}」的「{gname}」，"
                        f"就感情困擾「{point}」寫一篇1000字以上的感情分析文。\n"
                        f"格式：\n"
                        f"1. para1：400字，分析{zi}星座特質與此困擾的深層關聯\n"
                        f"2. para2：400字，給出具體行動方案與心理調適建議\n"
                        f"3. faq：3組FAQ（Q約25字、A約100字）\n"
                        f"4. tips：3條實用提醒\n"
                        f"語氣溫暖口語化，符合台灣網路文風。\n"
                        f"JSON回傳：{{\"para1\":\"...\",\"para2\":\"...\","
                        f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}],"
                        f"\"tips\":[\"...\",\"...\",\"...\"]}}"
                    ),
                })

    # ── C. 12 生肖 × 6 運勢 = 72 頁（+12星座×6=72，共144）──
    animals    = ["鼠","牛","虎","兔","龍","蛇","馬","羊","猴","雞","狗","豬"]
    animal_en  = ["rat","ox","tiger","rabbit","dragon","snake",
                  "horse","goat","monkey","rooster","dog","pig"]
    fortunes   = [
        ("2027桃花運完整預測","桃花運","romance2027"),
        ("2027偏財運爆發攻略","偏財運","wealth2027"),
        ("2027轉職換跑道時機","轉職運","career2027"),
        ("2027貴人運何時出現","貴人運","mentor2027"),
        ("2027流年大運總覽","流年運","annual2027"),
        ("2027正緣出現徵兆","正緣運","love2027"),
    ]
    for ani, aen in zip(animals, animal_en):
        for fname, fkw, fslug in fortunes:
            title = f"{ani}年生｜{fname}"
            slug  = f"{aen}-{fslug}"
            corpus.append({
                "title": title, "slug": slug,
                "utm": "fortune2027", "category": "生肖運勢",
                "keywords": f"{ani}年,{fkw},2027運勢,生肖預測",
                "desc": f"{ani}年生2027年{fkw}完整預測，掌握先機趨吉避凶。",
                "prompt": (
                    f"請用道地台灣繁體中文，以「{ani}年生」生肖為主角，"
                    f"撰寫「{fname}」運勢分析文，字數1000字以上。\n"
                    f"格式：\n"
                    f"1. para1：400字，概述2027年整體氣場與{fkw}走勢\n"
                    f"2. para2：400字，逐季拆解趨勢並給出趨吉避凶建議\n"
                    f"3. faq：3組FAQ（Q約25字、A約100字）\n"
                    f"4. tips：3條開運小撇步\n"
                    f"文風正向積極，貼近台灣命理節目口吻。\n"
                    f"JSON回傳：{{\"para1\":\"...\",\"para2\":\"...\","
                    f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}],"
                    f"\"tips\":[\"...\",\"...\",\"...\"]}}"
                ),
            })
    # 12星座×6運勢
    for zi, ze in zip(zodiacs, zodiac_en):
        for fname, fkw, fslug in fortunes:
            title = f"{zi}｜{fname}"
            slug  = f"{ze}-{fslug}"
            corpus.append({
                "title": title, "slug": slug,
                "utm": "fortune2027", "category": "星座運勢",
                "keywords": f"{zi},{fkw},2027運勢,星座預測",
                "desc": f"{zi}2027年{fkw}完整預測，幫助你掌握先機。",
                "prompt": (
                    f"請用道地台灣繁體中文，以「{zi}」星座為主角，"
                    f"撰寫「{fname}」運勢分析文，字數1000字以上。\n"
                    f"格式：para1（400字）、para2（400字）、3組FAQ、3條tips。\n"
                    f"JSON回傳：{{\"para1\":\"...\",\"para2\":\"...\","
                    f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}],"
                    f"\"tips\":[\"...\",\"...\",\"...\"]}}"
                ),
            })

    # ── D. 22 塔羅大牌 × 正逆位 × 3 場景 = 132 頁 ──
    tarot_cards = [
        ("愚者","fool"),("魔術師","magician"),("女祭司","high-priestess"),
        ("皇后","empress"),("皇帝","emperor"),("教皇","hierophant"),
        ("戀人","lovers"),("戰車","chariot"),("力量","strength"),
        ("隱士","hermit"),("命運之輪","wheel"),("正義","justice"),
        ("吊人","hanged-man"),("死神","death"),("節制","temperance"),
        ("惡魔","devil"),("高塔","tower"),("星星","star"),
        ("月亮","moon"),("太陽","sun"),("審判","judgement"),("世界","world"),
    ]
    positions = [("正位","upright"), ("逆位","reversed")]
    scenes    = [
        ("感情復合占卜","復合","love-return"),
        ("對方真實想法","想法","their-thoughts"),
        ("事業財運預測","財運","career-wealth"),
    ]
    for cname, cen in tarot_cards:
        for pname, pen in positions:
            for sname, skw, sen in scenes:
                title = f"塔羅｜{cname}{pname}｜{sname}"
                slug  = f"tarot-{cen}-{pen}-{sen}"
                corpus.append({
                    "title": title, "slug": slug,
                    "utm": "tarot_card", "category": "塔羅占卜",
                    "keywords": f"塔羅,{cname},{pname},{sname},{skw}",
                    "desc": f"塔羅牌{cname}{pname}在{sname}中的完整解析，幫助你看清感情真相。",
                    "prompt": (
                        f"請用道地台灣繁體中文，解析塔羅牌「{cname}（{pname}）」"
                        f"在「{sname}」情境下的涵義，字數1000字以上。\n"
                        f"格式：para1（400字解釋牌義核心）、para2（400字針對此場景的建議）"
                        f"、3組FAQ、3條實用提醒。\n"
                        f"JSON回傳：{{\"para1\":\"...\",\"para2\":\"...\","
                        f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}],"
                        f"\"tips\":[\"...\",\"...\",\"...\"]}}"
                    ),
                })

    # ── E. 15 廟宇 × 6 訴求 = 90 頁 ──
    temples = [
        ("霞海城隍廟","taipei-chenghuang"),("龍山寺","longshan-temple"),
        ("黃大仙祠","wong-tai-sin"),("紫南宮","zinan-temple"),
        ("鹿港天后宮","lukang-mazu"),("行天宮","xingtian-temple"),
        ("地藏庵","dizang-temple"),("大甲鎮瀾宮","dajia-mazu"),
        ("北港朝天宮","beigang-mazu"),("玄天上帝廟","xuantian-temple"),
        ("西門媽祖廟","ximending-mazu"),("車城福安宮","checheng-temple"),
        ("花蓮慶修院","hualien-temple"),("香港文武廟","man-mo-temple"),
        ("澳門媽閣廟","a-ma-temple"),
    ]
    wishes = [
        ("求姻緣祈福攻略","姻緣","love-blessing"),
        ("問感情復合靈驗儀式","復合","reunion-ritual"),
        ("求財運開運秘訣","財運","wealth-ritual"),
        ("問工作轉機祈禱方式","工作","career-prayer"),
        ("問健康平安祭祀禮儀","健康","health-ritual"),
        ("求考試順利祈願流程","考試","exam-blessing"),
    ]
    for tname, ten in temples:
        for wname, wkw, wslug in wishes:
            title = f"{tname}｜{wname}"
            slug  = f"{ten}-{wslug}"
            corpus.append({
                "title": title, "slug": slug,
                "utm": "temple", "category": "廟宇祈福",
                "keywords": f"{tname},{wkw},{wname},廟宇祈福",
                "desc": f"{tname}{wname}完整攻略，步驟詳解讓你的祈願更靈驗。",
                "prompt": (
                    f"請用道地台灣繁體中文，介紹「{tname}」的「{wname}」，字數1000字以上。\n"
                    f"格式：para1（400字介紹廟宇特色與神明職司）、"
                    f"para2（400字詳述祈願步驟與注意事項）、3組FAQ、3條溫馨提醒。\n"
                    f"JSON回傳：{{\"para1\":\"...\",\"para2\":\"...\","
                    f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}],"
                    f"\"tips\":[\"...\",\"...\",\"...\"]}}"
                ),
            })

    return corpus


# ─────────────────────────────────────────────
# HTML 模板生成
# ─────────────────────────────────────────────

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} - {site_name}</title>
  <meta name="description" content="{desc}">
  <meta name="keywords" content="{keywords}">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="{canonical}">

  <!-- Open Graph -->
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:site_name" content="{site_name}">
  <meta property="og:type" content="article">
  <meta property="og:locale" content="zh_TW">

  <!-- Schema.org -->
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@graph": [
      {{
        "@type": "Article",
        "@id": "{canonical}#article",
        "headline": "{title}",
        "description": "{desc}",
        "url": "{canonical}",
        "datePublished": "{date}",
        "dateModified": "{date}",
        "author": {{"@type": "Organization", "name": "{site_name}", "url": "{site_base}"}},
        "publisher": {{"@type": "Organization", "name": "{site_name}", "url": "{site_base}"}},
        "inLanguage": "zh-TW",
        "keywords": "{keywords}"
      }},
      {{
        "@type": "FAQPage",
        "@id": "{canonical}#faq",
        "mainEntity": {faq_schema}
      }},
      {{
        "@type": "BreadcrumbList",
        "itemListElement": [
          {{"@type":"ListItem","position":1,"name":"首頁","item":"{site_base}/"}},
          {{"@type":"ListItem","position":2,"name":"{category}","item":"{site_base}/category/{cat_slug}/"}},
          {{"@type":"ListItem","position":3,"name":"{title}","item":"{canonical}"}}
        ]
      }},
      {{
        "@type": "WebPage",
        "@id": "{canonical}",
        "url": "{canonical}",
        "name": "{title}",
        "description": "{desc}",
        "inLanguage": "zh-TW",
        "speakable": {{
          "@type": "SpeakableSpecification",
          "cssSelector": ["h1", "article h2", "article p"]
        }},
        "isPartOf": {{"@id": "{site_base}/#website"}},
        "primaryImageOfPage": {{"@type": "ImageObject", "url": "{site_base}/og-image.png"}}
      }},
      {{
        "@type": "WebSite",
        "@id": "{site_base}/#website",
        "url": "{site_base}/",
        "name": "{site_name}",
        "description": "專業感情占卜、星座運勢、塔羅解析，幫助你找到感情答案",
        "inLanguage": "zh-TW",
        "potentialAction": {{
          "@type": "SearchAction",
          "target": "{site_base}/?s={{search_term_string}}",
          "query-input": "required name=search_term_string"
        }}
      }}
    ]
  }}
  </script>

  <style>
    :root {{
      --brand: #c0392b;
      --brand-light: #e74c3c;
      --text: #2c3e50;
      --muted: #7f8c8d;
      --bg: #fff;
      --surface: #f8f9fa;
      --border: #e9ecef;
      --radius: 12px;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, "Noto Sans TC", sans-serif; color: var(--text); background: var(--bg); line-height: 1.8; }}

    /* Header */
    header {{ background: var(--brand); padding: 16px 20px; }}
    header a {{ color: #fff; text-decoration: none; font-size: 1.1rem; font-weight: 700; }}

    /* Hero CTA */
    .hero {{ background: linear-gradient(135deg, #c0392b 0%, #922b21 100%); color: #fff; text-align: center; padding: 40px 20px; }}
    .hero h1 {{ font-size: clamp(1.3rem, 4vw, 1.8rem); margin-bottom: 12px; line-height: 1.4; }}
    .hero p {{ opacity: .9; margin-bottom: 24px; font-size: .95rem; }}
    .cta-btn {{
      display: inline-block; background: #fff; color: var(--brand);
      font-weight: 700; font-size: 1.05rem; padding: 14px 32px;
      border-radius: 50px; text-decoration: none;
      box-shadow: 0 4px 15px rgba(0,0,0,.2); transition: transform .2s;
    }}
    .cta-btn:hover {{ transform: translateY(-2px); }}

    /* Content */
    .container {{ max-width: 760px; margin: 0 auto; padding: 32px 20px 60px; }}

    /* Breadcrumb */
    .breadcrumb {{ font-size: .82rem; color: var(--muted); margin-bottom: 24px; }}
    .breadcrumb a {{ color: var(--brand); text-decoration: none; }}
    .breadcrumb span {{ margin: 0 6px; }}

    /* Article */
    article h2 {{ font-size: 1.25rem; color: var(--brand); margin: 28px 0 12px; padding-left: 12px; border-left: 4px solid var(--brand); }}
    article p {{ margin-bottom: 16px; font-size: 1rem; }}

    /* FAQ */
    .faq {{ margin: 32px 0; }}
    .faq h2 {{ font-size: 1.25rem; color: var(--brand); margin-bottom: 16px; padding-left: 12px; border-left: 4px solid var(--brand); }}
    details {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 10px; overflow: hidden; }}
    summary {{ padding: 14px 18px; font-weight: 600; cursor: pointer; list-style: none; display: flex; justify-content: space-between; align-items: center; }}
    summary::after {{ content: "+"; font-size: 1.3rem; color: var(--brand); }}
    details[open] summary::after {{ content: "−"; }}
    .faq-answer {{ padding: 0 18px 14px; color: #444; line-height: 1.8; }}

    /* Tips */
    .tips {{ background: #fff9f9; border: 1px solid #fad7d7; border-radius: var(--radius); padding: 20px 24px; margin: 28px 0; }}
    .tips h3 {{ color: var(--brand); margin-bottom: 12px; font-size: 1rem; }}
    .tips ul {{ padding-left: 20px; }}
    .tips li {{ margin-bottom: 8px; font-size: .95rem; }}

    /* Bottom CTA */
    .bottom-cta {{ background: var(--surface); border: 2px solid var(--brand); border-radius: var(--radius); padding: 28px; text-align: center; margin: 40px 0 20px; }}
    .bottom-cta p {{ margin-bottom: 16px; font-size: 1rem; }}

    /* Footer */
    footer {{ background: var(--surface); border-top: 1px solid var(--border); padding: 24px 20px; text-align: center; color: var(--muted); font-size: .82rem; }}
    footer a {{ color: var(--brand); text-decoration: none; }}
  </style>
</head>
<body>

<header>
  <a href="{site_base}/">🔮 {site_name}</a>
</header>

<!-- 首屏 CTA -->
<div class="hero">
  <h1>{title}</h1>
  <p>專業感情占卜 · 解開你心中的答案</p>
  <a class="cta-btn" href="{cta_url}">✨ 立即免費諮詢 →</a>
</div>

<div class="container">

  <!-- 麵包屑 -->
  <nav class="breadcrumb" aria-label="breadcrumb">
    <a href="{site_base}/">首頁</a>
    <span>›</span>
    <a href="{site_base}/category/{cat_slug}/">{category}</a>
    <span>›</span>
    <span>{title}</span>
  </nav>

  <article>
    <h2>深度解析</h2>
    <p>{para1}</p>

    <h2>具體建議</h2>
    <p>{para2}</p>
  </article>

  <!-- Tips -->
  <div class="tips">
    <h3>💡 實用小提醒</h3>
    <ul>
      {tips_html}
    </ul>
  </div>

  <!-- FAQ -->
  <div class="faq">
    <h2>常見問題 Q&amp;A</h2>
    {faq_html}
  </div>

  <!-- 底部 CTA -->
  <div class="bottom-cta">
    <p>還有更多疑問？讓月下的專業老師為你一對一解答</p>
    <a class="cta-btn" href="{cta_url}">➡ 前往月下，獲得你的專屬感情指引</a>
  </div>

</div>

<footer>
  <p>© 2025 <a href="{site_base}/">{site_name}</a> · 感情占卜 · 星座運勢 · 塔羅解析</p>
  <p style="margin-top:8px"><a href="{target_url}">月下官網</a></p>
</footer>

</body>
</html>'''


def build_faq_schema(faqs: list) -> str:
    items = []
    for f in faqs:
        q = f["q"].replace('"', '\\"')
        a = f["a"].replace('"', '\\"')
        items.append(
            f'{{"@type":"Question","name":"{q}",'
            f'"acceptedAnswer":{{"@type":"Answer","text":"{a}"}}}}'
        )
    return "[" + ",".join(items) + "]"


def render_html(item: dict, data: dict) -> str:
    slug     = item["slug"]
    canonical = f"{SITE_BASE}/p/{slug}/"
    cta_url  = f"{TARGET_URL}?utm_source=seo&utm_medium={item['utm']}&utm_campaign={slug}"
    cat_slug = item["category"].replace("星座","zodiac").replace("生肖","shengxiao")\
                               .replace("塔羅","tarot").replace("廟宇","temple")\
                               .replace("月老","yuelao").replace("運勢","fortune")
    cat_slug = re.sub(r'[^\w-]', '', cat_slug)

    faqs = data.get("faq", [])[:3]
    tips = data.get("tips", [])[:3]

    faq_html = "\n    ".join(
        f'<details><summary>{f["q"]}</summary>'
        f'<div class="faq-answer">{f["a"]}</div></details>'
        for f in faqs
    )
    tips_html = "\n      ".join(f"<li>{t}</li>" for t in tips)
    faq_schema = build_faq_schema(faqs)
    date_str   = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return HTML_TEMPLATE.format(
        title=item["title"], site_name=SITE_NAME, site_base=SITE_BASE,
        desc=item["desc"], keywords=item["keywords"],
        canonical=canonical, cta_url=cta_url, target_url=TARGET_URL,
        category=item["category"], cat_slug=cat_slug,
        para1=data["para1"], para2=data["para2"],
        faq_html=faq_html, tips_html=tips_html,
        faq_schema=faq_schema, date=date_str,
    )


# ─────────────────────────────────────────────
# Sitemap 生成
# ─────────────────────────────────────────────

def generate_sitemap(slugs: list[str]):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls  = [f"  <url><loc>{SITE_BASE}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for s in slugs:
        urls.append(
            f"  <url><loc>{SITE_BASE}/p/{s}/</loc>"
            f"<lastmod>{today}</lastmod>"
            f"<changefreq>monthly</changefreq><priority>0.8</priority></url>"
        )
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += "\n".join(urls) + "\n</urlset>"
    (DOCS_DIR / "sitemap.xml").write_text(xml, encoding="utf-8")
    print(f"  ✅ sitemap.xml 更新，共 {len(slugs)+1} 條 URL")


def generate_robots():
    txt = f"User-agent: *\nAllow: /\nSitemap: {SITE_BASE}/sitemap.xml\n"
    (DOCS_DIR / "robots.txt").write_text(txt, encoding="utf-8")


def generate_index(corpus: list[dict], done: set):
    """生成帶分類導航的首頁"""
    categories = {}
    for item in corpus:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        if item["title"] in done:
            categories[cat].append(item)

    cards = ""
    for cat, items in categories.items():
        if not items:
            continue
        links = "".join(
            f'<li><a href="{SITE_BASE}/p/{it["slug"]}/">{it["title"]}</a></li>'
            for it in items[:12]
        )
        cards += f'''
        <section class="cat-section">
          <h2>{cat} <span class="count">({len(items)} 篇)</span></h2>
          <ul class="page-list">{links}</ul>
        </section>'''

    total_done = sum(len(v) for v in categories.values())
    total_all  = len(corpus)

    html = f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{SITE_NAME} - 專業感情占卜、星座運勢、塔羅解析</title>
  <meta name="description" content="{SITE_DESC}">
  <link rel="canonical" href="{SITE_BASE}/">
  <style>
    body {{ font-family: -apple-system, "Noto Sans TC", sans-serif; margin: 0; color: #2c3e50; }}
    header {{ background: #c0392b; padding: 20px; color: #fff; text-align: center; }}
    header h1 {{ font-size: 1.5rem; }}
    .hero {{ background: linear-gradient(135deg,#c0392b,#922b21); color:#fff; text-align:center; padding:40px 20px; }}
    .cta-btn {{ display:inline-block; background:#fff; color:#c0392b; font-weight:700; padding:14px 32px; border-radius:50px; text-decoration:none; margin-top:16px; }}
    .container {{ max-width:860px; margin:0 auto; padding:32px 20px; }}
    .stats {{ display:flex; gap:16px; justify-content:center; margin:24px 0; flex-wrap:wrap; }}
    .stat {{ background:#f8f9fa; border:1px solid #dee2e6; border-radius:12px; padding:16px 24px; text-align:center; }}
    .stat strong {{ display:block; font-size:1.8rem; color:#c0392b; }}
    .cat-section {{ margin-bottom:32px; }}
    .cat-section h2 {{ font-size:1.1rem; color:#c0392b; border-bottom:2px solid #c0392b; padding-bottom:8px; margin-bottom:12px; }}
    .count {{ font-size:.85rem; color:#7f8c8d; font-weight:400; }}
    .page-list {{ list-style:none; padding:0; display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:8px; }}
    .page-list a {{ display:block; padding:8px 12px; background:#f8f9fa; border-radius:8px; text-decoration:none; color:#2c3e50; font-size:.88rem; border:1px solid #e9ecef; transition:background .2s; }}
    .page-list a:hover {{ background:#fdecea; color:#c0392b; }}
    footer {{ background:#f8f9fa; border-top:1px solid #e9ecef; padding:24px; text-align:center; color:#7f8c8d; font-size:.82rem; }}
  </style>
</head>
<body>
<header><h1>🔮 {SITE_NAME}</h1></header>
<div class="hero">
  <p>{SITE_DESC}</p>
  <a class="cta-btn" href="{TARGET_URL}?utm_source=seo&utm_medium=index">✨ 立即免費諮詢</a>
</div>
<div class="container">
  <div class="stats">
    <div class="stat"><strong>{total_done}</strong>已發布頁面</div>
    <div class="stat"><strong>{total_all}</strong>收錄總量</div>
  </div>
  {cards}
</div>
<footer>© 2025 {SITE_NAME} · <a href="{TARGET_URL}">月下官網</a> · <a href="{SITE_BASE}/sitemap.xml">Sitemap</a></footer>
</body>
</html>'''
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")


# ─────────────────────────────────────────────
# LLM 內容生成
# ─────────────────────────────────────────────

def generate_content(client: OpenAI, prompt: str) -> dict:
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": (
                        "你是專業的台灣繁體中文感情命理內容創作者，"
                        "擅長撰寫有深度、有共鳴的感情諮詢長文。"
                        "嚴格規定：\n"
                        "1. 全程使用台灣正體中文，絕對禁止出現簡體字、英文或任何非中文字符\n"
                        "2. 輸出必須是合法 JSON 格式，不要加 markdown 代碼塊或反引號\n"
                        "3. para1 和 para2 每段必須超過 350 字\n"
                        "4. FAQ 的 Q 和 A 也必須用繁體中文\n"
                        "5. 語氣親切口語化，符合台灣用語習慣"
                    )},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.85,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )
            raw  = resp.choices[0].message.content.strip()
            data = json.loads(raw)
            assert "para1" in data and "para2" in data and "faq" in data
            assert len(data["faq"]) >= 2
            if "tips" not in data:
                data["tips"] = ["保持正向心態，相信緣分自然到來",
                                "適時與信任的朋友傾訴，不要獨自承受",
                                "給自己一些時間和空間，好好愛自己"]
            return data
        except Exception as e:
            print(f"  [LLM 重試 {attempt+1}/3] {e}")
            time.sleep(4 * (attempt + 1))
    raise RuntimeError("LLM 生成失敗，已重試 3 次")


# ─────────────────────────────────────────────
# 斷點續傳
# ─────────────────────────────────────────────

def load_done() -> set:
    if os.path.exists(DONE_FILE):
        return set(l.strip() for l in open(DONE_FILE, encoding="utf-8") if l.strip())
    return set()

def save_done(title: str):
    with open(DONE_FILE, "a", encoding="utf-8") as f:
        f.write(title + "\n")

def save_url(url: str):
    with open(URLS_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────

def main():
    if not OPENAI_API_KEY:
        print("❌ 缺少 OPENAI_API_KEY 環境變數")
        sys.exit(1)

    client  = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    corpus  = build_corpus()
    done    = load_done()
    pending = [item for item in corpus if item["title"] not in done]

    print(f"📚 詞庫：{len(corpus)} 頁  |  已完成：{len(done)}  |  "
          f"待處理：{len(pending)}  |  本批次：{min(BATCH_SIZE, len(pending))}")

    if not pending:
        print("🎉 所有頁面已生成完畢！")
        generate_sitemap([it["slug"] for it in corpus if it["title"] in done])
        generate_index(corpus, done)
        return

    # 確保輸出目錄存在
    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "p").mkdir(exist_ok=True)

    this_batch    = pending[:BATCH_SIZE]
    success_count = 0

    for idx, item in enumerate(this_batch, 1):
        print(f"[{idx}/{len(this_batch)}] {item['title']}")
        try:
            data     = generate_content(client, item["prompt"])
            html     = render_html(item, data)
            page_dir = DOCS_DIR / "p" / item["slug"]
            page_dir.mkdir(parents=True, exist_ok=True)
            (page_dir / "index.html").write_text(html, encoding="utf-8")

            url = f"{SITE_BASE}/p/{item['slug']}/"
            save_done(item["title"])
            save_url(url)
            done.add(item["title"])
            success_count += 1
            print(f"  ✅ {url}")
        except Exception as e:
            print(f"  ❌ 失敗：{e}")

        time.sleep(random.uniform(0.5, 1.2))

    # 更新 sitemap、robots、首頁
    all_slugs = [it["slug"] for it in corpus if it["title"] in done]
    generate_sitemap(all_slugs)
    generate_robots()
    generate_index(corpus, done)

    print(f"\n本批次：✅ {success_count} 頁  |  累計：{len(done)} / {len(corpus)} 頁")


if __name__ == "__main__":
    main()
