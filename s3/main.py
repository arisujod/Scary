import os, json, gzip, hashlib, base64, random, string, time, socket
from datetime import datetime
import requests as req
from flask import Flask, request, jsonify, render_template, session, Response

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'gpt-secret-key-change-me')

# ================= CONFIG =================
TARGET_BASE_URL = "https://dl.bs.freefiremobile.com/live/ABHotUpdates/"
VER_PHP_URL = "https://version.ggwhitehawk.com/live/ver.php"
TG_URL = "https://t.me/+HZmbe_GbIf0xZGVl"
YT_URL = "https://youtube.com/@zaru_exe?si=VGZw3cZDbpfD4Ann"
IG_URL = "https://instagram.com"
ADMIN_USER = "S3HACKSADMIN"
ADMIN_PASS = "#FFHUDT6O3j2mo8RBPo7eO"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "s3hacks_data.json")
PORT = int(os.environ.get("PORT", 6767))

# ================= DATA =================
user_configs = {}
registered_ips = {}
generated_keys = {}
resellers = {}
credit_rates = []
maintenance_mode = False

DEFAULT_RATES = [
    {"duration": 180, "cost": 1}, {"duration": 1440, "cost": 4},
    {"duration": 10080, "cost": 12}, {"duration": 43200, "cost": 30},
    {"duration": 99999999, "cost": 60},
]

DEFAULT_CONFIG = {
    "HS_NECK": True,
    "HS_CHEST": False,
    "BYPASSV1": True,
    "BACKJUMPV1": True,
    "HIGH_SENSI": True,
}

# ================= FIREBASE =================
FIREBASE_CRED = os.environ.get("FIREBASE_CREDENTIALS", "")
FIREBASE_URL = os.environ.get("FIREBASE_DB_URL", "")
_fb = None
try:
    import firebase_admin
    from firebase_admin import credentials as _fbc
    from firebase_admin import db as _fbd
    if FIREBASE_CRED and FIREBASE_URL:
        firebase_admin.initialize_app(_fbc.Certificate(json.loads(FIREBASE_CRED)), {"databaseURL": FIREBASE_URL})
        _fb = _fbd.reference("s3hacks")
        print("[*] Firebase connected (s3 db)")
except Exception as e:
    print(f"[ERROR] Firebase init: {e}")

def _data_dict():
    return {"user_configs": user_configs, "registered_ips": registered_ips,
            "generated_keys": generated_keys, "resellers": resellers,
            "credit_rates": credit_rates, "maintenance_mode": maintenance_mode}

def save_data():
    try:
        with open(DATA_FILE, "w") as f: json.dump(_data_dict(), f, indent=2)
    except Exception as e: print(f"[ERROR] save file: {e}")
    if _fb:
        try: _fb.set(_data_dict())
        except Exception as e: print(f"[ERROR] firebase push: {e}")

def load_data():
    global user_configs, registered_ips, generated_keys, resellers, credit_rates, maintenance_mode
    d = None
    if _fb:
        try: d = _fb.get()
        except Exception as e: print(f"[ERROR] fb load: {e}")
    if not d and os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f: d = json.load(f)
        except Exception: d = None
    d = d or {}
    user_configs = d.get("user_configs", {})
    registered_ips = d.get("registered_ips", {})
    generated_keys = d.get("generated_keys", {})
    resellers = d.get("resellers", {})
    credit_rates = d.get("credit_rates", []) or list(DEFAULT_RATES)
    maintenance_mode = d.get("maintenance_mode", False)
    print(f"[*] Loaded: {len(generated_keys)} keys, {len(resellers)} resellers, {len(registered_ips)} IPs")

# ================= HELPERS =================
def get_client_ip():
    for h in ("CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP"):
        v = request.headers.get(h)
        if v: return v.strip().split(",")[0].strip()
    return request.remote_addr or ""

def now(): return time.time()
def gen_key(): return "Gpt-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
def fmt_ts(ts):
    if not ts: return "—"
    return datetime.fromtimestamp(ts).strftime("%d %b, %H:%M")
