import requests
import streamlit as st

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
