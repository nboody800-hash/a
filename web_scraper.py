"""
Web Scraper - تصفح عادي أو عبر شبكة Tor
=========================================
المتطلبات:
    pip install requests[socks] beautifulsoup4 lxml stem

لتشغيل Tor:
    - Linux/Mac: sudo apt install tor && tor
    - Windows: حمّل Tor Browser أو Tor Expert Bundle وشغّله
    الـ SOCKS5 proxy يعمل على المنفذ 9050 بشكل افتراضي
"""

import requests
import json
import os
import re
import sys
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# ──────────────────────────────────────────────
#  الإعدادات
# ──────────────────────────────────────────────
TOR_PROXY = {
    "http":  "socks5h://127.0.0.1:9050",
    "https": "socks5h://127.0.0.1:9050",
}

MEMORY_FILE = "scraped_memory.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; rv:109.0) "
        "Gecko/20100101 Firefox/115.0"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}

# ──────────────────────────────────────────────
#  دالة التحقق من اتصال Tor
# ──────────────────────────────────────────────
def check_tor_connection() -> bool:
    """يتحقق إذا كان Tor يعمل ويعيد IP مختلف."""
    try:
        resp = requests.get(
            "https://check.torproject.org/api/ip",
            proxies=TOR_PROXY,
            timeout=15,
        )
        data = resp.json()
        if data.get("IsTor"):
            print(f"[✓] Tor يعمل بنجاح  ← IP: {data.get('IP')}")
            return True
        else:
            print(f"[!] الاتصال لا يمر عبر Tor  ← IP: {data.get('IP')}")
            return False
    except Exception as e:
        print(f"[✗] تعذّر الاتصال بـ Tor: {e}")
        print("    تأكد أن خدمة Tor تعمل على المنفذ 9050")
        return False


# ──────────────────────────────────────────────
#  دالة تنظيف HTML واستخراج النص
# ──────────────────────────────────────────────
def extract_clean_text(html: str) -> dict:
    """
    يستخرج ويُنظّف النص من HTML.
    يُعيد dict يحتوي: العنوان، الوصف، النص الكامل، الروابط.
    """
    soup = BeautifulSoup(html, "lxml")

    # حذف العناصر غير المفيدة
    for tag in soup(["script", "style", "noscript", "iframe",
                     "nav", "footer", "aside", "form"]):
        tag.decompose()

    # العنوان
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)

    # الوصف من meta
    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        description = meta_desc.get("content", "").strip()

    # استخراج النص الرئيسي
    # نحاول body أولاً، ثم article، ثم main
    body = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", {"id": re.compile(r"content|main", re.I)})
        or soup.body
        or soup
    )

    raw_text = body.get_text(separator="\n", strip=True) if body else ""

    # تنظيف النص: إزالة الأسطر الفارغة المتكررة والمسافات الزائدة
    lines = [line.strip() for line in raw_text.splitlines()]
    lines = [line for line in lines if len(line) > 2]          # حذف الأسطر القصيرة جداً
    clean_text = "\n".join(lines)
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)         # حذف الأسطر الفارغة الزائدة

    # استخراج الروابط
    links = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        text = a_tag.get_text(strip=True)
        if href.startswith("http") and text:
            links.append({"text": text[:80], "url": href})

    return {
        "title":       title,
        "description": description,
        "text":        clean_text,
        "links":       links[:30],          # أول 30 رابط فقط
        "word_count":  len(clean_text.split()),
    }


# ──────────────────────────────────────────────
#  دالة حفظ الذاكرة
# ──────────────────────────────────────────────
def save_to_memory(url: str, extracted: dict, mode: str) -> str:
    """
    يحفظ النص المستخرج في ملف JSON كذاكرة للسكربت.
    يُعيد مسار الملف المحفوظ.
    """
    # تحميل الذاكرة الحالية
    memory = []
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memory = json.load(f)
        except (json.JSONDecodeError, IOError):
            memory = []

    # إنشاء سجل جديد
    record = {
        "id":          len(memory) + 1,
        "timestamp":   datetime.now().isoformat(),
        "mode":        mode,                           # "normal" أو "tor"
        "url":         url,
        "domain":      urlparse(url).netloc,
        "title":       extracted["title"],
        "description": extracted["description"],
        "word_count":  extracted["word_count"],
        "text":        extracted["text"][:5000],       # أول 5000 حرف
        "links_count": len(extracted["links"]),
        "links":       extracted["links"],
    }

    memory.append(record)

    # الحفظ
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

    print(f"[💾] تم الحفظ في الذاكرة  ← السجل #{record['id']}  ({MEMORY_FILE})")
    return MEMORY_FILE


