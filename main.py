import os
import json
import gzip
import hashlib
import base64
import asyncio
import random
import string
import time
import socket
import hmac
import urllib.request
from aiohttp import web, ClientSession, ClientTimeout, TCPConnector

TARGET_BASE_URL = "https://core-bs.ggpolarbear.com/live/ABHotUpdates/"
VER_PHP_URL = "https://version.ggwhitehawk.com/live/ver.php"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
PORT = int(os.environ.get("PORT", 8080))
SERVE_CACHE_RES = "cache_res2"
REGISTERED_FILE = os.path.join(DATA_DIR, "registered_ips.json")
ENGAGED_FILE = os.path.join(DATA_DIR, "engaged_ips.json")
KEYS_FILE = os.path.join(DATA_DIR, "keys.json")

ADMIN_PATH = "/289fa1d93b1c5ee878dfb46bd0ebe447"
ADMIN_USER = "LUNARXATHEX"
ADMIN_PASS = "#FFHUDT6O3jfr/CBJPo7eO"
ADMIN_COOKIE = "lunar_admin_ok"
KEY_TTL = 86400

SECRET = base64.urlsafe_b64encode(os.urandom(32)).decode()

def make_token(ip, action):
    ts = int(time.time())
    raw = f"{ip}|{action}|{ts}|{SECRET}".encode()
    sig = hashlib.sha256(raw).hexdigest()[:24]
    return f"{ts:x}.{sig}"

def check_token(ip, action, token, max_age=600):
    if not token:
        return False
    try:
        ts_hex, sig = token.split(".", 1)
        ts = int(ts_hex, 16)
    except Exception:
        return False
    now = int(time.time())
    if now - ts > max_age or ts > now:
        return False
    raw = f"{ip}|{action}|{ts}|{SECRET}".encode()
    return hashlib.sha256(raw).hexdigest()[:24] == sig

YT_URL = "https://youtube.com/@hackinjectlab"
TG_URL = "https://t.me/+A8lCW97ZSy1kZDE1"
SHORT_URL = "https://urlking.in/af1294"

ANTI_BAN_OVERRIDES = {
    "FFAntihackDefenceLevel": {"var_type": "string", "var_value": "0"},
    "FFAntihackLightInitOnThread": {"var_type": "bool", "var_value": "false"},
    "FFAntihackEmulatorCheckDisbaledClientVariant": {"var_type": "string", "var_value": ""},
    "FFAntihackSDKDetailEncryptBySHA1": {"var_type": "bool", "var_value": "false"},
    "EnableFFAntihackInfoExtra": {"var_type": "bool", "var_value": "false"},
    "EarlyInitGGP": {"var_type": "bool", "var_value": "false"},
    "DisableGinInfoSend": {"var_type": "int", "var_value": "1"},
    "GinInfoBRAliveThreshold": {"var_type": "int", "var_value": "0"},
    "AntiHackResetSubgameInterval": {"var_type": "int", "var_value": "0"},
    "FFANTIHACKEXT_SPLIT_THRESHOLD": {"var_type": "int", "var_value": "0"},
    "EnablePlatformCheck": {"var_type": "bool", "var_value": "false"},
    "EnableSupCheck": {"var_type": "bool", "var_value": "false"},
    "EnableMMKPlatformCheck": {"var_type": "bool", "var_value": "false"},
}

def get_overrides():
    return dict(ANTI_BAN_OVERRIDES)

_registered = {}

