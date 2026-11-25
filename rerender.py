"""
rerender.py — 重新 render 所有已生成頁面的 CTA 連結，不重調 API
用法：python rerender.py（在 heimaoseo repo 根目錄執行）
"""
import sys, os, re
sys.argv = ['rerender.py']
os.environ.setdefault('OPENAI_API_KEY', 'x')

# 只 import build_corpus 和 render_html，不跑 main()
import main as m

corpus = m.build_corpus()
slug_to_item = {item['slug']: item for item in corpus}

docs_p = m.DOCS_DIR / 'p'
updated = 0
skipped = 0

for page_dir in sorted(docs_p.iterdir()):
    html_file = page_dir / 'index.html'
    if not html_file.exists():
        continue
    slug = page_dir.name
    item = slug_to_item.get(slug)
    if not item:
        # 舊式 slug 找不到 item，根據前綴猜分類
        if slug.startswith('tarot'):
            _fallback_landing = 'market?lite=tarot#tarot'
            _fallback_utm = 'tarot_card'
        elif any(slug.startswith(p) for p in ['aquarius','pisces','aries','taurus','gemini','cancer','leo','virgo','libra','scorpio','sagittarius','capricorn']):
            _fallback_landing = 'market#bazi'
            _fallback_utm = 'zodiac'
        elif any(slug.startswith(p) for p in ['rat-','ox-','tiger-','rabbit-','dragon-','snake-','horse-','goat-','monkey-','rooster-','dog-','pig-']):
            _fallback_landing = 'market#bazi'
            _fallback_utm = 'shengxiao'
        elif any(slug.startswith(p) for p in ['taipei','tainan','taichung','kaohsiung','mazu','guanyin','chenghuang']):
            _fallback_landing = 'jiaobei'
            _fallback_utm = 'temple'
        elif slug.startswith('psych'):
            _fallback_landing = 'tests'
            _fallback_utm = 'psychology'
        else:
            _fallback_landing = 'market?lite=1#yuelao'
            _fallback_utm = 'yuelao'
        # 直接替換
        new_cta = (f'https://yuexia.app/{_fallback_landing}&utm_source=seo&utm_medium={_fallback_utm}&utm_campaign={slug}'
                   if '?' in _fallback_landing else
                   f'https://yuexia.app/{_fallback_landing}?utm_source=seo&utm_medium={_fallback_utm}&utm_campaign={slug}')
        new_html = re.sub(
            r'https://yuexia\.app/\?utm_source=seo[^"\'<\s]*',
            new_cta,
            old_html
        )
        if new_html != old_html:
            html_file.write_text(new_html, encoding='utf-8')
            updated += 1
            if updated % 100 == 0:
                print(f'  已更新 {updated} 頁...')
        else:
            skipped += 1
        continue

    old_html = html_file.read_text(encoding='utf-8')
    # 只替換 CTA 連結部分（避免重調 API）
    # 找到舊的 cta_url
    old_cta = re.search(r'https://yuexia\.app/[^"\'<\s]*utm_source=seo[^"\'<\s]*', old_html)
    if not old_cta:
        skipped += 1
        continue

    # 生成新的 cta_url
    _CAT_LANDING = {
        '月老靈籤': 'market?lite=1#yuelao',
        '塔羅占卜': 'market?lite=tarot#tarot',
        '八字命理': 'market#bazi',
        '廟宇祈福': 'jiaobei',
        '感情修復': 'market?lite=1#yuelao',
        '感情占卜': 'market?lite=1#yuelao',
        '感情心理': 'tests',
        '感情技巧': 'market?lite=1#yuelao',
        '星座感情': 'market#bazi',
        '星座進階': 'market#bazi',
        '星座運勢': 'market#bazi',
        '星座配對': 'market#bazi',
        '生肖運勢': 'market#bazi',
    }
    _landing = _CAT_LANDING.get(item['category'], 'market?lite=1#yuelao')
    utm = item['utm']
    new_cta = (f'https://yuexia.app/{_landing}&utm_source=seo&utm_medium={utm}&utm_campaign={slug}'
               if '?' in _landing else
               f'https://yuexia.app/{_landing}?utm_source=seo&utm_medium={utm}&utm_campaign={slug}')

    # 替換所有 yuexia.app/?utm_... 或 yuexia.app/?...utm_... 形式
    new_html = re.sub(
        r'https://yuexia\.app/\?utm_source=seo[^"\'<\s]*',
        new_cta,
        old_html
    )

    if new_html != old_html:
        html_file.write_text(new_html, encoding='utf-8')
        updated += 1
        if updated % 100 == 0:
            print(f'  已更新 {updated} 頁...')
    else:
        skipped += 1

print(f'\n✅ 完成！更新：{updated} 頁，跳過：{skipped} 頁')
