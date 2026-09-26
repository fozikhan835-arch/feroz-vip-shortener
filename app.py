import os
import re
import secrets
import sqlite3
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Flask, abort, flash, redirect, render_template_string,
    request, session, url_for, send_from_directory
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

APP_NAME = "FEROZ KHKSA VIP SHORTNER"

# ================= ADMIN SETTINGS =================
# Change these BEFORE first run.
ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "+923216950394")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ferozkhan!")

# Set this to your real public domain after deployment, e.g.
# https://short.example.com
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

DB_FILE = Path(__file__).with_name("shortener.db")
UPLOAD_DIR = Path(__file__).with_name("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}

def db():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            destination TEXT NOT NULL,
            title TEXT,
            description TEXT,
            image TEXT,
            clicks INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.commit()
    con.close()

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def valid_url(value):
    try:
        p = urlparse(value)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

def make_code(length=7):
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    con = db()
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(length))
        if not con.execute("SELECT 1 FROM links WHERE code=?", (code,)).fetchone():
            con.close()
            return code

def public_url(code):
    base = PUBLIC_BASE_URL or request.host_url.rstrip("/")
    return f"{base}/{code}"

CSS = """
<style>
*{box-sizing:border-box}
body{margin:0;font-family:Arial,sans-serif;background:#f3f5f9;color:#18202a}
.top{background:#111827;color:white;padding:18px 22px;display:flex;justify-content:space-between;align-items:center}
.brand{font-weight:800;font-size:20px}
.wrap{max-width:1050px;margin:28px auto;padding:0 16px}
.card{background:white;border-radius:16px;padding:22px;box-shadow:0 5px 25px #00000012;margin-bottom:18px}
h1,h2{margin-top:0}
input,textarea{width:100%;padding:13px;border:1px solid #d5dae2;border-radius:10px;margin:7px 0 15px;font-size:15px}
textarea{min-height:100px;resize:vertical}
button,.btn{display:inline-block;border:0;border-radius:10px;padding:12px 17px;background:#111827;color:white;text-decoration:none;cursor:pointer;font-weight:700}
.btn.red{background:#dc2626}.btn.green{background:#16a34a}.muted{color:#667085}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:15px}
table{width:100%;border-collapse:collapse}th,td{padding:12px 8px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}
.code{font-family:monospace;word-break:break-all}
.alert{padding:12px;border-radius:10px;background:#fff7ed;color:#9a3412;margin-bottom:15px}
.stat{font-size:28px;font-weight:800}
.small{font-size:13px}
@media(max-width:700px){.grid{grid-template-columns:1fr}table{font-size:13px}.hide-mobile{display:none}}
</style>
"""

LOGIN = CSS + """
<div class="wrap" style="max-width:450px;margin-top:70px">
<div class="card">
<h1>{{ name }}</h1>
<p class="muted">Private admin access — public registration is disabled.</p>
{% with msgs=get_flashed_messages() %}{% for m in msgs %}<div class="alert">{{m}}</div>{% endfor %}{% endwith %}
<form method="post">
<label>Admin phone</label>
<input name="phone" type="tel" required autocomplete="username">
<label>Password</label>
<input name="password" type="password" required autocomplete="current-password">
<button type="submit">Login</button>
</form>
</div></div>
"""

DASH = CSS + """
<div class="top"><div class="brand">{{name}}</div><a class="btn" href="{{url_for('logout')}}">Logout</a></div>
<div class="wrap">
{% with msgs=get_flashed_messages() %}{% for m in msgs %}<div class="alert">{{m}}</div>{% endfor %}{% endwith %}
<div class="grid">
<div class="card"><div class="muted">Total links</div><div class="stat">{{links|length}}</div></div>
<div class="card"><div class="muted">Total clicks</div><div class="stat">{{total_clicks}}</div></div>
</div>
<div class="card">
<h2>Create New Link</h2>
<form method="post" action="{{url_for('create')}}">
<label>Destination URL *</label>
<input name="destination" placeholder="https://example.com/page" required>
<div class="grid">
<div><label>Custom Short Code (optional)</label><input name="code" placeholder="my-link"></div>
<div><label>Preview Title</label><input name="title" placeholder="My website"></div>
</div>
<label>Preview Description</label>
<textarea name="description" placeholder="Description shown in social previews"></textarea>
<label>Preview Image URL</label>
<input name="image" placeholder="https://example.com/image.jpg">
<p class="muted small">For Facebook/WhatsApp previews, the image URL must be publicly reachable over HTTPS.</p>
<button class="green" type="submit">Create Short Link</button>
</form>
</div>
<div class="card">
<h2>Your Links</h2>
{% if links %}
<table><tr><th>Short URL</th><th>Destination</th><th>Clicks</th><th>Action</th></tr>
{% for x in links %}
<tr>
<td><a class="code" href="{{public_url(x['code'])}}" target="_blank">{{public_url(x['code'])}}</a><br><span class="muted small">{{x['title'] or ''}}</span></td>
<td class="code">{{x['destination']}}</td>
<td>{{x['clicks']}}</td>
<td><form method="post" action="{{url_for('delete', link_id=x['id'])}}" onsubmit="return confirm('Delete this link?')"><button class="red">Delete</button></form></td>
</tr>
{% endfor %}</table>
{% else %}<p class="muted">No links yet.</p>{% endif %}
</div>
</div>
"""

