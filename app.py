import os
import io
import base64
import sqlite3
import hashlib
import secrets
import colorsys
from datetime import datetime, timedelta

import streamlit as st
from PIL import Image, ImageDraw

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------
st.set_page_config(page_title="Aperture", page_icon="📷", layout="centered")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aperture.db")
STORY_LIFETIME_HOURS = 24
CURATED_SEEDS = [1015, 1025, 1043, 1062, 1074, 1080, 1084, 1069, 1035, 1041, 1057, 1067]
BADGE_PALETTE = ["#f4c744", "#e4572e", "#8a7628", "#5b8a72", "#4a6fa5", "#9a5b8a", "#3f8f8f"]


@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        bio TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS follows (
        follower_id INTEGER NOT NULL, followee_id INTEGER NOT NULL,
        UNIQUE(follower_id, followee_id)
    );
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        image_ref TEXT NOT NULL,
        location TEXT DEFAULT '',
        caption TEXT DEFAULT '',
        hashtags TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS likes (post_id INTEGER, user_id INTEGER, UNIQUE(post_id, user_id));
    CREATE TABLE IF NOT EXISTS saves (post_id INTEGER, user_id INTEGER, UNIQUE(post_id, user_id));
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, user_id INTEGER,
        text TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS stories (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        image_ref TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS story_views (story_id INTEGER, viewer_id INTEGER, UNIQUE(story_id, viewer_id));
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, recipient_id INTEGER, actor_id INTEGER,
        message TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, sender_id INTEGER, receiver_id INTEGER,
        text TEXT NOT NULL, created_at TEXT NOT NULL, is_read INTEGER DEFAULT 0
    );
    """)
    conn.commit()

    if conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0:
        now = datetime.utcnow().isoformat()
        demo = [
            ("Lena Marsh", "lena.frames", "Fog chaser. Medium format, always overexposed by half a stop."),
            ("Theo Nakamura", "theo.contrast", "Expired film enthusiast. Kyoto based."),
            ("Wren Castillo", "wren.develops", "Darkroom nights, desert days."),
            ("Morgan Ali", "morgan.shoots", "Chasing light in medium format."),
        ]
        for name, uname, bio in demo:
            salt = secrets.token_hex(8)
            conn.execute(
                "INSERT INTO users (name, username, password_hash, salt, bio, created_at) VALUES (?,?,?,?,?,?)",
                (name, uname, hash_pw("password123", salt), salt, bio, now),
            )
        conn.commit()
        ids = {r["username"]: r["id"] for r in conn.execute("SELECT id, username FROM users")}
        demo_posts = [
            ("lena.frames", 1015, "Lake Bled, Slovenia", "Some mornings the fog does the composing for you.", "#filmphotography #lakebled"),
            ("theo.contrast", 1074, "Kyoto, Japan", "Shot on expired Portra. The colors had other plans.", "#portra400 #kyoto"),
            ("morgan.shoots", 1084, "Big Sur, CA", "Aperture wide open, patience wider.", "#bigsur #35mm"),
            ("wren.develops", 1069, "Joshua Tree, CA", "The desert doesn't do soft light.", "#joshuatree #desert"),
        ]
        for uname, seed, loc, cap, tags in demo_posts:
            conn.execute(
                "INSERT INTO posts (user_id, image_ref, location, caption, hashtags, created_at) VALUES (?,?,?,?,?,?)",
                (ids[uname], f"seed:{seed}", loc, cap, tags, now),
            )
        expires = (datetime.utcnow() + timedelta(hours=STORY_LIFETIME_HOURS)).isoformat()
        for uname, seed in [("lena.frames", 1025), ("theo.contrast", 1043), ("wren.develops", 1062)]:
            conn.execute(
                "INSERT INTO stories (user_id, image_ref, created_at, expires_at) VALUES (?,?,?,?)",
                (ids[uname], f"seed:{seed}", now, expires),
            )
        conn.commit()


# --------------------------------------------------------------------------
# Auth helpers
# --------------------------------------------------------------------------
def hash_pw(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


def verify_pw(password, salt, expected_hash):
    return hash_pw(password, salt) == expected_hash


# --------------------------------------------------------------------------
# Locally generated "photos" -- no external image host, ever.
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def generate_photo(seed: int, w=360, h=450):
    hue = (seed * 47) % 360
    hue2 = (hue + 35) % 360

    def hsl(h, s, l):
        r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
        return (int(r * 255), int(g * 255), int(b * 255))

    sky_top = hsl(hue, 50, 20)
    sky_bottom = hsl(hue2, 70, 48)
    sun = hsl((hue + 180) % 360, 85, 68)
    mountain = hsl((hue + 200) % 360, 30, 10)
    mountain2 = hsl((hue + 210) % 360, 25, 15)
    ground = hsl((hue + 205) % 360, 22, 7)

    img = Image.new("RGB", (w, h), sky_top)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        r = int(sky_top[0] + (sky_bottom[0] - sky_top[0]) * t)
        g = int(sky_top[1] + (sky_bottom[1] - sky_top[1]) * t)
        b = int(sky_top[2] + (sky_bottom[2] - sky_top[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    sun_x = int(w * (0.28 + (seed * 13 % 44) / 100))
    sun_y = int(h * (0.22 + (seed * 7 % 18) / 100))
    r = int(w * 0.09)
    draw.ellipse([sun_x - r, sun_y - r, sun_x + r, sun_y + r], fill=sun)

    def poly(pts_pct, color):
        pts = [(x / 100 * w, y / 100 * h) for x, y in pts_pct]
        draw.polygon(pts, fill=color)

    poly([(0, 78), (20, 53), (34, 69), (55, 46), (72, 67), (100, 56), (100, 100), (0, 100)], mountain2)
    poly([(0, 74), (22, 46), (40, 66), (58, 42), (78, 62), (100, 48), (100, 100), (0, 100)], mountain)
    draw.rectangle([0, int(h * 0.9), w, h], fill=ground)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def image_bytes(image_ref: str):
    if image_ref.startswith("seed:"):
        return generate_photo(int(image_ref.split(":", 1)[1]))
    if image_ref.startswith("upload:"):
        return base64.b64decode(image_ref.split(":", 1)[1])
    return generate_photo(0)


def badge_color(username):
    h = sum(ord(c) for c in username)
    return BADGE_PALETTE[h % len(BADGE_PALETTE)]


def badge_html(username, size=34):
    color = badge_color(username)
    letter = username[0].upper() if username else "?"
    fs = int(size * 0.42)
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;background:{color};'
        f'display:flex;align-items:center;justify-content:center;color:#1a1502;'
        f'font-weight:700;font-size:{fs}px;font-family:Georgia,serif;flex-shrink:0;">{letter}</div>'
    )


def time_ago(iso_str):
    try:
        then = datetime.fromisoformat(iso_str)
    except ValueError:
        return ""
    s = (datetime.utcnow() - then).total_seconds()
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{int(s // 60)} min ago"
    if s < 86400:
        return f"{int(s // 3600)} hours ago"
    return f"{int(s // 86400)} days ago"


# --------------------------------------------------------------------------
# CSS (dark theme, close to the original design)
# --------------------------------------------------------------------------
st.markdown("""
<style>
:root{
  --void:#121214; --surface:#1c1c1f; --surface-2:#232326; --ink:#f5f3ee; --ink-dim:#9a9a97;
  --flash:#f4c744; --safelight:#e4572e; --hairline:rgba(245,243,238,0.09);
}
.stApp{background:var(--void); color:var(--ink);}
.block-container{max-width:520px; padding-top:1.2rem;}
h1,h2,h3{font-family:Georgia,serif; font-style:italic;}
.ap-card{border:1px solid var(--hairline); border-radius:14px; padding:14px; margin-bottom:14px; background:var(--surface);}
.ap-caption{font-size:14px; line-height:1.5;}
.ap-hashtags{color:var(--flash); font-family:monospace; font-size:12px; display:block; margin-top:4px;}
.ap-dim{color:var(--ink-dim); font-size:12px;}
.ap-flash{color:var(--flash);}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Data helpers
# --------------------------------------------------------------------------
def get_user(username):
    return get_conn().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()