# ──────────────────────────────────────────────
#  دالة الجلب الرئيسية
# ──────────────────────────────────────────────
def fetch_page(url: str, use_tor: bool = False, timeout: int = 30) -> dict | None:
    """
    يجلب صفحة ويب ويُعيد النص المنظّف.

    Args:
        url:     رابط الصفحة
        use_tor: True لاستخدام Tor، False للتصفح العادي
        timeout: مهلة الانتظار بالثواني
    """
    mode    = "tor" if use_tor else "normal"
    proxies = TOR_PROXY if use_tor else None

    print(f"\n{'='*55}")
    print(f"[🌐] الوضع : {'Tor (مخفي)' if use_tor else 'عادي'}")
    print(f"[🔗] الرابط: {url}")
    print(f"{'='*55}")

    try:
        session = requests.Session()
        session.headers.update(HEADERS)

        resp = session.get(url, proxies=proxies, timeout=timeout)
        resp.raise_for_status()

        # اكتشاف الترميز
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text

        print(f"[✓] استجابة {resp.status_code}  |  الحجم: {len(html):,} حرف")

        # استخراج وتنظيف النص
        extracted = extract_clean_text(html)

        print(f"[📄] العنوان   : {extracted['title'][:70] or '(بدون عنوان)'}")
        print(f"[📝] الكلمات   : {extracted['word_count']:,}")
        print(f"[🔗] الروابط   : {len(extracted['links'])}")

        # حفظ في الذاكرة
        save_to_memory(url, extracted, mode)

        return extracted

    except requests.exceptions.ConnectionError:
        print("[✗] خطأ في الاتصال — تحقق من الإنترنت أو خدمة Tor")
    except requests.exceptions.Timeout:
        print(f"[✗] انتهت المهلة بعد {timeout} ثانية")
    except requests.exceptions.HTTPError as e:
        print(f"[✗] خطأ HTTP: {e}")
    except Exception as e:
        print(f"[✗] خطأ غير متوقع: {e}")

    return None


# ──────────────────────────────────────────────
#  عرض الذاكرة المحفوظة
# ──────────────────────────────────────────────
def show_memory(limit: int = 5):
    """يعرض آخر N سجلات محفوظة."""
    if not os.path.exists(MEMORY_FILE):
        print("[!] لا توجد ذاكرة محفوظة بعد.")
        return

    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        memory = json.load(f)

    print(f"\n{'='*55}")
    print(f"[📚] الذاكرة المحفوظة — آخر {min(limit, len(memory))} سجلات")
    print(f"{'='*55}")

    for rec in memory[-limit:]:
        print(f"\n  #{rec['id']}  [{rec['mode'].upper()}]  {rec['timestamp'][:19]}")
        print(f"  🔗 {rec['url'][:70]}")
        print(f"  📄 {rec['title'][:60] or '(بدون عنوان)'}")
        print(f"  📝 {rec['word_count']:,} كلمة  |  🔗 {rec['links_count']} رابط")
        print(f"  ─── مقتطف ───")
        snippet = rec["text"][:200].replace("\n", " ")
        print(f"  {snippet}...")


# ──────────────────────────────────────────────
#  واجهة التفاعل
# ──────────────────────────────────────────────
def interactive_mode():
    """واجهة تفاعلية سطر أوامر."""
    print("""
╔══════════════════════════════════════════╗
║        🕸️  Web Scraper  🧅               ║
║   تصفح عادي / مخفي عبر Tor              ║
╚══════════════════════════════════════════╝
""")
    while True:
        print("\n[1] جلب صفحة — وضع عادي")
        print("[2] جلب صفحة — وضع Tor (مخفي)")
        print("[3] التحقق من اتصال Tor")
        print("[4] عرض الذاكرة المحفوظة")
        print("[0] خروج")

        choice = input("\nاختر: ").strip()

        if choice == "0":
            print("مع السلامة! 👋")
            break

        elif choice in ("1", "2"):
            use_tor = (choice == "2")
            url = input("أدخل الرابط (مثال: https://example.com): ").strip()
            if not url.startswith("http"):
                url = "https://" + url

            result = fetch_page(url, use_tor=use_tor)

            if result:
                show_full = input("\nعرض النص الكامل؟ [y/N]: ").strip().lower()
                if show_full == "y":
                    print("\n" + "─"*55)
                    print(result["text"][:3000])
                    if len(result["text"]) > 3000:
                        print(f"\n... (النص كامل محفوظ في {MEMORY_FILE})")

        elif choice == "3":
            check_tor_connection()

        elif choice == "4":
            n = input("عدد السجلات للعرض [5]: ").strip()
            show_memory(int(n) if n.isdigit() else 5)

        else:
            print("[!] اختيار غير صالح")


# ──────────────────────────────────────────────
#  الاستخدام كمكتبة (import)
# ──────────────────────────────────────────────
def scrape(url: str, tor: bool = False) -> dict | None:
    """
    دالة مختصرة للاستخدام من سكربتات أخرى:

        from web_scraper import scrape
        data = scrape("https://example.com")
        data = scrape("http://someoniondomain.onion/page", tor=True)
    """
    return fetch_page(url, use_tor=tor)


# ──────────────────────────────────────────────
#  النقطة الرئيسية
# ──────────────────────────────────────────────
if __name__ == "__main__":
    # تشغيل مباشر مع رابط: python web_scraper.py https://example.com
    if len(sys.argv) >= 2:
        target_url = sys.argv[1]
        use_tor_flag = "--tor" in sys.argv
        fetch_page(target_url, use_tor=use_tor_flag)
    else:
        # الوضع التفاعلي
        interactive_mode()
