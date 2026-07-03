from flask import Flask, render_template_string, request, session, redirect, jsonify, send_file
import json
import os
import random
import string
import time
import hashlib
import collections
import re
import shutil
from datetime import datetime, timezone, timedelta
try:
    import requests as _req_tg
    _TG_OK = True
except ImportError:
    _req_tg = None
    _TG_OK = False

  
app = Flask(__name__)
app.secret_key = 'server_key_bi_mat_2026_vinhvien'
app.permanent_session_lifetime = timedelta(days=365)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    return response

# --- GLOBAL OPTIONS HANDLER (fix CORS preflight for all routes) ---
@app.before_request
def handle_options():
    # Xử lý CORS preflight (OPTIONS) cho tất cả routes
    if request.method == 'OPTIONS':
        from flask import make_response
        resp = make_response('', 204)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        return resp

# --- HEALTH CHECK ENDPOINT ---
@app.route('/healthz')
def healthz():
    return jsonify({"status": "ok", "db": os.path.exists(DB_FILE)}), 200

# --- KEEP-ALIVE: self-ping every 14 minutes to reduce cold starts ---
import threading, urllib.request as _ureq, urllib.parse

def _keep_alive_worker():
    import time as _time
    _time.sleep(60)  # wait for server to fully start
    while True:
        _time.sleep(14 * 60)
        try:
            host = os.environ.get('RENDER_EXTERNAL_URL', '')
            if host:
                _ureq.urlopen(host.rstrip('/') + '/healthz', timeout=10)
        except Exception:
            pass

_ka_thread = threading.Thread(target=_keep_alive_worker, daemon=True)
_ka_thread.start()

# ---- EXTRA KEEP-ALIVE #2: additional self-ping every 14 minutes (offset 7 min) ----
def _keep_alive_worker2():
    import time as _t2
    _t2.sleep(420)  # 7-minute offset from first pinger
    while True:
        _t2.sleep(14 * 60)
        try:
            host2 = os.environ.get('RENDER_EXTERNAL_URL', '')
            if host2:
                _ureq.urlopen(host2.rstrip('/') + '/healthz', timeout=10)
        except Exception:
            pass

_ka_thread2 = threading.Thread(target=_keep_alive_worker2, daemon=True)
_ka_thread2.start()

# ---- EXTRA KEEP-ALIVE #3: third self-ping every 14 minutes (offset ~4.5 min) ----
def _keep_alive_worker3():
    import time as _t3
    _t3.sleep(270)  # 4.5-minute offset — fills gap between worker1 and worker2
    while True:
        _t3.sleep(14 * 60)
        try:
            host3 = os.environ.get('RENDER_EXTERNAL_URL', '')
            if host3:
                _ureq.urlopen(host3.rstrip('/') + '/healthz', timeout=10)
        except Exception:
            pass

_ka_thread3 = threading.Thread(target=_keep_alive_worker3, daemon=True)
_ka_thread3.start()
# With 3 pingers (offsets: 0, 7min, 4.5min) each cycling every 14min,
# the server gets pinged roughly every ~4.5 minutes — well within Render's 15-min sleep threshold.



BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Use Render persistent disk if available, otherwise fall back to script directory
DATA_DIR = '/data' if os.path.isdir('/data') else BASE_DIR
DB_FILE = os.path.join(DATA_DIR, "database_keys.json")

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)
VN_TZ = timezone(timedelta(hours=7))

# --- REAL IP FROM SERVER ---
def get_real_ip():
    if request.headers.get('CF-Connecting-IP'): return request.headers.get('CF-Connecting-IP')
    if request.headers.get('X-Forwarded-For'): return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

# --- DATABASE ENGINE ---
def load_db():
    if not os.path.exists(DB_FILE):
        return {"___ADMIN_CONFIG___": {"user": "vkhanh", "pass": "1"}}
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            if "___ADMIN_CONFIG___" not in data:
                data["___ADMIN_CONFIG___"] = {"user": "vkhanh", "pass": "1"}
            return data
        except:
            return {"___ADMIN_CONFIG___": {"user": "vkhanh", "pass": "1"}}

def save_db(data):
    tmp = DB_FILE + '.tmp'
    bak = DB_FILE + '.bak'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        if os.path.exists(DB_FILE):
            shutil.copy2(DB_FILE, bak)
        os.replace(tmp, DB_FILE)
    except Exception as e:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass

def get_time_left_str(expiry_timestamp):
    if expiry_timestamp == -1: return "∞"
    now = time.time()
    diff = expiry_timestamp - now
    if diff <= 0: return "Hết hạn"
    days = int(diff // 86400)
    hours = int((diff % 86400) // 3600)
    minutes = int((diff % 3600) // 60)
    parts = []
    if days > 0: parts.append(f"{days} ngày")
    if hours > 0: parts.append(f"{hours} giờ")
    if minutes > 0: parts.append(f"{minutes} phút")
    return " ".join(parts) if parts else "Dưới 1 phút"

def format_ts(ts):
    if not ts: return "Chưa cập nhật"
    return datetime.fromtimestamp(ts, VN_TZ).strftime('%d/%m/%Y %H:%M:%S')

def format_full_ts(ts):
    if not ts: return "Chưa kích hoạt"
    dt = datetime.fromtimestamp(ts, VN_TZ)
    days = ["Chủ Nhật", "Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7"]
    day_str = days[int(dt.strftime('%w'))]
    return f"{day_str}, {dt.strftime('%d/%m/%Y %H:%M:%S')} (VN)"

# --- ROUTES ---
@app.route('/nhac.mp3')
def play_music():
    f = os.path.join(BASE_DIR, 'nhac.mp3')
    if os.path.exists(f): return send_file(f, mimetype='audio/mp3')
    return jsonify({"status": "missing"}), 404

@app.route('/nhac2.mp3')
def play_music2():
    f = os.path.join(BASE_DIR, 'nhac2.mp3')
    if os.path.exists(f): return send_file(f, mimetype='audio/mp3')
    return jsonify({"status": "missing"}), 404

@app.route('/nhac3.mp3')
def play_music3():
    f = os.path.join(BASE_DIR, 'nhac3.mp3')
    if os.path.exists(f): return send_file(f, mimetype='audio/mp3')
    return jsonify({"status": "missing"}), 404

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        k = request.form.get('key', '').strip()
        db = load_db()
        if k in db and not k.startswith("___"):
            info = db[k]
            now = time.time()
            if isinstance(info.get('used_devices', []), list):
                new_devs = {}
                for d in info.get('used_devices', []): new_devs[d] = info.get('expiry_time', 0)
                info['used_devices'] = new_devs
                save_db(db)
            if info['status'] == 'Đã kích hoạt':
                is_full = len(info['used_devices']) >= info['max_devices']
                _non_perm = [e for e in info['used_devices'].values() if e != -1]
                all_exp = len(_non_perm) > 0 and all(now > e for e in _non_perm)
                if is_full and all_exp:
                    info['status'] = "Hết hạn"
                    save_db(db)
            return jsonify({
                "exists": True, "key": k, "key_status": info['status'],
                "duration": f"{info['duration_val']} {info['duration_unit']}" if info['duration_unit'] != 'permanent' else "Vĩnh viễn",
                "max_devices": info['max_devices'], "used_devices": len(info['used_devices']),
                "created_at": format_ts(info.get('created_at', 0)),
                "activated_time": format_ts(info.get('activated_time')) if info.get('activated_time') else "Chưa kích hoạt",
                "dev_dict": info['used_devices']
            })
        return jsonify({"exists": False, "msg": "Mã Key không tồn tại trên hệ thống máy chủ!"})
    return render_template_string(UI_TEMPLATE)

@app.route('/login', methods=['POST'])
def login():
    db = load_db()
    admin_cfg = db.get("___ADMIN_CONFIG___", {"user": "vkhanh", "pass": "1"})
    if request.form.get('user') == admin_cfg['user'] and request.form.get('pass') == admin_cfg['pass']:
        session.clear()
        session.permanent = True
        session['is_admin'] = True
        session['admin_user'] = admin_cfg['user']
        session['admin_pass'] = admin_cfg['pass']
        session.modified = True
        # Auto-whitelist admin's IP on first successful login
        real_ip = None
        if request.headers.get('CF-Connecting-IP'):
            real_ip = request.headers.get('CF-Connecting-IP')
        elif request.headers.get('X-Forwarded-For'):
            real_ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
        else:
            real_ip = request.remote_addr
        if real_ip:
            saved_owners = db.get('___OWNER_IPS___', [])
            if real_ip not in saved_owners:
                saved_owners.append(real_ip)
                db['___OWNER_IPS___'] = saved_owners
                save_db(db)
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Sai thông tin tài khoản hoặc mật khẩu quản trị!"})

@app.route('/api/change_admin', methods=['POST'])
def change_admin():
    db = load_db()
    admin_cfg = db.get("___ADMIN_CONFIG___", {"user": "vkhanh", "pass": "1"})
    if not session.get('is_admin') or session.get('admin_pass') != admin_cfg['pass']:
        return jsonify({"status": "error"}), 401
    new_u = request.form.get('u', '').strip()
    new_p = request.form.get('p', '').strip()
    if new_u and new_p:
        db["___ADMIN_CONFIG___"] = {"user": new_u, "pass": new_p}
        save_db(db)
        # Update session to stay logged in — no logout
        session['admin_user'] = new_u
        session['admin_pass'] = new_p
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Tài khoản và mật khẩu không được để trống!"})

@app.before_request
def check_admin_changed():
    # Bỏ qua OPTIONS request (CORS preflight) — không cần check session
    if request.method == 'OPTIONS':
        return
    if session.get('is_admin'):
        db = load_db()
        admin_cfg = db.get("___ADMIN_CONFIG___", {"user": "vkhanh", "pass": "1"})
        if session.get('admin_pass') != admin_cfg['pass'] or session.get('admin_user') != admin_cfg['user']:
            session.clear()

@app.route('/admin', methods=['POST'])
def admin_add_key():
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    db = load_db()
    mode = request.form.get('mode', 'random')
    time_val = request.form.get('v', '1').strip()
    time_unit = request.form.get('u')
    max_dev = int(request.form.get('d', 1))
    if mode == 'custom' and request.form.get('c_key', '').strip():
        key_name = request.form.get('c_key').strip()
    else:
        p1 = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))
        p2 = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))
        pref_map = {"permanent": "VIP", "ngày": f"{time_val}DAY", "phút": f"{time_val}P", "tiếng": f"{time_val}H", "tháng": f"{time_val}M", "năm": f"{time_val}Y"}
        key_name = f"{pref_map.get(time_unit, 'KEY')}-{p1}-{p2}"
    db[key_name] = {
        "duration_val": int(time_val) if time_unit != "permanent" else 0,
        "duration_unit": time_unit, "max_devices": max_dev, "status": "Chưa kích hoạt",
        "activated_time": None, "created_at": time.time(), "used_devices": {}
    }
    save_db(db)
    return jsonify({"status": "success", "key": key_name})

@app.route('/api/list_keys', methods=['GET'])
def list_keys():
    if not session.get('is_admin'): return jsonify([]), 401
    db = load_db()
    now = time.time()
    res = []
    for k, v in db.items():
        if k.startswith("___"): continue
        if isinstance(v.get('used_devices', []), list):
            new_devs = {}
            for d in v.get('used_devices', []): new_devs[d] = v.get('expiry_time', 0)
            v['used_devices'] = new_devs
            save_db(db)
        if v['status'] == "Đã kích hoạt":
            is_full = len(v['used_devices']) >= v['max_devices']
            _non_perm2 = [e for e in v['used_devices'].values() if e != -1]
            all_exp = len(_non_perm2) > 0 and all(now > e for e in _non_perm2)
            if is_full and all_exp:
                v['status'] = "Hết hạn"
                save_db(db)
        dev_list = [{"device_id": did, "expiry": exp} for did, exp in v['used_devices'].items()]
        age_hours = (now - v.get('created_at', now)) / 3600
        res.append({
            "key": k, "status": v['status'],
            "han_dung": f"{v['duration_val']} {v['duration_unit']}" if v['duration_unit'] != 'permanent' else "Vĩnh viễn",
            "thiet_bi": f"{len(v['used_devices'])}/{v['max_devices']}",
            "activated_time_str": format_full_ts(v.get('activated_time')),
            "created_at_str": format_ts(v.get('created_at')),
            "creator_info": v.get('creator_info', 'Admin Gốc'),
            "devices": dev_list, "is_free": k.startswith("FREE-"),
            "created_at_ts": v.get('created_at', 0),
            "age_hours": round(age_hours, 1)
        })
    return jsonify(res)

@app.route('/delete/<key>')
def delete(key):
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    db = load_db()
    if key in db:
        del db[key]
        # Also remove from IP map
        ip_map = db.get("___IP_KEY_MAP___", {})
        to_remove = [ip for ip, k in ip_map.items() if k == key]
        for ip in to_remove: del ip_map[ip]
        db["___IP_KEY_MAP___"] = ip_map
        save_db(db)
    return jsonify({"status": "success"})

@app.route('/reset/<key>')
def reset_key(key):
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    db = load_db()
    if key in db:
        db[key]['status'] = "Chưa kích hoạt"
        db[key]['activated_time'] = None
        db[key]['used_devices'] = {}
        save_db(db)
    return jsonify({"status": "success"})

@app.route('/admin/free_setup', methods=['POST'])
def admin_free_setup():
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    db = load_db()
    db["___FREE_CONFIG___"] = {"val": request.form.get('v'), "unit": request.form.get('u'), "dev": request.form.get('d')}
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/admin/get_free_config', methods=['GET'])
def admin_get_free_config():
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    db = load_db()
    cfg = db.get("___FREE_CONFIG___", {"val": "12", "unit": "tiếng", "dev": "1"})
    return jsonify({"status": "success", "val": str(cfg.get('val', '12')), "unit": str(cfg.get('unit', 'tiếng')), "dev": str(cfg.get('dev', '1'))})

@app.route('/api/gen_free_task', methods=['POST'])
def gen_free_task():
    db = load_db()
    cfg = db.get("___FREE_CONFIG___", {"val": 12, "unit": "tiếng", "dev": 9999})
    client_ip_info = request.form.get('ip_info', 'Không quét được Client')
    server_ip = get_real_ip()
    final_info = f"SV IP: {server_ip} | {client_ip_info}"

    # Per-IP key: check if this IP already has a valid key
    ip_map = db.get("___IP_KEY_MAP___", {})
    existing_key = ip_map.get(server_ip)
    if existing_key and existing_key in db:
        existing_info = db[existing_key]
        created_at = existing_info.get('created_at', 0)
        age_hours = (time.time() - created_at) / 3600
        # Return existing key if < 12h old or still active
        if age_hours < 12 or existing_info.get('status') == 'Đã kích hoạt':
            return jsonify({"status": "success", "key": existing_key, "reused": True})

    k = f"FREE-{''.join(random.choices(string.ascii_uppercase + string.digits, k=5))}"
    db[k] = {
        "duration_val": int(cfg['val']), "duration_unit": cfg['unit'],
        "max_devices": int(cfg['dev']),
        "status": "Chưa kích hoạt", "activated_time": None,
        "created_at": time.time(), "used_devices": {},
        "creator_info": final_info,
        "client_ip": server_ip
    }
    # Update IP map
    ip_map[server_ip] = k
    db["___IP_KEY_MAP___"] = ip_map
    save_db(db)
    return jsonify({"status": "success", "key": k, "reused": False})

@app.route('/api/regen_free_key', methods=['POST'])
def regen_free_key():
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    target_ip = request.form.get('ip', '').strip()
    db = load_db()
    cfg = db.get("___FREE_CONFIG___", {"val": 12, "unit": "tiếng", "dev": 9999})
    ip_map = db.get("___IP_KEY_MAP___", {})

    # Delete old key for this IP if exists
    old_key = ip_map.get(target_ip)
    if old_key and old_key in db: del db[old_key]

    k = f"FREE-{''.join(random.choices(string.ascii_uppercase + string.digits, k=5))}"
    db[k] = {
        "duration_val": int(cfg['val']), "duration_unit": cfg['unit'],
        "max_devices": int(cfg['dev']),
        "status": "Chưa kích hoạt", "activated_time": None,
        "created_at": time.time(), "used_devices": {},
        "creator_info": f"Tái tạo bởi Admin | IP: {target_ip}",
        "client_ip": target_ip
    }
    ip_map[target_ip] = k
    db["___IP_KEY_MAP___"] = ip_map
    save_db(db)
    return jsonify({"status": "success", "key": k})

@app.route('/api/verify', methods=['POST'])
def api_verify():
    """
    ENDPOINT CHÍNH — Tool/script bên ngoài gọi để xác thực key + hwid.

    ══════════════════════════════════════════════════════════════════
    CƠ CHẾ HOẠT ĐỘNG:
    ══════════════════════════════════════════════════════════════════
    1. Gửi POST với { "key": "...", "hwid": "DEVICE_ID_CỐ_ĐỊNH" }
       Bắt buộc: hwid phải là chuỗi CỐ ĐỊNH của máy (không random mỗi lần!)
       Nếu hwid thay đổi mỗi lần → server xem là thiết bị mới → lỗi device_limit.

    2. Lần đầu gọi (key "Chưa kích hoạt", hwid chưa có):
       → Key được kích hoạt, hwid được đăng ký, timer bắt đầu chạy từ LÚC NÀY.
       → Trả về: { "status": "success", "is_new_device": true, "expiry_timestamp": ... }

    3. Lần sau gọi (hwid đã đăng ký):
       → Kiểm tra expiry của riêng hwid đó.
       → Nếu còn hạn: { "status": "success", "time_left": "X ngày Y giờ" }
       → Nếu hết hạn: { "status": "expired" }

    4. Nếu key là Vĩnh Viễn (permanent):
       → expiry_timestamp = -1, time_left = "∞", không bao giờ expired.

    5. Nếu key đã hết hạn (status "Hết hạn") hoặc max devices đã đầy:
       → Không cho đăng ký thiết bị mới.
    ══════════════════════════════════════════════════════════════════
    """
    data = request.get_json(silent=True) or {}
    key = (data.get('key', '') or request.form.get('key', '')).strip()
    hwid = (data.get('hwid', '') or data.get('device_id', '') or request.form.get('hwid', '') or request.form.get('device_id', '')).strip()
    if not key or not hwid:
        return jsonify({"status": "error", "message": "Missing key or hwid. Gửi: {key, hwid}"})
    db = load_db()
    if key not in db or key.startswith("___"):
        return jsonify({"status": "invalid", "message": "Key does not exist"})
    info = db[key]
    now = time.time()
    # Migrate dạng list cũ sang dict
    if isinstance(info.get('used_devices', []), list):
        new_devs = {}
        for d in info.get('used_devices', []): new_devs[d] = info.get('expiry_time', 0)
        info['used_devices'] = new_devs
    # Tính số giây theo thời hạn key (dùng khi đăng ký device mới)
    val, unit = info['duration_val'], info['duration_unit']
    sec = -1
    if unit == "phút": sec = val * 60
    elif unit == "tiếng": sec = val * 3600
    elif unit == "ngày": sec = val * 86400
    elif unit == "tháng": sec = val * 30 * 86400
    elif unit == "năm": sec = val * 365 * 86400
    # elif unit == "permanent": sec = -1  (vĩnh viễn)
    is_permanent = (sec == -1)
    # ── Kiểm tra key đã hết hạn toàn bộ (status "Hết hạn") ──
    if info['status'] == "Hết hạn":
        return jsonify({
            "status": "expired",
            "message": "Key này đã hết hạn và không còn dùng được",
            "key_status": "Hết hạn",
            "expiry_timestamp": None,
            "is_permanent": False,
            "time_left": "Hết hạn"
        })
    # ── Tự động kích hoạt khi lần đầu dùng ──
    is_first_activation = (info['status'] == "Chưa kích hoạt")
    if is_first_activation:
        info['status'] = "Đã kích hoạt"
        info['activated_time'] = now
    # ── Thiết bị đã đăng ký → chỉ kiểm tra expiry, KHÔNG tạo mới ──
    if hwid in info['used_devices']:
        dev_exp = info['used_devices'][hwid]
        if dev_exp != -1 and now > dev_exp:
            # Thiết bị này hết hạn → cập nhật trạng thái key nếu tất cả hết
            _non_perm = [e for e in info['used_devices'].values() if e != -1]
            is_full = len(info['used_devices']) >= info['max_devices']
            all_exp = len(_non_perm) > 0 and all(now > e for e in _non_perm)
            if is_full and all_exp:
                info['status'] = "Hết hạn"
            save_db(db)
            return jsonify({
                "status": "expired",
                "message": "Key đã hết hạn trên thiết bị này",
                "expiry_timestamp": dev_exp,
                "expiry_str": format_ts(dev_exp),
                "is_permanent": False
            })
        save_db(db)
        return jsonify({
            "status": "success",
            "message": "Key hợp lệ",
            "time_left": get_time_left_str(dev_exp),
            "expiry_timestamp": dev_exp,
            "expiry_str": format_ts(dev_exp) if dev_exp != -1 else "Vĩnh Viễn",
            "is_permanent": (dev_exp == -1),
            "is_new_device": False
        })
    # ── Thiết bị chưa đăng ký → kiểm tra slot rồi đăng ký ──
    else:
        # Kiểm tra xem có slot trống không
        if len(info['used_devices']) >= info['max_devices']:
            save_db(db)
            return jsonify({
                "status": "device_limit",
                "message": f"Đã đạt giới hạn thiết bị ({info['max_devices']} thiết bị)",
                "max_devices": info['max_devices'],
                "used_devices": len(info['used_devices'])
            })
        # Tính expiry cho thiết bị mới
        dev_exp = -1 if is_permanent else (now + sec)
        info['used_devices'][hwid] = dev_exp
        save_db(db)
        return jsonify({
            "status": "success",
            "message": "Thiết bị đã được đăng ký thành công",
            "time_left": get_time_left_str(dev_exp),
            "expiry_timestamp": dev_exp,
            "expiry_str": format_ts(dev_exp) if dev_exp != -1 else "Vĩnh Viễn",
            "is_permanent": is_permanent,
            "is_new_device": True,
            "activated_now": is_first_activation
        })


@app.route('/api/check_expiry', methods=['GET', 'POST', 'OPTIONS'])
def api_check_expiry():
    """
    ══════════════════════════════════════════════════════════════════
    ENDPOINT CHECK HẠN SỬ DỤNG KEY TỪ BÊN NGOÀI (READ-ONLY)
    ══════════════════════════════════════════════════════════════════

    MỤC ĐÍCH: Kiểm tra hạn sử dụng mà KHÔNG tạo device mới,
    KHÔNG kích hoạt key, KHÔNG thay đổi dữ liệu.
    Dùng sau khi đã verify lần đầu qua /api/verify.

    REQUEST (GET hoặc POST — form-data hoặc JSON):
        key       : mã key cần kiểm tra
        hwid      : device ID của thiết bị (tên khác: device_id)

    RESPONSE JSON:
    ┌─────────────────────────────────────────────────────────────┐
    │ Còn hạn:                                                    │
    │   { "status": "valid",                                      │
    │     "time_left": "5 ngày 3 giờ",                           │
    │     "expiry_timestamp": 1717000000,   ← Unix timestamp      │
    │     "expiry_str": "10/06/2024 15:30:00",                    │
    │     "is_permanent": false }                                 │
    │                                                             │
    │ Vĩnh viễn:                                                  │
    │   { "status": "valid",                                      │
    │     "time_left": "∞",                                       │
    │     "expiry_timestamp": -1,                                 │
    │     "expiry_str": "Vĩnh Viễn",                             │
    │     "is_permanent": true }                                  │
    │                                                             │
    │ Hết hạn:                                                    │
    │   { "status": "expired",                                    │
    │     "expiry_timestamp": 1710000000,                         │
    │     "expiry_str": "10/03/2024 08:00:00" }                   │
    │                                                             │
    │ Chưa kích hoạt (chưa từng verify):                         │
    │   { "status": "not_activated",                              │
    │     "message": "..." }                                      │
    │                                                             │
    │ Device chưa đăng ký trên key:                               │
    │   { "status": "device_not_found",                           │
    │     "message": "..." }                                      │
    │                                                             │
    │ Key không tồn tại:                                          │
    │   { "status": "invalid" }                                   │
    └─────────────────────────────────────────────────────────────┘

    LƯU Ý: Endpoint này CHỈ ĐỌC — không kích hoạt key, không
    đăng ký thiết bị mới. Để đăng ký lần đầu, dùng /api/verify.
    ══════════════════════════════════════════════════════════════════
    """
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or {}
    key = (data.get('key', '') or request.values.get('key', '')).strip()
    hwid = (data.get('hwid', '') or data.get('device_id', '') or request.values.get('hwid', '') or request.values.get('device_id', '')).strip()
    if not key:
        return jsonify({"status": "error", "message": "Thiếu tham số 'key'"}), 400
    if not hwid:
        return jsonify({"status": "error", "message": "Thiếu tham số 'hwid' hoặc 'device_id'"}), 400
    db = load_db()
    if key not in db or key.startswith("___"):
        return jsonify({"status": "invalid", "message": "Key không tồn tại trên hệ thống"})
    info = db[key]
    now = time.time()
    # Migrate list → dict nếu cần (chỉ trong memory, không save)
    devices = info.get('used_devices', {})
    if isinstance(devices, list):
        devices = {d: info.get('expiry_time', 0) for d in devices}
    # Kiểm tra trạng thái key tổng thể
    key_status = info.get('status', 'Chưa kích hoạt')
    if key_status == "Hết hạn":
        return jsonify({
            "status": "expired",
            "message": "Key đã bị đánh dấu hết hạn",
            "key_status": "Hết hạn"
        })
    if key_status == "Chưa kích hoạt":
        return jsonify({
            "status": "not_activated",
            "message": "Key chưa được kích hoạt. Dùng /api/verify để kích hoạt lần đầu.",
            "key_status": "Chưa kích hoạt"
        })
    # Key đang hoạt động → kiểm tra hwid cụ thể
    if hwid not in devices:
        return jsonify({
            "status": "device_not_found",
            "message": f"Device '{hwid}' chưa đăng ký trên key này. Dùng /api/verify để đăng ký.",
            "registered_count": len(devices),
            "max_devices": info.get('max_devices', 1)
        })
    dev_exp = devices[hwid]
    if dev_exp == -1:
        return jsonify({
            "status": "valid",
            "time_left": "∞",
            "expiry_timestamp": -1,
            "expiry_str": "Vĩnh Viễn",
            "is_permanent": True,
            "key_type": info.get('duration_unit', 'permanent')
        })
    if now > dev_exp:
        return jsonify({
            "status": "expired",
            "message": "Key đã hết hạn trên thiết bị này",
            "expiry_timestamp": dev_exp,
            "expiry_str": format_ts(dev_exp),
            "is_permanent": False,
            "expired_ago": get_time_left_str(now - dev_exp) + " trước"
        })
    return jsonify({
        "status": "valid",
        "time_left": get_time_left_str(dev_exp),
        "expiry_timestamp": dev_exp,
        "expiry_str": format_ts(dev_exp),
        "is_permanent": False,
        "key_type": f"{info.get('duration_val',0)} {info.get('duration_unit','?')}"
    })

