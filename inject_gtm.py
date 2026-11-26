"""
inject_gtm.py — 把 GTM 代碼注入所有已生成頁面（不重調 API）
"""
import re
from pathlib import Path

DOCS_DIR = Path("docs")
GTM_ID = "GTM-P3HF5V64"

GTM_HEAD = f"""
  <!-- Google Tag Manager -->
  <script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
  new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
  j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
  'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
  }})(window,document,'script','dataLayer','{GTM_ID}');</script>
  <!-- End Google Tag Manager -->"""

GTM_BODY = f"""<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={GTM_ID}"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->
"""

updated = 0
skipped = 0

for html_file in sorted(DOCS_DIR.rglob("index.html")):
    old_html = html_file.read_text(encoding="utf-8")

    # 已有 GTM 就跳過
    if GTM_ID in old_html:
        skipped += 1
        continue

    new_html = old_html

    # 在 </head> 前插入 GTM head snippet
    new_html = new_html.replace("</head>", GTM_HEAD + "\n</head>", 1)

    # 在 <body> 後插入 GTM noscript
    new_html = re.sub(r"(<body[^>]*>)", r"\1\n" + GTM_BODY, new_html, count=1)

    if new_html != old_html:
        html_file.write_text(new_html, encoding="utf-8")
        updated += 1
        if updated % 200 == 0:
            print(f"  已處理 {updated} 頁...")

print(f"\n✅ 完成！注入 GTM：{updated} 頁，跳過（已有）：{skipped} 頁")