def key_expired(v): return v.get("expires") is not None and now() > v.get("expires")
def key_active(ip):
    r = registered_ips.get(ip)
    if not r: return False
    v = generated_keys.get(r.get("key"))
    return bool(v) and not key_expired(v) and not v.get("paused")
def keys_list(only_reseller=None):
    out = []
    for k, v in generated_keys.items():
        if only_reseller and v.get("reseller") != only_reseller: continue
        out.append({"key": k, "owner": v.get("reseller", "ADMIN"),
                    "used": len(v.get("used_ips", [])), "limit": v.get("limit", 1),
                    "expired": key_expired(v), "exp": fmt_ts(v.get("expires")),
                    "paused": bool(v.get("paused"))})
    return out

def get_user_config(client_ip):
    if client_ip not in user_configs:
        user_configs[client_ip] = DEFAULT_CONFIG.copy()
        save_data()
    return user_configs[client_ip]

# ================= OVERRIDES =================
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
BACKJUMPV1_OVERRIDES = {
    "EnableAccelerationOnFalling": {"var_type": "bool", "var_value": "false"},
    "CanJumpFallingRunFast": {"var_type": "bool", "var_value": "false"},
    "CanCreepRunFast": {"var_type": "bool", "var_value": "false"},
    "CanCrouchingRunFast": {"var_type": "bool", "var_value": "false"},
    "StropFallingResetSpeed": {"var_type": "bool", "var_value": "true"},
}
HIGH_SENSI_OVERRIDES = {
    "SensitivityMaxSetting": {"var_type": "float", "var_value": "9.0"},
    "Sensitivity1PMaxSetting": {"var_type": "float", "var_value": "9.0"},
    "X1ScopeMaxSetting": {"var_type": "float", "var_value": "9.0"},
    "X2ScopeMaxSetting": {"var_type": "float", "var_value": "9.0"},
    "X4ScopeMaxSetting": {"var_type": "float", "var_value": "9.0"},
    "X8ScopeMaxSetting": {"var_type": "float", "var_value": "9.0"},
    "FreeLookMaxSetting": {"var_type": "float", "var_value": "9.0"},
}

def get_overrides_for_ip(client_ip):
    config = get_user_config(client_ip)
    overrides = {}
    if config.get("BYPASSV1"): overrides.update(ANTI_BAN_OVERRIDES)
    if config.get("BACKJUMPV1"): overrides.update(BACKJUMPV1_OVERRIDES)
    if config.get("HIGH_SENSI"): overrides.update(HIGH_SENSI_OVERRIDES)
    return overrides

# ================= PROXY FILES =================
def sha1_b64(data): return base64.b64encode(hashlib.sha1(data).digest()).decode()

def read_gz(name):
    p = os.path.join(BASE_DIR, name)
    if os.path.exists(p):
        with open(p, "rb") as f: return f.read()
    return None

def ensure_gz():
    for name in ("cache_res", "cache_res2"):
        p = os.path.join(BASE_DIR, name)
        if not os.path.exists(p): print(f"[!] {name} missing"); continue
        with open(p, "rb") as f: data = f.read()
        if data and not data.startswith(b"\x1f\x8b"):
            with open(p, "wb") as f: f.write(gzip.compress(data))

def modify_ver_response(text, cdn_self, ip):
    try:
        data = json.loads(text)
        data["abhotupdate_check"] = "cache_res"
        gv = data.get("gamevar", "")
        for n, o in get_overrides_for_ip(ip).items():
            gv += f"\n{n},{n},{o['var_type']},{o['var_value']},,"
        data["gamevar"] = gv
        data["abhotupdate_cdn_url"] = cdn_self
        data["cdn_url"] = cdn_self
        data["backup_cdn_url"] = cdn_self
        print(f"[VER] {ip} -> {cdn_self}")
        return json.dumps(data)
    except Exception as e:
        print(f"[ERROR] ver: {e}"); return text