def load_registered():
    global _registered
    try:
        with open(REGISTERED_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _registered = data
        else:
            _registered = {ip: {"key": "", "at": 0} for ip in data}
    except Exception:
        _registered = {}

def save_registered():
    try:
        with open(REGISTERED_FILE, "w") as f:
            json.dump(_registered, f, indent=2)
    except Exception as e:
        print(f"[ERROR] save registered: {e}")

def is_registered(ip):
    return ip in _registered

def register_ip(ip, key=""):
    _registered[ip] = {"key": key, "at": int(time.time())}
    save_registered()

def unregister_ip(ip):
    _registered.pop(ip, None)
    save_registered()

_engaged = {}

def load_engaged():
    global _engaged
    try:
        with open(ENGAGED_FILE, "r") as f:
            _engaged = json.load(f)
    except Exception:
        _engaged = {}

def save_engaged():
    try:
        with open(ENGAGED_FILE, "w") as f:
            json.dump(_engaged, f, indent=2)
    except Exception as e:
        print(f"[ERROR] save engaged: {e}")

def mark_engaged(ip, kind):
    _engaged.setdefault(ip, {})[kind] = True
    save_engaged()

def engagement(ip):
    d = _engaged.get(ip, {})
    return {"yt": bool(d.get("yt")), "tg": bool(d.get("tg")), "short": bool(d.get("short"))}

def steps_done(ip):
    e = engagement(ip)
    return e["yt"] and e["tg"] and e["short"]

_keys = {}

def load_keys():
    global _keys
    try:
        with open(KEYS_FILE, "r") as f:
            _keys = json.load(f)
    except Exception:
        _keys = {}

def save_keys():
    try:
        with open(KEYS_FILE, "w") as f:
            json.dump(_keys, f, indent=2)
    except Exception as e:
        print(f"[ERROR] save keys: {e}")

def get_key(ip):
    now = int(time.time())
    for k, v in _keys.items():
        if v.get("ip") == ip and not v.get("custom") and now <= v.get("expires", 0):
            return k
    return None

def generate_key(ip):
    existing = get_key(ip)
    if existing:
        return existing
    now = int(time.time())
    key = "".join(random.choices(string.ascii_uppercase + string.digits, k=16))
    _keys[key] = {"ip": ip, "created": now, "expires": now + KEY_TTL, "max_ips": 1, "used_ips": [], "custom": False}
    save_keys()
    return key

def can_register_with_key(key, ip):
    v = _keys.get(key)
    if not v:
        return False, "Invalid key. Check the key you pasted and try again."
    if int(time.time()) > v.get("expires", 0):
        return False, "Key expired. Complete the steps again to get a fresh key."
    if ip in v.get("used_ips", []):
        return True, ""
    if len(v.get("used_ips", [])) >= v.get("max_ips", 1):
        return False, "IP limit reached for this key. A key can register only the allowed number of devices/IPs."
    return True, ""

def use_key(key, ip):
    v = _keys[key]
    if ip not in v.get("used_ips", []):
        v["used_ips"].append(ip)
        save_keys()

def client_ip(request):
    for h in ("CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP"):
        val = request.headers.get(h)
        if val:
            return val.strip().split(",")[0].strip()
    return request.remote or ""

def sha1_b64(data):
    return base64.b64encode(hashlib.sha1(data).digest()).decode()

def cache_res_data():
    path = os.path.join(BASE_DIR, SERVE_CACHE_RES)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None

def ensure_cache_res_gzip():
    path = os.path.join(BASE_DIR, SERVE_CACHE_RES)
    if not os.path.exists(path):
        print(f"[!] {SERVE_CACHE_RES} missing")
        return
    with open(path, "rb") as f:
        data = f.read()
    if data and not data.startswith(b"\x1f\x8b"):
        print(f"[WARN] {SERVE_CACHE_RES} not gzip - compressing once and saving to disk")
        with open(path, "wb") as f:
            f.write(gzip.compress(data))

def patch_fileinfo(original_text):
    lines = original_text.splitlines()
    new_lines = []
    cr_line = None
    gz_data = cache_res_data()
    if gz_data is not None:
        try:
            raw_data = gzip.decompress(gz_data)
            cr_line = f"cache_res,{sha1_b64(raw_data)},{len(raw_data)},0,{sha1_b64(gz_data)},{len(gz_data)},True,0"
        except Exception as e:
            print(f"[ERROR] cache_res patch failed: {e}")
    for line in lines:
        if cr_line is not None and line.startswith("cache_res,"):
            new_lines.append(cr_line)
        else:
            new_lines.append(line)
    return "\n".join(new_lines)

def build_fileinfo():
    gz_data = cache_res_data()
    if gz_data is None:
        return None
    raw_data = gzip.decompress(gz_data)
    return f"cache_res,{sha1_b64(raw_data)},{len(raw_data)},0,{sha1_b64(gz_data)},{len(gz_data)},True,0"

def modify_ver_response(response_text, cdn_self, ip):
    try:
        data = json.loads(response_text)
        data["abhotupdate_check"] = "cache_res"
        overrides = get_overrides()
        if overrides:
            gamevar = data.get("gamevar", "")
            for var_name, override in overrides.items():
                gamevar += f"\n{var_name},{var_name},{override['var_type']},{override['var_value']},,"
            data["gamevar"] = gamevar
        data["abhotupdate_cdn_url"] = cdn_self
        data["cdn_url"] = cdn_self
        data["backup_cdn_url"] = cdn_self
        print(f"[VER] {ip} abhotupdate_cdn_url -> {cdn_self}")
        print(f"[VER] {ip} abhotupdate_check: cache_res")
        return json.dumps(data)
    except Exception as e:
        print(f"[ERROR] modify_ver_response: {e}")
        return response_text

PAGE_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ARISU GPT PROXY</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; }
body {
  min-height: 100vh;
  background: linear-gradient(160deg, #0b0218 0%, #1a0b3d 40%, #2b0f52 75%, #0b0218 100%);
  color: #f3efff;
  overflow-x: hidden;
  display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 18px;
}
.blob { position: fixed; border-radius: 50%; filter: blur(70px); opacity: .32; z-index: 0; pointer-events: none; }
.blob.a { width: 420px; height: 420px; background: #8b5cf6; top: -120px; left: -120px; }
.blob.b { width: 380px; height: 380px; background: #d946ef; bottom: -140px; right: -100px; }
.blob.c { width: 300px; height: 300px; background: #6d28d9; top: 45%; left: 62%; }
.wrap { position: relative; z-index: 2; width: 100%; max-width: 560px; text-align: center; }
.badge { font-size: 11px; letter-spacing: 5px; color: #c4b5fd; text-transform: uppercase; margin-bottom: 10px; }
h1 {
  font-size: clamp(30px, 7vw, 56px); font-weight: 800; letter-spacing: 3px; text-align: center;
  background: linear-gradient(90deg, #ffffff, #c4b5fd, #a78bfa);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.sub { text-align: center; color: #a99fc7; margin: 8px 0 26px; font-size: 13px; letter-spacing: 2px; }
.card {
  background: rgba(255,255,255,.06);
  border: 1px solid rgba(196,181,253,.25);
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.06);
  padding: 28px; margin-bottom: 20px; text-align: left;
}
h2 { font-size: 15px; letter-spacing: 2px; margin-bottom: 16px; color: #e9e3ff; text-transform: uppercase; }
.row { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; padding: 11px 4px; font-size: 15px; border-bottom: 1px solid rgba(196,181,253,.12); }
.row:last-child { border-bottom: none; }
.lbl { color: #a99fc7; min-width: 130px; letter-spacing: 1px; text-transform: uppercase; font-size: 11px; }
.val { font-weight: 600; word-break: break-all; }
.ok { color: #4ade80; } .no { color: #fb7185; }
button, .btn {
  width: 100%; padding: 14px; border: none; border-radius: 14px; font-size: 14px; font-weight: 700; letter-spacing: 2px;
  cursor: pointer; color: #fff; margin-top: 14px; text-align: center; text-decoration: none;
  display: flex; align-items: center; justify-content: center; gap: 8px;
  background: linear-gradient(90deg, #7c3aed, #c026d3);
  box-shadow: 0 8px 26px rgba(139,92,246,.45);
  transition: transform .15s, box-shadow .2s, filter .2s;
}
button:hover, .btn:hover { transform: translateY(-2px); filter: brightness(1.08); box-shadow: 0 12px 32px rgba(139,92,246,.6); }
button:disabled { opacity: .4; cursor: not-allowed; transform: none; }
.hint { font-size: 12px; color: #8f85ad; margin-top: 8px; line-height: 1.5; }
.links { display: flex; flex-direction: column; gap: 10px; margin-top: 14px; }
.btn.yt { background: linear-gradient(90deg, #dc2626, #f43f5e); box-shadow: 0 8px 26px rgba(220,38,38,.4); }
.btn.tg { background: linear-gradient(90deg, #0284c7, #38bdf8); box-shadow: 0 8px 26px rgba(2,132,199,.4); }
.btn.short { background: linear-gradient(90deg, #7c3aed, #a855f7); }
.msg { display: none; padding: 12px 14px; border-radius: 12px; font-size: 13px; margin-top: 12px; }
.msg.okm { display: block; background: rgba(74,222,128,.1); border: 1px solid rgba(74,222,128,.3); color: #4ade80; }
.msg.err { display: block; background: rgba(251,113,133,.1); border: 1px solid rgba(251,113,133,.3); color: #fb7185; }
.keybox {
  text-align: center; font-size: 21px; font-weight: 800; letter-spacing: 3px; color: #fff; user-select: all;
  background: linear-gradient(90deg, rgba(124,58,237,.28), rgba(192,38,211,.28));
  border: 1px dashed #a78bfa; border-radius: 14px; padding: 18px 10px; margin: 6px 0 4px;
}
input {
  width: 100%; padding: 14px; border-radius: 12px; border: 1px solid rgba(167,139,250,.4);
  background: rgba(255,255,255,.05); color: #fff; font-size: 15px; letter-spacing: 2px; text-align: center; margin-top: 14px; outline: none;
}
footer { margin-top: 24px; font-size: 11px; color: #6d6489; letter-spacing: 2px; }
footer .credit { display: flex; justify-content: center; gap: 16px; margin-bottom: 8px; font-size: 13px; }
</style>
</head>
<body>
<div class="blob a"></div><div class="blob b"></div><div class="blob c"></div>
<div class="wrap">
  <div class="badge">ARISU GPT GATEWAY</div>
  <h1>ARISU GPT PROXY</h1>
  <div class="sub">SECURE ACCESS &middot; KEY-BASED GATEWAY</div>
__CONTENT__
  <footer>
    <div class="credit">
      <a href="https://youtube.com/@hackinjectlab" target="_blank" rel="noopener" style="color:#fb7185;"><i class="fa-brands fa-youtube"></i>&nbsp; zaru_exe</a>
      <a href="https://t.me/+A8lCW97ZSy1kZDE1" target="_blank" rel="noopener" style="color:#38bdf8;"><i class="fa-brands fa-telegram"></i>&nbsp; Join Telegram</a>
    </div>
    <i class="fa-solid fa-moon"></i> ARISU GPT PROXY &middot; v2.0 &middot; <i class="fa-solid fa-shield-halved"></i> FOR AUTHORIZED USE ONLY
  </footer>
</div>
</body>
</html>"""

KEY_ENTRY_BODY = """<div class="card">
  <h2><i class="fa-solid fa-key"></i>&nbsp; Enter Your Access Key</h2>
  <div class="hint"><i class="fa-solid fa-circle-info"></i>&nbsp; Already have a key? Paste it below and press REGISTER ACCESS.</div>
  <input id="keyInput" placeholder="Paste your key here">
  <button id="regBtn" type="button"><i class="fa-solid fa-shield-halved"></i>&nbsp; REGISTER ACCESS</button>
  <div id="msg" class="msg"></div>
  <div class="hint" style="text-align:center; margin-top:22px;"><i class="fa-solid fa-question-circle"></i>&nbsp; Don't have a key?</div>
  <a class="btn" href="/steps" style="margin-top:10px;"><i class="fa-solid fa-arrow-right"></i>&nbsp; GET KEY</a>
</div>
<script>
document.getElementById('regBtn').addEventListener('click', async function () {
  var m = document.getElementById('msg');
  m.className = 'msg';
  m.textContent = 'Registering...';
  try {
    var k = document.getElementById('keyInput').value.trim().toUpperCase();
    if (!k) { m.className = 'msg err'; m.textContent = 'Paste your key first.'; return; }
    var r = await fetch('/register-access', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: k }) });
    var d = await r.json();
    m.className = 'msg ' + (r.ok ? 'okm' : 'err');
    m.textContent = r.ok ? (d.message || 'Registered') : (d.error || 'Registration failed');
    if (r.ok) setTimeout(function () { window.location.href = '/authorized'; }, 600);
  } catch (e) { m.className = 'msg err'; m.textContent = 'Connection error'; }
});
</script>"""

STEP_BODY = """<div class="card">
  <h2><i class="fa-solid fa-list-check"></i>&nbsp; Complete Steps</h2>
  <div class="row"><span class="lbl"><i class="fa-brands fa-youtube"></i>&nbsp; Step 1</span><span class="val no" id="s1"><i class="fa-regular fa-circle"></i> Not done</span></div>
  <div class="row"><span class="lbl"><i class="fa-brands fa-telegram"></i>&nbsp; Step 2</span><span class="val no" id="s2"><i class="fa-regular fa-circle"></i> Not done</span></div>
  <div class="row"><span class="lbl"><i class="fa-solid fa-link"></i>&nbsp; Step 3</span><span class="val no" id="s3"><i class="fa-regular fa-circle"></i> Not done</span></div>
  <div class="links">
    <a class="btn yt" href="/open/yt?t=__YT__" target="_blank" rel="noopener"><i class="fa-brands fa-youtube"></i>&nbsp; SUBSCRIBE ON YOUTUBE</a>
    <a class="btn tg" href="/open/tg?t=__TG__" target="_blank" rel="noopener"><i class="fa-brands fa-telegram"></i>&nbsp; JOIN ON TELEGRAM</a>
    <a class="btn short" href="/open/short?t=__SHORT__" target="_blank" rel="noopener"><i class="fa-solid fa-link"></i>&nbsp; COMPLETE SHORTENER</a>
  </div>
  <button id="keyBtn" type="button" disabled><i class="fa-solid fa-key"></i>&nbsp; GET YOUR ACCESS KEY</button>
  <div id="vmsg" class="msg"></div>
</div>
<script>
function setStep(id, done) {
  var el = document.getElementById(id);
  el.innerHTML = done ? '<i class="fa-solid fa-circle-check"></i> Done' : '<i class="fa-regular fa-circle"></i> Not done';
  el.className = 'val ' + (done ? 'ok' : 'no');
}
async function poll() {
  try {
    var r = await fetch('/status');
    var s = await r.json();
    setStep('s1', s.yt);
    setStep('s2', s.tg);
    setStep('s3', s.short);
    document.getElementById('keyBtn').disabled = !s.steps_done;
    if (s.registered) window.location.href = '/authorized';
  } catch (e) {}
}
document.getElementById('keyBtn').addEventListener('click', function () {
  window.location.href = '/key';
});
poll();
setInterval(poll, 6000);
</script>"""

KEY_BODY = """<div class="card">
  <h2><i class="fa-solid fa-key"></i>&nbsp; Your Access Key</h2>
  <div class="keybox">__KEY__</div>
  <button id="copyBtn" type="button"><i class="fa-solid fa-copy"></i>&nbsp; COPY KEY</button>
  <div class="hint"><i class="fa-solid fa-circle-info"></i>&nbsp; This key is valid for 24 hours. Copy it, then paste it below and press REGISTER ACCESS.</div>
  <input id="keyInput" placeholder="Paste your key here">
  <button id="regBtn" type="button"><i class="fa-solid fa-shield-halved"></i>&nbsp; REGISTER ACCESS</button>
  <div id="msg" class="msg"></div>
</div>
<script>
var key = '__KEY__';
document.getElementById('copyBtn').addEventListener('click', function () {
  var m = document.getElementById('msg');
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(key).then(function () { m.className = 'msg okm'; m.textContent = 'Key copied! Paste it below and register.'; });
  } else {
    m.className = 'msg okm'; m.textContent = 'Select the key above and copy it manually.';
  }
});
document.getElementById('regBtn').addEventListener('click', async function () {
  var m = document.getElementById('msg');
  m.className = 'msg';
  m.textContent = 'Registering...';
  try {
    var k = document.getElementById('keyInput').value.trim().toUpperCase();
    if (!k) { m.className = 'msg err'; m.textContent = 'Paste your key first.'; return; }
    var r = await fetch('/register-access', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: k }) });
    var d = await r.json();
    m.className = 'msg ' + (r.ok ? 'okm' : 'err');
    m.textContent = r.ok ? (d.message || 'Registered') : (d.error || 'Registration failed');
    if (r.ok) setTimeout(function () { window.location.href = '/authorized'; }, 600);
  } catch (e) { m.className = 'msg err'; m.textContent = 'Connection error'; }
});
</script>"""

AUTH_BODY = """<div class="card">
  <h2><i class="fa-solid fa-user-check"></i>&nbsp; IP REGISTERED</h2>
  <div class="row"><span class="lbl"><i class="fa-solid fa-fire"></i>&nbsp; Mode</span><span class="val ok">HS CHEST</span></div>
  <div class="row"><span class="lbl"><i class="fa-solid fa-server"></i>&nbsp; IP</span><span class="val">__IP__</span></div>
  <div class="hint"><i class="fa-solid fa-circle-check"></i>&nbsp; Your IP is REGISTERED. Now open the game and connect through the proxy — settings are applied automatically.</div>
</div>"""

ADMIN_BODY = """<style>
.stats { display: flex; flex-wrap: wrap; gap: 10px; }
.stat {
  flex: 1; min-width: 110px; text-align: center; padding: 14px 8px; border-radius: 14px;
  background: rgba(255,255,255,.05); border: 1px solid rgba(196,181,253,.2);
}
.stat b { display: block; font-size: 24px; letter-spacing: 2px; }
.stat span { font-size: 10px; color: #a99fc7; text-transform: uppercase; letter-spacing: 1px; }
</style>
<div class="card">
  <h2><i class="fa-solid fa-user-shield"></i>&nbsp; Admin Panel</h2>
  <div class="stats">
    <div class="stat"><b>__TOTAL__</b><span>Total keys</span></div>
    <div class="stat"><b class="ok">__ACTIVE__</b><span>Active keys</span></div>
    <div class="stat"><b>__USERS__</b><span>Users</span></div>
  </div>
</div>
<div class="card">
  <h2><i class="fa-solid fa-wand-magic-sparkles"></i>&nbsp; Create Custom Key</h2>
  <div class="hint"><i class="fa-solid fa-circle-info"></i>&nbsp; Custom keys are not tied to any device. Set an IP limit and how long the key stays valid.</div>
  <input id="maxIps" type="number" min="1" value="1" placeholder="IP limit">
  <input id="days" type="number" min="0" value="1" placeholder="Valid days">
  <input id="hours" type="number" min="0" value="0" placeholder="Valid hours">
  <button id="mkBtn" type="button"><i class="fa-solid fa-key"></i>&nbsp; CREATE KEY</button>
  <div id="cmsg" class="msg"></div>
</div>
<div class="card">
  <h2><i class="fa-solid fa-key"></i>&nbsp; Generated Keys</h2>
  __KEYROWS__
</div>
<div class="card">
  <h2><i class="fa-solid fa-users"></i>&nbsp; Registered Users</h2>
  __USERROWS__
</div>
<script>
document.getElementById('mkBtn').addEventListener('click', async function () {
  var m = document.getElementById('cmsg');
  m.className = 'msg';
  m.textContent = 'Creating...';
  try {
    var fd = new FormData();
    fd.append('max_ips', document.getElementById('maxIps').value || 1);
    fd.append('days', document.getElementById('days').value || 0);
    fd.append('hours', document.getElementById('hours').value || 0);
    var r = await fetch('__ADMIN__/create', { method: 'POST', body: fd });
    var d = await r.json();
    if (r.ok) {
      m.className = 'msg okm';
      m.textContent = 'Custom key created: ' + d.key + ' — limit ' + d.max_ips + ' IP, valid ' + d.valid_hours + 'h. Reload the panel to see it.';
    } else {
      m.className = 'msg err';
      m.textContent = d.error || 'Failed to create key';
    }
  } catch (e) { m.className = 'msg err'; m.textContent = 'Connection error'; }
});
</script>"""


def render_page(body, ip):
    return PAGE_SHELL.replace("__CONTENT__", body.replace("__IP__", ip or "unknown"))

load_registered()
load_engaged()
load_keys()

app = web.Application()

@web.middleware
async def ip_gate(request, handler):
    path = request.path
    if path in ("/", "/steps", "/key", "/authorized", "/get-key", "/register-access", "/status", "/favicon.ico", ADMIN_PATH, ADMIN_PATH + "/login", ADMIN_PATH + "/create") or path.startswith("/open/"):
        return await handler(request)
    ip = client_ip(request)
    if not is_registered(ip):
        return web.json_response({"error": "Access denied: your IP is not registered. Open / to authorize your device."}, status=403)
    return await handler(request)

app.middlewares.append(ip_gate)

async def init_session(app):
    connector = TCPConnector(limit=100, ttl_dns_cache=300)
    timeout = ClientTimeout(total=60, connect=10)
    app['session'] = ClientSession(connector=connector, timeout=timeout)

async def cleanup_session(app):
    await app['session'].close()

async def handle_root(request):
    ip = client_ip(request)
    if is_registered(ip):
        return web.Response(status=302, headers={"Location": "/authorized"})
    return web.Response(text=render_page(KEY_ENTRY_BODY, ip), content_type='text/html', charset='utf-8')

async def handle_steps(request):
    ip = client_ip(request)
    if is_registered(ip):
        return web.Response(status=302, headers={"Location": "/authorized"})
    body = (STEP_BODY
            .replace("__YT__", make_token(ip, "yt"))
            .replace("__TG__", make_token(ip, "tg"))
            .replace("__SHORT__", make_token(ip, "short")))
    return web.Response(text=render_page(body, ip), content_type='text/html', charset='utf-8')

async def handle_authorized(request):
    ip = client_ip(request)
    if not is_registered(ip):
        return web.Response(status=302, headers={"Location": "/"})
    return web.Response(text=render_page(AUTH_BODY, ip), content_type='text/html', charset='utf-8')

async def handle_key_page(request):
    ip = client_ip(request)
    if is_registered(ip):
        return web.Response(status=302, headers={"Location": "/authorized"})
    if not steps_done(ip):
        return web.Response(status=302, headers={"Location": "/"})
    key = generate_key(ip)
    return web.Response(text=render_page(KEY_BODY.replace("__KEY__", key), ip), content_type='text/html', charset='utf-8')

async def handle_get_key(request):
    ip = client_ip(request)
    if not steps_done(ip):
        return web.json_response({"error": "Complete ALL steps first: subscribe on YouTube, join on Telegram, and finish the shortener."}, status=403)
    key = generate_key(ip)
    print(f"[KEY] {ip}: {key}")
    return web.json_response({"success": True, "key": key})

async def handle_register_access(request):
    ip = client_ip(request)
    if is_registered(ip):
        return web.json_response({"success": True, "message": "Already registered", "registered": True})
    try:
        data = await request.json()
        key = (data.get("key") or "").strip().upper()
    except Exception:
        return web.json_response({"error": "Invalid request"}, status=400)
    if not key:
        return web.json_response({"error": "Paste your access key first."}, status=400)
    ok, err = can_register_with_key(key, ip)
    if not ok:
        print(f"[AUTH] rejected {ip} key={key}: {err}")
        return web.json_response({"error": err}, status=403)
    register_ip(ip, key)
    use_key(key, ip)
    print(f"[AUTH] IP REGISTERED with key: {ip} key={key}")
    return web.json_response({"success": True, "message": f"IP {ip} REGISTERED", "registered": True})

def admin_logged_in(request):
    return request.cookies.get(ADMIN_COOKIE) == "1"

ADMIN_LOGIN_BODY = """<div class="card">
  <h2><i class="fa-solid fa-user-shield"></i>&nbsp; Admin Login</h2>
  <input id="user" type="text" placeholder="Username" autocomplete="username">
  <input id="pass" type="password" placeholder="Password" autocomplete="current-password">
  <button id="loginBtn" type="button"><i class="fa-solid fa-right-to-bracket"></i>&nbsp; LOGIN</button>
  <div id="msg" class="msg"></div>
</div>
<script>
document.getElementById('loginBtn').addEventListener('click', async function () {
  var m = document.getElementById('msg');
  m.className = 'msg';
  m.textContent = 'Logging in...';
  try {
    var fd = new FormData();
    fd.append('user', document.getElementById('user').value);
    fd.append('pass', document.getElementById('pass').value);
    var r = await fetch('__ADMIN__/login', { method: 'POST', body: fd });
    var d = await r.json();
    if (r.ok) {
      m.className = 'msg okm';
      m.textContent = 'Login successful. Loading panel...';
      setTimeout(function () { window.location.href = '__ADMIN__'; }, 500);
    } else {
      m.className = 'msg err';
      m.textContent = d.error || 'Login failed';
    }
  } catch (e) { m.className = 'msg err'; m.textContent = 'Connection error'; }
});
</script>"""

async def handle_admin_login(request):
    try:
        data = await request.post()
        user = data.get("user", "")
        pwd = data.get("pass", "")
    except Exception:
        return web.json_response({"error": "Invalid request"}, status=400)
    if user == ADMIN_USER and pwd == ADMIN_PASS:
        print(f"[ADMIN] logged in: {user}")
        resp = web.json_response({"success": True})
        resp.set_cookie(ADMIN_COOKIE, "1", max_age=12 * 3600, httponly=True, samesite="strict")
        return resp
    print(f"[ADMIN] failed login attempt for {user}")
    return web.json_response({"error": "Invalid username or password"}, status=403)

async def handle_admin(request):
    ip = client_ip(request)
    if not admin_logged_in(request):
        body = ADMIN_LOGIN_BODY.replace("__ADMIN__", ADMIN_PATH)
        return web.Response(text=render_page(body, ip), content_type='text/html', charset='utf-8')
    now = int(time.time())
    total = len(_keys)
    active = sum(1 for v in _keys.values() if v.get("used_ips"))
    users = len(_registered)

    key_rows = ""
    items = sorted(_keys.items(), key=lambda kv: kv[1].get("created", 0), reverse=True)
    for k, v in items:
        exp = v.get("expires", 0)
        remain = exp - now
        if remain <= 0:
            status = '<span class="no">EXPIRED</span>'
        else:
            h, m = remain // 3600, (remain % 3600) // 60
            status = f'<span class="ok">ACTIVE</span> ({h}h {m}m left)'
        src = "ADMIN" if v.get("custom") else "SHORTENER"
        used = len(v.get("used_ips", []))
        lim = v.get("max_ips", 1)
        key_rows += f'<div class="row"><span class="lbl">{k}</span><span class="val">{src} &middot; {used}/{lim} IP &middot; {status}</span></div>'

    user_rows = ""
    for uip, info in sorted(_registered.items(), key=lambda kv: (kv[1].get("at", 0) if isinstance(kv[1], dict) else 0), reverse=True):
        k = info.get("key", "") if isinstance(info, dict) else ""
        user_rows += f'<div class="row"><span class="lbl">{uip}</span><span class="val">{k or "legacy"}</span></div>'

    body = (ADMIN_BODY
            .replace("__ADMIN__", ADMIN_PATH)
            .replace("__TOTAL__", str(total))
            .replace("__ACTIVE__", str(active))
            .replace("__USERS__", str(users))
            .replace("__KEYROWS__", key_rows if key_rows else '<div class="hint">No keys yet.</div>')
            .replace("__USERROWS__", user_rows if user_rows else '<div class="hint">No registered users yet.</div>'))
    return web.Response(text=render_page(body, ip), content_type='text/html', charset='utf-8')

async def handle_admin_create(request):
    if not admin_logged_in(request):
        return web.json_response({"error": "Not authorized. Log in to the admin panel first."}, status=403)
    try:
        data = await request.post()
        max_ips = int(data.get("max_ips", 1))
        days = int(data.get("days", 0))
        hours = int(data.get("hours", 0))
    except Exception:
        return web.json_response({"error": "Invalid input"}, status=400)
    if max_ips < 1:
        max_ips = 1
    valid_secs = days * 86400 + hours * 3600
    if valid_secs < 3600:
        valid_secs = 86400
    now = int(time.time())
    key = "".join(random.choices(string.ascii_uppercase + string.digits, k=16))
    _keys[key] = {"ip": "admin", "created": now, "expires": now + valid_secs, "max_ips": max_ips, "used_ips": [], "custom": True}
    save_keys()
    print(f"[ADMIN] custom key created: {key} limit={max_ips} valid={valid_secs}s")
    return web.json_response({"success": True, "key": key, "max_ips": max_ips, "valid_hours": valid_secs // 3600})

_short_pending = {}

async def handle_open_yt(request):
    ip = client_ip(request)
    tok = request.query.get("t")
    if not check_token(ip, "yt", tok):
        print(f"[BOT] {ip} yt missing/invalid token")
        return web.Response(status=403, text="Invalid or expired step link. Go back to the steps page and try again.")
    mark_engaged(ip, "yt")
    print(f"[AUTH] youtube opened: {ip}")
    return web.Response(status=302, headers={"Location": YT_URL})

async def handle_open_tg(request):
    ip = client_ip(request)
    tok = request.query.get("t")
    if not check_token(ip, "tg", tok):
        print(f"[BOT] {ip} tg missing/invalid token")
        return web.Response(status=403, text="Invalid or expired step link. Go back to the steps page and try again.")
    if not engagement(ip)["yt"]:
        print(f"[BOT] {ip} tg before yt")
        return web.Response(status=403, text="Complete step 1 (YouTube) first.")
    mark_engaged(ip, "tg")
    print(f"[AUTH] telegram opened: {ip}")
    return web.Response(status=302, headers={"Location": TG_URL})

async def handle_open_short(request):
    ip = client_ip(request)
    tok = request.query.get("t")
    if not check_token(ip, "short", tok):
        print(f"[BOT] {ip} short missing/invalid token")
        return web.Response(status=403, text="Invalid or expired step link. Go back to the steps page and try again.")
    if not (engagement(ip)["yt"] and engagement(ip)["tg"]):
        print(f"[BOT] {ip} short before yt/tg")
        return web.Response(status=403, text="Complete step 1 and 2 first.")
    _short_pending[ip] = int(time.time())
    print(f"[AUTH] shortener opened (waiting for return): {ip}")
    return web.Response(status=302, headers={"Location": SHORT_URL})

async def handle_short_return(request):
    ip = client_ip(request)
    start = _short_pending.get(ip)
    if start is None:
        print(f"[BOT] {ip} short return without opening")
        return web.Response(status=403, text="Open the shortener link first, let the ad finish, then come back here.")
    if int(time.time()) - start < 12:
        print(f"[BOT] {ip} short return too fast ({int(time.time()) - start}s)")
        return web.Response(status=403, text="Too fast. Let the shortener page finish loading, then retry.")
    _short_pending.pop(ip, None)
    mark_engaged(ip, "short")
    print(f"[AUTH] shortener completed via return: {ip}")
    return web.Response(status=302, headers={"Location": "/"})

async def handle_status(request):
    ip = client_ip(request)
    e = engagement(ip)
    return web.json_response({
        "ip": ip,
        "yt": e["yt"],
        "tg": e["tg"],
        "short": e["short"],
        "steps_done": steps_done(ip),
        "registered": is_registered(ip),
    })

async def handle_ver_php(request):
    session = request.app['session']
    params = dict(request.query)
    ip = client_ip(request)
    cdn_self = f"http://{request.host}/cdn/live/ABHotUpdates/"
    print(f"[REQUEST] ver.php {ip} {params}")
    try:
        async with session.get(VER_PHP_URL, params=params) as resp:
            text = await resp.text()
            modified = modify_ver_response(text, cdn_self, ip)
            print(f"[RESPONSE] ver.php status: {resp.status}")
            return web.Response(text=modified, content_type='application/json')
    except Exception as e:
        print(f"[ERROR] ver.php: {e}")
        return web.Response(text='Error', status=502)

async def handle_cdn(request):
    session = request.app['session']
    ip = client_ip(request)
    path = request.match_info.get('path', '')

    if not path or path == '/':
        print(f"[CDN] Empty path request")
        return web.Response(text='Not found', status=404)

    print(f"[CDN] {ip} Request: {path}")

    for prefix in ("cdn/live/ABHotUpdates/", "cdn/", "llive/ABHotUpdates/", "live/ABHotUpdates/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break

    upstream = TARGET_BASE_URL
    if not upstream.endswith("/"):
        upstream += "/"

    if "cache_res" in path and "avatar" not in path:
        gz_data = cache_res_data()
        if gz_data is not None:
            print(f"[CDN] {ip} Serving local {SERVE_CACHE_RES}")
            return web.Response(body=gz_data, content_type='application/octet-stream')

    if "fileinfo" in path:
        target_url = upstream + path
        print(f"[CDN] {ip} Proxying fileinfo: {target_url}")
        try:
            async with session.get(target_url) as resp:
                text = await resp.text()
                print(f"[CDN] fileinfo received: {len(text)} bytes (status {resp.status})")
                patched = patch_fileinfo(text)
                if resp.status == 200 and "cache_res," in patched:
                    if patched != text:
                        print(f"[CDN] {ip} fileinfo cache_res line patched")
                    return web.Response(body=patched.encode(), content_type='binary/octet-stream')
        except Exception as e:
            print(f"[ERROR] fileinfo upstream: {e}")
        local_fi = build_fileinfo()
        if local_fi:
            print(f"[CDN] {ip} Serving locally built fileinfo")
            return web.Response(body=local_fi.encode(), content_type='binary/octet-stream')
        return web.Response(text='Error', status=502)

    target_url = upstream + path
    print(f"[CDN] {ip} Proxying: {target_url}")
    try:
        async with session.get(target_url) as resp:
            body = await resp.read()
            print(f"[CDN] Response: {resp.status}, {len(body)} bytes")
            return web.Response(body=body, status=resp.status, content_type=resp.headers.get('content-type', 'application/octet-stream'))
    except Exception as e:
        print(f"[ERROR] cdn: {e}")
        return web.Response(text='Error', status=502)

app.router.add_get('/', handle_root)
app.router.add_get('/steps', handle_steps)
app.router.add_get('/key', handle_key_page)
app.router.add_get('/authorized', handle_authorized)
app.router.add_post('/get-key', handle_get_key)
app.router.add_post('/register-access', handle_register_access)
app.router.add_get(ADMIN_PATH, handle_admin)
app.router.add_post(ADMIN_PATH + '/login', handle_admin_login)
app.router.add_post(ADMIN_PATH + '/create', handle_admin_create)
app.router.add_get('/open/yt', handle_open_yt)
app.router.add_get('/open/tg', handle_open_tg)
app.router.add_get('/open/short', handle_open_short)
app.router.add_get('/open/short-return', handle_short_return)
app.router.add_get('/status', handle_status)
app.router.add_get('/ver.php', handle_ver_php)
app.router.add_get('/live/ver.php', handle_ver_php)
app.router.add_get('/cdn/live/ABHotUpdates/', handle_cdn)
app.router.add_get('/cdn/live/ABHotUpdates/{path:.*}', handle_cdn)
app.router.add_get('/{path:.*}', handle_cdn)

app.on_startup.append(init_session)
app.on_cleanup.append(cleanup_session)

SERVER_IP = "localhost"

if __name__ == "__main__":
    load_registered()
    load_engaged()
    load_keys()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        SERVER_IP = s.getsockname()[0]
        s.close()
    except Exception:
        SERVER_IP = "127.0.0.1"
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=8) as r:
            PUBLIC_IP = r.read().decode().strip()
    except Exception:
        PUBLIC_IP = SERVER_IP

    print("[*] ARISU GPT PROXY")
    print(f"[*] SERVER IP: {SERVER_IP}")
    print(f"[*] PUBLIC IP: {PUBLIC_IP}")
    print(f"[*] PUBLIC URL: http://{PUBLIC_IP}:{PORT}")
    print(f"[*] Panel: http://{PUBLIC_IP}:{PORT}")
    print(f"[*] CDN -> {TARGET_BASE_URL}")
    print(f"[*] ver.php -> {VER_PHP_URL}")
    print(f"[*] Injecting {len(get_overrides())} anti-ban overrides")
    print("[*] Mode: HS CHEST ({SERVE_CACHE_RES})")
    print("[*] Access: complete 3 steps -> GET KEY -> register with key")
    print(f"[*] Authorized IPs: {sorted(_registered) if _registered else 'none — open the page to register'}")
    print(f"[*] Keys issued: {len(_keys)}")
    print(f"[*] Admin panel: http://{PUBLIC_IP}:{PORT}{ADMIN_PATH}")
    print(f"[*] Verify gate: subscribe {YT_URL} and join {TG_URL}")
    ensure_cache_res_gzip()
    print(f"[*] cache_res: {'loaded' if os.path.exists(os.path.join(BASE_DIR, SERVE_CACHE_RES)) else 'missing'} ({SERVE_CACHE_RES})")
    print("[*] Waiting for requests...")
    web.run_app(app, host="0.0.0.0", port=PORT, access_log=None)