def me():
    return get_conn().execute("SELECT * FROM users WHERE id=?", (st.session_state.user_id,)).fetchone()


def all_usernames():
    return [r["username"] for r in get_conn().execute("SELECT username FROM users")]


def active_stories_for(username):
    conn = get_conn()
    u = get_user(username)
    if not u:
        return []
    cutoff = datetime.utcnow().isoformat()
    rows = conn.execute(
        "SELECT * FROM stories WHERE user_id=? AND expires_at>? ORDER BY created_at ASC",
        (u["id"], cutoff),
    ).fetchall()
    return rows


def has_seen_all(viewer_username, owner_username):
    stories = active_stories_for(owner_username)
    if not stories:
        return False
    viewer = get_user(viewer_username)
    conn = get_conn()
    for s in stories:
        seen = conn.execute("SELECT 1 FROM story_views WHERE story_id=? AND viewer_id=?", (s["id"], viewer["id"])).fetchone()
        if not seen:
            return False
    return True


def add_notification(recipient_id, actor_id, text):
    if recipient_id == actor_id:
        return
    get_conn().execute(
        "INSERT INTO notifications (recipient_id, actor_id, message, created_at) VALUES (?,?,?,?)",
        (recipient_id, actor_id, text, datetime.utcnow().isoformat()),
    )
    get_conn().commit()