def patch_fileinfo(text, config):
    name = None
    if config.get("HS_NECK"): name = "cache_res"
    elif config.get("HS_CHEST"): name = "cache_res2"
    if not name: return text
    gz = read_gz(name)
    if not gz: return text
    try:
        raw = gzip.decompress(gz)
        cr = f"cache_res,{sha1_b64(raw)},{len(raw)},0,{sha1_b64(gz)},{len(gz)},True,0"
        return "\n".join(cr if ln.startswith("cache_res,") else ln for ln in text.splitlines())
    except Exception: return text

def build_fileinfo(config):
    name = None
    if config.get("HS_NECK"): name = "cache_res"
    elif config.get("HS_CHEST"): name = "cache_res2"
    if not name: return None
    gz = read_gz(name)
    if not gz: return None
    raw = gzip.decompress(gz)
    return f"cache_res,{sha1_b64(raw)},{len(raw)},0,{sha1_b64(gz)},{len(gz)},True,0"

# ================= USER ROUTES =================
@app.route('/')
def index():
    ip = get_client_ip()
    if key_active(ip): return Response(status=302, headers={"Location": "/dashboard"})
    return render_template("user_login.html", TG_URL=TG_URL, YT_URL=YT_URL, IG_URL=IG_URL)

@app.route('/api/activate', methods=['POST'])
def activate():
    ip = get_client_ip()
    d = request.get_json(silent=True) or {}
    key = (d.get("key") or "").strip()
    v = generated_keys.get(key)
    if maintenance_mode and ip not in registered_ips:
        return jsonify({"error": "Maintenance mode ON — try later"}), 403
    if not v: return jsonify({"error": "Invalid key"}), 403
    if v.get("paused"): return jsonify({"error": "Key paused by admin"}), 403
    if key_expired(v): return jsonify({"error": "Key expired"}), 403
    if ip not in v.get("used_ips", []):
        if len(v.get("used_ips", [])) >= v.get("limit", 1):
            return jsonify({"error": "IP limit reached for this key"}), 403
        v.setdefault("used_ips", []).append(ip)
    if v.get("expires") is None:
        v["expires"] = now() + v.get("duration", 43200) * 60
    registered_ips[ip] = {"key": key, "at": now()}
    get_user_config(ip)
    save_data()
    print(f"[AUTH] {ip} activated {key}")
    return jsonify({"ok": True})

@app.route('/dashboard')
def dashboard():
    ip = get_client_ip()
    r = registered_ips.get(ip)
    if not r or not key_active(ip):
        return Response(status=302, headers={"Location": "/"})
    v = generated_keys.get(r.get("key"), {})
    return render_template("user_dash.html", ip=ip, expires=fmt_ts(v.get("expires")))

@app.route('/api/status')
def api_status():
    ip = get_client_ip()
    return jsonify({"ip": ip, "config": get_user_config(ip), "authorized": ip in registered_ips})

@app.route('/api/toggle', methods=['POST'])
def api_toggle():
    ip = get_client_ip()
    if ip not in registered_ips: return jsonify({"error": "Unauthorized"}), 401
    d = request.get_json(silent=True) or {}
    feat = d.get("feature"); val = bool(d.get("value"))
    fmap = {'hs_neck': 'HS_NECK', 'hs_chest': 'HS_CHEST', 'bypass_v1': 'BYPASSV1',
            'backjump_v1': 'BACKJUMPV1', 'high_sensi': 'HIGH_SENSI'}
    k = fmap.get(feat)
    if not k: return jsonify({"error": "Invalid feature"}), 400
    cfg = get_user_config(ip)
    if feat == 'hs_neck' and val: cfg['HS_CHEST'] = False
    if feat == 'hs_chest' and val: cfg['HS_NECK'] = False
    cfg[k] = val
    save_data()
    print(f"[TOGGLE] {ip} {feat}={val}")
    return jsonify({"ok": True, "config": cfg})

# ================= ADMIN =================
@app.route('/admin')
def admin():
    if not session.get("admin"): return render_template("admin_login.html")
    return render_template("admin_panel.html")