@app.route('/api/check-device', methods=['GET', 'POST', 'OPTIONS'])
def api_check_device():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or {}
    device_id = (
        data.get('device_id', '') or data.get('deviceId', '') or
        request.form.get('device_id', '') or request.args.get('device_id', '')
    ).strip()
    key = (data.get('key', '') or request.form.get('key', '') or request.args.get('key', '')).strip()
    note = (data.get('note', '') or request.form.get('note', '') or request.args.get('note', '')).strip()
    caller_ip = get_real_ip()
    if not check_rate_limit(caller_ip, max_req=10, window=30):
        return jsonify({"status": "error", "message": "Quá nhiều yêu cầu. Thử lại sau!"}), 429
    if not device_id:
        return jsonify({"status": "error", "message": "Missing device_id"}), 400
    db = load_db()
    now = time.time()
    # --- Kiểm tra trong ___APPROVED_DEVICES___ ---
    approved = db.get("___APPROVED_DEVICES___", {})
    if device_id in approved:
        dinfo = approved[device_id]
        exp = dinfo.get('expiry', -1)
        if exp == 0: exp = -1
        if exp != -1 and now > exp:
            tg_notify(f"📱 <b>CHECK-DEVICE: HẾT HẠN</b>\n🔧 Device: <code>{device_id}</code>\n📍 IP: <code>{caller_ip}</code>\n⏰ {format_ts(now)}")
            return jsonify({"status": "expired", "message": "Device approval expired", "expiry_timestamp": exp, "expiry_str": format_ts(exp), "is_permanent": False, "time_left": "Hết hạn"})
        tg_notify(f"✅ <b>CHECK-DEVICE: HỢP LỆ</b>\n🔧 Device: <code>{device_id}</code>\n📍 IP: <code>{caller_ip}</code>\n⏰ Hết hạn: {format_ts(exp) if exp != -1 else 'Vĩnh viễn'}")
        return jsonify({
            "status": "approved",
            "expiry": exp,
            "expiry_timestamp": exp,
            "is_permanent": (exp == -1),
            "time_left": get_time_left_str(exp),
            "expiry_str": format_ts(exp) if exp != -1 else "Vĩnh Viễn"
        })
    # --- Kiểm tra device_id trong các key DB ---
    found_key = None
    found_exp = None
    if key and key in db and not key.startswith("___"):
        kinfo = db[key]
        if device_id in kinfo.get('used_devices', {}):
            found_key = key
            found_exp = kinfo['used_devices'][device_id]
    if not found_key:
        for k, v in db.items():
            if k.startswith("___") or not isinstance(v, dict): continue
            if device_id in v.get('used_devices', {}):
                found_key = k
                found_exp = v['used_devices'][device_id]
                break
    if found_key:
        if found_exp != -1 and now > found_exp:
            tg_notify(f"⚠️ <b>CHECK-DEVICE: KEY HẾT HẠN</b>\n🔧 Device: <code>{device_id}</code>\n🔑 Key: <code>{found_key}</code>\n📍 IP: <code>{caller_ip}</code>")
            return jsonify({"status": "expired", "message": "Key on this device has expired", "key": found_key, "expiry": found_exp, "expiry_timestamp": found_exp, "expiry_str": format_ts(found_exp), "is_permanent": False, "time_left": "Hết hạn"})
        tg_notify(f"✅ <b>CHECK-DEVICE: KEY HỢP LỆ</b>\n🔧 Device: <code>{device_id}</code>\n🔑 Key: <code>{found_key}</code>\n📍 IP: <code>{caller_ip}</code>\n⏳ Còn: {get_time_left_str(found_exp)}")
        return jsonify({"status": "approved", "key": found_key, "expiry": found_exp, "expiry_timestamp": found_exp, "is_permanent": (found_exp == -1), "time_left": get_time_left_str(found_exp), "expiry_str": format_ts(found_exp) if found_exp != -1 else "Vĩnh Viễn"})
    # --- Không tìm thấy ---
    tg_notify(f"❓ <b>CHECK-DEVICE: KHÔNG TÌM THẤY</b>\n🔧 Device: <code>{device_id}</code>\n📍 IP: <code>{caller_ip}</code>\n📝 Note: {note or '—'}")
    return jsonify({"status": "not_found", "message": "Device not found in system"})

@app.route('/check-ip-key')
def check_ip_key_page():
    return render_template_string(CHECK_IP_KEY_HTML)

@app.route('/api/get_key_ip_info', methods=['POST'])
def get_key_ip_info():
    k = request.form.get('key', '').strip()
    db = load_db()
    if not k or k not in db or k.startswith("___"):
        return jsonify({"exists": False, "msg": "Key không tồn tại trên hệ thống!"})
    info = db[k]
    now = time.time()
    devices = []
    for did, exp in info.get('used_devices', {}).items():
        devices.append({
            "device_id": did,
            "expiry": exp,
            "expiry_str": format_ts(exp) if (isinstance(exp, (int, float)) and exp != -1) else "Vĩnh viễn"
        })
    return jsonify({
        "exists": True,
        "key": k,
        "status": info.get('status', '—'),
        "client_ip": info.get('client_ip', ''),
        "creator_info": info.get('creator_info', 'Không có thông tin'),
        "activated_time": format_ts(info.get('activated_time')) if info.get('activated_time') else "Chưa kích hoạt",
        "created_at": format_ts(info.get('created_at', 0)),
        "devices": devices,
        "duration": f"{info['duration_val']} {info['duration_unit']}" if info.get('duration_unit') != 'permanent' else "Vĩnh viễn"
    })

@app.route('/api/check_free_key_status', methods=['POST'])
def check_free_key_status():
    k = request.form.get('key', '')
    db = load_db()
    if k in db:
        info = db[k]
        now = time.time()
        if info['status'] == 'Đã kích hoạt':
            _non_perm3 = [e for e in info['used_devices'].values() if e != -1]
            all_expired = len(_non_perm3) > 0 and all(now > e for e in _non_perm3)
            if all_expired:
                return jsonify({"valid": False})
        return jsonify({"valid": True})
    return jsonify({"valid": False})

@app.route('/nhan-key-free')
def nhan_key_free_page(): return render_template_string(FREE_KEY_HTML)

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

@app.route('/api/check_key', methods=['GET', 'POST'])
def api_check_key():
    """
    Alias của /api/verify — hỗ trợ GET và POST form-data.
    Dùng /api/verify (POST JSON) để nhận thêm thông tin expiry_timestamp.
    """
    data = request.get_json(silent=True) or {}
    k = (data.get('key', '') or request.values.get('key', '')).strip()
    device_id = (data.get('hwid', '') or data.get('device_id', '') or request.values.get('device_id', '') or request.values.get('hwid', '')).strip()
    if not k or not device_id:
        return jsonify({"status": "error", "message": "Thiếu key hoặc device_id/hwid"})
    db = load_db()
    if k not in db or k.startswith("___"):
        return jsonify({"status": "invalid", "message": "Key không tồn tại"})
    info = db[k]
    now = time.time()
    if isinstance(info.get('used_devices', []), list):
        new_devs = {}
        for d in info.get('used_devices', []): new_devs[d] = info.get('expiry_time', 0)
        info['used_devices'] = new_devs
    val, unit = info['duration_val'], info['duration_unit']
    sec = -1
    if unit == "phút": sec = val * 60
    elif unit == "tiếng": sec = val * 3600
    elif unit == "ngày": sec = val * 86400
    elif unit == "tháng": sec = val * 30 * 86400
    elif unit == "năm": sec = val * 365 * 86400
    is_permanent = (sec == -1)
    # Kiểm tra key đã hết hạn
    if info['status'] == "Hết hạn":
        return jsonify({"status": "expired", "message": "Key đã hết hạn"})
    is_first_activation = (info['status'] == "Chưa kích hoạt")
    if is_first_activation:
        info['status'] = "Đã kích hoạt"
        info['activated_time'] = now
    if device_id in info['used_devices']:
        dev_exp = info['used_devices'][device_id]
        if dev_exp != -1 and now > dev_exp:
            _non_perm = [e for e in info['used_devices'].values() if e != -1]
            is_full = len(info['used_devices']) >= info['max_devices']
            all_exp = len(_non_perm) > 0 and all(now > e for e in _non_perm)
            if is_full and all_exp:
                info['status'] = "Hết hạn"
            save_db(db)
            return jsonify({
                "status": "expired",
                "message": "Key đã hết hạn trên thiết bị này",
                "expiry_timestamp": dev_exp,
                "expiry_str": format_ts(dev_exp)
            })
        save_db(db)
        return jsonify({
            "status": "success",
            "message": "Key hợp lệ",
            "time_left": get_time_left_str(dev_exp),
            "expiry_timestamp": dev_exp,
            "expiry_str": format_ts(dev_exp) if dev_exp != -1 else "Vĩnh Viễn",
            "is_permanent": (dev_exp == -1),
            "is_new_device": False
        })
    else:
        if len(info['used_devices']) < info['max_devices']:
            dev_exp = -1 if is_permanent else (now + sec)
            info['used_devices'][device_id] = dev_exp
            save_db(db)
            return jsonify({
                "status": "success",
                "message": "Thiết bị đã được đăng ký",
                "time_left": get_time_left_str(dev_exp),
                "expiry_timestamp": dev_exp,
                "expiry_str": format_ts(dev_exp) if dev_exp != -1 else "Vĩnh Viễn",
                "is_permanent": is_permanent,
                "is_new_device": True
            })
        save_db(db)
        return jsonify({
            "status": "device_limit",
            "message": f"Đã đạt giới hạn thiết bị ({info['max_devices']})"
        })

@app.route('/api/submit_device_request', methods=['POST', 'OPTIONS'])
def submit_device_request():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or {}
    device_id = (data.get('device_id', '') or request.form.get('device_id', '')).strip()
    val = (data.get('val', '') or request.form.get('val', '1')).strip()
    unit = (data.get('unit', '') or request.form.get('unit', 'ngày')).strip()
    note = (data.get('note', '') or request.form.get('note', '')).strip()
    if not device_id:
        return jsonify({"status": "error", "msg": "Thiếu Device ID!"})
    db = load_db()
    requests_map = db.get("___DEVICE_REQUESTS___", {})
    for rid, rinfo in requests_map.items():
        if rinfo.get('device_id') == device_id and rinfo.get('status') == 'pending':
            return jsonify({"status": "exists", "msg": "Device ID này đang chờ duyệt rồi!"})
    approved = db.get("___APPROVED_DEVICES___", {})
    if device_id in approved:
        exp = approved[device_id].get('expiry', 0)
        if exp == -1 or time.time() < exp:
            return jsonify({"status": "already_approved", "msg": "Device ID này đã được duyệt và còn hạn!"})
    req_id = str(int(time.time() * 1000)) + "-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    requests_map[req_id] = {
        "device_id": device_id,
        "val": val,
        "unit": unit,
        "note": note,
        "status": "pending",
        "submitted_at": time.time(),
        "ip": get_real_ip()
    }
    db["___DEVICE_REQUESTS___"] = requests_map
    save_db(db)
    return jsonify({"status": "success", "req_id": req_id})

@app.route('/api/list_device_requests', methods=['GET', 'OPTIONS'])
def list_device_requests():
    if request.method == 'OPTIONS': return jsonify([]), 200
    if not session.get('is_admin'): return jsonify([]), 401
    db = load_db()
    requests_map = db.get("___DEVICE_REQUESTS___", {})
    result = []
    for rid, rinfo in requests_map.items():
        if rinfo.get('status') == 'pending':
            result.append({
                "req_id": rid,
                "device_id": rinfo.get('device_id', ''),
                "val": rinfo.get('val', '1'),
                "unit": rinfo.get('unit', 'ngày'),
                "note": rinfo.get('note', ''),
                "submitted_at_str": format_ts(rinfo.get('submitted_at', 0)),
                "submitted_at_ts": rinfo.get('submitted_at', 0),
                "ip": rinfo.get('ip', '—')
            })
    result.sort(key=lambda x: x['submitted_at_ts'], reverse=True)
    return jsonify(result)

@app.route('/api/approve_device_request', methods=['POST', 'OPTIONS'])
def approve_device_request():
    if request.method == 'OPTIONS': return jsonify({"status": "ok"}), 200
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    req_id = request.form.get('req_id', '').strip()
    val = request.form.get('val', '').strip()
    unit = request.form.get('unit', '').strip()
    db = load_db()
    requests_map = db.get("___DEVICE_REQUESTS___", {})
    if req_id not in requests_map:
        return jsonify({"status": "error", "msg": "Yêu cầu không tồn tại!"})
    rinfo = requests_map[req_id]
    device_id = rinfo['device_id']
    now = time.time()
    val_int = int(val) if val and val.isdigit() else int(rinfo.get('val', 1))
    u = unit if unit else rinfo.get('unit', 'ngày')
    sec = -1
    if u == "phút": sec = val_int * 60
    elif u == "tiếng": sec = val_int * 3600
    elif u == "ngày": sec = val_int * 86400
    elif u == "tháng": sec = val_int * 30 * 86400
    elif u == "năm": sec = val_int * 365 * 86400
    expiry = -1 if sec == -1 else (now + sec)
    approved = db.get("___APPROVED_DEVICES___", {})
    approved[device_id] = {
        "expiry": expiry, "approved_at": now,
        "val": val_int, "unit": u,
        "note": rinfo.get('note', ''), "ip": rinfo.get('ip', '')
    }
    db["___APPROVED_DEVICES___"] = approved
    requests_map[req_id]['status'] = 'approved'
    db["___DEVICE_REQUESTS___"] = requests_map
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/reject_device_request', methods=['POST'])
def reject_device_request():
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    req_id = request.form.get('req_id', '').strip()
    db = load_db()
    requests_map = db.get("___DEVICE_REQUESTS___", {})
    if req_id in requests_map:
        requests_map[req_id]['status'] = 'rejected'
        db["___DEVICE_REQUESTS___"] = requests_map
        save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/list_approved_devices', methods=['GET'])
def list_approved_devices():
    if not session.get('is_admin'): return jsonify([]), 401
    db = load_db()
    approved = db.get("___APPROVED_DEVICES___", {})
    now = time.time()
    result = []
    for did, dinfo in approved.items():
        exp = dinfo.get('expiry', 0)
        if exp == -1:
            time_left = "Vĩnh viễn"
            is_expired = False
        else:
            time_left = get_time_left_str(exp)
            is_expired = now > exp
        result.append({
            "device_id": did,
            "expiry": exp,
            "expiry_str": format_ts(exp) if (exp != -1) else "Vĩnh viễn",
            "time_left": time_left,
            "is_expired": is_expired,
            "approved_at": format_ts(dinfo.get('approved_at', 0)),
            "val": dinfo.get('val', ''),
            "unit": dinfo.get('unit', ''),
            "note": dinfo.get('note', ''),
            "ip": dinfo.get('ip', '—')
        })
    return jsonify(result)

@app.route('/api/delete_approved_device', methods=['POST'])
def delete_approved_device():
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    device_id = request.form.get('device_id', '').strip()
    db = load_db()
    approved = db.get("___APPROVED_DEVICES___", {})
    if device_id in approved:
        del approved[device_id]
        db["___APPROVED_DEVICES___"] = approved
        save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/extend_approved_device', methods=['POST'])
def extend_approved_device():
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    device_id = request.form.get('device_id', '').strip()
    val = request.form.get('val', '').strip()
    unit = request.form.get('unit', '').strip()
    db = load_db()
    approved = db.get("___APPROVED_DEVICES___", {})
    if device_id not in approved:
        return jsonify({"status": "error", "msg": "Device ID không tồn tại!"})
    dinfo = approved[device_id]
    now = time.time()
    val_int = int(val) if val and val.isdigit() else 1
    sec = 0
    if unit == "phút": sec = val_int * 60
    elif unit == "tiếng": sec = val_int * 3600
    elif unit == "ngày": sec = val_int * 86400
    elif unit == "tháng": sec = val_int * 30 * 86400
    elif unit == "năm": sec = val_int * 365 * 86400
    cur_exp = dinfo.get('expiry', now)
    if cur_exp == -1:
        new_exp = -1
    else:
        base = max(cur_exp, now)
        new_exp = base + sec
    dinfo['expiry'] = new_exp
    dinfo['val'] = val_int
    dinfo['unit'] = unit
    approved[device_id] = dinfo
    db["___APPROVED_DEVICES___"] = approved
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/check_device_approval', methods=['POST', 'GET', 'OPTIONS'])
def check_device_approval():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or {}
    device_id = (data.get('device_id', '') or request.form.get('device_id', '') or request.args.get('device_id', '')).strip()
    if not device_id:
        return jsonify({"status": "error", "msg": "Thiếu Device ID"})
    db = load_db()
    approved = db.get("___APPROVED_DEVICES___", {})
    if device_id not in approved:
        return jsonify({"status": "not_found", "msg": "Device ID chưa được duyệt"})
    dinfo = approved[device_id]
    exp = dinfo.get('expiry', 0)
    now = time.time()
    if exp != -1 and now > exp:
        return jsonify({
            "status": "expired",
            "msg": "Device ID đã hết hạn",
            "expiry_timestamp": exp,
            "expiry_str": format_ts(exp),
            "is_permanent": False,
            "time_left": "Hết hạn"
        })
    return jsonify({
        "status": "approved",
        "expiry": exp,
        "expiry_timestamp": exp,
        "is_permanent": (exp == -1),
        "time_left": get_time_left_str(exp),
        "expiry_str": format_ts(exp) if exp != -1 else "Vĩnh viễn"
    })

@app.route('/api/direct_activate_device', methods=['POST'])
def direct_activate_device():
    device_id = request.form.get('device_id', '').strip()
    expiry_date = request.form.get('expiry_date', '').strip()
    if not device_id:
        return jsonify({"status": "error", "msg": "Thiếu Device ID"})
    db = load_db()
    approved = db.get("___APPROVED_DEVICES___", {})
    now = time.time()
    expiry = -1
    if expiry_date:
        try:
            dt = datetime.strptime(expiry_date, '%Y-%m-%d')
            expiry = dt.replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            expiry = -1
    approved[device_id] = {
        "expiry": expiry,
        "approved_at": now,
        "val": 0,
        "unit": "permanent" if expiry == -1 else "ngày",
        "note": "Kích hoạt trực tiếp bởi Admin",
        "ip": get_real_ip()
    }
    db["___APPROVED_DEVICES___"] = approved
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/dang-ky-thiet-bi')
def device_registration_page():
    return render_template_string(DEVICE_REG_HTML)

@app.route('/api/add_device_id', methods=['POST'])
def add_device_id():
    device_id = request.form.get('device_id', '').strip()
    val = request.form.get('val', '1').strip()
    unit = request.form.get('unit', 'ngày').strip()
    if not device_id:
        return jsonify({"status": "error", "msg": "Vui lòng nhập Device ID!"})
    db = load_db()
    approved = db.get("___APPROVED_DEVICES___", {})
    now = time.time()
    val_int = int(val) if val and val.isdigit() else 1
    sec = -1
    if unit == "phút": sec = val_int * 60
    elif unit == "tiếng": sec = val_int * 3600
    elif unit == "ngày": sec = val_int * 86400
    elif unit == "tháng": sec = val_int * 30 * 86400
    elif unit == "năm": sec = val_int * 365 * 86400
    expiry = -1 if sec == -1 else (now + sec)
    approved[device_id] = {
        "expiry": expiry,
        "approved_at": now,
        "val": val_int,
        "unit": unit,
        "note": "Thêm ID trực tiếp từ trang đăng ký",
        "ip": get_real_ip()
    }
    db["___APPROVED_DEVICES___"] = approved
    save_db(db)
    return jsonify({"status": "success"})

# ============================================================
#  NEW: LINK4M + FREE KEY BYPASS SYSTEM + ANTI-DDOS + STATS
# ============================================================

LINK4M_API_KEY = '69cb3ea598c5fa4c2c4c414d'

# Anti-DDoS rate limiter (hidden, in-memory, transparent to users)
_RATE_LIMITER = {}
_RATE_LOCK = threading.Lock()

def check_rate_limit(ip, max_req=20, window=60):
    now = time.time()
    with _RATE_LOCK:
        times = _RATE_LIMITER.get(ip, [])
        times = [t for t in times if now - t < window]
        if len(times) >= max_req:
            _RATE_LIMITER[ip] = times
            return False
        times.append(now)
        _RATE_LIMITER[ip] = times
        return True

def shorten_with_link4m(long_url):
    """
    Gọi link4m API để tạo link rút gọn thật.
    Trả về (short_url, error_msg).
    Nếu thành công: (url, None). Nếu lỗi: ('', reason).
    """
    try:
        # Thử cả 2 format: url encode và không encode
        for encoded_url in [urllib.parse.quote(long_url, safe=''), long_url]:
            api_url = f"https://link4m.co/api-shorten/v2?api={LINK4M_API_KEY}&url={encoded_url}"
            try:
                req = _ureq.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                resp = _ureq.urlopen(req, timeout=15)
                raw = resp.read().decode('utf-8', errors='replace')
                data = json.loads(raw)
                if data.get('status') == 'success':
                    su = data.get('shortenedUrl', '') or data.get('shorten_url', '')
                    if su and su.startswith('http'):
                        return su, None
                # API trả lỗi rõ ràng
                err_msg = data.get('message') or data.get('error') or str(data)
                return '', f"Link4m API lỗi: {err_msg}"
            except Exception:
                continue
        return '', "Không kết nối được Link4m API sau 2 lần thử"
    except Exception as e:
        return '', f"Lỗi hệ thống khi gọi Link4m: {str(e)}"

def check_vpn_or_proxy(ip):
    try:
        url = f"http://ip-api.com/json/{ip}?fields=status,proxy,hosting"
        resp = _ureq.urlopen(url, timeout=5)
        data = json.loads(resp.read().decode())
        if data.get('status') == 'success':
            return bool(data.get('proxy') or data.get('hosting'))
    except Exception:
        pass
    return False

@app.route('/api/getkey', methods=['GET', 'POST', 'OPTIONS'])
def api_getkey():
    """Public API endpoint for external tools/Telegram bots — auto creates link4m shortened link."""
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    ip = get_real_ip()
    if not check_rate_limit(ip, max_req=5, window=30):
        return jsonify({"status": "error", "message": "Quá nhiều yêu cầu. Thử lại sau 30 giây!"}), 429
    db = load_db()
    now = time.time()
    ip_free_history = db.get("___FREE_IP_HISTORY___", {})
    ip_records = [t for t in ip_free_history.get(ip, []) if now - t < 86400]
    if len(ip_records) >= 3:
        return jsonify({"status": "error", "message": f"IP {ip} đã lấy đủ 3 key hôm nay. Thử lại sau 24 giờ!"}), 429
    # Tạo token trước
    token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=20))
    host = os.environ.get('RENDER_EXTERNAL_URL', request.host_url.rstrip('/'))
    dest_url = f"{host}/nhan-key-free?token={token}"
    # Bắt buộc phải có link4m thật — KHÔNG fallback sang URL trực tiếp
    short_url, err = shorten_with_link4m(dest_url)
    if not short_url:
        return jsonify({"status": "error", "message": f"Không tạo được link Link4m. {err}"}), 503
    # Chỉ lưu token vào DB sau khi link4m thành công
    tokens = db.get("___GETKEY_TOKENS___", {})
    tokens = {k: v for k, v in tokens.items() if now - v.get('created_at', 0) < 3600}
    tokens[token] = {"ip": ip, "created_at": now, "status": "pending", "is_admin": False}
    db["___GETKEY_TOKENS___"] = tokens
    stats = db.get("___FREE_KEY_STATS___", {"total_bypasses": 0})
    stats["total_bypasses"] = stats.get("total_bypasses", 0) + 1
    db["___FREE_KEY_STATS___"] = stats
    save_db(db)
    tg_notify(f"🔗 <b>LINK4M MỚI (API/getkey)</b>\n📍 IP: <code>{ip}</code>\n🔑 Token: <code>{token[:8]}...</code>\n🌐 Link: {short_url}")
    return jsonify({"status": "success", "link": short_url, "token": token})

@app.route('/admin/gen_key_link', methods=['POST'])
def admin_gen_key_link():
    """Admin endpoint — generate link4m link for free key panel."""
    if not session.get('is_admin'):
        return jsonify({"status": "error"}), 401
    ip = get_real_ip()
    db = load_db()
    now = time.time()
    # Tạo token trước, chưa lưu DB
    token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=20))
    host = os.environ.get('RENDER_EXTERNAL_URL', request.host_url.rstrip('/'))
    dest_url = f"{host}/nhan-key-free?token={token}"
    # Bắt buộc phải có link4m thật — KHÔNG fallback sang URL trực tiếp
    short_url, err = shorten_with_link4m(dest_url)
    if not short_url:
        return jsonify({"status": "error", "message": f"Không tạo được link Link4m. {err}"}), 503
    # Chỉ lưu token vào DB sau khi link4m thành công
    tokens = db.get("___GETKEY_TOKENS___", {})
    tokens = {k: v for k, v in tokens.items() if now - v.get('created_at', 0) < 3600}
    tokens[token] = {"ip": ip, "created_at": now, "status": "pending", "is_admin": True}
    db["___GETKEY_TOKENS___"] = tokens
    stats = db.get("___FREE_KEY_STATS___", {"total_bypasses": 0})
    stats["total_bypasses"] = stats.get("total_bypasses", 0) + 1
    db["___FREE_KEY_STATS___"] = stats
    save_db(db)
    tg_notify(f"🔗 <b>LINK4M MỚI (Admin Panel)</b>\n📍 Admin IP: <code>{ip}</code>\n🔑 Token: <code>{token[:8]}...</code>\n🌐 Link: {short_url}")
    return jsonify({"status": "success", "link": short_url, "token": token})

