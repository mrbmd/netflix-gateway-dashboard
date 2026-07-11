import requests
import streamlit as st
import aiohttp
import asyncio
import re
import sqlite3
import json
from datetime import datetime
from typing import Tuple, Dict, Any

# ============================================================
# Optional Imports with Fallback
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
# Database Setup for Request Tracking
# ============================================================

DB_FILE = "request_history.db"

def init_db():
    """Initialize the database if it doesn't exist"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS requests
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      timestamp TEXT,
                      request_number INTEGER,
                      plan TEXT,
                      country TEXT,
                      pc_link_preview TEXT,
                      mobile_link_preview TEXT,
                      full_data TEXT)''')
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Database error: {e}")
        return False

def save_request_data(data, request_number):
    """Save request data to local database"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Store preview of links (not full links for privacy)
        pc_preview = data.get("pc_link", "")[:30] + "..." if data.get("pc_link") else None
        mobile_preview = data.get("mobile_link", "")[:30] + "..." if data.get("mobile_link") else None
        
        c.execute("""INSERT INTO requests 
                     (timestamp, request_number, plan, country, 
                      pc_link_preview, mobile_link_preview, full_data)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (datetime.now().isoformat(), 
                   request_number,
                   data.get("plan", "Unknown"),
                   data.get("country", "Unknown"),
                   pc_preview,
                   mobile_preview,
                   json.dumps(data)))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Failed to save: {e}")
        return False

def get_request_count():
    """Get total number of requests made"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM requests")
        count = c.fetchone()[0]
        conn.close()
        return count
    except:
        return 0

def get_recent_requests(limit=10):
    """Get recent requests for display"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""SELECT id, timestamp, request_number, plan, country 
                     FROM requests ORDER BY id DESC LIMIT ?""", (limit,))
        rows = c.fetchall()
        conn.close()
        return rows
    except:
        return []

def get_first_request():
    """Get first ever request"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""SELECT timestamp, request_number, plan, country 
                     FROM requests ORDER BY id ASC LIMIT 1""")
        row = c.fetchone()
        conn.close()
        return row
    except:
        return None