@app.route('/admin/login', methods=['POST'])
def admin_login():
    d = request.get_json(silent=True) or {}
    if d.get("user") == ADMIN_USER and d.get("pass") == ADMIN_PASS:
        session["admin"] = True
        return jsonify({"ok": True})
    return jsonify({"error": "Invalid credentials"}), 403

@app.route('/admin/logout')
def admin_logout():
    session.pop("admin", None)
    return Response(status=302, headers={"Location": "/admin"})

def need_admin():
    if not session.get("admin"): return jsonify({"error": "Not authorized"}), 403
    return None

@app.route('/admin/data')
def admin_data():
    e = need_admin()
    if e: return e
    active = sum(1 for ip in registered_ips if key_active(ip))
    return jsonify({"keys": keys_list(), "users": active,
                    "resellers": [{"id": i, "credits": r.get("credits", 0), "joined": r.get("joined", "—"), "banned": r.get("banned", False)} for i, r in resellers.items()],
                    "rates": credit_rates})

@app.route('/admin/key', methods=['POST'])
def admin_key():
    e = need_admin()
    if e: return e
    d = request.get_json(silent=True) or {}
    k = gen_key()
    generated_keys[k] = {"reseller": "ADMIN", "duration": int(d.get("duration", 43200)),
                         "limit": max(1, int(d.get("limit", 1))), "created": now(),
                         "used_ips": [], "expires": None, "paused": False}
    save_data()
    return jsonify({"ok": True, "key": k})

@app.route('/admin/user/reset', methods=['POST'])
def admin_user_reset():
    e = need_admin()
    if e: return e
    k = (request.get_json(silent=True) or {}).get("key")
    v = generated_keys.get(k)
    if not v: return jsonify({"error": "No key"}), 404
    for ip in v.get("used_ips", []): registered_ips.pop(ip, None)
    v["used_ips"] = []
    save_data()
    return jsonify({"ok": True})

@app.route('/admin/user/delete', methods=['POST'])
def admin_user_delete():
    e = need_admin()
    if e: return e
    k = (request.get_json(silent=True) or {}).get("key")
    v = generated_keys.pop(k, None)
    if v:
        for ip in v.get("used_ips", []): registered_ips.pop(ip, None)
    save_data()
    return jsonify({"ok": True})

@app.route('/admin/reseller/add', methods=['POST'])
def reseller_add():
    e = need_admin()
    if e: return e
    d = request.get_json(silent=True) or {}
    rid = (d.get("id") or "").strip()
    if not rid or not d.get("pass"): return jsonify({"error": "ID & password required"}), 400
    if rid in resellers: return jsonify({"error": "Reseller already exists"}), 400
    resellers[rid] = {"password": d.get("pass"), "credits": float(d.get("credits", 0)),
                      "joined": datetime.now().strftime("%b %d"), "banned": False}
    save_data()
    return jsonify({"ok": True})

@app.route('/admin/reseller/ban', methods=['POST'])
def reseller_ban():
    e = need_admin()
    if e: return e
    rid = (request.get_json(silent=True) or {}).get("id")
    r = resellers.get(rid)
    if not r: return jsonify({"error": "No reseller"}), 404
    r["banned"] = not r.get("banned", False)
    save_data()
    return jsonify({"ok": True})

@app.route('/admin/reseller/delete', methods=['POST'])
def reseller_delete():
    e = need_admin()
    if e: return e
    rid = (request.get_json(silent=True) or {}).get("id")
    resellers.pop(rid, None)
    save_data()
    return jsonify({"ok": True})

@app.route('/admin/rate/add', methods=['POST'])
def rate_add():
    e = need_admin()
    if e: return e
    d = request.get_json(silent=True) or {}
    dur = int(d.get("duration", 0)); cost = float(d.get("cost", 1))
    credit_rates[:] = [r for r in credit_rates if r["duration"] != dur]
    credit_rates.append({"duration": dur, "cost": cost})
    save_data()
    return jsonify({"ok": True})

