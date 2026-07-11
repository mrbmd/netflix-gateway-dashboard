import requests
import streamlit as st


# ============================================================
# Application Information
# ============================================================

APP_NAME = "Gateway Dashboard"
APP_VERSION = "v3"
REQUEST_TIMEOUT = 30


# ============================================================
# Streamlit Page Configuration
# ============================================================

st.set_page_config(
    page_title=f"{APP_NAME} {APP_VERSION}",
    page_icon="🔗",
    layout="centered",
)


# ============================================================
# Call Gateway API
# ============================================================

def call_gateway():
    """
    Reads the API URL and authentication key from Streamlit
    Secrets, sends a POST request, and returns the API response.
    """

    # Read private values from Streamlit Secrets
    api_url = st.secrets["gateway"]["api_url"]
    auth_key = st.secrets["gateway"]["auth_key"]

    # API authentication headers
    headers = {
        "Authorization": f"Bearer {auth_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Send request to the gateway API
    response = requests.post(
        api_url,
        headers=headers,
        json={},
        timeout=REQUEST_TIMEOUT,
    )

    # Handle API authentication failures
    if response.status_code in (401, 403):
        try:
            error_data = response.json()
            error_message = error_data.get(
                "message",
                "API authentication failed.",
            )
        except ValueError:
            error_message = "API authentication failed."

        raise PermissionError(error_message)

    # Raise error for other failed HTTP responses
    response.raise_for_status()

    # Convert the API response into JSON
    try:
        data = response.json()
    except ValueError as error:
        raise ValueError(
            "The API returned an invalid JSON response."
        ) from error

    # Check API success value
    if not data.get("success"):
        raise ValueError(
            data.get("message", "The API request failed.")
        )

    return data


# ============================================================
# Login Page
# ============================================================

def login_page():
    """
    Displays the login page and checks the entered credentials
    against values stored in Streamlit Secrets.
    """

    st.title(f"🔐 {APP_NAME}")
    st.info(f"Running Version: {APP_VERSION}")
    st.caption("Sign in to access the dashboard.")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        login_clicked = st.form_submit_button(
            "Login",
            use_container_width=True,
        )

    if login_clicked:
        correct_username = st.secrets["auth"]["username"]
        correct_password = st.secrets["auth"]["password"]

        if (
            username == correct_username
            and password == correct_password
        ):
            st.session_state["logged_in"] = True
            st.rerun()
        else:
            st.error("Invalid username or password.")


# ============================================================
# Display API Result
# ============================================================

def display_result(data):
    """
    Displays the API response returned by the gateway.
    """

    st.divider()

    st.success(
        data.get("message", "Links generated successfully.")
    )

    plan_column, country_column = st.columns(2)

    with plan_column:
        st.metric(
            label="Plan",
            value=data.get("plan", "Unknown"),
        )

    with country_column:
        st.metric(
            label="Country",
            value=data.get("country", "Unknown"),
        )

    # Desktop link
    st.write("### 💻 Desktop Link")

    pc_link = data.get("pc_link")

    if pc_link:
        st.code(
            pc_link,
            language=None,
            wrap_lines=True,
        )
    else:
        st.warning("Desktop link was not returned by the API.")

    # Mobile link
    st.write("### 📱 Mobile Link")

    mobile_link = data.get("mobile_link")

    if mobile_link:
        st.code(
            mobile_link,
            language=None,
            wrap_lines=True,
        )
    else:
        st.warning("Mobile link was not returned by the API.")


# ============================================================
# Dashboard Page
# ============================================================

def dashboard_page():
    """
    Displays the main dashboard after successful login.
    """

    st.title(f"🔗 {APP_NAME}")
    st.info(f"Running Version: {APP_VERSION}")
    st.caption("Generate desktop and mobile links.")

    if st.button(
        "🔗 Generate Links",
        use_container_width=True,
        type="primary",
    ):
        # Remove old result before sending a new request
        st.session_state.pop("gateway_result", None)

        try:
            with st.spinner("Sending request to the gateway..."):
                result = call_gateway()

            # Store result only in the current browser session
            st.session_state["gateway_result"] = result

        except PermissionError as error:
            st.error(f"Authentication error: {error}")

        except requests.exceptions.Timeout:
            st.error(
                "The API request timed out. Please try again."
            )

        except requests.exceptions.ConnectionError:
            st.error(
                "Could not connect to the API server."
            )

        except requests.exceptions.HTTPError as error:
            status_code = (
                error.response.status_code
                if error.response is not None
                else "Unknown"
            )

            st.error(
                f"The API returned HTTP status {status_code}."
            )

        except ValueError as error:
            st.error(str(error))

        except requests.exceptions.RequestException as error:
            st.error(f"Request failed: {error}")

        except Exception as error:
            st.error(f"Unexpected error: {error}")

    # Show result after successful API call
    if "gateway_result" in st.session_state:
        display_result(
            st.session_state["gateway_result"]
        )

    st.divider()

    if st.button(
        "Logout",
        use_container_width=True,
    ):
        # Clear login and API result from session
        st.session_state.clear()
        st.rerun()


# ============================================================
# Main Application Flow
# ============================================================

def main():
    """
    Shows either the login page or dashboard based on the
    current session state.
    """

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