@app.route('/api/confirm_bypass', methods=['POST'])
def confirm_bypass():
    """Called when user arrives at /nhan-key-free?token=XXX after bypassing link4m."""
    token = request.form.get('token', '').strip()
    client_ip_info = request.form.get('ip_info', '').strip()
    server_ip = get_real_ip()
    if not check_rate_limit(server_ip, max_req=8, window=60):
        return jsonify({"status": "error", "message": "Quá nhiều yêu cầu. Thử lại sau 1 phút!"})
    if not token:
        return jsonify({"status": "error", "message": "Token không hợp lệ! Bạn cần vượt link rút gọn trước."})
    db = load_db()
    now = time.time()
    tokens = db.get("___GETKEY_TOKENS___", {})
    if token not in tokens:
        return jsonify({"status": "error", "message": "Link đã hết hạn hoặc không hợp lệ! Vui lòng lấy link mới từ Admin."})
    token_info = tokens[token]
    if now - token_info.get('created_at', 0) > 3600:
        return jsonify({"status": "error", "message": "Link đã hết hạn (quá 1 giờ)! Vui lòng lấy link mới từ Admin."})
    if token_info.get('status') == 'used':
        existing_key = token_info.get('key', '')
        if existing_key and existing_key in db:
            return jsonify({"status": "success", "key": existing_key, "reused": True, "msg": "Bạn đã nhận key này rồi!"})
        return jsonify({"status": "error", "message": "Link này đã được sử dụng! Vui lòng lấy link mới."})
    is_admin_token = token_info.get('is_admin', False)
    if not is_admin_token:
        # CHECK 3: Bypass detection — token phải được tạo ít nhất 20 giây trước
        elapsed = now - token_info.get('created_at', now)
        if elapsed < 20:
            tg_notify(f"🚨 <b>BYPASS PHÁT HIỆN!</b>\n📍 IP: <code>{server_ip}</code>\n⏱ Elapsed: {elapsed:.1f}s (cần ≥20s)\n🔑 Token: <code>{token[:8]}...</code>\n📊 {client_ip_info[:80] if client_ip_info else '—'}")
            return jsonify({"status": "error", "message": "⚠️ Phát hiện hành vi bypass link! Bạn phải thực sự vượt link rút gọn. Vui lòng lấy link mới và thực hiện đúng!"})
        ip_free_history = db.get("___FREE_IP_HISTORY___", {})
        ip_records = [t for t in ip_free_history.get(server_ip, []) if now - t < 86400]
        if len(ip_records) >= 3:
            return jsonify({"status": "error", "message": "IP này đã đạt giới hạn 3 key/ngày. Thử lại sau 24 giờ!"})
        is_vpn = check_vpn_or_proxy(server_ip)
        if is_vpn:
            return jsonify({"status": "error", "message": "Phát hiện VPN hoặc Proxy! Vui lòng tắt VPN và thử lại để nhận key."})
    cfg = db.get("___FREE_CONFIG___", {"val": 12, "unit": "tiếng", "dev": 9999})
    key_name = f"FREE-{''.join(random.choices(string.ascii_uppercase + string.digits, k=12))}"
    final_info = f"SV IP: {server_ip} | Token: {token[:8]}... | {client_ip_info}"
    db[key_name] = {
        "duration_val": int(cfg.get('val', 12)),
        "duration_unit": cfg.get('unit', 'tiếng'),
        "max_devices": int(cfg.get('dev', 9999)),
        "status": "Chưa kích hoạt",
        "activated_time": None,
        "created_at": now,
        "used_devices": {},
        "creator_info": final_info,
        "client_ip": server_ip
    }
    tokens[token]['status'] = 'used'
    tokens[token]['key'] = key_name
    db["___GETKEY_TOKENS___"] = tokens
    if not is_admin_token:
        ip_free_history = db.get("___FREE_IP_HISTORY___", {})
        ip_records = [t for t in ip_free_history.get(server_ip, []) if now - t < 86400]
        ip_records.append(now)
        ip_free_history[server_ip] = ip_records
        db["___FREE_IP_HISTORY___"] = ip_free_history
    ip_map = db.get("___IP_KEY_MAP___", {})
    ip_map[server_ip] = key_name
    db["___IP_KEY_MAP___"] = ip_map
    save_db(db)
    tg_notify(f"🎉 <b>KEY FREE MỚI CẤP!</b>\n🔑 Key: <code>{key_name}</code>\n📍 IP: <code>{server_ip}</code>\n⏰ {cfg.get('val',12)} {cfg.get('unit','tiếng')} | {cfg.get('dev',1)} thiết bị\n📊 {client_ip_info[:100] if client_ip_info else '—'}")
    return jsonify({"status": "success", "key": key_name, "reused": False})

@app.route('/api/key_stats', methods=['GET'])
def api_key_stats():
    """Returns key statistics for the admin panel stats tab."""
    if not session.get('is_admin'):
        return jsonify({"status": "error"}), 401
    db = load_db()
    now = time.time()
    total = 0
    activated = 0
    expired = 0
    not_activated = 0
    free_total = 0
    for k, v in db.items():
        if k.startswith("___"):
            continue
        if not isinstance(v, dict):
            continue
        total += 1
        if k.startswith("FREE-"):
            free_total += 1
        st = v.get('status', '')
        if st == "Đã kích hoạt":
            _non_perm = [e for e in v.get('used_devices', {}).values() if e != -1]
            is_full = len(v.get('used_devices', {})) >= v.get('max_devices', 1)
            all_exp = len(_non_perm) > 0 and all(now > e for e in _non_perm)
            if is_full and all_exp:
                expired += 1
            else:
                activated += 1
        elif st == "Hết hạn":
            expired += 1
        else:
            not_activated += 1
    stats = db.get("___FREE_KEY_STATS___", {"total_bypasses": 0})
    return jsonify({
        "total": total,
        "activated": activated,
        "expired": expired,
        "not_activated": not_activated,
        "free_total": free_total,
        "total_bypasses": stats.get("total_bypasses", 0)
    })

# ============================================================
#  HTML TEMPLATES
# ============================================================

# ============================================================
# TELEGRAM BOT — Long polling daemon thread + notifications
# ============================================================
TELEGRAM_BOT_TOKEN = '8605090305:AAGMxGBN8dHw3Txi4F8K0Z4WsuBD2ETPBFs'
TELEGRAM_ADMIN_ID = 8401914033
_TG_OFFSET = [0]

def tg_send(chat_id, text, parse_mode='HTML'):
    if not _TG_OK or _req_tg is None:
        return
    try:
        _req_tg.post(
            f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage',
            json={'chat_id': chat_id, 'text': text[:4000], 'parse_mode': parse_mode, 'disable_web_page_preview': True},
            timeout=10
        )
    except Exception:
        pass

def tg_notify(text):
    tg_send(TELEGRAM_ADMIN_ID, text)

def _tg_handle_cmd(chat_id, text):
    if chat_id != TELEGRAM_ADMIN_ID:
        tg_send(chat_id, '⛔ Bạn không có quyền sử dụng bot này.\nLiên hệ @vkhanh3010 để được hỗ trợ.')
        return
    parts = text.strip().split()
    cmd = parts[0].lower().split('@')[0] if parts else ''
    args = parts[1:]

    if cmd in ('/start', '/menu', '/help'):
        tg_send(chat_id, """🤖 <b>BOT QUẢN LÝ KEY SERVER — VĂN KHÁNH</b>

📊 <b>Thống kê:</b>
/stats — Thống kê tổng quan keys
/link4mstats — Số link4m &amp; key đã lấy
/status — Trạng thái server &amp; DB

🔑 <b>Quản lý Keys VIP:</b>
/keys — 10 VIP keys mới nhất
/newkey [time] [unit] [devices] — Tạo key VIP
  Ví dụ: /newkey 7 ngày 1
/delkey [KEY] — Xóa key
/resetkey [KEY] — Reset key về chưa kích hoạt

🎁 <b>Key Free:</b>
/freekeys — 10 Free keys mới nhất
/genlink — Tạo link Link4m mới (Admin bypass)

📱 <b>Quản lý Device ID:</b>
/approvedev [id] [val] [unit] — Duyệt thiết bị
  Ví dụ: /approvedev ABC123 7 ngày
  Vĩnh viễn: /approvedev ABC123 1 permanent
/revokedev [id] — Thu hồi thiết bị đã duyệt
/listdev — Xem danh sách thiết bị đã duyệt
/pendingdev — Xem yêu cầu duyệt đang chờ

🛡️ <b>Bảo mật &amp; DDoS:</b>
/iplog — Nhật ký IP lấy key free
/ddos — Kiểm tra IPs rate-limit bất thường
/resetip [IP] — Reset giới hạn IP

<i>✅ Bot tự thông báo: link4m mới, key cấp, check-device, bypass phát hiện.</i>""")

    elif cmd == '/stats':
        try:
            db = load_db()
            now = time.time()
            total = activated = expired = not_act = free_total = 0
            for k, v in db.items():
                if k.startswith('___') or not isinstance(v, dict): continue
                total += 1
                if k.startswith('FREE-'): free_total += 1
                st = v.get('status', '')
                if st == 'Đã kích hoạt': activated += 1
                elif st == 'Hết hạn': expired += 1
                else: not_act += 1
            stats = db.get('___FREE_KEY_STATS___', {'total_bypasses': 0})
            tokens = db.get('___GETKEY_TOKENS___', {})
            used_tokens = sum(1 for v in tokens.values() if v.get('status') == 'used')
            tg_send(chat_id, f"""📊 <b>THỐNG KÊ HỆ THỐNG KEY</b>

🗄 Tổng keys: <b>{total}</b>
✅ Đã kích hoạt: <b>{activated}</b>
❌ Hết hạn: <b>{expired}</b>
⏳ Chưa kích hoạt: <b>{not_act}</b>
🎁 Keys Free: <b>{free_total}</b>
🔗 Lượt tạo link4m: <b>{stats.get('total_bypasses', 0)}</b>
🔑 Keys đã cấp qua link4m: <b>{used_tokens}</b>""")
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/link4mstats':
        try:
            db = load_db()
            stats = db.get('___FREE_KEY_STATS___', {'total_bypasses': 0})
            tokens = db.get('___GETKEY_TOKENS___', {})
            used = sum(1 for v in tokens.values() if v.get('status') == 'used')
            pending = sum(1 for v in tokens.values() if v.get('status') == 'pending')
            total_bp = stats.get('total_bypasses', 0)
            tg_send(chat_id, f"""🔗 <b>LINK4M STATISTICS</b>

📨 Tổng lượt tạo link: <b>{total_bp}</b>
✅ Đã lấy key thành công: <b>{used}</b>
⏳ Đang chờ (pending): <b>{pending}</b>
❌ Không vượt (bỏ): <b>{max(0, total_bp - used - pending)}</b>""")
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/status':
        try:
            db_size = os.path.getsize(DB_FILE) / 1024 if os.path.exists(DB_FILE) else 0
            host = os.environ.get('RENDER_EXTERNAL_URL', 'localhost')
            with _RATE_LOCK:
                rl_count = len(_RATE_LIMITER)
            now_vn = datetime.now(VN_TZ).strftime('%d/%m/%Y %H:%M:%S')
            tg_send(chat_id, f"""🟢 <b>SERVER STATUS</b>

🌐 Host: <code>{host}</code>
📦 DB Size: <b>{db_size:.1f} KB</b>
🛡 IPs rate-limit đang theo dõi: <b>{rl_count}</b>
⏰ Thời gian VN: <b>{now_vn}</b>""")
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/keys':
        try:
            db = load_db()
            vip_keys = [(k, v) for k, v in db.items() if not k.startswith('___') and isinstance(v, dict) and not k.startswith('FREE-')]
            vip_keys.sort(key=lambda x: x[1].get('created_at', 0), reverse=True)
            if not vip_keys:
                tg_send(chat_id, '📭 Chưa có VIP key nào.')
                return
            lines = ['🔑 <b>10 VIP KEYS MỚI NHẤT:</b>\n']
            for k, v in vip_keys[:10]:
                st = v.get('status', '?')
                icon = '✅' if st == 'Đã kích hoạt' else ('❌' if st == 'Hết hạn' else '⏳')
                lines.append(f'{icon} <code>{k}</code>\n   ⏰ {v.get("duration_val",0)} {v.get("duration_unit","?")} | 📱 {v.get("max_devices",1)} TB')
            tg_send(chat_id, '\n'.join(lines))
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/freekeys':
        try:
            db = load_db()
            free_keys = [(k, v) for k, v in db.items() if not k.startswith('___') and isinstance(v, dict) and k.startswith('FREE-')]
            free_keys.sort(key=lambda x: x[1].get('created_at', 0), reverse=True)
            if not free_keys:
                tg_send(chat_id, '📭 Chưa có Free key nào.')
                return
            lines = ['🎁 <b>10 FREE KEYS MỚI NHẤT:</b>\n']
            for k, v in free_keys[:10]:
                st = v.get('status', '?')
                icon = '✅' if st == 'Đã kích hoạt' else ('❌' if st == 'Hết hạn' else '⏳')
                ip = v.get('client_ip', '?')
                ct = format_ts(v.get('created_at', 0))
                lines.append(f'{icon} <code>{k}</code>\n   📍 IP: <code>{ip}</code> | {ct}')
            tg_send(chat_id, '\n'.join(lines))
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/newkey':
        try:
            if len(args) < 2:
                tg_send(chat_id, '❌ Cú pháp: /newkey [thời_gian] [đơn_vị] [thiết_bị]\nVí dụ: /newkey 7 ngày 1\nĐơn vị: phút, tiếng, ngày, tháng, năm')
                return
            time_val = args[0]
            time_unit = args[1]
            max_dev = int(args[2]) if len(args) > 2 else 1
            if time_unit not in ('phút', 'tiếng', 'ngày', 'tháng', 'năm', 'permanent'):
                tg_send(chat_id, '❌ Đơn vị không hợp lệ! Dùng: phút, tiếng, ngày, tháng, năm')
                return
            db = load_db()
            p1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
            p2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
            pfx = {'ngày': f'{time_val}D', 'tiếng': f'{time_val}H', 'phút': f'{time_val}P', 'tháng': f'{time_val}M', 'năm': f'{time_val}Y', 'permanent': 'VIP'}
            key_name = f"{pfx.get(time_unit, 'KEY')}-{p1}-{p2}"
            db[key_name] = {
                'duration_val': int(time_val) if time_unit != 'permanent' else 0,
                'duration_unit': time_unit, 'max_devices': max_dev, 'status': 'Chưa kích hoạt',
                'activated_time': None, 'created_at': time.time(), 'used_devices': {},
                'creator_info': 'Tạo bởi Admin Bot Telegram'
            }
            save_db(db)
            tg_send(chat_id, f'✅ <b>Tạo key thành công!</b>\n\n🔑 Key: <code>{key_name}</code>\n⏰ Hạn: {time_val} {time_unit}\n📱 Thiết bị: {max_dev}')
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi tạo key: {e}\n\nCú pháp: /newkey [thời_gian] [đơn_vị] [thiết_bị]')

    elif cmd == '/delkey':
        if not args:
            tg_send(chat_id, '❌ Cú pháp: /delkey [KEY]')
            return
        key = args[0]
        try:
            db = load_db()
            if key in db and not key.startswith('___'):
                del db[key]
                save_db(db)
                tg_send(chat_id, f'✅ Đã xóa key: <code>{key}</code>')
            else:
                tg_send(chat_id, f'❌ Key không tồn tại: <code>{key}</code>')
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/resetkey':
        if not args:
            tg_send(chat_id, '❌ Cú pháp: /resetkey [KEY]')
            return
        key = args[0]
        try:
            db = load_db()
            if key in db and not key.startswith('___'):
                db[key]['status'] = 'Chưa kích hoạt'
                db[key]['activated_time'] = None
                db[key]['used_devices'] = {}
                save_db(db)
                tg_send(chat_id, f'✅ Đã reset key: <code>{key}</code>')
            else:
                tg_send(chat_id, f'❌ Key không tồn tại: <code>{key}</code>')
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/genlink':
        try:
            now = time.time()
            token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=20))
            host = os.environ.get('RENDER_EXTERNAL_URL', 'https://localhost')
            dest_url = f"{host}/nhan-key-free?token={token}"
            short_url, err = shorten_with_link4m(dest_url)
            if not short_url:
                tg_send(chat_id, f'❌ Không tạo được link Link4m: {err}')
                return
            db = load_db()
            tokens = db.get('___GETKEY_TOKENS___', {})
            tokens = {k: v for k, v in tokens.items() if now - v.get('created_at', 0) < 3600}
            tokens[token] = {'ip': 'ADMIN_BOT', 'created_at': now - 60, 'status': 'pending', 'is_admin': True}
            db['___GETKEY_TOKENS___'] = tokens
            stats = db.get('___FREE_KEY_STATS___', {'total_bypasses': 0})
            stats['total_bypasses'] = stats.get('total_bypasses', 0) + 1
            db['___FREE_KEY_STATS___'] = stats
            save_db(db)
            tg_send(chat_id, f'🔗 <b>Link Link4m mới (Admin bypass):</b>\n\n<code>{short_url}</code>\n\n⏰ Hết hạn sau 1 giờ\n✅ Admin bypass — không cần VPN check, không cần timing')
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi tạo link: {e}')

    elif cmd == '/iplog':
        try:
            db = load_db()
            ip_history = db.get('___FREE_IP_HISTORY___', {})
            now = time.time()
            if not ip_history:
                tg_send(chat_id, '📭 Chưa có nhật ký IP nào.')
                return
            lines = ['📋 <b>NHẬT KÝ IP LẤY KEY FREE (24h):</b>\n']
            recent = [(ip, times) for ip, times in ip_history.items() if any(now - t < 86400 for t in times)]
            recent.sort(key=lambda x: max(x[1]), reverse=True)
            for ip_addr, times in recent[:20]:
                count = len([t for t in times if now - t < 86400])
                last = format_ts(max(times))
                lines.append(f'📍 <code>{ip_addr}</code> — {count} key | {last}')
            tg_send(chat_id, '\n'.join(lines) if len(lines) > 1 else '📭 Không có dữ liệu trong 24h.')
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/ddos':
        try:
            with _RATE_LOCK:
                rl_copy = dict(_RATE_LIMITER)
            now = time.time()
            high = [(ip_addr, len([t for t in times if now - t < 60])) for ip_addr, times in rl_copy.items()]
            high = [(ip_addr, cnt) for ip_addr, cnt in high if cnt >= 3]
            high.sort(key=lambda x: x[1], reverse=True)
            if not high:
                tg_send(chat_id, '✅ Không phát hiện hoạt động DDoS/Rate limit bất thường.')
                return
            lines = [f'⚠️ <b>RATE LIMIT ALERT ({len(high)} IPs):</b>\n']
            for ip_addr, cnt in high[:15]:
                lines.append(f'🔴 <code>{ip_addr}</code> — {cnt} req/60s')
            tg_send(chat_id, '\n'.join(lines))
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/resetip':
        if not args:
            tg_send(chat_id, '❌ Cú pháp: /resetip [IP]\nVí dụ: /resetip 1.2.3.4')
            return
        target_ip = args[0]
        try:
            db = load_db()
            changed = []
            ip_history = db.get('___FREE_IP_HISTORY___', {})
            if target_ip in ip_history:
                del ip_history[target_ip]
                db['___FREE_IP_HISTORY___'] = ip_history
                changed.append('Nhật ký IP')
            ip_map = db.get('___IP_KEY_MAP___', {})
            if target_ip in ip_map:
                del ip_map[target_ip]
                db['___IP_KEY_MAP___'] = ip_map
                changed.append('IP-Key map')
            save_db(db)
            msg = f'✅ Đã reset giới hạn cho IP: <code>{target_ip}</code>'
            if changed: msg += f'\nĐã xóa: {", ".join(changed)}'
            tg_send(chat_id, msg)
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/approvedev':
        # /approvedev [device_id] [val] [unit]
        if len(args) < 3:
            tg_send(chat_id, (
                '❌ Cú pháp: /approvedev [device_id] [val] [unit]\n'
                'Đơn vị: phút | tiếng | ngày | tháng | năm | permanent\n'
                'Ví dụ: /approvedev ABCD1234 7 ngày\n'
                'Hoặc vĩnh viễn: /approvedev ABCD1234 1 permanent'
            ))
            return
        did = args[0]
        val_str = args[1]
        unit_arg = args[2].lower()
        try:
            val_int = int(val_str)
        except Exception:
            tg_send(chat_id, '❌ Giá trị thời gian phải là số nguyên dương.')
            return
        db = load_db()
        approved = db.get("___APPROVED_DEVICES___", {})
        now_ts = time.time()
        if unit_arg == 'permanent':
            exp_ts = -1
        elif unit_arg == 'phút':
            exp_ts = now_ts + val_int * 60
        elif unit_arg == 'tiếng':
            exp_ts = now_ts + val_int * 3600
        elif unit_arg == 'ngày':
            exp_ts = now_ts + val_int * 86400
        elif unit_arg == 'tháng':
            exp_ts = now_ts + val_int * 30 * 86400
        elif unit_arg == 'năm':
            exp_ts = now_ts + val_int * 365 * 86400
        else:
            tg_send(chat_id, '❌ Đơn vị không hợp lệ. Dùng: phút | tiếng | ngày | tháng | năm | permanent')
            return
        approved[did] = {
            "expiry": exp_ts,
            "approved_at": now_ts,
            "val": val_int,
            "unit": unit_arg,
            "note": "Duyệt bởi Telegram Bot Admin",
            "ip": "telegram"
        }
        db["___APPROVED_DEVICES___"] = approved
        save_db(db)
        exp_display = 'Vĩnh viễn' if exp_ts == -1 else format_ts(exp_ts)
        tg_send(chat_id, (
            f'✅ <b>ĐÃ DUYỆT DEVICE ID</b>\n'
            f'🔧 Device: <code>{did}</code>\n'
            f'⏳ Thời gian: {val_int} {unit_arg}\n'
            f'⏰ Hết hạn: {exp_display}'
        ))

    elif cmd == '/revokedev':
        # /revokedev [device_id]
        if not args:
            tg_send(chat_id, '❌ Cú pháp: /revokedev [device_id]\nVí dụ: /revokedev ABCD1234')
            return
        did = args[0]
        db = load_db()
        approved = db.get("___APPROVED_DEVICES___", {})
        if did in approved:
            del approved[did]
            db["___APPROVED_DEVICES___"] = approved
            save_db(db)
            tg_send(chat_id, f'✅ <b>ĐÃ THU HỒI DEVICE ID</b>\n🔧 Device: <code>{did}</code>\nThiết bị này sẽ không còn được duyệt nữa.')
        else:
            tg_send(chat_id, f'⚠️ Device ID <code>{did}</code> không tồn tại trong danh sách duyệt.')

    elif cmd == '/listdev':
        # /listdev — liệt kê tất cả device đã được duyệt
        db = load_db()
        approved = db.get("___APPROVED_DEVICES___", {})
        now_ts = time.time()
        if not approved:
            tg_send(chat_id, '📋 <b>DANH SÁCH DEVICE ĐÃ DUYỆT</b>\n\n<i>Chưa có thiết bị nào được duyệt.</i>')
            return
        lines = ['📋 <b>DANH SÁCH DEVICE ĐÃ DUYỆT</b>\n']
        count = 0
        for did, dinfo in approved.items():
            exp = dinfo.get('expiry', -1)
            if exp == 0: exp = -1
            is_perm = (exp == -1)
            if not is_perm and exp < now_ts:
                status_icon = '❌'
                time_str = 'Hết hạn'
            else:
                status_icon = '✅'
                time_str = 'Vĩnh viễn' if is_perm else get_time_left_str(exp)
            short_id = did[:16] + '...' if len(did) > 16 else did
            lines.append(f'{status_icon} <code>{short_id}</code>\n   ⏳ {time_str}')
            count += 1
            if count >= 30:
                lines.append(f'\n<i>... và {len(approved) - 30} thiết bị khác</i>')
                break
        lines.append(f'\n<b>Tổng: {len(approved)} thiết bị</b>')
        tg_send(chat_id, '\n'.join(lines))

    elif cmd == '/pendingdev':
        # /pendingdev — liệt kê các yêu cầu duyệt device đang chờ
        db = load_db()
        pending = db.get("___PENDING_DEVICE_REQUESTS___", {})
        if not pending:
            tg_send(chat_id, '📥 <b>YÊU CẦU DUYỆT DEVICE</b>\n\n<i>Không có yêu cầu nào đang chờ duyệt.</i>')
            return
        lines = [f'📥 <b>YÊU CẦU DUYỆT DEVICE ({len(pending)} yêu cầu)</b>\n']
        count = 0
        for req_id, rinfo in pending.items():
            did = rinfo.get('device_id', '—')
            short_id = did[:16] + '...' if len(did) > 16 else did
            val = rinfo.get('val', 7)
            unit = rinfo.get('unit', 'ngày')
            ip = rinfo.get('ip', '—')
            note = rinfo.get('note', '')
            submitted = rinfo.get('submitted_at_str', '—')
            lines.append(
                f'🔧 <code>{short_id}</code>\n'
                f'   📅 {submitted} | ⏳ {val} {unit} | 🌐 {ip}'
                + (f'\n   📝 {note}' if note else '')
                + f'\n   /approvedev {did} {val} {unit}'
            )
            count += 1
            if count >= 10:
                lines.append(f'\n<i>... và {len(pending) - 10} yêu cầu khác</i>')
                break
        tg_send(chat_id, '\n'.join(lines))

    else:
        if text.startswith('/'):
            tg_send(chat_id, f'❓ Lệnh không hợp lệ: <code>{cmd}</code>\nGõ /start để xem menu đầy đủ.')

def _tg_poll_worker():
    import time as _tt
    _tt.sleep(10)
    while True:
        try:
            if not _TG_OK or _req_tg is None:
                _tt.sleep(30)
                continue
            resp = _req_tg.get(
                f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates',
                params={'offset': _TG_OFFSET[0], 'timeout': 25, 'allowed_updates': ['message']},
                timeout=32
            )
            data = resp.json()
            if data.get('ok'):
                for upd in data.get('result', []):
                    _TG_OFFSET[0] = upd['update_id'] + 1
                    try:
                        msg = upd.get('message', {})
                        if msg:
                            cid = msg.get('chat', {}).get('id', 0)
                            txt = msg.get('text', '').strip()
                            if txt:
                                _tg_handle_cmd(cid, txt)
                    except Exception:
                        pass
        except Exception:
            _tt.sleep(5)

_tg_thread = threading.Thread(target=_tg_poll_worker, daemon=True)
_tg_thread.start()


# ============================================================
# WEB LOG — in-memory access log
# ============================================================
_WEB_LOG = []
_WEB_LOG_LOCK = threading.Lock()

def web_log_add(entry):
    with _WEB_LOG_LOCK:
        _WEB_LOG.append(entry)
        if len(_WEB_LOG) > 300:
            _WEB_LOG.pop(0)

# Hook into Flask to log requests
@app.after_request
def log_request(response):
    try:
        ip = get_real_ip() if request.endpoint not in ('healthz', 'static') else None
        if ip and not request.path.startswith('/healthz'):
            web_log_add({
                "time": datetime.now(VN_TZ).strftime('%H:%M:%S %d/%m'),
                "ip": ip,
                "method": request.method,
                "path": request.path,
                "status": response.status_code
            })
    except Exception:
        pass
    return response

@app.route('/api/web_log', methods=['GET'])
def api_web_log():
    if not session.get('is_admin'):
        return jsonify([]), 401
    with _WEB_LOG_LOCK:
        return jsonify(list(reversed(_WEB_LOG[-100:])))

# ============================================================
# SOUNDCLOUD SEARCH — adapted from scl.py (no Zalo/PIL)
# ============================================================
_sc_client_id_cache = [None]

def _sc_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://soundcloud.com/"
    }

def _sc_get_client_id():
    if _sc_client_id_cache[0]:
        return _sc_client_id_cache[0]
    try:
        import re as _re2
        if not _TG_OK or _req_tg is None:
            return None
        res = _req_tg.get('https://soundcloud.com/', headers=_sc_headers(), timeout=8)
        try:
            from bs4 import BeautifulSoup as _BS
            soup = _BS(res.text, 'html.parser')
            scripts = [t.get('src') for t in soup.find_all('script', {'crossorigin': True}) if t.get('src', '').startswith('https')]
        except ImportError:
            scripts = _re2.findall(r'src="(https://[^"]+\.js[^"]*)"', res.text)
        if not scripts:
            return None
        js = _req_tg.get(scripts[-1], headers=_sc_headers(), timeout=8)
        m = _re2.search(r'client_id:"([a-zA-Z0-9]+)"', js.text)
        if m:
            _sc_client_id_cache[0] = m.group(1)
            return _sc_client_id_cache[0]
    except Exception:
        pass
    return None

