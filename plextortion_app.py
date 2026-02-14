import requests
import urllib3
urllib3.disable_warnings()
import json
import os
import sys
import webbrowser
import threading
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for
import database as db

app = Flask(__name__)

# ── WEBHOOK STATUS TRACKING ──
last_webhook_time = None

# ── PLEX CONNECTION (lazy loading) ──
_plex_connection = None

def get_plex_connection():
    global _plex_connection
    config = db.get_config()
    
    if not config.get('plex_url') or not config.get('plex_token'):
        return None, None, None
    
    try:
        from plexapi.server import PlexServer
        session = requests.Session()
        session.verify = False
        server = PlexServer(config['plex_url'], config['plex_token'], session=session, timeout=10)
        account = server.myPlexAccount()
        all_sections = server.library.sections()
        return server, account, all_sections
    except Exception as e:
        print(f"⚠️ Plex connection error: {e}")
        return None, None, None

def get_all_users():
    server, account, sections = get_plex_connection()
    if not account:
        return []
    return [user.title for user in account.users()]

def get_all_movies():
    server, account, sections = get_plex_connection()
    if not sections:
        return []
    movies = []
    for section in sections:
        if section.type == 'movie':
            for movie in section.all():
                movies.append(movie.title)
    return sorted(set(movies))

def get_all_libraries():
    server, account, sections = get_plex_connection()
    if not sections:
        return []
    return [s.title for s in sections]

def get_movies_by_library():
    server, account, sections = get_plex_connection()
    if not sections:
        return {}
    movies_by_lib = {}
    for section in sections:
        if section.type == 'movie':
            movies_by_lib[section.title] = sorted([movie.title for movie in section.all()])
    return movies_by_lib

def lock_library(username, library_name):
    """Soft lock - we don't actually hide the library anymore.
    Instead, we let them see it but kill their stream when they try to play."""
    print(f"🔒 SOFT LOCKED: '{library_name}' for {username} (library still visible, streams will be killed)")
    return True

def unlock_library(username):
    """Soft unlock - just log it, library was never hidden"""
    print(f"🔓 UNLOCKED: '{username}' can now watch without interruption")
    return True

def get_library_for_item(title):
    """Find which library a movie/show belongs to"""
    server, account, sections = get_plex_connection()
    if not sections:
        return None
    for section in sections:
        try:
            results = section.search(title)
            if results:
                return section.title
        except:
            pass
    return None

def get_session_key_by_player(player_uuid, username=None, title=None):
    """Get the session key for a player by matching its UUID or username+title to active sessions"""
    import time
    time.sleep(2)  # Wait for session to register
    
    server, account, sections = get_plex_connection()
    if not server:
        return None
    
    try:
        sessions = server.sessions()
        print(f"   🔍 Found {len(sessions)} active sessions")
        for session in sessions:
            session_user = session.usernames[0] if session.usernames else "Unknown"
            print(f"      Session: {session.sessionKey} - {session.title} (User: {session_user})")
            
            # Try to match by username + title first (more reliable)
            if username and title and session_user == username and session.title == title:
                print(f"      ✅ MATCH by username + title!")
                return session.sessionKey
            
            # Or match by player UUID
            for player in session.players:
                if player.machineIdentifier == player_uuid:
                    print(f"      ✅ MATCH by player UUID!")
                    return session.sessionKey
                
        print(f"   🔍 Looking for: {username} watching '{title}'")
        return None
    except Exception as e:
        print(f"⚠️ Error getting sessions: {e}")
        return None

def kill_stream(session_key, message):
    """Kill a Plex stream and display a message to the user"""
    config = db.get_config()
    if not config.get('plex_url') or not config.get('plex_token'):
        return False
    
    try:
        import urllib.parse
        encoded_message = urllib.parse.quote(message)
        base_url = config['plex_url'].rstrip('/')
        
        # Try the standard endpoint
        url = f"{base_url}/status/sessions/terminate?sessionId={session_key}&reason={encoded_message}&X-Plex-Token={config['plex_token']}"
        
        print(f"   🔗 Kill URL: {url[:120]}...")
        
        session = requests.Session()
        session.verify = False
        response = session.get(url, timeout=10)
        
        print(f"   📡 Response: {response.status_code}")
        
        if response.status_code == 200:
            print(f"💀 KILLED STREAM: Session {session_key}")
            return True
        
        # If that fails, try stopping via the session object
        print(f"   🔄 Trying alternative method...")
        
        server, account, sections = get_plex_connection()
        if server:
            for s in server.sessions():
                if str(s.sessionKey) == str(session_key):
                    try:
                        s.stop(reason=message)
                        print(f"💀 KILLED STREAM via stop(): Session {session_key}")
                        return True
                    except Exception as e2:
                        print(f"   ⚠️ stop() failed: {e2}")
        
        return False
    except Exception as e:
        print(f"⚠️ Error killing stream: {e}")
        return False

