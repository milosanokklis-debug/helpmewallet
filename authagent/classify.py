"""Heuristic form classifier: signup / login / other. Pure functions over extracted form dicts."""
import re

SIGNUP_WORDS = re.compile(r"sign[\s-]?up|register|create (an )?account|join|get started|confirm (your )?password|new account", re.I)
LOGIN_WORDS = re.compile(r"log[\s-]?in|sign[\s-]?in|welcome back|forgot (your )?password", re.I)
SIGNUP_URL = re.compile(r"register|signup|sign-up|join|create", re.I)
LOGIN_URL = re.compile(r"login|log-in|signin|sign-in", re.I)
CONFIRM = re.compile(r"confirm|repeat|retype|again", re.I)
PROFILE_AC = ("name", "given-name", "family-name", "new-password")


def _blob(f):
    return " ".join(str(f.get(k) or "") for k in ("name", "id", "aria_label", "label", "placeholder"))


def classify_form(form, url=""):
    """Return {'kind', 'signup_score', 'login_score', 'reasons'}. form = dict from the extractor."""
    fields = form.get("fields", [])
    pw = [f for f in fields if f.get("type") == "password"]
    text = " ".join([form.get("text", ""), " ".join(form.get("buttons", [])), form.get("aria_label") or ""])
    score = {"signup": 0, "login": 0}
    why = []

    def add(kind, n, reason):
        score[kind] += n
        why.append(f"{kind}+{n}:{reason}")

    if len(pw) >= 2:
        add("signup", 3, "2+ password fields")
    elif len(pw) == 1:
        add("login", 1, "single password field")
    for f in pw:
        ac = (f.get("autocomplete") or "").lower()
        if ac == "new-password":
            add("signup", 3, "autocomplete new-password")
        elif ac == "current-password":
            add("login", 3, "autocomplete current-password")
        if CONFIRM.search(_blob(f)):
            add("signup", 2, "confirm-password field")
    if any((f.get("autocomplete") or "").lower() in PROFILE_AC for f in fields if f.get("type") != "password"):
        add("signup", 1, "profile autocomplete")
    if len([f for f in fields if f.get("type") in ("text", "email", "tel")]) >= 3:
        add("signup", 1, "3+ text-like fields")
    if SIGNUP_WORDS.search(text):
        add("signup", 2, "signup wording")
    if LOGIN_WORDS.search(text):
        add("login", 2, "login wording")
    path = re.sub(r"^\w+://[^/]+", "", url or "")
    if SIGNUP_URL.search(path):
        add("signup", 2, "signup URL hint")
    if LOGIN_URL.search(path):
        add("login", 2, "login URL hint")
    s, l = score["signup"], score["login"]
    kind = "signup" if s > l and s >= 3 else "login" if l > s and l >= 3 else "other"
    return {"kind": kind, "signup_score": s, "login_score": l, "reasons": why}