def uploaded_to_ref(uploaded_file):
    if uploaded_file is None:
        return None
    data = uploaded_file.read()
    return "upload:" + base64.b64encode(data).decode()


# --------------------------------------------------------------------------
# Auth screens
# --------------------------------------------------------------------------
def screen_auth():
    st.markdown("# Aperture<span class='ap-flash'>.</span>", unsafe_allow_html=True)
    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in", use_container_width=True)
        if submitted:
            u = get_user(username.strip())
            if not u or not verify_pw(password, u["salt"], u["password_hash"]):
                st.error("Incorrect username or password.")
            else:
                st.session_state.user_id = u["id"]
                st.session_state.page = "feed"
                st.rerun()
        st.caption("Demo accounts (password: password123): lena.frames, theo.contrast, wren.develops, morgan.shoots")

    with tab_signup:
        with st.form("signup_form"):
            name = st.text_input("Your name")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            confirm = st.text_input("Confirm password", type="password")
            bio = st.text_input("Bio (optional)")
            submitted = st.form_submit_button("Enter Aperture", use_container_width=True)
        if submitted:
            if not name.strip():
                st.error("Add your name first.")
            elif not username.strip():
                st.error("Pick a username first.")
            elif len(password) < 6:
                st.error("Password must be at least 6 characters.")
            elif password != confirm:
                st.error("Passwords don't match.")
            elif get_user(username.strip()):
                st.error("That username's already taken — try another.")
            else:
                salt = secrets.token_hex(8)
                conn = get_conn()
                conn.execute(
                    "INSERT INTO users (name, username, password_hash, salt, bio, created_at) VALUES (?,?,?,?,?,?)",
                    (name.strip(), username.strip(), hash_pw(password, salt), salt,
                     bio.strip() or "New to Aperture.", datetime.utcnow().isoformat()),
                )
                conn.commit()
                st.session_state.user_id = get_user(username.strip())["id"]
                st.session_state.page = "feed"
                st.rerun()


# --------------------------------------------------------------------------
# Nav
# --------------------------------------------------------------------------
def top_nav():
    my = me()
    c1, c2 = st.columns([4, 1])
    with c1:
        st.markdown("### Aperture<span class='ap-flash'>.</span>", unsafe_allow_html=True)
    with c2:
        if st.button("Log out", use_container_width=True):
            st.session_state.user_id = None
            st.rerun()

    cols = st.columns(6)
    labels = ["Home", "Explore", "+ Post", "+ Story", "Messages", "Activity"]
    targets = ["feed", "explore", "create_post", "create_story", "inbox", "activity"]
    for c, label, target in zip(cols, labels, targets):
        if c.button(label, use_container_width=True, key=f"nav_{target}"):
            st.session_state.page = target
            st.rerun()
    if st.button(f"👤 My profile ({my['username']})", use_container_width=True):
        st.session_state.page = "profile"
        st.session_state.profile_target = my["username"]
        st.rerun()
    st.divider()


