import streamlit as st
import requests


st.set_page_config(
    page_title="Gateway Dashboard",
    page_icon="🔗",
    layout="centered"
)


def call_gateway():
    api_url = st.secrets["gateway"]["api_url"]
    auth_key = st.secrets["gateway"]["auth_key"]

    headers = {
        "Authorization": f"Bearer {auth_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(api_url, headers=headers, timeout=30)
    response.raise_for_status()

    data = response.json()

    if not data.get("success"):
        raise Exception(data.get("message", "Unknown error from API"))

    return data


def login_page():
    st.title("Gateway Dashboard Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        correct_username = st.secrets["auth"]["username"]
        correct_password = st.secrets["auth"]["password"]

        if username == correct_username and password == correct_password:
            st.session_state["logged_in"] = True
            st.rerun()
        else:
            st.error("Invalid username or password")


def dashboard_page():
    st.title("🔗 Gateway Dashboard")

    st.write("Click the button below to generate links.")

    if st.button("Request"):
        try:
            with st.spinner("Generating links..."):
                data = call_gateway()
                st.session_state["links"] = data

            st.success("Request successful")

        except requests.exceptions.HTTPError as e:
            st.error(f"HTTP error: {e}")

        except requests.exceptions.RequestException as e:
            st.error(f"Request failed: {e}")

        except Exception as e:
            st.error(f"Error: {e}")

    if "links" in st.session_state:
        data = st.session_state["links"]

        st.subheader("Result")

        st.write(f"**Plan:** {data.get('plan', 'Premium')}")
        st.write(f"**Country:** {data.get('country', 'Unknown')}")

        st.write("**Desktop Link:**")
        st.code(data.get("pc_link", "N/A"))

        st.write("**Mobile Link:**")
        st.code(data.get("mobile_link", "N/A"))

    st.divider()

    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()


def main():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if st.session_state["logged_in"]:
        dashboard_page()
    else:
        login_page()


if __name__ == "__main__":
    main()
