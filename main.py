#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量生成繁體中文 Telegraph 引流頁面
目標網站：https://yuexia.app/
"""

import os
import sys
import json
import time
import random
import requests
from openai import OpenAI

# ─────────────────────────────────────────────
# 環境變數配置
# ─────────────────────────────────────────────
OPENAI_API_KEY   = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL  = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
MODEL_NAME       = os.environ.get("MODEL_NAME", "deepseek-chat")
BATCH_SIZE       = int(os.environ.get("BATCH_SIZE", "200"))

DONE_FILE  = "done_titles.txt"
URLS_FILE  = "telegraph_urls.txt"
TARGET_URL = "https://yuexia.app/"

# ─────────────────────────────────────────────
# 1,026 頁詞庫矩陣生成
# ─────────────────────────────────────────────

def build_corpus() -> list[dict]:
    """
    返回所有任務條目，每條包含：
      title    – Telegraph 頁面標題（繁中）
      prompt   – 傳給 LLM 的指令
      utm      – utm_medium 參數值
    共 300 + 360 + 144 + 132 + 90 = 1,026 條
    """
    corpus = []

    # ── A. 月老靈籤 300 頁 ──────────────────────
    yuelao_points = [
        "感情復合解析",
        "單身求正緣指引",
        "曖昧暗戀白話解籤",
    ]
    for n in range(1, 101):
        for point in yuelao_points:
            title = f"月老靈籤第{n}籤｜{point}"
            prompt = (
                f"請用道地台灣繁體中文，以「月老靈籤第{n}籤」為主題，"
                f"針對「{point}」寫一篇感情諮詢文章。"
                f"格式：兩段各150~200字的正文（第一段點出籤意與情感意涵，"
                f"第二段給出具體行動建議），再附2組FAQ（Q＋A格式，"
                f"每組Q約20字、A約60字）。語氣親切、貼近台灣用語，"
                f"不要出現簡體字或大陸用語。"
                f"以JSON回傳：{{\"para1\":\"...\",\"para2\":\"...\","
                f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}]}}"
            )
            corpus.append({"title": title, "prompt": prompt, "utm": "yuelao"})

    # ── B. 12 星座 × 男女 × 15 痛點 = 360 頁 ──
    zodiacs = ["牡羊座","金牛座","雙子座","巨蟹座","獅子座","處女座",
               "天秤座","天蠍座","射手座","摩羯座","水瓶座","雙魚座"]
    genders = ["男生","女生"]
    love_points = [
        "他心裡還有我嗎",
        "我們會復合嗎",
        "冷戰中他在想什麼",
        "他為什麼突然消失",
        "怎麼讓他主動聯絡我",
        "他對我是認真的嗎",
        "我要怎麼挽回他",
        "分手後還有機會嗎",
        "他喜歡我還是把我當備胎",
        "曖昧期要怎麼確認關係",
        "他說需要時間是什麼意思",
        "異地戀還有未來嗎",
        "他劈腿後我該原諒嗎",
        "單身多久才能遇到正緣",
        "今年桃花運什麼時候來",
    ]
    for zodiac in zodiacs:
        for gender in genders:
            for point in love_points:
                title = f"{zodiac}{gender}｜{point}"
                prompt = (
                    f"請用道地台灣繁體中文，針對「{zodiac}」的「{gender}」，"
                    f"就感情困擾「{point}」寫一篇感情分析文。"
                    f"格式：兩段各150~200字正文（第一段分析星座特質與此困擾的關聯，"
                    f"第二段給出具體行動方案），再附2組FAQ。"
                    f"語氣溫暖、口語化，符合台灣網路文風。"
                    f"以JSON回傳：{{\"para1\":\"...\",\"para2\":\"...\","
                    f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}]}}"
                )
                corpus.append({"title": title, "prompt": prompt, "utm": "tarot"})

    # ── C. 12 生肖 × 2027 六大運勢 = 144 頁 ──
    # 規格要求是「12生肖與12星座 × 6」= 144，此處用12生肖×12=144
    animals = ["鼠","牛","虎","兔","龍","蛇","馬","羊","猴","雞","狗","豬"]
    fortunes = [
        "2027桃花運完整預測",
        "2027偏財運爆發攻略",
        "2027轉職換跑道時機",
        "2027貴人運何時出現",
        "2027流年大運總覽",
        "2027正緣出現徵兆",
    ]
    for animal in animals:
        for fortune in fortunes:
            title = f"{animal}年生｜{fortune}"
            prompt = (
                f"請用道地台灣繁體中文，以「{animal}年生」生肖為主角，"
                f"撰寫「{fortune}」運勢分析文。"
                f"格式：兩段各150~200字正文（第一段概述今年整體氣場，"
                f"第二段給出趨吉避凶具體建議），再附2組FAQ。"
                f"文風溫暖正向，貼近台灣命理節目口吻。"
                f"以JSON回傳：{{\"para1\":\"...\",\"para2\":\"...\","
                f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}]}}"
            )
            corpus.append({"title": title, "prompt": prompt, "utm": "fortune2027"})

    # ── D. 22 張塔羅大牌 × 正逆位 × 3 場景 = 132 頁 ──
    tarot_cards = [
        "愚者","魔術師","女祭司","皇后","皇帝","教皇","戀人","戰車",
        "力量","隱士","命運之輪","正義","吊人","死神","節制","惡魔",
        "高塔","星星","月亮","太陽","審判","世界",
    ]
    positions   = ["正位","逆位"]
    scenes      = ["感情復合占卜","對方真實想法","事業財運預測"]
    for card in tarot_cards:
        for pos in positions:
            for scene in scenes:
                title = f"塔羅｜{card}{pos}｜{scene}"
                prompt = (
                    f"請用道地台灣繁體中文，解析塔羅牌「{card}（{pos}）」"
                    f"在「{scene}」情境下的涵義。"
                    f"格式：兩段各150~200字正文（第一段解釋牌義核心，"
                    f"第二段針對此場景給出實際建議），再附2組FAQ。"
                    f"語氣專業又親切，適合台灣塔羅愛好者閱讀。"
                    f"以JSON回傳：{{\"para1\":\"...\",\"para2\":\"...\","
                    f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}]}}"
                )
                corpus.append({"title": title, "prompt": prompt, "utm": "tarot_card"})

    # ── E. 15 間港台廟宇 × 6 訴求 = 90 頁 ──
    temples = [
        "霞海城隍廟","龍山寺","黃大仙祠","紫南宮","鹿港天后宮",
        "行天宮","地藏庵","大甲鎮瀾宮","北港朝天宮","玄天上帝廟",
        "西門媽祖廟","車城福安宮","花蓮慶修院","香港文武廟","澳門媽閣廟",
    ]
    wishes = [
        "求姻緣祈福攻略",
        "問感情復合靈驗儀式",
        "求財運開運秘訣",
        "問工作轉機祈禱方式",
        "問健康平安祭祀禮儀",
        "求考試順利祈願流程",
    ]
    for temple in temples:
        for wish in wishes:
            title = f"{temple}｜{wish}"
            prompt = (
                f"請用道地台灣繁體中文，介紹「{temple}」的「{wish}」。"
                f"格式：兩段各150~200字正文（第一段介紹廟宇特色與神明職司，"
                f"第二段詳述祈願步驟與注意事項），再附2組FAQ。"
                f"文風生動貼近台灣民俗文化，讓讀者有身歷其境的感覺。"
                f"以JSON回傳：{{\"para1\":\"...\",\"para2\":\"...\","
                f"\"faq\":[{{\"q\":\"...\",\"a\":\"...\"}},{{\"q\":\"...\",\"a\":\"...\"}}]}}"
            )
            corpus.append({"title": title, "prompt": prompt, "utm": "temple"})

    return corpus


# ─────────────────────────────────────────────
# Telegraph 操作
# ─────────────────────────────────────────────

TELEGRAPH_API = "https://api.telegra.ph"

def create_account() -> str:
    """建立新的 Telegraph 帳號，回傳 access_token"""
    resp = requests.post(f"{TELEGRAPH_API}/createAccount", json={
        "short_name": f"yuexia_{random.randint(1000,9999)}",
        "author_name": "月夏星座館",
        "author_url": TARGET_URL,
    }, timeout=15)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"createAccount 失敗：{data}")
    return data["result"]["access_token"]


def build_node(tag: str, children, attrs: dict | None = None) -> dict:
    node = {"tag": tag, "children": children}
    if attrs:
        node["attrs"] = attrs
    return node


def publish_page(token: str, title: str, utm: str,
                 para1: str, para2: str, faqs: list) -> str:
    """組裝 Telegraph content 並發布，回傳頁面 URL"""
    cta_url = f"{TARGET_URL}?utm_source=telegraph&utm_medium={utm}"

    content = [
        # 首屏 CTA
        build_node("p", [
            build_node("strong", [
                build_node("a", ["🔮 立即免費諮詢，解開你的感情謎題 →"],
                           {"href": cta_url})
            ])
        ]),
        build_node("p", [""]),   # 空行

        # 正文第一段
        build_node("p", [para1]),
        build_node("p", [""]),

        # 正文第二段
        build_node("p", [para2]),
        build_node("p", [""]),

        # FAQ 區塊
        build_node("h4", ["常見問題 Q&A"]),
    ]

    for faq in faqs:
        content.append(build_node("p", [
            build_node("strong", [f"Q：{faq['q']}"]),
        ]))
        content.append(build_node("p", [f"A：{faq['a']}"]))
        content.append(build_node("p", [""]))

    # 文末 CTA
    content.append(build_node("p", [
        build_node("a", ["➡ 點此前往月夏，獲得你的專屬感情指引"],
                   {"href": cta_url})
    ]))

    payload = {
        "access_token": token,
        "title": title,
        "content": json.dumps(content, ensure_ascii=False),
        "author_name": "月夏星座館",
        "author_url": TARGET_URL,
        "return_content": False,
    }
    resp = requests.post(f"{TELEGRAPH_API}/createPage", json=payload, timeout=20)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"createPage 失敗：{data}")
    return "https://telegra.ph/" + data["result"]["path"]


# ─────────────────────────────────────────────
# LLM 內容生成
# ─────────────────────────────────────────────

def generate_content(client: OpenAI, prompt: str) -> dict:
    """呼叫 LLM，回傳包含 para1/para2/faq 的 dict"""
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system",
                     "content": (
                         "你是專業的台灣繁體中文感情命理內容創作者，"
                         "擅長撰寫讓讀者產生共鳴的命理與感情諮詢文章。"
                         "輸出必須是合法 JSON，不要加 markdown 代碼塊。"
                     )},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.85,
                max_tokens=800,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content.strip()
            data = json.loads(raw)
            # 基本欄位校驗
            assert "para1" in data and "para2" in data and "faq" in data
            assert len(data["faq"]) >= 2
            return data
        except Exception as e:
            print(f"  [LLM 重試 {attempt+1}/3] {e}")
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("LLM 生成失敗，已重試 3 次")


# ─────────────────────────────────────────────
# 斷點續傳輔助
# ─────────────────────────────────────────────

def load_done_titles() -> set:
    if os.path.exists(DONE_FILE):
        with open(DONE_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_done_title(title: str):
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
        print("❌ 缺少 OPENAI_API_KEY 環境變數，請在 GitHub Secrets 中設定。")
        sys.exit(1)

    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

    corpus     = build_corpus()
    done       = load_done_titles()
    pending    = [item for item in corpus if item["title"] not in done]

    total_pending = len(pending)
    this_batch    = pending[:BATCH_SIZE]

    print(f"📚 詞庫總量：{len(corpus)}  |  已完成：{len(done)}  |  "
          f"待發布：{total_pending}  |  本批次：{len(this_batch)}")

    if not this_batch:
        print("🎉 所有頁面已發布完畢！")
        return

    # 初始化第一個 Telegraph token
    token         = create_account()
    pages_since_new_account = 0
    success_count = 0
    fail_count    = 0

    for idx, item in enumerate(this_batch, 1):
        title = item["title"]
        utm   = item["utm"]

        # 每 30 頁換一個新 token，降低被限流風險
        if pages_since_new_account >= 30:
            print(f"  🔄 換新 Telegraph 帳號（已用 {pages_since_new_account} 頁）")
            try:
                token = create_account()
                pages_since_new_account = 0
                time.sleep(2)
            except Exception as e:
                print(f"  ⚠️  換帳號失敗，繼續沿用舊 token：{e}")

        print(f"[{idx}/{len(this_batch)}] 處理：{title}")

        try:
            # 生成內容
            data  = generate_content(client, item["prompt"])
            faqs  = data["faq"][:2]  # 最多取 2 組

            # 發布到 Telegraph
            url   = publish_page(token, title, utm,
                                 data["para1"], data["para2"], faqs)

            save_done_title(title)
            save_url(url)
            pages_since_new_account += 1
            success_count += 1
            print(f"  ✅ {url}")

        except Exception as e:
            fail_count += 1
            print(f"  ❌ 發布失敗：{e}")

        # 防限流：1.5~2.5 秒隨機間隔
        time.sleep(random.uniform(1.5, 2.5))

    print(f"\n本批次完成：✅ {success_count} 頁成功  ❌ {fail_count} 頁失敗")
    print(f"累計已發布：{len(done) + success_count} / {len(corpus)} 頁")


if __name__ == "__main__":
    main()
