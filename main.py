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
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from openai import OpenAI

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    from pypinyin import lazy_pinyin
    _PINYIN_OK = True
except ImportError:
    _PINYIN_OK = False

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
    """
    精準長尾詞庫 — 30,000+ 頁
    策略：具體場景 × 具體行為 × 具體情緒，模擬真實用戶搜尋字串
    競爭力：避開 TVBS / bella.tw / Dcard 佔領的廣泛詞，
           鎖定低競爭、高購買意圖的細節型查詢
    """
    corpus = []
    seen_slugs: set = set()

    def _title_to_slug(title: str, max_len: int = 60) -> str:
        """把中文標題轉成拼音 slug，數字/英文保留原樣"""
        t = re.sub(r'[｜|【】《》「」『』、，。？！：；…—·\s]+', '-', title)
        if _PINYIN_OK:
            parts = lazy_pinyin(t)
        else:
            # fallback：只保留 ASCII + 數字
            parts = [c if c.isascii() else '' for c in t]
        slug = '-'.join(p for p in parts if p)
        slug = re.sub(r'-+', '-', slug).strip('-').lower()
        if len(slug) > max_len:
            slug = slug[:max_len].rsplit('-', 1)[0]
        return slug

    def add(item: dict):
        """加入後自動去重；若無 slug 則從標題生成"""
        if not item.get("slug"):
            item["slug"] = _title_to_slug(item["title"])
        s = item["slug"]
        if s in seen_slugs:
            return
        seen_slugs.add(s)
        corpus.append(item)

    # ═══════════════════════════════════════════════════════════════════
    # 精準長尾詞庫 — 目標 30,000+ 頁
    # 維度：場景 × 行為 × 情緒 × 時間 × 性別 × 星座/生肖/牌/廟宇
    # ═══════════════════════════════════════════════════════════════════

    def _make(title, utm, category, keywords, desc, prompt_core, slug=""):
        """統一建構詞條，slug 可選；若空則從標題自動生成拼音"""
        p = (
            f"請用道地台灣繁體中文，針對「{title}」這個主題，"
            f"寫一篇1200字以上的深度感情分析或命理解答文章。\n"
            f"重點聚焦：{prompt_core}\n"
            f"格式要求（嚴格遵守）：\n"
            f"1. para1：500字以上，深入分析問題核心，給出有洞察力的解讀，讓讀者感覺被理解\n"
            f"2. para2：500字以上，給出3-5個具體可執行的行動建議，包含實際話術和步驟\n"
            f"3. faq：3組最常見的延伸問題（Q約25字、A約100字，要實用不空泛）\n"
            f"4. tips：3條立即可用的實用提醒（每條30字內，要具體）\n"
            f"語氣親切口語化，像台灣閨蜜在聊天，不要文縐縐。\n"
            f"JSON格式（直接輸出，不要加```json代碼塊）：\n"
            f"{{\"para1\":\"...\",\"para2\":\"...\","
            f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}],"
            f"\"tips\":[\"...\",\"...\",\"...\"]}}"
        )
        add({
            "title": title, "slug": slug,   # 傳入的 slug 優先；空字串 → add() 自動從標題生成
            "utm": utm, "category": category,
            "keywords": keywords, "desc": desc,
            "prompt": p,
        })

    # ─────────────────────────────────────────────────────────────────
    # A. 月老靈籤 — 100 籤 × 10 具體問題 = 1,000 頁
    # ─────────────────────────────────────────────────────────────────
    yuelao_qs = [
        ("分手後他會回來嗎",          "yl-return",    "分手後復合,月老靈籤解籤",    "抽到這籤問分手後他會不會回來"),
        ("曖昧已讀不回三天怎麼辦",    "yl-ignore",    "已讀不回,曖昧期,月老指引",   "曖昧中他已讀不回三天，月老怎麼說"),
        ("單身多久了問何時脫單",       "yl-single",    "何時脫單,單身求緣",          "久單族抽這籤問脫單時機"),
        ("喜歡的人說只想當朋友",       "yl-friend",    "朋友圈,友達以上",            "被放進友達圈抽這籤還有機會嗎"),
        ("他說需要時間是要分手嗎",     "yl-needtime",  "說需要時間,冷靜期",          "他說需要時間冷靜，月老籤意怎麼看"),
        ("問他現在在想誰",             "yl-thinking",  "對方心意,感情占卜",          "抽這籤問對方現在心裡在想誰"),
        ("告白會成功嗎",               "yl-confess",   "告白,感情表白,成功率",       "即將告白抽這籤，月老給你的答案"),
        ("感情裡的阻礙能化解嗎",       "yl-obstacle",  "感情阻礙,化解,月老解籤",    "籤詩說有阻礙，是哪種阻礙怎麼化解"),
        ("這段緣分是否值得繼續",       "yl-worth",     "緣分,值得繼續,感情判斷",    "猶豫要不要繼續這段感情抽這籤"),
        ("正緣什麼時候會出現",         "yl-zhengyu",   "正緣,緣分時機,月老指引",    "問月老正緣出現時機的完整解讀"),
    ]
    for n in range(1, 101):
        for suffix, slug_sfx, kws, desc_tpl in yuelao_qs:
            _make(
                title=f"月老靈籤第{n}籤｜{suffix}",
                slug=f"yuelao-{n}-{slug_sfx}",
                utm="yuelao", category="月老靈籤",
                keywords=f"月老靈籤第{n}籤,{kws},感情占卜",
                desc=f"{desc_tpl}，月老靈籤第{n}籤完整解析",
                prompt_core=(
                    f"以月老靈籤第{n}籤為基礎，深入解析「{suffix}」這個問題。"
                    f"para1要結合第{n}籤的象徵意義給出籤意詮釋，"
                    f"para2要給出具體可執行的建議和時機判斷"
                ),
            )

    # ─────────────────────────────────────────────────────────────────
    # B. 12 星座 × 男女 × 30 具體行為場景 = 720 頁
    # ─────────────────────────────────────────────────────────────────
    zodiacs = [
        ("牡羊座","aries"), ("金牛座","taurus"), ("雙子座","gemini"),
        ("巨蟹座","cancer"), ("獅子座","leo"), ("處女座","virgo"),
        ("天秤座","libra"), ("天蠍座","scorpio"), ("射手座","sagittarius"),
        ("摩羯座","capricorn"), ("水瓶座","aquarius"), ("雙魚座","pisces"),
    ]
    genders = [("男生","male"), ("女生","female")]
    zodiac_scenes = [
        ("說需要時間冷靜是分手還是要空間",      "need-time",         "說需要時間,冷靜期"),
        ("已讀不回三天還有機會嗎",              "read-no-reply",     "已讀不回,三天,感情"),
        ("主動傳訊息都是我先怎麼辦",            "always-first-text", "我先傳訊息,主動追"),
        ("曖昧一個月突然冷淡是怎麼了",          "aimei-cold",        "突然冷淡,曖昧"),
        ("說分手但還是一直找我是什麼意思",      "breakup-contact",   "說分手還找我,藕斷絲連"),
        ("交往半年開始不積極了怎麼挽回",        "6m-less-effort",    "交往半年,熱情下降"),
        ("喜歡我還是把我當備胎怎麼看",          "backup-or-like",    "備胎,是否喜歡"),
        ("分手後還傳訊息是想復合嗎",            "ex-text",           "前任傳訊息,復合"),
        ("生氣後不回訊息要怎麼哄",              "angry-no-reply",    "生氣不回訊,哄對方"),
        ("只約吃飯不約其他代表什麼",            "only-dinner",       "只約吃飯,關係曖昧"),
        ("說忙但還是回訊息是在意嗎",            "busy-reply",        "說忙還回訊,在乎"),
        ("問他喜不喜歡我他說不知道",            "dontknow",          "說不知道,感情表態"),
        ("交往前就提分手是認真的嗎",            "almost-break",      "曖昧期分手,感情不穩"),
        ("表白後他沒有給答案怎麼辦",            "no-answer",         "表白沒答案,等待"),
        ("在一起後突然說要當朋友是怎麼了",      "friend-after-date", "突然變朋友,感情退縮"),
        ("追了三個月沒進展要放棄嗎",            "3m-no-progress",    "追三個月,沒進展"),
        ("他對別人很好對我很普通是什麼意思",    "good-to-others",    "對別人好,對我普通"),
        ("說喜歡你但不想交往該怎麼辦",          "like-no-date",      "喜歡但不談感情"),
        ("分手後他主動找我是什麼意思",          "ex-contact",        "前任主動聯絡,動機"),
        ("每次吵架都是我先道歉正常嗎",          "always-apologize",  "每次先道歉,感情失衡"),
        ("異地戀突然變得很冷淡怎麼辦",          "ld-cold",           "異地戀冷淡,感情危機"),
        ("告白成功後關係反而變奇怪",            "post-confess-awk",  "告白成功後尷尬"),
        ("在一起一年了還是沒有安全感",          "1y-insecure",       "交往一年,沒安全感"),
        ("他說愛我但行動不一致怎麼辦",          "word-action-diff",  "說愛我,行動不符"),
        ("感情中一直委屈自己要怎麼辦",          "self-sacrifice",    "感情委屈,自我犧牲"),
        ("他最近開始不傳早晚安了代表什麼",      "no-goodnight",      "不傳早晚安,感情降溫"),
        ("約了好幾次都說忙是不想見面嗎",        "always-busy-date",  "約不到面,說忙"),
        ("對方突然說要給彼此空間",              "give-space",        "給彼此空間,感情降溫"),
        ("他回訊很慢但偶爾秒回是什麼心態",      "slow-reply",        "回訊慢,偶爾秒回"),
        ("復合後他又開始變冷是怎麼了",          "reunion-cold",      "復合後變冷,感情反覆"),
    ]
    for zi, ze in zodiacs:
        for gname, gen in genders:
            for scene, slug_sfx, kws in zodiac_scenes:
                _make(
                    title=f"{zi}{gname}｜{scene}",
                    slug=f"{ze}-{gen}-{slug_sfx}",
                    utm="zodiac", category="星座感情",
                    keywords=f"{zi},{gname},{kws}",
                    desc=f"{zi}{gname}{scene}？從星座特質深度分析，給你最真實的感情建議",
                    prompt_core=(
                        f"從{zi}星座的性格特質分析「{gname}」在「{scene}」背後的心理動機，"
                        f"給出針對這個星座{gname}的具體應對方式，包含可用的話術"
                    ),
                )

    # ─────────────────────────────────────────────────────────────────
    # C. 星座配對 — 12×11/2=66 對 × 5 問題 = 330 頁
    # ─────────────────────────────────────────────────────────────────
    compat_questions = [
        ("在一起最大的衝突是什麼", "conflict",    "星座衝突,感情矛盾,配對問題"),
        ("為什麼互相吸引但又常吵架","attract-fight","互相吸引,常吵架,星座矛盾"),
        ("這對配對能走到最後嗎",   "last-long",   "星座配對,長久感情,是否合適"),
        ("如何讓對方愛上你",       "make-love",   "讓對方喜歡,追求技巧,星座配對"),
        ("吵架後誰先道歉比較好",   "apology",     "星座道歉,冷戰,和好方式"),
    ]
    for i, (z1, e1) in enumerate(zodiacs):
        for z2, e2 in zodiacs[i+1:]:
            for qsuffix, qslug, kws in compat_questions:
                pair_slug = f"compat-{e1}-{e2}-{qslug}"
                _make(
                    title=f"{z1}和{z2}｜{qsuffix}",
                    slug=pair_slug,
                    utm="compat", category="星座配對",
                    keywords=f"{z1},{z2},{kws}",
                    desc=f"{z1}配{z2}：{qsuffix}完整分析",
                    prompt_core=(
                        f"深度分析{z1}和{z2}這對配對「{qsuffix}」的核心原因，"
                        f"結合兩個星座的性格特質給出具體實用建議"
                    ),
                )

    # ─────────────────────────────────────────────────────────────────
    # D. 22 塔羅大牌 × 正逆位 × 8 具體問題 = 352 頁
    # ─────────────────────────────────────────────────────────────────
    tarot_cards = [
        ("愚者","fool"), ("魔術師","magician"), ("女祭司","high-priestess"),
        ("皇后","empress"), ("皇帝","emperor"), ("教皇","hierophant"),
        ("戀人","lovers"), ("戰車","chariot"), ("力量","strength"),
        ("隱士","hermit"), ("命運之輪","wheel"), ("正義","justice"),
        ("吊人","hanged-man"), ("死神","death"), ("節制","temperance"),
        ("惡魔","devil"), ("高塔","tower"), ("星星","star"),
        ("月亮","moon"), ("太陽","sun"), ("審判","judgement"), ("世界","world"),
    ]
    positions = [("正位","upright"), ("逆位","reversed")]
    tarot_qs = [
        ("代表他現在對我的心意",       "feelings",      "塔羅感情,對方心意"),
        ("問復合是好是壞",             "reunion",       "復合塔羅,分手後"),
        ("感情是否徹底結束了",         "end-or-not",    "塔羅感情結束,是否放手"),
        ("對方有沒有在想我",           "thinking-me",   "塔羅占卜,對方想法"),
        ("我們感情的未來走向",         "future",        "感情未來,塔羅預測"),
        ("他有沒有喜歡我",             "does-like",     "塔羅喜歡,感情確認"),
        ("感情遇到阻礙要怎麼化解",     "obstacle",      "感情阻礙,塔羅建議"),
        ("這段感情值不值得繼續努力",   "worth-try",     "感情值得,塔羅判斷"),
    ]
    for cname, cen in tarot_cards:
        for pname, pen in positions:
            for qsuffix, qslug, kws in tarot_qs:
                _make(
                    title=f"塔羅{cname}{pname}｜{qsuffix}",
                    slug=f"tarot-{cen}-{pen}-{qslug}",
                    utm="tarot_card", category="塔羅占卜",
                    keywords=f"塔羅,{cname},{pname},{kws}",
                    desc=f"塔羅{cname}{pname}：{qsuffix}完整解析",
                    prompt_core=(
                        f"解析塔羅{cname}（{pname}）針對「{qsuffix}」的完整涵義，"
                        f"說明{pname}和正位的差別，並給出具體行動建議"
                    ),
                )

    # ─────────────────────────────────────────────────────────────────
    # E. 塔羅牌組 × 感情場景 — 小阿爾克那 56 張（4組×14）×3場景 = 168 頁
    # ─────────────────────────────────────────────────────────────────
    minor_arcana = [
        ("權杖A","wands-ace"), ("權杖二","wands-2"), ("權杖三","wands-3"),
        ("權杖四","wands-4"), ("權杖五","wands-5"), ("權杖六","wands-6"),
        ("權杖七","wands-7"), ("權杖八","wands-8"), ("權杖九","wands-9"),
        ("權杖十","wands-10"), ("權杖侍者","wands-page"), ("權杖騎士","wands-knight"),
        ("權杖皇后","wands-queen"), ("權杖國王","wands-king"),
        ("聖杯A","cups-ace"), ("聖杯二","cups-2"), ("聖杯三","cups-3"),
        ("聖杯四","cups-4"), ("聖杯五","cups-5"), ("聖杯六","cups-6"),
        ("聖杯七","cups-7"), ("聖杯八","cups-8"), ("聖杯九","cups-9"),
        ("聖杯十","cups-10"), ("聖杯侍者","cups-page"), ("聖杯騎士","cups-knight"),
        ("聖杯皇后","cups-queen"), ("聖杯國王","cups-king"),
        ("寶劍A","swords-ace"), ("寶劍二","swords-2"), ("寶劍三","swords-3"),
        ("寶劍四","swords-4"), ("寶劍五","swords-5"), ("寶劍六","swords-6"),
        ("寶劍七","swords-7"), ("寶劍八","swords-8"), ("寶劍九","swords-9"),
        ("寶劍十","swords-10"), ("寶劍侍者","swords-page"), ("寶劍騎士","swords-knight"),
        ("寶劍皇后","swords-queen"), ("寶劍國王","swords-king"),
        ("星幣A","pentacles-ace"), ("星幣二","pentacles-2"), ("星幣三","pentacles-3"),
        ("星幣四","pentacles-4"), ("星幣五","pentacles-5"), ("星幣六","pentacles-6"),
        ("星幣七","pentacles-7"), ("星幣八","pentacles-8"), ("星幣九","pentacles-9"),
        ("星幣十","pentacles-10"), ("星幣侍者","pentacles-page"), ("星幣騎士","pentacles-knight"),
        ("星幣皇后","pentacles-queen"), ("星幣國王","pentacles-king"),
    ]
    minor_scenes = [
        ("感情中出現代表什麼", "love-mean", "塔羅小阿爾克那,感情牌義"),
        ("問對方心意出現代表什麼", "other-mind", "塔羅感情,對方心意"),
        ("在復合牌陣中出現代表什麼", "reunion-spread", "復合塔羅,牌陣解讀"),
    ]
    for cname, cen in minor_arcana:
        for scene, slug_sfx, kws in minor_scenes:
            _make(
                title=f"塔羅{cname}｜{scene}",
                slug=f"tarot-minor-{cen}-{slug_sfx}",
                utm="tarot_minor", category="塔羅占卜",
                keywords=f"塔羅,{cname},{kws}",
                desc=f"塔羅{cname}在感情牌陣中的完整解析",
                prompt_core=(
                    f"解析塔羅小阿爾克那{cname}「{scene}」，"
                    f"說明這張牌在感情占卜中的正逆位含義和具體建議"
                ),
            )

    # ─────────────────────────────────────────────────────────────────
    # F. 廟宇求籤 — 20 廟 × 10 具體問題 = 200 頁
    # ─────────────────────────────────────────────────────────────────
    temples = [
        ("霞海城隍廟","taipei-chenghuang","台北"),
        ("龍山寺","longshan-temple","台北"),
        ("紫南宮","zinan-temple","南投"),
        ("鹿港天后宮","lukang-mazu","彰化"),
        ("行天宮","xingtian-temple","台北"),
        ("大甲鎮瀾宮","dajia-mazu","台中"),
        ("北港朝天宮","beigang-mazu","雲林"),
        ("西門媽祖廟","ximending-mazu","台北"),
        ("花蓮慶修院","hualien-temple","花蓮"),
        ("香港黃大仙祠","wong-tai-sin","香港"),
        ("南投地母廟","nantou-dimu","南投"),
        ("台南大天后宮","tainan-mazu","台南"),
        ("嘉義城隍廟","chiayi-chenghuang","嘉義"),
        ("苗栗獅頭山","shitoushan","苗栗"),
        ("宜蘭二結王公廟","yilan-wanggong","宜蘭"),
        ("彰化南瑤宮","changhua-mazu","彰化"),
        ("台中樂成宮","taichung-mazu","台中"),
        ("屏東東港東隆宮","donggang-wangye","屏東"),
        ("基隆慶安宮","keelung-mazu","基隆"),
        ("新竹城隍廟","hsinchu-chenghuang","新竹"),
    ]
    temple_qs = [
        ("求月老紅線步驟與禁忌完整攻略", "red-thread",   "月老紅線,求姻緣步驟"),
        ("感情籤哪號最靈驗完整解說",     "love-sign",    "感情籤,最靈驗籤號"),
        ("第一次去拜拜流程新手攻略",     "first-visit",  "第一次拜拜,流程"),
        ("還願正確方式和時機",           "fulfill-vow",  "還願,如何還願"),
        ("外縣市交通和最佳時間規劃",     "travel-plan",  "外縣市拜拜,交通攻略"),
        ("帶交往對象一起去的注意事項",   "bring-partner","帶男女朋友拜拜"),
        ("求籤後多久會有感應",           "response-time","求籤感應,靈驗時間"),
        ("失戀後去拜拜有沒有用",         "after-break",  "失戀拜拜,心靈療癒"),
        ("求財運的正確許願方式",         "wealth-pray",  "求財運,財運許願"),
        ("求考試順利的祈願流程",         "exam-pray",    "求考試,祈願步驟"),
    ]
    for tname, ten, tcity in temples:
        for qsuffix, qslug, kws in temple_qs:
            _make(
                title=f"{tname}｜{qsuffix}",
                slug=f"{ten}-{qslug}",
                utm="temple", category="廟宇祈福",
                keywords=f"{tname},{tcity},{kws}",
                desc=f"{tname}{qsuffix}完整攻略，讓你的祈願更有效",
                prompt_core=(
                    f"介紹{tname}（{tcity}）的「{qsuffix}」，"
                    f"給出具體步驟、注意事項和民間習俗說明"
                ),
            )

    # ─────────────────────────────────────────────────────────────────
    # G. 生肖運勢 × 感情場景 — 12 生肖 × 25 具體問題 = 300 頁
    # ─────────────────────────────────────────────────────────────────
    animals = [
        ("鼠","rat"), ("牛","ox"), ("虎","tiger"), ("兔","rabbit"),
        ("龍","dragon"), ("蛇","snake"), ("馬","horse"), ("羊","goat"),
        ("猴","monkey"), ("雞","rooster"), ("狗","dog"), ("豬","pig"),
    ]
    shengxiao_qs = [
        ("2027感情運最旺是哪個月",         "love-peak-2027",    "2027感情,桃花月"),
        ("2027告白最佳時機怎麼看",         "confess-2027",      "告白時機,2027"),
        ("2027分手後能復合嗎",             "reunion-2027",      "分手復合,2027運勢"),
        ("2027單身能脫單嗎",               "single-2027",       "脫單,2027桃花"),
        ("2027感情阻礙怎麼化解",           "obstacle-2027",     "感情阻礙,2027化解"),
        ("2027異地戀能維持嗎",             "ld-2027",           "異地戀,2027感情"),
        ("2027桃花旺但感情穩定嗎",         "peach-2027",        "桃花多,2027感情穩"),
        ("2027適合結婚嗎",                 "marry-2027",        "結婚,2027感情"),
        ("2027感情冷淡期如何激活",         "reactivate-2027",   "感情冷淡,2027激活"),
        ("2027遇到舊情人是緣是劫",         "ex-2027",           "舊情人,2027感情"),
        ("2027暗戀能表白成功嗎",           "secret-love-2027",  "暗戀,2027表白"),
        ("2027感情是大破大立的一年嗎",     "big-change-2027",   "感情變化,2027大運"),
        ("2028感情運整體走勢預測",         "love-2028",         "2028感情運,整體預測"),
        ("2028桃花運最旺月份",             "peach-2028",        "2028桃花,桃花月"),
        ("2028單身求緣最好時機",           "single-2028",       "2028脫單,求緣時機"),
        ("感情一直不順是命中注定嗎",       "love-fate",         "感情不順,命中注定"),
        ("八字看感情何時到來",             "bazi-love",         "八字感情,何時到來"),
        ("適合和什麼生肖的人在一起",       "best-match",        "生肖配對,感情合適"),
        ("和哪個生肖在一起最容易分手",     "worst-match",       "生肖不合,感情地雷"),
        ("生肖看感情中容易遇到的問題",     "love-problem",      "生肖感情問題,特質"),
        ("生肖看吵架後多久會主動和好",     "makeup-time",       "生肖冷戰,和好時間"),
        ("生肖看喜歡一個人的表現方式",     "love-expression",   "生肖示愛,表達喜歡"),
        ("生肖看被甩後需要多久走出來",     "recovery-time",     "失戀復原,生肖時間"),
        ("生肖看曖昧期多久才會表白",       "confess-timing",    "曖昧期,生肖表白"),
        ("生肖看這個人對你是否認真",       "is-serious",        "是否認真,生肖判斷"),
    ]
    for ani, aen in animals:
        for qsuffix, qslug, kws in shengxiao_qs:
            _make(
                title=f"屬{ani}｜{qsuffix}",
                slug=f"sx-{aen}-{qslug}",
                utm="shengxiao", category="生肖運勢",
                keywords=f"屬{ani},{kws},生肖感情",
                desc=f"屬{ani}的人：{qsuffix}完整分析",
                prompt_core=(
                    f"針對屬{ani}的人「{qsuffix}」給出深度分析，"
                    f"結合生肖特質和命理觀點給出具體建議"
                ),
            )

    # ─────────────────────────────────────────────────────────────────
    # H. 月亮星座/上升星座 × 感情場景 — 12×12=144 組合 × 3問 = 432 頁
    # ─────────────────────────────────────────────────────────────────
    moon_qs = [
        ("月亮星座看感情中的情緒反應模式", "moon-emotion",  "月亮星座,感情情緒"),
        ("上升星座影響第一印象和吸引力",   "rising-attract","上升星座,第一印象"),
        ("月亮星座看吵架後的修復需求",     "moon-makeup",   "月亮星座,冷戰修復"),
    ]
    for zi, ze in zodiacs:
        for zi2, ze2 in zodiacs:
            for qsuffix, qslug, kws in moon_qs:
                _make(
                    title=f"太陽{zi}月亮{zi2}｜{qsuffix}",
                    slug=f"sun{ze}-moon{ze2}-{qslug}",
                    utm="astro", category="星座進階",
                    keywords=f"{zi},{zi2},太陽月亮,{kws}",
                    desc=f"太陽{zi}月亮{zi2}的感情特質分析",
                    prompt_core=(
                        f"分析太陽{zi}、月亮{zi2}組合的人在感情中「{qsuffix}」，"
                        f"兩個星座能量如何影響這個人的感情模式"
                    ),
                )

    # ─────────────────────────────────────────────────────────────────
    # I. 八字命理感情場景 — 天干地支 × 感情問題 ≈ 200 頁
    # ─────────────────────────────────────────────────────────────────
    heavenly_stems = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"]
    earthly_branches = ["子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"]
    bazi_qs = [
        ("日柱看感情中的相處模式",     "daily-pillar-love", "八字日柱,感情相處"),
        ("八字看何時是感情旺盛期",     "love-peak-bazi",    "八字感情,旺盛期"),
        ("八字看感情劫的化解方法",     "love-disaster",     "感情劫,八字化解"),
        ("日主強弱影響感情運勢",       "daymaster-love",    "日主,感情運勢"),
    ]
    for hs in heavenly_stems:
        for eb in earthly_branches[:5]:  # 只用前5地支避免過多
            for qsuffix, qslug, kws in bazi_qs:
                _make(
                    title=f"{hs}{eb}日柱｜{qsuffix}",
                    slug=f"bazi-{hs}{eb}-{qslug}",
                    utm="bazi", category="八字命理",
                    keywords=f"{hs}{eb}日柱,{kws}",
                    desc=f"{hs}{eb}日柱的人：{qsuffix}完整解析",
                    prompt_core=(
                        f"以八字{hs}{eb}日柱為基礎，分析「{qsuffix}」，"
                        f"結合天干地支的五行特質給出具體感情建議"
                    ),
                )

    # ─────────────────────────────────────────────────────────────────
    # J. 感情行為情境分析 — 純場景長尾詞 ≈ 500 頁
    # ─────────────────────────────────────────────────────────────────
    longtail_pages = [
        # 月老籤 × 具體困境（20）
        ("月老靈籤問感情要怎麼許願才有效", "yuelao-how-pray", "月老許願,感情許願"),
        ("抽到上上籤感情還是沒有進展是怎麼回事","upper-sign-no-progress","上上籤,感情沒進展"),
        ("月老靈籤抽到下下籤感情真的沒救了嗎","lower-sign-hope","下下籤,感情挽回"),
        ("問復合抽到中籤是好還是壞","mid-sign-reunion","中籤解讀,問復合"),
        ("月老說感情有阻礙是指什麼阻礙","love-obstacles-type","感情阻礙,月老解籤"),
        ("同一個問題一直抽到同一張籤代表什麼","same-sign-repeat","重複抽籤,月老訊息"),
        ("感情籤詩說要等待要等多久","waiting-period-sign","等待時機,感情籤詩"),
        ("問喜歡的人抽到代表相思的籤","lovesick-sign","相思籤,暗戀占卜"),
        ("月老籤詩說要主動怎麼主動","how-to-initiate-sign","主動追求,感情主動"),
        ("問姻緣籤詩說緣分已到是真的嗎","fate-arrived-sign","緣分到來,正緣"),
        ("月老靈籤和塔羅結果不同要相信哪個","sign-vs-tarot","月老vs塔羅,占卜比較"),
        ("連續三次都抽到凶籤感情是不是沒希望","bad-sign-3times","凶籤,感情絕望"),
        ("男生可以幫女生去月老廟求籤嗎","male-pray-for-female","代求籤,感情代禱"),
        ("月老籤詩講的時間怎麼換算現代","sign-time-convert","籤詩時間,換算方法"),
        ("問是否有外遇月老靈籤準不準","infidelity-sign","外遇,第三者,月老籤"),
        ("月老靈籤上中下籤的完整分類說明","sign-classification","月老籤類型,解籤說明"),
        ("在外地可以網路代求月老籤嗎","online-pray-yuelao","網路代求籤,月老"),
        ("月老靈籤和命盤合盤哪個更準","sign-vs-chart","月老籤vs合盤,準確度"),
        ("失戀中抽籤心情影響結果嗎","emotion-affect-sign","心情影響占卜,失戀抽籤"),
        ("問感情問幾次比較合適不要太貪心","how-many-times","抽籤次數,感情占卜"),
        # 塔羅困境（20）
        ("塔羅問他有沒有在想我怎麼解讀","tarot-he-thinking","塔羅占卜,對方想法"),
        ("塔羅問感情未來出現死神牌是完了嗎","tarot-death-future","死神牌,感情未來"),
        ("塔羅問復合出現高塔牌代表什麼","tarot-tower-reunion","高塔牌,復合塔羅"),
        ("塔羅問他喜歡我嗎出現戀人牌","tarot-lovers-like","戀人牌,塔羅喜歡"),
        ("自己占卜塔羅結果可信嗎","tarot-self-read","自占塔羅,準確度"),
        ("問同一件事一直出現逆位是怎麼回事","tarot-reversed-repeat","逆位,重複牌"),
        ("感情位置一直出現寶劍牌組","tarot-swords-love","寶劍牌組,感情衝突"),
        ("初學者用塔羅問感情最容易犯的錯誤","tarot-beginner-mistakes","塔羅新手,感情占卜"),
        ("塔羅問這段感情值不值得繼續","tarot-worth-continuing","感情值得,塔羅判斷"),
        ("塔羅逆位一定是壞的意思嗎","tarot-reversed-meaning","逆位含義,塔羅基礎"),
        ("塔羅問第三者的出現在哪張牌","tarot-third-party","第三者,塔羅判斷"),
        ("塔羅感情牌陣怎麼擺最準確","tarot-spread-setup","塔羅牌陣,感情占卜"),
        ("塔羅代表舊情人的牌有哪些","tarot-ex-cards","前任,舊情人,塔羅"),
        ("塔羅感情中最讓人害怕的五張牌","tarot-scary-cards","塔羅恐懼,感情壞牌"),
        ("塔羅代表真愛的牌有哪些","tarot-true-love","真愛,塔羅好牌"),
        ("問對方有沒有外遇要用哪個牌陣","tarot-infidelity","外遇塔羅,第三者牌陣"),
        ("塔羅感情占卜前要怎麼淨化牌","tarot-cleansing","塔羅淨化,感情占卜"),
        ("問新認識的人適不適合深交","tarot-new-person","新認識,深交,塔羅"),
        ("塔羅感情結果和星座運勢不同怎麼辦","tarot-vs-zodiac","塔羅vs星座,感情比較"),
        ("塔羅感情占卜每天都問好嗎","tarot-daily-ask","每天占卜,塔羅頻率"),
        # 感情行為分析（無星座）（60）
        ("喜歡的人突然變得很冷淡是發生什麼事","suddenly-cold","突然冷淡,感情變化"),
        ("秒回但約出來一直推說不行代表什麼","reply-fast-refuse","秒回不約,感情訊號"),
        ("男生說很忙但還是會傳訊息是在意嗎","busy-man-text","男生說忙,傳訊息"),
        ("異地戀突然不回訊息三天怎麼辦","ld-no-reply-3d","異地戀,不回訊息"),
        ("曖昧一個月他說我們當朋友就好","friendzone-after-aimei","朋友就好,曖昧後被拒"),
        ("主動追了一個月對方沒什麼反應","1m-chase-no-response","追了一個月,沒反應"),
        ("他說現在不想談感情是在拒絕我嗎","dont-want-rs","不想談感情,被拒"),
        ("分手後他主動傳訊息說想你","ex-miss-you","前任說想你,分手後"),
        ("喜歡一個人怎麼看出他有沒有喜歡你","how-to-know-likes","判斷喜歡,感情訊號"),
        ("感情問題一直用占卜決定是不是不健康","relying-divination","過度占卜,感情依賴"),
        ("告白被拒後還能當朋友嗎","after-rejection","告白被拒,是否當朋友"),
        ("喜歡一個人多久才算適合表白","when-to-confess","表白時機,告白準備"),
        ("男生不主動但又不拒絕你","passive-not-refuse","不主動不拒絕,模糊態度"),
        ("在一起一年了感覺越來越像朋友","1y-like-friends","熱情消退,感情瓶頸"),
        ("他傳訊息都很簡短是不在意我嗎","short-replies","短回覆,是否在意"),
        ("異地戀多久要見一次面才能維持","ld-meet-frequency","異地戀見面,多久見面"),
        ("男生第一次約會後沒有主動傳訊息","first-date-no-text","第一次約會,沒主動"),
        ("她說我們不合適是在拒絕我嗎","not-suitable","不合適,是否拒絕"),
        ("在一起很久了他沒有求婚意思","no-proposal","求婚,長期交往"),
        ("告白前怎麼確認對方對你的感覺","pre-confession-check","告白前確認,感情訊號"),
        ("前任突然說想見你是什麼動機","ex-wants-meet","前任見面,動機"),
        ("怎麼知道自己是喜歡還是習慣他","like-or-habit","喜歡還是習慣,感情"),
        ("感情中覺得自己付出比較多","imbalanced-effort","付出不對等,感情失衡"),
        ("男生送禮物但不表白是什麼意思","gift-no-confession","送禮物,不表白"),
        ("失戀後多久才算適合重新開始","after-break-new","失戀多久,重新開始"),
        ("如何讓一段停滯的感情有進展","stagnant-rs","感情停滯,推進感情"),
        ("他說喜歡你但又說現在不想談","like-but-no-rs","喜歡但不談感情,模糊"),
        ("不擅長表達感情的人怎麼判斷","bad-expressing","不善表達,感情判斷"),
        ("兩個人都不主動推進感情","both-passive","雙方不主動,感情進退"),
        ("曖昧期說太喜歡你了會嚇跑嗎","express-too-much","說太喜歡,嚇跑對方"),
        ("感情占卜用哪種方式最準","best-divination","感情占卜方式,哪種準"),
        ("占卜感情結果不好可以重新占嗎","redivine-bad","重新占卜,感情結果"),
        ("感情占卜對決策真的有幫助嗎","divination-decision","占卜決策,感情選擇"),
        ("為什麼感情占卜有時準有時不準","divination-accuracy","占卜準確度,影響因素"),
        ("同時喜歡兩個人怎麼辦","like-two-people","喜歡兩個人,感情選擇"),
        ("失戀後一直想聯絡前任要怎麼忍住","post-break-no-contact","失戀,不聯絡前任"),
        ("怎麼知道已經走出失戀了","healed-breakup","走出失戀,心理復原"),
        ("和前任保持朋友關係是正確的嗎","ex-as-friends","前任朋友,分手後"),
        ("剛分手馬上交新戀情是逃避嗎","rebound-rs","閃回,速食感情"),
        ("感情裡的安全感要靠自己還是對方","security-love","安全感,感情依賴"),
        ("在乎的人卻一直讓你感到焦慮","love-anxiety","感情焦慮,在乎才焦慮"),
        ("如何讓自己在感情裡不那麼患得患失","less-anxious","患得患失,感情焦慮"),
        ("對感情死心了要怎麼確認自己放棄","give-up-love","死心,確認放棄"),
        ("告白成功後關係反而變奇怪","post-confess-awkward","告白成功後尷尬"),
        ("喜歡的人和別人很好但對我很普通","special-others","對別人好,對我普通"),
        ("為什麼每次感情都是自己受傷先放手","always-hurt","感情模式,重複受傷"),
        ("怎麼在感情裡保有自我","keep-self-love","感情自我,獨立性"),
        ("感情裡的嫉妒心要怎麼控制","jealousy-control","嫉妒心,感情嫉妒"),
        ("在一起很自然但沒有心動感","comfort-no-spark","相處自然無心動"),
        ("如何判斷自己是否真的愛上一個人","know-if-love","愛的感覺,判斷真愛"),
        ("表白被拒後多久可以再試一次","try-again-rejection","被拒後再試,時機"),
        ("感情裡的承諾是否有必要說出口","verbal-commitment","感情承諾,說出口"),
        ("怎麼在不催婚的情況下讓男友考慮婚姻","marriage-no-pressure","催婚,結婚計劃"),
        ("感情中冷戰最長多久算正常","cold-war-duration","冷戰,多久正常"),
        ("為什麼越喜歡越不敢在他面前表現","shy-with-crush","越喜歡越不自然"),
        ("如何知道一段感情是否值得繼續努力","worth-continuing","感情值得,判斷依據"),
        ("愛一個人愛得很累要怎麼辦","love-exhausted","愛得很累,感情疲憊"),
        ("感情裡的直覺準不準應該相信嗎","love-intuition","感情直覺,相信直覺"),
        ("兩個人在一起到底算不算正式交往","official-dating","正式交往,關係定義"),
        ("要怎麼鼓起勇氣告白不後悔","confession-courage","告白勇氣,表白技巧"),
        # 星座進階議題（40）
        ("水瓶座女生和天蠍座男生在一起合適嗎","aqua-scorp-compat","水瓶座,天蠍座,配對"),
        ("雙魚座女生和射手座男生能走到最後嗎","pisc-sagi-compat","雙魚座,射手座,配對"),
        ("巨蟹座和摩羯座真的是天生一對嗎","canc-capr-compat","巨蟹座,摩羯座,對立"),
        ("獅子座女生配什麼星座最適合","leo-female-match","獅子座女,最配星座"),
        ("處女座配對哪個星座最不合","virgo-worst-match","處女座,星座不合"),
        ("上升星座影響感情的程度比太陽大嗎","rising-vs-sun","上升星座,太陽星座"),
        ("看月亮還是太陽星座來判斷感情","moon-vs-sun-love","月亮星座,感情判斷"),
        ("星座配對不合還是在一起幸福的案例","incompat-happy","星座不合,幸福案例"),
        ("金牛座男生被甩後多久才會主動找回","taurus-male-ex","金牛座,被甩,主動"),
        ("天蠍座女生生氣後沉默多久才會好","scorpio-female-angry","天蠍座,生氣沉默"),
        ("雙子座男生曖昧期到底有沒有在認真","gemini-male-aimei","雙子座男,曖昧認真"),
        ("巨蟹座女生哭了之後需要什麼安慰","cancer-female-cry","巨蟹座女,哭泣安慰"),
        ("牡羊座男生說愛你是認真的還是說說","aries-male-love","牡羊座男,說愛你"),
        ("天秤座女生一直說要想想是什麼意思","libra-female-think","天秤座女,說要想想"),
        ("射手座男生突然不聯絡是不是移情了","sagi-male-gone","射手座男,突然消失"),
        ("摩羯座女生冷戰最長可以多久","capri-female-cold","摩羯座女,冷戰時間"),
        ("水瓶座男生吃醋嗎怎麼表現","aqua-male-jealous","水瓶座男,吃醋"),
        ("雙魚座女生感情中容易遇到什麼問題","pisc-female-problem","雙魚座女,感情問題"),
        ("處女座男生喜歡你的10個表現","virgo-male-likes","處女座男,喜歡表現"),
        ("獅子座女生分手後還會主動找前任嗎","leo-female-ex","獅子座女,分手前任"),
        ("天蠍座男生冷淡是因為不喜歡嗎","scorpio-male-cold","天蠍座男,冷淡"),
        ("金牛座女生異地戀能維持嗎","taurus-female-ld","金牛座女,異地戀"),
        ("雙子座女生感情花心是真的嗎","gemini-female-fickle","雙子座女,花心"),
        ("巨蟹座男生保護欲太強怎麼溝通","cancer-male-protect","巨蟹座男,保護欲"),
        ("牡羊座女生被冷落了會怎麼樣","aries-female-neglect","牡羊座女,被冷落"),
        ("天秤座男生優柔寡斷在感情上怎麼辦","libra-male-indecisive","天秤座男,優柔寡斷"),
        ("射手座女生害怕承諾怎麼讓她定下來","sagi-female-commit","射手座女,害怕承諾"),
        ("摩羯座男生工作狂感情怎麼排第幾","capri-male-career","摩羯座男,工作vs感情"),
        ("水瓶座女生感情距離感怎麼拉近","aqua-female-distance","水瓶座女,距離感"),
        ("雙魚座男生在感情中容易移情別戀嗎","pisc-male-wander","雙魚座男,移情別戀"),
        ("感情裡最會吃醋的三個星座","most-jealous-zodiac","吃醋星座,嫉妒"),
        ("感情裡最容易冷戰的三個星座","most-coldwar-zodiac","冷戰星座,沉默"),
        ("感情裡最難追的三個星座","hardest-chase-zodiac","難追星座,感情挑戰"),
        ("感情裡最專一的三個星座","most-loyal-zodiac","專一星座,忠誠感情"),
        ("感情裡最容易移情別戀的星座","most-fickle-zodiac","花心星座,移情"),
        ("感情裡最會表達愛意的星座","most-expressive-zodiac","表達愛意,星座"),
        ("感情遇到困難最不放棄的星座","most-persistent-zodiac","不放棄,堅持感情"),
        ("最容易因為太自由而破壞感情的星座","too-free-zodiac","自由感情,星座問題"),
        ("最需要對方陪伴和安全感的星座","need-security-zodiac","安全感,星座依賴"),
        ("感情中最容易成為備胎的星座","backup-zodiac","備胎,被利用星座"),
    ]
    for title, slug, kws, *_ in longtail_pages:
        desc = kws.split(",")[0] + "的深度感情分析"
        _make(
            title=title, slug=f"lt-{slug}",
            utm="longtail", category="感情占卜",
            keywords=kws,
            desc=desc,
            prompt_core=f"針對「{title}」這個問題給出深度分析和具體建議",
        )

    # ─────────────────────────────────────────────────────────────────
    # K. 感情修復/溝通技巧 × 星座 — 12 × 10 = 120 頁
    # ─────────────────────────────────────────────────────────────────
    repair_qs = [
        ("怎麼道歉才有效不只是說對不起",   "apology-effective", "道歉方式,感情修復"),
        ("冷戰後怎麼重新開口不尷尬",       "resume-after-cold", "冷戰後和好,開口方式"),
        ("如何讓他主動找你而不是你一直等", "make-contact-first","讓對方主動,感情技巧"),
        ("說分手後悔了要怎麼挽回",         "regret-breakup",    "後悔分手,挽回感情"),
        ("如何在不逼迫的情況下讓關係進展", "progress-no-force", "推進感情,不逼迫"),
        ("吵架後他說需要時間怎麼應對",     "fight-need-time",   "吵架後,說需要時間"),
        ("如何讓感情保持新鮮感不無聊",     "keep-fresh",        "感情新鮮感,維持熱情"),
        ("如何讓對方知道你在意但不黏人",   "care-not-clingy",   "在意不黏,感情平衡"),
        ("如何在感情裡建立健康的界線",     "healthy-boundary",  "感情界線,健康關係"),
        ("長期感情如何重新點燃熱情",       "rekindle-long",     "長期感情,重燃激情"),
    ]
    for zi, ze in zodiacs:
        for qsuffix, qslug, kws in repair_qs:
            _make(
                title=f"{zi}感情修復｜{qsuffix}",
                slug=f"{ze}-repair-{qslug}",
                utm="repair", category="感情技巧",
                keywords=f"{zi},{kws},感情修復",
                desc=f"和{zi}的感情遇到問題？{qsuffix}完整指南",
                prompt_core=(
                    f"從{zi}星座的性格特質分析「{qsuffix}」，"
                    f"給出針對這個星座有效的具體行動方式和話術"
                ),
            )

    # ─────────────────────────────────────────────────────────────────
    # L. 年度運勢 × 星座 × 季度 — 12 × 4季 × 3面向 = 144 頁
    # ─────────────────────────────────────────────────────────────────
    quarters = [
        ("2027年第一季感情運勢", "q1-2027", "2027Q1,感情運勢,第一季"),
        ("2027年第二季感情運勢", "q2-2027", "2027Q2,感情運勢,第二季"),
        ("2027年第三季感情運勢", "q3-2027", "2027Q3,感情運勢,第三季"),
        ("2027年第四季感情運勢", "q4-2027", "2027Q4,感情運勢,第四季"),
    ]
    quarter_aspects = [
        ("完整預測與注意事項", "full", "整體預測"),
        ("桃花高峰期和告白最佳時機", "peach-peak", "桃花高峰"),
        ("感情阻礙和化解方法", "obstacle-resolve", "感情阻礙"),
    ]
    for zi, ze in zodiacs:
        for qname, qslug, qkws in quarters:
            for aname, aslug, akws in quarter_aspects:
                _make(
                    title=f"{zi}｜{qname}｜{aname}",
                    slug=f"{ze}-{qslug}-{aslug}",
                    utm="fortune2027", category="星座運勢",
                    keywords=f"{zi},{qkws},{akws}",
                    desc=f"{zi}{qname}：{aname}完整解析",
                    prompt_core=(
                        f"預測{zi}在{qname}的「{aname}」，"
                        f"給出具體月份提示和行動建議"
                    ),
                )

    # ─────────────────────────────────────────────────────────────────
    # M. 分手/失戀/復合 完整攻略 × 星座 — 12 × 8 = 96 頁
    # ─────────────────────────────────────────────────────────────────
    breakup_qs = [
        ("和這個星座分手後多久他會主動聯絡", "breakup-contact-time", "分手後聯絡,主動找回"),
        ("這個星座分手後能做到完全斷聯嗎",   "can-no-contact",       "完全斷聯,分手後"),
        ("如何讓這個星座主動提出復合",       "make-ex-propose",      "對方主動復合,星座"),
        ("和這個星座分手後復合成功率高嗎",   "reunion-rate",         "復合成功率,星座"),
        ("這個星座分手後還會吃醋嗎",         "post-break-jealous",   "分手後吃醋,星座"),
        ("讓這個星座後悔分手的方法",         "make-regret",          "讓對方後悔,星座挽回"),
        ("如何跟這個星座好聚好散",           "good-farewell",        "好好分手,星座溝通"),
        ("這個星座最難忘的前任類型",         "hard-to-forget-ex",    "難忘前任,星座類型"),
    ]
    for zi, ze in zodiacs:
        for qsuffix, qslug, kws in breakup_qs:
            _make(
                title=f"{zi}｜{qsuffix}",
                slug=f"{ze}-break-{qslug}",
                utm="breakup", category="感情修復",
                keywords=f"{zi},{kws}",
                desc=f"{zi}的分手與復合：{qsuffix}深度分析",
                prompt_core=(
                    f"從{zi}星座的心理特質分析「{qsuffix}」，"
                    f"給出針對這個星座有效的具體建議和話術"
                ),
            )

    # ─────────────────────────────────────────────────────────────────
    # N. 感情心理學 × 情境分析 — 100 頁
    # ─────────────────────────────────────────────────────────────────
    psych_topics = [
        ("為什麼越愛越沒有安全感的心理分析","psych-love-insecurity","愛越深越不安,心理"),
        ("迴避型依附在感情裡的表現和應對","psych-avoidant","迴避型依附,感情模式"),
        ("焦慮型依附讓感情很累怎麼改善","psych-anxious","焦慮型依附,感情焦慮"),
        ("為什麼喜歡不愛你的人心理學解析","psych-unavailable","愛不對的人,心理分析"),
        ("感情裡的自我破壞行為怎麼停止","psych-self-sabotage","自我破壞,感情問題"),
        ("如何辨識愛情轟炸和真正的喜歡","psych-love-bombing","愛情轟炸,真愛辨別"),
        ("分手後為什麼越想越難受心理原因","psych-post-break","分手越來越難受,心理"),
        ("為什麼有人在感情裡容易成為工具人","psych-nice-guy","工具人心理,感情付出"),
        ("感情裡總是讓步的人心理特質分析","psych-always-yield","總是讓步,感情心理"),
        ("為什麼感情中容易被PUA怎麼識別","psych-pua-identify","PUA辨識,感情操控"),
        ("感情裡的嫉妒心從哪裡來怎麼管理","psych-jealousy","嫉妒心理,感情嫉妒"),
        ("為什麼分手後還是會夢到前任","psych-dream-ex","夢到前任,心理解析"),
        ("如何建立健康的感情自我邊界","psych-boundaries","感情邊界,心理健康"),
        ("為什麼我總是喜歡不適合自己的人","psych-wrong-person","喜歡不適合,模式"),
        ("感情中的控制慾從哪來怎麼克服","psych-control","控制慾,感情問題"),
        ("分手後為什麼會有物理性的心痛感","psych-heartbreak-pain","失戀心痛,生理現象"),
        ("怎麼區分真愛和對對方的執念","psych-love-vs-obsession","真愛vs執念,感情"),
        ("為什麼有些人在感情裡容易消失","psych-ghosting","被ghost,突然消失"),
        ("感情裡的吃醋到什麼程度算健康","psych-healthy-jealousy","健康嫉妒,吃醋程度"),
        ("如何不靠對方也能建立自我價值感","psych-self-worth","自我價值,感情獨立"),
        ("為什麼越在乎對方越容易討好","psych-people-pleasing","討好型,感情委屈"),
        ("感情中為什麼越說越吵解決不了","psych-argue-cycle","感情吵架惡性循環,溝通"),
        ("失戀後的悲傷期大概需要多久","psych-grief-period","失戀悲傷期,多久走出"),
        ("感情裡比較健康的相處距離是什麼","psych-healthy-distance","感情距離,相處模式"),
        ("如何不依賴對方也能找到幸福感","psych-independence","感情獨立,幸福來源"),
        ("為什麼有人分手後馬上找新對象","psych-rebound-reason","速食感情,原因分析"),
        ("感情裡的沉默成本讓你無法離開","psych-sunk-cost","沉沒成本,感情執念"),
        ("如何辨識對方是喜歡你還是習慣你","psych-habit-vs-love","習慣vs喜歡,感情判斷"),
        ("為什麼感情裡總是我先讓步","psych-always-give-in","總是先讓步,心理原因"),
        ("如何不害怕說出自己在感情裡的需求","psych-express-needs","說出需求,感情表達"),
        ("感情中為什麼越解釋越說不清楚","psych-over-explain","越解釋越亂,溝通問題"),
        ("如何培養在感情裡的自信心","psych-confidence","感情自信,不卑微"),
        ("為什麼分手後會一直刷他的社群","psych-social-stalking","刷前任社群,心理"),
        ("感情裡的過度付出最後為什麼都失敗","psych-over-give","過度付出,感情失敗"),
        ("如何讓自己停止過度想像和分析","psych-overthink","感情過度分析,停止想"),
        ("愛情和依賴的差異怎麼區分","psych-love-vs-depend","愛vs依賴,感情判斷"),
        ("感情裡的爭吵之後如何有效修復","psych-repair-after-fight","吵架後修復,溝通"),
        ("如何在失戀後不走錯誤的復合回頭路","psych-wrong-reunion","錯誤復合,感情陷阱"),
        ("為什麼有人寧可單身也不要將就","psych-rather-single","寧願單身,感情標準"),
        ("感情裡的心動感消失了還要繼續嗎","psych-no-spark","心動消失,感情判斷"),
        ("如何在感情中保持自我不完全融入","psych-keep-identity","感情自我,保持個性"),
        ("愛情裡的不安全感要靠自己療癒嗎","psych-heal-insecurity","療癒不安感,感情"),
        ("感情中的失望累積最後變成冷漠","psych-disappointment","感情失望,累積冷漠"),
        ("如何把前任從心裡徹底刪除","psych-delete-ex","刪除前任,心理技巧"),
        ("為什麼很多人寧願不表白也不要失去","psych-fear-rejection","害怕被拒,感情恐懼"),
        ("感情中的爭吵到底有沒有贏家","psych-no-winner","感情爭吵,沒有贏家"),
        ("如何重建分手後的自信心和自尊","psych-rebuild-confidence","失戀後自信,重建"),
        ("為什麼有些感情讓人越來越消耗","psych-draining-love","消耗型感情,離開"),
        ("感情裡的好好說話為什麼那麼難","psych-hard-to-talk","感情溝通難,心理"),
        ("如何讓感情不因為太熟悉而消磨","psych-familiarity","感情太熟,消磨熱情"),
        ("感情中為什麼越要求越得不到","psych-demand-backfire","越要求越得不到,感情"),
        ("如何辨識健康和不健康的戀愛關係","psych-healthy-vs-toxic","健康關係,toxic感情"),
        ("感情中的過度期待如何調整","psych-expectations","感情期待,調整心態"),
        ("為什麼有人在感情裡很容易受傷","psych-sensitive-hurt","感情敏感,容易受傷"),
        ("如何不把前任的陰影帶進新感情","psych-past-shadow","前任陰影,新感情"),
        ("感情裡總是在等待對方的人心理分析","psych-always-wait","總是在等,感情心理"),
        ("如何讓感情裡的不安轉化成動力","psych-anxiety-to-action","感情不安轉動力"),
        ("分手後的空洞感要如何填補","psych-emptiness","失戀空洞感,填補"),
        ("感情裡的理想化和現實落差怎麼調適","psych-idealization","感情理想化,落差"),
        ("如何在不受傷的前提下先喜歡一個人","psych-protect-heart","保護自己,喜歡人"),
        ("感情裡的主動和被動平衡在哪","psych-active-passive","主動被動,感情平衡"),
    ]
    for title, slug, kws in psych_topics:
        _make(
            title=title, slug=f"psych-{slug}",
            utm="psychology", category="感情心理",
            keywords=kws,
            desc=kws.split(",")[0] + "深度心理分析",
            prompt_core=f"從心理學角度深度分析「{title}」，結合依附理論和感情心理學給出實用建議",
        )

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
  <meta property="og:image" content="{og_image_url}">
  <meta property="og:image:width" content="800">
  <meta property="og:image:height" content="420">
  <meta property="og:image:alt" content="{title}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{og_image_url}">

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
        "image": {{"@type": "ImageObject", "url": "{og_image_url}", "width": 800, "height": 420}},
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
        "primaryImageOfPage": {{"@type": "ImageObject", "url": "{og_image_url}", "width": 800, "height": 420}}
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


