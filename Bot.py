import discord
import requests
import json
import os
import asyncio
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from urllib.parse import urlencode

print("🚀 STARTING BOT...")

# Load config safely from Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
MAIN_SERVER = 1552933219354284113 

if not BOT_TOKEN or not CLIENT_ID or not CLIENT_SECRET:
    print("❌ ERROR: Missing secrets in Environment Variables!")
    exit(1)

print(f"✅ Config loaded | Client ID: {CLIENT_ID}")

# --- ROLE LIMIT CONFIGURATION ---
ROLE_JOIN_LIMITS = {
    1553338998003466241: 5,    # Free
    1553706783208636626: 7,    # Bronze
    1553708035443003402: 10,   # Gold
    1553708129001414656: 25,   # Premium
    1553708171514740816: 35,   # Booster
    1553708235230281748: 50,   # Diamond
    1553708288892469329: 90,   # Emerald
    1553708334543151114: 160   # Ruby
}

# Channel Restrictions
GET_TOKEN_CHANNEL = 1557255357779419197
DJOIN_CHANNEL = 1557255395502985276

# YOUR NEW NETLIFY REDIRECT URL
REDIRECT_URL = "https://comforting-douhua-d292ab.netlify.app/"

def load_limits():
    if os.path.exists('limits.json'):
        with open('limits.json', 'r') as f: return json.load(f)
    return {}

def save_limits(data):
    with open('limits.json', 'w') as f: json.dump(data, f, indent=4)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=['!', '?'], intents=intents)
bot.remove_command("help")

server_join_times = {}

@bot.event
async def on_ready():
    print(f' Bot is ready: {bot.user}')
    await bot.tree.sync()
    
    for guild in bot.guilds:
        if guild.id != MAIN_SERVER:
            server_join_times[guild.id] = datetime.now()
    
    check_server_ages.start()

@tasks.loop(hours=24)
async def check_server_ages():
    """Auto-leaves servers after 14 days to keep the bot safe from Discord bans"""
    for guild in bot.guilds:
        if guild.id == MAIN_SERVER: continue
        gid, gname = guild.id, guild.name
        age = None
        
        if gid in server_join_times:
            age = datetime.now() - server_join_times[gid]
        else:
            server_join_times[gid] = datetime.now()
            age = timedelta(0)
            
        if age >= timedelta(days=14):
            try:
                print(f" Leaving {gname} ({gid}) - Age: {age.days} days")
                await guild.leave()
                mg = bot.get_guild(MAIN_SERVER)
                if mg:
                    for c in mg.text_channels:
                        if c.permissions_for(mg.me).send_messages:
                            await c.send(embed=discord.Embed(
                                title="🚪 Bot Left Server",
                                description=f"**Server:** {gname}\n**ID:** {gid}\n**Reason:** Exceeded 14 days",
                                color=0xED4245, timestamp=datetime.now()
                            ))
                            break
                if gid in server_join_times: del server_join_times[gid]
            except Exception as e: print(f"❌ Error leaving {gname}: {e}")

@bot.event
async def on_guild_join(guild):
    if guild.id != MAIN_SERVER:
        server_join_times[guild.id] = datetime.now()
        mg = bot.get_guild(MAIN_SERVER)
        if mg:
            for c in mg.text_channels:
                if c.permissions_for(mg.me).send_messages:
                    await c.send(embed=discord.Embed(
                        title="🏠 Bot Joined Server",
                        description=f"**Server:** {guild.name}\n**ID:** {guild.id}\n**Members:** {guild.member_count}",
                        color=0x57F287, timestamp=datetime.now()
                    ))
                    break

@bot.event
async def on_guild_remove(guild):
    if guild.id in server_join_times: del server_join_times[guild.id]

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Command not found. Use `!help`")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send(f"❌ You lack permissions: {error.missing_perms}")
    else:
        print(f"❌ Command error: {error}")

# ================= AUTH & JOIN LOGIC =================
def refresh_access_token(refresh_token):
    try:
        resp = requests.post('https://discord.com/api/v10/oauth2/token', data={
            'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
            'grant_type': 'refresh_token', 'refresh_token': refresh_token
        })
        return resp.json() if resp.status_code == 200 else None
    except: return None

