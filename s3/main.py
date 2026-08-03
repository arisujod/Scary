import os
import re
import json
import gzip
import hashlib
import base64
import requests
import string
import random
from flask import Flask, request, Response, jsonify, session, redirect, url_for, render_template_string
from datetime import datetime, timedelta
from functools import wraps
import socket

app = Flask(__name__)
app.secret_key = os.urandom(32).hex()

TARGET_BASE_URL = "https://dl.bs.freefiremobile.com/live/ABHotUpdates/"
VER_PHP_URL = "https://version.ggwhitehawk.com/live/ver.php"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", 6767))

# server.py (api.php) key system connection
KEY_API_URL = os.environ.get('KEY_API_URL', 'https://s3-hacks-get-key.onrender.com/api.php')

ADMIN_USER = "S3HACKSADMIN"
ADMIN_PASS = "#FFHUDT6O3j2mo8RBPo7eO"

# Data file paths
DATA_FILE = os.path.join(BASE_DIR, "s3hacks_data.json")

user_configs = {}
registered_ips = {}
generated_keys = {}
key_expiry = {}
maintenance_mode = False  # Global maintenance flag

DEFAULT_CONFIG = {
    "HS_NECK": True,
    "HS_CHEST": False,
    "BYPASSV1": True,
    "BACKJUMPV1": True,
    "HIGH_SENSI": True
}

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
    "StropFallingResetSpeed": {"var_type": "bool", "var_value": "true"}
}

HIGH_SENSI_OVERRIDES = {
    "SensitivityMaxSetting": {"var_type": "float", "var_value": "9.0"},
    "Sensitivity1PMaxSetting": {"var_type": "float", "var_value": "9.0"},
    "X1ScopeMaxSetting": {"var_type": "float", "var_value": "9.0"},
    "X2ScopeMaxSetting": {"var_type": "float", "var_value": "9.0"},
    "X4ScopeMaxSetting": {"var_type": "float", "var_value": "9.0"},
    "X8ScopeMaxSetting": {"var_type": "float", "var_value": "9.0"},
    "FreeLookMaxSetting": {"var_type": "float", "var_value": "9.0"}
}

# ==================== DATA PERSISTENCE ====================

def save_data():
    """Save all data to JSON file"""
    global maintenance_mode
    data = {
        'user_configs': user_configs,
        'registered_ips': registered_ips,
        'generated_keys': generated_keys,
        'key_expiry': {ip: exp.isoformat() for ip, exp in key_expiry.items()},
        'maintenance_mode': maintenance_mode
    }
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")

def load_data():
    """Load all data from JSON file"""
    global user_configs, registered_ips, generated_keys, key_expiry, maintenance_mode
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
            user_configs = data.get('user_configs', {})
            registered_ips = data.get('registered_ips', {})
            generated_keys = data.get('generated_keys', {})
            maintenance_mode = data.get('maintenance_mode', False)
            # Convert expiry strings back to datetime
            key_expiry = {}
            for ip, exp_str in data.get('key_expiry', {}).items():
                try:
                    key_expiry[ip] = datetime.fromisoformat(exp_str)
                except:
                    pass
            print(f"Loaded data: {len(generated_keys)} keys, {len(registered_ips)} IPs, Maintenance: {maintenance_mode}")
        except Exception as e:
            print(f"Error loading data: {e}")
            # Initialize empty data structures on error
            user_configs = {}
            registered_ips = {}
            generated_keys = {}
            key_expiry = {}
            maintenance_mode = False
    else:
        print("No existing data file found. Starting fresh.")
        # Explicitly initialize empty data structures
        user_configs = {}
        registered_ips = {}
        generated_keys = {}
        key_expiry = {}
        maintenance_mode = False
        # Save the empty state to create the file
        save_data()

# ========================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def maintenance_check(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        global maintenance_mode
        # Allow admin routes and login
        if request.path.startswith('/admin') or request.path == '/Po7eO' or request.path == '/admin/logout':
            return f(*args, **kwargs)
        # Allow API status check
        if request.path == '/api/ip/check':
            return f(*args, **kwargs)
        # Check maintenance
        if maintenance_mode:
            return render_template_string(MAINTENANCE_PAGE)
        return f(*args, **kwargs)
    return decorated_function

def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

def get_user_config(client_ip):
    if client_ip not in user_configs:
        user_configs[client_ip] = DEFAULT_CONFIG.copy()
        save_data()
    return user_configs[client_ip]

def generate_key(prefix="S3-HACKS"):
    random_part = ''.join(random.choices(string.digits, k=4))
    return f"{prefix}-{random_part}"

def get_overrides_for_ip(client_ip):
    config = get_user_config(client_ip)
    overrides = {}
    if config.get("BYPASSV1", False):
        overrides.update(ANTI_BAN_OVERRIDES)
    if config.get("BACKJUMPV1", False):
        overrides.update(BACKJUMPV1_OVERRIDES)
    if config.get("HIGH_SENSI", False):
        overrides.update(HIGH_SENSI_OVERRIDES)
    return overrides

def sha1_b64(data):
    return base64.b64encode(hashlib.sha1(data).digest()).decode()

def patch_fileinfo(original_text, config):
    if not config.get("HS_NECK", False) and not config.get("HS_CHEST", False):
        return original_text
    lines = original_text.splitlines()
    new_lines = []
    cache_res_file = os.path.join(BASE_DIR, "cache_res")
    cache_res2_file = os.path.join(BASE_DIR, "cache_res2")
    for line in lines:
        if line.startswith("cache_res,"):
            if config.get("HS_NECK", False) and os.path.exists(cache_res_file):
                try:
                    with open(cache_res_file, "rb") as f:
                        gz_data = f.read()
                    raw_data = gzip.decompress(gz_data)
                    new_line = f"cache_res,{sha1_b64(raw_data)},{len(raw_data)},0,{sha1_b64(gz_data)},{len(gz_data)},True,0"
                    new_lines.append(new_line)
                except:
                    new_lines.append(line)
            elif config.get("HS_CHEST", False) and os.path.exists(cache_res2_file):
                try:
                    with open(cache_res2_file, "rb") as f:
                        gz_data = f.read()
                    raw_data = gzip.decompress(gz_data)
                    new_line = f"cache_res,{sha1_b64(raw_data)},{len(raw_data)},0,{sha1_b64(gz_data)},{len(gz_data)},True,0"
                    new_lines.append(new_line)
                except:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    return "\n".join(new_lines)

def modify_ver_response(response_text, client_ip):
    try:
        data = json.loads(response_text)
        cdn_url = f"http://{request.host}/cdn/live/ABHotUpdates/"
        data["cdn_url"] = cdn_url
        data["backup_cdn_url"] = cdn_url
        data["abhotupdate_cdn_url"] = cdn_url
        overrides = get_overrides_for_ip(client_ip)
        if overrides:
            gamevar = data.get("gamevar", "")
            for var_name, override in overrides.items():
                gamevar += f"\n{var_name},{var_name},{override['var_type']},{override['var_value']},,"
            data["gamevar"] = gamevar
        return json.dumps(data)
    except:
        return response_text

# ==================== ROUTES ====================