@app.route('/api/search_music', methods=['GET', 'POST', 'OPTIONS'])
def api_search_music():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    query = (request.args.get('q') or request.form.get('q') or '').strip()
    if not query:
        return jsonify({"status": "error", "message": "Thiếu từ khóa tìm kiếm"})
    if not _TG_OK or _req_tg is None:
        return jsonify({"status": "error", "message": "requests không có sẵn"})
    try:
        import re as _re3
        encoded_q = urllib.parse.quote(query)
        search_url = f'https://m.soundcloud.com/search?q={encoded_q}'
        res = _req_tg.get(search_url, headers=_sc_headers(), timeout=10)
        songs = []
        url_pat = _re3.compile(r'^/[^/]+/[^/]+$')
        try:
            from bs4 import BeautifulSoup as _BS2
            soup = _BS2(res.text, 'html.parser')
            for elem in soup.select('li > div'):
                a = elem.select_one('a')
                if a and a.has_attr('href') and url_pat.match(a['href']):
                    title = a.get('aria-label', a['href'].split('/')[-1].replace('-', ' ')).strip()
                    link = 'https://soundcloud.com' + a['href']
                    img = elem.select_one('img')
                    cover = img['src'] if img and img.has_attr('src') else ''
                    if cover and '-large' in cover:
                        cover = cover.replace('-large', '-t200x200')
                    songs.append({"title": title, "url": link, "cover": cover})
                if len(songs) >= 5:
                    break
        except ImportError:
            # Fallback: regex search
            hrefs = _re3.findall(r'href="(/[^/"]+/[^/"]+)"[^>]*aria-label="([^"]+)"', res.text)
            for href, label in hrefs[:5]:
                link = 'https://soundcloud.com' + href
                imgs = _re3.findall(r'src="(https://i1\.sndcdn\.com/artworks-[^"]+)"', res.text)
                cover = imgs[len(songs)] if len(imgs) > len(songs) else ''
                songs.append({"title": label.strip(), "url": link, "cover": cover})
        return jsonify({"status": "success", "songs": songs})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/get_stream_url', methods=['POST', 'OPTIONS'])