# ─────────────────────────────────────────────
# OG 配圖生成
# ─────────────────────────────────────────────

_FONT_SERIF = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
_FONT_SANS  = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
# 備用字體（GitHub Actions ubuntu-latest 有安裝）
_FONT_FALLBACKS = [
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

def _get_font(size: int, serif: bool = True) -> "ImageFont.FreeTypeFont":
    """取得字體，找不到理想字體就嘗試備用"""
    candidates = [_FONT_SERIF if serif else _FONT_SANS] + _FONT_FALLBACKS
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_og_image(title: str, category: str, out_path: Path) -> bool:
    """
    生成 800×420 OG 配圖，存到 out_path。
    回傳 True 表示成功，False 表示 Pillow 不可用或失敗。
    """
    if not _PIL_OK:
        return False
    try:
        W, H = 800, 420

        # ── 背景漸層（深紅→深紫紅）──
        img = Image.new("RGB", (W, H))
        draw = ImageDraw.Draw(img)
        for i in range(H):
            t = i / H
            r = int(160 * (1 - t) + 100 * t)
            g = int(28  * (1 - t) + 15  * t)
            b = int(28  * (1 - t) + 70  * t)
            draw.line([(0, i), (W, i)], fill=(r, g, b))

        # ── 頂部金色條 ──
        draw.rectangle([0, 0, W, 7], fill=(212, 175, 55))
        # ── 底部金色條 ──
        draw.rectangle([0, H - 7, W, H], fill=(212, 175, 55))

        # ── 右下角裝飾圓（半透明感） ──
        draw.ellipse([W - 160, H - 160, W + 60, H + 60],
                     fill=(255, 200, 80, 25))

        # ── 品牌名 ──
        font_brand = _get_font(24, serif=True)
        draw.text((44, 22), "月下 · 感情占卜", font=font_brand,
                  fill=(212, 175, 55))

        # ── 分類標籤 ──
        font_cat = _get_font(19, serif=False)
        cat_text = f"# {category}"
        draw.text((44, 56), cat_text, font=font_cat, fill=(255, 200, 150))

        # ── 分隔線 ──
        draw.line([(44, 86), (W - 44, 86)], fill=(255, 255, 255, 60), width=1)

        # ── 標題（自動換行，每行 ≤13 字） ──
        font_title = _get_font(40, serif=True)
        lines = textwrap.wrap(title, width=13)[:3]  # 最多3行
        y = 108
        for line in lines:
            draw.text((44, y), line, font=font_title, fill=(255, 255, 255))
            y += 56

        # ── 副文案 ──
        font_sub = _get_font(20, serif=False)
        draw.text((44, y + 18),
                  "深度解析 · 感情建議 · 實用攻略",
                  font=font_sub, fill=(255, 210, 170))

        # ── 底部域名 ──
        font_url = _get_font(17, serif=False)
        draw.text((44, H - 36), "cqseo.github.io/heimaoseo",
                  font=font_url, fill=(200, 200, 200))

        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out_path), "PNG", optimize=True)
        return True
    except Exception as e:
        print(f"  [OG圖生成失敗] {e}")
        return False


