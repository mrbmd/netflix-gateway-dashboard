# Gateway Dashboard

A minimal Streamlit app: login → dashboard → "Request" button → triggers your
gateway call → shows links with one-click copy → everything clears on logout
or when the session ends. Nothing is saved to a database.

## Files

- `app.py` — the whole app
- `requirements.txt` — dependencies
- `.streamlit/secrets.toml.example` — template for your login + auth key (copy → `secrets.toml`, never commit the real one)
- `.gitignore` — keeps `secrets.toml` out of git

## 1. Fill in your gateway logic

Open `app.py` and edit the `call_gateway()` function. Replace the placeholder
`return [...]` with your real request, e.g.:

```python
def call_gateway():
    auth_key = st.secrets["gateway"]["auth_key"]
    resp = requests.post(
        "https://your-gateway-url.example.com/reset",
        headers={"Authorization": f"Bearer {auth_key}"},
        json={"some": "payload"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["links"]
```

Adjust the URL, headers, payload, and response parsing to match your actual
gateway.

## 2. Test locally (optional but recommended)

```bash
cd gateway-dashboard
python3 -m venv venv
source venv/bin/activate        # on Mac/Linux
pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml with your real username/password/auth_key

streamlit run app.py
```

It'll open at `http://localhost:8501`.

## 3. Deploy for free on Streamlit Community Cloud

1. Push this folder to a **GitHub repo** (public or private is fine).
   - Make sure `.streamlit/secrets.toml` is NOT pushed (the `.gitignore`
     already excludes it) — only `secrets.toml.example` should be in git.
2. Go to **https://share.streamlit.io** and sign in with GitHub.
3. Click **"New app"**, pick your repo, branch, and set the main file to
   `app.py`.
4. Before (or after) deploying, open **App settings → Secrets** in the
   Streamlit Cloud dashboard and paste in the contents of your real
   `secrets.toml`, e.g.:

   ```toml
   [auth]
   username = "your-username"
   password = "your-strong-password"

   [gateway]
   auth_key = "your-gateway-auth-key"
   ```

5. Click **Deploy**. You'll get a free `https://your-app-name.streamlit.app`
   URL you can share or bookmark.

## Notes on your requirements

- **Login**: single shared username/password, checked against Streamlit
  secrets (not hardcoded in code, not stored in a database).
- **Copy button**: `st.code()` renders each link in a box with a built-in
  copy icon — no custom JS needed.
- **Auto-clearing links**: links live only in `st.session_state`, which is
  per-browser-session. Clicking **Logout** wipes them immediately; closing
  the tab or letting the session time out also clears them since nothing is
  persisted to disk or a database.