def api_get_stream_url():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    url = request.form.get('url', '').strip()
    if not url:
        return jsonify({"status": "error", "message": "Thiếu URL"})
    if not _TG_OK or _req_tg is None:
        return jsonify({"status": "error", "message": "requests không có sẵn"})
    try:
        client_id = _sc_get_client_id()
        if not client_id:
            return jsonify({"status": "error", "message": "Không lấy được client_id từ SoundCloud"})
        api_url = f'https://api-v2.soundcloud.com/resolve?url={urllib.parse.quote(url, safe="")}&client_id={client_id}'
        res = _req_tg.get(api_url, headers=_sc_headers(), timeout=10)
        data = res.json()
        title = data.get('title', 'SoundCloud Track')
        cover = data.get('artwork_url') or data.get('user', {}).get('avatar_url', '')
        if cover:
            cover = cover.replace('-large', '-t300x300')
        for t in data.get('media', {}).get('transcodings', []):
            if t.get('format', {}).get('protocol') == 'progressive':
                sr = _req_tg.get(f"{t['url']}?client_id={client_id}", headers=_sc_headers(), timeout=8)
                stream_url = sr.json().get('url')
                if stream_url:
                    return jsonify({"status": "success", "stream_url": stream_url, "title": title, "cover": cover})
        return jsonify({"status": "error", "message": "Không tìm thấy stream URL"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# ============================================================
# NEW HTML TEMPLATES — White/Light Theme
# ============================================================

HTML_P1 = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Server Key Premium — Văn Khánh</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;500;600;700;800;900&family=Orbitron:wght@500;700;900&display=swap');
:root {
  --bg: #f0f2f7;
  --panel: #ffffff;
  --card: #f8fafc;
  --card2: #f1f5f9;
  --border: rgba(0,0,0,0.08);
  --border-h: rgba(99,102,241,0.35);
  --primary: #6366f1;
  --primary2: #8b5cf6;
  --grad: linear-gradient(135deg, #6366f1, #8b5cf6);
  --grad-btn: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  --muted: #94a3b8;
  --text: #1e293b;
  --text2: #475569;
  --danger: #ef4444;
  --success: #22c55e;
  --warn: #f59e0b;
  --blue: #3b82f6;
  --shadow: 0 4px 24px rgba(99,102,241,0.10);
  --shadow-lg: 0 12px 48px rgba(99,102,241,0.18);
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
*:focus { outline: none; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Nunito', sans-serif;
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  position: relative;
  overflow-x: hidden;
}

/* STARTUP LOADING */
#startupLoading {
  position: fixed; inset: 0; background: #fff; z-index: 9999;
  display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 22px;
}
.startup-logo { width: 72px; height: 72px; background: var(--grad); border-radius: 20px; display: flex; align-items: center; justify-content: center; font-size: 2rem; color: #fff; box-shadow: var(--shadow-lg); animation: logoPop 1s ease; }
@keyframes logoPop { from { transform: scale(0.7); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.startup-title { font-family: 'Orbitron', sans-serif; font-size: 1rem; font-weight: 900; background: var(--grad); -webkit-background-clip: text; -webkit-text-fill-color: transparent; letter-spacing: 2px; }
.progress-wrap { width: min(300px, 75vw); }
.progress-track { width: 100%; height: 8px; background: #e2e8f0; border-radius: 99px; overflow: hidden; }
.progress-fill { height: 100%; width: 0%; background: var(--grad); border-radius: 99px; transition: width 0.12s linear; }
.progress-pct { text-align: center; font-size: 0.78rem; font-weight: 700; color: var(--primary); margin-top: 6px; }

/* TOAST NOTIFICATION */
#toast-overlay {
  position: fixed; inset: 0; z-index: 8888; display: none;
  justify-content: center; align-items: center; pointer-events: none;
}
#toast-overlay.show { display: flex; }
.toast-icon-wrap {
  width: 120px; height: 120px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 3.2rem; animation: toastPop 0.4s cubic-bezier(0.175,0.885,0.32,1.275) both;
  box-shadow: 0 20px 60px rgba(0,0,0,0.2);
}
@keyframes toastPop { from { transform: scale(0.3); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.toast-success { background: linear-gradient(135deg, #22c55e, #16a34a); color: #fff; }
.toast-error { background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; }
.toast-fade-out { animation: toastFade 0.4s ease forwards; }
@keyframes toastFade { to { transform: scale(0.8); opacity: 0; } }

/* HAMBURGER */
.hamburger {
  position: fixed; top: 14px; left: 16px; z-index: 600;
  cursor: pointer; display: flex; flex-direction: column; gap: 5px; padding: 8px;
  background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.10);
  transition: box-shadow 0.2s;
}
.hamburger:hover { box-shadow: 0 4px 20px rgba(99,102,241,0.2); }
.hamburger span { display: block; width: 22px; height: 2.5px; border-radius: 4px; background: var(--primary); transition: all 0.3s ease; }
.hamburger span:nth-child(2) { width: 16px; }
.hamburger.open span:nth-child(1) { transform: translateY(7.5px) rotate(45deg); }
.hamburger.open span:nth-child(2) { opacity: 0; transform: translateX(-8px); }
.hamburger.open span:nth-child(3) { transform: translateY(-7.5px) rotate(-45deg); }

/* NAV DROPDOWN */
.nav-dropdown {
  position: fixed; top: 62px; left: 12px; z-index: 599;
  background: #fff; border: 1px solid rgba(99,102,241,0.15);
  border-radius: 18px; padding: 8px; min-width: 220px;
  box-shadow: 0 16px 60px rgba(0,0,0,0.15);
  display: none; flex-direction: column; gap: 3px;
}
.nav-dropdown.show { display: flex; animation: navIn 0.25s cubic-bezier(0.175,0.885,0.32,1.275); }
@keyframes navIn { from { opacity: 0; transform: translateY(-8px) scale(0.96); } to { opacity: 1; transform: none; } }
.nav-item {
  padding: 10px 14px; border: none; background: transparent; color: var(--text2);
  font-size: 0.84rem; font-weight: 700; cursor: pointer; border-radius: 11px;
  text-align: left; display: flex; align-items: center; gap: 10px;
  transition: all 0.15s ease; font-family: 'Nunito', sans-serif;
}
.nav-item i { width: 18px; text-align: center; color: var(--muted); }
.nav-item:hover { color: var(--primary); background: rgba(99,102,241,0.07); }
.nav-item:hover i { color: var(--primary); }
.nav-item.active { background: var(--grad); color: #fff; font-weight: 800; box-shadow: 0 4px 16px rgba(99,102,241,0.3); }
.nav-item.active i { color: #fff; }
.nav-divider { height: 1px; background: #f1f5f9; margin: 4px 0; }
.nav-item-logout { color: var(--danger) !important; }
.nav-item-logout i { color: var(--danger) !important; }
.nav-item-logout:hover { background: rgba(239,68,68,0.07) !important; }

/* VIP BADGE */
.vip-badge {
  position: fixed; top: 14px; right: 16px; z-index: 600;
  background: var(--grad); padding: 7px 14px; border-radius: 20px;
  font-size: 0.72rem; font-weight: 800; color: #fff;
  display: flex; align-items: center; gap: 6px;
  box-shadow: 0 4px 16px rgba(99,102,241,0.35);
  letter-spacing: 0.4px; text-transform: uppercase;
  animation: badgePulse 3s ease infinite;
}
@keyframes badgePulse { 0%,100%{box-shadow:0 4px 14px rgba(99,102,241,0.3)} 50%{box-shadow:0 4px 24px rgba(139,92,246,0.5)} }

/* ADMIN LOGIN BTN (user view) */
.admin-login-btn {
  position: fixed; top: 14px; right: 16px; z-index: 600;
  background: #fff; border: 1.5px solid rgba(99,102,241,0.3); color: var(--primary);
  padding: 7px 14px; border-radius: 20px; font-size: 0.78rem; font-weight: 800;
  display: flex; align-items: center; gap: 6px; cursor: pointer;
  box-shadow: 0 2px 12px rgba(99,102,241,0.12); transition: 0.2s;
  font-family: 'Nunito', sans-serif;
}
.admin-login-btn:hover { background: rgba(99,102,241,0.07); border-color: var(--primary); }

/* MAIN PANEL */
.panel {
  width: min(500px, 100vw);
  min-height: 100vh;
  background: var(--bg);
  display: flex;
  flex-direction: column;
  position: relative;
  padding-top: 58px;
}

/* PANEL BODY / SCROLL */
.panel-body { flex: 1; padding: 0 12px 80px; }
.panel-body::-webkit-scrollbar { width: 3px; }

/* TABS */
.tab { display: none; }
.tab.active { display: block; animation: tabIn 0.35s cubic-bezier(0.22,1,0.36,1) both; }
@keyframes tabIn { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }

/* CARDS */
.card {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 18px; padding: 18px; margin-bottom: 14px;
  box-shadow: var(--shadow);
}
.card-title {
  font-size: 0.85rem; font-weight: 800; color: var(--text);
  display: flex; align-items: center; gap: 8px; margin-bottom: 16px;
}
.card-title i { color: var(--primary); font-size: 0.92rem; }

/* SECTION HEADER */
.section-header {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 12px 10px; margin-bottom: 4px;
}
.section-header-title {
  font-family: 'Orbitron', sans-serif; font-size: 0.75rem; font-weight: 900;
  background: var(--grad); -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  letter-spacing: 1.5px; text-transform: uppercase;
}

/* FORMS */
.fg { margin-bottom: 12px; }
.fg label { display: block; font-size: 0.73rem; font-weight: 800; color: var(--text2); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
.fg input, .fg select, .fg textarea {
  width: 100%; padding: 11px 14px;
  background: var(--card); border: 1.5px solid var(--border);
  border-radius: 12px; color: var(--text); font-size: 0.88rem; font-weight: 600;
  transition: 0.2s; outline: none; font-family: 'Nunito', sans-serif;
  -webkit-appearance: none;
}
.fg input:focus, .fg select:focus, .fg textarea:focus {
  border-color: var(--primary); box-shadow: 0 0 0 3px rgba(99,102,241,0.12);
}
.fg select option { background: #fff; }
.fg input::placeholder { color: var(--muted); font-weight: 500; }

/* RADIO */
.radio-row { display: flex; gap: 8px; }
.radio-opt {
  flex: 1; padding: 10px 12px; background: var(--card);
  border: 1.5px solid var(--border); border-radius: 11px;
  cursor: pointer; display: flex; align-items: center; gap: 7px;
  font-size: 0.82rem; font-weight: 700; color: var(--text2); transition: 0.2s;
}
.radio-opt:has(input:checked) { border-color: var(--primary); color: var(--primary); background: rgba(99,102,241,0.06); }
.radio-opt input { accent-color: var(--primary); width: 15px; height: 15px; }

/* BUTTONS */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 7px;
  padding: 12px 18px; border: none; border-radius: 12px;
  font-weight: 800; font-size: 0.88rem; cursor: pointer;
  transition: all 0.2s ease; font-family: 'Nunito', sans-serif; letter-spacing: 0.2px;
}
.btn-primary { background: var(--grad-btn); color: #fff; width: 100%; margin-top: 6px; box-shadow: 0 4px 16px rgba(99,102,241,0.3); }
.btn-primary:hover { transform: translateY(-2px); box-shadow: 0 8px 28px rgba(99,102,241,0.4); }
.btn-primary:active { transform: translateY(0); }
.btn-danger { background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; width: 100%; margin-top: 6px; }
.btn-danger:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(239,68,68,0.3); }
.btn-outline { background: transparent; border: 1.5px solid var(--primary); color: var(--primary); }
.btn-outline:hover { background: rgba(99,102,241,0.07); }
.btn-sm { padding: 6px 10px; font-size: 0.72rem; border-radius: 8px; border: 1.5px solid transparent; background: transparent; cursor: pointer; font-weight: 700; font-family: 'Nunito', sans-serif; transition: 0.2s; }
.btn-sm-blue { color: var(--blue); border-color: rgba(59,130,246,0.3); background: rgba(59,130,246,0.07); }
.btn-sm-blue:hover { background: rgba(59,130,246,0.15); }
.btn-sm-warn { color: var(--warn); border-color: rgba(245,158,11,0.3); background: rgba(245,158,11,0.07); }
.btn-sm-warn:hover { background: rgba(245,158,11,0.15); }
.btn-sm-red { color: var(--danger); border-color: rgba(239,68,68,0.3); background: rgba(239,68,68,0.07); }
.btn-sm-red:hover { background: rgba(239,68,68,0.15); }
.btn-sm-green { color: var(--success); border-color: rgba(34,197,94,0.3); background: rgba(34,197,94,0.07); }
.btn-sm-green:hover { background: rgba(34,197,94,0.15); }

/* BADGES */
.badge { display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; border-radius: 20px; font-size: 0.72rem; font-weight: 800; }
.badge-yes { background: rgba(34,197,94,0.12); color: #16a34a; border: 1px solid rgba(34,197,94,0.3); }
.badge-no { background: rgba(239,68,68,0.10); color: #dc2626; border: 1px solid rgba(239,68,68,0.2); }
.badge-warn { background: rgba(245,158,11,0.10); color: #b45309; border: 1px solid rgba(245,158,11,0.2); }

/* TABLES */
.tbl-wrap { width: 100%; overflow-x: auto; border-radius: 12px; border: 1px solid var(--border); }
table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
th { padding: 10px 12px; background: #f8fafc; color: var(--primary); font-weight: 800; text-transform: uppercase; font-size: 0.68rem; letter-spacing: 0.5px; white-space: nowrap; border-bottom: 1px solid var(--border); }
td { padding: 10px 12px; border-top: 1px solid rgba(0,0,0,0.04); vertical-align: middle; color: var(--text); }
tr:hover td { background: rgba(99,102,241,0.03); }
.key-val { font-weight: 800; color: var(--primary); font-size: 0.72rem; letter-spacing: 0.3px; }
.td-actions { display: flex; gap: 5px; flex-wrap: wrap; }

/* INFO ROWS */
.info-row { display: flex; justify-content: space-between; align-items: center; padding: 9px 0; border-bottom: 1px solid rgba(0,0,0,0.05); font-size: 0.84rem; }
.info-row:last-child { border-bottom: none; }
.info-label { color: var(--text2); font-weight: 600; }
.info-val { color: var(--text); font-weight: 700; text-align: right; }

/* SPINNER */
.spinner { width: 32px; height: 32px; border: 3px solid rgba(99,102,241,0.15); border-top-color: var(--primary); border-radius: 50%; animation: spin 0.7s linear infinite; }
.spinner-sm { width: 18px; height: 18px; border-width: 2px; display: inline-block; vertical-align: middle; }
@keyframes spin { to { transform: rotate(360deg); } }

/* LOAD OVERLAY */
.load-overlay { position: fixed; inset: 0; background: rgba(240,242,247,0.8); z-index: 400; display: none; justify-content: center; align-items: center; flex-direction: column; gap: 14px; backdrop-filter: blur(4px); }

/* LOGIN OVERLAY */
.login-overlay {
  position: fixed; inset: 0; background: rgba(15,23,42,0.55);
  z-index: 700; display: none; justify-content: center; align-items: center;
  backdrop-filter: blur(8px);
}
.login-overlay.show { display: flex; }
.login-card {
  width: min(380px, 94vw); padding: 36px 28px;
  background: #fff; border-radius: 24px;
  box-shadow: 0 24px 80px rgba(0,0,0,0.2);
  animation: loginIn 0.35s cubic-bezier(0.175,0.885,0.32,1.275);
}
@keyframes loginIn { from { transform: scale(0.9); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.login-logo { width: 56px; height: 56px; background: var(--grad); border-radius: 16px; display: flex; align-items: center; justify-content: center; margin: 0 auto 18px; font-size: 1.4rem; color: #fff; box-shadow: 0 8px 24px rgba(99,102,241,0.35); }
.login-title { font-family: 'Orbitron', sans-serif; font-size: 1.1rem; font-weight: 900; text-align: center; margin-bottom: 5px; background: var(--grad); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.login-sub { font-size: 0.8rem; color: var(--muted); margin-bottom: 22px; text-align: center; }
.login-err { background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.2); color: #dc2626; padding: 10px 12px; border-radius: 10px; font-size: 0.82rem; margin-bottom: 14px; display: none; }
.login-close { position: absolute; top: 14px; right: 14px; width: 32px; height: 32px; border: none; background: #f1f5f9; border-radius: 50%; cursor: pointer; font-size: 0.9rem; color: var(--text2); display: flex; align-items: center; justify-content: center; }
.input-with-icon { position: relative; }
.input-with-icon i { position: absolute; left: 13px; top: 50%; transform: translateY(-50%); color: var(--muted); font-size: 0.82rem; }
.input-with-icon input { padding-left: 38px; }

/* FREE LINK BOX */
.free-link-box { background: rgba(34,197,94,0.06); border: 1.5px dashed rgba(34,197,94,0.35); border-radius: 14px; padding: 14px; margin-top: 14px; }
.free-link-label { font-size: 0.73rem; color: var(--text2); font-weight: 800; margin-bottom: 8px; text-transform: uppercase; }
.free-link-input { width: 100%; padding: 10px 13px; background: #f8fafc; border: 1px solid rgba(34,197,94,0.25); border-radius: 10px; color: #16a34a; font-weight: 700; font-size: 0.84rem; margin-bottom: 8px; }

/* RESULT BOX */
.result-box { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 16px; margin-top: 12px; font-size: 0.84rem; line-height: 1.65; }
.result-title { text-align: center; color: var(--primary); font-weight: 800; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border); padding-bottom: 10px; margin-bottom: 14px; }

/* IP BOX */
.ip-box { background: rgba(99,102,241,0.04); border: 1px solid rgba(99,102,241,0.18); border-radius: 14px; padding: 14px; margin-top: 12px; font-size: 0.82rem; line-height: 1.7; }
.ip-box .ip-header { font-weight: 800; color: var(--primary); display: flex; align-items: center; gap: 6px; margin-bottom: 8px; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.5px; }
.ip-field { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid rgba(0,0,0,0.05); }
.ip-field:last-child { border-bottom: none; }
.ip-key { color: var(--muted); font-size: 0.78rem; }
.ip-val { color: var(--text); font-weight: 700; font-size: 0.82rem; }

/* MUSIC PLAYER */
.music-player-card {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 20px; padding: 18px; margin-bottom: 14px;
  box-shadow: var(--shadow); overflow: hidden;
  position: relative;
}
.music-player-card::before {
  content: ''; position: absolute; inset: 0; pointer-events: none;
  background: linear-gradient(135deg, rgba(99,102,241,0.04) 0%, rgba(139,92,246,0.04) 100%);
}
.dj-header { display: flex; align-items: center; gap: 9px; margin-bottom: 14px; }
.dj-header-title { font-family: 'Orbitron', sans-serif; font-size: 0.72rem; font-weight: 900; background: var(--grad); -webkit-background-clip: text; -webkit-text-fill-color: transparent; letter-spacing: 2px; text-transform: uppercase; }
.dj-eq-bars { display: flex; align-items: flex-end; gap: 2.5px; height: 18px; margin-left: auto; }
.dj-eq-bar { width: 3px; border-radius: 2px; background: var(--primary); opacity: 0.2; transform-origin: bottom; }
.dj-eq-bar.active { opacity: 1; animation: eqAnim 0.55s ease-in-out infinite alternate; }
@keyframes eqAnim { from{transform:scaleY(0.2)} to{transform:scaleY(1)} }
.dj-tracks { display: flex; gap: 7px; margin-bottom: 14px; }
.dj-track-btn {
  flex: 1; padding: 8px 5px; border-radius: 12px;
  border: 1.5px solid var(--border); background: var(--card);
  cursor: pointer; transition: 0.2s; text-align: center; min-width: 0;
}
.dj-track-btn .dt-num { font-size: 0.6rem; font-weight: 900; color: var(--muted); margin-bottom: 3px; font-family: 'Orbitron', sans-serif; }
.dj-track-btn .dt-name { font-size: 0.7rem; font-weight: 700; color: var(--text2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dj-track-btn:hover { border-color: var(--primary); background: rgba(99,102,241,0.06); }
.dj-track-btn.playing { border-color: var(--primary); background: rgba(99,102,241,0.08); box-shadow: 0 2px 12px rgba(99,102,241,0.15); }
.dj-track-btn.playing .dt-num { color: var(--primary); }
.dj-track-btn.playing .dt-name { color: var(--primary); font-weight: 800; }
.dj-main { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
.vinyl { width: 60px; height: 60px; flex-shrink: 0; border-radius: 50%; background: linear-gradient(135deg, #e2e8f0 0%, #cbd5e1 100%); border: 2px solid #e2e8f0; display: flex; justify-content: center; align-items: center; box-shadow: 0 4px 16px rgba(0,0,0,0.1); }
.vinyl-c { width: 22px; height: 22px; background: var(--grad); border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.vinyl.spin { animation: spin 3s linear infinite; }
.dj-info { flex: 1; min-width: 0; }
.music-title-text { font-size: 0.88rem; font-weight: 800; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 4px; }
.music-status-text { font-size: 0.74rem; color: var(--muted); font-weight: 600; }
.dj-cover-sm { width: 44px; height: 44px; border-radius: 10px; object-fit: cover; flex-shrink: 0; border: 1px solid var(--border); display: none; }
.dj-controls { display: flex; align-items: center; justify-content: center; gap: 12px; margin-bottom: 14px; }
.ctrl-btn { width: 36px; height: 36px; border-radius: 50%; border: 1.5px solid var(--border); background: var(--card); cursor: pointer; color: var(--text2); font-size: 0.82rem; display: flex; align-items: center; justify-content: center; transition: 0.2s; }
.ctrl-btn:hover { border-color: var(--primary); color: var(--primary); background: rgba(99,102,241,0.07); }
.play-btn { width: 52px; height: 52px; border-radius: 50%; background: var(--grad); border: none; cursor: pointer; color: #fff; font-size: 1.05rem; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: 0.2s; box-shadow: 0 6px 22px rgba(99,102,241,0.4); }
.play-btn:hover { transform: scale(1.1); box-shadow: 0 10px 32px rgba(99,102,241,0.55); }
.seek-bar { width: 100%; height: 4px; border-radius: 99px; background: #e2e8f0; outline: none; -webkit-appearance: none; cursor: pointer; accent-color: var(--primary); display: block; }
.seek-bar::-webkit-slider-thumb { -webkit-appearance: none; width: 14px; height: 14px; border-radius: 50%; background: var(--primary); cursor: pointer; box-shadow: 0 2px 8px rgba(99,102,241,0.5); }
.seek-times { display: flex; justify-content: space-between; font-size: 0.67rem; color: var(--muted); margin-top: 5px; font-weight: 700; font-family: 'Orbitron', sans-serif; }

/* SOUNDCLOUD SEARCH */
.sc-search-card { background: var(--panel); border: 1px solid var(--border); border-radius: 20px; padding: 18px; margin-bottom: 14px; box-shadow: var(--shadow); }
.sc-search-row { display: flex; gap: 9px; margin-bottom: 12px; }
.sc-input { flex: 1; padding: 12px 15px; background: var(--card); border: 1.5px solid var(--border); border-radius: 12px; color: var(--text); font-size: 0.88rem; font-weight: 600; font-family: 'Nunito', sans-serif; outline: none; transition: 0.2s; }
.sc-input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(99,102,241,0.12); }
.sc-btn { flex-shrink: 0; padding: 12px 16px; background: var(--grad-btn); border: none; border-radius: 12px; color: #fff; font-weight: 800; font-size: 0.85rem; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: 0.2s; font-family: 'Nunito', sans-serif; white-space: nowrap; box-shadow: 0 4px 14px rgba(99,102,241,0.3); }
.sc-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(99,102,241,0.4); }
.sc-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
.sc-loading { display: none; text-align: center; padding: 24px 0; }
.sc-loading-spin { width: 40px; height: 40px; border: 3px solid rgba(99,102,241,0.15); border-top-color: var(--primary); border-radius: 50%; animation: spin 0.7s linear infinite; margin: 0 auto 12px; }
.sc-results { display: none; }
.sc-song-card {
  display: flex; align-items: center; gap: 12px;
  padding: 12px; border-radius: 14px; border: 1.5px solid var(--border);
  background: var(--card); margin-bottom: 8px; cursor: pointer; transition: 0.2s;
}
.sc-song-card:hover { border-color: rgba(99,102,241,0.4); background: rgba(99,102,241,0.04); }
.sc-song-card.selected { border-color: var(--primary); background: rgba(99,102,241,0.08); box-shadow: 0 2px 12px rgba(99,102,241,0.15); }
.sc-cover { width: 52px; height: 52px; border-radius: 10px; object-fit: cover; flex-shrink: 0; background: linear-gradient(135deg, #e2e8f0, #cbd5e1); border: 1px solid var(--border); }
.sc-cover-placeholder { width: 52px; height: 52px; border-radius: 10px; flex-shrink: 0; background: var(--grad); display: flex; align-items: center; justify-content: center; color: #fff; font-size: 1.1rem; }
.sc-song-info { flex: 1; min-width: 0; }
.sc-song-title { font-size: 0.84rem; font-weight: 800; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 3px; }
.sc-song-meta { font-size: 0.72rem; color: var(--muted); font-weight: 600; }
.sc-sel-indicator { width: 22px; height: 22px; border-radius: 50%; border: 2px solid var(--border); flex-shrink: 0; display: flex; align-items: center; justify-content: center; transition: 0.2s; }
.sc-song-card.selected .sc-sel-indicator { background: var(--primary); border-color: var(--primary); color: #fff; }
.sc-listen-row { display: flex; gap: 9px; margin-top: 10px; }
.sc-listen-btn { flex: 1; padding: 12px; background: var(--grad-btn); border: none; border-radius: 12px; color: #fff; font-weight: 800; font-size: 0.88rem; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 7px; transition: 0.2s; font-family: 'Nunito', sans-serif; box-shadow: 0 4px 16px rgba(99,102,241,0.3); }
.sc-listen-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 28px rgba(99,102,241,0.4); }
.sc-listen-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

/* GET KEY SECTION */
.getkey-card {
  background: var(--panel); border: 1.5px solid rgba(99,102,241,0.2); border-radius: 20px; padding: 20px; margin-bottom: 14px;
  box-shadow: var(--shadow);
  background: linear-gradient(135deg, rgba(99,102,241,0.04) 0%, rgba(139,92,246,0.04) 100%);
}
.getkey-icon { width: 52px; height: 52px; background: var(--grad); border-radius: 14px; display: flex; align-items: center; justify-content: center; font-size: 1.3rem; color: #fff; margin: 0 auto 14px; box-shadow: 0 6px 20px rgba(99,102,241,0.3); }
.getkey-title { font-family: 'Orbitron', sans-serif; font-size: 0.9rem; font-weight: 900; text-align: center; margin-bottom: 6px; background: var(--grad); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.getkey-sub { font-size: 0.78rem; color: var(--text2); text-align: center; margin-bottom: 16px; line-height: 1.6; }
.getkey-info-pills { display: flex; gap: 7px; justify-content: center; flex-wrap: wrap; margin-bottom: 16px; }
.getkey-pill { background: rgba(99,102,241,0.1); color: var(--primary); border: 1px solid rgba(99,102,241,0.2); border-radius: 20px; padding: 4px 12px; font-size: 0.72rem; font-weight: 700; display: flex; align-items: center; gap: 5px; }

/* SOCIAL BUTTONS */
.social-btn { display: flex; align-items: center; gap: 12px; padding: 13px 16px; border-radius: 14px; color: #fff; text-decoration: none; font-weight: 700; font-size: 0.84rem; margin-bottom: 9px; transition: all 0.2s ease; }
.social-btn:hover { transform: translateX(4px); }
.social-btn .s-icon { width: 38px; height: 38px; border-radius: 11px; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; flex-shrink: 0; }
.social-btn .s-text { display: flex; flex-direction: column; gap: 1px; }
.social-btn .s-label { font-size: 0.68rem; font-weight: 700; opacity: 0.75; letter-spacing: 0.3px; text-transform: uppercase; }
.social-btn .s-name { font-size: 0.86rem; font-weight: 800; }
.social-btn .s-arrow { margin-left: auto; opacity: 0.5; font-size: 0.78rem; }
.social-tg { background: linear-gradient(135deg, #1a3a5c, #1d5c8a); border: 1px solid rgba(29,142,217,0.3); }
.social-tg .s-icon { background: linear-gradient(135deg, #1d8ec3, #229ED9); }
.social-tg:hover { box-shadow: 0 6px 20px rgba(34,158,217,0.2); }
.social-tt { background: linear-gradient(135deg, #1a1a2e, #2d2d45); border: 1px solid rgba(255,255,255,0.12); }
.social-tt .s-icon { background: linear-gradient(135deg, #111, #333); border: 1px solid #444; }
.social-tt:hover { box-shadow: 0 6px 20px rgba(0,0,0,0.25); }
.social-yt { background: linear-gradient(135deg, #2d1010, #3a1515); border: 1px solid rgba(255,0,0,0.2); }
.social-yt .s-icon { background: linear-gradient(135deg, #c4302b, #ff0000); }
.social-yt:hover { box-shadow: 0 6px 20px rgba(255,0,0,0.15); }
.social-fb { background: linear-gradient(135deg, #0d1f3c, #1a3060); border: 1px solid rgba(24,119,242,0.25); }
.social-fb .s-icon { background: linear-gradient(135deg, #1877f2, #4293ff); }
.social-fb:hover { box-shadow: 0 6px 20px rgba(24,119,242,0.18); }

/* DEV REVIEW */
.dev-req-card { background: var(--card); border: 1.5px solid rgba(139,92,246,0.18); border-radius: 14px; padding: 14px 16px; margin-bottom: 10px; transition: 0.2s; }
.dev-req-card:hover { border-color: rgba(139,92,246,0.4); }
.dev-req-device { font-size: 0.76rem; font-weight: 800; color: var(--primary); word-break: break-all; margin-bottom: 8px; display: flex; align-items: flex-start; gap: 7px; }
.dev-req-meta { display: flex; flex-wrap: wrap; gap: 6px; font-size: 0.73rem; color: var(--text2); margin-bottom: 10px; }
.dev-req-meta span { background: var(--card2); border: 1px solid var(--border); padding: 3px 8px; border-radius: 6px; }
.dev-req-actions { display: flex; gap: 7px; flex-wrap: wrap; align-items: center; }
.badge-pending { background: rgba(245,158,11,0.10); color: #b45309; border: 1px solid rgba(245,158,11,0.25); display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; border-radius: 20px; font-size: 0.72rem; font-weight: 800; }
.badge-approved-dev { background: rgba(34,197,94,0.10); color: #15803d; border: 1px solid rgba(34,197,94,0.25); display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; border-radius: 20px; font-size: 0.72rem; font-weight: 800; }
.badge-expired-dev { background: rgba(239,68,68,0.10); color: #dc2626; border: 1px solid rgba(239,68,68,0.25); display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; border-radius: 20px; font-size: 0.72rem; font-weight: 800; }
.apv-card { background: var(--card); border: 1.5px solid rgba(99,102,241,0.15); border-radius: 14px; padding: 13px 16px; margin-bottom: 9px; transition: 0.2s; }
.apv-card:hover { border-color: rgba(99,102,241,0.35); }
.apv-device { font-size: 0.74rem; font-weight: 900; color: var(--text); word-break: break-all; margin-bottom: 7px; }
.apv-meta { display: flex; flex-wrap: wrap; gap: 6px; font-size: 0.72rem; color: var(--text2); margin-bottom: 9px; }
.apv-meta span { background: var(--card2); border: 1px solid var(--border); padding: 3px 8px; border-radius: 6px; }
.apv-actions { display: flex; gap: 7px; flex-wrap: wrap; }
.dev-empty { text-align: center; padding: 24px 0; color: var(--muted); font-size: 0.83rem; }
.dev-empty i { font-size: 1.6rem; display: block; margin-bottom: 8px; opacity: 0.3; }

/* CHANGE PASS CARD */
.change-pass-card { background: rgba(99,102,241,0.04); border: 1.5px solid rgba(99,102,241,0.2); border-radius: 18px; padding: 22px; }
.change-pass-icon { width: 52px; height: 52px; margin: 0 auto 12px; background: var(--grad); border-radius: 14px; display: flex; align-items: center; justify-content: center; font-size: 1.3rem; color: #fff; box-shadow: 0 6px 20px rgba(99,102,241,0.3); }
.change-pass-title { font-family: 'Orbitron', sans-serif; font-size: 0.9rem; font-weight: 900; text-align: center; margin-bottom: 5px; background: var(--grad); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.change-pass-sub { font-size: 0.78rem; color: var(--muted); margin-top: 5px; text-align: center; }
.change-pass-warn { background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.2); border-radius: 10px; padding: 10px 13px; font-size: 0.78rem; color: #15803d; margin-bottom: 14px; display: flex; gap: 8px; align-items: flex-start; }

/* KEY SEARCH WRAP */
.key-search-wrap { position: relative; }
.key-search-wrap input { padding-right: 50px; }
.key-search-wrap .scan-ip-btn { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: rgba(99,102,241,0.1); border: 1px solid rgba(99,102,241,0.25); color: var(--primary); border-radius: 8px; padding: 5px 9px; font-size: 0.7rem; font-weight: 800; cursor: pointer; transition: 0.2s; }

/* CHECK IP TAB */
.check-ip-result { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 16px; margin-top: 12px; display: none; }
.ip-info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
.ip-info-cell { background: var(--panel); border-radius: 11px; padding: 11px 13px; border: 1px solid var(--border); }
.ip-info-cell .ic-label { font-size: 0.66rem; color: var(--muted); font-weight: 800; text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 4px; }
.ip-info-cell .ic-val { font-size: 0.85rem; font-weight: 800; color: var(--text); word-break: break-all; }
.ip-info-cell.full-width { grid-column: 1 / -1; }

/* SETTINGS / EP */
.ep-outer { background: #f0fdf4; border: 1px solid rgba(34,197,94,0.22); border-radius: 16px; padding: 18px; margin-bottom: 14px; }
.ep-section-name { font-size: 0.8rem; font-weight: 900; color: #15803d; letter-spacing: 1px; text-transform: uppercase; }
.ep-section-desc { font-size: 0.75rem; color: #4b7a5a; line-height: 1.65; margin-bottom: 16px; }
.ep-card { background: rgba(255,255,255,0.7); border: 1px solid rgba(34,197,94,0.15); border-radius: 12px; padding: 16px; margin-bottom: 12px; }
.ep-badge-post { background: rgba(34,197,94,0.15); color: #15803d; border: 1px solid rgba(34,197,94,0.4); border-radius: 5px; padding: 3px 9px; font-size: 0.7rem; font-weight: 900; letter-spacing: 1px; }
.ep-path { font-family: 'Courier New', monospace; color: #1e293b; font-size: 0.84rem; font-weight: 600; }
.ep-url-row { background: rgba(240,253,244,0.8); border: 1px solid rgba(34,197,94,0.12); border-radius: 9px; padding: 10px 13px; display: flex; align-items: flex-start; gap: 10px; margin-bottom: 10px; }
.ep-url-text { flex: 1; font-family: 'Courier New', monospace; font-size: 0.74rem; color: #2d6a4f; word-break: break-all; line-height: 1.6; }
.ep-copy-btn { flex-shrink: 0; background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.3); color: #15803d; border-radius: 7px; padding: 5px 9px; font-size: 0.72rem; font-weight: 700; cursor: pointer; transition: 0.2s; font-family: 'Nunito', sans-serif; }
.ep-copy-btn:hover { background: rgba(34,197,94,0.18); }
.ep-body-box { background: rgba(240,253,244,0.7); border: 1px solid rgba(34,197,94,0.1); border-radius: 9px; padding: 12px 14px; font-family: 'Courier New', monospace; font-size: 0.78rem; line-height: 1.8; color: #4b6a5a; }

/* WEB LOG */
.log-entry { display: flex; align-items: center; gap: 10px; padding: 9px 12px; border-radius: 10px; background: var(--card); border: 1px solid var(--border); margin-bottom: 7px; font-size: 0.75rem; }
.log-time { color: var(--muted); font-family: 'Orbitron', sans-serif; font-size: 0.65rem; flex-shrink: 0; }
.log-method { padding: 2px 7px; border-radius: 5px; font-weight: 900; font-size: 0.65rem; flex-shrink: 0; }
.log-method-get { background: rgba(34,197,94,0.12); color: #15803d; }
.log-method-post { background: rgba(59,130,246,0.12); color: #1d4ed8; }
.log-path { flex: 1; color: var(--text); font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.log-status { flex-shrink: 0; font-weight: 800; font-family: 'Orbitron', sans-serif; font-size: 0.68rem; }
.log-status-ok { color: var(--success); }
.log-status-err { color: var(--danger); }
.log-ip { color: var(--muted); font-size: 0.68rem; flex-shrink: 0; }

/* COUNTDOWN */
.free-cd { font-family: 'Orbitron', sans-serif; font-size: 0.9rem; color: var(--success); }

/* ADMIN HEADER */
.admin-header {
  position: fixed; top: 0; left: 50%; transform: translateX(-50%);
  z-index: 2000; pointer-events: none;
  display: flex; align-items: center; justify-content: center;
  gap: 11px; padding: 8px 22px 8px 14px;
  background: rgba(255,255,255,0.92);
  border-bottom: 1px solid rgba(99,102,241,0.18);
  border-radius: 0 0 24px 24px;
  box-shadow: 0 6px 28px rgba(99,102,241,0.16);
  backdrop-filter: blur(14px);
  width: min(460px, 100vw);
  animation: headerDrop .5s cubic-bezier(0.34,1.56,0.64,1) both;
}
@keyframes headerDrop {
  from { transform: translateX(-50%) translateY(-100%); opacity:0; }
  to { transform: translateX(-50%) translateY(0); opacity:1; }
}
.admin-avatar-wrap {
  position: relative; flex-shrink: 0; width: 46px; height: 46px;
}
.admin-avatar-ring {
  position: absolute; inset: -5px; border-radius: 50%;
  border: 3px solid transparent;
  border-top-color: #6366f1; border-right-color: #8b5cf6;
  border-bottom-color: #6366f1; border-left-color: rgba(99,102,241,0.2);
  animation: ringSpinVip 1.4s linear infinite;
  box-shadow: 0 0 12px rgba(99,102,241,0.35);
}
@keyframes ringSpinVip { to { transform: rotate(360deg); } }
.admin-avatar-ring2 {
  position: absolute; inset: -9px; border-radius: 50%;
  border: 2px solid transparent;
  border-top-color: rgba(139,92,246,0.5); border-bottom-color: rgba(99,102,241,0.3);
  animation: ringSpinVip 2.2s linear infinite reverse;
}
.admin-avatar-img {
  width: 46px; height: 46px; border-radius: 50%;
  object-fit: cover; border: 2px solid rgba(99,102,241,0.3);
  display: block;
}
.admin-header-info { display: flex; flex-direction: column; gap: 1px; }
.admin-header-name {
  font-family: 'Orbitron', sans-serif; font-size: 0.75rem; font-weight: 900;
  background: linear-gradient(135deg,#6366f1,#8b5cf6);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  letter-spacing: 1px; line-height: 1.2;
}
.admin-header-tag {
  font-size: 0.62rem; font-weight: 800; color: #94a3b8;
  text-transform: uppercase; letter-spacing: 0.5px;
  display: flex; align-items: center; gap: 4px;
}
.admin-header-dot {
  width: 6px; height: 6px; background: #22c55e; border-radius: 50%;
  box-shadow: 0 0 6px #22c55e; animation: pulse 1.4s ease infinite;
}
@keyframes pulse {
  0%,100%{transform:scale(1);opacity:1;}
  50%{transform:scale(1.5);opacity:.7;}
}
/* Push content below admin header */
.panel { margin-top: 74px !important; }
/* Ensure hamburger is below header */
.hamburger { top: 88px !important; }
.vip-badge, .admin-login-btn { top: 88px !important; }

/* IMPROVED TAB TRANSITIONS */
@keyframes tabIn {
  from { opacity: 0; transform: translateY(18px) scale(0.98); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
.tab.active { animation: tabIn 0.38s cubic-bezier(0.34,1.2,0.64,1) both; }

</style>
</head>
"""

HTML_P2 = """
<body>

<!-- TOAST NOTIFICATION -->
<div id="toast-overlay">
  <div id="toast-icon" class="toast-icon-wrap toast-success"><i id="toast-i" class="fa-solid fa-check"></i></div>
</div>

<!-- STARTUP LOADING -->
<div id="startupLoading">
  <div class="startup-logo"><i class="fa-solid fa-key"></i></div>
  <div class="startup-title">ĐANG KẾT NỐI...</div>
  <div class="progress-wrap">
    <div class="progress-track"><div class="progress-fill" id="pfill"></div></div>
    <div class="progress-pct" id="ppct">0%</div>
  </div>
</div>
<script>
(function(){
  var p=0,tgt=0,si=0;
  var steps=[[25,300],[55,400],[75,380],[90,420],[98,300],[100,150]];
  function ns(){ if(si>=steps.length)return; tgt=steps[si][0]; setTimeout(ns,steps[si][1]); si++; }
  ns();
  function tick(){
    if(p<tgt){p=Math.min(tgt,p+1.8);}
    var d=Math.min(100,Math.floor(p));
    document.getElementById('pfill').style.width=d+'%';
    document.getElementById('ppct').innerText=d+'%';
    if(d<100){requestAnimationFrame(tick);}
    else{setTimeout(function(){document.getElementById('startupLoading').style.display='none';},400);}
  }
  requestAnimationFrame(tick);
})();
</script>

<!-- LOAD OVERLAY -->
<div class="load-overlay" id="loadOverlay">
  <div class="spinner"></div>
  <div style="font-size:0.82rem;color:var(--primary);font-weight:800;">ĐANG XỬ LÝ...</div>
</div>

<!-- LOGIN OVERLAY -->
<div class="login-overlay" id="loginOverlay">
  <div class="login-card" style="position:relative;">
    <button class="login-close" onclick="closeLogin()" style="position:absolute;top:14px;right:14px;"><i class="fa-solid fa-xmark"></i></button>
    <div class="login-logo"><i class="fa-solid fa-shield-halved"></i></div>
    <div class="login-title">ADMIN LOGIN</div>
    <div class="login-sub">Nhập thông tin quản trị để tiếp tục</div>
    <div class="login-err" id="loginErr"></div>
    <div id="loginSpinner" style="display:none;padding:14px 0;"><div class="spinner" style="margin:auto;"></div></div>
    <form id="loginForm">
      <div class="fg">
        <label>Tài khoản</label>
        <div class="input-with-icon"><i class="fa-solid fa-user"></i><input type="text" id="lu" required placeholder="Tài khoản admin"></div>
      </div>
      <div class="fg">
        <label>Mật khẩu</label>
        <div class="input-with-icon"><i class="fa-solid fa-key"></i><input type="password" id="lp" required placeholder="Mật khẩu admin"></div>
      </div>
      <button type="submit" class="btn btn-primary"><i class="fa-solid fa-right-to-bracket"></i> ĐĂNG NHẬP</button>
    </form>
  </div>
</div>


<!-- ADMIN HEADER -->
<div class="admin-header" id="adminTopBar">
  <div class="admin-avatar-wrap">
    <div class="admin-avatar-ring2"></div>
    <div class="admin-avatar-ring"></div>
    <img src="data:image/jpeg;base64,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" alt="Admin" class="admin-avatar-img">
  </div>
  <div class="admin-header-info">
    <div class="admin-header-name">VĂN KHÁNH</div>
    <div class="admin-header-tag"><div class="admin-header-dot"></div> KEY MANAGER · ONLINE</div>
  </div>
</div>

<!-- HAMBURGER -->
<div class="hamburger" id="hbg" onclick="toggleMenu()"><span></span><span></span><span></span></div>

<!-- NAV DROPDOWN -->
<div class="nav-dropdown" id="navDrop">
  {% if session.get('is_admin') %}
  <button class="nav-item active" onclick="sw('trangchu')"><i class="fa-solid fa-house"></i> Trang Chủ</button>
  <button class="nav-item" onclick="sw('taokhoa')"><i class="fa-solid fa-plus-circle"></i> Tạo Khóa Mới</button>
  <button class="nav-item" onclick="sw('database')"><i class="fa-solid fa-database"></i> Quản Lý Keys</button>
  <button class="nav-item" onclick="sw('checkkey')"><i class="fa-solid fa-shield-halved"></i> Kiểm Tra Key</button>
  <button class="nav-item" onclick="sw('keyfree')"><i class="fa-solid fa-gift"></i> Key Free</button>
  <button class="nav-item" onclick="sw('keystats')"><i class="fa-solid fa-chart-bar"></i> Thống Kê Key</button>
  <button class="nav-item" onclick="sw('getkeyconfig')"><i class="fa-solid fa-sliders"></i> GetKey Config</button>
  <button class="nav-item" onclick="sw('weblog')"><i class="fa-solid fa-terminal"></i> Web Log</button>
  <button class="nav-item" onclick="sw('quyenriengtu')"><i class="fa-solid fa-lock"></i> Bảo Mật</button>
  <button class="nav-item" onclick="sw('devicereview')"><i class="fa-solid fa-mobile-screen-button"></i> Duyệt Thiết Bị</button>
  <button class="nav-item" onclick="sw('checkip')"><i class="fa-solid fa-globe"></i> Check IP</button>
  <button class="nav-item" onclick="sw('settings')"><i class="fa-solid fa-gear"></i> API Docs</button>
  <div class="nav-divider"></div>
  <a href="/logout" class="nav-item nav-item-logout" style="text-decoration:none;"><i class="fa-solid fa-arrow-right-from-bracket"></i> Đăng Xuất</a>
  {% else %}
  <button class="nav-item active" onclick="sw('trangchu');closeNav()"><i class="fa-solid fa-house"></i> Trang Chủ</button>
  <button class="nav-item" onclick="sw('trangchu');setTimeout(function(){document.getElementById('sc-section').scrollIntoView({behavior:'smooth'})},200);closeNav()"><i class="fa-brands fa-soundcloud"></i> Tìm Nhạc</button>
  <button class="nav-item" onclick="sw('trangchu');setTimeout(function(){document.getElementById('getkey-section').scrollIntoView({behavior:'smooth'})},200);closeNav()"><i class="fa-solid fa-key"></i> Lấy Key</button>
  <button class="nav-item" onclick="sw('checkkey');closeNav()"><i class="fa-solid fa-search"></i> Tra Cứu Key</button>
  <div class="nav-divider"></div>
  <button class="nav-item" onclick="showLogin();closeNav()"><i class="fa-solid fa-user-shield"></i> Admin Login</button>
  {% endif %}
</div>

{% if session.get('is_admin') %}
<div class="vip-badge"><i class="fa-solid fa-crown"></i> ADMIN VĂN KHÁNH</div>
{% else %}
<button class="admin-login-btn" onclick="showLogin()"><i class="fa-solid fa-user-shield"></i> Admin</button>
{% endif %}

<!-- MAIN PANEL -->
<div class="panel">
  <div class="panel-body">
"""

HTML_P3 = """
<!-- ========== TAB: TRANGCHU (User homepage) ========== -->
<div class="tab active" id="tab-trangchu">

  <!-- HERO -->
  <div style="text-align:center;padding:22px 0 10px;">
    <div style="display:inline-flex;align-items:center;justify-content:center;width:70px;height:70px;background:var(--grad);border-radius:20px;font-size:1.8rem;color:#fff;box-shadow:0 10px 32px rgba(99,102,241,0.4);margin-bottom:14px;">
      <i class="fa-solid fa-key"></i>
    </div>
    <div style="font-family:'Orbitron',sans-serif;font-size:1.1rem;font-weight:900;background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:2px;margin-bottom:4px;">VĂN KHÁNH SERVER</div>
    <div style="font-size:0.78rem;color:var(--text2);font-weight:600;">Premium Key Manager — MLBB Game Tools</div>
  </div>

  <!-- MUSIC PLAYER -->
  <div class="music-player-card">
    <div class="dj-header">
      <i class="fa-solid fa-music" style="color:var(--primary);"></i>
      <span class="dj-header-title">DJ MUSIC</span>
      <div class="dj-eq-bars">
        <div class="dj-eq-bar" id="eq1" style="height:6px;"></div>
        <div class="dj-eq-bar" id="eq2" style="height:12px;"></div>
        <div class="dj-eq-bar" id="eq3" style="height:9px;"></div>
        <div class="dj-eq-bar" id="eq4" style="height:15px;"></div>
        <div class="dj-eq-bar" id="eq5" style="height:7px;"></div>
      </div>
    </div>
    <div class="dj-tracks">
      <div class="dj-track-btn playing" id="trk0" onclick="switchTrack(0)">
        <div class="dt-num">01</div>
        <div class="dt-name">Track 1</div>
      </div>
      <div class="dj-track-btn" id="trk1" onclick="switchTrack(1)">
        <div class="dt-num">02</div>
        <div class="dt-name">nhac2.mp3</div>
      </div>
      <div class="dj-track-btn" id="trk2" onclick="switchTrack(2)">
        <div class="dt-num">03</div>
        <div class="dt-name">nhac3.mp3</div>
      </div>
    </div>
    <div class="dj-main">
      <div class="vinyl" id="vinylDisc">
        <div class="vinyl-c"><i class="fa-solid fa-circle-dot" style="font-size:0.55rem;color:#fff;"></i></div>
      </div>
      <img class="dj-cover-sm" id="djCoverSm" src="" alt="">
      <div class="dj-info">
        <div class="music-title-text" id="musicTitle">nhac.mp3</div>
        <div class="music-status-text" id="musicStatus"><i class="fa-solid fa-pause"></i> Tạm dừng</div>
      </div>
    </div>
    <div class="dj-controls">
      <button class="ctrl-btn" onclick="prevTrack()"><i class="fa-solid fa-backward-step"></i></button>
      <button class="play-btn" id="playBtn" onclick="togglePlay()"><i class="fa-solid fa-play" id="playIcon"></i></button>
      <button class="ctrl-btn" onclick="nextTrack()"><i class="fa-solid fa-forward-step"></i></button>
      <button class="ctrl-btn" id="volBtn" onclick="toggleMute()" title="Tắt/bật tiếng"><i class="fa-solid fa-volume-high" id="volIcon"></i></button>
    </div>
    <input type="range" class="seek-bar" id="seekBar" value="0" min="0" max="100" step="0.1" oninput="onSeek()">
    <div class="seek-times"><span id="curTime">0:00</span><span id="totTime">0:00</span></div>
    <audio id="bgAudio"></audio>
  </div>

  <!-- SOUNDCLOUD SEARCH -->
  <div class="sc-search-card" id="sc-section">
    <div class="card-title"><i class="fa-brands fa-soundcloud"></i> TÌM NHẠC SOUNDCLOUD</div>
    <div class="sc-search-row">
      <input class="sc-input" id="scQuery" type="text" placeholder="Nhập tên bài hát..." onkeydown="if(event.key==='Enter')scSearch()">
      <button class="sc-btn" id="scBtn" onclick="scSearch()"><i class="fa-solid fa-magnifying-glass"></i> Tìm</button>
    </div>
    <div class="sc-loading" id="scLoading">
      <div class="sc-loading-spin"></div>
      <div style="font-size:0.78rem;color:var(--muted);font-weight:700;">Đang tìm kiếm...</div>
    </div>
    <div class="sc-results" id="scResults">
      <div id="scSongList"></div>
      <div class="sc-listen-row">
        <button class="sc-listen-btn" id="scListenBtn" onclick="scListen()" disabled><i class="fa-solid fa-play"></i> Nghe Bài Này</button>
      </div>
    </div>
    <div id="scEmpty" style="display:none;text-align:center;padding:16px 0;color:var(--muted);font-size:0.82rem;font-weight:700;"><i class="fa-solid fa-face-meh" style="font-size:1.4rem;display:block;margin-bottom:8px;opacity:0.35;"></i>Không tìm thấy bài hát</div>
    <div id="scError" style="display:none;text-align:center;padding:12px;background:rgba(239,68,68,0.07);border-radius:12px;color:var(--danger);font-size:0.8rem;font-weight:700;"></div>
  </div>

  <!-- GET KEY FREE -->
  <div class="getkey-card" id="getkey-section">
    <div class="getkey-icon"><i class="fa-solid fa-key"></i></div>
    <div class="getkey-title">LẤY KEY MIỄN PHÍ</div>
    <div class="getkey-sub">Key miễn phí dành cho game thủ. Hoàn thành bước xác minh đơn giản để nhận key.</div>
    <div class="getkey-info-pills">
      <div class="getkey-pill"><i class="fa-solid fa-clock"></i> 12 giờ sử dụng</div>
      <div class="getkey-pill"><i class="fa-solid fa-mobile-screen-button"></i> 1 thiết bị</div>
      <div class="getkey-pill"><i class="fa-solid fa-rotate"></i> Tối đa 3 lần/ngày</div>
    </div>
    <div id="gkBtn">
      <button class="btn btn-primary" onclick="doGetKey()"><i class="fa-solid fa-gift"></i> NHẬN KEY NGAY</button>
    </div>
    <div id="gkSpinner" style="display:none;text-align:center;padding:16px 0;"><div class="spinner" style="margin:auto;"></div></div>
    <div id="gkLink" style="display:none;">
      <div class="free-link-box">
        <div class="free-link-label">Link xác minh (bấm mở trong tab mới)</div>
        <input class="free-link-input" id="gkLinkInput" readonly onclick="this.select()">
        <div style="display:flex;gap:8px;">
          <button class="btn btn-primary" onclick="window.open(document.getElementById('gkLinkInput').value,'_blank')" style="flex:1;margin-top:0;padding:9px;font-size:0.8rem;"><i class="fa-solid fa-arrow-up-right-from-square"></i> Mở Link</button>
          <button class="btn btn-outline" onclick="copyText(document.getElementById('gkLinkInput').value)" style="flex:1;padding:9px;font-size:0.8rem;"><i class="fa-solid fa-copy"></i> Sao Chép</button>
        </div>
        <div style="margin-top:10px;font-size:0.75rem;color:var(--text2);line-height:1.65;"><i class="fa-solid fa-circle-info" style="color:var(--primary);margin-right:5px;"></i>Sau khi hoàn thành xác minh, key sẽ tự hiện tại link đã mở.</div>
      </div>
    </div>
    <div id="gkErr" style="display:none;margin-top:12px;padding:12px;background:rgba(239,68,68,0.07);border-radius:12px;color:var(--danger);font-size:0.82rem;font-weight:700;text-align:center;"></div>
  </div>

  <!-- SOCIAL LINKS -->
  <div class="card">
    <div class="card-title"><i class="fa-solid fa-share-nodes"></i> KẾT NỐI VỚI ADMIN</div>
    <a class="social-btn social-tg" href="https://t.me/vkhanh3010" target="_blank">
      <div class="s-icon"><i class="fa-brands fa-telegram"></i></div>
      <div class="s-text"><span class="s-label">Telegram</span><span class="s-name">@vkhanh3010</span></div>
      <span class="s-arrow"><i class="fa-solid fa-chevron-right"></i></span>
    </a>
    <a class="social-btn social-tt" href="https://tiktok.com/@midu.c2" target="_blank">
      <div class="s-icon"><i class="fa-brands fa-tiktok"></i></div>
      <div class="s-text"><span class="s-label">TikTok</span><span class="s-name">@midu.c2</span></div>
      <span class="s-arrow"><i class="fa-solid fa-chevron-right"></i></span>
    </a>
    <a class="social-btn social-yt" href="https://youtube.com/@dokimodsgame" target="_blank">
      <div class="s-icon"><i class="fa-brands fa-youtube"></i></div>
      <div class="s-text"><span class="s-label">YouTube</span><span class="s-name">@dokimodsgame</span></div>
      <span class="s-arrow"><i class="fa-solid fa-chevron-right"></i></span>
    </a>
    <a class="social-btn social-fb" href="https://www.facebook.com/sharer/sharer.php?u=https://vkhanh.onrender.com" target="_blank">
      <div class="s-icon"><i class="fa-brands fa-facebook-f"></i></div>
      <div class="s-text"><span class="s-label">Facebook</span><span class="s-name">Chia sẻ Server</span></div>
      <span class="s-arrow"><i class="fa-solid fa-chevron-right"></i></span>
    </a>
  </div>

</div><!-- end tab-trangchu -->

<!-- ========== TAB: CHECK KEY (available without login) ========== -->
<div class="tab" id="tab-checkkey">
  <div class="section-header"><div class="section-header-title">Kiểm Tra Key</div></div>
  <div class="card">
    <div class="card-title"><i class="fa-solid fa-shield-halved"></i> TRA CỨU THÔNG TIN KEY</div>
    <div class="fg">
      <label>Nhập Key</label>
      <div class="key-search-wrap">
        <input type="text" id="ck_key" placeholder="ABCD-EFGH-IJKL-MNOP">
      </div>
    </div>
    <button class="btn btn-primary" onclick="doCheckKey()"><i class="fa-solid fa-magnifying-glass"></i> KIỂM TRA</button>
    <div id="ck_result" style="display:none;margin-top:14px;"></div>
  </div>
</div>

{% if session.get('is_admin') %}

<!-- ========== TAB: TẠO KHÓA ========== -->
<div class="tab" id="tab-taokhoa">
  <div class="section-header"><div class="section-header-title">Tạo Khóa Mới</div></div>
  <div class="card">
    <div class="card-title"><i class="fa-solid fa-plus-circle"></i> TẠO KEY MỚI</div>
    <div class="fg"><label>Thời hạn</label>
      <select id="tk_duration" onchange="updateExpiry()">
        <option value="3600">1 giờ</option><option value="10800">3 giờ</option>
        <option value="21600">6 giờ</option><option value="43200">12 giờ</option>
        <option value="86400" selected>1 ngày</option><option value="259200">3 ngày</option>
        <option value="604800">7 ngày</option><option value="1296000">15 ngày</option>
        <option value="2592000">30 ngày</option><option value="7776000">3 tháng</option>
        <option value="15552000">6 tháng</option><option value="31536000">1 năm</option>
        <option value="315360000">Vĩnh viễn</option>
      </select>
    </div>
    <div class="fg"><label>Hết hạn (dự kiến)</label><input type="text" id="tk_expiry_preview" readonly style="color:var(--primary);font-weight:800;"></div>
    <div class="fg"><label>Số thiết bị tối đa</label><input type="number" id="tk_maxdev" value="1" min="1" max="99"></div>
    <div class="fg"><label>Ghi chú (tuỳ chọn)</label><input type="text" id="tk_note" placeholder="Ghi chú cho key này..."></div>
    <div class="fg"><label>Số lượng key</label><input type="number" id="tk_count" value="1" min="1" max="50"></div>
    <div class="fg"><label>Loại key</label>
      <div class="radio-row">
        <label class="radio-opt"><input type="radio" name="tk_type" value="premium" checked> <span>Premium</span></label>
        <label class="radio-opt"><input type="radio" name="tk_type" value="vip"> <span>VIP</span></label>
      </div>
    </div>
    <button class="btn btn-primary" onclick="doCreateKey()"><i class="fa-solid fa-key"></i> TẠO KEY</button>
    <div id="tk_result" style="margin-top:14px;display:none;"></div>
  </div>
</div>

<!-- ========== TAB: DATABASE ========== -->
<div class="tab" id="tab-database">
  <div class="section-header"><div class="section-header-title">Quản Lý Keys</div></div>
  <div class="card">
    <div class="card-title"><i class="fa-solid fa-database"></i> DANH SÁCH KEYS</div>
    <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
      <input type="text" id="db_filter" placeholder="Lọc key..." style="flex:1;padding:9px 13px;background:var(--card);border:1.5px solid var(--border);border-radius:11px;color:var(--text);font-size:0.84rem;min-width:120px;font-family:'Nunito',sans-serif;" oninput="renderDbTable()" onfocus="this.style.borderColor='var(--primary)'" onblur="this.style.borderColor='var(--border)'">
      <button class="btn btn-primary" onclick="loadDatabase()" style="width:auto;margin-top:0;padding:9px 15px;font-size:0.82rem;white-space:nowrap;"><i class="fa-solid fa-rotate"></i> Tải lại</button>
    </div>
    <div class="tbl-wrap">
      <table id="dbTable">
        <thead><tr>
          <th>Key</th><th>Loại</th><th>Hết hạn</th><th>Thiết bị</th><th>Trạng thái</th><th>Thao tác</th>
        </tr></thead>
        <tbody id="dbBody"><tr><td colspan="6" style="text-align:center;color:var(--muted);padding:24px;">Nhấn "Tải lại" để xem dữ liệu</td></tr></tbody>
      </table>
    </div>
    <div id="db_page_info" style="text-align:center;font-size:0.72rem;color:var(--muted);margin-top:8px;font-weight:700;"></div>
  </div>
</div>

<!-- ========== TAB: KEY FREE ========== -->
<div class="tab" id="tab-keyfree">
  <div class="section-header"><div class="section-header-title">Key Free</div></div>
  <div class="card">
    <div class="card-title"><i class="fa-solid fa-gift"></i> DANH SÁCH KEY FREE</div>
    <button class="btn btn-primary" onclick="loadFreeKeys()" style="margin-bottom:14px;"><i class="fa-solid fa-rotate"></i> Tải danh sách key free</button>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>Key</th><th>IP nhận</th><th>Thời gian</th><th>Hết hạn</th><th>Thao tác</th></tr></thead>
        <tbody id="freeKeyBody"><tr><td colspan="5" style="text-align:center;color:var(--muted);padding:22px;">Nhấn tải để xem</td></tr></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ========== TAB: KEYSTATS ========== -->
<div class="tab" id="tab-keystats">
  <div class="section-header"><div class="section-header-title">Thống Kê Key</div></div>
  <div id="statsCards" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px;"></div>
  <div class="card">
    <div class="card-title"><i class="fa-solid fa-clock-rotate-left"></i> LỊCH SỬ TẠO KEY</div>
    <div class="tbl-wrap"><table><thead><tr><th>Key</th><th>Loại</th><th>Tạo lúc</th><th>Hết hạn</th></tr></thead><tbody id="histBody"></tbody></table></div>
  </div>
  <button class="btn btn-primary" onclick="loadStats()"><i class="fa-solid fa-chart-bar"></i> TẢI THỐNG KÊ</button>
</div>

<!-- ========== TAB: QUYENRIENGTU (Security) ========== -->
<div class="tab" id="tab-quyenriengtu">
  <div class="section-header"><div class="section-header-title">Bảo Mật</div></div>
  <div class="change-pass-card">
    <div class="change-pass-icon"><i class="fa-solid fa-key"></i></div>
    <div class="change-pass-title">ĐỔI MẬT KHẨU ADMIN</div>
    <div class="change-pass-sub">Mật khẩu mới có hiệu lực ngay lập tức</div>
    <div class="change-pass-warn" style="margin-top:16px;">
      <i class="fa-solid fa-circle-check" style="color:#16a34a;margin-top:1px;"></i>
      <span>Mật khẩu hiện tại và mật khẩu mới phải khác nhau. Độ dài tối thiểu 6 ký tự.</span>
    </div>
    <div class="fg"><label>Mật khẩu hiện tại</label><div class="input-with-icon"><i class="fa-solid fa-lock"></i><input type="password" id="cp_old" placeholder="Mật khẩu hiện tại"></div></div>
    <div class="fg"><label>Mật khẩu mới</label><div class="input-with-icon"><i class="fa-solid fa-key"></i><input type="password" id="cp_new" placeholder="Mật khẩu mới (tối thiểu 6 ký tự)"></div></div>
    <div class="fg"><label>Xác nhận mật khẩu mới</label><div class="input-with-icon"><i class="fa-solid fa-check-double"></i><input type="password" id="cp_confirm" placeholder="Nhập lại mật khẩu mới"></div></div>
    <button class="btn btn-primary" onclick="doChangePass()"><i class="fa-solid fa-floppy-disk"></i> LƯU MẬT KHẨU MỚI</button>
    <div id="cp_result" style="margin-top:12px;display:none;"></div>
  </div>
</div>

<!-- ========== TAB: DEVICEREVIEW ========== -->
<div class="tab" id="tab-devicereview">
  <div class="section-header"><div class="section-header-title">Duyệt Thiết Bị</div></div>
  <div class="card">
    <div class="card-title"><i class="fa-solid fa-clock"></i> CHỜ DUYỆT</div>
    <button class="btn btn-primary" onclick="loadDeviceRequests()" style="margin-bottom:14px;"><i class="fa-solid fa-rotate"></i> Tải danh sách</button>
    <div id="devReqList"><div class="dev-empty"><i class="fa-solid fa-inbox"></i>Chưa có thiết bị chờ duyệt</div></div>
  </div>
  <div class="card">
    <div class="card-title"><i class="fa-solid fa-circle-check"></i> ĐÃ DUYỆT</div>
    <div id="devApvList"><div class="dev-empty"><i class="fa-solid fa-check-double"></i>Chưa có thiết bị được duyệt</div></div>
  </div>
</div>

<!-- ========== TAB: CHECK IP ========== -->
<div class="tab" id="tab-checkip">
  <div class="section-header"><div class="section-header-title">Check IP</div></div>
  <div class="card">
    <div class="card-title"><i class="fa-solid fa-globe"></i> TRA CỨU THÔNG TIN IP</div>
    <div class="fg"><label>Địa chỉ IP</label><input type="text" id="ci_ip" placeholder="Ví dụ: 1.2.3.4"></div>
    <button class="btn btn-primary" onclick="doCheckIp()"><i class="fa-solid fa-magnifying-glass"></i> KIỂM TRA IP</button>
    <div id="ci_result" style="display:none;margin-top:14px;"></div>
  </div>
</div>

<!-- ========== TAB: GETKEY CONFIG ========== -->
<div class="tab" id="tab-getkeyconfig">
  <div class="section-header"><div class="section-header-title">GetKey Config</div></div>
  <div class="card">
    <div class="card-title"><i class="fa-solid fa-sliders"></i> CẤU HÌNH KEY FREE</div>
    <div class="fg"><label>Thời hạn key (giờ)</label><input type="number" id="gkc_duration" value="12" min="1" max="720" placeholder="12"></div>
    <div class="fg"><label>Số thiết bị tối đa</label><input type="number" id="gkc_maxdev" value="1" min="1" max="10" placeholder="1"></div>
    <div class="fg"><label>Số lần lấy tối đa mỗi IP/ngày</label><input type="number" id="gkc_ratelimit" value="3" min="1" max="20" placeholder="3"></div>
    <button class="btn btn-primary" onclick="saveGetkeyConfig()"><i class="fa-solid fa-floppy-disk"></i> LƯU CẤU HÌNH</button>
    <div id="gkc_result" style="display:none;margin-top:12px;"></div>
    <div style="margin-top:16px;">
      <button class="btn btn-outline" onclick="loadGetkeyConfig()" style="width:100%;"><i class="fa-solid fa-rotate"></i> Tải cấu hình hiện tại</button>
    </div>
  </div>
</div>

<!-- ========== TAB: WEB LOG ========== -->
<div class="tab" id="tab-weblog">
  <div class="section-header"><div class="section-header-title">Web Log</div></div>
  <div class="card">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
      <div class="card-title" style="margin-bottom:0;"><i class="fa-solid fa-terminal"></i> NHẬT KÝ TRUY CẬP</div>
      <button class="btn btn-outline" onclick="loadWebLog()" style="padding:7px 14px;font-size:0.76rem;"><i class="fa-solid fa-rotate"></i> Tải lại</button>
    </div>
    <div id="webLogList"><div style="text-align:center;padding:24px;color:var(--muted);font-size:0.8rem;"><i class="fa-solid fa-terminal" style="font-size:1.4rem;display:block;margin-bottom:8px;opacity:0.3;"></i>Nhấn "Tải lại" để xem log</div></div>
  </div>
</div>

<!-- ========== TAB: SETTINGS / API DOCS ========== -->
<div class="tab" id="tab-settings">
  <div class="section-header"><div class="section-header-title">API Docs</div></div>
  <div class="ep-outer">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
      <span class="ep-badge-post">POST</span>
      <span class="ep-section-name">TẠO KEY</span>
    </div>
    <div class="ep-section-desc">Tạo key mới thông qua API. Yêu cầu xác thực admin.</div>
    <div class="ep-card">
      <div class="ep-path">/api/create_key</div>
      <div class="ep-url-row" style="margin-top:8px;">
        <span class="ep-url-text" id="ep_create">Đang tải...</span>
        <button class="ep-copy-btn" onclick="copyText(document.getElementById('ep_create').innerText)"><i class="fa-solid fa-copy"></i></button>
      </div>
      <div class="ep-body-box">duration: 86400<br>max_devices: 1<br>note: test<br>count: 1<br>key_type: premium</div>
    </div>
  </div>
  <div class="ep-outer">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
      <span class="ep-badge-post" style="background:rgba(59,130,246,0.15);color:#1d4ed8;border-color:rgba(59,130,246,0.4);">GET</span>
      <span class="ep-section-name" style="color:#1d4ed8;">KIỂM TRA KEY</span>
    </div>
    <div class="ep-section-desc">Kiểm tra thông tin và trạng thái key.</div>
    <div class="ep-card">
      <div class="ep-path">/api/check_key?key=XXXX</div>
      <div class="ep-url-row" style="margin-top:8px;">
        <span class="ep-url-text" id="ep_check">Đang tải...</span>
        <button class="ep-copy-btn" onclick="copyText(document.getElementById('ep_check').innerText)"><i class="fa-solid fa-copy"></i></button>
      </div>
    </div>
  </div>
  <div class="ep-outer">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
      <span class="ep-badge-post">POST</span>
      <span class="ep-section-name">XÁC THỰC THIẾT BỊ</span>
    </div>
    <div class="ep-section-desc">Đăng ký/xác thực thiết bị với key.</div>
    <div class="ep-card">
      <div class="ep-path">/api/validate</div>
      <div class="ep-url-row" style="margin-top:8px;">
        <span class="ep-url-text" id="ep_validate">Đang tải...</span>
        <button class="ep-copy-btn" onclick="copyText(document.getElementById('ep_validate').innerText)"><i class="fa-solid fa-copy"></i></button>
      </div>
      <div class="ep-body-box">key: YOUR_KEY<br>device_id: DEVICE_ID</div>
    </div>
  </div>
</div>

{% endif %}
"""

HTML_P5 = """
  </div><!-- end panel-body -->
</div><!-- end panel -->

<script>
// =============================================
// UTILS
// =============================================
var BASE = window.location.origin;
function $(id){return document.getElementById(id);}
function fmt(s){return s===undefined?'—':s;}

function toast(ok, msg){
  var ov=$('toast-overlay'),ic=$('toast-icon'),ii=$('toast-i');
  ic.className='toast-icon-wrap '+(ok?'toast-success':'toast-error');
  ii.className='fa-solid '+(ok?'fa-check':'fa-xmark');
  ov.classList.remove('toast-fade-out');
  ov.classList.add('show');
  setTimeout(function(){
    ic.classList.add('toast-fade-out');
    setTimeout(function(){ov.classList.remove('show');ic.classList.remove('toast-fade-out');},400);
  },1800);
}

function copyText(t){
  if(!t||t==='Đang tải...')return;
  navigator.clipboard.writeText(t).then(function(){toast(true);}).catch(function(){
    var a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();document.execCommand('copy');document.body.removeChild(a);toast(true);
  });
}

function showLoad(){$('loadOverlay').style.display='flex';}
function hideLoad(){$('loadOverlay').style.display='none';}

function showLogin(){$('loginOverlay').classList.add('show');}
function closeLogin(){$('loginOverlay').classList.remove('show');}

function closeNav(){
  $('navDrop').classList.remove('show');
  $('hbg').classList.remove('open');
}

function toggleMenu(){
  $('hbg').classList.toggle('open');
  $('navDrop').classList.toggle('show');
}

// Close nav when clicking outside
document.addEventListener('click', function(e){
  var nd=$('navDrop'),hb=$('hbg');
  if(nd && nd.classList.contains('show') && !nd.contains(e.target) && !hb.contains(e.target)){
    closeNav();
  }
});

// Tab switching
var curTab='trangchu';
function sw(name, closeMenu){
  if(curTab===name && !closeMenu)return;
  var old=$('tab-'+curTab);
  var nw=$('tab-'+name);
  if(!nw)return;
  if(old){old.classList.remove('active');}
  nw.classList.add('active');
  curTab=name;
  // Update nav active state
  document.querySelectorAll('.nav-item').forEach(function(el){
    el.classList.remove('active');
  });
  closeNav();
  // Load data for tab
  if(name==='database')loadDatabase();
  if(name==='weblog')loadWebLog();
  if(name==='keystats')loadStats();
  if(name==='keyfree')loadFreeKeys();
  if(name==='devicereview')loadDeviceRequests();
  if(name==='getkeyconfig')loadGetkeyConfig();
  if(name==='settings')loadApiUrls();
}

// =============================================
// LOGIN
// =============================================
$('loginForm').addEventListener('submit',function(e){
  e.preventDefault();
  var u=$('lu').value.trim(),p=$('lp').value.trim();
  if(!u||!p)return;
  $('loginErr').style.display='none';
  $('loginSpinner').style.display='block';
  $('loginForm').style.display='none';
  fetch('/login',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'user='+encodeURIComponent(u)+'&pass='+encodeURIComponent(p)})
  .then(function(r){return r.json();})
  .then(function(d){
    $('loginSpinner').style.display='none';
    $('loginForm').style.display='block';
    if(d.status==='success'||d.success){toast(true);setTimeout(function(){location.reload();},600);}
    else{$('loginErr').textContent=d.message||'Sai tài khoản hoặc mật khẩu';$('loginErr').style.display='block';}
  }).catch(function(){
    $('loginSpinner').style.display='none';
    $('loginForm').style.display='block';
    $('loginErr').textContent='Lỗi kết nối';$('loginErr').style.display='block';
  });
});

// =============================================
// MUSIC PLAYER
// =============================================
var tracks=['/nhac.mp3','/nhac2.mp3','/nhac3.mp3'];
var trackNames=['Nhạc 1','Nhạc 2','Nhạc 3'];
var curTrack=0;
var scTrack={url:null,title:null,cover:null};
var isScTrack=false;
var audio=$('bgAudio');
var isPlaying=false;

function fmtTime(s){
  if(isNaN(s)||!isFinite(s))return'0:00';
  var m=Math.floor(s/60),sc=Math.floor(s%60);
  return m+':'+(sc<10?'0':'')+sc;
}

function setEq(on){
  var delays=['0s','0.15s','0.3s','0.1s','0.25s'];
  for(var i=1;i<=5;i++){
    var b=$('eq'+i);
    if(on){b.classList.add('active');b.style.animationDelay=delays[i-1];b.style.animationDuration=(0.45+Math.random()*0.3)+'s';}
    else{b.classList.remove('active');}
  }
}

function updateTrackUI(){
  for(var i=0;i<3;i++){
    var b=$('trk'+i);
    if(b){b.classList.toggle('playing',!isScTrack && i===curTrack);}
  }
  var vn=$('vinylDisc'),cs=$('djCoverSm');
  if(isScTrack && scTrack.cover){
    cs.src=scTrack.cover; cs.style.display='block'; vn.style.display='none';
    $('musicTitle').textContent=scTrack.title||'SoundCloud Track';
  } else {
    cs.style.display='none'; vn.style.display='flex';
    $('musicTitle').textContent=trackNames[curTrack];
  }
}

function switchTrack(idx){
  isScTrack=false; curTrack=idx; isPlaying=false;
  audio.src=tracks[idx]; audio.load();
  $('playIcon').className='fa-solid fa-play';
  $('musicStatus').innerHTML='<i class="fa-solid fa-pause"></i> Tạm dừng';
  $('vinylDisc').classList.remove('spin');
  setEq(false);
  updateTrackUI();
}

function togglePlay(){
  if(audio.paused){
    audio.play().then(function(){
      isPlaying=true;
      $('playIcon').className='fa-solid fa-pause';
      $('musicStatus').innerHTML='<i class="fa-solid fa-play"></i> Đang phát';
      $('vinylDisc').classList.add('spin');
      setEq(true);
    }).catch(function(){});
  } else {
    audio.pause();
    isPlaying=false;
    $('playIcon').className='fa-solid fa-play';
    $('musicStatus').innerHTML='<i class="fa-solid fa-pause"></i> Tạm dừng';
    $('vinylDisc').classList.remove('spin');
    setEq(false);
  }
}

function prevTrack(){
  if(isScTrack){isScTrack=false;switchTrack(curTrack);return;}
  switchTrack((curTrack-1+3)%3);
}
function nextTrack(){
  if(isScTrack){isScTrack=false;switchTrack((curTrack+1)%3);return;}
  switchTrack((curTrack+1)%3);
}

var isMuted=false;
function toggleMute(){
  isMuted=!isMuted; audio.muted=isMuted;
  $('volIcon').className='fa-solid '+(isMuted?'fa-volume-xmark':'fa-volume-high');
}

function onSeek(){
  if(audio.duration)audio.currentTime=($('seekBar').value/100)*audio.duration;
}

audio.addEventListener('timeupdate',function(){
  if(!audio.duration)return;
  var p=(audio.currentTime/audio.duration)*100;
  $('seekBar').value=p;
  $('curTime').textContent=fmtTime(audio.currentTime);
  $('totTime').textContent=fmtTime(audio.duration);
});
audio.addEventListener('ended',function(){nextTrack();});
audio.addEventListener('loadedmetadata',function(){$('totTime').textContent=fmtTime(audio.duration);});

// Init first track
audio.src=tracks[0];

// =============================================
// SOUNDCLOUD SEARCH
// =============================================
var selectedSong=null;

function scSearch(){
  var q=$('scQuery').value.trim();
  if(!q)return;
  $('scBtn').disabled=true;
  $('scResults').style.display='none';
  $('scEmpty').style.display='none';
  $('scError').style.display='none';
  $('scLoading').style.display='block';
  selectedSong=null; $('scListenBtn').disabled=true;
  fetch('/api/search_music?q='+encodeURIComponent(q))
  .then(function(r){return r.json();})
  .then(function(d){
    $('scLoading').style.display='none';
    $('scBtn').disabled=false;
    if(d.status==='success' && d.songs && d.songs.length>0){
      $('scResults').style.display='block';
      renderSongList(d.songs);
    } else if(d.status==='success'){
      $('scEmpty').style.display='block';
    } else {
      $('scError').textContent=d.message||'Lỗi tìm kiếm';
      $('scError').style.display='block';
    }
  }).catch(function(e){
    $('scLoading').style.display='none';
    $('scBtn').disabled=false;
    $('scError').textContent='Lỗi kết nối: '+e.message;
    $('scError').style.display='block';
  });
}

function renderSongList(songs){
  var html='';
  songs.forEach(function(s,i){
    var cover=s.cover?('<img class="sc-cover" src="'+s.cover+'" alt="" onerror="this.hidden=true">'):('<div class="sc-cover-placeholder"><i class="fa-solid fa-music"></i></div>');
    html+='<div class="sc-song-card" id="sc_card_'+i+'" onclick="selectSong('+i+','+JSON.stringify(JSON.stringify(s))+')">'
    +cover
    +'<div class="sc-song-info"><div class="sc-song-title">'+s.title+'</div><div class="sc-song-meta"><i class="fa-brands fa-soundcloud"></i> SoundCloud</div></div>'
    +'<div class="sc-sel-indicator" id="sc_sel_'+i+'"><i class="fa-solid fa-check" style="font-size:0.65rem;"></i></div>'
    +'</div>';
  });
  $('scSongList').innerHTML=html;
}

function selectSong(idx, songJson){
  var s=JSON.parse(songJson);
  selectedSong=s;
  document.querySelectorAll('.sc-song-card').forEach(function(el,i){
    el.classList.toggle('selected',i===idx);
  });
  $('scListenBtn').disabled=false;
}

function scListen(){
  if(!selectedSong)return;
  $('scListenBtn').disabled=true;
  $('scListenBtn').innerHTML='<div class="spinner spinner-sm" style="border-top-color:#fff;border-color:rgba(255,255,255,0.3);"></div> Đang lấy link...';
  var fd=new FormData(); fd.append('url',selectedSong.url);
  fetch('/api/get_stream_url',{method:'POST',body:fd})
  .then(function(r){return r.json();})
  .then(function(d){
    $('scListenBtn').innerHTML='<i class="fa-solid fa-play"></i> Nghe Bài Này';
    $('scListenBtn').disabled=false;
    if(d.status==='success'){
      isScTrack=true;
      scTrack.url=d.stream_url;
      scTrack.title=d.title||selectedSong.title;
      scTrack.cover=d.cover||selectedSong.cover||'';
      audio.src=d.stream_url; audio.load();
      updateTrackUI();
      audio.play().then(function(){
        isPlaying=true;
        $('playIcon').className='fa-solid fa-pause';
        $('musicStatus').innerHTML='<i class="fa-solid fa-play"></i> Đang phát';
        $('vinylDisc').classList.add('spin');
        setEq(true);
        sw('trangchu');
        setTimeout(function(){$('bgAudio').scrollIntoView({behavior:'smooth',block:'center'});},400);
      }).catch(function(){});
    } else {
      toast(false); alert('Lỗi: '+(d.message||'Không lấy được stream URL'));
    }
  }).catch(function(e){
    $('scListenBtn').innerHTML='<i class="fa-solid fa-play"></i> Nghe Bài Này';
    $('scListenBtn').disabled=false;
    toast(false);
  });
}

// =============================================
// GET KEY FREE
// =============================================
function doGetKey(){
  $('gkBtn').style.display='none';
  $('gkSpinner').style.display='block';
  $('gkLink').style.display='none';
  $('gkErr').style.display='none';
  fetch('/api/getkey',{method:'POST'})
  .then(function(r){return r.json();})
  .then(function(d){
    $('gkSpinner').style.display='none';
    if(d.status==='success'&&d.link){
      $('gkLinkInput').value=d.link;
      $('gkLink').style.display='block';
    } else {
      $('gkErr').textContent=d.message||'Lỗi tạo link';
      $('gkErr').style.display='block';
      $('gkBtn').style.display='block';
    }
  }).catch(function(){
    $('gkSpinner').style.display='none';
    $('gkErr').textContent='Lỗi kết nối';
    $('gkErr').style.display='block';
    $('gkBtn').style.display='block';
  });
}

// =============================================
// CHECK KEY (public)
// =============================================
function doCheckKey(){
  var k=$('ck_key').value.trim();
  if(!k){return;}
  showLoad();
  fetch('/api/check_key?key='+encodeURIComponent(k))
  .then(function(r){return r.json();})
  .then(function(d){
    hideLoad();
    var box=$('ck_result');
    box.style.display='block';
    if(d.status==='success'){
      var info=d.info||d.data||d;
      var exp=info.expiry_date||info.expiry||info.expires||'—';
      var maxd=info.max_devices||info.max_dev||'—';
      var usedc=info.devices_count!==undefined?info.devices_count:(info.used_devices||'—');
      var typ=info.key_type||info.type||'—';
      var valid=(d.valid||d.is_valid)?'<span class="badge badge-yes"><i class="fa-solid fa-check"></i> Còn hạn</span>':'<span class="badge badge-no"><i class="fa-solid fa-xmark"></i> Hết hạn</span>';
      box.innerHTML='<div class="result-box"><div class="result-title">Thông tin Key</div>'
        +'<div class="info-row"><span class="info-label">Key</span><span class="info-val key-val" style="font-size:0.7rem;">'+k+'</span></div>'
        +'<div class="info-row"><span class="info-label">Trạng thái</span><span class="info-val">'+valid+'</span></div>'
        +'<div class="info-row"><span class="info-label">Loại</span><span class="info-val">'+fmt(typ)+'</span></div>'
        +'<div class="info-row"><span class="info-label">Hết hạn</span><span class="info-val">'+fmt(exp)+'</span></div>'
        +'<div class="info-row"><span class="info-label">Thiết bị</span><span class="info-val">'+fmt(usedc)+' / '+fmt(maxd)+'</span></div>'
        +'</div>';
    } else {
      box.innerHTML='<div style="background:rgba(239,68,68,0.07);border:1px solid rgba(239,68,68,0.2);border-radius:12px;padding:14px;color:var(--danger);font-size:0.84rem;font-weight:700;text-align:center;"><i class="fa-solid fa-circle-xmark" style="font-size:1.3rem;display:block;margin-bottom:8px;"></i>'+(d.message||'Key không tồn tại hoặc không hợp lệ')+'</div>';
    }
  }).catch(function(){hideLoad();});
}

{% if session.get('is_admin') %}
// =============================================
// DATABASE TAB
// =============================================
var dbAll=[];
function loadDatabase(){
  showLoad();
  fetch('/api/list_keys')
  .then(function(r){return r.json();})
  .then(function(d){
    hideLoad();
    dbAll=d.keys||d.data||d||[];
    renderDbTable();
  }).catch(function(){hideLoad();});
}

var _dbKeyArr=[];
function renderDbTable(){
  var f=$('db_filter').value.trim().toLowerCase();
  var rows=dbAll.filter(function(k){
    return !f||(k.key||'').toLowerCase().includes(f)||(k.note||'').toLowerCase().includes(f)||(k.key_type||'').toLowerCase().includes(f);
  });
  _dbKeyArr=rows.map(function(k){return k.key;});
  var html='';
  rows.forEach(function(k,i){
    var valid=k.is_valid||k.valid;
    var badge=valid?'<span class="badge badge-yes">Hợp lệ</span>':'<span class="badge badge-no">Hết hạn</span>';
    html+='<tr>'
      +'<td><span class="key-val" onclick="copyText(_dbKeyArr['+i+'])" style="cursor:pointer;" title="Click để copy">'+k.key+'</span></td>'
      +'<td><span class="badge badge-warn">'+fmt(k.key_type||k.type)+'</span></td>'
      +'<td style="font-size:0.73rem;color:var(--text2);">'+fmt(k.expiry_date||k.expiry)+'</td>'
      +'<td style="text-align:center;">'+(k.devices_count!==undefined?k.devices_count:fmt(k.used_devices))+' / '+fmt(k.max_devices||k.max_dev)+'</td>'
      +'<td>'+badge+'</td>'
      +'<td><div class="td-actions">'
      +'<button class="btn-sm btn-sm-warn" onclick="extendKeyPrompt(_dbKeyArr['+i+'])"><i class="fa-solid fa-clock"></i></button>'
      +'<button class="btn-sm btn-sm-red" onclick="deleteKey(_dbKeyArr['+i+'])"><i class="fa-solid fa-trash"></i></button>'
      +'</div></td>'
      +'</tr>';
  });
  $('dbBody').innerHTML=html||'<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:22px;">Không có key nào</td></tr>';
  $('db_page_info').textContent='Tổng: '+rows.length+' key'+(f?' (lọc từ '+dbAll.length+')':'');
}

function deleteKey(key){
  if(!confirm('Xóa key '+key+'?'))return;
  showLoad();
  fetch('/delete/'+encodeURIComponent(key))
  .then(function(r){return r.json();})
  .then(function(d){hideLoad();toast(d.status==='success');if(d.status==='success')loadDatabase();})
  .catch(function(){hideLoad();toast(false);});
}

function resetDevices(key){
  if(!confirm('Reset thiết bị cho key '+key+'?'))return;
  showLoad();
  fetch('/reset/'+encodeURIComponent(key))
  .then(function(r){return r.json();})
  .then(function(d){hideLoad();toast(d.status==='success');if(d.status==='success')loadDatabase();})
  .catch(function(){hideLoad();toast(false);});
}

function extendKeyPrompt(key){
  var h=prompt('Gia hạn thêm bao nhiêu giờ?','24');
  if(!h||isNaN(h))return;
  showLoad();
  var fd=new FormData(); fd.append('key',key); fd.append('hours',h);
  fetch('/api/extend_key',{method:'POST',body:fd})
  .then(function(r){return r.json();})
  .then(function(d){hideLoad();toast(d.status==='success');if(d.status==='success')loadDatabase();})
  .catch(function(){hideLoad();toast(false);});
}

// =============================================
// CREATE KEY
// =============================================
function updateExpiry(){
  var dur=parseInt($('tk_duration').value);
  var d=new Date(Date.now()+dur*1000);
  $('tk_expiry_preview').value=d.toLocaleString('vi-VN');
}
updateExpiry();

function doCreateKey(){
  var dur=$('tk_duration').value;
  var maxd=$('tk_maxdev').value;
  var note=$('tk_note').value;
  var cnt=$('tk_count').value;
  var typ=document.querySelector('input[name="tk_type"]:checked').value;
  showLoad();
  var fd=new FormData();
  fd.append('duration',dur); fd.append('max_devices',maxd); fd.append('note',note);
  fd.append('count',cnt); fd.append('key_type',typ);
  fetch('/api/create_key',{method:'POST',body:fd})
  .then(function(r){return r.json();})
  .then(function(d){
    hideLoad(); toast(d.status==='success');
    var box=$('tk_result');
    box.style.display='block';
    if(d.status==='success'){
      var keys=d.keys||d.key||[];
      if(!Array.isArray(keys))keys=[keys];
      var html='<div class="result-box"><div class="result-title"><i class="fa-solid fa-check-circle" style="color:var(--success);"></i> TẠO THÀNH CÔNG '+keys.length+' KEY</div>';
      keys.forEach(function(k){
        html+='<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);">'
          +'<span class="key-val">'+k+'</span>'
          +'<button class="btn-sm btn-sm-blue" onclick="copyText(this.previousElementSibling.textContent)"><i class="fa-solid fa-copy"></i> Sao chép</button>'
          +'</div>';
      });
      box.innerHTML=html+'</div>';
    } else {
      box.innerHTML='<div style="background:rgba(239,68,68,0.07);border:1px solid rgba(239,68,68,0.2);border-radius:12px;padding:12px;color:var(--danger);font-size:0.84rem;">'+( d.message||'Lỗi tạo key')+'</div>';
    }
  }).catch(function(){hideLoad();toast(false);});
}

// =============================================
// STATS
// =============================================
function loadStats(){
  showLoad();
  fetch('/api/key_stats')
  .then(function(r){return r.json();})
  .then(function(d){
    hideLoad();
    var sc=$('statsCards');
    var total=d.total||0,active=d.active||0,expired=d.expired||0,pending=d.pending||0;
    var devTotal=d.total_devices||0;
    var stats=[
      {label:'Tổng Keys',val:total,icon:'key',color:'var(--primary)'},
      {label:'Đã kích hoạt',val:active,icon:'check-circle',color:'var(--success)'},
      {label:'Hết hạn',val:expired,icon:'circle-xmark',color:'var(--danger)'},
      {label:'Chưa kích hoạt',val:pending,icon:'clock',color:'#f59e0b'},
    ];
    sc.innerHTML=stats.map(function(s){
      return '<div class="card" style="padding:16px;margin-bottom:0;">'
        +'<div style="font-size:1.6rem;color:'+s.color+';margin-bottom:6px;"><i class="fa-solid fa-'+s.icon+'"></i></div>'
        +'<div style="font-size:1.4rem;font-weight:900;color:var(--text);">'+s.val+'</div>'
        +'<div style="font-size:0.73rem;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">'+s.label+'</div>'
        +'</div>';
    }).join('');
    // Render recent keys as history
    if(d.keys){
      var rows=d.keys.slice(0,30).map(function(h){
        var badge='';
        if(h.status==='Đã kích hoạt')badge='<span class="badge badge-ok" style="font-size:0.6rem;">Active</span>';
        else if(h.status==='Hết hạn')badge='<span class="badge badge-err" style="font-size:0.6rem;">Hết hạn</span>';
        else badge='<span class="badge badge-warn" style="font-size:0.6rem;">Chưa KH</span>';
        return '<tr><td><span class="key-val">'+fmt(h.key)+'</span></td><td>'+badge+'</td><td style="font-size:0.72rem;">'+fmt(h.created_at_str||'—')+'</td><td style="font-size:0.72rem;">'+fmt(h.han_dung||'—')+'</td></tr>';
      }).join('');
      $('histBody').innerHTML=rows||'<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:18px;">Không có dữ liệu</td></tr>';
    }
  }).catch(function(){hideLoad();});
}

// =============================================
// FREE KEYS
// =============================================
function loadFreeKeys(){
  showLoad();
  fetch('/api/list_free_keys')
  .then(function(r){return r.json();})
  .then(function(d){
    hideLoad();
    var keys=d.keys||d.data||[];
    var _fkArr=keys.map(function(x){return x.key;});
    var html=keys.map(function(k,i){
      return '<tr><td><span class="key-val" onclick="copyText(_fkArr['+i+'])" style="cursor:pointer;">'+k.key+'</span></td>'
        +'<td style="font-size:0.73rem;">'+fmt(k.ip)+'</td>'
        +'<td style="font-size:0.73rem;">'+fmt(k.created_at||k.time)+'</td>'
        +'<td style="font-size:0.73rem;">'+fmt(k.expiry_date||k.expiry)+'</td>'
        +'<td><button class="btn-sm btn-sm-red" onclick="deleteFreeKey(_fkArr['+i+'])"><i class="fa-solid fa-trash"></i></button></td>'
        +'</tr>';
    }).join('');
    $('freeKeyBody').innerHTML=html||'<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:22px;">Không có key free</td></tr>';
  }).catch(function(){hideLoad();});
}

function deleteFreeKey(key){
  if(!confirm('Xóa key '+key+'?'))return;
  showLoad();
  fetch('/delete/'+encodeURIComponent(key))
  .then(function(r){return r.json();})
  .then(function(d){hideLoad();toast(d.status==='success');if(d.status==='success')loadFreeKeys();})
  .catch(function(){hideLoad();toast(false);});
}

// =============================================
// CHANGE PASSWORD
// =============================================
function doChangePass(){
  var o=$('cp_old').value,n=$('cp_new').value,c=$('cp_confirm').value;
  if(!n||!c){alert('Vui lòng điền mật khẩu mới và xác nhận');return;}
  if(n!==c){alert('Mật khẩu mới không khớp');return;}
  if(n.length<6){alert('Mật khẩu mới phải dài ít nhất 6 ký tự');return;}
  // Get current admin username from session — send same username or ask admin to enter it
  var u=prompt('Nhập tài khoản admin hiện tại:','vkhanh');
  if(!u)return;
  showLoad();
  // Backend /api/change_admin accepts: u=new_user, p=new_pass (verifies via session)
  var fd=new FormData(); fd.append('u',u); fd.append('p',n);
  fetch('/api/change_admin',{method:'POST',body:fd})
  .then(function(r){return r.json();})
  .then(function(d){
    hideLoad(); toast(d.status==='success');
    var box=$('cp_result'); box.style.display='block';
    if(d.status==='success'){
      box.innerHTML='<div style="background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.25);border-radius:12px;padding:12px;color:#15803d;font-size:0.84rem;font-weight:700;"><i class="fa-solid fa-check"></i> Đổi mật khẩu thành công!</div>';
      $('cp_old').value=''; $('cp_new').value=''; $('cp_confirm').value='';
    } else {
      box.innerHTML='<div style="background:rgba(239,68,68,0.07);border:1px solid rgba(239,68,68,0.2);border-radius:12px;padding:12px;color:var(--danger);font-size:0.84rem;">'+(d.message||'Lỗi đổi mật khẩu')+'</div>';
    }
  }).catch(function(){hideLoad();toast(false);});
}

// =============================================
// DEVICE REVIEW
// =============================================
function loadDeviceRequests(){
  showLoad();
  Promise.all([
    fetch('/api/list_device_requests').then(function(r){return r.json();}),
    fetch('/api/list_approved_devices').then(function(r){return r.json();})
  ]).then(function(results){
    hideLoad();
    var pending=results[0]||[];
    var approved=results[1]||[];
    renderDevPending(Array.isArray(pending)?pending:(pending.requests||[]));
    renderDevApproved(Array.isArray(approved)?approved:(approved.devices||[]));
  }).catch(function(){hideLoad();});
}

var _devPendArr=[];
function renderDevPending(list){
  if(!list.length){$('devReqList').innerHTML='<div class="dev-empty"><i class="fa-solid fa-inbox"></i>Chưa có thiết bị chờ duyệt</div>';return;}
  _devPendArr=list.map(function(r){return {key:r.key,dev:r.device_id};});
  $('devReqList').innerHTML=list.map(function(r,i){
    return '<div class="dev-req-card">'
      +'<div class="dev-req-device"><i class="fa-solid fa-mobile-screen-button" style="color:var(--primary);margin-top:2px;flex-shrink:0;"></i>'+r.device_id+'</div>'
      +'<div class="dev-req-meta"><span><i class="fa-solid fa-key"></i> '+r.key+'</span><span><i class="fa-solid fa-clock"></i> '+fmt(r.time||r.created_at)+'</span></div>'
      +'<div class="dev-req-actions">'
      +'<span class="badge-pending"><i class="fa-solid fa-hourglass"></i> Chờ duyệt</span>'
      +'<button class="btn-sm btn-sm-green" onclick="approveDevice(_devPendArr['+i+'].key,_devPendArr['+i+'].dev)"><i class="fa-solid fa-check"></i> Duyệt</button>'
      +'<button class="btn-sm btn-sm-red" onclick="rejectDevice(_devPendArr['+i+'].key,_devPendArr['+i+'].dev)"><i class="fa-solid fa-ban"></i> Từ chối</button>'
      +'</div></div>';
  }).join('');
}

var _devApvArr=[];
function renderDevApproved(list){
  if(!list.length){$('devApvList').innerHTML='<div class="dev-empty"><i class="fa-solid fa-check-double"></i>Chưa có thiết bị được duyệt</div>';return;}
  _devApvArr=list.map(function(r){return {key:r.key,dev:r.device_id};});
  $('devApvList').innerHTML=list.map(function(r,i){
    return '<div class="apv-card">'
      +'<div class="apv-device">'+r.device_id+'</div>'
      +'<div class="apv-meta"><span><i class="fa-solid fa-key"></i> '+r.key+'</span><span><i class="fa-solid fa-clock"></i> '+fmt(r.approved_at||r.time)+'</span></div>'
      +'<div class="apv-actions">'
      +'<span class="badge-approved-dev"><i class="fa-solid fa-check"></i> Đã duyệt</span>'
      +'<button class="btn-sm btn-sm-red" onclick="revokeDevice(_devApvArr['+i+'].key,_devApvArr['+i+'].dev)"><i class="fa-solid fa-trash"></i> Thu hồi</button>'
      +'</div></div>';
  }).join('');
}

function approveDevice(rid,key,dev){
  showLoad();
  // approve with default 1 month duration
  var fd=new FormData(); fd.append('req_id',rid); fd.append('val','30'); fd.append('unit','ngày');
  fetch('/api/approve_device_request',{method:'POST',body:fd})
  .then(function(r){return r.json();})
  .then(function(d){hideLoad();toast(d.status==='success');if(d.status==='success')loadDeviceRequests();})
  .catch(function(){hideLoad();toast(false);});
}

function rejectDevice(rid){
  showLoad();
  var fd=new FormData(); fd.append('req_id',rid);
  fetch('/api/reject_device_request',{method:'POST',body:fd})
  .then(function(r){return r.json();})
  .then(function(d){hideLoad();toast(d.status==='success');if(d.status==='success')loadDeviceRequests();})
  .catch(function(){hideLoad();toast(false);});
}

function revokeDevice(deviceId){
  if(!confirm('Thu hồi quyền thiết bị này?'))return;
  showLoad();
  var fd=new FormData(); fd.append('device_id',deviceId);
  fetch('/api/delete_approved_device',{method:'POST',body:fd})
  .then(function(r){return r.json();})
  .then(function(d){hideLoad();toast(d.status==='success');if(d.status==='success')loadDeviceRequests();})
  .catch(function(){hideLoad();toast(false);});
}

// =============================================
// CHECK IP (Admin tab)
// =============================================
function doCheckIp(){
  var ip=$('ci_ip').value.trim();
  if(!ip)return;
  showLoad();
  fetch('https://ipapi.co/'+encodeURIComponent(ip)+'/json/')
  .then(function(r){return r.json();})
  .then(function(d){
    hideLoad();
    var box=$('ci_result'); box.style.display='block';
    if(!d.error){
      var html='<div class="check-ip-result" style="display:block;">'
        +'<div class="result-title"><i class="fa-solid fa-globe"></i> Thông Tin IP: '+ip+'</div>'
        +'<div class="ip-info-grid">';
      var fields=[
        ['Quốc gia',(d.country_name||'—')+' '+( d.country_code||'')],
        ['Thành phố',d.city||'—'],
        ['Vùng',d.region||'—'],
        ['ISP / Tổ chức',d.org||d.asn||'—'],
        ['Múi giờ',d.timezone||'—'],
        ['Tọa độ',(d.latitude&&d.longitude)?d.latitude+', '+d.longitude:'—']
      ];
      fields.forEach(function(f,i){
        html+='<div class="ip-info-cell"><div class="ic-label">'+f[0]+'</div><div class="ic-val">'+f[1]+'</div></div>';
      });
      box.innerHTML=html+'</div></div>';
    } else {
      box.innerHTML='<div style="background:rgba(239,68,68,0.07);border:1px solid rgba(239,68,68,0.2);border-radius:12px;padding:12px;color:var(--danger);font-size:0.84rem;">'+(d.reason||'Lỗi kiểm tra IP')+'</div>';
    }
  }).catch(function(){hideLoad();$('ci_result').style.display='block';$('ci_result').innerHTML='<div style="color:var(--danger);padding:10px;">Không thể kiểm tra IP này.</div>';});
}

// =============================================
// GETKEY CONFIG
// =============================================
function loadGetkeyConfig(){
  fetch('/admin/get_free_config')
  .then(function(r){return r.json();})
  .then(function(d){
    // backend returns: val (number), unit (tiếng/ngày), dev (devices)
    if(d.val)$('gkc_duration').value=d.val;
    if(d.dev)$('gkc_maxdev').value=d.dev;
    // unit shown in label
  }).catch(function(){});
}

function saveGetkeyConfig(){
  var dur=$('gkc_duration').value;
  var maxd=$('gkc_maxdev').value;
  // backend expects v=val, u=unit, d=devices
  showLoad();
  var fd=new FormData();
  fd.append('v',dur); fd.append('u','tiếng'); fd.append('d',maxd);
  fetch('/admin/free_setup',{method:'POST',body:fd})
  .then(function(r){return r.json();})
  .then(function(d){
    hideLoad(); toast(d.status==='success');
    var box=$('gkc_result'); box.style.display='block';
    if(d.status==='success'){
      box.innerHTML='<div style="background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.25);border-radius:12px;padding:12px;color:#15803d;font-weight:700;font-size:0.84rem;"><i class="fa-solid fa-check"></i> Lưu cấu hình thành công!</div>';
    } else {
      box.innerHTML='<div style="background:rgba(239,68,68,0.07);border:1px solid rgba(239,68,68,0.2);border-radius:12px;padding:12px;color:var(--danger);font-size:0.84rem;">'+(d.message||'Lỗi lưu cấu hình')+'</div>';
    }
  }).catch(function(){hideLoad();toast(false);});
}

// =============================================
// WEB LOG
// =============================================
function loadWebLog(){
  fetch('/api/web_log')
  .then(function(r){return r.json();})
  .then(function(logs){
    var html=logs.map(function(l){
      var mClass='log-method-'+(l.method==='POST'?'post':'get');
      var sClass=l.status>=400?'log-status-err':'log-status-ok';
      return '<div class="log-entry">'
        +'<span class="log-time">'+l.time+'</span>'
        +'<span class="log-method '+mClass+'">'+l.method+'</span>'
        +'<span class="log-path">'+l.path+'</span>'
        +'<span class="log-status '+sClass+'">'+l.status+'</span>'
        +'<span class="log-ip">'+l.ip+'</span>'
        +'</div>';
    }).join('');
    $('webLogList').innerHTML=html||'<div style="text-align:center;padding:24px;color:var(--muted);font-size:0.8rem;">Chưa có log</div>';
  }).catch(function(){});
}

// =============================================
// API URLS
// =============================================
function loadApiUrls(){
  var base=window.location.origin;
  var paths={ep_create:'/api/create_key',ep_check:'/api/check_key?key=XXXX',ep_validate:'/api/validate'};
  Object.keys(paths).forEach(function(id){
    var el=$(id); if(el)el.textContent=base+paths[id];
  });
}

{% endif %}
</script>
</body>
</html>
"""

FREE_KEY_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Nhận Key Free — Văn Khánh</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&family=Orbitron:wght@700;900&display=swap');
:root{--bg:#f0f2f7;--panel:#fff;--primary:#6366f1;--primary2:#8b5cf6;--grad:linear-gradient(135deg,#6366f1,#8b5cf6);--text:#1e293b;--text2:#475569;--muted:#94a3b8;--success:#22c55e;--danger:#ef4444;--border:rgba(0,0,0,0.08);--shadow:0 8px 32px rgba(99,102,241,0.12);}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
*:focus{outline:none;}
body{background:var(--bg);color:var(--text);font-family:'Nunito',sans-serif;min-height:100vh;display:flex;justify-content:center;align-items:flex-start;padding:20px 12px 60px;}
.wrap{width:min(480px,100%);padding-top:20px;}
.logo-row{display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:28px;}
.logo-ico{width:52px;height:52px;background:var(--grad);border-radius:15px;display:flex;align-items:center;justify-content:center;font-size:1.35rem;color:#fff;box-shadow:0 8px 26px rgba(99,102,241,0.35);}
.logo-text{font-family:'Orbitron',sans-serif;font-size:1rem;font-weight:900;background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:2px;}
.card{background:var(--panel);border:1px solid var(--border);border-radius:22px;padding:28px;box-shadow:var(--shadow);margin-bottom:16px;}
.card-title{font-family:'Orbitron',sans-serif;font-size:0.88rem;font-weight:900;background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:20px;display:flex;align-items:center;gap:8px;}
.card-title::before{content:'';display:inline-block;width:4px;height:18px;border-radius:2px;background:var(--grad);}
/* SCAN ANIMATION */
.scan-wrap{position:relative;width:180px;height:180px;margin:0 auto 24px;border-radius:50%;}
.scan-ring{position:absolute;inset:0;border-radius:50%;border:3px solid transparent;animation:ringPop 2.5s ease infinite;}
.scan-ring:nth-child(1){border-top-color:var(--primary);border-right-color:rgba(99,102,241,0.3);animation-delay:0s;}
.scan-ring:nth-child(2){inset:12px;border-bottom-color:var(--primary2);border-left-color:rgba(139,92,246,0.3);animation-delay:0.4s;animation-direction:reverse;}
.scan-ring:nth-child(3){inset:26px;border-top-color:rgba(99,102,241,0.5);animation-delay:0.2s;}
@keyframes ringPop{to{transform:rotate(360deg);}}
.scan-center{position:absolute;inset:40px;background:var(--grad);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:2rem;color:#fff;box-shadow:0 8px 30px rgba(99,102,241,0.4);}
/* PROGRESS */
.step-list{display:flex;flex-direction:column;gap:10px;margin-bottom:20px;}
.step-item{display:flex;align-items:center;gap:12px;padding:12px 14px;border-radius:14px;background:#f8fafc;border:1.5px solid transparent;transition:0.3s;}
.step-item.done{border-color:rgba(34,197,94,0.3);background:rgba(34,197,94,0.05);}
.step-item.active{border-color:rgba(99,102,241,0.4);background:rgba(99,102,241,0.06);}
.step-dot{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:0.8rem;flex-shrink:0;font-weight:900;}
.step-dot.waiting{background:#e2e8f0;color:#94a3b8;}
.step-dot.spinning{background:rgba(99,102,241,0.12);color:var(--primary);}
.step-dot.spinning i{animation:spin 1s linear infinite;}
@keyframes spin{to{transform:rotate(360deg);}}
.step-dot.ok{background:rgba(34,197,94,0.15);color:#15803d;}
.step-label{font-size:0.84rem;font-weight:700;color:var(--text2);}
.step-item.done .step-label{color:#15803d;}
.step-item.active .step-label{color:var(--primary);}
/* PROGRESS BAR */
.prog-track{width:100%;height:8px;background:#e2e8f0;border-radius:99px;overflow:hidden;margin-bottom:6px;}
.prog-fill{height:100%;background:var(--grad);border-radius:99px;transition:width 0.5s ease;}
.prog-pct{text-align:right;font-size:0.72rem;font-weight:800;font-family:'Orbitron',sans-serif;color:var(--primary);}
/* KEY RESULT */
.key-result{display:none;margin-top:6px;}
.key-display{background:rgba(99,102,241,0.06);border:2px dashed rgba(99,102,241,0.4);border-radius:18px;padding:22px;text-align:center;margin-bottom:16px;}
.key-label{font-size:0.72rem;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;}
.key-value{font-family:'Orbitron',sans-serif;font-size:1rem;font-weight:900;background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:1px;word-break:break-all;line-height:1.6;margin-bottom:12px;}
.copy-btn{display:inline-flex;align-items:center;gap:7px;padding:10px 22px;background:var(--grad);border:none;border-radius:12px;color:#fff;font-weight:800;font-size:0.85rem;cursor:pointer;transition:0.2s;font-family:'Nunito',sans-serif;box-shadow:0 4px 16px rgba(99,102,241,0.3);}
.copy-btn:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(99,102,241,0.4);}
.info-row{display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid var(--border);font-size:0.84rem;}
.info-row:last-child{border-bottom:none;}
.info-label{color:var(--text2);font-weight:600;}
.info-val{color:var(--text);font-weight:800;}
.error-box{background:rgba(239,68,68,0.07);border:1px solid rgba(239,68,68,0.2);border-radius:16px;padding:22px;text-align:center;display:none;}
.error-icon{font-size:2.2rem;color:var(--danger);margin-bottom:12px;}
.error-msg{font-size:0.88rem;font-weight:700;color:var(--danger);margin-bottom:8px;}
.error-sub{font-size:0.78rem;color:var(--text2);}
.back-btn{display:inline-flex;align-items:center;gap:7px;padding:10px 18px;background:rgba(99,102,241,0.1);border:1.5px solid rgba(99,102,241,0.3);border-radius:12px;color:var(--primary);font-weight:800;font-size:0.82rem;cursor:pointer;text-decoration:none;font-family:'Nunito',sans-serif;transition:0.2s;margin-top:12px;}
.back-btn:hover{background:rgba(99,102,241,0.18);}
</style>
</head>
<body>
<div class="wrap">
  <div class="logo-row">
    <div class="logo-ico"><i class="fa-solid fa-key"></i></div>
    <div class="logo-text">VĂN KHÁNH</div>
  </div>
  <div class="card">
    <div class="card-title"><i class="fa-solid fa-gift" style="-webkit-text-fill-color:initial;color:var(--primary);"></i> NHẬN KEY FREE</div>
    <div class="scan-wrap">
      <div class="scan-ring"></div><div class="scan-ring"></div><div class="scan-ring"></div>
      <div class="scan-center"><i class="fa-solid fa-shield-halved"></i></div>
    </div>
    <div class="step-list">
      <div class="step-item active" id="s1"><div class="step-dot spinning"><i class="fa-solid fa-spinner"></i></div><span class="step-label">Xác minh token bypass</span></div>
      <div class="step-item" id="s2"><div class="step-dot waiting"><i class="fa-solid fa-clock"></i></div><span class="step-label">Kiểm tra giới hạn IP</span></div>
      <div class="step-item" id="s3"><div class="step-dot waiting"><i class="fa-solid fa-cog"></i></div><span class="step-label">Tạo key miễn phí</span></div>
      <div class="step-item" id="s4"><div class="step-dot waiting"><i class="fa-solid fa-paper-plane"></i></div><span class="step-label">Kích hoạt & thông báo</span></div>
    </div>
    <div class="prog-track"><div class="prog-fill" id="pf" style="width:0%"></div></div>
    <div class="prog-pct" id="pp">0%</div>
    <div class="key-result" id="keyResult">
      <div class="key-display">
        <div class="key-label"><i class="fa-solid fa-key"></i> Key của bạn</div>
        <div class="key-value" id="keyVal">—</div>
        <button class="copy-btn" onclick="copyKey()"><i class="fa-solid fa-copy"></i> Sao chép key</button>
      </div>
      <div class="info-row"><span class="info-label">Hết hạn</span><span class="info-val" id="keyExp">—</span></div>
      <div class="info-row"><span class="info-label">Thiết bị tối đa</span><span class="info-val" id="keyDev">—</span></div>
      <div class="info-row"><span class="info-label">Loại key</span><span class="info-val"><span style="background:rgba(99,102,241,0.1);color:var(--primary);padding:3px 10px;border-radius:20px;font-size:0.75rem;font-weight:800;">FREE</span></span></div>
      <a href="/" class="back-btn"><i class="fa-solid fa-house"></i> Về trang chủ</a>
    </div>
    <div class="error-box" id="errBox">
      <div class="error-icon"><i class="fa-solid fa-circle-xmark"></i></div>
      <div class="error-msg" id="errMsg">Lỗi xác minh</div>
      <div class="error-sub" id="errSub">Vui lòng thử lại sau</div>
      <a href="/" class="back-btn"><i class="fa-solid fa-house"></i> Về trang chủ</a>
    </div>
  </div>
</div>
<script>
var token='{{ token }}';
var stepData=[
  {pct:20,delay:600},
  {pct:45,delay:900},
  {pct:70,delay:700},
  {pct:90,delay:500},
];
var si=0;
function setStep(n,ok){
  for(var i=1;i<=4;i++){
    var el=document.getElementById('s'+i);
    var dot=el.querySelector('.step-dot');
    var ic=el.querySelector('i');
    if(i<n){el.className='step-item done';dot.className='step-dot ok';ic.className='fa-solid fa-check';}
    else if(i===n){el.className='step-item active';dot.className='step-dot spinning';ic.className='fa-solid fa-spinner';}
    else{el.className='step-item';dot.className='step-dot waiting';}
  }
}
function setProgress(pct){
  document.getElementById('pf').style.width=pct+'%';
  document.getElementById('pp').textContent=pct+'%';
}
function animSteps(){
  if(si>=4){confirm_bypass();return;}
  setTimeout(function(){
    setStep(si+1,false);
    setProgress(stepData[si].pct);
    si++;
    animSteps();
  },stepData[si]?stepData[si].delay:600);
}
function confirm_bypass(){
  fetch('/api/confirm_bypass',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'token='+encodeURIComponent(token)})
  .then(function(r){return r.json();})
  .then(function(d){
    setProgress(100);
    for(var i=1;i<=4;i++){
      var el=document.getElementById('s'+i);
      var dot=el.querySelector('.step-dot');
      var ic=el.querySelector('i');
      el.className='step-item done'; dot.className='step-dot ok'; ic.className='fa-solid fa-check';
    }
    if(d.status==='success'&&d.key){
      document.getElementById('keyVal').textContent=d.key;
      document.getElementById('keyExp').textContent=d.expiry||d.expiry_date||'—';
      document.getElementById('keyDev').textContent=d.max_devices||'1';
      document.getElementById('keyResult').style.display='block';
    } else {
      document.getElementById('errMsg').textContent=d.message||'Xác minh thất bại';
      document.getElementById('errSub').textContent=d.sub||d.detail||'Vui lòng thử lại sau';
      document.getElementById('errBox').style.display='block';
    }
  }).catch(function(e){
    document.getElementById('errMsg').textContent='Lỗi kết nối máy chủ';
    document.getElementById('errSub').textContent=e.message;
    document.getElementById('errBox').style.display='block';
  });
}
function copyKey(){
  var k=document.getElementById('keyVal').textContent;
  navigator.clipboard.writeText(k).catch(function(){
    var a=document.createElement('textarea');a.value=k;document.body.appendChild(a);a.select();document.execCommand('copy');document.body.removeChild(a);
  });
}
setTimeout(animSteps,800);
</script>
</body>
</html>
"""

CHECK_IP_KEY_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Kiểm Tra IP Key — Văn Khánh</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&family=Orbitron:wght@700;900&display=swap');
:root{--bg:#f0f2f7;--panel:#fff;--primary:#6366f1;--primary2:#8b5cf6;--grad:linear-gradient(135deg,#6366f1,#8b5cf6);--text:#1e293b;--text2:#475569;--muted:#94a3b8;--success:#22c55e;--danger:#ef4444;--border:rgba(0,0,0,0.08);--shadow:0 8px 32px rgba(99,102,241,0.12);}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
*:focus{outline:none;}
body{background:var(--bg);color:var(--text);font-family:'Nunito',sans-serif;min-height:100vh;display:flex;justify-content:center;align-items:flex-start;padding:24px 12px 60px;}
.wrap{width:min(480px,100%);padding-top:16px;}
.logo-row{display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:26px;}
.logo-ico{width:52px;height:52px;background:var(--grad);border-radius:15px;display:flex;align-items:center;justify-content:center;font-size:1.35rem;color:#fff;box-shadow:0 8px 26px rgba(99,102,241,0.35);}
.logo-text{font-family:'Orbitron',sans-serif;font-size:1rem;font-weight:900;background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:2px;}
.card{background:var(--panel);border:1px solid var(--border);border-radius:22px;padding:26px;box-shadow:var(--shadow);margin-bottom:14px;}
.card-title{font-family:'Orbitron',sans-serif;font-size:0.85rem;font-weight:900;background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:18px;}
/* RADAR */
.radar-wrap{position:relative;width:160px;height:160px;margin:0 auto 22px;}
.radar-ring{position:absolute;inset:0;border-radius:50%;border:2.5px solid transparent;animation:radarSpin 2s linear infinite;}
.radar-ring:nth-child(1){border-top-color:var(--primary);animation-duration:1.8s;}
.radar-ring:nth-child(2){inset:16px;border-right-color:var(--primary2);animation-direction:reverse;animation-duration:2.2s;}
.radar-ring:nth-child(3){inset:32px;border-bottom-color:rgba(99,102,241,0.5);animation-duration:1.5s;}
@keyframes radarSpin{to{transform:rotate(360deg);}}
.radar-center{position:absolute;inset:52px;background:var(--grad);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.3rem;color:#fff;box-shadow:0 6px 24px rgba(99,102,241,0.4);}
/* FORM */
.fg{margin-bottom:14px;}
.fg label{display:block;font-size:0.72rem;font-weight:800;color:var(--text2);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;}
.fg input{width:100%;padding:12px 15px;background:#f8fafc;border:1.5px solid var(--border);border-radius:13px;color:var(--text);font-size:0.9rem;font-weight:700;font-family:'Nunito',sans-serif;}
.fg input:focus{border-color:var(--primary);box-shadow:0 0 0 3px rgba(99,102,241,0.12);}
.btn-check{width:100%;padding:13px;background:var(--grad);border:none;border-radius:13px;color:#fff;font-weight:800;font-size:0.9rem;cursor:pointer;font-family:'Nunito',sans-serif;box-shadow:0 6px 20px rgba(99,102,241,0.3);transition:0.2s;}
.btn-check:hover{transform:translateY(-2px);box-shadow:0 10px 32px rgba(99,102,241,0.4);}
/* RESULT */
.result-card{display:none;background:rgba(99,102,241,0.04);border:1.5px solid rgba(99,102,241,0.2);border-radius:18px;padding:20px;margin-top:14px;}
.result-title{font-family:'Orbitron',sans-serif;font-size:0.75rem;font-weight:900;background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:1px;text-transform:uppercase;margin-bottom:16px;display:flex;align-items:center;gap:7px;}
.info-row{display:flex;justify-content:space-between;align-items:flex-start;padding:9px 0;border-bottom:1px solid rgba(0,0,0,0.05);font-size:0.84rem;gap:8px;}
.info-row:last-child{border-bottom:none;}
.info-label{color:var(--text2);font-weight:600;flex-shrink:0;}
.info-val{color:var(--text);font-weight:800;text-align:right;word-break:break-all;}
.badge-ok{background:rgba(34,197,94,0.1);color:#15803d;border:1px solid rgba(34,197,94,0.25);padding:3px 9px;border-radius:20px;font-size:0.72rem;font-weight:800;}
.badge-no{background:rgba(239,68,68,0.08);color:#dc2626;border:1px solid rgba(239,68,68,0.2);padding:3px 9px;border-radius:20px;font-size:0.72rem;font-weight:800;}
.dev-list{margin-top:12px;display:flex;flex-direction:column;gap:7px;}
.dev-item{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:11px 14px;font-size:0.78rem;}
.dev-id{font-weight:800;color:var(--text);word-break:break-all;margin-bottom:4px;}
.dev-meta{color:var(--muted);font-size:0.72rem;}
.spinner{width:36px;height:36px;border:3px solid rgba(99,102,241,0.15);border-top-color:var(--primary);border-radius:50%;animation:spin 0.7s linear infinite;margin:0 auto;}
@keyframes spin{to{transform:rotate(360deg);}}
.back-btn{display:inline-flex;align-items:center;gap:7px;padding:9px 16px;background:rgba(99,102,241,0.1);border:1.5px solid rgba(99,102,241,0.3);border-radius:11px;color:var(--primary);font-weight:800;font-size:0.8rem;cursor:pointer;text-decoration:none;font-family:'Nunito',sans-serif;transition:0.2s;margin-top:14px;}
</style>
</head>
<body>
<div class="wrap">
  <div class="logo-row">
    <div class="logo-ico"><i class="fa-solid fa-globe"></i></div>
    <div class="logo-text">CHECK IP KEY</div>
  </div>
  <div class="card">
    <div class="card-title">KIỂM TRA THÔNG TIN KEY</div>
    <div class="radar-wrap">
      <div class="radar-ring"></div><div class="radar-ring"></div><div class="radar-ring"></div>
      <div class="radar-center"><i class="fa-solid fa-shield-halved"></i></div>
    </div>
    <div class="fg"><label>Key của bạn</label><input type="text" id="cik_key" placeholder="Nhập key cần kiểm tra..."></div>
    <div class="fg"><label>Device ID (tuỳ chọn)</label><input type="text" id="cik_dev" placeholder="Device ID (nếu có)"></div>
    <button class="btn-check" onclick="doCheck()"><i class="fa-solid fa-magnifying-glass"></i> KIỂM TRA NGAY</button>
    <div id="cik_loading" style="display:none;padding:22px 0;"><div class="spinner"></div></div>
    <div class="result-card" id="cik_result"></div>
  </div>
  <a href="/" class="back-btn"><i class="fa-solid fa-arrow-left"></i> Về trang chủ</a>
</div>
<script>
function doCheck(){
  var k=document.getElementById('cik_key').value.trim();
  var dev=document.getElementById('cik_dev').value.trim();
  if(!k){alert('Vui lòng nhập key');return;}
  document.getElementById('cik_loading').style.display='block';
  document.getElementById('cik_result').style.display='none';
  var url='/api/check_key?key='+encodeURIComponent(k)+(dev?'&device_id='+encodeURIComponent(dev):'');
  fetch(url).then(function(r){return r.json();}).then(function(d){
    document.getElementById('cik_loading').style.display='none';
    var box=document.getElementById('cik_result');
    box.style.display='block';
    if(d.status==='success'){
      var i=d.info||d.data||d;
      var valid=d.valid||d.is_valid;
      var badge=valid?'<span class="badge-ok"><i class="fa-solid fa-check"></i> Còn hạn</span>':'<span class="badge-no"><i class="fa-solid fa-xmark"></i> Hết hạn</span>';
      var devs=(i.devices||[]).map(function(dv){
        return '<div class="dev-item"><div class="dev-id"><i class="fa-solid fa-mobile-screen-button" style="color:var(--primary);font-size:0.75rem;"></i> '+dv.device_id+'</div><div class="dev-meta">Đăng ký: '+( dv.registered_at||'—')+'</div></div>';
      }).join('');
      box.innerHTML='<div class="result-title"><i class="fa-solid fa-circle-check" style="-webkit-text-fill-color:initial;color:var(--success);"></i> KẾT QUẢ</div>'
        +'<div class="info-row"><span class="info-label">Trạng thái</span><span class="info-val">'+badge+'</span></div>'
        +'<div class="info-row"><span class="info-label">Key</span><span class="info-val" style="font-size:0.7rem;font-family:monospace;">'+k+'</span></div>'
        +'<div class="info-row"><span class="info-label">Loại</span><span class="info-val">'+(i.key_type||i.type||'—')+'</span></div>'
        +'<div class="info-row"><span class="info-label">Hết hạn</span><span class="info-val">'+(i.expiry_date||i.expiry||'—')+'</span></div>'
        +'<div class="info-row"><span class="info-label">Thiết bị</span><span class="info-val">'+(i.devices_count!==undefined?i.devices_count:i.used_devices||0)+' / '+(i.max_devices||i.max_dev||'—')+'</span></div>'
        +(devs?'<div style="margin-top:4px;font-size:0.72rem;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">Thiết bị đã đăng ký</div><div class="dev-list">'+devs+'</div>':'');
    } else {
      box.innerHTML='<div style="text-align:center;padding:16px;"><div style="font-size:1.8rem;color:var(--danger);margin-bottom:10px;"><i class="fa-solid fa-circle-xmark"></i></div><div style="font-weight:800;color:var(--danger);">'+(d.message||'Key không hợp lệ')+'</div></div>';
    }
  }).catch(function(){document.getElementById('cik_loading').style.display='none';});
}
document.getElementById('cik_key').addEventListener('keydown',function(e){if(e.key==='Enter')doCheck();});
</script>
</body>
</html>
"""

DEVICE_REG_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Đăng Ký Thiết Bị — Văn Khánh</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&family=Orbitron:wght@700;900&display=swap');
:root{--bg:#f0f2f7;--panel:#fff;--primary:#6366f1;--primary2:#8b5cf6;--grad:linear-gradient(135deg,#6366f1,#8b5cf6);--text:#1e293b;--text2:#475569;--muted:#94a3b8;--success:#22c55e;--danger:#ef4444;--border:rgba(0,0,0,0.08);--shadow:0 8px 32px rgba(99,102,241,0.12);}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
*:focus{outline:none;}
body{background:var(--bg);color:var(--text);font-family:'Nunito',sans-serif;min-height:100vh;display:flex;justify-content:center;align-items:flex-start;padding:24px 12px 60px;}
.wrap{width:min(480px,100%);padding-top:16px;}
.logo-row{display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:26px;}
.logo-ico{width:52px;height:52px;background:var(--grad);border-radius:15px;display:flex;align-items:center;justify-content:center;font-size:1.35rem;color:#fff;box-shadow:0 8px 26px rgba(99,102,241,0.35);}
.logo-text{font-family:'Orbitron',sans-serif;font-size:1rem;font-weight:900;background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:2px;}
.card{background:var(--panel);border:1px solid var(--border);border-radius:22px;padding:26px;box-shadow:var(--shadow);margin-bottom:14px;}
.card-icon{width:60px;height:60px;background:var(--grad);border-radius:18px;display:flex;align-items:center;justify-content:center;font-size:1.5rem;color:#fff;margin:0 auto 18px;box-shadow:0 8px 28px rgba(99,102,241,0.35);}
.card-title{font-family:'Orbitron',sans-serif;font-size:0.92rem;font-weight:900;background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:1.5px;text-transform:uppercase;text-align:center;margin-bottom:6px;}
.card-sub{font-size:0.78rem;color:var(--muted);text-align:center;margin-bottom:22px;line-height:1.6;}
.fg{margin-bottom:14px;}
.fg label{display:block;font-size:0.72rem;font-weight:800;color:var(--text2);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;}
.fg input,.fg select{width:100%;padding:12px 15px;background:#f8fafc;border:1.5px solid var(--border);border-radius:13px;color:var(--text);font-size:0.9rem;font-weight:700;font-family:'Nunito',sans-serif;-webkit-appearance:none;}
.fg input:focus,.fg select:focus{border-color:var(--primary);box-shadow:0 0 0 3px rgba(99,102,241,0.12);}
.fg input::placeholder{color:var(--muted);font-weight:500;}
.info-box{background:rgba(59,130,246,0.06);border:1px solid rgba(59,130,246,0.2);border-radius:13px;padding:12px 14px;font-size:0.78rem;color:#1d4ed8;font-weight:600;margin-bottom:16px;display:flex;gap:9px;align-items:flex-start;line-height:1.6;}
.info-box i{margin-top:1px;flex-shrink:0;}
.btn-reg{width:100%;padding:14px;background:var(--grad);border:none;border-radius:13px;color:#fff;font-weight:800;font-size:0.92rem;cursor:pointer;font-family:'Nunito',sans-serif;box-shadow:0 6px 22px rgba(99,102,241,0.35);transition:0.2s;display:flex;align-items:center;justify-content:center;gap:8px;}
.btn-reg:hover{transform:translateY(-2px);box-shadow:0 10px 32px rgba(99,102,241,0.45);}
.btn-reg:disabled{opacity:0.5;cursor:not-allowed;transform:none;}
.result{margin-top:14px;display:none;}
.success-box{background:rgba(34,197,94,0.07);border:1px solid rgba(34,197,94,0.25);border-radius:16px;padding:22px;text-align:center;}
.success-icon{font-size:2.4rem;color:var(--success);margin-bottom:12px;}
.success-title{font-weight:900;font-size:1rem;color:#15803d;margin-bottom:6px;}
.success-msg{font-size:0.82rem;color:var(--text2);line-height:1.65;}
.error-box{background:rgba(239,68,68,0.07);border:1px solid rgba(239,68,68,0.2);border-radius:16px;padding:22px;text-align:center;}
.error-icon{font-size:2.2rem;color:var(--danger);margin-bottom:12px;}
.error-title{font-weight:900;font-size:0.95rem;color:#dc2626;margin-bottom:6px;}
.error-msg{font-size:0.82rem;color:var(--text2);}
.spinner{width:22px;height:22px;border:2.5px solid rgba(255,255,255,0.3);border-top-color:#fff;border-radius:50%;animation:spin 0.7s linear infinite;}
@keyframes spin{to{transform:rotate(360deg);}}
.back-btn{display:inline-flex;align-items:center;gap:7px;padding:9px 16px;background:rgba(99,102,241,0.1);border:1.5px solid rgba(99,102,241,0.3);border-radius:11px;color:var(--primary);font-weight:800;font-size:0.8rem;cursor:pointer;text-decoration:none;font-family:'Nunito',sans-serif;transition:0.2s;margin-top:14px;}
</style>
</head>
<body>
<div class="wrap">
  <div class="logo-row">
    <div class="logo-ico"><i class="fa-solid fa-mobile-screen-button"></i></div>
    <div class="logo-text">VĂN KHÁNH</div>
  </div>
  <div class="card">
    <div class="card-icon"><i class="fa-solid fa-mobile-screen-button"></i></div>
    <div class="card-title">ĐĂNG KÝ THIẾT BỊ</div>
    <div class="card-sub">Nhập thông tin thiết bị và key để gửi yêu cầu đăng ký. Admin sẽ xét duyệt trong thời gian sớm nhất.</div>
    <div class="info-box"><i class="fa-solid fa-circle-info"></i><span>Thiết bị sẽ được kích hoạt sau khi admin duyệt. Vui lòng đảm bảo Device ID chính xác.</span></div>
    <div class="fg"><label>Key của bạn</label><input type="text" id="dr_key" placeholder="XXXX-XXXX-XXXX-XXXX"></div>
    <div class="fg"><label>Device ID</label><input type="text" id="dr_dev" placeholder="Ví dụ: android_abc123 hoặc ios_xyz456"></div>
    <div class="fg"><label>Tên thiết bị (tuỳ chọn)</label><input type="text" id="dr_name" placeholder="Samsung Galaxy A52, iPhone 14..."></div>
    <button class="btn-reg" id="regBtn" onclick="doRegister()"><i class="fa-solid fa-paper-plane"></i> GỬI YÊU CẦU</button>
    <div class="result" id="drResult"></div>
  </div>
  <a href="/" class="back-btn"><i class="fa-solid fa-arrow-left"></i> Về trang chủ</a>
</div>
<script>
function doRegister(){
  var k=document.getElementById('dr_key').value.trim();
  var dev=document.getElementById('dr_dev').value.trim();
  var name=document.getElementById('dr_name').value.trim();
  if(!k||!dev){alert('Vui lòng nhập Key và Device ID');return;}
  var btn=document.getElementById('regBtn');
  btn.disabled=true;
  btn.innerHTML='<div class="spinner"></div> Đang gửi...';
  var fd=new FormData();
  fd.append('key',k); fd.append('device_id',dev); if(name)fd.append('device_name',name);
  fetch('/dang-ky-thiet-bi',{method:'POST',body:fd})
  .then(function(r){return r.json();})
  .then(function(d){
    btn.disabled=false;
    btn.innerHTML='<i class="fa-solid fa-paper-plane"></i> GỬI YÊU CẦU';
    var box=document.getElementById('drResult');
    box.style.display='block';
    if(d.status==='success'||d.success){
      box.innerHTML='<div class="success-box"><div class="success-icon"><i class="fa-solid fa-circle-check"></i></div><div class="success-title">Gửi yêu cầu thành công!</div><div class="success-msg">Yêu cầu đăng ký thiết bị đã được ghi nhận. Admin sẽ xét duyệt và thông báo qua Telegram.<br><br><strong>Device ID:</strong> '+dev+'</div></div>';
    } else {
      box.innerHTML='<div class="error-box"><div class="error-icon"><i class="fa-solid fa-circle-xmark"></i></div><div class="error-title">Gửi thất bại</div><div class="error-msg">'+(d.message||'Có lỗi xảy ra, vui lòng thử lại')+'</div></div>';
    }
  }).catch(function(){
    btn.disabled=false;
    btn.innerHTML='<i class="fa-solid fa-paper-plane"></i> GỬI YÊU CẦU';
    document.getElementById('drResult').style.display='block';
    document.getElementById('drResult').innerHTML='<div class="error-box"><div class="error-icon"><i class="fa-solid fa-circle-xmark"></i></div><div class="error-title">Lỗi kết nối</div><div class="error-msg">Không thể kết nối máy chủ, vui lòng thử lại.</div></div>';
  });
}
</script>
</body>
</html>
"""

UI_TEMPLATE = HTML_P1 + HTML_P2 + HTML_P3 + HTML_P5

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(port=port, host='0.0.0.0')
