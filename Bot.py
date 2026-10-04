import discord
import requests
import json
import os
import asyncio
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import time
from urllib.parse import urlencode

print(" STARTING BOT...")

# Load config safely from Environment Variables (Render)
BOT_TOKEN = os.getenv("BOT_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
MAIN_SERVER = 1437381878310109185 

if not BOT_TOKEN or not CLIENT_ID or not CLIENT_SECRET:
    print("❌ ERROR: Missing secrets in Environment Variables!")
    exit(1)

print(f"✅ Config loaded | Client ID: {CLIENT_ID}")

# --- ROLE LIMIT CONFIGURATION ---
ROLE_JOIN_LIMITS = {
    1553338998003466241: 5,    # Free Role (5 members)
    1553706783208636626: 7,    # Bronze Role (7 members)
    1553708035443003402: 10,   # Gold Role (10 members)
    1553708129001414656: 25,   # Premium Role (25 members)
    1553708171514740816: 35,   # Booster Role (35 members)
    1553708235230281748: 50,   # Diamond Role (50 members)
    1553708288892469329: 90,   # Emerald Role (90 members)
    1553708334543151114: 160   # Ruby Role (160 members)
}

def load_limits():
    if os.path.exists('limits.json'):
        with open('limits.json', 'r') as f: return json.load(f)
    return {}

def save_limits(data):
    with open('limits.json', 'w') as f: json.dump(data, f, indent=4)

# Create bot with ALL required intents for mod/tickets/reactions
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix=['!', '?'], intents=intents)
bot.remove_command("help")

server_join_times = {}

@bot.event
async def on_ready():
    print(f'🎯 Bot is ready: {bot.user}')
    await bot.tree.sync()
    
    for guild in bot.guilds:
        if guild.id != MAIN_SERVER:
            server_join_times[guild.id] = datetime.now()
    
    check_server_ages.start()

@tasks.loop(hours=24)
async def check_server_ages():
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
                print(f"🚪 Leaving {gname} ({gid}) - Age: {age.days} days")
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
    redirect_url = "https://memberswave.netlify.app"
    oauth_url = f"https://discord.com/oauth2/authorize?{urlencode({
        'client_id': CLIENT_ID, 'response_type': 'code',
        'redirect_uri': redirect_url, 'scope': 'identify guilds.join', 'prompt': 'consent'
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
        'redirect_uri': "https://memberswave.netlify.app"
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

@bot.hybrid_command(name='djoin')
async def join_server(ctx, target_server_id: str):
    tg = bot.get_guild(int(target_server_id))
    if not tg: 
        await ctx.send(f"❌ Bot not in `{target_server_id}`"); return
    if not os.path.exists('auths.txt'):
        await ctx.send("❌ No authenticated users."); return
    
    limits = load_limits()
    mg = bot.get_guild(MAIN_SERVER)
    if not mg: await ctx.send("❌ Main server not found!"); return
    
    users = []
    with open('auths.txt', 'r') as f:
        for line in f:
            p = line.strip().split(',')
            if len(p)>=3: users.append({'user_id':p[0],'access_token':p[1],'refresh_token':p[2]})
    
    if not users: await ctx.send("❌ No valid users."); return
    
    status = await ctx.send(f" Processing {len(users)} users...")
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

# ================= MODERATION COMMANDS =================
@bot.hybrid_command(name='kick')
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(embed=discord.Embed(title="👢 Kicked", 
        description=f"**{member}** was kicked.\n**Reason:** {reason}", color=0xED4245))

@bot.hybrid_command(name='ban')
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.ban(reason=reason)
    await ctx.send(embed=discord.Embed(title="🔨 Banned", 
        description=f"**{member}** was banned.\n**Reason:** {reason}", color=0xED4245))

@bot.hybrid_command(name='timeout')
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason="No reason provided"):
    until = datetime.utcnow() + timedelta(minutes=minutes)
    await member.timeout(until, reason=reason)
    await ctx.send(embed=discord.Embed(title=" Timed Out", 
        description=f"**{member}** timed out for {minutes} mins.\n**Reason:** {reason}", color=0xF1C40F))

@bot.hybrid_command(name='purge')
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    deleted = await ctx.channel.purge(limit=amount+1)
    await ctx.send(f"🧹 Deleted {len(deleted)-1} messages.", delete_after=5)