PREVIEW = CSS + """
<!doctype html><html><head>
<meta charset="utf-8">
<meta property="og:type" content="website">
<meta property="og:url" content="{{short_url}}">
<meta property="og:title" content="{{title}}">
<meta property="og:description" content="{{description}}">
{% if image %}<meta property="og:image" content="{{image}}">{% endif %}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{{title}}">
<meta name="twitter:description" content="{{description}}">
{% if image %}<meta name="twitter:image" content="{{image}}">{% endif %}
<meta http-equiv="refresh" content="0;url={{destination}}">
<script>location.replace({{destination|tojson}});</script>
<title>{{title}}</title>
</head><body>
<div class="wrap"><div class="card"><h2>Opening link…</h2><p>If you are not redirected, <a href="{{destination}}">tap here</a>.</p></div></div>
</body></html>
"""

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        if phone == ADMIN_PHONE and password == ADMIN_PASSWORD:
            session.clear()
            session["admin"] = True
            return redirect(url_for("dashboard"))
        flash("Invalid admin phone or password.")
    return render_template_string(LOGIN, name=APP_NAME)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def dashboard():
    return redirect(url_for("dashboard") if session.get("admin") else url_for("login"))

@app.route("/dashboard")
@admin_required
def dashboard():
    con = db()
    links = con.execute("SELECT * FROM links ORDER BY id DESC").fetchall()
    total = con.execute("SELECT COALESCE(SUM(clicks),0) AS n FROM links").fetchone()["n"]
    con.close()
    return render_template_string(DASH, name=APP_NAME, links=links,
                                  total_clicks=total, public_url=public_url)

@app.route("/create", methods=["POST"])
@admin_required
def create():
    destination = request.form.get("destination", "").strip()
    code = request.form.get("code", "").strip()
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    image = request.form.get("image", "").strip()

    if not valid_url(destination):
        flash("Destination must be a valid http:// or https:// URL.")
        return redirect(url_for("dashboard"))

    if code:
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,40}", code):
            flash("Short code: 3-40 characters, only letters, numbers, _ and -.")
            return redirect(url_for("dashboard"))
    else:
        code = make_code()

    con = db()
    try:
        con.execute(
            "INSERT INTO links(code,destination,title,description,image) VALUES(?,?,?,?,?)",
            (code, destination, title, description, image)
        )
        con.commit()
    except sqlite3.IntegrityError:
        con.close()
        flash("That short code is already in use.")
        return redirect(url_for("dashboard"))
    con.close()
    flash("Short link created: " + public_url(code))
    return redirect(url_for("dashboard"))

@app.route("/delete/<int:link_id>", methods=["POST"])
@admin_required
def delete(link_id):
    con = db()
    con.execute("DELETE FROM links WHERE id=?", (link_id,))
    con.commit()
    con.close()
    flash("Link deleted.")
    return redirect(url_for("dashboard"))

@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.route("/<code>")
def short_link(code):
    # Reserve application paths.
    if code in {"login", "logout", "dashboard", "create", "delete", "uploads"}:
        abort(404)

    con = db()
    row = con.execute("SELECT * FROM links WHERE code=?", (code,)).fetchone()
    if not row:
        con.close()
        abort(404)

    con.execute("UPDATE links SET clicks=clicks+1 WHERE id=?", (row["id"],))
    con.commit()
    con.close()

    title = row["title"] or APP_NAME
    description = row["description"] or "You are being redirected."
    image = row["image"] or ""
    return render_template_string(
        PREVIEW,
        destination=row["destination"],
        title=title,
        description=description,
        image=image,
        short_url=public_url(code)
    )

if __name__ == "__main__":
    init_db()
    print("=" * 60)
    print(APP_NAME)
    print("Admin phone:", ADMIN_PHONE)
    print("Change ADMIN_PASSWORD before putting this online.")
    print("Local: http://127.0.0.1:5000/login")
    print("=" * 60)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
