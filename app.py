import streamlit as st
import requests

# ────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Gateway Dashboard", page_icon="🔗", layout="centered")

# ────────────────────────────────────────────────────────────────
# SESSION STATE INIT
# Everything lives here only for the current browser session.
# Nothing is written to disk or a database — closing the tab or
# logging out wipes it all, which is exactly what you asked for.
# ────────────────────────────────────────────────────────────────
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "links" not in st.session_state:
    st.session_state.links = []


# ────────────────────────────────────────────────────────────────
# >>> PLACEHOLDER: YOUR GATEWAY CALL GOES HERE <<<
# Replace the body of this function with your actual Python logic
# that sends the request to your gateway using the auth key and
# returns the list of links from the response.
# ────────────────────────────────────────────────────────────────
def call_gateway():
    """
    Example of what this will probably look like — edit freely.

    auth_key = st.secrets["gateway"]["auth_key"]
    resp = requests.post(
        "https://your-gateway-url.example.com/reset",
        headers={"Authorization": f"Bearer {auth_key}"},
        json={"some": "payload"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["links"]   # <-- adjust to match your actual response shape
    """
    # Dummy placeholder response so the app runs end-to-end right now.
    return [
        "https://example.com/reset-link-1",
        "https://example.com/reset-link-2",
    ]


# ────────────────────────────────────────────────────────────────
# LOGIN PAGE
# ────────────────────────────────────────────────────────────────
def login_page():
    st.title("🔐 Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

        if submitted:
            correct_user = st.secrets["auth"]["username"]
            correct_pass = st.secrets["auth"]["password"]
            if username == correct_user and password == correct_pass:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Invalid username or password")


# ────────────────────────────────────────────────────────────────
# DASHBOARD PAGE
# ────────────────────────────────────────────────────────────────
def dashboard_page():
    top_left, top_right = st.columns([4, 1])
    with top_left:
        st.title("📊 Dashboard")
    with top_right:
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.links = []   # wipe links immediately on logout
            st.rerun()

    st.write("Click the button below to trigger the gateway request.")

    if st.button("🚀 Request", type="primary"):
        with st.spinner("Contacting gateway..."):
            try:
                st.session_state.links = call_gateway()
                st.success("Request completed.")
            except Exception as e:
                st.error(f"Request failed: {e}")

    if st.session_state.links:
        st.subheader("Links")
        for link in st.session_state.links:
            # st.code() renders a built-in copy icon in the top-right
            # corner of the block — no extra JS needed.
            st.code(link, language=None)
    else:
        st.info("No links yet. Click Request to generate some.")


# ────────────────────────────────────────────────────────────────
# ROUTER
# ────────────────────────────────────────────────────────────────
if st.session_state.logged_in:
    dashboard_page()
else:
    login_page()