def _clean_text(text: str) -> str:
    """移除 LLM 可能帶入的 Markdown 符號，確保輸出是乾淨的 HTML 文字"""
    # 移除 **粗體**、*斜體*、__底線__ 等 markdown 符號
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', text)
    # 移除 # 標題符號（行首）
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    # 移除反引號
    text = re.sub(r'`+([^`]*)`+', r'\1', text)
    # 移除多餘的連字號列表符號
    text = re.sub(r'^\s*[-•]\s*', '', text, flags=re.MULTILINE)
    # 移除數字列表「1. 」「2. 」（保留內容）
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # 合併多餘空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    # HTML 轉義（< > &）
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    # 段落換行轉 <br>
    text = text.replace('\n\n', '</p><p>').replace('\n', '<br>')
    return text.strip()


def render_html(item: dict, data: dict) -> str:
    slug      = item["slug"]
    canonical = f"{SITE_BASE}/p/{slug}/"
    og_image_url = f"{SITE_BASE}/p/{slug}/og.png"
    cta_url   = f"{TARGET_URL}?utm_source=seo&utm_medium={item['utm']}&utm_campaign={slug}"
    cat_slug = item["category"].replace("星座","zodiac").replace("生肖","shengxiao")\
                               .replace("塔羅","tarot").replace("廟宇","temple")\
                               .replace("月老","yuelao").replace("運勢","fortune")\
                               .replace("感情","love").replace("占卜","divination")
    cat_slug = re.sub(r'[^\w-]', '', cat_slug)

    faqs = data.get("faq", [])[:3]
    tips = data.get("tips", [])[:3]

    faq_html = "\n    ".join(
        f'<details><summary>{_clean_text(f["q"])}</summary>'
        f'<div class="faq-answer">{_clean_text(f["a"])}</div></details>'
        for f in faqs
    )
    tips_html = "\n      ".join(f"<li>{_clean_text(t)}</li>" for t in tips)
    faq_schema = build_faq_schema(faqs)
    date_str   = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 清理正文 markdown
    para1_clean = _clean_text(data["para1"])
    para2_clean = _clean_text(data["para2"])

    return HTML_TEMPLATE.format(
        title=item["title"], site_name=SITE_NAME, site_base=SITE_BASE,
        desc=item["desc"], keywords=item["keywords"],
        canonical=canonical, cta_url=cta_url, target_url=TARGET_URL,
        og_image_url=og_image_url,
        category=item["category"], cat_slug=cat_slug,
        para1=para1_clean, para2=para2_clean,
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
                        "擅長撰寫有深度、有共鳴的感情諮詢長文。\n"
                        "【絕對禁止事項】\n"
                        "1. 禁止出現簡體字，全程使用台灣正體繁體中文\n"
                        "2. 禁止出現任何英文字母（包括utm、para等）\n"
                        "3. 禁止在JSON值中使用markdown符號：**、*、__、#、```、-列表符號、數字列表\n"
                        "4. 輸出必須是合法JSON，不要加代碼塊反引號，不要加```json\n"
                        "5. 禁止出現換行符\\n，段落直接寫成連續文字\n"
                        "【必須做到】\n"
                        "6. para1 和 para2 每段必須超過400字，要有具體內容和細節\n"
                        "7. FAQ每個答案必須超過80字，要實用不能空泛\n"
                        "8. 語氣親切口語，像台灣閨蜜在聊天，不要文縐縐\n"
                        "9. 內容要具體，要有可執行的建議，不要只說「放寬心」之類的廢話"
                    )},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.85,
                max_tokens=2500,
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
    lock = __import__("threading").Lock()

    def process_one(args):
        idx, item = args
        try:
            data     = generate_content(client, item["prompt"])
            html     = render_html(item, data)
            page_dir = DOCS_DIR / "p" / item["slug"]
            page_dir.mkdir(parents=True, exist_ok=True)
            (page_dir / "index.html").write_text(html, encoding="utf-8")
            generate_og_image(item["title"], item["category"], page_dir / "og.png")
            url = f"{SITE_BASE}/p/{item['slug']}/"
            with lock:
                save_done(item["title"])
                save_url(url)
                done.add(item["title"])
            print(f"  ✅ [{idx}/{len(this_batch)}] {url}")
            return True
        except Exception as e:
            print(f"  ❌ [{idx}/{len(this_batch)}] {item['title']}：{e}")
            return False

    from concurrent.futures import ThreadPoolExecutor, as_completed
    WORKERS = int(os.environ.get("WORKERS", "10"))
    print(f"🚀 並發數：{WORKERS}")

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(process_one, (i+1, item)): item
                   for i, item in enumerate(this_batch)}
        for future in as_completed(futures):
            if future.result():
                success_count += 1

    # 更新 sitemap、robots、首頁
    all_slugs = [it["slug"] for it in corpus if it["title"] in done]
    generate_sitemap(all_slugs)
    generate_robots()
    generate_index(corpus, done)

    print(f"\n本批次：✅ {success_count} 頁  |  累計：{len(done)} / {len(corpus)} 頁")


if __name__ == "__main__":
    main()