# --------------------------------------------------------------------------
# Feed
# --------------------------------------------------------------------------
def screen_feed():
    my = me()
    conn = get_conn()

    st.markdown("#### Stories")
    my_stories = active_stories_for(my["username"])
    others = [u for u in all_usernames() if u != my["username"] and active_stories_for(u)]

    story_cols = st.columns(min(len(others) + 1, 6) or 1)
    with story_cols[0]:
        st.markdown(badge_html(my["username"], 44), unsafe_allow_html=True)
        label = "Add more" if my_stories else "Add to story"
        if st.button(label, key="story_add_btn"):
            st.session_state.page = "create_story"
            st.rerun()
        if my_stories:
            if st.button("View your story", key="view_my_story"):
                st.session_state.page = "story"
                st.session_state.story_target = my["username"]
                st.session_state.story_idx = 0
                st.rerun()
    for i, u in enumerate(others[:5]):
        with story_cols[i + 1]:
            seen = has_seen_all(my["username"], u)
            st.markdown(badge_html(u, 44), unsafe_allow_html=True)
            label = f"{u} {'✓' if seen else '●'}"
            if st.button(label, key=f"story_btn_{u}"):
                st.session_state.page = "story"
                st.session_state.story_target = u
                st.session_state.story_idx = 0
                st.rerun()

    st.markdown("#### Feed")
    posts = conn.execute("""
        SELECT p.*, u.username FROM posts p JOIN users u ON u.id=p.user_id
        ORDER BY p.created_at DESC
    """).fetchall()
    if not posts:
        st.info("No shots yet. Use '+ Post' to develop your first one.")
        return

    for p in posts:
        with st.container():
            st.markdown('<div class="ap-card">', unsafe_allow_html=True)
            c1, c2 = st.columns([1, 8])
            with c1:
                st.markdown(badge_html(p["username"]), unsafe_allow_html=True)
            with c2:
                if st.button(p["username"], key=f"user_{p['id']}"):
                    st.session_state.page = "profile"
                    st.session_state.profile_target = p["username"]
                    st.rerun()
                st.caption(p["location"])
            st.image(image_bytes(p["image_ref"]), use_container_width=True)

            liked = conn.execute("SELECT 1 FROM likes WHERE post_id=? AND user_id=?", (p["id"], my["id"])).fetchone()
            saved = conn.execute("SELECT 1 FROM saves WHERE post_id=? AND user_id=?", (p["id"], my["id"])).fetchone()
            like_count = conn.execute("SELECT COUNT(*) c FROM likes WHERE post_id=?", (p["id"],)).fetchone()["c"]

            bl, bs, _ = st.columns([1, 1, 4])
            if bl.button("♥ Liked" if liked else "♡ Like", key=f"like_{p['id']}"):
                if liked:
                    conn.execute("DELETE FROM likes WHERE post_id=? AND user_id=?", (p["id"], my["id"]))
                else:
                    conn.execute("INSERT INTO likes (post_id, user_id) VALUES (?,?)", (p["id"], my["id"]))
                    add_notification(p["user_id"], my["id"], f"<b>{my['username']}</b> liked your photo")
                conn.commit()
                st.rerun()
            if bs.button("★ Saved" if saved else "☆ Save", key=f"save_{p['id']}"):
                if saved:
                    conn.execute("DELETE FROM saves WHERE post_id=? AND user_id=?", (p["id"], my["id"]))
                else:
                    conn.execute("INSERT INTO saves (post_id, user_id) VALUES (?,?)", (p["id"], my["id"]))
                conn.commit()
                st.rerun()

            st.markdown(f"**{like_count} likes**")
            st.markdown(
                f'<div class="ap-caption"><b>{p["username"]}</b> {p["caption"]}'
                f'<span class="ap-hashtags">{p["hashtags"]}</span></div>',
                unsafe_allow_html=True,
            )

            comments = conn.execute("""
                SELECT c.*, u.username FROM comments c JOIN users u ON u.id=c.user_id
                WHERE post_id=? ORDER BY c.created_at ASC
            """, (p["id"],)).fetchall()
            for c in comments:
                st.markdown(f"<div class='ap-caption'><b>{c['username']}</b> {c['text']}</div>", unsafe_allow_html=True)

            with st.form(f"comment_form_{p['id']}", clear_on_submit=True):
                text = st.text_input("Add a comment…", key=f"ci_{p['id']}", label_visibility="collapsed")
                if st.form_submit_button("Post comment"):
                    if text.strip():
                        conn.execute(
                            "INSERT INTO comments (post_id, user_id, text, created_at) VALUES (?,?,?,?)",
                            (p["id"], my["id"], text.strip(), datetime.utcnow().isoformat()),
                        )
                        add_notification(p["user_id"], my["id"], f"<b>{my['username']}</b> commented: \"{text.strip()[:40]}\"")
                        conn.commit()
                        st.rerun()

            st.caption(time_ago(p["created_at"]))
            st.markdown('</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Create post / create story (kept fully separate from each other)
# --------------------------------------------------------------------------
def _pick_image_ui(key_prefix):
    upload = st.file_uploader("Upload your own", type=["png", "jpg", "jpeg", "gif", "webp"], key=f"{key_prefix}_upload")
    st.caption("Or choose a frame")
    cols = st.columns(4)
    choice = st.session_state.get(f"{key_prefix}_choice")
    for i, seed in enumerate(CURATED_SEEDS):
        with cols[i % 4]:
            st.image(generate_photo(seed, 120, 150), use_container_width=True)
            if st.button("Select" if choice != seed else "Selected ✓", key=f"{key_prefix}_pick_{seed}"):
                st.session_state[f"{key_prefix}_choice"] = seed
                st.rerun()
    if upload is not None:
        return uploaded_to_ref(upload)
    choice = st.session_state.get(f"{key_prefix}_choice")
    if choice:
        return f"seed:{choice}"
    return None


def screen_create_post():
    st.markdown("### New shot")
    image_ref = _pick_image_ui("post")
    location = st.text_input("Location", placeholder="e.g. Big Sur, CA")
    caption = st.text_input("Caption", placeholder="Say something about this shot")
    hashtags = st.text_input("Hashtags", placeholder="#filmphotography #goldenhour")
    if st.button("Share to feed", type="primary"):
        if not image_ref:
            st.error("Pick or upload a photo first.")
        else:
            conn = get_conn()
            conn.execute(
                "INSERT INTO posts (user_id, image_ref, location, caption, hashtags, created_at) VALUES (?,?,?,?,?,?)",
                (me()["id"], image_ref, location.strip() or "New shot", caption.strip(), hashtags.strip(),
                 datetime.utcnow().isoformat()),
            )
            conn.commit()
            st.session_state.pop("post_choice", None)
            st.session_state.page = "feed"
            st.rerun()


def screen_create_story():
    st.markdown("### Add to your story")
    st.caption("Stories disappear after 24 hours and are separate from your feed posts.")
    image_ref = _pick_image_ui("story")
    if st.button("Add to story", type="primary"):
        if not image_ref:
            st.error("Pick or upload a photo for your story.")
        else:
            now = datetime.utcnow()
            conn = get_conn()
            conn.execute(
                "INSERT INTO stories (user_id, image_ref, created_at, expires_at) VALUES (?,?,?,?)",
                (me()["id"], image_ref, now.isoformat(), (now + timedelta(hours=STORY_LIFETIME_HOURS)).isoformat()),
            )
            conn.commit()
            st.session_state.pop("story_choice", None)
            st.session_state.page = "feed"
            st.rerun()


# --------------------------------------------------------------------------
# Story viewer -- strictly scoped to ONE person's own stories
# --------------------------------------------------------------------------
def screen_story():
    owner = st.session_state.get("story_target")
    stories = active_stories_for(owner)  # only ever this user's stories
    if not stories:
        st.info(f"{owner} has no active story right now.")
        if st.button("Back to feed"):
            st.session_state.page = "feed"
            st.rerun()
        return

    idx = min(st.session_state.get("story_idx", 0), len(stories) - 1)
    s = stories[idx]

    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO story_views (story_id, viewer_id) VALUES (?,?)", (s["id"], me()["id"]))
    conn.commit()

    c1, c2 = st.columns([1, 8])
    with c1:
        st.markdown(badge_html(owner), unsafe_allow_html=True)
    with c2:
        st.markdown(f"**{owner}**  ·  shot {idx+1} of {len(stories)} — only {owner}'s story")

    st.image(image_bytes(s["image_ref"]), use_container_width=True)

    p1, p2, p3 = st.columns(3)
    if p1.button("← Prev", disabled=idx == 0):
        st.session_state.story_idx = idx - 1
        st.rerun()
    if p2.button("Close"):
        st.session_state.page = "feed"
        st.rerun()
    if p3.button("Next →", disabled=idx == len(stories) - 1):
        st.session_state.story_idx = idx + 1
        st.rerun()


# --------------------------------------------------------------------------
# Explore / activity / profile
# --------------------------------------------------------------------------
def screen_explore():
    st.markdown("### Explore")
    q = st.text_input("Search photographers, captions, #hashtags").lower().strip()
    conn = get_conn()
    posts = conn.execute("""
        SELECT p.*, u.username FROM posts p JOIN users u ON u.id=p.user_id ORDER BY p.created_at DESC
    """).fetchall()
    if q:
        posts = [p for p in posts if q in p["username"].lower() or q in p["caption"].lower() or q in p["hashtags"].lower()]
    if not posts:
        st.info("No shots match that search.")
        return
    cols = st.columns(3)
    for i, p in enumerate(posts):
        with cols[i % 3]:
            st.image(image_bytes(p["image_ref"]), use_container_width=True)
            if st.button(p["username"], key=f"exp_{p['id']}"):
                st.session_state.page = "profile"
                st.session_state.profile_target = p["username"]
                st.rerun()


def screen_activity():
    st.markdown("### Activity")
    conn = get_conn()
    notes = conn.execute("""
        SELECT n.*, u.username actor_name FROM notifications n JOIN users u ON u.id=n.actor_id
        WHERE recipient_id=? ORDER BY n.created_at DESC
    """, (me()["id"],)).fetchall()
    if not notes:
        st.info("No activity yet. Likes, follows, and comments will show up here.")
        return
    for n in notes:
        c1, c2 = st.columns([1, 8])
        with c1:
            st.markdown(badge_html(n["actor_name"]), unsafe_allow_html=True)
        with c2:
            st.markdown(n["message"], unsafe_allow_html=True)
            st.caption(time_ago(n["created_at"]))


def screen_profile():
    conn = get_conn()
    username = st.session_state.get("profile_target") or me()["username"]
    u = get_user(username)
    if not u:
        st.error("User not found.")
        return
    is_me = username == me()["username"]

    c1, c2 = st.columns([1, 4])
    with c1:
        st.markdown(badge_html(username, 78), unsafe_allow_html=True)
    with c2:
        posts = conn.execute("SELECT * FROM posts WHERE user_id=? ORDER BY created_at DESC", (u["id"],)).fetchall()
        followers = conn.execute("SELECT COUNT(*) c FROM follows WHERE followee_id=?", (u["id"],)).fetchone()["c"]
        following = conn.execute("SELECT COUNT(*) c FROM follows WHERE follower_id=?", (u["id"],)).fetchone()["c"]
        st.markdown(f"**{len(posts)}** posts &nbsp;&nbsp; **{followers}** followers &nbsp;&nbsp; **{following}** following",
                    unsafe_allow_html=True)

    st.markdown(f"*{u['name']}*")
    st.markdown(f"**{u['username']}**")
    st.caption(u["bio"])

    if is_me:
        with st.form("bio_form"):
            new_bio = st.text_input("Update your bio", value=u["bio"])
            if st.form_submit_button("Save"):
                conn.execute("UPDATE users SET bio=? WHERE id=?", (new_bio.strip(), u["id"]))
                conn.commit()
                st.rerun()
    else:
        is_following = conn.execute("SELECT 1 FROM follows WHERE follower_id=? AND followee_id=?",
                                     (me()["id"], u["id"])).fetchone() is not None
        c1, c2 = st.columns(2)
        if c1.button("Following ✓" if is_following else "Follow", key="follow_btn"):
            if is_following:
                conn.execute("DELETE FROM follows WHERE follower_id=? AND followee_id=?", (me()["id"], u["id"]))
            else:
                conn.execute("INSERT INTO follows (follower_id, followee_id) VALUES (?,?)", (me()["id"], u["id"]))
                add_notification(u["id"], me()["id"], f"<b>{me()['username']}</b> started following you")
            conn.commit()
            st.rerun()
        if c2.button("Message", key="msg_btn"):
            st.session_state.page = "thread"
            st.session_state.thread_target = username
            st.rerun()

    if posts:
        cols = st.columns(3)
        for i, p in enumerate(posts):
            with cols[i % 3]:
                st.image(image_bytes(p["image_ref"]), use_container_width=True)
    else:
        st.info("No shots yet.")


# --------------------------------------------------------------------------
# Direct messages
# --------------------------------------------------------------------------
def screen_inbox():
    st.markdown("### Messages")
    conn = get_conn()
    my_id = me()["id"]
    rows = conn.execute("SELECT DISTINCT sender_id, receiver_id FROM messages WHERE sender_id=? OR receiver_id=?",
                         (my_id, my_id)).fetchall()
    others = set()
    for r in rows:
        others.add(r["sender_id"] if r["sender_id"] != my_id else r["receiver_id"])

    if not others:
        st.info("No messages yet. Visit someone's profile and tap Message to start a chat.")
        return

    for uid in others:
        urow = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        last = conn.execute("""
            SELECT * FROM messages WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)
            ORDER BY created_at DESC LIMIT 1
        """, (my_id, uid, uid, my_id)).fetchone()
        c1, c2 = st.columns([1, 8])
        with c1:
            st.markdown(badge_html(urow["username"]), unsafe_allow_html=True)
        with c2:
            if st.button(f"{urow['username']} — {last['text'][:40]}", key=f"inbox_{uid}"):
                st.session_state.page = "thread"
                st.session_state.thread_target = urow["username"]
                st.rerun()


def screen_thread():
    other_username = st.session_state.get("thread_target")
    other = get_user(other_username)
    if not other:
        st.error("User not found.")
        return
    conn = get_conn()
    my_id = me()["id"]

    st.markdown(f"### {other_username}")
    if st.button("← Back to messages"):
        st.session_state.page = "inbox"
        st.rerun()

    thread = conn.execute("""
        SELECT * FROM messages WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)
        ORDER BY created_at ASC
    """, (my_id, other["id"], other["id"], my_id)).fetchall()

    for m in thread:
        align = "right" if m["sender_id"] == my_id else "left"
        bg = "#f4c744" if m["sender_id"] == my_id else "#232326"
        fg = "#1a1502" if m["sender_id"] == my_id else "#f5f3ee"
        st.markdown(
            f'<div style="text-align:{align};margin:4px 0;">'
            f'<span style="background:{bg};color:{fg};padding:8px 12px;border-radius:14px;'
            f'display:inline-block;max-width:75%;">{m["text"]}</span></div>',
            unsafe_allow_html=True,
        )
    if not thread:
        st.info(f"Say hello to {other_username}.")

    with st.form("send_msg_form", clear_on_submit=True):
        text = st.text_input(f"Message {other_username}…", label_visibility="collapsed")
        if st.form_submit_button("Send"):
            if text.strip():
                conn.execute(
                    "INSERT INTO messages (sender_id, receiver_id, text, created_at) VALUES (?,?,?,?)",
                    (my_id, other["id"], text.strip(), datetime.utcnow().isoformat()),
                )
                conn.commit()
                st.rerun()


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    init_db()
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "page" not in st.session_state:
        st.session_state.page = "feed"

    if not st.session_state.user_id:
        screen_auth()
        return

    top_nav()
    page = st.session_state.page
    if page == "feed":
        screen_feed()
    elif page == "explore":
        screen_explore()
    elif page == "activity":
        screen_activity()
    elif page == "profile":
        screen_profile()
    elif page == "create_post":
        screen_create_post()
    elif page == "create_story":
        screen_create_story()
    elif page == "story":
        screen_story()
    elif page == "inbox":
        screen_inbox()
    elif page == "thread":
        screen_thread()
    else:
        screen_feed()


if __name__ == "__main__":
    main()