@bot.hybrid_command(name='embed')
@commands.has_permissions(manage_messages=True)
async def send_embed(ctx, title: str, description: str, color: str = "5865F2"):
    hex_color = int(color.replace("#",""), 16) if color.startswith("#") else int(color, 16)
    await ctx.send(embed=discord.Embed(title=title, description=description, color=hex_color))

# ================= REACTION ROLES =================
reaction_roles = {}

@bot.hybrid_command(name='rr_create')
@commands.has_permissions(manage_roles=True)
async def rr_create(ctx, message_id: int, emoji: str, role: discord.Role):
    try:
        msg = await ctx.fetch_message(message_id)
        await msg.add_reaction(emoji)
        reaction_roles[(msg.id, emoji)] = role.id
        with open('reaction_roles.json', 'w') as f: json.dump(reaction_roles, f)
        await ctx.send(f"✅ Reaction role set: {emoji} → {role.mention}")
    except Exception as e: await ctx.send(f"❌ Error: {e}")

@bot.event
async def on_raw_reaction_add(payload):
    key = (payload.message_id, str(payload.emoji))
    if key in reaction_roles:
        guild = bot.get_guild(payload.guild_id)
        if guild:
            role = guild.get_role(reaction_roles[key])
            if role: await payload.member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    key = (payload.message_id, str(payload.emoji))
    if key in reaction_roles:
        guild = bot.get_guild(payload.guild_id)
        if guild:
            member = guild.get_member(payload.user_id)
            role = guild.get_role(reaction_roles[key])
            if member and role: await member.remove_roles(role)

# Load reaction roles on startup
if os.path.exists('reaction_roles.json'):
    with open('reaction_roles.json', 'r') as f: reaction_roles = json.load(f)

# ================= TICKET SYSTEM =================
ticket_categories = {}

@bot.hybrid_command(name='ticket_setup')
@commands.has_permissions(manage_channels=True)
async def ticket_setup(ctx, category: discord.CategoryChannel):
    ticket_categories[ctx.guild.id] = category.id
    with open('tickets.json', 'w') as f: json.dump(ticket_categories, f)
    await ctx.send(f"✅ Tickets will be created in **{category.name}**")

@bot.hybrid_command(name='ticket')
async def create_ticket(ctx):
    cid = ticket_categories.get(ctx.guild.id)
    if not cid:
        await ctx.send("❌ Tickets not configured. Admin must run `!ticket_setup CATEGORY`"); return
    
    cat = ctx.guild.get_channel(cid)
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        ctx.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }
    channel = await cat.create_text_channel(f"ticket-{ctx.author.name}", overwrites=overwrites)
    await channel.send(embed=discord.Embed(
        title="🎫 Support Ticket",
        description=f"Hello {ctx.author.mention}! Staff will be with you shortly.\nType `!close` to close this ticket.",
        color=0x5865F2
    ))
    await ctx.send(f"✅ Ticket created: {channel.mention}", delete_after=5)

@bot.hybrid_command(name='close')
@commands.has_permissions(manage_channels=True)
async def close_ticket(ctx):
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ This is not a ticket channel."); return
    await ctx.channel.delete()

# Load ticket categories on startup
if os.path.exists('tickets.json'):
    with open('tickets.json', 'r') as f: ticket_categories = json.load(f)

# ================= HELP COMMAND =================
@bot.hybrid_command(name='help')
async def show_help(ctx):
    embed = discord.Embed(title="🤖 Full Bot Commands", color=0x5865F2)
    embed.add_field(name="🔐 Auth & Join", value="`!get_token` `!auth CODE` `!djoin SERVER_ID`", inline=False)
    embed.add_field(name="️ Moderation", value="`!kick` `!ban` `!timeout MIN` `!purge AMT` `!embed TITLE DESC COLOR`", inline=False)
    embed.add_field(name="⭐ Reaction Roles", value="`!rr_create MSG_ID EMOJI @ROLE`", inline=False)
    embed.add_field(name="🎫 Tickets", value="`!ticket_setup CAT` `!ticket` `!close`", inline=False)
    embed.add_field(name="🔧 Utility", value="`!servers` `!list_users` `!check_tokens` `!invite`", inline=False)
    await ctx.send(embed=embed)

if __name__ == "__main__":
    print(" Starting full-featured Discord bot...")
    try: bot.run(BOT_TOKEN)
    except Exception as e: print(f"❌ Failed: {e}")