@app.route('/admin/rate/delete', methods=['POST'])
def rate_delete():
    e = need_admin()
    if e: return e
    dur = int((request.get_json(silent=True) or {}).get("id", 0))
    credit_rates[:] = [r for r in credit_rates if r["duration"] != dur]
    save_data()
    return jsonify({"ok": True})

@app.route('/admin/bulk/extend', methods=['POST'])
def bulk_extend():
    e = need_admin()
    if e: return e
    n = 0
    for v in generated_keys.values():
        if key_expired(v): v["expires"] = now() + 7 * 86400; n += 1
    save_data()
    return jsonify({"ok": True, "n": n})

@app.route('/admin/bulk/pause', methods=['POST'])
def bulk_pause():
    e = need_admin()
    if e: return e
    used = [v for v in generated_keys.values() if v.get("used_ips")]
    do_pause = any(not v.get("paused") for v in used)
    for v in used:
        if do_pause:
            v["remaining"] = (v["expires"] - now()) if v.get("expires") else None
            v["paused"] = True
        else:
            if v.get("remaining"): v["expires"] = now() + v["remaining"]
            v["paused"] = False
    save_data()
    return jsonify({"ok": True, "paused": do_pause})

@app.route('/admin/bulk/reset-all', methods=['POST'])
def bulk_reset():
    e = need_admin()
    if e: return e
    for v in generated_keys.values():
        for ip in v.get("used_ips", []): registered_ips.pop(ip, None)
        v["used_ips"] = []
    save_data()
    return jsonify({"ok": True})

@app.route('/admin/bulk/delete-expired', methods=['POST'])
def bulk_delete_expired():
    e = need_admin()
    if e: return e
    dead = [k for k, v in generated_keys.items() if key_expired(v)]
    for k in dead:
        v = generated_keys.pop(k)
        for ip in v.get("used_ips", []): registered_ips.pop(ip, None)
    save_data()
    return jsonify({"ok": True, "n": len(dead)})

@app.route('/admin/bulk/delete-all', methods=['POST'])
def bulk_delete_all():
    e = need_admin()
    if e: return e
    generated_keys.clear(); registered_ips.clear()
    save_data()
    return jsonify({"ok": True})

@app.route('/admin/maintenance', methods=['POST'])
def maint():
    e = need_admin()
    if e: return e
    global maintenance_mode
    maintenance_mode = not maintenance_mode
    save_data()
    return jsonify({"ok": True, "on": maintenance_mode})

# ================= RESELLER =================
@app.route('/reseller')
def reseller():
    rid = session.get("reseller")
    if not rid or rid not in resellers: return render_template("reseller_login.html")
    return render_template("reseller_panel.html")

@app.route('/reseller/login', methods=['POST'])
def reseller_login():
    d = request.get_json(silent=True) or {}
    r = resellers.get((d.get("user") or "").strip())
    if r and r.get("password") == d.get("pass") and not r.get("banned"):
        session["reseller"] = d.get("user").strip()
        return jsonify({"ok": True})
    if r and r.get("banned"): return jsonify({"error": "Account banned"}), 403
    return jsonify({"error": "Invalid credentials"}), 403

@app.route('/reseller/logout')
def reseller_logout():
    session.pop("reseller", None)
    return Response(status=302, headers={"Location": "/reseller"})

def need_res():
    rid = session.get("reseller")
    if not rid or rid not in resellers: return None, (jsonify({"error": "Not authorized"}), 403)
    return rid, None

@app.route('/reseller/data')
def reseller_data():
    rid, e = need_res()
    if e: return e
    return jsonify({"credits": resellers[rid].get("credits", 0),
                    "keys": keys_list(only_reseller=rid), "rates": credit_rates})

