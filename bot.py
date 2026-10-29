import os
import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta
from flask import Flask, redirect, url_for, session, request
import requests
import base64
import threading

# 1. إعداد خادم الويب (Flask) للبقاء في حالة تشغيل 24/7 ولوحة التحكم (Dashboard)
app = Flask(__name__)
app.secret_key = os.urandom(24)

# قم بتحديث هذه البيانات لاحقاً عند الحاجة للوحة التحكم عبر Discord OAuth2
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "YOUR_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "https://your-app-name.koyeb.app/callback")
DISCORD_API_ENDPOINT = "https://discord.com/api/v10"

@app.route('/')
def home():
    return "Secure Discord Bot & Dashboard Active 24/7!"

# مسارات لوحة التحكم (Discord OAuth2 & Guild Management)
@app.route('/login')
def login():
    return redirect(f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds")

@app.route('/callback')
def callback():
    code = request.args.get('code')
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    r = requests.post(f"{DISCORD_API_ENDPOINT}/oauth2/token", data=data, headers=headers)
    token_json = r.json()
    access_token = token_json.get('access_token')
    
    if not access_token:
        return "❌ فشل المصادقة مع ديسكورد.", 400
        
    session['token'] = access_token
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    token = session.get('token')
    if not token:
        return redirect('/login')
    
    headers = {'Authorization': f"Bearer {token}"}
    guilds_r = requests.get(f"{DISCORD_API_ENDPOINT}/users/@me/guilds", headers=headers)
    guilds = guilds_r.json()
    
    if isinstance(guilds, dict) and guilds.get('code') == 0:
        return redirect('/login')
        
    # تصفية السيرفرات التي يملك المستخدم صلاحية الإدارة فيها (Manage Server = 0x20)
    admin_guilds = [g for g in guilds if (int(g['permissions']) & 0x20) == 0x20]
    
    html = "<h1>لوحة تحكم السيرفرات</h1><ul>"
    for guild in admin_guilds:
        html += f"<li>{guild['name']} - <a href='/configure/{guild['id']}'>إدارة السيرفر وتغيير الاسم/الصورة</a></li>"
    html += "</ul>"
    
    return html

@app.route('/configure/<guild_id>', methods=['GET', 'POST'])
def configure(guild_id):
    token = session.get('token')
    if not token:
        return redirect('/login')
        
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_TOKEN")
    
    if request.method == 'POST':
        new_name = request.form.get('guild_name')
        image_file = request.files.get('guild_icon')
        
        payload = {}
        if new_name:
            payload['name'] = new_name
            
        if image_file and image_file.filename != '':
            image_bytes = image_file.read()
            encoded_image = base64.b64encode(image_bytes).decode('utf-8')
            payload['icon'] = f"data:image/jpeg;base64,{encoded_image}"
            
        headers_bot = {
            'Authorization': f"Bot {DISCORD_BOT_TOKEN}",
            'Content-Type': 'application/json'
        }
        
        r = requests.patch(f"{DISCORD_API_ENDPOINT}/guilds/{guild_id}", headers=headers_bot, json=payload)
        if r.status_code == 200:
            return "✅ تم تحديث بيانات السيرفر بنجاح! <a href='/dashboard'>العودة</a>"
        else:
            return f"❌ فشل التحديث. تأكد أن البوت يمتلك صلاحية Manage Server في هذا السيرفر. (رمز الخطأ: {r.status_code})"

    return '''
        <h2>تعديل إعدادات السيرفر</h2>
        <form method="POST" enctype="multipart/form-data">
            اسم السيرفر الجديد: <input type="text" name="guild_name"><br><br>
            أيقونة السيرفر (صورة): <input type="file" name="guild_icon"><br><br>
            <input type="submit" value="حفظ التغييرات">
        </form>
        <br><a href="/dashboard">العودة للوحة التحكم</a>
    '''

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run_web)
    t.start()


# 2. إعدادات بوت الديسكورد وأوامر الإشراف
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

class UltimateBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("[+] Slash commands synced successfully.")

bot = UltimateBot()

@bot.event
async def on_ready():
    print(f"[+] Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Game(name="حماية وإدارة السيرفرات 24/7"))

# أوامر الإشراف المتقدمة
@bot.tree.command(name="mute", description="إسكات عضو في الشات مع تحديد المدة (بالدقائق) والسبب")
@app_commands.checks.has_permissions(moderate_members=True)
async def mute_member(interaction: discord.Interaction, member: discord.Member, duration_minutes: int, reason: str):
    try:
        time_delta = timedelta(minutes=duration_minutes)
        await member.timeout(time_delta, reason=reason)
        
        embed = discord.Embed(title="تم إسكات العضو بنجاح", color=discord.Color.red())
        embed.add_field(name="العضو المستهدف", value=member.mention, inline=True)
        embed.add_field(name="المدة", value=f"{duration_minutes} دقيقة", inline=True)
        embed.add_field(name="السبب", value=reason, inline=False)
        embed.set_footer(text=f"بواسطة المشرف: {interaction.user.name}")
        
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"تعذر تنفيذ الإسكات: {e}", ephemeral=True)

@bot.tree.command(name="unmute", description="فك الإسكات والسماح للعضو بالتكلم مرة أخرى")
@app_commands.checks.has_permissions(moderate_members=True)
async def unmute_member(interaction: discord.Interaction, member: discord.Member, reason: str = "انتهاء العقوبة أو العفو"):
    try:
        await member.timeout(None, reason=reason)
        
        embed = discord.Embed(title="تم فك الإسكات عن العضو", color=discord.Color.green())
        embed.add_field(name="العضو", value=member.mention, inline=True)
        embed.add_field(name="السبب", value=reason, inline=False)
        
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"تعذر فك الإسكات: {e}", ephemeral=True)

@bot.tree.command(name="warn", description="إصدار تحذير رسمي لعضو مع ذكر السبب وتسجيله")
@app_commands.checks.has_permissions(manage_messages=True)
async def warn_member(interaction: discord.Interaction, member: discord.Member, reason: str):
    embed = discord.Embed(title="تنبيه / تحذير إداري", color=discord.Color.orange())
    embed.add_field(name="العضو المخالف", value=member.mention, inline=True)
    embed.add_field(name="المشرف المسؤول", value=interaction.user.mention, inline=True)
    embed.add_field(name="السبب", value=reason, inline=False)
    
    try:
        await member.send(f"⚠️ لقد تلقيت تحذيراً في سيرفر **{interaction.guild.name}** بسبب: {reason}")
    except:
        pass

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="unwarn", description="إزالة تحذير أو سجل سابق عن العضو")
@app_commands.checks.has_permissions(manage_messages=True)
async def unwarn_member(interaction: discord.Interaction, member: discord.Member, reason: str = "مراجعة وسحب التحذير"):
    embed = discord.Embed(title="إزالة تحذير إداري", color=discord.Color.blue())
    embed.add_field(name="العضو", value=member.mention, inline=True)
    embed.add_field(name="التوضيح", value=reason, inline=False)
    
    await interaction.response.send_message(embed=embed)

@mute_member.error
@unmute_member.error
@warn_member.error
@unwarn_member.error
async def moderation_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ عذراً، لا تمتلك الصلاحيات الكافية لتنفيذ هذا الأمر الإداري.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ حدث خطأ غير متوقع: {error}", ephemeral=True)

# 3. تشغيل النظام
if __name__ == "__main__":
    keep_alive()
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("[!] Error: DISCORD_TOKEN environment variable not found.")
    else:
        bot.run(TOKEN)