def clear_history():
    """Clear all request history (for testing)"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM requests")
        conn.commit()
        conn.close()
        return True
    except:
        return False

# ============================================================
# Application Information
# ============================================================

APP_NAME = "Gateway Dashboard"
APP_VERSION = "v3"
REQUEST_TIMEOUT = 30

# ============================================================
# Mobile Headers for Verification
# ============================================================

MOBILE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ============================================================
# Enhanced Patterns
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

async def verify_link_async(session: aiohttp.ClientSession, url: str) -> Tuple[bool, Dict[str, Any]]:
    """Returns (is_valid, debug_info) with positive and negative matches."""
    debug = {'positive_matches': [], 'negative_matches': []}
    
    if not BEAUTIFULSOUP_AVAILABLE:
        debug['error'] = "BeautifulSoup not available"
        return False, debug
    
    try:
        kwargs = {
            "headers": MOBILE_HEADERS,
            "timeout": aiohttp.ClientTimeout(total=15),
            "allow_redirects": True
        }
        
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
            
            title = ''
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            else:
                title_tag = soup.find('title')
                if title_tag:
                    title = title_tag.get_text(strip=True)
            
            body_text = soup.get_text(separator=' ', strip=True)
            combined_text = f"{title} {body_text}"
            
            # Language detection (optional)
            if LANGDETECT_AVAILABLE:
                try:
                    lang = detect(combined_text)
                    if lang != 'en' and DEEP_TRANSLATOR_AVAILABLE:
                        try:
                            translator = GoogleTranslator(source='auto', target='en')
                            max_chunk = 4000
                            chunks = [combined_text[i:i+max_chunk] for i in range(0, len(combined_text), max_chunk)]
                            translated_chunks = []
                            for chunk in chunks:
                                translated_chunks.append(translator.translate(chunk))
                            combined_text = ' '.join(translated_chunks)
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

async def grab_link_worker(session: aiohttp.ClientSession, worker_id: int, stop_event: asyncio.Event, result_holder: list):
    """Worker to fetch and validate links."""
    try:
        api_url = st.secrets["gateway"]["api_url"]
        auth_key = st.secrets["gateway"]["auth_key"]
        
        headers = {
            "Authorization": f"Bearer {auth_key}",
            "Content-Type": "application/json"
        }
        
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
    except Exception as e:
        pass

async def async_link_extraction():
    """Main async function to extract valid links."""
    for batch in range(1, MAX_BATCHES + 1):
        stop_event = asyncio.Event()
        result_holder = []
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in range(BATCH_SIZE):
                tasks.append(asyncio.create_task(
                    grab_link_worker(session, i+1, stop_event, result_holder)
                ))
            
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
# Streamlit Page Configuration
# ============================================================

st.set_page_config(
    page_title=f"{APP_NAME} {APP_VERSION}",
    page_icon="🔗",
    layout="centered",
)

# ============================================================
# Call Gateway API (Synchronous - Original Method)
# ============================================================

def call_gateway():
    api_url = st.secrets["gateway"]["api_url"]
    auth_key = st.secrets["gateway"]["auth_key"]

    headers = {
        "Authorization": f"Bearer {auth_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    response = requests.post(
        api_url,
        headers=headers,
        json={},
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code in (401, 403):
        try:
            error_data = response.json()
            error_message = error_data.get("message", "API authentication failed.")
        except ValueError:
            error_message = "API authentication failed."
        raise PermissionError(error_message)

    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as error:
        raise ValueError("The API returned an invalid JSON response.") from error

    if not data.get("success"):
        raise ValueError(data.get("message", "The API request failed."))

    return data

# ============================================================
# Async Gateway Call (Wrapper for Streamlit)
# ============================================================

def call_gateway_async():
    """Wrapper to run async function in Streamlit."""
    try:
        if not BEAUTIFULSOUP_AVAILABLE:
            st.warning("Advanced validation mode requires 'beautifulsoup4'. Using standard mode.")
            return call_gateway()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            data = loop.run_until_complete(async_link_extraction())
        finally:
            loop.close()
        
        if data is None:
            return {"success": False, "message": "No valid link found after all attempts"}
        
        if not data.get("success"):
            data["success"] = True
            
        return data
    except Exception as e:
        st.warning(f"Advanced mode failed: {str(e)}. Falling back to standard mode...")
        return call_gateway()

# ============================================================
# Login Page
# ============================================================

def login_page():
    st.title(f"🔐 {APP_NAME}")
    st.info(f"Running Version: {APP_VERSION}")
    st.caption("Sign in to access the dashboard.")

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
# Display Request Status (NEW)
# ============================================================

def display_request_status():
    """Show request status and history in dashboard"""
    
    total_requests = get_request_count()
    current_request = total_requests + 1
    
    st.divider()
    st.subheader("📊 Request Status")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Requests", total_requests)
    
    with col2:
        if total_requests == 0:
            st.metric("Current Request", "1 🆕")
            st.success("🌟 FIRST REQUEST EVER!")
        else:
            st.metric("Current Request", current_request)
            
            if current_request <= 5:
                st.info(f"🔍 Early testing phase (Request #{current_request})")
            elif current_request <= 20:
                st.info(f"🔄 Testing phase (Request #{current_request})")
            else:
                st.success(f"✅ Consistent testing (Request #{current_request})")
    
    with col3:
        if total_requests > 0:
            first = get_first_request()
            if first:
                st.metric("First Request", f"#{first[1]}")
                st.caption(f"at {first[0][:10]}")
    
    if total_requests > 0:
        with st.expander(f"📜 Last {min(10, total_requests)} Requests"):
            history = get_recent_requests(10)
            if history:
                for row in history:
                    col1, col2, col3 = st.columns([1, 2, 2])
                    with col1:
                        st.write(f"**#{row[2]}**")
                    with col2:
                        st.write(f"🕐 {row[1][:16]}")
                    with col3:
                        st.write(f"📋 {row[3]} | {row[4]}")
                    st.divider()
            else:
                st.info("No history yet")
    
    if total_requests > 0:
        if st.button("🗑️ Clear History", key="clear_history"):
            if clear_history():
                st.success("History cleared!")
                st.rerun()

# ============================================================
# Display API Result
# ============================================================

def display_result(data):
    st.divider()

    if data.get("success", False):
        st.success(data.get("message", "Links generated successfully."))
        
        plan_column, country_column = st.columns(2)
        with plan_column:
            st.metric(label="Plan", value=data.get("plan", "Unknown"))
        with country_column:
            st.metric(label="Country", value=data.get("country", "Unknown"))
        
        if "validation" in data:
            validation = data["validation"]
            if validation.get("valid", False):
                st.success("✅ Link Validation Passed!")
            else:
                st.warning("⚠️ Link Validation Failed")
            
            with st.expander("🔍 Validation Details"):
                if validation.get("positive_matches"):
                    st.write("**Positive Matches Found:**")
                    for match in validation["positive_matches"]:
                        st.code(match)
                
                if validation.get("negative_matches"):
                    st.write("**Negative Matches Found:**")
                    for match in validation["negative_matches"]:
                        st.code(match)
                
                if "error" in validation:
                    st.error(f"Validation Error: {validation['error']}")

        st.write("### 💻 Desktop Link")
        pc_link = data.get("pc_link")
        if pc_link:
            st.code(pc_link, language=None, wrap_lines=True)
        else:
            st.warning("Desktop link was not returned by the API.")

        st.write("### 📱 Mobile Link")
        mobile_link = data.get("mobile_link")
        if mobile_link:
            st.code(mobile_link, language=None, wrap_lines=True)
        else:
            st.warning("Mobile link was not returned by the API.")
    else:
        st.error(data.get("message", "Failed to generate links."))

# ============================================================
# Dashboard Page (MODIFIED with tracking)
# ============================================================

def dashboard_page():
    """Displays the main dashboard after successful login with tracking."""
    
    # Initialize database if not already done
    if "db_initialized" not in st.session_state:
        if init_db():
            st.session_state["db_initialized"] = True
    
    st.title(f"🔗 {APP_NAME}")
    st.info(f"Running Version: {APP_VERSION}")
    st.caption("Generate desktop and mobile links.")
    
    # Display request tracking
    display_request_status()
    
    # Check if advanced mode is available
    advanced_available = BEAUTIFULSOUP_AVAILABLE
    
    if not advanced_available:
        st.info("ℹ️ Advanced validation mode requires additional packages. Install with: pip install beautifulsoup4 langdetect deep-translator")

    if advanced_available:
        operation_mode = st.radio(
            "Select Operation Mode:",
            ["Standard (Single Request)", "Advanced (Batch Validation)"],
            horizontal=True
        )
    else:
        operation_mode = "Standard (Single Request)"
        st.info("Using standard mode only")

    if st.button("🔗 Generate Links", use_container_width=True, type="primary"):
        st.session_state.pop("gateway_result", None)

        try:
            if operation_mode == "Standard (Single Request)":
                with st.spinner("Sending request to the gateway..."):
                    result = call_gateway()
                    st.session_state["gateway_result"] = result
                    
                    request_num = get_request_count() + 1
                    save_request_data(result, request_num)
                    
                    if request_num == 1:
                        st.balloons()
                        st.success("🌟 FIRST SUCCESSFUL REQUEST EVER! 🎉")
                    else:
                        st.success(f"✅ Request #{request_num} saved!")
            else:
                with st.spinner("Launching batch workers for link validation..."):
                    result = call_gateway_async()
                    
                    if result:
                        st.session_state["gateway_result"] = result
                        request_num = get_request_count() + 1
                        save_request_data(result, request_num)
                        
                        if request_num == 1:
                            st.balloons()
                            st.success("🌟 FIRST SUCCESSFUL REQUEST EVER! 🎉")
                        else:
                            st.success(f"✅ Request #{request_num} saved!")
                    else:
                        st.error("No valid link could be obtained after all attempts.")

        except PermissionError as error:
            st.error(f"Authentication error: {error}")
        except requests.exceptions.Timeout:
            st.error("The API request timed out. Please try again.")
        except requests.exceptions.ConnectionError:
            st.error("Could not connect to the API server.")
        except requests.exceptions.HTTPError as error:
            status_code = error.response.status_code if error.response is not None else "Unknown"
            st.error(f"The API returned HTTP status {status_code}.")
        except ValueError as error:
            st.error(str(error))
        except requests.exceptions.RequestException as error:
            st.error(f"Request failed: {error}")
        except Exception as error:
            st.error(f"Unexpected error: {error}")
    
    if "gateway_result" in st.session_state:
        display_result(st.session_state["gateway_result"])
        
        total_requests = get_request_count()
        if total_requests > 0:
            first = get_first_request()
            if first:
                st.caption(f"📌 First request was #{first[1]} on {first[0][:10]}")
                if total_requests == 1:
                    st.info("✨ This is the FIRST data fetch ever!")
                else:
                    st.info(f"📊 This is data from request #{total_requests}")

    st.divider()

    if st.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

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
