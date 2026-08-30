#!/usr/bin/env python3
"""Local CMS server for maxgoodstein.com"""

import json
import os
import re
import subprocess
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PORT = 8080
ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT_FILE = os.path.join(ROOT, "content.json")
INDEX_FILE = os.path.join(ROOT, "index.html")
DASHBOARD_FILE = os.path.join(ROOT, "dashboard.html")
PORTFOLIO_JS = os.path.join(ROOT, "portfolio", "projects.js")
PORTFOLIO_IMG_DIR = os.path.join(ROOT, "portfolio", "img")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")

ICON_SVG = {
    "linkedin": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>',
    "github": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>',
    "email": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 7l-10 6L2 7"/></svg>',
    "twitter": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>',
    "instagram": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>',
    "website": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>',
    "portfolio": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/></svg>',
    "youtube": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>',
    "tiktok": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/></svg>',
}

# Google Fonts to load
FONT_IMPORTS = {
    "Inter": "Inter:wght@400;500;600",
    "Playfair Display": "Playfair+Display:wght@400;500;600",
    "Space Grotesk": "Space+Grotesk:wght@400;500;600",
    "DM Sans": "DM+Sans:wght@400;500;600",
    "Libre Baskerville": "Libre+Baskerville:wght@400;700",
}

# Avatar shape CSS
AVATAR_SHAPES = {
    "circle": "50%",
    "rounded": "20%",
    "square": "0%",
}

# Link style CSS generators
LINK_STYLES = {
    "outline": """
    .links a { display: flex; align-items: center; justify-content: center; gap: 0.6rem; padding: 0.85rem 1.5rem; border: 1px solid var(--border); border-radius: 10px; text-decoration: none; color: var(--text); font-size: 0.95rem; font-weight: 500; background: var(--card-bg); transition: all 0.2s ease; }
    .links a:hover { border-color: var(--accent); color: var(--accent); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.08); }""",
    "filled": """
    .links a { display: flex; align-items: center; justify-content: center; gap: 0.6rem; padding: 0.85rem 1.5rem; border: none; border-radius: 10px; text-decoration: none; color: white; font-size: 0.95rem; font-weight: 500; background: var(--accent); transition: all 0.2s ease; }
    .links a:hover { background: var(--accent-hover); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }""",
    "pill": """
    .links a { display: flex; align-items: center; justify-content: center; gap: 0.6rem; padding: 0.85rem 1.5rem; border: 2px solid var(--accent); border-radius: 50px; text-decoration: none; color: var(--accent); font-size: 0.95rem; font-weight: 500; background: transparent; transition: all 0.2s ease; }
    .links a:hover { background: var(--accent); color: white; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }""",
    "minimal": """
    .links a { display: flex; align-items: center; justify-content: center; gap: 0.6rem; padding: 0.85rem 1.5rem; border: none; border-radius: 0; border-bottom: 1px solid var(--border); text-decoration: none; color: var(--text); font-size: 0.95rem; font-weight: 500; background: transparent; transition: all 0.2s ease; }
    .links a:hover { color: var(--accent); border-bottom-color: var(--accent); }""",
}