@app.route('/Po7eO', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username == ADMIN_USER and password == ADMIN_PASS:
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        return render_template_string(LOGIN_PAGE, error="Invalid credentials")
    return render_template_string(LOGIN_PAGE, error=None)

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    global maintenance_mode
    used_count = sum(1 for kd in generated_keys.values() if kd.get('used_ips'))
    return render_template_string(ADMIN_DASHBOARD, 
                                 keys=generated_keys, 
                                 ips=registered_ips,
                                 key_expiry=key_expiry,
                                 used_count=used_count,
                                 maintenance_mode=maintenance_mode)

@app.route('/admin/generate', methods=['POST'])
@login_required
def generate_new_key():
    data = request.json
    key_prefix = data.get('prefix', 'S3-HACKS')
    ip_limit = int(data.get('limit', 1))
    days_valid = int(data.get('days', 7))
    
    new_key = generate_key(key_prefix)
    generated_keys[new_key] = {
        'prefix': key_prefix,
        'limit': ip_limit,
        'days': days_valid,
        'created': datetime.now().isoformat(),
        'used_ips': []
    }
    save_data()
    
    return jsonify({'key': new_key, 'limit': ip_limit, 'days': days_valid})

@app.route('/admin/revoke', methods=['POST'])
@login_required
def revoke_key():
    data = request.json
    key = data.get('key')
    
    if key in generated_keys:
        for ip in generated_keys[key]['used_ips']:
            if ip in registered_ips:
                del registered_ips[ip]
            if ip in key_expiry:
                del key_expiry[ip]
        del generated_keys[key]
        save_data()
        return jsonify({'success': True})
    return jsonify({'error': 'Key not found'}), 400

@app.route('/admin/maintenance', methods=['POST'])
@login_required
def toggle_maintenance():
    global maintenance_mode
    data = request.json
    status = data.get('status', False)
    maintenance_mode = bool(status)
    save_data()
    return jsonify({
        'success': True, 
        'maintenance_mode': maintenance_mode,
        'message': f'Maintenance {"activated" if maintenance_mode else "deactivated"}'
    })

@app.route('/admin/logout')
@login_required
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/verify', methods=['POST'])
@maintenance_check
def verify_key():
    client_ip = get_client_ip()
    data = request.json
    key = data.get('key', '').strip()
    
    if client_ip in registered_ips:
        return jsonify({'success': True, 'message': 'Already registered'})
    
    # 1. Local admin-generated keys (backward compatibility)
    if key in generated_keys:
        key_data = generated_keys[key]
        if len(key_data['used_ips']) >= key_data['limit']:
            return jsonify({'success': False, 'message': 'Key limit reached'}), 401
        
        registered_ips[client_ip] = key
        key_data['used_ips'].append(client_ip)
        expiry_date = datetime.now() + timedelta(days=key_data['days'])
        key_expiry[client_ip] = expiry_date
        save_data()
        
        return jsonify({
            'success': True, 
            'message': 'Key verified successfully',
            'expires': expiry_date.isoformat()
        })
    
    # 2. server.py /api.php key system (shared keys)
    try:
        resp = requests.post(KEY_API_URL, json={
            'action': 'login',
            'key': key,
            'hwid': client_ip
        }, timeout=15)
        result = resp.json()
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'message': 'Auth server offline'}), 503
    except Exception as e:
        return jsonify({'success': False, 'message': 'Auth server error'}), 500
    
    if result.get('success'):
        data_resp = result.get('data', {})
        expiry_ts = data_resp.get('EXP')
        if expiry_ts:
            expiry_date = datetime.fromtimestamp(expiry_ts)
        else:
            expiry_date = datetime.now() + timedelta(days=1)
        
        registered_ips[client_ip] = key
        key_expiry[client_ip] = expiry_date
        save_data()
        
        return jsonify({
            'success': True,
            'message': 'Key verified successfully',
            'expires': expiry_date.isoformat()
        })
    
    error = result.get('error') or result.get('message') or 'Invalid key'
    return jsonify({'success': False, 'message': error}), 401

def key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = get_client_ip()
        if client_ip not in registered_ips:
            return Response(json.dumps({'error': 'Unauthorized'}), status=401, content_type='application/json')
        if client_ip in key_expiry:
            if datetime.now() > key_expiry[client_ip]:
                del registered_ips[client_ip]
                del key_expiry[client_ip]
                save_data()
                return Response(json.dumps({'error': 'Key expired'}), status=401, content_type='application/json')
        return f(*args, **kwargs)
    return decorated_function

@app.route('/ver.php', methods=['GET'])
@app.route('/live/ver.php', methods=['GET'])
@maintenance_check
@key_required
def handle_ver_php():
    client_ip = get_client_ip()
    params = dict(request.args)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length", "connection", "accept-encoding")}
    try:
        response = requests.get(VER_PHP_URL, params=params, headers=headers, timeout=60)
        modified = modify_ver_response(response.text, client_ip)
        return Response(modified, status=200, content_type="application/json")
    except Exception as e:
        return Response(f"Error: {e}", status=502)

@app.route('/cdn/live/ABHotUpdates/', methods=['GET'])
@app.route('/cdn/live/ABHotUpdates/<path:path>', methods=['GET'])
@maintenance_check
@key_required
def handle_cdn(path=""):
    client_ip = get_client_ip()
    config = get_user_config(client_ip)
    cache_file = os.path.join(BASE_DIR, "cache_res")
    cache_res2_file = os.path.join(BASE_DIR, "cache_res2")
    assetindexer_file = os.path.join(BASE_DIR, "cache_res3")
    
    if re.compile(r"android_astc/1\.123\.[^/]*/gameassetbundles/avatar/assetindexer").match(path) and os.path.exists(assetindexer_file):
        with open(assetindexer_file, "rb") as f:
            return Response(f.read(), status=200, content_type="application/octet-stream")
    
    if "cache_res" in path:
        if config.get("HS_NECK", False) and os.path.exists(cache_file):
            with open(cache_file, "rb") as f:
                return Response(f.read(), status=200, content_type="application/octet-stream")
        elif config.get("HS_CHEST", False) and os.path.exists(cache_res2_file):
            with open(cache_res2_file, "rb") as f:
                return Response(f.read(), status=200, content_type="application/octet-stream")
    
    if "fileinfo" in path:
        target_url = TARGET_BASE_URL + path
        try:
            resp = requests.get(target_url, timeout=60)
            if config.get("HS_NECK", False) or config.get("HS_CHEST", False):
                patched = patch_fileinfo(resp.text, config)
                return Response(patched.encode(), status=200, content_type="binary/octet-stream")
            return Response(resp.content, status=200, content_type="binary/octet-stream")
        except Exception as e:
            return Response(f"Error: {e}", status=502)
    
    target_url = TARGET_BASE_URL + path
    try:
        resp = requests.get(target_url, timeout=60)
        return Response(resp.content, status=resp.status_code, content_type=resp.headers.get('content-type', 'application/octet-stream'))
    except Exception as e:
        return Response(f"Error: {e}", status=502)

@app.route('/api/status', methods=['GET'])
@maintenance_check
@key_required
def api_status():
    client_ip = get_client_ip()
    config = get_user_config(client_ip)
    return jsonify({
        "ip": client_ip,
        "config": config,
        "key": registered_ips.get(client_ip),
        "expires": key_expiry.get(client_ip, "").isoformat() if client_ip in key_expiry else None
    })

@app.route('/api/toggle', methods=['POST'])
@maintenance_check
@key_required
def api_toggle():
    client_ip = get_client_ip()
    data = request.json
    feature = data.get('feature')
    value = data.get('value')
    
    feature_map = {
        'hs_neck': 'HS_NECK',
        'hs_chest': 'HS_CHEST',
        'bypass_v1': 'BYPASSV1',
        'backjump_v1': 'BACKJUMPV1',
        'high_sensi': 'HIGH_SENSI'
    }
    
    config_key = feature_map.get(feature)
    if not config_key:
        return jsonify({"error": "Invalid feature"}), 400
    
    config = get_user_config(client_ip)
    
    # Mutual exclusion for HS_NECK and HS_CHEST
    if feature == 'hs_neck' and value == True:
        config['HS_CHEST'] = False
    elif feature == 'hs_chest' and value == True:
        config['HS_NECK'] = False
    
    config[config_key] = value
    save_data()
    
    return jsonify({
        "success": True,
        "ip": client_ip,
        "feature": feature,
        "value": value
    })

@app.route('/api/ip/check', methods=['GET'])
def api_ip_check():
    client_ip = get_client_ip()
    return jsonify({
        "ip": client_ip,
        "key": registered_ips.get(client_ip),
        "is_authorized": client_ip in registered_ips,
        "expires": key_expiry.get(client_ip, "").isoformat() if client_ip in key_expiry else None
    })

@app.route('/')
@maintenance_check
def index():
    client_ip = get_client_ip()
    if client_ip in registered_ips:
        return render_template_string(MAIN_UI)
    return render_template_string(KEY_ENTRY)

# ==================== HTML TEMPLATES ====================

