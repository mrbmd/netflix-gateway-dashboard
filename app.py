import requests
import streamlit as st

# ============================================================
# Streamlit Page Configuration
# ============================================================
st.set_page_config(
    page_title="Gateway Dashboard",
    page_icon="🔗",
    layout="centered",
)


# ============================================================
# Call Gateway API
# ------------------------------------------------------------
# Reads API URL and Auth Key from Streamlit Secrets
# Sends request to the Gateway
# Returns JSON response
# ============================================================
def call_gateway():
    api_url = st.secrets["gateway"]["api_url"]
    auth_key = st.secrets["gateway"]["auth_key"]

    headers = {
        "Authorization": f"Bearer {auth_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        api_url,
        headers=headers,
        json={},          # Add request body here if required later
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    # Check if API returned success
    if not data.get("success"):
        raise Exception(data.get("message", "Unknown error from API"))

    return data


# ============================================================
# Login Screen
# ------------------------------------------------------------
# Checks Username & Password stored in Streamlit Secrets
# If correct -> Open Dashboard
# ============================================================
def login_page():

    st.title("🔐 Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login", use_container_width=True):

        correct_username = st.secrets["auth"]["username"]
        correct_password = st.secrets["auth"]["password"]

        if username == correct_username and password == correct_password:

            st.session_state["logged_in"] = True
            st.rerun()

        else:
            st.error("Invalid username or password")


# ============================================================
# Dashboard
# ------------------------------------------------------------
# Main page after successful login
# Generates links from Gateway API
# Displays returned information
# ============================================================
def dashboard_page():

    st.title("🔗 Gateway Dashboard")
    st.caption("Generate desktop and mobile links")

    # --------------------------------------------------------
    # Generate Links Button
    # --------------------------------------------------------
    if st.button("🔗 Generate Links", use_container_width=True):

        try:

            with st.spinner("Generating links..."):

                # Call Gateway API
                data = call_gateway()

                # Save response in current browser session
                st.session_state["links"] = data

            st.success(data.get("message", "Links generated successfully"))

        except requests.exceptions.HTTPError as e:
            st.error(f"HTTP Error: {e}")

        except requests.exceptions.RequestException as e:
            st.error(f"Request Failed: {e}")

        except Exception as e:
            st.error(f"Error: {e}")

    # --------------------------------------------------------
    # Display Result
    # Only shown after Generate Links is clicked
    # --------------------------------------------------------
    if "links" in st.session_state:

        data = st.session_state["links"]

        st.divider()
        st.subheader("Result")

        # Display Plan & Country side by side
        col1, col2 = st.columns(2)

        with col1:
            st.metric("Plan", data.get("plan", "Premium"))

        with col2:
            st.metric("Country", data.get("country", "Unknown"))

        # Desktop Link
        st.write("### 💻 Desktop Link")
        st.code(data.get("pc_link", "N/A"))

        # Mobile Link
        st.write("### 📱 Mobile Link")
        st.code(data.get("mobile_link", "N/A"))

    # --------------------------------------------------------
    # Logout
    # Clears current session
    # --------------------------------------------------------
    st.divider()

    if st.button("Logout", use_container_width=True):

        st.session_state.clear()
        st.rerun()


# ============================================================
# Main Entry Point
# ------------------------------------------------------------
# Decides whether to show Login or Dashboard
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
