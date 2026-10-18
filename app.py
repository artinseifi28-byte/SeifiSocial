from flask import (
    Flask, request, redirect, session,
    render_template_string, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
import secrets
import uuid
import re

app = Flask(__name__)

# Development configuration.
# Set SECRET_KEY to a long random value before public deployment.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "social.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}


# ---------------- DATABASE ----------------

def connect():
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    with connect() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                image TEXT NOT NULL,
                caption TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS likes (
                user_id INTEGER NOT NULL,
                post_id INTEGER NOT NULL,
                UNIQUE(user_id, post_id),
                FOREIGN KEY(user_id) REFERENCES users(id)
                    ON DELETE CASCADE,
                FOREIGN KEY(post_id) REFERENCES posts(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                post_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
                    ON DELETE CASCADE,
                FOREIGN KEY(post_id) REFERENCES posts(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS follows (
                follower_id INTEGER NOT NULL,
                followed_id INTEGER NOT NULL,
                UNIQUE(follower_id, followed_id),
                CHECK(follower_id != followed_id),
                FOREIGN KEY(follower_id) REFERENCES users(id)
                    ON DELETE CASCADE,
                FOREIGN KEY(followed_id) REFERENCES users(id)
                    ON DELETE CASCADE
            );
        """)


init_db()


# ---------------- DESIGN ----------------

PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>SEIFI SOCIAL</title>

<style>
* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: #080d18;
    color: #edf3ff;
    font-family: Arial, sans-serif;
}

header {
    background: #0d1526;
    padding: 22px 15px;
    text-align: center;
    border-bottom: 1px solid #20324f;
}

.logo {
    color: #38a5ff;
    font-size: 30px;
    font-weight: bold;
    letter-spacing: 1px;
}

.subtitle {
    color: #91a8c8;
    margin-top: 7px;
    font-size: 12px;
}

nav {
    margin-top: 20px;
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 18px;
}

a {
    color: #58b4ff;
    text-decoration: none;
}

nav a {
    color: #d4e6ff;
}

a:hover {
    color: #75c6ff;
}

main {
    max-width: 650px;
    margin: 30px auto;
    padding: 0 15px;
    min-height: 60vh;
}

.card {
    background: #101a2c;
    border: 1px solid #243752;
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 20px;
    overflow-wrap: anywhere;
}

h2 {
    color: #58b4ff;
}

input, textarea {
    display: block;
    width: 100%;
    margin: 12px 0;
    padding: 13px;
    border: 1px solid #304765;
    border-radius: 9px;
    background: #091222;
    color: white;
    font-size: 15px;
}

textarea {
    min-height: 90px;
    resize: vertical;
}

button, .button {
    display: inline-block;
    padding: 11px 17px;
    border: none;
    border-radius: 9px;
    background: #1688ef;
    color: white;
    cursor: pointer;
    font-weight: bold;
    font-size: 14px;
}

button:hover, .button:hover {
    background: #0871d0;
    color: white;
}

.post-image {
    display: block;
    width: 100%;
    max-height: 550px;
    object-fit: contain;
    border-radius: 10px;
    background: #080d18;
}

.muted {
    color: #91a2bc;
    font-size: 14px;
}

.error {
    color: #ff8a8a;
}

.success {
    color: #65e5ad;
}

.username {
    font-weight: bold;
    font-size: 17px;
}

.actions {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin: 15px 0;
}

.comment {
    padding: 10px 0;
    border-bottom: 1px solid #26354c;
}

footer {
    text-align: center;
    padding: 25px;
    color: #71839e;
}

hr {
    border: 0;
    border-top: 1px solid #26354c;
    margin: 18px 0;
}
</style>
</head>

<body>

<header>
    <div class="logo">SEIFI SOCIAL</div>
    <div class="subtitle">YOUR WORLD. YOUR COMMUNITY.</div>

    <nav>
        <a href="/">Home</a>

        {% if user %}
            <a href="/profile/{{ user['id'] }}">My Profile</a>
            <a href="/explore">Explore</a>
            <a href="/logout">Log out</a>
        {% else %}
            <a href="/login">Log in</a>
            <a href="/register">Sign up</a>
        {% endif %}
    </nav>
</header>

<main>

{% if message %}
    <div class="card {{ message_type }}">
        {{ message }}
    </div>
{% endif %}


{% if page == 'home' %}

    {% if user %}
    <div class="card">
        <h2>Welcome back, {{ user['username'] }}!</h2>
        <p class="muted">Share something with your community.</p>

        <form action="/upload" method="post"
              enctype="multipart/form-data">

            <input type="hidden" name="csrf_token"
                   value="{{ csrf_token }}">

            <input type="file" name="image"
                   accept=".png,.jpg,.jpeg,.webp,.gif"
                   required>

            <textarea name="caption" maxlength="1000"
                      placeholder="Write a caption..."></textarea>

            <button type="submit">＋ Publish Post</button>
        </form>
    </div>
    {% else %}
    <div class="card">
        <h2>Your community starts here.</h2>
        <p>Share photos, discover people, and connect.</p>
        <br>
        <a class="button" href="/register">Create Account</a>
        <a class="button" href="/login">Log In</a>
    </div>
    {% endif %}

    <h2>Latest Posts</h2>

    {% for post in posts %}
    <div class="card">

        <a class="username"
           href="/profile/{{ post['user_id'] }}">
           @{{ post['username'] }}
        </a>

        <p class="muted">{{ post['created_at'] }}</p>

        <img class="post-image"
             src="/uploads/{{ post['image'] }}"
             alt="Post image">

        <p>{{ post['caption'] }}</p>

        <div class="actions">
            {% if user %}
            <form action="/like/{{ post['id'] }}" method="post">
                <input type="hidden" name="csrf_token"
                       value="{{ csrf_token }}">
                <button type="submit">
                    {% if post['liked'] %}❤️{% else %}🤍{% endif %}
                    {{ post['likes'] }}
                </button>
            </form>
            {% else %}
            <span>❤️ {{ post['likes'] }} likes</span>
            {% endif %}
        </div>

        <hr>
        <h3>Comments</h3>

        {% for comment in post['comments'] %}
        <div class="comment">
            <a href="/profile/{{ comment['user_id'] }}">
                @{{ comment['username'] }}
            </a>
            : {{ comment['text'] }}
        </div>
        {% endfor %}

        {% if user %}
        <form action="/comment/{{ post['id'] }}" method="post">
            <input type="hidden" name="csrf_token"
                   value="{{ csrf_token }}">
            <input name="text" maxlength="500"
                   placeholder="Write a comment..." required>
            <button type="submit">Comment</button>
        </form>
        {% endif %}

        {% if user and user['id'] == post['user_id'] %}
        <form action="/delete/{{ post['id'] }}" method="post">
            <input type="hidden" name="csrf_token"
                   value="{{ csrf_token }}">
            <button type="submit">Delete Post</button>
        </form>
        {% endif %}

    </div>
    {% else %}
    <div class="card">
        No posts yet. Be the first to share something!
    </div>
    {% endfor %}


{% elif page == 'register' or page == 'login' %}

    <div class="card">
        <h2>
            {% if page == 'register' %}
                Create Your Account
            {% else %}
                Welcome Back
            {% endif %}
        </h2>

        <form method="post">
            <input type="hidden" name="csrf_token"
                   value="{{ csrf_token }}">

            <input name="username"
                   placeholder="Username"
                   minlength="3" maxlength="24"
                   autocomplete="username" required>

            <input name="password" type="password"
                   placeholder="Password"
                   minlength="8" maxlength="128"
                   autocomplete="{% if page == 'register' %}new-password{% else %}current-password{% endif %}"
                   required>

            <button type="submit">
                {% if page == 'register' %}
                    Sign Up
                {% else %}
                    Log In
                {% endif %}
            </button>
        </form>

        {% if page == 'register' %}
        <p class="muted">
            Already have an account?
            <a href="/login">Log in</a>
        </p>
        <p class="muted">
            Username: letters, numbers, underscores and dots.
        </p>
        {% else %}
        <p class="muted">
            New here? <a href="/register">Create an account</a>
        </p>
        {% endif %}
    </div>


{% elif page == 'profile' %}

    <div class="card">
        <h2>@{{ profile['username'] }}</h2>

        <p class="muted">
            {{ posts|length }} posts ·
            {{ followers }} followers ·
            {{ following }} following
        </p>

        {% if user and user['id'] != profile['id'] %}
        <form action="/follow/{{ profile['id'] }}" method="post">
            <input type="hidden" name="csrf_token"
                   value="{{ csrf_token }}">
            <button type="submit">
                {% if is_following %}
                    Unfollow
                {% else %}
                    ＋ Follow
                {% endif %}
            </button>
        </form>
        {% endif %}
    </div>

    {% for post in posts %}
    <div class="card">
        <img class="post-image"
             src="/uploads/{{ post['image'] }}"
             alt="Post image">

        <p>{{ post['caption'] }}</p>
        <p class="muted">❤️ {{ post['likes'] }} likes</p>

        {% if user and user['id'] == profile['id'] %}
        <form action="/delete/{{ post['id'] }}" method="post">
            <input type="hidden" name="csrf_token"
                   value="{{ csrf_token }}">
            <button type="submit">Delete Post</button>
        </form>
        {% endif %}
    </div>
    {% else %}
    <div class="card">No posts published yet.</div>
    {% endfor %}


{% elif page == 'explore' %}

    <div class="card">
        <h2>Explore People</h2>

        <form method="get">
            <input name="q" value="{{ query }}"
                   placeholder="Search usernames...">
            <button type="submit">Search</button>
        </form>

        {% for person in people %}
        <p>
            <a href="/profile/{{ person['id'] }}">
                @{{ person['username'] }}
            </a>
        </p>
        {% else %}
        <p class="muted">No users found.</p>
        {% endfor %}
    </div>

{% endif %}

</main>

<footer>SEIFI SOCIAL · Made with 💙</footer>

</body>
</html>
"""


# ---------------- HELPERS ----------------

def current_user():
    uid = session.get("user_id")

    if not uid:
        return None

    with connect() as con:
        return con.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (uid,)
        ).fetchone()


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    return session["csrf_token"]


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        saved = session.get("csrf_token", "")

        if not saved or not secrets.compare_digest(sent, saved):
            return "Invalid or expired form. Refresh the page and try again.", 400


def render_page(page, message=None, message_type="error", **kwargs):
    user = current_user()
    posts = []

    with connect() as con:

        if page == "home":
            rows = con.execute("""
                SELECT
                    p.*,
                    u.username,
                    (SELECT COUNT(*) FROM likes l
                     WHERE l.post_id = p.id) AS likes
                FROM posts p
                JOIN users u ON u.id = p.user_id
                ORDER BY p.id DESC
            """).fetchall()

            for row in rows:
                post = dict(row)

                post["liked"] = False

                if user:
                    post["liked"] = bool(con.execute(
                        "SELECT 1 FROM likes WHERE user_id=? AND post_id=?",
                        (user["id"], post["id"])
                    ).fetchone())

                post["comments"] = [
                    dict(c) for c in con.execute("""
                        SELECT c.text, u.username, u.id AS user_id
                        FROM comments c
                        JOIN users u ON u.id = c.user_id
                        WHERE c.post_id = ?
                        ORDER BY c.id
                    """, (post["id"],)).fetchall()
                ]

                posts.append(post)

        elif page == "profile":
            rows = con.execute("""
                SELECT p.*,
                    (SELECT COUNT(*) FROM likes l
                     WHERE l.post_id=p.id) AS likes
                FROM posts p
                WHERE p.user_id=?
                ORDER BY p.id DESC
            """, (kwargs["profile"]["id"],)).fetchall()

            posts = [dict(r) for r in rows]

    return render_template_string(
        PAGE,
        page=page,
        user=user,
        posts=posts,
        message=message,
        message_type=message_type,
        csrf_token=csrf_token(),
        **kwargs
    )


# ---------------- HOME ----------------

@app.route("/")
def home():
    return render_page("home")


# ---------------- REGISTER ----------------

@app.route("/register", methods=["GET", "POST"])
def register():
    message = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not 3 <= len(username) <= 24:
            message = "Username must contain 3-24 characters."

        elif not re.fullmatch(r"[A-Za-z0-9_.]+", username):
            message = "Use English letters, numbers, dots or underscores."

        elif len(password) < 8:
            message = "Password must contain at least 8 characters."

        elif len(password) > 128:
            message = "Password is too long."

        else:
            try:
                hashed_password = generate_password_hash(password)

                with connect() as con:
                    con.execute(
                        "INSERT INTO users(username, password) VALUES (?, ?)",
                        (username, hashed_password)
                    )

                session.clear()
                session["user_id"] = None

                # Log the newly created user in automatically.
                with connect() as con:
                    account = con.execute(
                        "SELECT id FROM users WHERE username = ?",
                        (username,)
                    ).fetchone()

                session["user_id"] = account["id"]
                csrf_token()

                return redirect("/")

            except sqlite3.IntegrityError:
                message = "This username already exists. Try logging in."

    return render_page("register", message)


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    message = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        with connect() as con:
            account = con.execute(
                "SELECT id, username, password FROM users WHERE username = ?",
                (username,)
            ).fetchone()

        if account and check_password_hash(account["password"], password):
            session.clear()
            session["user_id"] = account["id"]
            csrf_token()
            return redirect("/")

        message = "Incorrect username or password."

    return render_page("login", message)


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------------- UPLOAD ----------------

@app.route("/upload", methods=["POST"])
def upload():
    user = current_user()

    if not user:
        return redirect("/login")

    file = request.files.get("image")
    caption = request.form.get("caption", "").strip()[:1000]

    if not file or not file.filename:
        return redirect("/")

    original = secure_filename(file.filename)

    if "." not in original:
        return "Invalid image filename.", 400

    extension = original.rsplit(".", 1)[1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        return "Unsupported image format.", 400

    filename = uuid.uuid4().hex + "." + extension
    filepath = os.path.join(UPLOAD_DIR, filename)

    file.save(filepath)

    with connect() as con:
        con.execute(
            "INSERT INTO posts(user_id, image, caption) VALUES (?, ?, ?)",
            (user["id"], filename, caption)
        )

    return redirect("/")


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    if secure_filename(filename) != filename:
        return "Invalid filename.", 400

    return send_from_directory(UPLOAD_DIR, filename)


# ---------------- LIKE ----------------

@app.route("/like/<int:post_id>", methods=["POST"])
def like(post_id):
    user = current_user()

    if not user:
        return redirect("/login")

    with connect() as con:
        exists = con.execute(
            "SELECT 1 FROM posts WHERE id = ?", (post_id,)
        ).fetchone()

        if not exists:
            return "Post not found.", 404

        liked = con.execute(
            "SELECT 1 FROM likes WHERE user_id=? AND post_id=?",
            (user["id"], post_id)
        ).fetchone()

        if liked:
            con.execute(
                "DELETE FROM likes WHERE user_id=? AND post_id=?",
                (user["id"], post_id)
            )
        else:
            con.execute(
                "INSERT OR IGNORE INTO likes(user_id, post_id) VALUES (?, ?)",
                (user["id"], post_id)
            )

    return redirect("/")


# ---------------- COMMENTS ----------------

@app.route("/comment/<int:post_id>", methods=["POST"])
def comment(post_id):
    user = current_user()

    if not user:
        return redirect("/login")

    text = request.form.get("text", "").strip()[:500]

    if text:
        with connect() as con:
            exists = con.execute(
                "SELECT 1 FROM posts WHERE id=?", (post_id,)
            ).fetchone()

            if exists:
                con.execute(
                    "INSERT INTO comments(user_id, post_id, text) VALUES (?, ?, ?)",
                    (user["id"], post_id, text)
                )

    return redirect("/")


# ---------------- FOLLOW ----------------

@app.route("/follow/<int:user_id>", methods=["POST"])
def follow(user_id):
    user = current_user()

    if not user:
        return redirect("/login")

    if user["id"] == user_id:
        return redirect(f"/profile/{user_id}")

    with connect() as con:
        target = con.execute(
            "SELECT id FROM users WHERE id=?", (user_id,)
        ).fetchone()

        if not target:
            return "User not found.", 404

        exists = con.execute(
            "SELECT 1 FROM follows WHERE follower_id=? AND followed_id=?",
            (user["id"], user_id)
        ).fetchone()

        if exists:
            con.execute(
                "DELETE FROM follows WHERE follower_id=? AND followed_id=?",
                (user["id"], user_id)
            )
        else:
            con.execute(
                "INSERT OR IGNORE INTO follows(follower_id, followed_id) VALUES (?, ?)",
                (user["id"], user_id)
            )

    return redirect(f"/profile/{user_id}")


# ---------------- PROFILE ----------------

@app.route("/profile/<int:user_id>")
def profile(user_id):
    with connect() as con:
        person = con.execute(
            "SELECT id, username FROM users WHERE id=?",
            (user_id,)
        ).fetchone()

        if not person:
            return "User not found.", 404

        followers = con.execute(
            "SELECT COUNT(*) FROM follows WHERE followed_id=?",
            (user_id,)
        ).fetchone()[0]

        following = con.execute(
            "SELECT COUNT(*) FROM follows WHERE follower_id=?",
            (user_id,)
        ).fetchone()[0]

        user = current_user()

        is_following = False

        if user:
            is_following = bool(con.execute(
                "SELECT 1 FROM follows WHERE follower_id=? AND followed_id=?",
                (user["id"], user_id)
            ).fetchone())

    return render_page(
        "profile",
        profile=person,
        followers=followers,
        following=following,
        is_following=is_following
    )


# ---------------- EXPLORE ----------------

@app.route("/explore")
def explore():
    query = request.args.get("q", "").strip()[:24]

    with connect() as con:
        people = con.execute(
            """
            SELECT id, username FROM users
            WHERE username LIKE ? ESCAPE '\\'
            ORDER BY username LIMIT 50
            """,
            ("%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",)
        ).fetchall()

    return render_page("explore", people=people, query=query)


# ---------------- DELETE POST ----------------

@app.route("/delete/<int:post_id>", methods=["POST"])
def delete_post(post_id):
    user = current_user()

    if not user:
        return redirect("/login")

    with connect() as con:
        post = con.execute(
            "SELECT * FROM posts WHERE id=? AND user_id=?",
            (post_id, user["id"])
        ).fetchone()

        if post:
            con.execute("DELETE FROM likes WHERE post_id=?", (post_id,))
            con.execute("DELETE FROM comments WHERE post_id=?", (post_id,))
            con.execute("DELETE FROM posts WHERE id=?", (post_id,))

            try:
                os.remove(os.path.join(UPLOAD_DIR, post["image"]))
            except OSError:
                pass

    return redirect(f"/profile/{user['id']}")


# ---------------- ERRORS ----------------

@app.errorhandler(413)
def too_large(error):
    return "Image too large. Maximum allowed size is 5 MB.", 413


if __name__ == "__main__":
    app.run(debug=True)