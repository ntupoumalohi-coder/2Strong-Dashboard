"""
2Strong Financial — Agent Portal backend.
Pure Python standard library (sqlite3 + http.server). No pip installs needed.

Run:
    python3 server.py
Then open:
    http://localhost:8787

Demo logins (password for all: password123):
    morgan.ellis      Admin
    dana.whitfield    Agency Partner
    priya.nandakumar  Senior Producer
    jordan.blake      Associate
(see seed.py for the full roster)
"""
import json
import mimetypes
import os
import secrets
import sqlite3
import sys
import urllib.parse
from datetime import datetime, timedelta
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ============================================================================
# --- Database schema + seed data (originally backend/seed.py) ---
# ============================================================================
import sqlite3
import hashlib
import secrets
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db.sqlite3")

SCHEMA = """
CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  salt TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  tier TEXT,
  initials TEXT,
  email TEXT,
  phone TEXT,
  agent_id TEXT,
  agency TEXT,
  upline_id INTEGER REFERENCES users(id),
  join_date TEXT,
  license_states TEXT,
  npn TEXT,
  status TEXT DEFAULT 'Active',
  ytd REAL DEFAULT 0,
  policies INTEGER DEFAULT 0
);

CREATE TABLE prospects (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  stage TEXT NOT NULL,
  source TEXT,
  agent_id INTEGER REFERENCES users(id),
  premium REAL DEFAULT 0,
  last_contact TEXT,
  phone TEXT,
  created_at TEXT
);

CREATE TABLE clients (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  policy_type TEXT,
  carrier TEXT,
  premium REAL DEFAULT 0,
  status TEXT,
  agent_id INTEGER REFERENCES users(id),
  effective TEXT,
  created_at TEXT
);

CREATE TABLE commissions (
  id TEXT PRIMARY KEY,
  date TEXT,
  client_name TEXT,
  agent_id INTEGER REFERENCES users(id),
  carrier TEXT,
  product TEXT,
  premium REAL DEFAULT 0,
  commission REAL DEFAULT 0,
  status TEXT
);

CREATE TABLE submitted_business (
  id TEXT PRIMARY KEY,
  date TEXT,
  client_name TEXT,
  agent_id INTEGER REFERENCES users(id),
  carrier TEXT,
  product TEXT,
  face_amount REAL DEFAULT 0,
  status TEXT,
  created_at TEXT
);

CREATE TABLE eapplications (
  id TEXT PRIMARY KEY,
  client_name TEXT,
  agent_id INTEGER REFERENCES users(id),
  carrier TEXT,
  started TEXT,
  progress INTEGER DEFAULT 0,
  status TEXT,
  created_at TEXT
);

CREATE TABLE events (
  id INTEGER PRIMARY KEY,
  title TEXT,
  type TEXT,
  date TEXT,
  month TEXT,
  day TEXT,
  time TEXT,
  location TEXT
);

CREATE TABLE training_modules (
  id INTEGER PRIMARY KEY,
  title TEXT,
  category TEXT
);

CREATE TABLE training_progress (
  training_id INTEGER REFERENCES training_modules(id),
  user_id INTEGER REFERENCES users(id),
  progress INTEGER DEFAULT 0,
  status TEXT,
  due TEXT,
  PRIMARY KEY (training_id, user_id)
);

CREATE TABLE billing_invoices (
  id TEXT PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  date TEXT,
  description TEXT,
  amount REAL,
  status TEXT
);

CREATE TABLE sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  created_at TEXT,
  expires_at TEXT
);
"""

DEMO_PASSWORD = "password123"


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000).hex()
    return h, salt