BASE_STYLE = """
    :root {
        --bg:#05060a;
        --card:rgba(13,16,23,0.82);
        --card-solid:#0d1017;
        --border:rgba(255,255,255,0.06);
        --border-soft:rgba(255,255,255,0.04);
        --text:#f4f5fa;
        --muted:rgba(255,255,255,0.48);
        --dim:rgba(255,255,255,0.14);
        --grad:linear-gradient(135deg,#8b5cf6,#6366f1 55%,#22d3ee);
        --grad-soft:linear-gradient(135deg,rgba(139,92,246,.16),rgba(34,211,238,.16));
        --glow:rgba(99,102,241,.35);
    }
    * { margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
    html,body { min-height:100%; }
    body {
        background:var(--bg);
        font-family:'Inter','Segoe UI',system-ui,-apple-system,sans-serif;
        color:var(--text);
        overflow-x:hidden;
    }
    h1,h2,h3,.brand-text,.btn,.stat-num { font-family:'Space Grotesk','Inter',sans-serif; }
    .aurora { position:fixed; border-radius:50%; filter:blur(110px); opacity:.16; pointer-events:none; z-index:0; will-change:transform; }
    .a1 { width:480px; height:480px; background:#7c3aed; top:-140px; left:-120px; animation:drift1 20s ease-in-out infinite alternate; }
    .a2 { width:420px; height:420px; background:#0ea5e9; bottom:-140px; right:-100px; animation:drift2 24s ease-in-out infinite alternate; }
    .a3 { width:300px; height:300px; background:#6366f1; top:40%; left:55%; opacity:.08; animation:drift1 28s ease-in-out infinite alternate-reverse; }
    @keyframes drift1 { to { transform:translate(70px,50px) scale(1.12); } }
    @keyframes drift2 { to { transform:translate(-60px,-60px) scale(1.18); } }
    .grid-bg {
        position:fixed; inset:0; z-index:0; pointer-events:none;
        background-image:linear-gradient(rgba(255,255,255,.022) 1px,transparent 1px),
                         linear-gradient(90deg,rgba(255,255,255,.022) 1px,transparent 1px);
        background-size:56px 56px;
        -webkit-mask-image:radial-gradient(ellipse at 50% 25%,#000 20%,transparent 75%);
        mask-image:radial-gradient(ellipse at 50% 25%,#000 20%,transparent 75%);
    }
    .card {
        background:var(--card);
        backdrop-filter:blur(28px); -webkit-backdrop-filter:blur(28px);
        border:1px solid var(--border);
        border-radius:26px;
        box-shadow:0 40px 90px rgba(0,0,0,.65), inset 0 1px 0 rgba(255,255,255,.04);
        animation:rise .6s cubic-bezier(.22,.68,.35,1) both;
        position:relative; z-index:1;
    }
    @keyframes rise { from { opacity:0; transform:translateY(22px) scale(.985); } to { opacity:1; transform:none; } }
    .card::before {
        content:''; position:absolute; inset:0; border-radius:inherit; padding:1px;
        background:linear-gradient(160deg,rgba(255,255,255,.09),transparent 30%,transparent 70%,rgba(99,102,241,.18));
        -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);
        -webkit-mask-composite:xor; mask-composite:exclude;
        pointer-events:none;
    }
    .btn {
        position:relative; overflow:hidden; cursor:pointer; border:none;
        background:var(--grad); color:#fff;
        border-radius:14px; font-weight:600; letter-spacing:.06em;
        transition:transform .25s cubic-bezier(.22,.68,.35,1), box-shadow .25s ease;
        display:inline-flex; align-items:center; justify-content:center; gap:10px;
    }
    .btn:hover { transform:translateY(-2px); box-shadow:0 14px 40px var(--glow); }
    .btn:active { transform:translateY(0) scale(.98); }
    .btn::after {
        content:''; position:absolute; top:0; left:-160%; width:60%; height:100%;
        background:linear-gradient(100deg,transparent,rgba(255,255,255,.38),transparent);
        transform:skewX(-20deg); transition:left .65s ease;
    }
    .btn:hover::after { left:160%; }
    .btn:disabled { opacity:.45; cursor:not-allowed; transform:none !important; box-shadow:none !important; }
    .input {
        width:100%; padding:15px 18px; outline:none; color:var(--text);
        background:rgba(255,255,255,.03); border:1px solid var(--border);
        border-radius:14px; font-size:15px; transition:border-color .3s, box-shadow .3s, background .3s;
    }
    .input::placeholder { color:var(--dim); }
    .input:focus {
        border-color:rgba(139,92,246,.5);
        background:rgba(139,92,246,.04);
        box-shadow:0 0 0 4px rgba(139,92,246,.08), 0 0 30px rgba(99,102,241,.12);
    }
    .badge {
        display:inline-flex; align-items:center; gap:7px;
        padding:5px 14px; border-radius:100px; font-size:11px; font-weight:600;
        background:var(--grad-soft); color:#a5b4fc;
        border:1px solid rgba(139,92,246,.25);
    }
    .badge.green { background:rgba(52,211,153,.08); color:#34d399; border-color:rgba(52,211,153,.2); }
    .badge.red { background:rgba(244,63,94,.08); color:#fb7185; border-color:rgba(244,63,94,.2); }
    .badge.cyan { background:rgba(34,211,238,.08); color:#22d3ee; border-color:rgba(34,211,238,.2); }
    .grad-text {
        background:var(--grad);
        -webkit-background-clip:text; background-clip:text;
        -webkit-text-fill-color:transparent; color:transparent;
    }
    .toast {
        position:fixed; bottom:28px; left:50%; transform:translateX(-50%) translateY(20px);
        background:rgba(13,16,23,.92); backdrop-filter:blur(20px);
        border:1px solid rgba(139,92,246,.25); border-radius:14px;
        padding:13px 24px; color:var(--text); font-size:13px; font-weight:500;
        box-shadow:0 20px 50px rgba(0,0,0,.6), 0 0 30px rgba(99,102,241,.1);
        opacity:0; pointer-events:none; transition:opacity .3s ease, transform .35s cubic-bezier(.22,.68,.35,1);
        z-index:999; max-width:90%; white-space:nowrap;
    }
    .toast.show { opacity:1; transform:translateX(-50%) translateY(0); }
    .spinner {
        display:inline-block; width:15px; height:15px; flex-shrink:0;
        border:2px solid rgba(255,255,255,.18); border-top-color:#fff;
        border-radius:50%; animation:spin .65s linear infinite;
    }
    @keyframes spin { to { transform:rotate(360deg); } }
    @keyframes pulse-dot { 0%,100% { opacity:1; box-shadow:0 0 0 0 rgba(52,211,153,.5);} 50% { opacity:.5; box-shadow:0 0 0 6px rgba(52,211,153,0);} }
    
    .social.getkey { 
        background:linear-gradient(135deg,#f59e0b,#d97706); 
    }
    .social.getkey:hover { 
        box-shadow:0 12px 32px rgba(245,158,11,.35); 
    }
    .social.telegram-maintenance {
        background:linear-gradient(135deg,#229ed9,#0088cc);
        box-shadow:0 12px 32px rgba(0,136,204,.35);
    }
    .social.telegram-maintenance:hover {
        transform:translateY(-3px);
        box-shadow:0 16px 40px rgba(0,136,204,.5);
    }
"""

LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>S3 HACKS · Secure Access</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>__STYLE__
        body { display:flex; justify-content:center; align-items:center; min-height:100vh; padding:20px; }
        .wrap { position:relative; width:100%; max-width:400px; }
        .card { padding:46px 38px; text-align:center; }
        .logo {
            width:64px; height:64px; margin:0 auto 18px; border-radius:19px;
            background:var(--grad); display:flex; align-items:center; justify-content:center;
            font-size:26px; color:#fff;
            box-shadow:0 14px 40px var(--glow), inset 0 1px 0 rgba(255,255,255,.25);
            animation:logofloat 5s ease-in-out infinite;
            position:relative;
        }
        .logo::after {
            content:''; position:absolute; inset:-7px; border-radius:24px;
            border:1px solid rgba(139,92,246,.25); animation:ring 3.5s ease-out infinite;
        }
        @keyframes ring { 0% { transform:scale(.85); opacity:.8; } 100% { transform:scale(1.25); opacity:0; } }
        @keyframes logofloat { 0%,100% { transform:translateY(0);} 50% { transform:translateY(-6px);} }
        h1 { font-size:30px; font-weight:700; letter-spacing:.14em; }
        .sub { color:var(--dim); font-size:9px; letter-spacing:.42em; margin:8px 0 34px; font-weight:600; }
        form { text-align:left; }
        .field { margin-bottom:16px; }
        .field label { display:block; color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.22em; font-weight:600; margin-bottom:8px; }
        .input-wrap { position:relative; }
        .input-wrap i {
            position:absolute; left:16px; top:50%; transform:translateY(-50%);
            color:var(--dim); font-size:13px; pointer-events:none; transition:color .3s;
        }
        .input-wrap:focus-within i { color:#a5b4fc; }
        .input-wrap .input { padding-left:44px; }
        .btn { width:100%; padding:16px; font-size:13px; margin-top:8px; }
        .btn i { font-size:13px; }
        .error {
            margin-top:16px; padding:12px 16px; border-radius:12px;
            color:#fb7185; font-size:13px; font-weight:500;
            background:rgba(244,63,94,.07); border:1px solid rgba(244,63,94,.18);
            animation:shake .4s ease;
        }
        @keyframes shake { 0%,100%{transform:translateX(0);} 25%{transform:translateX(-6px);} 75%{transform:translateX(6px);} }
        .footer { margin-top:30px; color:rgba(255,255,255,.14); font-size:9px; letter-spacing:.42em; font-weight:600; }
        .footer .dot { display:inline-block; width:5px; height:5px; border-radius:50%; background:#34d399; margin-right:8px; animation:pulse-dot 2s infinite; }
    </style>
</head>
<body>
    <div class="aurora a1"></div><div class="aurora a2"></div><div class="grid-bg"></div>
    <div class="wrap">
        <div class="card">
            <div class="logo"><i class="fas fa-shield-halved"></i></div>
            <h1>S3<span class="grad-text">HACKS</span></h1>
            <div class="sub">ADMINISTRATOR ACCESS</div>
            <form method="POST" autocomplete="off">
                <div class="field">
                    <label>Username</label>
                    <div class="input-wrap">
                        <i class="fas fa-user"></i>
                        <input class="input" type="text" name="username" placeholder="Enter username" required>
                    </div>
                </div>
                <div class="field">
                    <label>Password</label>
                    <div class="input-wrap">
                        <i class="fas fa-lock"></i>
                        <input class="input" type="password" name="password" placeholder="Enter password" required>
                    </div>
                </div>
                <button type="submit" class="btn"><i class="fas fa-fingerprint"></i> Authenticate</button>
                {% if error %}
                <div class="error"><i class="fas fa-triangle-exclamation" style="margin-right:8px;"></i>{{ error }}</div>
                {% endif %}
            </form>
            <div class="footer"><span class="dot"></span>ENCRYPTED CHANNEL</div>
        </div>
    </div>
</body>
</html>
"""

ADMIN_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>S3 HACKS · Command Center</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>__STYLE__
        body { padding:28px 24px 60px; }
        .container { max-width:1180px; margin:0 auto; position:relative; z-index:1; }
        .header { display:flex; justify-content:space-between; align-items:center; padding:10px 2px 22px; }
        .brand { display:flex; align-items:center; gap:14px; }
        .brand .logo {
            width:46px; height:46px; border-radius:14px; background:var(--grad);
            display:flex; align-items:center; justify-content:center; color:#fff; font-size:19px;
            box-shadow:0 10px 30px var(--glow);
        }
        .brand h1 { font-size:20px; letter-spacing:.12em; }
        .brand .tagline { color:var(--dim); font-size:9px; letter-spacing:.35em; font-weight:600; margin-top:3px; }
        .logout {
            display:inline-flex; align-items:center; gap:9px;
            padding:11px 22px; border-radius:12px; text-decoration:none;
            color:var(--muted); font-size:13px; font-weight:600;
            border:1px solid var(--border); transition:.25s; background:rgba(255,255,255,.02);
        }
        .logout:hover { color:#fb7185; border-color:rgba(244,63,94,.3); background:rgba(244,63,94,.05); transform:translateY(-1px); }
        .stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; margin-bottom:22px; }
        .stat { padding:22px; border-radius:20px; background:var(--card); border:1px solid var(--border); animation:rise .55s cubic-bezier(.22,.68,.35,1) both; position:relative; overflow:hidden; }
        .stat:nth-child(2){animation-delay:.06s;} .stat:nth-child(3){animation-delay:.12s;} .stat:nth-child(4){animation-delay:.18s;}
        .stat .ic {
            width:40px; height:40px; border-radius:12px; display:flex; align-items:center; justify-content:center;
            font-size:15px; color:#fff; margin-bottom:14px;
        }
        .stat .ic.key { background:var(--grad); box-shadow:0 8px 24px var(--glow); }
        .stat .ic.ip { background:linear-gradient(135deg,#34d399,#22d3ee); box-shadow:0 8px 24px rgba(52,211,153,.25); }
        .stat .ic.used { background:linear-gradient(135deg,#f59e0b,#f43f5e); box-shadow:0 8px 24px rgba(244,63,94,.2); }
        .stat .ic.days { background:linear-gradient(135deg,#22d3ee,#8b5cf6); box-shadow:0 8px 24px rgba(34,211,238,.2); }
        .stat .ic.maintenance { background:linear-gradient(135deg,#f43f5e,#fb7185); box-shadow:0 8px 24px rgba(244,63,94,.2); }
        .stat .label { color:var(--dim); font-size:9px; letter-spacing:.22em; text-transform:uppercase; font-weight:600; margin-bottom:6px; }
        .stat .num { font-size:32px; font-weight:700; letter-spacing:-.02em; }
        .stat .num small { font-size:14px; color:var(--dim); font-weight:500; }
        .grid { display:grid; grid-template-columns:1.1fr .9fr; gap:22px; }
        .card { padding:26px; }
        .card h2 { font-size:12px; letter-spacing:.2em; text-transform:uppercase; color:var(--muted); margin-bottom:20px; font-weight:700; }
        .card h2 i { margin-right:10px; background:var(--grad); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; font-size:13px; }
        .field { margin-bottom:14px; }
        .field label { display:block; color:var(--dim); font-size:10px; text-transform:uppercase; letter-spacing:.2em; font-weight:600; margin-bottom:7px; }
        .btn { padding:13px 26px; font-size:12px; width:100%; margin-top:6px; }
        .btn.danger { background:linear-gradient(135deg,#f43f5e,#e11d48); box-shadow:0 10px 30px rgba(244,63,94,.2); }
        .btn.danger:hover { box-shadow:0 12px 36px rgba(244,63,94,.35); }
        .btn.sm { padding:8px 16px; font-size:11px; width:auto; border-radius:10px; }
        .btn.maintenance-on { background:linear-gradient(135deg,#f43f5e,#e11d48); box-shadow:0 10px 30px rgba(244,63,94,.2); }
        .btn.maintenance-on:hover { box-shadow:0 12px 36px rgba(244,63,94,.35); }
        .btn.maintenance-off { background:linear-gradient(135deg,#34d399,#059669); box-shadow:0 10px 30px rgba(52,211,153,.2); }
        .btn.maintenance-off:hover { box-shadow:0 12px 36px rgba(52,211,153,.35); }
        .key-out {
            margin-top:16px; padding:14px; border-radius:12px; text-align:center;
            background:rgba(139,92,246,.06); border:1px dashed rgba(139,92,246,.35);
            font-family:'Space Grotesk',monospace; font-size:15px; font-weight:700; letter-spacing:.08em;
            color:#c4b5fd; min-height:20px; transition:.3s;
        }
        .key-out.reveal { animation:keypop .45s cubic-bezier(.22,.68,.35,1); }
        @keyframes keypop { from { transform:scale(.9); opacity:0; } to { transform:scale(1); opacity:1; } }
        .card.full { grid-column:1 / -1; margin-top:22px; }
        .table-wrap { overflow-x:auto; margin-top:6px; }
        table { width:100%; border-collapse:collapse; font-size:13px; }
        th {
            text-align:left; padding:12px 10px; color:var(--dim);
            font-size:9px; text-transform:uppercase; letter-spacing:.18em; font-weight:700;
            border-bottom:1px solid var(--border); white-space:nowrap;
        }
        td { padding:14px 10px; border-bottom:1px solid var(--border-soft); color:var(--muted); white-space:nowrap; }
        tbody tr { transition:background .2s; }
        tbody tr:hover { background:rgba(139,92,246,.03); }
        .mono { font-family:'Space Grotesk',monospace; font-weight:600; }
        .empty { text-align:center; padding:36px 0; color:var(--dim); font-size:13px; }
        .empty i { font-size:26px; margin-bottom:10px; opacity:.5; }
        .maintenance-status {
            display:inline-flex; align-items:center; gap:8px;
            padding:6px 16px; border-radius:100px; font-size:11px; font-weight:700;
            margin-left:10px;
        }
        .maintenance-status.active { background:rgba(244,63,94,.15); color:#fb7185; border:1px solid rgba(244,63,94,.25); }
        .maintenance-status.inactive { background:rgba(52,211,153,.15); color:#34d399; border:1px solid rgba(52,211,153,.25); }
        @media (max-width:860px) {
            .grid { grid-template-columns:1fr; }
            .header { flex-direction:column; gap:16px; align-items:flex-start; }
        }
    </style>
</head>
<body>
    <div class="aurora a1"></div><div class="aurora a2"></div><div class="aurora a3"></div><div class="grid-bg"></div>
    <div class="container">
        <div class="header">
            <div class="brand">
                <div class="logo"><i class="fas fa-bolt"></i></div>
                <div>
                    <h1>S3<span class="grad-text">HACKS</span> · COMMAND</h1>
                    <div class="tagline">CONTROL PANEL</div>
                </div>
            </div>
            <a class="logout" href="/admin/logout"><i class="fas fa-power-off"></i> Exit</a>
        </div>

        <div class="stats">
            <div class="stat">
                <div class="ic key"><i class="fas fa-key"></i></div>
                <div class="label">Total Keys</div>
                <div class="num grad-text">{{ keys|length }}</div>
            </div>
            <div class="stat">
                <div class="ic ip"><i class="fas fa-network-wired"></i></div>
                <div class="label">Active IPs</div>
                <div class="num">{{ ips|length }}</div>
            </div>
            <div class="stat">
                <div class="ic used"><i class="fas fa-bolt"></i></div>
                <div class="label">Keys In Use</div>
                <div class="num">{{ used_count }}</div>
            </div>
            <div class="stat">
                <div class="ic days"><i class="fas fa-clock"></i></div>
                <div class="label">Expired IPs</div>
                <div class="num">{{ key_expiry|length - ips|length }}</div>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <h2><i class="fas fa-wand-magic-sparkles"></i> Generate License</h2>
                <div class="field">
                    <label>Key Prefix</label>
                    <input class="input" type="text" id="keyPrefix" value="S3-HACKS">
                </div>
                <div class="field">
                    <label>IP Limit</label>
                    <input class="input" type="number" id="ipLimit" value="1" min="1">
                </div>
                <div class="field">
                    <label>Validity (Days)</label>
                    <input class="input" type="number" id="keyDays" value="7" min="1">
                </div>
                <button class="btn" id="genBtn" onclick="generateKey()"><i class="fas fa-plus"></i> Generate Key</button>
                <div class="key-out" id="generatedKey"></div>
            </div>

            <div class="card">
                <h2><i class="fas fa-shield-halved"></i> Session Info</h2>
                <div style="display:flex;flex-direction:column;gap:12px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-radius:12px;background:rgba(255,255,255,.02);border:1px solid var(--border-soft);">
                        <span style="color:var(--dim);font-size:11px;letter-spacing:.12em;font-weight:600;">SERVER</span>
                        <span class="badge green"><i class="fas fa-circle" style="font-size:6px;"></i> Operational</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-radius:12px;background:rgba(255,255,255,.02);border:1px solid var(--border-soft);">
                        <span style="color:var(--dim);font-size:11px;letter-spacing:.12em;font-weight:600;">PROTECTION</span>
                        <span class="badge"><i class="fas fa-lock" style="font-size:10px;"></i> Secure</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-radius:12px;background:rgba(255,255,255,.02);border:1px solid var(--border-soft);">
                        <span style="color:var(--dim);font-size:11px;letter-spacing:.12em;font-weight:600;">DATABASE</span>
                        <span class="badge cyan"><i class="fas fa-database" style="font-size:10px;"></i> Synced</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- MAINTENANCE MODE SECTION -->
        <div class="card full" style="border-color:rgba(244,63,94,0.15);">
            <h2><i class="fas fa-tools"></i> Maintenance Mode 
                <span class="maintenance-status {% if maintenance_mode %}active{% else %}inactive{% endif %}">
                    <i class="fas fa-circle" style="font-size:6px;"></i>
                    {% if maintenance_mode %}ACTIVE{% else %}INACTIVE{% endif %}
                </span>
            </h2>
            <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
                <div style="flex:1;min-width:200px;">
                    <p style="color:var(--muted);font-size:12px;margin-bottom:8px;">
                        {% if maintenance_mode %}
                        <i class="fas fa-exclamation-triangle" style="color:#fb7185;"></i> 
                        Maintenance is currently <strong style="color:#fb7185;">ACTIVE</strong>. Users will see maintenance page.
                        {% else %}
                        <i class="fas fa-check-circle" style="color:#34d399;"></i> 
                        Maintenance is <strong style="color:#34d399;">INACTIVE</strong>. All services are running normally.
                        {% endif %}
                    </p>
                </div>
                <button class="btn {% if maintenance_mode %}maintenance-on{% else %}maintenance-off{% endif %}" 
                        id="maintenanceToggle" 
                        onclick="toggleMaintenance()" 
                        style="width:auto;padding:14px 28px;min-width:180px;">
                    <i class="fas {% if maintenance_mode %}fa-power-off{% else %}fa-play{% endif %}"></i>
                    {% if maintenance_mode %}Disable Maintenance{% else %}Enable Maintenance{% endif %}
                </button>
            </div>
        </div>

        <div class="card full">
            <h2><i class="fas fa-list-ul"></i> Active Licenses</h2>
            <div class="table-wrap">
                <table>
                    <thead><tr>
                        <th>Key</th><th>Prefix</th><th>Limit</th><th>Used</th><th>Validity</th><th>Created</th><th></th>
                    </tr></thead>
                    <tbody>
                        {% for key, data in keys.items() %}
                        <tr>
                            <td><span class="badge mono">{{ key }}</span></td>
                            <td>{{ data.prefix }}</td>
                            <td>{{ data.limit }}</td>
                            <td><span class="badge {% if data.used_ips|length >= data.limit %}cyan{% else %}green{% endif %}">{{ data.used_ips|length }} / {{ data.limit }}</span></td>
                            <td>{{ data.days }}d</td>
                            <td>{{ data.created[:10] }}</td>
                            <td><button class="btn danger sm" onclick="revokeKey('{{ key }}')"><i class="fas fa-trash"></i> Revoke</button></td>
                        </tr>
                        {% else %}
                        <tr><td colspan="7" class="empty"><i class="fas fa-key"></i><br>No licenses generated yet</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="card full">
            <h2><i class="fas fa-user-secret"></i> Registered Clients</h2>
            <div class="table-wrap">
                <table>
                    <thead><tr>
                        <th>IP Address</th><th>License</th><th>Expires</th><th>Status</th>
                    </tr></thead>
                    <tbody>
                        {% for ip, key in ips.items() %}
                        <tr>
                            <td class="mono"><i class="fas fa-desktop" style="color:var(--dim);margin-right:8px;"></i>{{ ip }}</td>
                            <td><span class="badge">{{ key }}</span></td>
                            <td>{% if key_expiry[ip] %}<span class="mono">{{ key_expiry[ip].strftime('%Y-%m-%d') }}</span>{% else %}<span style="color:var(--dim);">—</span>{% endif %}</td>
                            <td><span class="badge green"><i class="fas fa-circle" style="font-size:6px;"></i> Active</span></td>
                        </tr>
                        {% else %}
                        <tr><td colspan="4" class="empty"><i class="fas fa-user-slash"></i><br>No clients registered</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <div class="toast" id="toast"></div>
    <script>
        function toast(msg, ok = true) {
            const t = document.getElementById('toast');
            t.textContent = (ok ? '✓ ' : '✗ ') + msg;
            t.style.borderColor = ok ? 'rgba(52,211,153,.3)' : 'rgba(244,63,94,.3)';
            t.className = 'toast show';
            clearTimeout(t._h);
            t._h = setTimeout(() => t.className = 'toast', 2000);
        }
        function generateKey() {
            const prefix = document.getElementById('keyPrefix').value.trim() || 'S3-HACKS';
            const limit = parseInt(document.getElementById('ipLimit').value) || 1;
            const days = parseInt(document.getElementById('keyDays').value) || 7;
            const btn = document.getElementById('genBtn');
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> Generating...';
            fetch('/admin/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({prefix, limit, days})
            })
            .then(r => r.json())
            .then(d => {
                const el = document.getElementById('generatedKey');
                el.textContent = d.key;
                el.classList.remove('reveal');
                void el.offsetWidth;
                el.classList.add('reveal');
                toast('License generated');
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-plus"></i> Generate Key';
                setTimeout(() => location.reload(), 900);
            })
            .catch(() => {
                toast('Generation failed', false);
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-plus"></i> Generate Key';
            });
        }
        function revokeKey(key) {
            if (!confirm('Revoke ' + key + '?')) return;
            fetch('/admin/revoke', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({key})
            })
            .then(r => r.json())
            .then(d => {
                if (d.success) { toast('Key revoked'); setTimeout(() => location.reload(), 700); }
                else toast(d.error, false);
            });
        }
        function toggleMaintenance() {
            const btn = document.getElementById('maintenanceToggle');
            const currentStatus = btn.textContent.includes('Disable');
            const newStatus = !currentStatus;
            
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> Processing...';
            
            fetch('/admin/maintenance', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({status: newStatus})
            })
            .then(r => r.json())
            .then(d => {
                if (d.success) {
                    toast(d.message);
                    setTimeout(() => location.reload(), 700);
                } else {
                    toast('Failed to toggle maintenance', false);
                    btn.disabled = false;
                    btn.innerHTML = currentStatus ? '<i class="fas fa-power-off"></i> Disable Maintenance' : '<i class="fas fa-play"></i> Enable Maintenance';
                }
            })
            .catch(() => {
                toast('Connection error', false);
                btn.disabled = false;
                btn.innerHTML = currentStatus ? '<i class="fas fa-power-off"></i> Disable Maintenance' : '<i class="fas fa-play"></i> Enable Maintenance';
            });
        }
    </script>
</body>
</html>
"""

MAINTENANCE_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>S3 HACKS · Maintenance</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>__STYLE__
        body { display:flex; justify-content:center; align-items:center; min-height:100vh; padding:20px; }
        .wrap { position:relative; width:100%; max-width:430px; }
        .card { padding:48px 34px; text-align:center; }
        .icon-box {
            width:72px; height:72px; margin:0 auto 20px; border-radius:22px;
            background:linear-gradient(135deg,#f43f5e,#e11d48);
            display:flex; align-items:center; justify-content:center;
            font-size:30px; color:#fff;
            box-shadow:0 14px 40px rgba(244,63,94,.3), inset 0 1px 0 rgba(255,255,255,.25);
            animation:pulse-icon 2.5s ease-in-out infinite;
        }
        @keyframes pulse-icon {
            0%,100% { transform:scale(1); box-shadow:0 14px 40px rgba(244,63,94,.3); }
            50% { transform:scale(1.05); box-shadow:0 14px 60px rgba(244,63,94,.5); }
        }
        h1 { font-size:28px; font-weight:700; letter-spacing:.06em; margin-bottom:10px; }
        .sub { color:var(--dim); font-size:9px; letter-spacing:.42em; font-weight:600; margin-bottom:24px; }
        .message {
            color:var(--muted); font-size:14px; line-height:1.7; max-width:320px; margin:0 auto 30px;
            font-weight:400;
        }
        .message strong { color:var(--text); }
        .divider {
            width:40px; height:2px; margin:0 auto 30px;
            background:linear-gradient(90deg,transparent,var(--dim),transparent);
            border-radius:2px;
        }
        .socials { display:grid; gap:12px; margin-top:6px; }
        .social {
            position:relative; overflow:hidden; display:flex; align-items:center; justify-content:center; gap:12px;
            width:100%; padding:16px; border-radius:16px; text-decoration:none; color:#fff;
            font-size:14px; font-weight:600; transition:transform .25s cubic-bezier(.22,.68,.35,1), box-shadow .25s;
        }
        .social:hover { transform:translateY(-3px); }
        .social:active { transform:scale(.98); }
        .social i { font-size:18px; }
        .social.telegram-maintenance { background:linear-gradient(135deg,#229ed9,#0088cc); }
        .social.telegram-maintenance:hover { box-shadow:0 14px 40px rgba(0,136,204,.45); }
        .footer { margin-top:30px; color:rgba(255,255,255,.14); font-size:9px; letter-spacing:.42em; font-weight:600; }
        .footer .dot { display:inline-block; width:5px; height:5px; border-radius:50%; background:#fb7185; margin-right:8px; animation:pulse-dot 2s infinite; }
    </style>
</head>
<body>
    <div class="aurora a1"></div><div class="aurora a2"></div><div class="grid-bg"></div>
    <div class="wrap">
        <div class="card">
            <div class="icon-box"><i class="fas fa-tools"></i></div>
            <h1>🔧 <span class="grad-text">Maintenance</span> Mode</h1>
            <div class="sub">S3HACKS PROXY</div>
            
            <div class="message">
                <strong>We are currently performing scheduled maintenance.</strong><br>
                Please check back later. We appreciate your patience!
            </div>
            <div class="divider"></div>

            <div class="socials">
                <a href="https://t.me/+uEc9_y-CcRIyMTY1" target="_blank" class="social telegram-maintenance">
                    <i class="fab fa-telegram-plane"></i> JOIN TELEGRAM
                </a>
            </div>

            <div class="footer"><span class="dot"></span>MAINTENANCE · PROXY OFFLINE</div>
        </div>
    </div>
</body>
</html>
"""

MAIN_UI = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>S3 HACKS · Control Center</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>__STYLE__
        body { display:flex; justify-content:center; align-items:center; min-height:100vh; padding:18px; }
        .dashboard { max-width:430px; width:100%; padding:26px 22px; }
        .header { display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; }
        .brand { display:flex; align-items:center; gap:13px; }
        .brand-icon {
            width:44px; height:44px; border-radius:14px; background:var(--grad);
            display:flex; align-items:center; justify-content:center; color:#fff; font-size:18px;
            box-shadow:0 10px 32px var(--glow), inset 0 1px 0 rgba(255,255,255,.25);
        }
        .brand-text { font-size:19px; font-weight:700; letter-spacing:-.02em; }
        .live {
            display:flex; align-items:center; gap:8px; padding:7px 15px; border-radius:100px;
            background:rgba(52,211,153,.06); border:1px solid rgba(52,211,153,.2);
        }
        .live .dot { width:7px; height:7px; border-radius:50%; background:#34d399; animation:pulse-dot 2s infinite; }
        .live span { color:#34d399; font-size:9px; font-weight:700; letter-spacing:.18em; }
        .ip-bar {
            display:flex; align-items:center; gap:12px;
            padding:13px 16px; border-radius:16px; margin-bottom:16px;
            background:rgba(255,255,255,.025); border:1px solid var(--border-soft);
        }
        .ip-bar i { color:#a5b4fc; font-size:13px; }
        .ip-bar .ip { flex:1; color:var(--muted); font-family:'Space Grotesk',monospace; font-size:12.5px; letter-spacing:.04em; }
        .proxy-btn {
            width:100%; padding:17px; border-radius:16px; font-size:14px; margin-bottom:20px;
        }
        .proxy-btn.active {
            background:linear-gradient(135deg,#059669,#0ea5e9);
            box-shadow:0 14px 40px rgba(16,185,129,.35);
            animation:activepulse 2.2s ease-in-out infinite;
        }
        @keyframes activepulse {
            0%,100% { box-shadow:0 14px 40px rgba(16,185,129,.35); }
            50% { box-shadow:0 14px 50px rgba(16,185,129,.55); }
        }
        .section { display:flex; align-items:center; gap:10px; color:var(--dim); font-size:9.5px; text-transform:uppercase; letter-spacing:.24em; font-weight:700; margin:20px 0 10px; }
        .section i { background:var(--grad); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; font-size:12px; }
        .grid { display:grid; grid-template-columns:1fr; gap:10px; }
        .item {
            background:rgba(255,255,255,.02); border:1px solid var(--border-soft);
            border-radius:16px; padding:13px 13px; display:flex; align-items:center; gap:10px;
            transition:border-color .25s, background .25s, transform .2s;
        }
        .item:hover { border-color:rgba(139,92,246,.25); background:rgba(139,92,246,.03); }
        .item .ico { font-size:15px; width:26px; text-align:center; }
        .item .info { flex:1; min-width:0; }
        .item .name { color:var(--text); font-size:11.5px; font-weight:700; letter-spacing:.04em; }
        .item .desc { color:var(--dim); font-size:9px; margin-top:2px; letter-spacing:.08em; }
        
        /* SMOOTH TOGGLE SWITCH */
        .sw {
            width:44px;
            height:24px;
            border-radius:100px;
            flex-shrink:0;
            cursor:pointer;
            background:rgba(255,255,255,.07);
            border:1px solid rgba(255,255,255,.1);
            position:relative;
            transition:background 0.4s cubic-bezier(0.34, 1.56, 0.64, 1), 
                       border-color 0.4s cubic-bezier(0.34, 1.56, 0.64, 1),
                       box-shadow 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        .sw .th {
            width:18px;
            height:18px;
            border-radius:50%;
            background: #4b5163;
            position:absolute;
            top:2px;
            left:2px;
            transition:all 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
            box-shadow:0 2px 8px rgba(0,0,0,0.5);
            will-change: transform, left;
        }
        .sw.on {
            background:var(--grad);
            border-color:transparent;
            box-shadow:0 0 24px rgba(99,102,241,0.45), inset 0 1px 0 rgba(255,255,255,0.15);
        }
        .sw.on .th {
            left:22px;
            background:#ffffff;
            box-shadow:0 2px 12px rgba(0,0,0,0.4), 0 0 20px rgba(99,102,241,0.3);
        }
        .sw:active .th {
            transform:scale(0.75);
            transition:transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        .sw.on:active .th {
            transform:scale(0.75);
        }
        .sw:hover {
            border-color:rgba(139,92,246,0.3);
        }
        .sw.on:hover {
            border-color:rgba(139,92,246,0.5);
            box-shadow:0 0 32px rgba(99,102,241,0.55), inset 0 1px 0 rgba(255,255,255,0.15);
        }
        .sw .ripple {
            position:absolute;
            border-radius:50%;
            background:rgba(139,92,246,0.2);
            transform:scale(0);
            animation:rippleAnim 0.6s ease-out forwards;
            pointer-events:none;
        }
        @keyframes rippleAnim {
            to {
                transform:scale(4);
                opacity:0;
            }
        }
        
        .socials { display:grid; gap:10px; margin-top:22px; }
        .social {
            position:relative; overflow:hidden; display:flex; align-items:center; justify-content:center; gap:11px;
            width:100%; padding:14px; border-radius:15px; text-decoration:none; color:#fff;
            font-size:13px; font-weight:600; transition:transform .25s cubic-bezier(.22,.68,.35,1), box-shadow .25s;
        }
        .social:hover { transform:translateY(-2px); }
        .social:active { transform:scale(.98); }
        .social i { font-size:17px; }
        .social.telegram { background:linear-gradient(135deg,#229ed9,#0088cc); }
        .social.telegram:hover { box-shadow:0 12px 32px rgba(0,136,204,.35); }
        .social.youtube { background:linear-gradient(135deg,#ff4e45,#d10000); }
        .social.youtube:hover { box-shadow:0 12px 32px rgba(255,0,0,.3); }
        .social.instagram { background:linear-gradient(45deg,#feda75,#fa7e1e,#d62976,#962fbf,#4f5bd5); }
        .social.instagram:hover { box-shadow:0 12px 32px rgba(225,48,108,.35); }
        .footer { text-align:center; margin-top:24px; padding-top:18px; border-top:1px solid var(--border-soft); }
        .footer-text { color:var(--dim); font-size:9px; letter-spacing:.4em; font-weight:700; }
    </style>
</head>
<body>
    <div class="aurora a1"></div><div class="aurora a2"></div><div class="grid-bg"></div>
    <div class="dashboard card">
        <div class="header">
            <div class="brand">
                <div class="brand-icon"><i class="fas fa-satellite-dish"></i></div>
                <div class="brand-text">S3 <span class="grad-text">HACKS</span></div>
            </div>
            <div class="live"><div class="dot"></div><span>Live</span></div>
        </div>

        <div class="ip-bar">
            <i class="fas fa-network-wired"></i>
            <span class="ip" id="ipDisplay">Loading...</span>
            <span class="badge green"><i class="fas fa-key" style="font-size:9px;"></i> Authorized</span>
        </div>

        <button class="btn proxy-btn" id="proxyBtn" onclick="toggleProxy()"><i class="fas fa-play"></i> Start Proxy</button>

        <div class="section"><i class="fas fa-crosshairs"></i> Aim Assist</div>
        <div class="grid">
            <div class="item">
                <div class="ico" style="color:#a78bfa;"><i class="fas fa-crosshairs"></i></div>
                <div class="info"><div class="name">HS NECK</div><div class="desc">Headshot Priority</div></div>
                <div class="sw" id="sw_hs_neck" onclick="toggle('hs_neck', event)"><div class="th"></div></div>
            </div>
            <div class="item">
                <div class="ico" style="color:#60a5fa;"><i class="fas fa-bullseye"></i></div>
                <div class="info"><div class="name">HS CHEST</div><div class="desc">Chest Lock</div></div>
                <div class="sw" id="sw_hs_chest" onclick="toggle('hs_chest', event)"><div class="th"></div></div>
            </div>
        </div>

        <div class="section"><i class="fas fa-shield-halved"></i> Protection</div>
        <div class="grid">
            <div class="item">
                <div class="ico" style="color:#34d399;"><i class="fas fa-shield-virus"></i></div>
                <div class="info"><div class="name">BYPASS</div><div class="desc">Bypass Engine</div></div>
                <div class="sw" id="sw_bypass_v1" onclick="toggle('bypass_v1', event)"><div class="th"></div></div>
            </div>
        </div>

        <div class="section"><i class="fas fa-sliders"></i> Configuration</div>
        <div class="grid">
            <div class="item">
                <div class="ico" style="color:#fbbf24;"><i class="fas fa-arrow-up"></i></div>
                <div class="info"><div class="name">BACKJUMP</div><div class="desc">Jump Enhance</div></div>
                <div class="sw" id="sw_backjump_v1" onclick="toggle('backjump_v1', event)"><div class="th"></div></div>
            </div>
            <div class="item">
                <div class="ico" style="color:#fb7185;"><i class="fas fa-gauge-high"></i></div>
                <div class="info"><div class="name">HIGH SENSI</div><div class="desc">Max Sensitivity</div></div>
                <div class="sw" id="sw_high_sensi" onclick="toggle('high_sensi', event)"><div class="th"></div></div>
            </div>
        </div>

        <div class="socials">
            <a href="https://t.me/+uEc9_y-CcRIyMTY1" target="_blank" class="social telegram">
                <i class="fab fa-telegram-plane"></i> Join Telegram
            </a>
            <a href="https://youtube.com/@s3xzr?si=LhRPsQ9LKCoB-l3o" target="_blank" class="social youtube">
                <i class="fab fa-youtube"></i> Subscribe YouTube
            </a>
            <a href="https://www.instagram.com/s3_aronnak?igsh=cWdib295YWhmbDdh" target="_blank" class="social instagram">
                <i class="fab fa-instagram"></i> Follow Instagram
            </a>
        </div>

        <div class="footer"><div class="footer-text"><span class="grad-text">S3HACKS</span> · PROXY</div></div>
    </div>

    <div class="toast" id="toast"></div>
    <script>
        let proxyActive = false;
        let isToggling = false;

        function toast(msg) {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.className = 'toast show';
            clearTimeout(t._h);
            t._h = setTimeout(() => t.className = 'toast', 1800);
        }

        function createRipple(e, element) {
            const rect = element.getBoundingClientRect();
            const ripple = document.createElement('span');
            ripple.className = 'ripple';
            const size = Math.max(rect.width, rect.height);
            ripple.style.width = ripple.style.height = size + 'px';
            ripple.style.left = (e.clientX - rect.left - size/2) + 'px';
            ripple.style.top = (e.clientY - rect.top - size/2) + 'px';
            element.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        }

        fetch('/api/ip/check').then(r=>r.json()).then(d=>{
            document.getElementById('ipDisplay').textContent = d.ip;
        });

        fetch('/api/status').then(r=>r.json()).then(d=>{
            const c = d.config;
            const set = (id, val) => {
                const el = document.getElementById(id);
                if (el) el.className = 'sw' + (val ? ' on' : '');
            };
            set('sw_hs_neck', c.HS_NECK);
            set('sw_hs_chest', c.HS_CHEST);
            set('sw_bypass_v1', c.BYPASSV1);
            set('sw_backjump_v1', c.BACKJUMPV1);
            set('sw_high_sensi', c.HIGH_SENSI);
        });

        function toggleProxy() {
            proxyActive = !proxyActive;
            const btn = document.getElementById('proxyBtn');
            if(proxyActive) {
                btn.innerHTML = '<i class="fas fa-circle" style="font-size:9px;"></i> Proxy Active';
                btn.classList.add('active');
                toast('Proxy is now active');
            } else {
                btn.innerHTML = '<i class="fas fa-play"></i> Start Proxy';
                btn.classList.remove('active');
                toast('Proxy stopped');
            }
        }

        function toggle(feature, event) {
            if (isToggling) return;
            
            const el = document.getElementById('sw_' + feature);
            if (!el) return;
            
            if (event) createRipple(event, el);
            
            const on = el.classList.contains('on');
            const val = !on;
            
            el.classList.toggle('on', val);
            
            if (feature === 'hs_neck' && val === true) {
                const chestEl = document.getElementById('sw_hs_chest');
                if (chestEl && chestEl.classList.contains('on')) {
                    chestEl.classList.remove('on');
                    fetch('/api/toggle', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({feature: 'hs_chest', value: false})
                    });
                }
            } else if (feature === 'hs_chest' && val === true) {
                const neckEl = document.getElementById('sw_hs_neck');
                if (neckEl && neckEl.classList.contains('on')) {
                    neckEl.classList.remove('on');
                    fetch('/api/toggle', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({feature: 'hs_neck', value: false})
                    });
                }
            }
            
            isToggling = true;
            el.style.opacity = '0.6';
            el.style.cursor = 'wait';
            
            fetch('/api/toggle', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({feature, value: val})
            })
            .then(r => r.json())
            .then(d => {
                if(d.success) {
                    toast(feature.toUpperCase() + ' ' + (val ? 'ON' : 'OFF'));
                } else {
                    el.classList.toggle('on', !val);
                    toast('Failed to toggle ' + feature, false);
                }
            })
            .catch(() => {
                el.classList.toggle('on', !val);
                toast('Connection error', false);
            })
            .finally(() => {
                isToggling = false;
                el.style.opacity = '1';
                el.style.cursor = 'pointer';
            });
        }
    </script>
</body>
</html>
"""

KEY_ENTRY = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>S3 HACKS · Authorization</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>__STYLE__
        body { display:flex; justify-content:center; align-items:center; min-height:100vh; padding:20px; }
        .wrap { position:relative; width:100%; max-width:410px; }
        .card { padding:40px 34px; text-align:center; }
        .logo {
            width:62px; height:62px; margin:0 auto 16px; border-radius:18px;
            background:var(--grad); display:flex; align-items:center; justify-content:center;
            font-size:25px; color:#fff;
            box-shadow:0 14px 40px var(--glow), inset 0 1px 0 rgba(255,255,255,.25);
            animation:logofloat 5s ease-in-out infinite;
        }
        @keyframes logofloat { 0%,100% { transform:translateY(0);} 50% { transform:translateY(-6px);} }
        h1 { font-size:28px; font-weight:700; letter-spacing:.14em; }
        .sub { color:var(--dim); font-size:9px; letter-spacing:.42em; margin:8px 0 30px; font-weight:600; }
        .field { margin-bottom:16px; }
        .field label { display:block; color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.22em; font-weight:600; margin-bottom:8px; text-align:left; }
        .key-input {
            width:100%; padding:16px 18px; outline:none; color:var(--text);
            background:rgba(255,255,255,.03); border:1px solid var(--border);
            border-radius:15px; font-size:16px; text-align:center; letter-spacing:.14em;
            font-family:'Space Grotesk',monospace; font-weight:700;
            transition:border-color .3s, box-shadow .3s, background .3s;
        }
        .key-input::placeholder { color:var(--dim); letter-spacing:.06em; font-weight:500; }
        .key-input:focus {
            border-color:rgba(139,92,246,.5); background:rgba(139,92,246,.04);
            box-shadow:0 0 0 4px rgba(139,92,246,.08), 0 0 30px rgba(99,102,241,.15);
        }
        .btn { width:100%; padding:17px; font-size:13.5px; margin-top:4px; }
        .msg {
            margin-top:16px; padding:13px 16px; border-radius:12px; font-size:13px; font-weight:600;
            display:none; animation:rise .35s cubic-bezier(.22,.68,.35,1);
        }
        .msg.error { display:block; color:#fb7185; background:rgba(244,63,94,.07); border:1px solid rgba(244,63,94,.18); }
        .msg.success { display:block; color:#34d399; background:rgba(52,211,153,.07); border:1px solid rgba(52,211,153,.18); }
        .msg .fa-circle-check, .msg .fa-circle-xmark { margin-right:8px; }
        .socials { display:grid; gap:10px; margin-top:22px; }
        .social {
            position:relative; overflow:hidden; display:flex; align-items:center; justify-content:center; gap:11px;
            width:100%; padding:14px; border-radius:15px; text-decoration:none; color:#fff;
            font-size:13px; font-weight:600; transition:transform .25s cubic-bezier(.22,.68,.35,1), box-shadow .25s;
        }
        .social:hover { transform:translateY(-2px); }
        .social:active { transform:scale(.98); }
        .social i { font-size:17px; }
        .social.telegram { background:linear-gradient(135deg,#229ed9,#0088cc); }
        .social.telegram:hover { box-shadow:0 12px 32px rgba(0,136,204,.35); }
        .social.youtube { background:linear-gradient(135deg,#ff4e45,#d10000); }
        .social.youtube:hover { box-shadow:0 12px 32px rgba(255,0,0,.3); }
        .social.instagram { background:linear-gradient(45deg,#feda75,#fa7e1e,#d62976,#962fbf,#4f5bd5); }
        .social.instagram:hover { box-shadow:0 12px 32px rgba(225,48,108,.35); }
        .social.getkey { 
            background:linear-gradient(135deg,#f59e0b,#d97706); 
        }
        .social.getkey:hover { 
            box-shadow:0 12px 32px rgba(245,158,11,.35); 
        }
        .footer { margin-top:26px; color:rgba(255,255,255,.14); font-size:9px; letter-spacing:.42em; font-weight:600; }
        .footer .dot { display:inline-block; width:5px; height:5px; border-radius:50%; background:#34d399; margin-right:8px; animation:pulse-dot 2s infinite; }
    </style>
</head>
<body>
    <div class="aurora a1"></div><div class="aurora a2"></div><div class="grid-bg"></div>
    <div class="wrap">
        <div class="card">
            <div class="logo"><i class="fas fa-key"></i></div>
            <h1>S3<span class="grad-text">HACKS</span></h1>
            <div class="sub">PROXY ACCESS</div>
            <div class="field">
                <label>Enter License Key</label>
                <input class="key-input" type="text" id="keyInput" placeholder="S3-HACKS-XXXX" autocomplete="off" spellcheck="false" maxlength="32">
            </div>
            <button class="btn" id="verifyBtn" onclick="verifyKey()"><i class="fas fa-unlock"></i> Activate</button>
            <div class="msg" id="msgBox"></div>

            <div class="socials">
                <a href="https://s3-hacks-get-key.onrender.com" target="_blank" class="social getkey">
                    <i class="fas fa-key"></i> GET KEY
                </a>
                <a href="https://t.me/+uEc9_y-CcRIyMTY1" target="_blank" class="social telegram">
                    <i class="fab fa-telegram-plane"></i> Join Telegram
                </a>
                <a href="https://youtube.com/@s3xzr?si=LhRPsQ9LKCoB-l3o" target="_blank" class="social youtube">
                    <i class="fab fa-youtube"></i> Subscribe YouTube
                </a>
                <a href="https://www.instagram.com/s3_aronnak?igsh=cWdib295YWhmbDdh" target="_blank" class="social instagram">
                    <i class="fab fa-instagram"></i> Follow Instagram
                </a>
            </div>

            <div class="footer"><span class="dot"></span>SECURE · VERIFIED</div>
        </div>
    </div>

    <script>
        const input = document.getElementById('keyInput');
        input.addEventListener('keydown', function(e) {
            if(e.key === 'Enter') verifyKey();
        });
        input.focus();

        function verifyKey() {
            const key = input.value.trim().toUpperCase();
            const btn = document.getElementById('verifyBtn');
            const msg = document.getElementById('msgBox');

            if(!key) {
                msg.className = 'msg error';
                msg.innerHTML = '<i class="fas fa-circle-xmark"></i>Please enter your license key';
                input.focus();
                return;
            }

            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> Verifying...';
            msg.className = 'msg';

            fetch('/verify', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({key})
            })
            .then(r => r.json())
            .then(d => {
                if(d.success) {
                    msg.className = 'msg success';
                    msg.innerHTML = '<i class="fas fa-circle-check"></i>' + d.message;
                    btn.innerHTML = '<i class="fas fa-check"></i> Authorized';
                    setTimeout(() => location.reload(), 800);
                } else {
                    msg.className = 'msg error';
                    msg.innerHTML = '<i class="fas fa-circle-xmark"></i>' + d.message;
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-unlock"></i> Activate';
                }
            })
            .catch(() => {
                msg.className = 'msg error';
                msg.innerHTML = '<i class="fas fa-circle-xmark"></i>Connection error';
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-unlock"></i> Activate';
            });
        }
    </script>
</body>
</html>
"""

LOGIN_PAGE = LOGIN_PAGE.replace("__STYLE__", BASE_STYLE)
ADMIN_DASHBOARD = ADMIN_DASHBOARD.replace("__STYLE__", BASE_STYLE)
MAIN_UI = MAIN_UI.replace("__STYLE__", BASE_STYLE)
KEY_ENTRY = KEY_ENTRY.replace("__STYLE__", BASE_STYLE)
MAINTENANCE_PAGE = MAINTENANCE_PAGE.replace("__STYLE__", BASE_STYLE)

def get_public_ip():
    try:
        response = requests.get('https://api.ipify.org', timeout=5)
        return response.text.strip()
    except:
        try:
            response = requests.get('https://icanhazip.com', timeout=5)
            return response.text.strip()
        except:
            return "Unable to get public IP"

# ================= FIREBASE PERSISTENCE (S3) =================
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

if _fb is not None:
    try:
        _remote = _fb.get()
        if _remote:
            with open(DATA_FILE, "w") as _f:
                json.dump(_remote, _f, indent=2)
            print("[*] S3 data restored from Firebase")
    except Exception as e:
        print(f"[ERROR] Firebase restore: {e}")

    _save_fn = globals().get("save_data") or globals().get("save_all") or globals().get("write_data")
    if _save_fn:
        def _wrapped_save(*a, **k):
            _r = _save_fn(*a, **k)
            try:
                with open(DATA_FILE) as _f:
                    _fb.set(json.load(_f))
            except Exception as e:
                print(f"[ERROR] Firebase push: {e}")
            return _r
        save_data = _wrapped_save
        print(f"[*] Save function wrapped: {_save_fn.__name__}")
    else:
        print("[WARN] save function nahi mila - 'def save' search karke naam check karo")

    try:
        load_data()
    except Exception:
        pass
# =============================================================

if __name__ == "__main__":
    # Load existing data before starting
    load_data()
    
    public_ip = get_public_ip()
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "127.0.0.1"
    
    print("\n" + "="*50)
    print("  S3HACKS PROXY INTERCEPTOR")
    print("="*50)
    print(f"  Server   : http://{local_ip}:{PORT}")
    print(f"  Public IP: http://{public_ip}:{PORT}")
    print(f"  Admin    : http://{local_ip}:{PORT}/Po7eO")
    print(f"  Port     : {PORT}")
    print(f"  Status   : Running")
    print(f"  Key API  : {KEY_API_URL}")
    print(f"  Data File: {DATA_FILE}")
    print(f"  Maintenance: {'ON' if maintenance_mode else 'OFF'}")
    print("="*50 + "\n")
    
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
