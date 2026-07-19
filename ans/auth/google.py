import json
import urllib.parse
import urllib.request
from functools import wraps
from flask import session, redirect, url_for
from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, OWNER_EMAIL
from ans.data.storage import load_users, save_users


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def owner_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = session.get("user", {})
        if user.get("email") != OWNER_EMAIL:
            return redirect(url_for("hm"))
        return f(*args, **kwargs)
    return decorated


def is_owner():
    return session.get("user", {}).get("email") == OWNER_EMAIL


def exchange_code_for_token(code):
    try:
        redirect_uri = session.pop("google_redirect_uri", None) or GOOGLE_REDIRECT_URI
        data = urllib.parse.urlencode({
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }).encode()
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Token exchange error: {e}")
        return None


def get_google_user_info(access_token):
    try:
        req = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