@app.route('/reseller/key', methods=['POST'])
def reseller_key():
    rid, e = need_res()
    if e: return e
    d = request.get_json(silent=True) or {}
    dur = int(d.get("duration", 0))
    rate = next((r for r in credit_rates if r["duration"] == dur), None)
    if not rate: return jsonify({"error": "Invalid duration"}), 400
    r = resellers[rid]
    if r.get("credits", 0) < rate["cost"]:
        return jsonify({"error": "Insufficient credits"}), 403
    r["credits"] = round(r["credits"] - rate["cost"], 2)
    k = gen_key()
    generated_keys[k] = {"reseller": rid, "duration": dur,
                         "limit": max(1, int(d.get("limit", 1))), "created": now(),
                         "used_ips": [], "expires": None, "paused": False}
    save_data()
    return jsonify({"ok": True, "key": k, "cost": rate["cost"]})

@app.route('/reseller/reset', methods=['POST'])
def reseller_reset():
    rid, e = need_res()
    if e: return e
    k = (request.get_json(silent=True) or {}).get("key")
    v = generated_keys.get(k)
    if not v or v.get("reseller") != rid: return jsonify({"error": "Not your key"}), 403
    for ip in v.get("used_ips", []): registered_ips.pop(ip, None)
    v["used_ips"] = []
    save_data()
    return jsonify({"ok": True})

@app.route('/reseller/delete-expired', methods=['POST'])
def reseller_del_exp():
    rid, e = need_res()
    if e: return e
    dead = [k for k, v in generated_keys.items() if v.get("reseller") == rid and key_expired(v)]
    for k in dead:
        v = generated_keys.pop(k)
        for ip in v.get("used_ips", []): registered_ips.pop(ip, None)
    save_data()
    return jsonify({"ok": True, "n": len(dead)})

@app.route('/reseller/reset-all', methods=['POST'])
def reseller_reset_all():
    rid, e = need_res()
    if e: return e
    for v in generated_keys.values():
        if v.get("reseller") == rid:
            for ip in v.get("used_ips", []): registered_ips.pop(ip, None)
            v["used_ips"] = []
    save_data()
    return jsonify({"ok": True})

# ================= PROXY ROUTES =================
@app.route('/ver.php')
@app.route('/live/ver.php')
def ver_php():
    ip = get_client_ip()
    cdn_self = f"http://{request.host}/cdn/live/ABHotUpdates/"
    try:
        r = req.get(VER_PHP_URL, params=request.args.to_dict(), timeout=30)
        return Response(modify_ver_response(r.text, cdn_self, ip), mimetype='application/json')
    except Exception as e:
        print(f"[ERROR] ver.php: {e}")
        return Response("Error", status=502)

@app.route('/cdn/live/ABHotUpdates/<path:p>')
@app.route('/<path:p>')
def cdn(p):
    ip = get_client_ip()
    for pre in ("cdn/live/ABHotUpdates/", "cdn/", "live/ABHotUpdates/"):
        if p.startswith(pre): p = p[len(pre):]; break
    if "cache_res" in p and "avatar" not in p:
        cfg = get_user_config(ip)
        name = None
        if cfg.get("HS_NECK"): name = "cache_res"
        elif cfg.get("HS_CHEST"): name = "cache_res2"
        gz = read_gz(name) if name else None
        if gz:
            print(f"[CDN] {ip} local {name}")
            return Response(gz, mimetype='application/octet-stream')
    up = TARGET_BASE_URL.rstrip("/") + "/" + p
    try:
        r = req.get(up, timeout=60)
        if "fileinfo" in p:
            patched = patch_fileinfo(r.text, get_user_config(ip))
            if r.status_code == 200 and "cache_res," in patched and patched != r.text:
                print(f"[CDN] {ip} fileinfo patched")
                return Response(patched.encode(), mimetype='binary/octet-stream')
            if r.status_code != 200:
                lf = build_fileinfo(get_user_config(ip))
                if lf: return Response(lf.encode(), mimetype='binary/octet-stream')
        return Response(r.content, status=r.status_code, mimetype=r.headers.get('content-type', 'application/octet-stream'))
    except Exception as e:
        print(f"[ERROR] cdn: {e}")
        return Response("Error", status=502)

if __name__ == "__main__":
    load_data()
    ensure_gz()
    print(f"[*] Gpt proxy on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