def get_valid_token(uid, access, refresh):
    r = requests.get('https://discord.com/api/v10/users/@me', headers={'Authorization': f'Bearer {access}'})
    if r.status_code == 200: return access
    new = refresh_access_token(refresh)
    if new:
        update_token_in_file(uid, new['access_token'], new['refresh_token'])
        return new['access_token']
    return None

def update_token_in_file(uid, new_acc, new_ref):
    if not os.path.exists('auths.txt'): return False
    with open('auths.txt', 'r', encoding='utf-8') as f: lines = f.readlines()
    updated, new_lines = False, []
    for line in lines:
        line = line.strip()
        if not line: continue
        parts = line.split(',')
        if len(parts) >= 3 and parts[0] == uid:
            new_lines.append(f"{uid},{new_acc},{new_ref}\n")
            updated = True
        else: new_lines.append(line + '\n')
    if updated:
        with open('auths.txt', 'w', encoding='utf-8') as f: f.writelines(new_lines)
    return updated

@bot.hybrid_command(name='get_token')
async def get_auth_token(ctx):
    if ctx.channel.id != GET_TOKEN_CHANNEL:
        await ctx.send(f"⛔ This command can only be used in <#{GET_TOKEN_CHANNEL}>!", delete_after=10)
        return
    
    oauth_url = f"https://discord.com/oauth2/authorize?{urlencode({
        'client_id': CLIENT_ID, 'response_type': 'code',
        'redirect_uri': REDIRECT_URL, 'scope': 'identify guilds.join', 'prompt': 'consent'
    })}"
    await ctx.send(embed=discord.Embed(title="🔐 Authentication Required", 
        description="**Click below to authenticate:**", color=0x5865F2
    ).add_field(name="🔗 Link", value=f"[**CLICK HERE**]({oauth_url})", inline=False))

@bot.hybrid_command(name='auth')
async def authenticate_user(ctx, authorization_code: str):
    msg = await ctx.send("🔄 Authenticating...")
    token_resp = requests.post('https://discord.com/api/v10/oauth2/token', data={
        'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code', 'code': authorization_code.strip(),
        'redirect_uri': REDIRECT_URL
    })
    if token_resp.status_code != 200:
        await msg.edit(content=f"❌ Failed: {token_resp.json().get('error_description')}"); return
    
    t = token_resp.json()
    uid = str(ctx.author.id)
    entry = f"{uid},{t['access_token']},{t['refresh_token']}\n"
    
    existing = []
    if os.path.exists('auths.txt'):
        with open('auths.txt', 'r', encoding='utf-8') as f: existing = f.readlines()
    
    cleaned = [l+'\n' for l in existing if l.strip() and l.strip().split(',')[0] != uid]
    cleaned.append(entry)
    
    with open('auths.txt', 'w', encoding='utf-8') as f: f.writelines(cleaned)
    await msg.edit(content="", embed=discord.Embed(title="✅ Authenticated!", 
        description=f"**{ctx.author.name}** is now ready!", color=0x57F287))

@bot.hybrid_command(name='check_my_token')
async def check_my_token(ctx):
    if not os.path.exists('auths.txt'):
        await ctx.send("❌ No auth file found."); return
    
    uid = str(ctx.author.id)
    with open('auths.txt', 'r') as f:
        for line in f:
            parts = line.strip().split(',')
            if len(parts) >= 3 and parts[0] == uid:
                access_token = parts[1]
                r = requests.get('https://discord.com/api/v10/users/@me', 
                               headers={'Authorization': f'Bearer {access_token}'})
                
                if r.status_code == 200:
                    await ctx.send(embed=discord.Embed(title="✅ Token Valid",
                        description="Your authentication token is active!", color=0x57F287))
                else:
                    await ctx.send(embed=discord.Embed(title="❌ Token Expired",
                        description="Please run `!get_token` to re-authenticate.", color=0xED4245))
                return
    
    await ctx.send(embed=discord.Embed(title="⚠️ Not Authenticated",
        description="Run `!get_token` to authenticate.", color=0xF1C40F))

