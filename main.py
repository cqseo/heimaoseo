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
    """
    精準長尾詞庫 — 1,026 頁
    策略：具體場景 × 具體行為 × 具體情緒，模擬真實用戶搜尋字串
    競爭力：避開 TVBS / bella.tw / Dcard 佔領的廣泛詞，
           鎖定低競爭、高購買意圖的細節型查詢
    """
    corpus = []

    # ── A. 月老靈籤 — 100 籤 × 4 具體問題 = 400 頁 ──────────────────────────
    # 真實用戶搜法：「月老靈籤第X籤 + 【具體場景/行為/結果】」
    yuelao_variants = [
        # (標題後綴, slug後綴, 核心關鍵字, meta描述片段, 提示詞重點)
        (
            "分手後他會回來嗎", "breakup-return",
            "分手後復合,月老靈籤解籤,感情挽回",
            "抽到這籤問分手後他會不會回來，月老給你真實答案",
            "分手後對方是否會主動回來，籤意如何判斷時間點，哪些跡象代表有望復合"
        ),
        (
            "曖昧對象已讀不回怎麼辦", "aimei-ignore",
            "已讀不回,曖昧期,月老靈籤感情",
            "曖昧中他已讀不回，月老靈籤第{n}籤告訴你該怎麼做",
            "曖昧對象突然已讀不回三天，籤意暗示你主動還是等待，如何判斷對方真實心意"
        ),
        (
            "單身多久了問什麼時候脫單", "single-when",
            "何時脫單,單身求緣,月老靈籤",
            "單身很久了問月老第{n}籤，感情何時會有進展",
            "久單族抽到這籤問脫單時機，籤意如何看待緣分出現的信號，要主動還是順其自然"
        ),
        (
            "喜歡的人說只想當朋友還有救嗎", "friendzone-rescue",
            "朋友圈,友達以上,月老靈籤感情逆境",
            "被放進友達圈抽月老第{n}籤，還有機會嗎",
            "喜歡的人說只想當朋友，抽到這籤代表什麼，籤意如何指引從朋友變戀人的可能性"
        ),
    ]
    for n in range(1, 101):
        for suffix, slug_sfx, kws, desc_tpl, prompt_focus in yuelao_variants:
            title = f"月老靈籤第{n}籤｜{suffix}"
            slug  = f"yuelao-{n}-{slug_sfx}"
            desc  = desc_tpl.replace("{n}", str(n))
            corpus.append({
                "title": title, "slug": slug,
                "utm": "yuelao", "category": "月老靈籤",
                "keywords": f"月老靈籤第{n}籤,{kws},感情占卜",
                "desc": desc,
                "prompt": (
                    f"請用道地台灣繁體中文，以「月老靈籤第{n}籤」為主題，"
                    f"針對用戶的具體困擾「{suffix}」寫一篇1000字以上的感情諮詢文章。\n"
                    f"重點聚焦：{prompt_focus}\n"
                    f"格式要求：\n"
                    f"1. para1（400字以上）：深入解析籤詩意涵，結合第{n}籤的象徵意義，"
                    f"針對「{suffix}」這個具體情境給出籤意詮釋\n"
                    f"2. para2（400字以上）：給出3-5個具體可執行的行動建議，"
                    f"包含時機判斷與心態調整\n"
                    f"3. faq：3組常見問答（Q約25字、A約100字）\n"
                    f"4. tips：3條實用提醒（每條30字內）\n"
                    f"語氣親切口語化，符合台灣用語習慣。\n"
                    f"JSON：{{\"para1\":\"...\",\"para2\":\"...\","
                    f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}],"
                    f"\"tips\":[\"...\",\"...\",\"...\"]}}"
                ),
            })

    # ── B. 12 星座 × 男生/女生 × 13 具體行為場景 = 312 頁 ─────────────────────
    # 真實用戶搜法：「[星座]男生/女生 + [具體行為] + [想問的結果]」
    zodiacs = ["牡羊座","金牛座","雙子座","巨蟹座","獅子座","處女座",
               "天秤座","天蠍座","射手座","摩羯座","水瓶座","雙魚座"]
    zodiac_en = ["aries","taurus","gemini","cancer","leo","virgo",
                 "libra","scorpio","sagittarius","capricorn","aquarius","pisces"]
    genders = [("男生","male"), ("女生","female")]

    # 具體行為場景（低競爭長尾，媒體不會寫的細節場景）
    behavior_scenes = [
        # (標題場景, slug關鍵字, 搜尋關鍵字, meta描述, 提示詞聚焦點)
        (
            "說需要時間冷靜是什麼意思", "need-time",
            "說需要時間,冷靜期,是否分手",
            "{zi}{g}說需要時間冷靜，到底是想分手還是真的需要空間",
            "分析這句話的真實含義，冷靜期多久算正常，你該主動還是等待"
        ),
        (
            "已讀不回三天還有機會嗎", "read-no-reply-3days",
            "已讀不回,三天,還有機會",
            "{zi}{g}已讀不回三天，現在還能挽回嗎",
            "三天已讀不回的可能原因，主動傳什麼訊息比較好，冷處理還是直接問"
        ),
        (
            "主動傳訊息都是我先怎麼辦", "always-first-text",
            "我先傳訊息,主動追,感情不對等",
            "每次都是我先傳訊息，{zi}{g}到底有沒有喜歡我",
            "分析這個星座在喜歡的人面前的互動習慣，不主動傳訊息是否代表不在意"
        ),
        (
            "曖昧一個月突然冷淡是怎麼了", "aimei-cold",
            "突然冷淡,曖昧,熱情下降",
            "曖昧一個月的{zi}{g}突然變得很冷淡，發生什麼事了",
            "分析這個星座曖昧期突然冷淡的常見原因，是移情別戀還是只是忙"
        ),
        (
            "說分手但還是會找我是什麼意思", "breakup-still-contact",
            "說分手還找我,藕斷絲連,前任聯絡",
            "{zi}{g}說要分手但還是一直找我，他到底想要什麼",
            "這個星座說分手卻還藕斷絲連的心理，代表還有感情還是只是習慣"
        ),
        (
            "交往半年開始不積極了怎麼挽回", "6months-less-effort",
            "交往半年,熱情下降,如何挽回",
            "和{zi}{g}交往半年後他明顯不積極了，感情是不是出問題了",
            "這個星座交往進入穩定期後的相處模式，熱情下降是正常還是感情轉淡"
        ),
        (
            "喜歡我還是把我當備胎怎麼看出來", "backup-or-like",
            "備胎,是否喜歡,判斷心意",
            "怎麼判斷{zi}{g}是真的喜歡我還是把我當備胎",
            "從這個星座的具體行為分辨真心喜歡和當備胎的差異，5個觀察重點"
        ),
        (
            "分手後還傳訊息是想復合嗎", "exback-text",
            "分手後傳訊息,前任,想復合",
            "{zi}{g}分手後還一直傳訊息給我，他是想復合還是放不下",
            "分析這個星座分手後傳訊息的可能動機，哪些內容代表想復合，哪些只是不捨"
        ),
        (
            "生氣後不回訊息要怎麼哄", "angry-no-reply",
            "生氣不回訊息,哄對方,冷戰處理",
            "{zi}{g}生氣後一個訊息都不回，要怎麼道歉才有效",
            "這個星座生氣後的反應模式，冷戰時最需要的是什麼，哪種道歉方式最有效"
        ),
        (
            "只約吃飯不約其他代表什麼", "only-dinner-date",
            "只約吃飯,關係曖昧,進展停滯",
            "和{zi}{g}出去只約吃飯，從不約其他活動，這段關係到底算什麼",
            "分析這個星座在曖昧期的約會習慣，只約吃飯是喜歡你還是只把你當朋友"
        ),
        (
            "說忙但還是會回訊息到底怎麼想", "busy-but-reply",
            "說忙還是回訊,感情判斷,在乎",
            "{zi}{g}說最近很忙，但還是會回我訊息，他有在意我嗎",
            "這個星座真忙和找藉口的差別，說忙還是回訊息代表的真實心意"
        ),
        (
            "交往前就提分手是認真的嗎", "almost-breakup",
            "交往前分手,感情不穩定,是否繼續",
            "還在曖昧期的{zi}{g}就說要分手，這段感情還要繼續嗎",
            "還沒正式交往就提分手的心理，這個星座的感情模式，要繼續還是放手"
        ),
        (
            "問他喜不喜歡我他說不知道是什麼意思", "dontknow-feelings",
            "說不知道,感情表態,模糊態度",
            "問{zi}{g}喜不喜歡我，他說不知道，到底算什麼意思",
            "這個星座在感情表態上說「不知道」的真實含義，是真的不確定還是在拖延"
        ),
    ]

    for zi, ze in zip(zodiacs, zodiac_en):
        for gname, gen in genders:
            for scene, slug_sfx, kws, desc_tpl, prompt_focus in behavior_scenes:
                title = f"{zi}{gname}｜{scene}"
                slug  = f"{ze}-{gen}-{slug_sfx}"
                desc  = desc_tpl.replace("{zi}", zi).replace("{g}", gname)
                corpus.append({
                    "title": title, "slug": slug,
                    "utm": "zodiac", "category": "星座感情",
                    "keywords": f"{zi},{gname},{kws}",
                    "desc": desc,
                    "prompt": (
                        f"請用道地台灣繁體中文，針對「{zi}{gname}」的具體感情行為「{scene}」，"
                        f"寫一篇1000字以上的深度分析文章。\n"
                        f"重點聚焦：{prompt_focus.replace('{zi}', zi).replace('{g}', gname)}\n"
                        f"格式：\n"
                        f"1. para1（400字以上）：深入分析{zi}星座在此行為背後的心理動機，"
                        f"結合星座特質給出有洞察力的解讀\n"
                        f"2. para2（400字以上）：給出3-5個具體可操作的應對建議，"
                        f"包含實際可用的話術和行動步驟\n"
                        f"3. faq：3組最常被問的問題（Q約25字、A約100字）\n"
                        f"4. tips：3條立即可用的實用提醒\n"
                        f"語氣溫暖口語化，符合台灣網路文風，像閨蜜分析給你聽。\n"
                        f"JSON：{{\"para1\":\"...\",\"para2\":\"...\","
                        f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}],"
                        f"\"tips\":[\"...\",\"...\",\"...\"]}}"
                    ),
                })

    # ── C. 22 塔羅大牌 × 正逆位 × 具體人生問題 = 132 頁 ─────────────────────
    # 真實搜法：「[塔羅牌名] [正/逆位] [具體問題]」
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
    tarot_questions = [
        # (問題標題, slug關鍵, keywords, meta描述, 提示詞聚焦)
        (
            "感情代表他現在對我的心意", "love-feelings",
            "感情塔羅,對方心意,塔羅占卜",
            "抽到這張牌問感情，代表對方現在怎麼看你",
            "這張牌在感情牌陣中代表對方當下的心意，正逆位的差別，以及你下一步該怎麼做"
        ),
        (
            "問復合這張牌是好是壞", "reunion-sign",
            "復合塔羅,分手後,塔羅解讀",
            "問復合抽到這張牌，代表有希望還是放手",
            "這張牌在復合問題上的具體涵義，什麼行動會有助於復合，什麼會阻礙"
        ),
        (
            "徹底結束了還是還有機會", "end-or-chance",
            "塔羅感情結束,還有機會,感情判斷",
            "抽到這張牌問感情是否徹底結束，塔羅怎麼說",
            "這張牌是否代表感情的終結，如何判斷「結束」和「轉機」的細微差別"
        ),
    ]
    for cname, cen in tarot_cards:
        for pname, pen in positions:
            for qtitle, qslug, kws, desc_tpl, prompt_focus in tarot_questions:
                title = f"塔羅{cname}{pname}｜{qtitle}"
                slug  = f"tarot-{cen}-{pen}-{qslug}"
                corpus.append({
                    "title": title, "slug": slug,
                    "utm": "tarot_card", "category": "塔羅占卜",
                    "keywords": f"塔羅,{cname},{pname},{kws}",
                    "desc": desc_tpl,
                    "prompt": (
                        f"請用道地台灣繁體中文，解析塔羅牌「{cname}（{pname}）」"
                        f"針對問題「{qtitle}」的完整涵義，字數1000字以上。\n"
                        f"重點聚焦：{prompt_focus}\n"
                        f"格式：\n"
                        f"1. para1（400字以上）：解析「{cname}{pname}」的核心象徵，"
                        f"結合這個具體問題給出直白的牌義詮釋\n"
                        f"2. para2（400字以上）：給出具體的行動建議和注意事項，"
                        f"讓提問者知道接下來怎麼做\n"
                        f"3. faq：3組常見追問（Q約25字、A約100字）\n"
                        f"4. tips：3條塔羅解讀小提示\n"
                        f"語氣親切直接，像在幫朋友解牌。\n"
                        f"JSON：{{\"para1\":\"...\",\"para2\":\"...\","
                        f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}],"
                        f"\"tips\":[\"...\",\"...\",\"...\"]}}"
                    ),
                })

    # ── D. 廟宇求籤 — 10 廟 × 8 具體步驟/疑問 = 80 頁 ─────────────────────
    # 真實搜法：「[廟宇名] + [具體做法/注意事項/靈驗問題]」
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
    ]
    temple_questions = [
        # (問題, slug, keywords, meta描述, 提示詞聚焦)
        (
            "求月老紅線步驟與禁忌完整攻略", "red-thread-guide",
            "月老紅線,求姻緣步驟,廟宇攻略",
            "求月老紅線正確步驟，哪些禁忌一定要避開",
            "詳述求月老紅線的完整流程，包含拜拜時間、供品、心誠則靈的具體做法，以及最常見的禁忌誤區"
        ),
        (
            "求感情簽第幾號最靈驗", "best-love-sign",
            "感情籤,最靈驗,哪號籤",
            "問感情要抽哪號籤，哪些籤代表感情順遂",
            "說明這間廟在感情籤上的特色，哪幾號籤感情運最旺，解籤的正確方式"
        ),
        (
            "第一次去拜拜流程不懂怎麼辦", "first-visit-guide",
            "第一次拜拜,流程,新手攻略",
            "第一次去這間廟不知道流程？完整新手攻略",
            "給第一次去的人完整的參拜流程，包含購香、繞境順序、還願方式，以及常見錯誤"
        ),
        (
            "還願要怎麼做才正確", "fulfill-vow",
            "還願,如何還願,廟宇還願",
            "許願後感情順利了，要怎麼回廟還願才正確",
            "說明還願的正確時機、流程和供品選擇，以及沒有及時還願會怎樣"
        ),
        (
            "外縣市去要注意什麼和怎麼規劃", "travel-worship-plan",
            "外縣市拜拜,交通攻略,旅遊規劃",
            "從外縣市專程來這間廟拜拜，交通和注意事項全攻略",
            "詳述交通方式、停車、最佳參拜時間、附近可以一起去的景點，以及省時省力的規劃建議"
        ),
        (
            "問感情能帶男女朋友一起去嗎", "bring-partner",
            "帶男女朋友拜拜,感情廟宇,注意事項",
            "去求姻緣可以帶交往對象一起去嗎？有什麼禁忌",
            "說明帶伴侶一起去求感情廟宇的注意事項和民間說法，以及什麼情況不適合一起去"
        ),
        (
            "求完籤之後多久會有感應", "when-response",
            "求籤感應,靈驗時間,多久有效",
            "求完月老或感情籤之後，大概多久會有感應或變化",
            "從信徒經驗分享說明感應的時間範圍，以及在等待期間應該配合哪些自我提升行動"
        ),
        (
            "失戀後去拜拜有用嗎", "after-breakup-pray",
            "失戀拜拜,感情修復,心靈療癒",
            "失戀後去求月老有用嗎？什麼心態去拜效果最好",
            "從身心靈角度說明失戀後去廟宇求籤的意義，以及以什麼樣的心態許願效果更好"
        ),
    ]
    for tname, ten, tcity in temples:
        for qtitle, qslug, kws, desc_tpl, prompt_focus in temple_questions:
            title = f"{tname}｜{qtitle}"
            slug  = f"{ten}-{qslug}"
            corpus.append({
                "title": title, "slug": slug,
                "utm": "temple", "category": "廟宇祈福",
                "keywords": f"{tname},{tcity},{kws}",
                "desc": desc_tpl,
                "prompt": (
                    f"請用道地台灣繁體中文，針對「{tname}」（位於{tcity}）的問題「{qtitle}」，"
                    f"寫一篇1000字以上的完整解答文章。\n"
                    f"重點聚焦：{prompt_focus}\n"
                    f"格式：\n"
                    f"1. para1（400字以上）：介紹{tname}的特色和神明職司，"
                    f"針對這個具體問題給出詳細說明\n"
                    f"2. para2（400字以上）：給出具體步驟和實用建議，"
                    f"讓讀者看完之後知道怎麼做\n"
                    f"3. faq：3組最常見疑問（Q約25字、A約100字）\n"
                    f"4. tips：3條溫馨提醒\n"
                    f"語氣親切，像地方人介紹給外地朋友聽。\n"
                    f"JSON：{{\"para1\":\"...\",\"para2\":\"...\","
                    f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}],"
                    f"\"tips\":[\"...\",\"...\",\"...\"]}}"
                ),
            })

    # ── E. 感情占卜情境題 — 純場景長尾詞 102 頁 ───────────────────────────
    # 真實搜法：「[具體情境] 感情占卜/怎麼辦/代表什麼」
    # 完全不依附星座，鎖定情境本身的流量
    longtail_pages = [
        # 月老籤詩 × 具體人生困境（20頁）
        ("月老靈籤問感情要怎麼許願才有效","yuelao-how-to-pray","月老許願,感情許願,月老求法","許願前先了解月老靈籤的正確許願方式，讓你的祈求更清晰有效"),
        ("抽到上上籤感情還是沒有進展是怎麼回事","upper-sign-no-progress","上上籤,感情沒進展,解籤疑惑","抽到最好的籤感情卻沒動靜，可能是這幾個原因"),
        ("月老靈籤抽到下下籤感情真的沒救了嗎","lower-sign-hope","下下籤,感情挽回,籤意解釋","抽到下下籤不代表感情結束，真正的意思是這樣"),
        ("問復合抽到中籤是好還是壞","mid-sign-reunion","中籤解讀,問復合,感情占卜","抽到中等的籤問復合，月老到底在告訴你什麼"),
        ("月老說感情有阻礙是指什麼阻礙","love-obstacles","感情阻礙,月老解籤,障礙化解","籤詩說感情有阻礙，常見的3種阻礙和解決方向"),
        ("同一個問題一直抽到同一張籤代表什麼","same-sign-repeat","重複抽籤,月老訊息,感情指引","一直抽到同一張籤是月老在強調什麼重要訊息"),
        ("感情籤詩說要等待要等多久","waiting-period","等待時機,感情籤詩,時間判斷","籤詩說等待，到底是等幾天、幾週還是幾個月"),
        ("問喜歡的人抽到代表相思的籤是什麼意思","lovesick-sign","相思籤,暗戀占卜,感情解籤","抽到相思類的月老籤，代表對方也在想你嗎"),
        ("月老籤詩說要主動但我不知道怎麼主動","how-to-initiate","主動追求,感情主動,具體做法","籤詩叫你主動，這裡有3個具體行動方案"),
        ("問姻緣籤詩說緣分已到是真的嗎","fate-arrived","緣分到來,正緣,姻緣占卜","籤詩說緣分已到，這代表什麼，你要做什麼配合"),
        # 塔羅 × 具體人生困境（20頁）
        ("塔羅問他有沒有在想我怎麼解讀","tarot-he-thinking","塔羅占卜,對方想法,感情塔羅","用塔羅問對方有沒有在想你，這幾張牌代表「有」"),
        ("塔羅問我們感情的未來出現死神牌是完了嗎","tarot-death-future","死神牌,感情未來,塔羅恐懼","塔羅出現死神牌問感情，不是你想的那個意思"),
        ("塔羅問復合出現高塔牌代表什麼","tarot-tower-reunion","高塔牌,復合塔羅,衝突牌","問復合塔羅出現高塔，可能代表這幾種情況"),
        ("塔羅問他喜歡我嗎出現戀人牌是好事嗎","tarot-lovers-like","戀人牌,塔羅喜歡,感情確認","問喜歡嗎出現戀人牌，意思比你想的更複雜"),
        ("塔羅自己占卜結果可信嗎","tarot-self-read-accurate","自占塔羅,準確度,塔羅可信度","自己幫自己占塔羅準不準，這是影響準確度的關鍵"),
        ("塔羅問同一個問題一直出現逆位是怎麼回事","tarot-reversed-repeat","逆位,重複牌,塔羅訊息","每次問同一件事都出現逆位，塔羅可能在告訴你這件事"),
        ("塔羅問感情位置一直出現寶劍牌組是什麼意思","tarot-swords-love","寶劍牌組,感情衝突,塔羅解讀","感情牌陣出現大量寶劍，不一定是壞事，看怎麼解讀"),
        ("初學者用塔羅問感情最容易犯的錯誤","tarot-beginner-mistakes","塔羅新手,感情占卜,常見錯誤","塔羅新手問感情最容易犯的5個錯誤，你中了幾個"),
        ("塔羅問這段感情值不值得繼續","tarot-worth-continuing","感情值得,塔羅判斷,是否繼續","用塔羅判斷一段感情要不要繼續，這幾個牌位最關鍵"),
        ("塔羅逆位一定是壞的意思嗎","tarot-reversed-meaning","逆位含義,塔羅基礎,正逆位差別","塔羅逆位不是你想的壞事，真正的涵義是這樣"),
        # 感情行為分析（無星座）（30頁）
        ("喜歡的人突然變得很冷淡是發生什麼事了","suddenly-cold","突然冷淡,感情變化,原因分析","喜歡的人突然冷淡，可能是這5個原因，對應建議"),
        ("傳訊息秒回但約出來一直推說不行代表什麼","reply-fast-refuse-date","秒回不約,感情訊號,行為解讀","秒回訊息卻不願意約出來，他在想什麼"),
        ("男生說很忙但還是會傳訊息是在意嗎","busy-man-text","男生說忙,傳訊息,是否在意","男生說忙還是傳訊息，這樣算喜歡你嗎"),
        ("異地戀突然不回訊息三天怎麼辦","long-distance-no-reply","異地戀,不回訊息,感情危機","異地戀三天不回訊，先別慌，做這幾件事"),
        ("曖昧一個月他說我們當朋友就好怎麼辦","friendzone-after-aimei","朋友就好,曖昧後被拒,感情挫折","曖昧後被放朋友圈，還有逆轉的機會嗎"),
        ("主動追了一個月對方沒什麼反應要放棄嗎","1month-chase-no-response","追了一個月,沒反應,是否放棄","追一個月對方沒明顯回應，繼續還是放手的判斷依據"),
        ("他說現在不想談感情是在拒絕我嗎","dont-want-relationship","不想談感情,被拒絕,感情判斷","他說不想談感情，是拒絕你還是真的時機未到"),
        ("分手後他主動傳訊息說想你是認真的嗎","ex-says-miss-you","前任說想你,分手後聯絡,復合可能","前任說想你，可能的真實動機和你應該怎麼回應"),
        ("喜歡一個人要怎麼看出他有沒有喜歡你","how-to-know-if-likes","判斷喜歡,感情訊號,告白前確認","告白前先確認這5個訊號，他喜歡你的可能性有多高"),
        ("感情問題一直用占卜決定是不是不健康","relying-on-divination","過度占卜,感情依賴,心理健康","一直用占卜決定感情是否正常？什麼程度算過度依賴"),
        # 生肖運勢 × 具體場景（32頁）
        ("屬虎人2027年感情運最旺是哪個月","tiger-love-peak-2027","屬虎,2027感情,桃花月","屬虎的人2027年感情最旺的月份和要注意的時間點"),
        ("屬鼠人2027年適合告白嗎時機怎麼看","rat-confess-2027","屬鼠,告白時機,2027","屬鼠的人2027年最適合告白的月份，失敗率最低的時間"),
        ("屬龍人2027年分手後能復合嗎","dragon-reunion-2027","屬龍,分手復合,2027運勢","2027年屬龍的人問復合，這年的感情氣場怎麼看"),
        ("屬馬人2027年單身能脫單嗎","horse-single-2027","屬馬,脫單,2027桃花","屬馬的人2027年桃花運分析，哪段時間最容易遇到正緣"),
        ("屬牛人2027年感情遇到阻礙怎麼化解","ox-love-obstacle-2027","屬牛,感情阻礙,2027化解","2027年屬牛感情運波動，這幾個月要特別注意"),
        ("屬羊人2027年異地戀能維持嗎","goat-longdistance-2027","屬羊,異地戀,2027感情","2027年屬羊的人問異地戀，運勢是否支持繼續"),
        ("屬猴人2027年桃花多但感情穩定嗎","monkey-peachblossom-2027","屬猴,桃花多,2027感情穩定","2027屬猴桃花旺但感情是否穩定，怎麼把握好的桃花"),
        ("屬豬人2027年適合結婚嗎","pig-marry-2027","屬豬,結婚,2027感情","2027年屬豬的人問結婚，這年的感情運支持長期承諾嗎"),
        ("屬雞人2027年感情冷淡期如何激活","rooster-cold-period-2027","屬雞,感情冷淡,2027激活","屬雞的人2027年感情進入瓶頸期，這樣做能重新點燃"),
        ("屬蛇人2027年遇到舊情人是緣是劫","snake-ex-2027","屬蛇,舊情人,2027感情","2027年屬蛇遇到前任，這是重續緣分還是考驗"),
        ("屬兔人2027年暗戀能表白成功嗎","rabbit-secret-love-2027","屬兔,暗戀,2027表白","屬兔的人2027年暗戀能成真嗎，哪個月表白成功率最高"),
        ("屬狗人2027年感情是大破大立的一年嗎","dog-love-change-2027","屬狗,感情變化,2027大運","2027年屬狗感情是否有大變動，要怎麼因應"),
        ("水瓶座女生和天蠍座男生在一起合適嗎","aquarius-scorpio-compatibility","水瓶座,天蠍座,星座配對","水瓶女+天蠍男的配對分析，優勢與挑戰完整解析"),
        ("雙魚座女生和射手座男生能走到最後嗎","pisces-sagittarius-compatibility","雙魚座,射手座,星座配對","雙魚女+射手男看起來不合，但其實有這個優勢"),
        ("巨蟹座和摩羯座真的是天生一對嗎","cancer-capricorn-compatibility","巨蟹座,摩羯座,對立星座","巨蟹和摩羯相對星座，吸引力從何而來，衝突怎麼化解"),
        ("獅子座女生配什麼星座最適合", "leo-female-best-match","獅子座女生,星座配對,最配星座","獅子座女生最適合哪個星座，從個性互補角度完整分析"),
        ("處女座配對哪個星座最不合", "virgo-worst-match","處女座,星座不合,感情地雷","處女座最難相處的星座配對，以及衝突的核心原因"),
        ("上升星座影響感情的程度比太陽星座大嗎","rising-sign-love","上升星座,太陽星座,感情影響","上升星座和太陽星座哪個對感情影響更大，怎麼一起看"),
        ("看月亮星座還是太陽星座來判斷感情","moon-vs-sun-sign-love","月亮星座,感情,星盤","判斷感情合不合要看月亮星座還是太陽星座"),
        ("星座配對不合還是在一起幸福的案例","incompatible-but-happy","星座不合,幸福案例,感情突破","星座「不合」卻幸福的情侶，他們是怎麼做到的"),
        # 額外場景補足（51頁）
        ("告白被拒後還能當朋友嗎還是直接斷聯","after-rejection-friend","告白被拒,是否當朋友,斷聯","告白失敗後繼續當朋友還是斷聯，哪個對自己比較好"),
        ("喜歡一個人多久才算適合表白","when-to-confess","表白時機,喜歡多久,告白準備","喜歡一個人多久才算適合告白，這幾個條件達到才說"),
        ("對方突然說要給彼此空間是什麼意思","give-space-meaning","給彼此空間,感情降溫,是否分手","他說要給彼此空間，是要分手還是真的需要喘息"),
        ("男生不主動但又不拒絕你是在想什麼","passive-not-refuse","不主動不拒絕,模糊態度,感情判斷","男生對你不冷不熱，不主動但又不拒絕，他到底什麼心態"),
        ("在一起一年了感覺越來越像朋友怎麼辦","1year-like-friends","熱情消退,感情瓶頸,重燃愛意","交往一年感覺像朋友，這是正常現象還是感情快沒了"),
        ("他傳訊息都很簡短是不在意我嗎","short-replies-meaning","短回覆,是否在意,感情判斷","回覆很短是不在意還是他本來就這樣，這樣判斷"),
        ("復合後他又開始變冷是怎麼了","reunion-then-cold","復合後變冷,感情反覆,再次危機","好不容易復合了他又冷淡，是試探你還是真的後悔復合"),
        ("異地戀多久要見一次面才能維持感情","long-distance-frequency","異地戀見面,多久見面,感情維持","異地戀要多久見一次面才夠，見面頻率對感情的影響"),
        ("男生第一次約會後沒有主動傳訊息是沒興趣嗎","first-date-no-text","第一次約會,沒主動聯絡,是否喜歡","第一次約會後他沒傳訊息，是沒興趣還是在等你先動"),
        ("她說我們不合適是在拒絕我嗎還是在試探","not-suitable-meaning","不合適,是否拒絕,感情試探","被說不合適，這真的是拒絕還是另有含義"),
        ("在一起很久了他沒有求婚的意思怎麼辦","no-proposal-plan","求婚,長期交往,感情下一步","交往幾年了他沒有求婚計劃，要催還是等，怎麼溝通"),
        ("告白前要怎麼確認對方對你的感覺","pre-confession-check","告白前確認,感情訊號,告白成功率","告白前這幾個訊號可以幫你判斷對方的感覺"),
        ("前任突然說想見你是什麼動機","ex-wants-to-meet","前任見面,動機判斷,復合可能","前任突然說想見你，可能的原因和你該如何應對"),
        ("怎麼知道自己是喜歡他還是習慣他","like-or-habit","喜歡還是習慣,感情判斷,自我覺察","到底是喜歡這個人還是只是習慣有他，這樣區分"),
        ("感情中覺得自己付出比較多要怎麼辦","imbalanced-effort","付出不對等,感情失衡,溝通建議","感覺自己付出比較多，是你想太多還是感情真的不對等"),
        ("男生送禮物但不表白是什麼意思","gift-no-confession","送禮物,不表白,感情訊號","他送你禮物但一直不說喜歡你，他到底在等什麼"),
        ("失戀後多久才算適合重新開始感情","after-breakup-new-love","失戀多久,重新開始,心理準備","失戀後多久算適合再談感情，這幾個跡象代表你準備好了"),
        ("如何讓一段停滯的感情有進展","stagnant-relationship","感情停滯,推進感情,關係進展","曖昧很久感情沒有進展，可以這樣讓關係往前走"),
        ("他說喜歡你但又說現在不想談感情怎麼辦","like-but-no-relationship","喜歡但不談感情,模糊關係,等待","他說喜歡你卻不想交往，這樣值得等嗎"),
        ("感情裡一直是付出的那個人怎麼調整心態","always-giving","感情付出,調整心態,自我保護","在感情裡一直是付出的角色，怎麼保護自己不受傷"),
        ("不擅長表達感情的人怎麼判斷他喜不喜歡你","bad-at-expressing","不善表達,感情判斷,內斂性格","他不擅長說喜歡，但這些行為可以看出他的真心"),
        ("兩個人都不主動推進感情要怎麼辦","both-passive","雙方都不主動,感情進退,打破僵局","兩個人都等對方先動，這種僵局要怎麼打破"),
        ("曖昧期說太喜歡你了會嚇跑對方嗎","express-too-much","說太喜歡,嚇跑對方,感情節奏","曖昧期太早表達喜歡會嚇跑對方嗎，怎麼拿捏"),
        ("感情占卜用哪種方式最準","best-divination-method","感情占卜方式,哪種準,占卜比較","月老籤、塔羅、星座、生肖，哪種感情占卜最準"),
        ("占卜感情結果不好可以重新占嗎","redivine-bad-result","重新占卜,感情結果不好,占卜心態","占卜結果不好，可以再占一次嗎，正確的占卜心態"),
        ("感情占卜對於決策真的有幫助嗎","divination-decision-making","占卜決策,感情選擇,心理角度","用占卜做感情決策科學嗎，心理學怎麼看這件事"),
        ("為什麼感情占卜有時候很準有時候不準","divination-accuracy","占卜準確度,為何不準,影響因素","占卜感情有時準有時不準，這幾個因素影響結果"),
        ("同時喜歡兩個人怎麼辦用占卜能決定嗎","like-two-people","喜歡兩個人,感情選擇,占卜決定","同時有感覺的兩個人，占卜能幫你選擇嗎"),
        ("失戀後一直想聯絡前任要怎麼忍住","post-breakup-no-contact","失戀,不聯絡前任,斷聯30天","失戀後一直想傳訊息給前任，這樣忍住的3個方法"),
        ("怎麼知道已經走出失戀了","healed-from-breakup","走出失戀,心理復原,感情癒合","這5個跡象告訴你已經真正走出上段感情了"),
        ("和前任保持朋友關係是正確的嗎","ex-as-friends","前任朋友,分手後關係,是否斷聯","和前任保持朋友，對雙方都好還是阻礙新感情"),
        ("剛分手馬上交新戀情是逃避還是走出來了","rebound-relationship","閃回,速食感情,是否走出","分手後很快進入新感情，是真的喜歡還是在逃避傷痛"),
        ("感情裡的安全感要靠自己還是靠對方給","security-in-love","安全感,感情依賴,自我建立","感情裡的安全感要自己建立還是等對方給，正確做法"),
        ("在乎的人卻一直讓你感到焦慮正常嗎","love-anxiety","感情焦慮,在乎才焦慮,心理分析","越在乎越焦慮，這是感情的問題還是自己的問題"),
        ("如何讓自己在感情裡不那麼患得患失","less-anxious-love","患得患失,感情焦慮,心態調整","感情裡太患得患失讓你很累，這樣調整心態"),
        ("對感情死心了要怎麼確認自己是真的放棄了","give-up-love","死心,確認放棄,感情結束","想放棄一段感情，這幾個標準幫你確認是真的死心了"),
        ("告白成功後關係反而變奇怪要怎麼辦","after-confession-awkward","告白成功後尷尬,關係轉變,交往初期","終於告白成功了感覺卻變得很奇怪，這很正常，這樣處理"),
        ("喜歡的人和別人很好但對我很普通是什麼意思","special-to-others","對別人好,對我普通,感情訊號","他對別人熱情對你普通，這是不喜歡你還是另有原因"),
        ("為什麼每次感情都是自己受傷先放手","always-hurt-first","感情模式,重複受傷,自我覺察","每次感情都是自己先受傷，這個情感模式從哪裡來"),
        ("怎麼在感情裡保有自我不完全失去自己","keep-yourself-in-love","感情自我,獨立性,愛情平衡","愛一個人愛到失去自我，怎麼在感情裡保有自己"),
        ("感情裡的嫉妒心要怎麼控制不影響關係","jealousy-control","嫉妒心,感情嫉妒,控制情緒","感情裡的嫉妒心正常嗎，太強烈的嫉妒要怎麼調整"),
        ("兩個人在一起很自然但沒有心動感要繼續嗎","comfortable-not-excited","相處自然無心動,感情判斷,是否繼續","相處很舒服但沒有心跳感，這段感情要繼續嗎"),
        ("如何判斷自己是否真的愛上一個人了","know-if-love","愛的感覺,判斷真愛,感情確認","你真的愛上他了嗎，這幾個感受可以告訴你答案"),
        ("表白被拒後多久可以再試一次","try-again-after-rejection","被拒後再試,時機判斷,告白再次","告白失敗後多久可以再表白，哪些條件改變了才有機會"),
        ("感情裡的承諾是否有必要說出口","verbal-commitment","感情承諾,說出口,表達愛意","承諾一定要說出口嗎，行動和言語哪個在感情裡更重要"),
        ("怎麼在不催婚的情況下讓男友考慮婚姻","marriage-without-pressure","催婚,結婚計劃,感情進展","不想催婚但又想讓對方考慮結婚，這幾種溝通方式有效"),
        ("感情中冷戰最長多久算正常","cold-war-duration","冷戰,多久算正常,和好方法","感情裡冷戰最長幾天算正常，超過這個時間要主動化解"),
        ("為什麼越喜歡一個人越不敢在他面前表現自己","shy-with-crush","越喜歡越不自然,暗戀行為,心理解析","越喜歡他越在他面前表現失常，這是正常的嗎，怎麼改善"),
        ("如何知道一段感情是否值得繼續努力","worth-continuing-efforts","感情值得,繼續還是放手,判斷依據","到底要繼續努力還是放手，這幾個問題幫你做決定"),
        ("愛一個人愛得很累要怎麼辦","love-exhausted","愛得很累,感情疲憊,是否繼續","感情讓你很疲憊，是因為不對的人還是不對的方式"),
        ("怎麼判斷一段感情是命中注定還是自己一廂情願","fate-or-one-sided","命中注定,一廂情願,感情判斷","感覺和他有緣分，但怎麼確認不是自己一廂情願"),
        ("感情裡的直覺準不準應該相信嗎","love-intuition","感情直覺,相信直覺,心理感受","感情裡的直覺告訴你不對勁，這個感覺要相信嗎"),
    ]
    for item in longtail_pages:
        if len(item) == 4:
            title, slug, kws, desc = item
        else:
            # 有些tuple可能格式不同，兜底處理
            title, slug, kws, desc = item[0], item[1], item[2], item[3] if len(item) > 3 else item[2]
        corpus.append({
            "title": title, "slug": f"lt-{slug}",
            "utm": "longtail", "category": "感情占卜",
            "keywords": kws,
            "desc": desc,
            "prompt": (
                f"請用道地台灣繁體中文，針對「{title}」這個主題，"
                f"寫一篇1000字以上的深度感情分析或占卜解答文章。\n"
                f"格式：\n"
                f"1. para1（400字以上）：直接回答標題問題，給出有洞察力的分析，"
                f"讓讀者一開始就能獲得有價值的資訊\n"
                f"2. para2（400字以上）：給出具體行動建議，讓讀者知道接下來怎麼做\n"
                f"3. faq：3組最常被問的延伸問題（Q約25字、A約100字）\n"
                f"4. tips：3條實用提醒\n"
                f"語氣親切自然，像在和朋友談心。\n"
                f"JSON：{{\"para1\":\"...\",\"para2\":\"...\","
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