USERS = [
    # username, name, role, tier, initials, email, phone, agent_id, agency, upline_username, join_date, states, npn, status, ytd, policies
    ("morgan.ellis", "Morgan Ellis", "Admin", "Admin", "ME", "morgan.ellis@2strongfinancial.com", "(602) 555-0134", "2SF-00021", "2Strong Financial — HQ", None, "Jan 12, 2019", "AZ,CA,TX,FL,NV", "8841022", "Active", 0, 0),
    ("dana.whitfield", "Dana Whitfield", "Agency Partner", "Partner", "DW", "dana.whitfield@2strongfinancial.com", "(480) 555-0188", "2SF-00147", "2Strong Financial — Desert Ridge", "morgan.ellis", "Mar 4, 2020", "AZ,CA,NM", "7729841", "Active", 284500, 61),
    ("priya.nandakumar", "Priya Nandakumar", "Senior Producer", "Senior Producer", "PN", "priya.n@2strongfinancial.com", "(602) 555-0221", "2SF-00398", "2Strong Financial — Desert Ridge", "dana.whitfield", "Sep 18, 2021", "AZ,CA", "6650213", "Active", 152300, 38),
    ("jordan.blake", "Jordan Blake", "Associate", "Associate", "JB", "jordan.blake@2strongfinancial.com", "(623) 555-0176", "2SF-00512", "2Strong Financial — Desert Ridge", "priya.nandakumar", "Feb 2, 2025", "AZ", "5502187", "Active", 41200, 12),
    ("marcus.reyes", "Marcus Reyes", "Associate", "Associate", "MR", "marcus.reyes@2strongfinancial.com", "(480) 555-0000", "2SF-00600", "2Strong Financial — Desert Ridge", "dana.whitfield", "Nov 2024", "AZ", "5502188", "Active", 58900, 17),
    ("alicia.fenwick", "Alicia Fenwick", "Senior Producer", "Senior Producer", "AF", "alicia.fenwick@2strongfinancial.com", "(480) 555-0001", "2SF-00601", "2Strong Financial — Desert Ridge", "dana.whitfield", "Jun 2022", "AZ,CA", "5502189", "Active", 133700, 34),
    ("tobias.kim", "Tobias Kim", "Associate", "Associate", "TK", "tobias.kim@2strongfinancial.com", "(480) 555-0002", "2SF-00602", "2Strong Financial — Desert Ridge", "alicia.fenwick", "May 2026", "AZ", "5502190", "Pending License", 6100, 2),
    ("renee.castillo", "Renee Castillo", "Associate", "Associate", "RC", "renee.castillo@2strongfinancial.com", "(480) 555-0003", "2SF-00603", "2Strong Financial — Desert Ridge", "alicia.fenwick", "Aug 2024", "AZ", "5502191", "Active", 39800, 11),
    ("sam.okafor", "Sam Okafor", "Associate", "Associate", "SO", "sam.okafor@2strongfinancial.com", "(480) 555-0004", "2SF-00604", "2Strong Financial — Desert Ridge", "marcus.reyes", "Jan 2024", "AZ", "5502192", "Inactive", 4200, 1),
]

PROSPECTS = [
    ("Harold Beckwith", "New Lead", "Referral", "jordan.blake", 3200, "Jun 28, 2026", "(602) 555-9911"),
    ("Cynthia Marsh", "Contacted", "Facebook Ad", "marcus.reyes", 5400, "Jun 29, 2026", "(480) 555-2231"),
    ("Devon Ashcroft", "Appointment Set", "Web Form", "jordan.blake", 8100, "Jun 30, 2026", "(623) 555-7743"),
    ("Lena Petrova", "Quoted", "Referral", "priya.nandakumar", 12500, "Jun 27, 2026", "(602) 555-3390"),
    ("Grant Whitmore", "Contacted", "Seminar", "alicia.fenwick", 6700, "Jun 25, 2026", "(480) 555-6612"),
    ("Isabel Ruiz", "New Lead", "Web Form", "renee.castillo", 4100, "Jun 30, 2026", "(602) 555-8827"),
    ("Walter Boone", "Not Interested", "Cold Call", "marcus.reyes", 2900, "Jun 20, 2026", "(623) 555-4415"),
    ("Naomi Fischer", "Appointment Set", "Referral", "jordan.blake", 9800, "Jul 1, 2026", "(480) 555-1187"),
]

CLIENTS = [
    ("Robert & Linda Chan", "Indexed Universal Life", "Pinnacle Mutual", 4800, "In Force", "priya.nandakumar", "Apr 14, 2025"),
    ("Marcus Delaney", "Term Life 20", "Everstone Life", 1200, "In Force", "jordan.blake", "Jan 8, 2026"),
    ("Sophia Turner", "Fixed Annuity", "Granite Peak Financial", 65000, "In Force", "dana.whitfield", "Nov 2, 2024"),
    ("The Ferraro Family", "Whole Life", "Everstone Life", 3100, "Lapsed", "marcus.reyes", "Jun 19, 2023"),
    ("Diane Ostrowski", "Medicare Supplement", "BlueCrest Health", 1850, "In Force", "alicia.fenwick", "Feb 27, 2026"),
    ("Kevin Alarcon", "Term Life 30", "Pinnacle Mutual", 940, "In Force", "jordan.blake", "May 30, 2026"),
    ("Patricia Nguyen", "Indexed Annuity", "Granite Peak Financial", 82000, "In Force", "priya.nandakumar", "Mar 11, 2026"),
    ("Bruce Halloway", "Final Expense", "BlueCrest Health", 610, "Pending", "renee.castillo", "Pending"),
]