@bot.hybrid_command(name='djoin')
async def join_server(ctx, target_server_id: str):
    if ctx.channel.id != DJOIN_CHANNEL:
        await ctx.send(f"⛔ This command can only be used in <#{DJOIN_CHANNEL}>!", delete_after=10)
        return
        
    tg = bot.get_guild(int(target_server_id))
    if not tg: 
        await ctx.send(f"❌ Bot not in `{target_server_id}`"); return
    if not os.path.exists('auths.txt'):
        await ctx.send(" No authenticated users."); return
    
    limits = load_limits()
    mg = bot.get_guild(MAIN_SERVER)
    if not mg: await ctx.send(" Main server not found!"); return
    
    users = []
    with open('auths.txt', 'r') as f:
        for line in f:
            p = line.strip().split(',')
            if len(p)>=3: users.append({'user_id':p[0],'access_token':p[1],'refresh_token':p[2]})
    
    if not users: await ctx.send("❌ No valid users."); return
    
    status = await ctx.send(f"🚀 Processing {len(users)} users...")
    ok, fail, skip_role, skip_lim = 0, 0, 0, 0
    
    for i, u in enumerate(users):
        if i%5==0: 
            await status.edit(content=f"🚀 {i+1}/{len(users)} | ✅{ok} ❌{fail} ⏭️{skip_role+skip_lim}")
        
        member = mg.get_member(int(u['user_id']))
        if not member: skip_role+=1; continue
        
        allowed = 0
        for rid, lim in ROLE_JOIN_LIMITS.items():
            if member.get_role(rid): allowed=lim; break
        if allowed == 0: skip_role+=1; continue
        
        cur = limits.get(u['user_id'], 0)
        if cur >= allowed: skip_lim+=1; continue
        
        vt = get_valid_token(u['user_id'], u['access_token'], u['refresh_token'])
        if not vt: fail+=1; continue
        
        r = requests.put(f"https://discord.com/api/v10/guilds/{target_server_id}/members/{u['user_id']}",
            headers={"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"},
            json={"access_token": vt})
        
        if r.status_code in (201,204):
            ok += 1; limits[u['user_id']] = cur + 1
        else: fail += 1
        await asyncio.sleep(1)
    
    save_limits(limits)
    await status.edit(content="", embed=discord.Embed(title="🎯 Mass Join Done",
        description=f"**Server:** {tg.name}\n✅ {ok} | ❌ {fail} | ⏭️ {skip_role+skip_lim}",
        color=0x57F287 if ok>0 else 0xED4245))

@bot.hybrid_command(name='list_users')
async def list_authenticated_users(ctx):
    if not os.path.exists('auths.txt'):
        await ctx.send("❌ No users are authenticated yet.")
        return
    
    users = []
    with open('auths.txt', 'r') as auth_file:
        for line_num, line in enumerate(auth_file, 1):
            line = line.strip()
            if not line: continue
            parts = line.split(',')
            if len(parts) >= 1:
                user_id = parts[0]
                users.append(f"`{line_num}.` <@{user_id}>")
    
    if not users:
        await ctx.send("❌ No valid authenticated users found.")
        return
    
    embed = discord.Embed(title="📋 AUTHENTICATED USERS", description=f"**Total: {len(users)} users**", color=0x5865F2)
    embed.add_field(name="Users", value="\n".join(users[:20]), inline=False)
    await ctx.send(embed=embed)

@bot.hybrid_command(name='help')
async def show_help(ctx):
    embed = discord.Embed(title="🤖 Bot Commands", color=0x5865F2)
    embed.add_field(name="🔐 Authentication", value="`!get_token` - Get auth link\n`!auth CODE` - Verify code\n`!check_my_token` - Check status", inline=False)
    embed.add_field(name="🚀 Mass Join", value="`!djoin SERVER_ID` - Add users to server\n`!list_users` - View authenticated users", inline=False)
    await ctx.send(embed=embed)
import threading
import time
from aiohttp import web

async def handle_ping(request):
    return web.Response(text="OK")

app = web.Application()
app.router.add_get('/ping', handle_ping)

def run_keepalive():
    web.run_app(app, host='0.0.0.0', port=8080, print=None)

# Start keep-alive in a separate thread so it doesn't block the bot
threading.Thread(target=run_keepalive, daemon=True).start()
print("🟢 Keep-alive endpoint running on :8080/ping")

if __name__ == "__main__":
    print("🎯 Starting Mass Join Bot...")
    try: bot.run(BOT_TOKEN)
    except Exception as e: print(f"❌ Failed: {e}")