def build_index_html(data):
    theme = data.get("theme", {})
    accent = theme.get("accentColor", "#2d6a4f")
    accent_light = theme.get("accentColorLight", "#40916c")
    bg = theme.get("bgColor", "#fafafa")
    text_color = theme.get("textColor", "#1a1a1a")
    text_secondary = theme.get("textSecondary", "#555555")
    border_color = theme.get("borderColor", "#e0e0e0")
    card_bg = theme.get("cardBg", "#ffffff")
    font = theme.get("font", "Inter")
    link_style = theme.get("linkStyle", "outline")
    avatar_shape = data.get("avatarShape", "circle")

    font_import = FONT_IMPORTS.get(font, FONT_IMPORTS["Inter"])
    avatar_radius = AVATAR_SHAPES.get(avatar_shape, "50%")
    link_css = LINK_STYLES.get(link_style, LINK_STYLES["outline"])

    name = escape(data.get("name", ""))
    tagline = escape(data.get("tagline", ""))
    bio = escape(data.get("bio", ""))

    # Avatar HTML
    if data.get("avatarType") == "image" and data.get("avatarImage"):
        avatar_html = f'<div class="avatar"><img src="{escape(data["avatarImage"])}" alt="{name}"></div>'
    else:
        initials = escape(data.get("avatarInitials", "MG"))
        avatar_html = f'<div class="avatar">{initials}</div>'

    # Links HTML
    links_lines = []
    for link in data.get("links", []):
        icon = ICON_SVG.get(link.get("icon", "website"), ICON_SVG["website"])
        # Internal links (e.g. /portfolio/) stay in the same tab
        internal = link["url"].startswith(("/", "#"))
        target = "" if internal else ' target="_blank" rel="noopener"'
        links_lines.append(
            f'      <a href="{escape(link["url"])}"{target}>\n'
            f"        {icon}\n"
            f'        {escape(link["label"])}\n'
            f"      </a>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{name}</title>
  <meta name="description" content="{name} — {tagline}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family={font_import}&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
    :root {{
      --accent: {accent};
      --accent-hover: {accent_light};
      --bg: {bg};
      --text: {text_color};
      --text-secondary: {text_secondary};
      --border: {border_color};
      --card-bg: {card_bg};
    }}
    body {{ font-family: '{font}', -apple-system, BlinkMacSystemFont, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 2rem; -webkit-font-smoothing: antialiased; }}
    .container {{ max-width: 520px; width: 100%; text-align: center; }}
    .avatar {{ width: 120px; height: 120px; border-radius: {avatar_radius}; background: linear-gradient(135deg, var(--accent), var(--accent-hover)); display: flex; align-items: center; justify-content: center; margin: 0 auto 2rem; font-size: 2.5rem; font-weight: 600; color: white; letter-spacing: 1px; overflow: hidden; }}
    .avatar img {{ width: 100%; height: 100%; object-fit: cover; }}
    h1 {{ font-size: 1.75rem; font-weight: 600; margin-bottom: 0.5rem; letter-spacing: -0.02em; }}
    .tagline {{ font-size: 1rem; color: var(--text-secondary); margin-bottom: 2rem; line-height: 1.5; }}
    .bio {{ font-size: 0.95rem; line-height: 1.7; color: var(--text-secondary); margin-bottom: 2.5rem; padding: 0 0.5rem; white-space: pre-line; }}
    .links {{ display: flex; flex-direction: column; gap: 0.75rem; }}
    {link_css}
    .links a svg {{ width: 20px; height: 20px; flex-shrink: 0; }}
    .divider {{ width: 40px; height: 1px; background: var(--border); margin: 2.5rem auto; }}
    .footer {{ font-size: 0.8rem; color: var(--text-secondary); opacity: 0.6; }}
    @media (max-width: 480px) {{ body {{ padding: 1.5rem; }} h1 {{ font-size: 1.5rem; }} .avatar {{ width: 100px; height: 100px; font-size: 2rem; }} }}
  </style>
</head>
<body>
  <main class="container">
    {avatar_html}
    <h1>{name}</h1>
    <p class="tagline">{tagline}</p>
    <p class="bio">{bio}</p>
    <div class="links">
{chr(10).join(links_lines)}
    </div>
    <div class="divider"></div>
    <p class="footer">&copy; 2026 {name}</p>
  </main>
</body>
</html>"""
    return html


def load_content():
    with open(CONTENT_FILE, "r") as f:
        return json.load(f)


def save_content(data):
    with open(CONTENT_FILE, "w") as f:
        json.dump(data, f, indent=2)
    generate_index(data)


def generate_index(data):
    html = build_index_html(data)
    with open(INDEX_FILE, "w") as f:
        f.write(html)


PORTFOLIO_HEADER = """\
// Portfolio content: edit via the local dashboard (python3 server.py -> Portfolio tab),
// directly in this file, or at maxgoodstein.com/portfolio/?edit (download the result).
// To publish from the dashboard just hit Push Live; otherwise commit and push.

"""


def load_portfolio():
    with open(PORTFOLIO_JS, "r") as f:
        text = f.read()
    start = text.index("[", text.index("const PROJECTS"))
    end = text.rindex("]")
    return json.loads(text[start:end + 1])


def save_portfolio(projects):
    with open(PORTFOLIO_JS, "w") as f:
        f.write(PORTFOLIO_HEADER + "const PROJECTS = " + json.dumps(projects, indent=2, ensure_ascii=False) + ";\n")


def unique_path(directory, filename):
    """Return a path in directory for filename, suffixing -2, -3... if taken."""
    stem, ext = os.path.splitext(filename)
    candidate = filename
    n = 2
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{stem}-{n}{ext}"
        n += 1
    return os.path.join(directory, candidate)


def git_push():
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
    try:
        subprocess.run(["git", "add", "."], cwd=ROOT, check=True, capture_output=True)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT, check=True, capture_output=True, text=True
        )
        if not result.stdout.strip():
            return {"ok": True, "message": "No changes to push."}
        subprocess.run(
            ["git", "commit", "-m", "Update site via dashboard"],
            cwd=ROOT, check=True, capture_output=True, text=True, env=env
        )
        subprocess.run(
            ["git", "push"],
            cwd=ROOT, check=True, capture_output=True, text=True, env=env
        )
        return {"ok": True, "message": "Pushed live! Changes will appear in ~30 seconds."}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "message": f"Git error: {e.stderr or e.stdout or str(e)}"}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/dashboard":
            self.send_file(DASHBOARD_FILE, "text/html")
        elif path == "/api/content":
            self.send_json(load_content())
        elif path == "/api/portfolio":
            self.send_json(load_portfolio())
        elif path == "/preview":
            self.send_file(INDEX_FILE, "text/html")
        elif path == "/portfolio" or path == "/portfolio/":
            self.send_file(os.path.join(ROOT, "portfolio", "index.html"), "text/html")
        elif path == "/portfolio/projects.js":
            self.send_file(PORTFOLIO_JS, "text/javascript")
        elif path.startswith("/uploads/") or path.endswith(IMAGE_EXTS):
            super().do_GET()
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/content":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
            save_content(data)
            self.send_json({"ok": True})
        elif path == "/api/portfolio":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            projects = json.loads(body)
            save_portfolio(projects)
            self.send_json({"ok": True})
        elif path == "/api/push":
            result = git_push()
            self.send_json(result)
        elif path == "/api/upload":
            upload = self.read_upload()
            if not upload:
                self.send_json({"ok": False, "message": "No file found"})
                return
            filename, file_data = upload
            uploads_dir = os.path.join(ROOT, "uploads")
            os.makedirs(uploads_dir, exist_ok=True)
            filepath = os.path.join(uploads_dir, filename)
            with open(filepath, "wb") as f:
                f.write(file_data)
            self.send_json({"ok": True, "path": f"uploads/{filename}"})
        elif path == "/api/portfolio/upload":
            upload = self.read_upload()
            if not upload:
                self.send_json({"ok": False, "message": "No file found"})
                return
            filename, file_data = upload
            if not filename.lower().endswith(IMAGE_EXTS):
                self.send_json({"ok": False, "message": "Not an image file"})
                return
            filename = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).lower()
            os.makedirs(PORTFOLIO_IMG_DIR, exist_ok=True)
            filepath = unique_path(PORTFOLIO_IMG_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(file_data)
            saved = os.path.basename(filepath)
            # projects.js page ids: bare names map to img/<name>.webp,
            # names containing a dot are used as-is (img/<name.ext>)
            stem, ext = os.path.splitext(saved)
            page_id = stem if ext == ".webp" else saved
            self.send_json({"ok": True, "id": page_id})
        else:
            self.send_error(404)

    def read_upload(self):
        """Parse a single-file multipart upload; returns (filename, bytes) or None."""
        content_type = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        boundary = content_type.split("boundary=")[1] if "boundary=" in content_type else None
        if not boundary:
            return None
        parts = body.split(b"--" + boundary.encode())
        for part in parts:
            if b"filename=" in part:
                header_end = part.index(b"\r\n\r\n")
                header = part[:header_end].decode("utf-8", errors="replace")
                file_data = part[header_end + 4:]
                if file_data.endswith(b"\r\n"):
                    file_data = file_data[:-2]
                match = re.search(r'filename="([^"]+)"', header)
                if match:
                    return os.path.basename(match.group(1)), file_data
        return None

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, filepath, content_type):
        with open(filepath, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


if __name__ == "__main__":
    if os.path.exists(CONTENT_FILE):
        save_content(load_content())
        print("Regenerated index.html from content.json")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"\n  Dashboard running at http://localhost:{PORT}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()