COMMISSIONS = [
    ("C-10432", "Jun 30, 2026", "Kevin Alarcon", "jordan.blake", "Pinnacle Mutual", "Term Life 30", 940, 799, "Paid"),
    ("C-10431", "Jun 28, 2026", "Patricia Nguyen", "priya.nandakumar", "Granite Peak Financial", "Indexed Annuity", 82000, 4920, "Paid"),
    ("C-10428", "Jun 24, 2026", "Diane Ostrowski", "alicia.fenwick", "BlueCrest Health", "Medicare Supplement", 1850, 462, "Processing"),
    ("C-10421", "Jun 18, 2026", "Marcus Delaney", "jordan.blake", "Everstone Life", "Term Life 20", 1200, 1020, "Paid"),
    ("C-10417", "Jun 12, 2026", "Sophia Turner", "dana.whitfield", "Granite Peak Financial", "Fixed Annuity", 65000, 3900, "Paid"),
    ("C-10409", "Jun 5, 2026", "Bruce Halloway", "renee.castillo", "BlueCrest Health", "Final Expense", 610, 293, "Pending"),
    ("C-10402", "May 29, 2026", "Robert & Linda Chan", "priya.nandakumar", "Pinnacle Mutual", "Indexed Universal Life", 4800, 3840, "Paid"),
    ("C-10396", "May 21, 2026", "The Ferraro Family", "marcus.reyes", "Everstone Life", "Whole Life", 3100, 2170, "Chargeback"),
]

SUBMITTED = [
    ("SB-2201", "Jun 30, 2026", "Kevin Alarcon", "jordan.blake", "Pinnacle Mutual", "Term Life 30", 500000, "Approved"),
    ("SB-2199", "Jun 29, 2026", "Naomi Fischer", "jordan.blake", "Everstone Life", "Term Life 20", 250000, "In Underwriting"),
    ("SB-2196", "Jun 26, 2026", "Patricia Nguyen", "priya.nandakumar", "Granite Peak Financial", "Indexed Annuity", 82000, "Approved"),
    ("SB-2190", "Jun 24, 2026", "Diane Ostrowski", "alicia.fenwick", "BlueCrest Health", "Medicare Supplement", 0, "Approved"),
    ("SB-2184", "Jun 20, 2026", "Isabel Ruiz", "renee.castillo", "Pinnacle Mutual", "Whole Life", 150000, "Requires Info"),
    ("SB-2179", "Jun 15, 2026", "Bruce Halloway", "renee.castillo", "BlueCrest Health", "Final Expense", 15000, "In Underwriting"),
    ("SB-2171", "Jun 9, 2026", "Lena Petrova", "priya.nandakumar", "Granite Peak Financial", "Fixed Annuity", 45000, "Declined"),
]

EAPPS = [
    ("EA-8841", "Naomi Fischer", "jordan.blake", "Everstone Life", "Jun 29, 2026", 90, "Awaiting E-Sign"),
    ("EA-8837", "Isabel Ruiz", "renee.castillo", "Pinnacle Mutual", "Jun 27, 2026", 55, "In Progress"),
    ("EA-8829", "Grant Whitmore", "alicia.fenwick", "BlueCrest Health", "Jun 24, 2026", 100, "Submitted"),
    ("EA-8815", "Devon Ashcroft", "jordan.blake", "Everstone Life", "Jun 20, 2026", 30, "In Progress"),
    ("EA-8802", "Lena Petrova", "priya.nandakumar", "Granite Peak Financial", "Jun 14, 2026", 100, "Submitted"),
    ("EA-8794", "Cynthia Marsh", "marcus.reyes", "Pinnacle Mutual", "Jun 10, 2026", 10, "Draft"),
]

EVENTS = [
    ("New Agent Orientation", "Onboarding", "Jul 6, 2026", "JUL", "06", "9:00 AM MST", "Virtual — Zoom"),
    ("Q3 Product Launch: Pinnacle IUL 2.0", "Carrier Update", "Jul 9, 2026", "JUL", "09", "1:00 PM MST", "HQ — Main Hall"),
    ("Advanced Annuity Sales Workshop", "Training", "Jul 14, 2026", "JUL", "14", "10:00 AM MST", "Virtual — Zoom"),
    ("Monthly Leaderboard Recognition Call", "Recognition", "Jul 17, 2026", "JUL", "17", "4:00 PM MST", "Virtual — Teams"),
    ("Desert Ridge Team Summit", "Team Event", "Jul 24, 2026", "JUL", "24", "9:00 AM MST", "Scottsdale, AZ"),
    ("Compliance & Ethics Refresher", "Compliance", "Jul 30, 2026", "JUL", "30", "11:00 AM MST", "Virtual — Zoom"),
]

TRAINING_MODULES = [
    ("2Strong Onboarding Fundamentals", "Onboarding"),
    ("Life Insurance Product Suite Certification", "Product"),
    ("Annuity Sales & Suitability", "Product"),
    ("State Continuing Education — AZ (24 hrs)", "Compliance"),
    ("Medicare Supplement Certification", "Product"),
    ("Advanced Prospecting & Referral Systems", "Sales Skills"),
]
# same default progress applied to every seeded user, per module index
TRAINING_DEFAULT_PROGRESS = [
    (100, "Completed", "Completed Feb 10, 2025"),
    (100, "Completed", "Completed Mar 2, 2025"),
    (65, "In Progress", "Due Jul 15, 2026"),
    (40, "In Progress", "Due Aug 1, 2026"),
    (0, "Not Started", "Due Sep 1, 2026"),
    (20, "In Progress", "Due Jul 30, 2026"),
]

