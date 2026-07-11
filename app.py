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
# Database Setup - Track Links Only
# ============================================================

DB_FILE = "link_history.db"

def init_db():
    """Initialize database to track links"""
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
    """Save link data and check for duplicates"""
    try:
        pc_link = data.get("pc_link")
        mobile_link = data.get("mobile_link")
        
        # Check if this link already exists
        is_duplicate = False
        duplicate_of = None
        
        if pc_link and mobile_link:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            # Check for duplicate PC link
            c.execute("SELECT id, request_number FROM links WHERE pc_link = ?", (pc_link,))
            pc_result = c.fetchone()
            
            # Check for duplicate Mobile link
            c.execute("SELECT id, request_number FROM links WHERE mobile_link = ?", (mobile_link,))
            mobile_result = c.fetchone()
            
            if pc_result or mobile_result:
                is_duplicate = True
                # Use the first duplicate found
                if pc_result:
                    duplicate_of = pc_result[0]
                elif mobile_result:
                    duplicate_of = mobile_result[0]
            
            # Insert the new record
            c.execute("""INSERT INTO links 
                         (timestamp, request_number, plan, country, 
                          pc_link, mobile_link, is_duplicate, duplicate_of)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                      (datetime.now().isoformat(), 
                       request_number,
                       data.get("plan", "Unknown"),
                       data.get("country", "Unknown"),
                       pc_link,
                       mobile_link,
                       is_duplicate,
                       duplicate_of))
            
            conn.commit()
            conn.close()
            
            return is_duplicate, duplicate_of
        
        return False, None
    except Exception as e:
        st.error(f"Failed to save: {e}")
        return False, None

def get_link_stats():
    """Get statistics about links"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Total requests
        c.execute("SELECT COUNT(*) FROM links")
        total = c.fetchone()[0]
        
        # Unique links
        c.execute("SELECT COUNT(DISTINCT pc_link) FROM links WHERE pc_link IS NOT NULL")
        unique = c.fetchone()[0]
        
        # Duplicate count
        c.execute("SELECT COUNT(*) FROM links WHERE is_duplicate = 1")
        duplicates = c.fetchone()[0]
        
        # Get last 5 requests
        c.execute("""SELECT id, timestamp, request_number, plan, country, 
                     pc_link, mobile_link, is_duplicate, duplicate_of 
                     FROM links ORDER BY id DESC LIMIT 5""")
        recent = c.fetchall()
        
        conn.close()
        return total, unique, duplicates, recent
    except:
        return 0, 0, 0, []

def get_duplicate_details(duplicate_of_id):
    """Get details of the original link"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT request_number, timestamp, plan, country FROM links WHERE id = ?", (duplicate_of_id,))
        result = c.fetchone()
        conn.close()
        return result
    except:
        return None

def clear_history():
    """Clear all link history"""
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
    """Original synchronous method - kept for fallback"""
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
# Display Link Status (NEW - Duplicate Detection)
# ============================================================

def display_link_status():
    """Show link statistics and duplicate detection"""
    
    total, unique, duplicates, recent = get_link_stats()
    
    st.divider()
    st.subheader("🔗 Link Status")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Requests", total)
    
    with col2:
        st.metric("Unique Links", unique, delta=f"+{unique}" if unique > 0 else "0")
    
    with col3:
        duplicate_percentage = (duplicates / total * 100) if total > 0 else 0
        st.metric("Duplicate Links", duplicates, 
                  delta=f"{duplicate_percentage:.1f}%" if duplicates > 0 else "0%")
    
    # Show recent requests with duplicate status
    if recent:
        st.write("**Last 5 Requests:**")
        for row in recent:
            id_num, timestamp, req_num, plan, country, pc_link, mobile_link, is_dup, dup_of = row
            
            # Determine status
            if is_dup:
                status = "🔄 DUPLICATE"
                color = "orange"
                # Get original request info
                original = get_duplicate_details(dup_of)
                if original:
                    orig_req, orig_time, orig_plan, orig_country = original
                    detail = f"(Same as Request #{orig_req} from {orig_time[:10]})"
                else:
                    detail = ""
            else:
                status = "✅ NEW LINK"
                color = "green"
                detail = ""
            
            # Display with color coding
            col1, col2, col3, col4 = st.columns([1, 2, 2, 3])
            with col1:
                st.write(f"**#{req_num}**")
            with col2:
                st.write(f"🕐 {timestamp[11:16]}")
            with col3:
                st.write(f"{plan} | {country}")
            with col4:
                if is_dup:
                    st.warning(f"🔄 DUPLICATE {detail}")
                else:
                    st.success("✅ NEW LINK")
    
    # Add clear history button
    if total > 0:
        if st.button("🗑️ Clear History", key="clear_history"):
            if clear_history():
                st.success("History cleared!")
                st.rerun()

# ============================================================
# Display API Result (Modified with duplicate detection)
# ============================================================

def display_result(data, is_duplicate=False, duplicate_of=None):
    """Display API result with duplicate detection"""
    
    st.divider()
    
    # Show duplicate status first (most important)
    if is_duplicate:
        st.warning("⚠️ **This is a DUPLICATE link!**")
        if duplicate_of:
            original = get_duplicate_details(duplicate_of)
            if original:
                orig_req, orig_time, orig_plan, orig_country = original
                st.info(f"📌 This link was first seen in Request #{orig_req} on {orig_time[:10]}")
        st.info("💡 The backend is giving you the SAME link again!")
    else:
        st.success("🎉 **This is a FRESH NEW link!**")
        st.info("💡 The backend gave you a UNIQUE link that hasn't been seen before!")
    
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
# Dashboard Page (Modified - Advanced Mode Only)
# ============================================================

def dashboard_page():
    """Displays the dashboard with duplicate detection - Advanced Mode Only"""
    
    # Initialize database if not already done
    if "db_initialized" not in st.session_state:
        if init_db():
            st.session_state["db_initialized"] = True
    
    st.title(f"🔗 {APP_NAME}")
    st.info(f"Running Version: {APP_VERSION}")
    st.caption("Generate and track links - Advanced Mode with Duplicate Detection")
    
    # Display link status
    display_link_status()
    
    # Check if advanced mode is available
    if not BEAUTIFULSOUP_AVAILABLE:
        st.warning("⚠️ BeautifulSoup not available. Please install: pip install beautifulsoup4")
    
    # Single button for Advanced Mode only
    if st.button("🚀 Generate & Check Link", use_container_width=True, type="primary"):
        st.session_state.pop("gateway_result", None)
        st.session_state.pop("is_duplicate", None)
        st.session_state.pop("duplicate_of", None)

        try:
            with st.spinner("Launching batch workers for link validation..."):
                result = call_gateway_async()
                
                if result:
                    st.session_state["gateway_result"] = result
                    
                    # Check for duplicates
                    request_num = get_link_stats()[0] + 1
                    is_dup, dup_of = save_link_data(result, request_num)
                    
                    st.session_state["is_duplicate"] = is_dup
                    st.session_state["duplicate_of"] = dup_of
                    
                    if is_dup:
                        st.warning("🔄 DUPLICATE DETECTED! The backend gave the same link again.")
                    else:
                        st.balloons()
                        st.success("🎉 FRESH NEW LINK! The backend gave a unique link!")
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
    
    # Show result after successful API call
    if "gateway_result" in st.session_state:
        display_result(
            st.session_state["gateway_result"],
            st.session_state.get("is_duplicate", False),
            st.session_state.get("duplicate_of", None)
        )

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
