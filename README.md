# Aperture (Streamlit version)

A rebuild of Aperture as a genuine Streamlit app — single `app.py`, no Flask.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Demo accounts (password `password123`): `lena.frames`, `theo.contrast`,
`wren.develops`, `morgan.shoots` — or sign up fresh.

## Deploying on Streamlit Community Cloud

1. Push this folder to a GitHub repo (just `app.py` and `requirements.txt` at
   the root — same as before).
2. Go to share.streamlit.io → **New app** → pick the repo → set the main
   file to `app.py` → Deploy.

That's it — no build/start commands needed, Streamlit Cloud runs `app.py`
directly.

## What's different from the Flask version

- Navigation is a row of buttons instead of a mobile bottom nav — Streamlit
  reruns the whole script per interaction rather than routing between pages.
- The story viewer uses **Prev / Next / Close** buttons instead of an
  auto-advancing timer (Streamlit has no background timers), but it's still
  strictly scoped to one person's own stories — opening someone's story only
  ever shows their stories, never bleeds into anyone else's.
- Posting to the feed and adding to your story are still two completely
  separate flows/tables, same as before.
- No avatars anywhere — colored initial badges instead, same as before.
- Signup asks for your name in addition to username/password.
- Images (curated + generated) are drawn locally with Pillow — no external
  image host, so nothing ever shows up blank.

## Notes

- Data lives in a local SQLite file (`aperture.db`) created automatically on
  first run. On Streamlit Community Cloud, the filesystem is not guaranteed
  to persist across redeploys/restarts — fine for demoing, but don't rely on
  it for anything you need to keep long-term.
- Password hashing uses PBKDF2-SHA256 with a per-user salt (stdlib
  `hashlib`, no extra dependency).