BILLING_TEMPLATE = [
    ("Jun 1, 2026", "Monthly E&O Insurance", 45.0, "Paid"),
    ("Jun 1, 2026", "CRM & Quoting Platform Fee", 59.0, "Paid"),
    ("May 1, 2026", "Monthly E&O Insurance", 45.0, "Paid"),
    ("May 1, 2026", "CRM & Quoting Platform Fee", 59.0, "Paid"),
    ("Apr 1, 2026", "Monthly E&O Insurance", 45.0, "Paid"),
    ("Jul 1, 2026", "CRM & Quoting Platform Fee", 59.0, "Due Jul 5"),
]


def init_db(force=False):
    if force and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    is_new = not os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    if is_new:
        conn.executescript(SCHEMA)
        _seed(conn)
        conn.commit()
    return conn


def _seed(conn):
    username_to_id = {}
    # first pass: insert without upline to get ids
    for row in USERS:
        (username, name, role, tier, initials, email, phone, agent_id, agency,
         upline_username, join_date, states, npn, status, ytd, policies) = row
        pw_hash, salt = hash_password(DEMO_PASSWORD)
        cur = conn.execute(
            """INSERT INTO users (username, password_hash, salt, name, role, tier, initials,
               email, phone, agent_id, agency, upline_id, join_date, license_states, npn,
               status, ytd, policies) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (username, pw_hash, salt, name, role, tier, initials, email, phone, agent_id,
             agency, None, join_date, states, npn, status, ytd, policies),
        )
        username_to_id[username] = cur.lastrowid
    # second pass: set upline_id
    for row in USERS:
        username, upline_username = row[0], row[9]
        if upline_username:
            conn.execute("UPDATE users SET upline_id=? WHERE username=?",
                         (username_to_id[upline_username], username))

    for name, stage, source, agent_username, premium, last_contact, phone in PROSPECTS:
        conn.execute(
            "INSERT INTO prospects (name, stage, source, agent_id, premium, last_contact, phone, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
            (name, stage, source, username_to_id[agent_username], premium, last_contact, phone),
        )

    for name, ptype, carrier, premium, status, agent_username, effective in CLIENTS:
        conn.execute(
            "INSERT INTO clients (name, policy_type, carrier, premium, status, agent_id, effective, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
            (name, ptype, carrier, premium, status, username_to_id[agent_username], effective),
        )

    for cid, date, client_name, agent_username, carrier, product, premium, commission, status in COMMISSIONS:
        conn.execute(
            "INSERT INTO commissions (id, date, client_name, agent_id, carrier, product, premium, commission, status) VALUES (?,?,?,?,?,?,?,?,?)",
            (cid, date, client_name, username_to_id[agent_username], carrier, product, premium, commission, status),
        )

    for sid, date, client_name, agent_username, carrier, product, face, status in SUBMITTED:
        conn.execute(
            "INSERT INTO submitted_business (id, date, client_name, agent_id, carrier, product, face_amount, status, created_at) VALUES (?,?,?,?,?,?,?,?,datetime('now'))",
            (sid, date, client_name, username_to_id[agent_username], carrier, product, face, status),
        )

    for eid, client_name, agent_username, carrier, started, progress, status in EAPPS:
        conn.execute(
            "INSERT INTO eapplications (id, client_name, agent_id, carrier, started, progress, status, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
            (eid, client_name, username_to_id[agent_username], carrier, started, progress, status),
        )

    for title, etype, date, month, day, time_, location in EVENTS:
        conn.execute(
            "INSERT INTO events (title, type, date, month, day, time, location) VALUES (?,?,?,?,?,?,?)",
            (title, etype, date, month, day, time_, location),
        )

    module_ids = []
    for title, category in TRAINING_MODULES:
        cur = conn.execute("INSERT INTO training_modules (title, category) VALUES (?,?)", (title, category))
        module_ids.append(cur.lastrowid)

    for uid in username_to_id.values():
        for i, mid in enumerate(module_ids):
            progress, status, due = TRAINING_DEFAULT_PROGRESS[i]
            conn.execute(
                "INSERT INTO training_progress (training_id, user_id, progress, status, due) VALUES (?,?,?,?,?)",
                (mid, uid, progress, status, due),
            )
        for i, (date, desc, amount, status) in enumerate(BILLING_TEMPLATE):
            conn.execute(
                "INSERT INTO billing_invoices (id, user_id, date, description, amount, status) VALUES (?,?,?,?,?,?)",
                (f"INV-{uid}-{i+1}", uid, date, desc, amount, status),
            )


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = BASE_DIR  # index.html lives next to this script
PORT = int(os.environ.get("PORT", "8787"))
SESSION_TTL_DAYS = 7


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Scoping helpers
# ---------------------------------------------------------------------------
def get_downline_ids(conn, root_id):
    ids = {root_id}
    rows = conn.execute("SELECT id, upline_id FROM users").fetchall()
    changed = True
    while changed:
        changed = False
        for r in rows:
            if r["upline_id"] in ids and r["id"] not in ids:
                ids.add(r["id"])
                changed = True
    return ids


def scope_user_ids(conn, user):
    """Returns None for org-wide (Admin), else a set of user ids in scope."""
    if user["role"] == "Admin":
        return None
    return get_downline_ids(conn, user["id"])


def user_public(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "name": row["name"],
        "role": row["role"],
        "tier": row["tier"],
        "initials": row["initials"],
        "email": row["email"],
        "phone": row["phone"],
        "agentId": row["agent_id"],
        "agency": row["agency"],
        "uplineId": row["upline_id"],
        "joinDate": row["join_date"],
        "licenseStates": (row["license_states"] or "").split(",") if row["license_states"] else [],
        "npn": row["npn"],
        "status": row["status"],
        "ytd": row["ytd"],
        "policies": row["policies"],
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def create_session(conn, user_id):
    token = secrets.token_hex(32)
    now = datetime.utcnow()
    expires = now + timedelta(days=SESSION_TTL_DAYS)
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token, user_id, now.isoformat(), expires.isoformat()),
    )
    conn.commit()
    return token


def get_user_from_token(conn, token):
    if not token:
        return None
    row = conn.execute(
        "SELECT s.*, u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
        (token,),
    ).fetchone()
    if not row:
        return None
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        return None
    return row


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "2StrongPortal/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- helpers -----------------------------------------------------------
    def _cookies(self):
        c = SimpleCookie()
        if "Cookie" in self.headers:
            c.load(self.headers["Cookie"])
        return c

    def _session_token(self):
        c = self._cookies()
        if "session" in c:
            return c["session"].value
        return None

    def _current_user(self, conn):
        return get_user_from_token(conn, self._session_token())

    def _cookie_flags(self):
        # Hosting platforms (Render, Railway, etc.) terminate TLS at a proxy
        # and forward plain HTTP to this process, setting X-Forwarded-Proto.
        # If we're being served over HTTPS, use SameSite=None; Secure so the
        # session cookie still works when this app is embedded in an iframe
        # on another domain (e.g. a GHL custom menu link). Over plain HTTP
        # (local dev), SameSite=None without Secure would be rejected by
        # browsers, so fall back to Lax.
        proto = self.headers.get("X-Forwarded-Proto", "")
        if proto.lower() == "https":
            return "SameSite=None; Secure"
        return "SameSite=Lax"

    def _send_json(self, status, payload, set_cookie=None, clear_cookie=False):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if set_cookie:
            self.send_header(
                "Set-Cookie",
                f"session={set_cookie}; Path=/; HttpOnly; Max-Age={SESSION_TTL_DAYS*86400}; {self._cookie_flags()}",
            )
        if clear_cookie:
            self.send_header("Set-Cookie", f"session=; Path=/; HttpOnly; Max-Age=0; {self._cookie_flags()}")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _require_auth(self, conn):
        user = self._current_user(conn)
        if not user:
            self._send_json(401, {"error": "Authentication required"})
            return None
        return user

    # -- static file serving ------------------------------------------------
    # This is a single-file deploy: only index.html is ever served over
    # HTTP. That explicitly keeps db.sqlite3 (password hashes + all business
    # data) and this server's own source from ever being downloadable.
    def _serve_static(self):
        parsed = urllib.parse.urlparse(self.path)
        rel = parsed.path.lstrip("/")
        if rel not in ("", "index.html"):
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found")
            return
        full = os.path.join(FRONTEND_DIR, "index.html")
        if not os.path.isfile(full):
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found")
            return
        ctype, _ = mimetypes.guess_type(full)
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- routing --------------------------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            return self._serve_static()

        conn = get_conn()
        try:
            if path == "/api/auth/me":
                user = self._current_user(conn)
                if not user:
                    return self._send_json(401, {"error": "Not authenticated"})
                return self._send_json(200, {"user": user_public(user)})

            if path == "/api/demo-accounts":
                rows = conn.execute("SELECT username, name, role FROM users ORDER BY id").fetchall()
                return self._send_json(200, {"accounts": [dict(r) for r in rows], "password": "password123"})

            user = self._require_auth(conn)
            if not user:
                return

            if path == "/api/dashboard":
                return self._send_json(200, self._dashboard_payload(conn, user))
            if path == "/api/team":
                return self._send_json(200, {"team": self._team(conn, user)})
            if path == "/api/prospects":
                return self._send_json(200, {"prospects": self._scoped_prospects(conn, user)})
            if path == "/api/clients":
                return self._send_json(200, {"clients": self._scoped_clients(conn, user)})
            if path == "/api/commissions":
                return self._send_json(200, {"commissions": self._scoped_commissions(conn, user)})
            if path == "/api/submitted":
                return self._send_json(200, {"submitted": self._scoped_submitted(conn, user)})
            if path == "/api/eapps":
                return self._send_json(200, {"eapps": self._scoped_eapps(conn, user)})
            if path == "/api/leaderboard":
                return self._send_json(200, {"leaderboard": self._leaderboard(conn)})
            if path == "/api/events":
                rows = conn.execute("SELECT * FROM events ORDER BY id").fetchall()
                return self._send_json(200, {"events": [dict(r) for r in rows]})
            if path == "/api/training":
                return self._send_json(200, {"training": self._training(conn, user)})
            if path == "/api/billing":
                return self._send_json(200, self._billing(conn, user))
            if path == "/api/profile":
                return self._send_json(200, {"user": user_public(user)})

            return self._send_json(404, {"error": "Unknown endpoint"})
        finally:
            conn.close()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        conn = get_conn()
        try:
            if path == "/api/auth/login":
                body = self._read_json_body()
                username = (body.get("username") or "").strip().lower()
                password = body.get("password") or ""
                row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
                if not row:
                    return self._send_json(401, {"error": "Invalid username or password"})
                computed, _ = hash_password(password, row["salt"])
                if computed != row["password_hash"]:
                    return self._send_json(401, {"error": "Invalid username or password"})
                token = create_session(conn, row["id"])
                return self._send_json(200, {"user": user_public(row)}, set_cookie=token)

            if path == "/api/auth/logout":
                token = self._session_token()
                if token:
                    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                    conn.commit()
                return self._send_json(200, {"ok": True}, clear_cookie=True)

            user = self._require_auth(conn)
            if not user:
                return

            body = self._read_json_body()

            if path == "/api/prospects":
                return self._create_prospect(conn, user, body)
            if path == "/api/clients":
                return self._create_client(conn, user, body)
            if path == "/api/submitted":
                return self._create_submitted(conn, user, body)
            if path == "/api/eapps":
                return self._create_eapp(conn, user, body)
            if path == "/api/auth/change-password":
                return self._change_password(conn, user, body)

            return self._send_json(404, {"error": "Unknown endpoint"})
        finally:
            conn.close()

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        conn = get_conn()
        try:
            user = self._require_auth(conn)
            if not user:
                return
            body = self._read_json_body()
            if path == "/api/profile":
                fields = {}
                for key, col in (("phone", "phone"), ("email", "email")):
                    if key in body and body[key]:
                        fields[col] = body[key]
                if fields:
                    set_clause = ", ".join(f"{c} = ?" for c in fields)
                    conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", (*fields.values(), user["id"]))
                    conn.commit()
                updated = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
                return self._send_json(200, {"user": user_public(updated)})
            return self._send_json(404, {"error": "Unknown endpoint"})
        finally:
            conn.close()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def _change_password(self, conn, user, body):
        current = body.get("currentPassword") or ""
        new = body.get("newPassword") or ""
        computed, _ = hash_password(current, user["salt"])
        if computed != user["password_hash"]:
            return self._send_json(401, {"error": "Current password is incorrect"})
        if len(new) < 8:
            return self._send_json(400, {"error": "New password must be at least 8 characters"})
        pw_hash, salt = hash_password(new)
        conn.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (pw_hash, salt, user["id"]))
        # Log out every other session for this user; keep the current one valid.
        current_token = self._session_token()
        conn.execute("DELETE FROM sessions WHERE user_id = ? AND token != ?", (user["id"], current_token))
        conn.commit()
        return self._send_json(200, {"ok": True})

    # -- data assemblers --------------------------------------------------
    def _team(self, conn, user):
        scope = scope_user_ids(conn, user)
        if user["role"] == "Admin":
            rows = conn.execute("SELECT * FROM users WHERE role != 'Admin' ORDER BY ytd DESC").fetchall()
        else:
            ids = scope - {user["id"]}
            if not ids:
                return []
            q = ",".join("?" * len(ids))
            rows = conn.execute(f"SELECT * FROM users WHERE id IN ({q}) ORDER BY ytd DESC", tuple(ids)).fetchall()
        return [user_public(r) for r in rows]

    def _agent_filter_clause(self, conn, user, alias):
        scope = scope_user_ids(conn, user)
        if scope is None:
            return "", ()
        ids = tuple(scope)
        q = ",".join("?" * len(ids))
        return f" WHERE {alias} IN ({q})", ids

    def _scoped_prospects(self, conn, user):
        clause, params = self._agent_filter_clause(conn, user, alias="p.agent_id")
        rows = conn.execute(
            f"SELECT p.*, u.name as agent_name FROM prospects p JOIN users u ON u.id = p.agent_id{clause} ORDER BY p.id DESC",
            params,
        ).fetchall()
        return [self._prospect_json(r) for r in rows]

    def _prospect_json(self, r):
        return {
            "id": r["id"], "name": r["name"], "stage": r["stage"], "source": r["source"],
            "agent": r["agent_name"], "premium": r["premium"], "lastContact": r["last_contact"], "phone": r["phone"],
        }

    def _scoped_clients(self, conn, user):
        clause, params = self._agent_filter_clause(conn, user, alias="c.agent_id")
        rows = conn.execute(
            f"SELECT c.*, u.name as agent_name FROM clients c JOIN users u ON u.id = c.agent_id{clause} ORDER BY c.id DESC",
            params,
        ).fetchall()
        return [{
            "id": r["id"], "name": r["name"], "policyType": r["policy_type"], "carrier": r["carrier"],
            "premium": r["premium"], "status": r["status"], "agent": r["agent_name"], "effective": r["effective"],
        } for r in rows]

    def _scoped_commissions(self, conn, user):
        clause, params = self._agent_filter_clause(conn, user, alias="c.agent_id")
        rows = conn.execute(
            f"SELECT c.*, u.name as agent_name FROM commissions c JOIN users u ON u.id = c.agent_id{clause} ORDER BY c.date DESC, c.id DESC",
            params,
        ).fetchall()
        return [{
            "id": r["id"], "date": r["date"], "client": r["client_name"], "agent": r["agent_name"],
            "carrier": r["carrier"], "product": r["product"], "premium": r["premium"],
            "commission": r["commission"], "status": r["status"],
        } for r in rows]

    def _scoped_submitted(self, conn, user):
        clause, params = self._agent_filter_clause(conn, user, alias="s.agent_id")
        rows = conn.execute(
            f"SELECT s.*, u.name as agent_name FROM submitted_business s JOIN users u ON u.id = s.agent_id{clause} ORDER BY s.id DESC",
            params,
        ).fetchall()
        return [{
            "id": r["id"], "date": r["date"], "client": r["client_name"], "agent": r["agent_name"],
            "carrier": r["carrier"], "product": r["product"], "faceAmount": r["face_amount"], "status": r["status"],
        } for r in rows]

    def _scoped_eapps(self, conn, user):
        clause, params = self._agent_filter_clause(conn, user, alias="e.agent_id")
        rows = conn.execute(
            f"SELECT e.*, u.name as agent_name FROM eapplications e JOIN users u ON u.id = e.agent_id{clause} ORDER BY e.id DESC",
            params,
        ).fetchall()
        return [{
            "id": r["id"], "client": r["client_name"], "agent": r["agent_name"], "carrier": r["carrier"],
            "started": r["started"], "progress": r["progress"], "status": r["status"],
        } for r in rows]

    def _leaderboard(self, conn):
        rows = conn.execute(
            "SELECT * FROM users WHERE role != 'Admin' ORDER BY ytd DESC"
        ).fetchall()
        out = []
        for i, r in enumerate(rows):
            out.append({
                "rank": i + 1, "name": r["name"], "tier": r["tier"], "ytd": r["ytd"],
                "policies": r["policies"], "initials": r["initials"],
            })
        return out

    def _training(self, conn, user):
        rows = conn.execute(
            """SELECT tm.id, tm.title, tm.category, tp.progress, tp.status, tp.due
               FROM training_modules tm JOIN training_progress tp ON tp.training_id = tm.id
               WHERE tp.user_id = ? ORDER BY tm.id""",
            (user["id"],),
        ).fetchall()
        return [dict(r) for r in rows]

    def _billing(self, conn, user):
        rows = conn.execute(
            "SELECT * FROM billing_invoices WHERE user_id = ? ORDER BY id DESC", (user["id"],)
        ).fetchall()
        invoices = [{
            "id": r["id"], "date": r["date"], "desc": r["description"], "amount": r["amount"], "status": r["status"],
        } for r in rows]
        due = next((i for i in invoices if i["status"] != "Paid"), None)
        summary = {
            "planName": "2Strong Pro Agent Bundle",
            "nextChargeDate": due["date"] if due else "—",
            "nextChargeAmount": sum(i["amount"] for i in invoices if i["status"] != "Paid") or 104.0,
            "paymentMethod": "Visa •••• 4471",
        }
        return {"invoices": invoices, "summary": summary}

    def _dashboard_payload(self, conn, user):
        team = self._team(conn, user)
        active_agents = sum(1 for t in team if t["status"] == "Active")
        commissions = self._scoped_commissions(conn, user)
        submitted = self._scoped_submitted(conn, user)
        total_commission = sum(c["commission"] for c in commissions)
        paid_commission = sum(c["commission"] for c in commissions if c["status"] == "Paid")
        approved = sum(1 for s in submitted if s["status"] == "Approved")
        return {
            "teamCount": len(team),
            "activeAgents": active_agents,
            "totalCommission": total_commission,
            "paidCommission": paid_commission,
            "submittedCount": len(submitted),
            "approvedCount": approved,
            "recentCommissions": commissions[:5],
            "leaderboardTop5": self._leaderboard(conn)[:5],
        }

    # -- create endpoints ---------------------------------------------------
    def _create_prospect(self, conn, user, body):
        name = (body.get("name") or "").strip()
        if not name:
            return self._send_json(400, {"error": "Name is required"})
        stage = body.get("stage") or "New Lead"
        source = body.get("source") or "Manual Entry"
        premium = float(body.get("premium") or 0)
        phone = body.get("phone") or ""
        today = datetime.utcnow().strftime("%b %-d, %Y") if os.name != "nt" else datetime.utcnow().strftime("%b %d, %Y")
        cur = conn.execute(
            "INSERT INTO prospects (name, stage, source, agent_id, premium, last_contact, phone, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
            (name, stage, source, user["id"], premium, today, phone),
        )
        conn.commit()
        row = conn.execute(
            "SELECT p.*, u.name as agent_name FROM prospects p JOIN users u ON u.id = p.agent_id WHERE p.id = ?",
            (cur.lastrowid,),
        ).fetchone()
        return self._send_json(201, {"prospect": self._prospect_json(row)})

    def _create_client(self, conn, user, body):
        name = (body.get("name") or "").strip()
        if not name:
            return self._send_json(400, {"error": "Name is required"})
        policy_type = body.get("policyType") or "Term Life"
        carrier = body.get("carrier") or "Pinnacle Mutual"
        premium = float(body.get("premium") or 0)
        status = body.get("status") or "Pending"
        effective = body.get("effective") or "Pending"
        cur = conn.execute(
            "INSERT INTO clients (name, policy_type, carrier, premium, status, agent_id, effective, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
            (name, policy_type, carrier, premium, status, user["id"], effective),
        )
        conn.commit()
        row = conn.execute(
            "SELECT c.*, u.name as agent_name FROM clients c JOIN users u ON u.id = c.agent_id WHERE c.id = ?",
            (cur.lastrowid,),
        ).fetchone()
        return self._send_json(201, {"client": {
            "id": row["id"], "name": row["name"], "policyType": row["policy_type"], "carrier": row["carrier"],
            "premium": row["premium"], "status": row["status"], "agent": row["agent_name"], "effective": row["effective"],
        }})

    def _create_submitted(self, conn, user, body):
        client_name = (body.get("client") or "").strip()
        if not client_name:
            return self._send_json(400, {"error": "Client name is required"})
        carrier = body.get("carrier") or "Pinnacle Mutual"
        product = body.get("product") or "Term Life"
        face_amount = float(body.get("faceAmount") or 0)
        new_id = f"SB-{secrets.randbelow(9000) + 1000}"
        today = datetime.utcnow().strftime("%b %-d, %Y") if os.name != "nt" else datetime.utcnow().strftime("%b %d, %Y")
        conn.execute(
            "INSERT INTO submitted_business (id, date, client_name, agent_id, carrier, product, face_amount, status, created_at) VALUES (?,?,?,?,?,?,?,?,datetime('now'))",
            (new_id, today, client_name, user["id"], carrier, product, face_amount, "In Underwriting"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT s.*, u.name as agent_name FROM submitted_business s JOIN users u ON u.id = s.agent_id WHERE s.id = ?",
            (new_id,),
        ).fetchone()
        return self._send_json(201, {"submitted": {
            "id": row["id"], "date": row["date"], "client": row["client_name"], "agent": row["agent_name"],
            "carrier": row["carrier"], "product": row["product"], "faceAmount": row["face_amount"], "status": row["status"],
        }})

    def _create_eapp(self, conn, user, body):
        client_name = (body.get("client") or "").strip()
        if not client_name:
            return self._send_json(400, {"error": "Client name is required"})
        carrier = body.get("carrier") or "Pinnacle Mutual"
        new_id = f"EA-{secrets.randbelow(9000) + 1000}"
        today = datetime.utcnow().strftime("%b %-d, %Y") if os.name != "nt" else datetime.utcnow().strftime("%b %d, %Y")
        conn.execute(
            "INSERT INTO eapplications (id, client_name, agent_id, carrier, started, progress, status, created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
            (new_id, client_name, user["id"], carrier, today, 5, "Draft"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT e.*, u.name as agent_name FROM eapplications e JOIN users u ON u.id = e.agent_id WHERE e.id = ?",
            (new_id,),
        ).fetchone()
        return self._send_json(201, {"eapp": {
            "id": row["id"], "client": row["client_name"], "agent": row["agent_name"], "carrier": row["carrier"],
            "started": row["started"], "progress": row["progress"], "status": row["status"],
        }})


def main():
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"2Strong Financial portal running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
