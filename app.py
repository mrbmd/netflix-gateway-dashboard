import requests
import streamlit as st
import aiohttp
import asyncio
import re
import sqlite3
from datetime import datetime
from typing import Tuple, Dict, Any

# ============================================================
# Optional Imports
# ============================================================

try:
    from bs4 import BeautifulSoup
    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    BEAUTIFULSOUP_AVAILABLE = False

try:
    from langdetect import detect
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False

try:
    from deep_translator import GoogleTranslator
    DEEP_TRANSLATOR_AVAILABLE = True
except ImportError:
    DEEP_TRANSLATOR_AVAILABLE = False

# ============================================================
# Database Setup - Track Links Only
# ============================================================

DB_FILE = "link_history.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS links
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      timestamp TEXT,
                      request_number INTEGER,
                      plan TEXT,
                      country TEXT,
                      pc_link TEXT,
                      mobile_link TEXT,
                      is_duplicate BOOLEAN DEFAULT 0,
                      duplicate_of INTEGER DEFAULT NULL)''')
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Database error: {e}")
        return False

def save_link_data(data, request_number):
    try:
        pc_link = data.get("pc_link")
        mobile_link = data.get("mobile_link")
        is_duplicate = False
        duplicate_of = None
        
        if pc_link and mobile_link:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id FROM links WHERE pc_link = ? OR mobile_link = ?", (pc_link, mobile_link))
            result = c.fetchone()
            if result:
                is_duplicate = True
                duplicate_of = result[0]
            
            c.execute("""INSERT INTO links 
                         (timestamp, request_number, plan, country, 
                          pc_link, mobile_link, is_duplicate, duplicate_of)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                      (datetime.now().isoformat(), request_number,
                       data.get("plan", "Unknown"), data.get("country", "Unknown"),
                       pc_link, mobile_link, is_duplicate, duplicate_of))
            conn.commit()
            conn.close()
            return is_duplicate, duplicate_of
        return False, None
    except:
        return False, None

def get_link_stats():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM links")
        total = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(DISTINCT pc_link) FROM links WHERE pc_link IS NOT NULL")
        unique = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM links WHERE is_duplicate = 1")
        duplicates = c.fetchone()[0] or 0
        conn.close()
        return total, unique, duplicates
    except:
        return 0, 0, 0

def get_duplicate_origin(duplicate_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT request_number FROM links WHERE id = ?", (duplicate_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None
    except:
        return None

def export_history():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT request_number, timestamp, plan, country, pc_link, mobile_link, is_duplicate FROM links ORDER BY id DESC")
        data = c.fetchall()
        conn.close()
        if data:
            import pandas as pd
            df = pd.DataFrame(data, columns=['Request#', 'Timestamp', 'Plan', 'Country', 'PC Link', 'Mobile Link', 'Is Duplicate'])
            return df.to_csv(index=False)
        return None
    except:
        return None

def clear_history():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM links")
        conn.commit()
        conn.close()
        return True
    except:
        return False

# ============================================================
# Application Information
# ============================================================

APP_NAME = "Link Tester"
APP_VERSION = "v4"
REQUEST_TIMEOUT = 30

# ============================================================
# Mobile Headers
# ============================================================

MOBILE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ============================================================
# Patterns
# ============================================================

POSITIVE_PATTERNS = re.compile(
    r'(?:Open\s+App|'
    r'Download\s+the\s+mysitename\s+app|'
    r'Netflix\s+is\s+better\s+with\s+the\s+app|'
    r'You\s+need\s+the\s+mysitename\s+app|'
    r'To\s+go\s+out|'
    r'Log\s*out|'
    r'Sign\s*out|'
    r'Manage\s+Account|'
    r'Your\s+Account|'
    r'Open\s+application|'
    r'Unsupported\s+browser|'
    r'Tap\s+to\s+open)',
    re.IGNORECASE
)

NEGATIVE_PATTERNS = re.compile(
    r'(?:Sign\s+In(?!\s*Out)|'
    r'Create\s+Account|'
    r'Enter\s+your\s+info\s+to\s+sign\s+in|'
    r'Sign\s+in\s+to\s+mysitename|'
    r'Forgot\s+password|'
    r'Remember\s+me|'
    r'Get\s+Started|'
    r'Or\s+get\s+started\s+with\s+a\s+new\s+account\.|'
    r'Email\s+or\s+mobile\s+number|'
    r'Continue|'
    r'Forgot\s+email\s+or\s+mobile\s+number|'
    r'Learn\s+more\s+about\s+sign[- ]in|'
    r'This\s+page\s+is\s+protected\s+by\s+Google\s+reCAPTCHA\s+to\s+ensure\s+you\'?re\s+not\s+a\s+bot\.?)',
    re.IGNORECASE
)

# ============================================================
# Async Link Verification
# ============================================================

BATCH_SIZE = 10
MAX_BATCHES = 3

async def verify_link_async(session, url):
    debug = {'positive_matches': [], 'negative_matches': []}
    if not BEAUTIFULSOUP_AVAILABLE:
        debug['error'] = "BeautifulSoup not available"
        return False, debug
    try:
        kwargs = {"headers": MOBILE_HEADERS, "timeout": aiohttp.ClientTimeout(total=15), "allow_redirects": True}
        async with session.get(url, **kwargs) as resp:
            if resp.status != 200:
                return False, debug
            final_url = str(resp.url)
            if any(part in final_url for part in ['/login', '/SignUp', '/help', 'nextpage']):
                return False, debug
            for hist in resp.history:
                if any(part in str(hist.url) for part in ['/login', '/SignUp', '/help', 'nextpage']):
                    return False, debug
            html = await resp.text()
            soup = BeautifulSoup(html, 'html.parser')
            title = soup.title.string.strip() if soup.title and soup.title.string else ''
            body_text = soup.get_text(separator=' ', strip=True)
            combined_text = f"{title} {body_text}"
            if LANGDETECT_AVAILABLE:
                try:
                    lang = detect(combined_text)
                    if lang != 'en' and DEEP_TRANSLATOR_AVAILABLE:
                        try:
                            translator = GoogleTranslator(source='auto', target='en')
                            chunks = [combined_text[i:i+4000] for i in range(0, len(combined_text), 4000)]
                            combined_text = ' '.join([translator.translate(c) for c in chunks])
                        except:
                            pass
                except:
                    pass
            debug['positive_matches'] = POSITIVE_PATTERNS.findall(combined_text)
            debug['negative_matches'] = NEGATIVE_PATTERNS.findall(combined_text)
            has_positive = bool(debug['positive_matches'])
            has_negative = bool(debug['negative_matches'])
            return (has_positive and not has_negative), debug
    except Exception as e:
        debug['error'] = str(e)
        return False, debug

async def grab_link_worker(session, worker_id, stop_event, result_holder):
    try:
        api_url = st.secrets["gateway"]["api_url"]
        auth_key = st.secrets["gateway"]["auth_key"]
        headers = {"Authorization": f"Bearer {auth_key}", "Content-Type": "application/json"}
        async with session.post(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            data = await resp.json()
            if data.get("success") and data.get("plan", "").lower() == "premium":
                mobile_link = data.get("mobile_link")
                if mobile_link:
                    is_valid, debug = await verify_link_async(session, mobile_link)
                    data['validation'] = {
                        'positive_matches': debug.get('positive_matches', [])[:5],
                        'negative_matches': debug.get('negative_matches', [])[:5],
                        'valid': is_valid
                    }
                    if 'error' in debug:
                        data['validation']['error'] = debug['error']
                    result_holder.append(data)
                    stop_event.set()
                    return
    except:
        pass

async def async_link_extraction():
    for batch in range(1, MAX_BATCHES + 1):
        stop_event = asyncio.Event()
        result_holder = []
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in range(BATCH_SIZE):
                tasks.append(asyncio.create_task(grab_link_worker(session, i+1, stop_event, result_holder)))
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=20.0)
            except asyncio.TimeoutError:
                pass
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if result_holder:
                return result_holder[0]
            else:
                if batch < MAX_BATCHES:
                    await asyncio.sleep(2)
                else:
                    return None
    return None

# ============================================================
# NEW: Async TV Gateway Call
# ============================================================

async def async_tv_injection(digits):
    """Try both formats for TV code"""
    tv_url = st.secrets["gateway"]["tv_url"]
    auth_key = st.secrets["gateway"]["auth_key"]
    headers = {"Authorization": f"Bearer {auth_key}", "Content-Type": "application/json"}
    
    async with aiohttp.ClientSession() as session:
        # Attempt 1: hyphenated format
        formatted = f"{digits[:4]}-{digits[4:]}"
        try:
            async with session.post(tv_url, json={"tv_code": formatted}, headers=headers, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                data = await resp.json()
                if data.get("success"):
                    return data
        except Exception as e:
            pass
        
        # Attempt 2: plain digits
        try:
            async with session.post(tv_url, json={"tv_code": digits}, headers=headers, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                data = await resp.json()
                return data
        except Exception as e:
            return {"success": False, "message": str(e)}

# ============================================================
# NEW: Async Cookie Gateway Call (with retries)
# ============================================================

async def async_grab_cookie():
    """Fetch cookie with up to 3 retries"""
    cookie_url = st.secrets["gateway"]["cookie_url"]
    auth_key = st.secrets["gateway"]["auth_key"]
    headers = {"Authorization": f"Bearer {auth_key}", "Content-Type": "application/json"}
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(cookie_url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        raise Exception(f"HTTP {resp.status}")
                    data = await resp.json()
                    if data.get("success") and data.get("cookie"):
                        return data
                    else:
                        if attempt < max_retries:
                            await asyncio.sleep(1.5)
        except Exception as e:
            if attempt < max_retries:
                await asyncio.sleep(2)
    return {"success": False, "message": "All attempts exhausted"}

# ============================================================
# Wrappers for Streamlit (run async functions)
# ============================================================

def run_async(coro):
    """Helper to run async function in Streamlit"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def call_gateway_async():
    try:
        if not BEAUTIFULSOUP_AVAILABLE:
            return {"success": False, "message": "BeautifulSoup not installed"}
        data = run_async(async_link_extraction())
        if data is None:
            return {"success": False, "message": "No valid link found"}
        if not data.get("success"):
            data["success"] = True
        return data
    except Exception as e:
        return {"success": False, "message": str(e)}

def call_tv_gateway(digits):
    try:
        return run_async(async_tv_injection(digits))
    except Exception as e:
        return {"success": False, "message": str(e)}

def call_cookie_gateway():
    try:
        return run_async(async_grab_cookie())
    except Exception as e:
        return {"success": False, "message": str(e)}

# ============================================================
# Streamlit Page Configuration
# ============================================================

st.set_page_config(
    page_title=f"Link Tester {APP_VERSION}",
    page_icon="🔗",
    layout="centered",
)

# ============================================================
# Login Page
# ============================================================

def login_page():
    st.title("🔐 Link Tester")
    st.caption("Sign in to access the dashboard")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_clicked = st.form_submit_button("Login", use_container_width=True)

    if login_clicked:
        correct_username = st.secrets["auth"]["username"]
        correct_password = st.secrets["auth"]["password"]
        if username == correct_username and password == correct_password:
            st.session_state["logged_in"] = True
            st.rerun()
        else:
            st.error("Invalid username or password.")

# ============================================================
# Dashboard Page - With 3 Modes
# ============================================================

def dashboard_page():
    if "db_initialized" not in st.session_state:
        if init_db():
            st.session_state["db_initialized"] = True
    
    st.title("🔗 Link Tester")
    st.caption("Test links, TV login, and cookies")
    
    # ─── Mode Selector ───
    mode = st.radio(
        "Select Mode:",
        ["🔗 Link Grabber", "📺 TV Login", "🍪 Cookie Grabber"],
        horizontal=True
    )
    
    st.divider()
    
    # ─── MODE 1: Link Grabber ───
    if mode == "🔗 Link Grabber":
        link_grabber_mode()
    # ─── MODE 2: TV Login ───
    elif mode == "📺 TV Login":
        tv_login_mode()
    # ─── MODE 3: Cookie Grabber ───
    else:
        cookie_grabber_mode()
    
    st.divider()
    
    # Logout
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# ============================================================
# Mode 1: Link Grabber (Existing)
# ============================================================

def link_grabber_mode():
    total, unique, duplicates = get_link_stats()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Requests", total)
    with col2:
        st.metric("Unique Links", unique)
    with col3:
        dup_percent = (duplicates / total * 100) if total > 0 else 0
        st.metric("Duplicates", f"{duplicates} ({dup_percent:.0f}%)")
    
    st.divider()
    
    if st.button("🔍 Check for New Link", use_container_width=True, type="primary"):
        st.session_state.pop("result", None)
        st.session_state.pop("is_dup", None)
        st.session_state.pop("duplicate_of", None)
        st.session_state.pop("request_num", None)
        
        with st.spinner("Searching for links..."):
            result = call_gateway_async()
            if result and result.get("success"):
                current_total = get_link_stats()[0]
                request_num = current_total + 1
                is_dup, dup_of = save_link_data(result, request_num)
                
                st.session_state["result"] = result
                st.session_state["is_dup"] = is_dup
                st.session_state["duplicate_of"] = dup_of
                st.session_state["request_num"] = request_num
                
                if is_dup:
                    st.warning("🔄 This is a DUPLICATE link")
                    if dup_of:
                        orig = get_duplicate_origin(dup_of)
                        if orig:
                            st.caption(f"First seen in Request #{orig}")
                else:
                    st.success("✅ This is a FRESH NEW link")
            else:
                st.error(result.get("message", "Failed to get link"))
    
    # Show result
    if "result" in st.session_state:
        result = st.session_state["result"]
        request_num = st.session_state.get("request_num", 0)
        
        st.divider()
        if request_num > 0:
            st.caption(f"Request #{request_num}")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Plan", result.get("plan", "Unknown"))
        with col2:
            st.metric("Country", result.get("country", "Unknown"))
        
        st.write("**Desktop Link:**")
        st.code(result.get("pc_link") or "Not available", language=None)
        
        st.write("**Mobile Link:**")
        st.code(result.get("mobile_link") or "Not available", language=None)
        
        if "validation" in result:
            validation = result["validation"]
            if validation.get("valid", False):
                st.success("✅ Link validated")
            else:
                st.warning("⚠️ Link validation failed")
            
            with st.expander("Validation Details"):
                if validation.get("positive_matches"):
                    st.write("Positive matches:")
                    for match in validation["positive_matches"]:
                        st.code(match)
                if validation.get("negative_matches"):
                    st.write("Negative matches:")
                    for match in validation["negative_matches"]:
                        st.code(match)
    
    st.divider()
    
    # Action buttons
    col1, col2 = st.columns(2)
    with col1:
        if total > 0:
            csv = export_history()
            if csv:
                st.download_button(
                    "📥 Export CSV", csv,
                    f"link_history_{datetime.now().strftime('%Y%m%d')}.csv",
                    "text/csv", use_container_width=True
                )
    with col2:
        if total > 0:
            if st.button("🗑️ Clear History", use_container_width=True):
                if clear_history():
                    st.success("History cleared!")
                    st.rerun()

# ============================================================
# Mode 2: TV Login (NEW)
# ============================================================

def tv_login_mode():
    st.subheader("📺 TV Login")
    st.caption("Enter the 8-digit code shown on your TV")
    
    # Input for TV code
    tv_code = st.text_input(
        "TV Code",
        placeholder="XXXX-XXXX or XXXXXXXX or XXXX XXXX",
        max_chars=20
    )
    
    if st.button("📺 Submit TV Code", use_container_width=True, type="primary"):
        # Extract digits only
        digits = ''.join(ch for ch in tv_code if ch.isdigit())
        
        if len(digits) != 8:
            st.error("❌ Invalid code. Must contain exactly 8 digits.")
            return
        
        with st.spinner("Processing TV code..."):
            result = call_tv_gateway(digits)
            
            if result and result.get("success"):
                st.success("✅ TV Login Successful!")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Plan", result.get("plan", "Unknown"))
                with col2:
                    st.metric("Country", result.get("country", "Unknown"))
                
                st.info(result.get("message", "Account unlocked"))
            else:
                st.error(f"❌ Failed: {result.get('message', 'Unknown error')}")

# ============================================================
# Mode 3: Cookie Grabber (NEW)
# ============================================================

def cookie_grabber_mode():
    st.subheader("🍪 Cookie Grabber")
    st.caption("Fetch session cookie from the gateway")
    
    if st.button("🍪 Fetch Cookie", use_container_width=True, type="primary"):
        with st.spinner("Fetching cookie..."):
            result = call_cookie_gateway()
            
            if result and result.get("success"):
                st.success("✅ Cookie Fetched Successfully!")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Plan", result.get("plan", "Unknown"))
                with col2:
                    st.metric("Country", result.get("country", "Unknown"))
                
                if result.get("message"):
                    st.info(result["message"])
                
                st.write("**Cookie:**")
                st.code(result.get("cookie", "Not available"), language=None)
            else:
                st.error(f"❌ Failed: {result.get('message', 'Unknown error')}")

# ============================================================
# Main Application Flow
# ============================================================

def main():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if st.session_state["logged_in"]:
        dashboard_page()
    else:
        login_page()

# ============================================================
# Start Application
# ============================================================

if __name__ == "__main__":
    main()