# ── HTML TEMPLATES ──

SETUP_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Plextortion Setup</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Segoe UI', sans-serif;
            background: #0a0a0a; 
            color: #e8e8e8;
            padding: 2rem;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .setup-card {
            background: #161616;
            border: 1px solid #222;
            border-radius: 12px;
            padding: 3rem;
            max-width: 500px;
            width: 100%;
        }
        h1 { color: #ff3c3c; margin-bottom: 0.5rem; font-size: 2rem; }
        .subtitle { color: #888; margin-bottom: 2rem; }
        label { 
            display: block; 
            margin-bottom: 0.3rem; 
            color: #888;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-top: 1rem;
        }
        input {
            width: 100%;
            padding: 0.75rem;
            background: #111;
            border: 1px solid #333;
            border-radius: 4px;
            color: #e8e8e8;
            font-size: 1rem;
        }
        input:focus { outline: none; border-color: #ff3c3c; }
        .btn {
            width: 100%;
            margin-top: 2rem;
            padding: 1rem;
            background: #ff3c3c;
            color: #fff;
            border: none;
            border-radius: 4px;
            font-size: 1rem;
            cursor: pointer;
        }
        .btn:hover { background: #ff5555; }
        .help { color: #666; font-size: 0.8rem; margin-top: 0.5rem; }
        .error { color: #ff3c3c; margin-top: 1rem; padding: 1rem; background: rgba(255,60,60,0.1); border-radius: 4px; }
    </style>
</head>
<body>
    <div class="setup-card">
        <h1>🎬 Plextortion</h1>
        <p class="subtitle">First-time setup</p>
        
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        
        <form method="post" action="/setup">
            <label>Plex Server URL</label>
            <input type="text" name="plex_url" placeholder="https://192.168.1.100:32400" value="{{ config.plex_url or '' }}" required>
            <p class="help">Your Plex server's local IP address with port 32400</p>
            
            <label>Plex Token</label>
            <input type="text" name="plex_token" placeholder="Your Plex token" value="{{ config.plex_token or '' }}" required>
            <p class="help">Find this in Plex: any media → Get Info → View XML → token in URL</p>
            
            <button type="submit" class="btn">Connect to Plex</button>
        </form>
    </div>
</body>
</html>
'''

SETTINGS_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Plextortion Settings</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Segoe UI', sans-serif;
            background: #0a0a0a; 
            color: #e8e8e8;
            padding: 2rem;
        }
        .container { max-width: 600px; margin: 0 auto; }
        h1 { color: #ff3c3c; margin-bottom: 2rem; }
        h3 { margin-bottom: 1rem; color: #e8e8e8; }
        .card {
            background: #161616;
            border: 1px solid #222;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1rem;
        }
        label { 
            display: block; 
            margin-bottom: 0.3rem; 
            color: #888;
            font-size: 0.85rem;
            text-transform: uppercase;
            margin-top: 1rem;
        }
        label:first-child { margin-top: 0; }
        input {
            width: 100%;
            padding: 0.75rem;
            background: #111;
            border: 1px solid #333;
            border-radius: 4px;
            color: #e8e8e8;
            font-size: 1rem;
        }
        .btn {
            margin-top: 1.5rem;
            padding: 0.75rem 1.5rem;
            background: #ff3c3c;
            color: #fff;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1rem;
        }
        .btn:hover { background: #ff5555; }
        .btn-back {
            background: #333;
            margin-right: 1rem;
            text-decoration: none;
            display: inline-block;
        }
        .btn-back:hover { background: #444; }
        .btn-test {
            background: #2ecc71;
            margin-left: 1rem;
        }
        .btn-test:hover { background: #27ae60; }
        .success { color: #2ecc71; margin-top: 1rem; }
        .webhook-info {
            background: #111;
            border: 1px solid #333;
            border-radius: 4px;
            padding: 1rem;
            margin-top: 1rem;
            font-family: monospace;
            font-size: 0.9rem;
            color: #f39c12;
            word-break: break-all;
        }
        .help { color: #666; font-size: 0.8rem; margin-top: 0.5rem; }
        .status-box {
            padding: 1rem;
            border-radius: 4px;
            margin-top: 1rem;
        }
        .status-ok { background: rgba(46, 204, 113, 0.1); border: 1px solid #2ecc71; }
        .status-warning { background: rgba(243, 156, 18, 0.1); border: 1px solid #f39c12; }
        .status-error { background: rgba(255, 60, 60, 0.1); border: 1px solid #ff3c3c; }
        .instructions {
            background: #111;
            border: 1px solid #333;
            border-radius: 4px;
            padding: 1rem;
            margin-top: 1rem;
            font-size: 0.9rem;
        }
        .instructions ol {
            margin-left: 1.5rem;
            color: #888;
        }
        .instructions li {
            margin: 0.5rem 0;
        }
        .instructions code {
            background: #222;
            padding: 0.2rem 0.4rem;
            border-radius: 3px;
            color: #f39c12;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚙️ Settings</h1>
        
        <div class="card">
            <h3>Plex Connection</h3>
            <form method="post" action="/settings">
                <label>Plex Server URL</label>
                <input type="text" name="plex_url" value="{{ config.plex_url or '' }}" required>
                
                <label>Plex Token</label>
                <input type="text" name="plex_token" value="{{ config.plex_token or '' }}" required>
                <p class="help">If your token expires, get a new one from Plex and update it here.</p>
                
                <a href="/" class="btn btn-back">← Back</a>
                <button type="submit" class="btn">Save Settings</button>
            </form>
            
            {% if saved %}
            <p class="success">✓ Settings saved successfully!</p>
            {% endif %}
        </div>
        
        <div class="card">
            <h3>Webhook Configuration</h3>
            <p style="color: #888; margin-bottom: 1rem;">Plextortion needs webhooks to track viewing progress.</p>
            
            <div class="webhook-info">
                http://{{ local_ip }}:5555/webhook
            </div>
            
            {% if webhook_status == 'ok' %}
            <div class="status-box status-ok">
                ✅ <strong>Webhooks working!</strong><br>
                <span style="color: #888;">Last received: {{ last_webhook }}</span>
            </div>
            {% elif webhook_status == 'never' %}
            <div class="status-box status-warning">
                ⚠️ <strong>No webhooks received yet</strong><br>
                <span style="color: #888;">Configure webhooks in Plex and play something to test.</span>
            </div>
            {% endif %}
            
            <div class="instructions">
                <strong>How to enable webhooks in Plex:</strong>
                <ol>
                    <li>Open Plex Web (on your server or app.plex.tv)</li>
                    <li>Go to <strong>Settings</strong> (wrench icon)</li>
                    <li>Click <strong>Webhooks</strong> in the left sidebar</li>
                    <li>Click <strong>Add Webhook</strong></li>
                    <li>Paste this URL: <code>http://{{ local_ip }}:5555/webhook</code></li>
                    <li>Click <strong>Save Changes</strong></li>
                </ol>
                <p style="margin-top: 1rem; color: #f39c12;">⚠️ Webhooks require <strong>Plex Pass</strong>. If you don't see the Webhooks option, you may need to upgrade.</p>
            </div>
            
            <a href="/test-webhook" class="btn btn-test" style="margin-top: 1rem; display: inline-block;">🔔 Send Test Webhook</a>
            <p class="help">Click to simulate a webhook. If it works, you'll see a success message.</p>
        </div>
    </div>
</body>
</html>
'''

ADMIN_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Plextortion Admin</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Segoe UI', sans-serif;
            background: #0a0a0a; 
            color: #e8e8e8;
            padding: 2rem;
            line-height: 1.6;
            text-align: left;
        }
        .container { max-width: 900px; margin: 0 auto; }
        .header-row {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 1rem;
        }
        h1 { 
            font-size: 2.5rem; 
            margin-bottom: 0.5rem;
            color: #ff3c3c;
            text-align: left;
        }
        h2 { 
            font-size: 1.3rem; 
            margin: 2rem 0 1rem;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            text-align: left;
        }
        .subtitle { color: #888; margin-bottom: 2rem; }
        .settings-link {
            color: #888;
            text-decoration: none;
            font-size: 0.9rem;
            padding: 0.5rem 1rem;
            border: 1px solid #333;
            border-radius: 4px;
        }
        .settings-link:hover { color: #fff; border-color: #555; }
        .status-badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            font-size: 0.8rem;
            margin-left: 1rem;
        }
        .status-connected { background: rgba(46, 204, 113, 0.2); color: #2ecc71; }
        .status-disconnected { background: rgba(255, 60, 60, 0.2); color: #ff3c3c; }
        .webhook-warning {
            background: rgba(243, 156, 18, 0.1);
            border: 1px solid #f39c12;
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .webhook-warning a {
            color: #f39c12;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border: 1px solid #f39c12;
            border-radius: 4px;
            font-size: 0.85rem;
        }
        .webhook-warning a:hover {
            background: rgba(243, 156, 18, 0.2);
        }
        .card {
            background: #161616;
            border: 1px solid #222;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1rem;
        }
        .ransom-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem;
            background: #111;
            border: 1px solid #222;
            border-radius: 6px;
            margin-bottom: 0.5rem;
        }
        .ransom-info strong { color: #ff3c3c; }
        .ransom-info span { color: #888; font-size: 0.9rem; }
        .btn {
            padding: 0.5rem 1rem;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: all 0.2s;
        }
        .btn-delete {
            background: #333;
            color: #ff3c3c;
        }
        .btn-delete:hover { background: #ff3c3c; color: #fff; }
        .btn-create {
            background: #ff3c3c;
            color: #fff;
            padding: 0.75rem 1.5rem;
            font-size: 1rem;
        }
        .btn-create:hover { background: #ff5555; }
        form.create-form {
            display: grid;
            gap: 1rem;
        }
        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }
        label { 
            display: block; 
            margin-bottom: 0.3rem; 
            color: #888;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        select, input {
            width: 100%;
            padding: 0.75rem;
            background: #111;
            border: 1px solid #333;
            border-radius: 4px;
            color: #e8e8e8;
            font-size: 1rem;
        }
        select:focus, input:focus {
            outline: none;
            border-color: #ff3c3c;
        }
        .empty-state {
            text-align: center;
            padding: 2rem;
            color: #555;
        }
        .progress-bar {
            height: 6px;
            background: #333;
            border-radius: 3px;
            margin-top: 0.5rem;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: #ff3c3c;
            border-radius: 3px;
        }
        .collapsible {
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .collapsible:hover { color: #fff; }
        .collapsible::after {
            content: '▼';
            font-size: 0.8rem;
            transition: transform 0.3s;
        }
        .collapsible.collapsed::after {
            transform: rotate(-90deg);
        }
        .history-content {
            overflow: hidden;
            transition: max-height 0.3s ease-out;
        }
        .history-content.collapsed {
            max-height: 0 !important;
        }
        .threshold-badge {
            background: #333;
            color: #f39c12;
            padding: 0.2rem 0.5rem;
            border-radius: 3px;
            font-size: 0.75rem;
            margin-left: 0.5rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header-row">
            <div>
                <h1>🎬 Plextortion
                    {% if server_name %}
                    <span class="status-badge status-connected">● {{ server_name }}</span>
                    {% else %}
                    <span class="status-badge status-disconnected">● Disconnected</span>
                    {% endif %}
                </h1>
                <p class="subtitle">Extortion Management System</p>
            </div>
            <a href="/settings" class="settings-link">⚙️ Settings</a>
        </div>
        
        {% if not webhook_ok %}
        <div class="webhook-warning">
            <span>⚠️ <strong>Webhooks not detected.</strong> Progress tracking won't work until webhooks are configured.</span>
            <div style="display: flex; gap: 0.5rem;">
                <a href="/test-webhook">🔔 Test</a>
                <a href="/settings">⚙️ Configure</a>
            </div>
        </div>
        {% endif %}
        
        <h2>Active Ransoms</h2>
        {% if ransoms %}
            {% for r in ransoms %}
            <div class="ransom-item">
                <div class="ransom-info">
                    <strong>{{ r.username }}</strong>
                    <span class="threshold-badge">{{ r.threshold }}% required</span><br>
                    <span>Must watch: <em>{{ r.prerequisite }}</em></span><br>
                    <span>To unlock: {{ r.locked_library }}</span>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {{ (r.progress / r.threshold * 100) if r.threshold > 0 else 0 }}%"></div>
                    </div>
                    <span>{{ r.progress }}% / {{ r.threshold }}%</span>
                </div>
                <form action="/delete/{{ r.id }}" method="post" style="margin:0">
                    <button type="submit" class="btn btn-delete">Delete</button>
                </form>
            </div>
            {% endfor %}
        {% else %}
            <div class="card empty-state">
                No active ransoms. Time to extort someone!
            </div>
        {% endif %}
        
        <h2>Create New Ransom</h2>
        <div class="card">
            <form class="create-form" action="/create" method="post" id="ransomForm">
                <div>
                    <label>Victim</label>
                    <select name="username" id="username" required onchange="updatePreview()">
                        <option value="">Select a user...</option>
                        {% for user in users %}
                        <option value="{{ user }}">{{ user }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label>Must Watch Library (optional filter)</label>
                    <select name="prereq_library" id="prereq_library" onchange="filterMovies()">
                        <option value="">All libraries...</option>
                        {% for lib in movie_libraries %}
                        <option value="{{ lib }}">{{ lib }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label>Must Watch Movie</label>
                    <select name="prerequisite" id="prerequisite" required onchange="updatePreview()">
                        <option value="">Select a movie...</option>
                        {% for movie in movies %}
                        <option value="{{ movie }}">{{ movie }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-row">
                    <div>
                        <label>Library to Lock</label>
                        <select name="locked_library" id="locked_library" required onchange="updatePreview()">
                            <option value="">Select a library...</option>
                            {% for lib in libraries %}
                            <option value="{{ lib }}">{{ lib }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div>
                        <label>Watch Threshold</label>
                        <select name="threshold" id="threshold" required onchange="updatePreview()">
                            <option value="10">10% - Quick taste</option>
                            <option value="20" selected>20% - Standard</option>
                            <option value="30">30% - Committed</option>
                            <option value="40">40% - Dedicated</option>
                            <option value="50">50% - Halfway there</option>
                            <option value="75">75% - Almost all</option>
                            <option value="100">100% - Full movie</option>
                        </select>
                    </div>
                </div>
                
                <div style="border-top: 1px solid #333; margin-top: 1rem; padding-top: 1rem;">
                    <h3 style="color: #888; font-size: 0.9rem; margin-bottom: 1rem;">✉️ MESSAGE CUSTOMIZATION (Optional)</h3>
                    <div>
                        <label>🔒 Lock Message (when they try to watch locked content)</label>
                        <input type="text" name="custom_message" id="custom_message" placeholder="Leave blank for default" onkeyup="updatePreview()">
                        <p class="help" style="color: #666; font-size: 0.8rem;">Use {movie}, {threshold}, {library} as placeholders.</p>
                    </div>
                    <div style="margin-top: 1rem;">
                        <label>🔓 Unlock Message (when they complete the prerequisite)</label>
                        <input type="text" name="unlock_message" id="unlock_message" placeholder="Leave blank for default" onkeyup="updatePreview()">
                        <p class="help" style="color: #666; font-size: 0.8rem;">Use {movie}, {progress}, {library} as placeholders.</p>
                    </div>
                </div>
                
                <div style="background: #111; border: 1px solid #333; border-radius: 4px; padding: 1rem; margin-top: 1rem;">
                    <label style="margin: 0;">📺 MESSAGE PREVIEW</label>
                    <div style="margin-top: 0.5rem;">
                        <span style="color: #ff3c3c; font-size: 0.8rem;">LOCK:</span>
                        <div id="lockPreview" style="padding: 0.5rem; background: #1a1a1a; border-radius: 4px; color: #f39c12; font-family: monospace; margin-bottom: 0.5rem;">
                            Select options above to see preview...
                        </div>
                        <span style="color: #2ecc71; font-size: 0.8rem;">UNLOCK:</span>
                        <div id="unlockPreview" style="padding: 0.5rem; background: #1a1a1a; border-radius: 4px; color: #2ecc71; font-family: monospace;">
                            Select options above to see preview...
                        </div>
                    </div>
                </div>
                
                <button type="submit" class="btn btn-create">🔒 Create Ransom</button>
            </form>
        </div>

        <h2>🏆 Most Ransomed Movies</h2>
        {% if top_ransoms %}
            <div class="card">
                {% for movie, count in top_ransoms %}
                <div style="display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #222;">
                    <span>{{ movie }}</span>
                    <span style="color: #888;">{{ count }}x</span>
                </div>
                {% endfor %}
            </div>
        {% else %}
            <div class="card empty-state">
                No ransoms yet. Start extorting!
            </div>
        {% endif %}

        <h2 class="collapsible" onclick="toggleHistory()">Ransom History</h2>
        <div class="history-content" id="historyContent">
            {% if completed %}
                {% for r in completed %}
                <div class="ransom-item" style="opacity: 0.6;">
                    <div class="ransom-info">
                        <strong>{{ r.username }}</strong> ✅<br>
                        <span>Watched: <em>{{ r.prerequisite }}</em></span><br>
                        <span>Unlocked: {{ r.locked_library }}</span><br>
                        <span style="color: #2ecc71;">Completed at {{ r.progress }}%</span>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <div class="card empty-state">
                    No completed ransoms yet.
                </div>
            {% endif %}
        </div>
    </div>
    
    <script>
        const moviesByLibrary = {{ movies_by_library | tojson }};
        const allMovies = {{ movies | tojson }};
        const defaultFromName = "{{ server_name or 'Plex Admin' }}";
        
        function filterMovies() {
            const libSelect = document.getElementById('prereq_library');
            const movieSelect = document.getElementById('prerequisite');
            const selectedLib = libSelect.value;
            
            movieSelect.innerHTML = '<option value="">Select a movie...</option>';
            
            let moviesToShow = selectedLib ? moviesByLibrary[selectedLib] || [] : allMovies;
            
            moviesToShow.forEach(movie => {
                const option = document.createElement('option');
                option.value = movie;
                option.textContent = movie;
                movieSelect.appendChild(option);
            });
            updatePreview();
        }
        
        function toggleHistory() {
            const content = document.getElementById('historyContent');
            const header = document.querySelector('.collapsible');
            content.classList.toggle('collapsed');
            header.classList.toggle('collapsed');
        }
        
        function updatePreview() {
            const movie = document.getElementById('prerequisite').value || '[movie]';
            const library = document.getElementById('locked_library').value || '[library]';
            const threshold = document.getElementById('threshold').value || '20';
            const customMessage = document.getElementById('custom_message').value;
            const unlockMessage = document.getElementById('unlock_message').value;
            
            // Lock message preview
            let lockMsg;
            if (customMessage) {
                lockMsg = customMessage
                    .replace('{movie}', movie)
                    .replace('{threshold}', threshold)
                    .replace('{library}', library);
            } else {
                lockMsg = `LIBRARY LOCKED! Watch ${threshold}% of '${movie}' to unlock '${library}'`;
            }
            document.getElementById('lockPreview').innerHTML = lockMsg;
            
            // Unlock message preview
            let unlockMsg;
            if (unlockMessage) {
                unlockMsg = unlockMessage
                    .replace('{movie}', movie)
                    .replace('{progress}', threshold + '+')
                    .replace('{library}', library);
            } else {
                unlockMsg = `🎉 FREEDOM! You watched ${threshold}%+ - '${library}' is now unlocked!`;
            }
            document.getElementById('unlockPreview').innerHTML = unlockMsg;
        }
        
        // Initialize preview on page load
        document.addEventListener('DOMContentLoaded', updatePreview);
    </script>
</body>
</html>
'''

TEST_WEBHOOK_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Webhook Test</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Segoe UI', sans-serif;
            background: #0a0a0a; 
            color: #e8e8e8;
            padding: 2rem;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .card {
            background: #161616;
            border: 1px solid #222;
            border-radius: 12px;
            padding: 3rem;
            max-width: 500px;
            width: 100%;
            text-align: center;
        }
        .success { color: #2ecc71; font-size: 3rem; margin-bottom: 1rem; }
        h2 { color: #2ecc71; margin-bottom: 1rem; }
        p { color: #888; margin-bottom: 2rem; }
        .btn {
            display: inline-block;
            padding: 0.75rem 1.5rem;
            background: #333;
            color: #fff;
            border: none;
            border-radius: 4px;
            text-decoration: none;
            font-size: 1rem;
        }
        .btn:hover { background: #444; }
    </style>
</head>
<body>
    <div class="card">
        <div class="success">✓</div>
        <h2>Webhook Test Successful!</h2>
        <p>Your webhook endpoint is working. Now make sure Plex is configured to send webhooks to this URL.</p>
        <a href="/settings" class="btn">← Back to Settings</a>
    </div>
</body>
</html>
'''

# ── HELPER FUNCTIONS ──

def get_local_ip():
    """Get the local IP address of this machine"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "YOUR_IP"

# ── ROUTES ──

@app.route('/')
def index():
    db.init_db()
    config = db.get_config()
    
    # If no config, redirect to setup
    if not config.get('plex_url') or not config.get('plex_token'):
        return redirect(url_for('setup'))
    
    server, account, sections = get_plex_connection()
    server_name = server.friendlyName if server else None
    
    # Check webhook status
    webhook_ok = last_webhook_time is not None
    
    # If can't connect, still show page but with disconnect warning
    ransoms = db.get_active_ransoms()
    completed = db.get_completed_ransoms()
    top_ransoms = db.get_most_used_ransoms()
    users = get_all_users()
    movies = get_all_movies()
    libraries = get_all_libraries()
    movies_by_library = get_movies_by_library()
    movie_libraries = list(movies_by_library.keys())
    
    return render_template_string(ADMIN_HTML,
        ransoms=ransoms,
        users=users,
        movies=movies,
        libraries=libraries,
        completed=completed,
        movies_by_library=movies_by_library,
        movie_libraries=movie_libraries,
        top_ransoms=top_ransoms,
        server_name=server_name,
        webhook_ok=webhook_ok
    )

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    db.init_db()
    error = None
    config = db.get_config()
    
    if request.method == 'POST':
        plex_url = request.form['plex_url']
        plex_token = request.form['plex_token']
        
        # Test connection
        try:
            from plexapi.server import PlexServer
            session = requests.Session()
            session.verify = False
            server = PlexServer(plex_url, plex_token, session=session, timeout=10)
            server_name = server.friendlyName
            
            # Connection works - save config
            db.save_config(plex_url, plex_token)
            print(f"✅ Connected to Plex server: {server_name}")
            return redirect(url_for('index'))
        except Exception as e:
            error = f"Could not connect to Plex: {e}"
            print(f"⚠️ {error}")
    
    return render_template_string(SETUP_HTML, config=config, error=error)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    db.init_db()
    saved = False
    config = db.get_config()
    
    if request.method == 'POST':
        plex_url = request.form['plex_url']
        plex_token = request.form['plex_token']
        db.save_config(plex_url, plex_token)
        saved = True
        config = {'plex_url': plex_url, 'plex_token': plex_token}
        print(f"✅ Settings updated")
    
    local_ip = get_local_ip()
    
    # Webhook status
    if last_webhook_time:
        webhook_status = 'ok'
        last_webhook = last_webhook_time.strftime('%Y-%m-%d %H:%M:%S')
    else:
        webhook_status = 'never'
        last_webhook = None
    
    return render_template_string(SETTINGS_HTML, 
        config=config, 
        saved=saved, 
        local_ip=local_ip,
        webhook_status=webhook_status,
        last_webhook=last_webhook
    )

@app.route('/test-webhook')
def test_webhook():
    global last_webhook_time
    last_webhook_time = datetime.now()
    print(f"🔔 Test webhook received at {last_webhook_time}")
    return render_template_string(TEST_WEBHOOK_HTML)

@app.route('/create', methods=['POST'])
def create_ransom():
    username = request.form['username']
    prerequisite = request.form['prerequisite']
    locked_library = request.form['locked_library']
    threshold = float(request.form['threshold'])
    custom_from = request.form.get('custom_from', '').strip() or None
    custom_message = request.form.get('custom_message', '').strip() or None
    unlock_message = request.form.get('unlock_message', '').strip() or None
    
    db.add_ransom(username, prerequisite, locked_library, threshold, custom_from, custom_message, unlock_message)
    lock_library(username, locked_library)
    print(f"🔒 Created ransom: {username} must watch '{prerequisite}' ({threshold}%) to unlock '{locked_library}'")
    
    return redirect(url_for('index'))

@app.route('/delete/<int:ransom_id>', methods=['POST'])
def delete_ransom(ransom_id):
    db.delete_ransom(ransom_id)
    print(f"🗑️ Deleted ransom #{ransom_id}")
    return redirect(url_for('index'))

@app.route('/webhook', methods=['POST'])
def webhook():
    global last_webhook_time
    last_webhook_time = datetime.now()
    
    # Reload active ransoms from database each time
    active_ransoms = {}
    for ransom in db.get_active_ransoms():
        active_ransoms[ransom["username"]] = ransom

    if request.form:
        payload = json.loads(request.form.get('payload', '{}'))
    else:
        payload = request.get_json(force=True) or {}

    event = payload.get('event', 'unknown')
    username = payload.get('Account', {}).get('title', 'Unknown')
    metadata = payload.get('Metadata', {})
    title = metadata.get('title', 'Unknown')
    
    # Get player UUID for session lookup
    player = payload.get('Player', {})
    player_uuid = player.get('uuid')
    
    # Get library directly from metadata (much faster than searching!)
    content_library = metadata.get('librarySectionTitle')

    view_offset = metadata.get('viewOffset', 0)
    duration = metadata.get('duration', 1)
    progress = round((view_offset / duration) * 100, 1) if duration > 0 else 0

    # Only care about ransomed users
    if username in active_ransoms:
        ransom = active_ransoms[username]
        prereq = ransom["prerequisite"]
        threshold = ransom.get("threshold", 20.0)
        locked_library = ransom.get("locked_library", "")
        custom_message = ransom.get("custom_message")
        unlock_message = ransom.get("unlock_message")

        print(f"\n👀 {username} | {event} | {title} | {progress}%")
        print(f"   📚 Library: {content_library} | Locked: {locked_library}")

        # Check if they're trying to watch something OTHER than the prerequisite
        if title != prereq and event in ['media.play', 'playback.started']:
            
            if content_library == locked_library:
                print(f"   🚫 Attempting to watch from locked library!")
                
                # Get the session key by player UUID
                session_key = get_session_key_by_player(player_uuid, username, title)
                
                if session_key:
                    # Build the ransom message
                    if custom_message:
                        ransom_message = custom_message.replace('{movie}', prereq).replace('{threshold}', str(int(threshold))).replace('{library}', locked_library)
                    else:
                        ransom_message = f"LIBRARY LOCKED! Watch {int(threshold)}% of '{prereq}' to unlock '{locked_library}'"
                    
                    print(f"   💀 Killing session {session_key} with message: {ransom_message}")
                    kill_stream(session_key, ransom_message)
                else:
                    print(f"   ⚠️ Could not find session for player {player_uuid}")

        # Check if they're watching the prerequisite
        if title == prereq and event in ['media.stop', 'media.pause']:
            print(f"   📊 Progress on prerequisite: {progress}% (need {threshold}%)")
            db.update_progress(username, progress)

            if progress >= threshold:
                print(f"\n🎉 THRESHOLD MET! {username} watched {progress}% of '{prereq}'")
                unlock_library(username)
                db.mark_unlocked(username)
                print(f"   🍺 One step closer to beer night!")
                
                # Kill the prerequisite stream with a freedom message!
                session_key = get_session_key_by_player(player_uuid, username, title)
                if session_key:
                    # Build the freedom message
                    if unlock_message:
                        freedom_message = unlock_message.replace('{movie}', prereq).replace('{progress}', str(int(progress))).replace('{library}', locked_library)
                    else:
                        freedom_message = f"🎉 FREEDOM! You watched {int(progress)}% - '{locked_library}' is now unlocked!"
                    print(f"   🗽 Sending freedom message...")
                    kill_stream(session_key, freedom_message)
            else:
                remaining = threshold - progress
                print(f"   ⏳ Need {remaining}% more to unlock")

    return 'OK', 200

# ── STARTUP ──

def open_browser():
    """Open browser after a short delay to let the server start"""
    import time
    time.sleep(1.5)
    webbrowser.open('http://localhost:5555')

if __name__ == '__main__':
    db.init_db()
    
    print("\n" + "="*50)
    print("🎬 PLEXTORTION")
    print("="*50)
    
    config = db.get_config()
    if config.get('plex_url'):
        server, account, sections = get_plex_connection()
        if server:
            print(f"✅ Connected to: {server.friendlyName}")
        else:
            print("⚠️ Could not connect to Plex - check settings")
    else:
        print("⚠️ No Plex configured - open browser to set up")
    
    # Show active ransoms
    ransoms = db.get_active_ransoms()
    if ransoms:
        print(f"\n📋 Active ransoms: {len(ransoms)}")
        for r in ransoms:
            print(f"   • {r['username']}: watch '{r['prerequisite']}' ({r['threshold']}%) to unlock '{r['locked_library']}'")
    
    local_ip = get_local_ip()
    print(f"\n🌐 Admin dashboard: http://{local_ip}:5555")
    print(f"🔗 Webhook URL: http://{local_ip}:5555/webhook")
    print("="*50 + "\n")
    
    # Open browser in background thread
    threading.Thread(target=open_browser, daemon=True).start()
    
    app.run(host='0.0.0.0', port=5555, debug=False)
