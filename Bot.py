import discord
import requests
import json
import os
import asyncio
import threading
from discord.ext import commands, tasks
from discord import ui
from datetime import datetime, timedelta
from urllib.parse import urlencode
from aiohttp import web

print("🌱 STARTING GROWXGROW™ ULTIMATE...")

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
MAIN_SERVER = int(os.getenv("MAIN_SERVER", "0"))
STICKY_CHANNEL_ID = int(os.getenv("STICKY_CHANNEL_ID", "0"))
AUTH_CHANNEL_ID = int(os.getenv("AUTH_CHANNEL_ID", "0"))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "0"))

if not BOT_TOKEN or not CLIENT_ID or not CLIENT_SECRET:
    print("❌ ERROR: Missing secrets in Environment Variables!")
    exit(1)

# Role Limits & Status Config
ROLE_JOIN_LIMITS = {
    1553338998003466241: 5, 1553706783208636626: 7, 
    1553708035443003402: 10, 1553708129001414656: 25,
    1553708171514740816: 35, 1553708235230281748: 50,
    1553708288892469329: 90, 1553708334543151114: 160
}
GET_TOKEN_CHANNEL = 1557255357779419197
DJOIN_CHANNEL = 1557255395502985276
REDIRECT_URL = "https://comforting-douhua-d292ab.netlify.app/"
CUSTOM_STATUS_TEXT = "Free members at https://discord.gg/8sh6fezN5n"
BRONZE_ROLE_ID = 1553706783208636626

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix='?', intents=intents)
bot.remove_command("help")

# ================= KEEP ALIVE (RENDER FIX) =================
async def handle_ping(request):
    return web.Response(text="OK")

app = web.Application()
app.router.add_get('/ping', handle_ping)

def run_keepalive():
    web.run_app(app, host='0.0.0.0', port=8080, print=None)

threading.Thread(target=run_keepalive, daemon=True).start()
print("🟢 Keep-alive active on :8080/ping")

# ================= TICKET SYSTEM (UI) =================
class TicketDropdown(ui.StringSelect):
    def __init__(self):
        super().__init__(placeholder="Select a ticket category", min_values=1, max_values=1, options=[
            discord.SelectOption(label="Support Ticket", description="Get help from our team", value="support", emoji=""),
            discord.SelectOption(label="Plans Buying Ticket", description="Purchase or upgrade a plan", value="plans", emoji="💳"),
            discord.SelectOption(label="Issue / Bug Report Ticket", description="Report a bug or issue", value="bug", emoji=""),
            discord.SelectOption(label="Other Tickets", description="Everything else", value="other", emoji="📝")
        ])

    async def callback(self, interaction: discord.Interaction):
        category = bot.get_channel(TICKET_CATEGORY_ID)
        if not category:
            await interaction.response.send_message(" Ticket category not configured.", ephemeral=True)
            return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        
        cat_name = self.values[0]
        channel = await category.create_text_channel(name=f"ticket-{interaction.user.name}-{cat_name}", overwrites=overwrites)
        
        embed = discord.Embed(title=f" {cat_name.upper()} TICKET", description=f"Hello {interaction.user.mention}! Support will be with you shortly.\nType `?close` to close this ticket.", color=0xCD7F32)
        await channel.send(embed=embed)
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

class TicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())

# ================= STICKY LOGGER & AUTO LIST =================
sticky_msg_id = None
list_msg_id = None

@tasks.loop(seconds=30)
async def background_tasks():
    global sticky_msg_id, list_msg_id
    
    # 1. Sticky Status Logger
    try:
        ch = bot.get_channel(STICKY_CHANNEL_ID)
        if ch:
            guild = bot.get_guild(MAIN_SERVER)
            role = guild.get_role(BRONZE_ROLE_ID) if guild else None
            count = len(role.members) if role else 0
            
            embed = discord.Embed(title="GrowXGrow™ Live Status", description=CUSTOM_STATUS_TEXT, color=0xCD7F32, timestamp=datetime.utcnow())
            embed.add_field(name=" Bronze Holders", value=str(count), inline=True)
            embed.set_footer(text="GrowXGrow™ | Auto-updates every 30s")
            
            if sticky_msg_id:
                try:
                    msg = await ch.fetch_message(sticky_msg_id)
                    await msg.edit(embed=embed)
                except: sticky_msg_id = None
            if not sticky_msg_id:
                msg = await ch.send(embed=embed)
                sticky_msg_id = msg.id
    except Exception as e: print(f"Sticky Error: {e}")

    # 2. Auto List Users in Auth Channel
    try:
        ach = bot.get_channel(AUTH_CHANNEL_ID)
        if ach and os.path.exists('auths.txt'):
            with open('auths.txt', 'r') as f:
                users = [f"<@{line.strip().split(',')[0]}>" for line in f if line.strip()]
            
            embed = discord.Embed(title="GrowXGrow™ - Authenticated Users", description=f"**Total:** {len(users)} users", color=0x5865F2)
            embed.add_field(name="Users", value="\n".join(users[:20]) if users else "None", inline=False)
            
            if list_msg_id:
                try:
                    msg = await ach.fetch_message(list_msg_id)
                    await msg.edit(embed=embed)
                except: list_msg_id = None
            if not list_msg_id:
                msg = await ach.send(embed=embed)
                list_msg_id = msg.id
    except Exception as e: print(f"List Error: {e}")

# ================= STATUS TO ROLE =================
@bot.event
async def on_member_update(before, after):
    if before.guild.id != MAIN_SERVER: return
    role = before.guild.get_role(BRONZE_ROLE_ID)
    if not role: return
    
    has_status = after.activity and isinstance(after.activity, discord.CustomActivity) and after.activity.name == CUSTOM_STATUS_TEXT
    has_role = role in after.roles
    
    try:
        if has_status and not has_role: await after.add_roles(role)
        elif not has_status and has_role: await after.remove_roles(role)
    except: pass

# ================= AUTH & JOIN LOGIC =================
def load_limits():
    return json.load(open('limits.json', 'r')) if os.path.exists('limits.json') else {}

def save_limits(data):
    with open('limits.json', 'w') as f: json.dump(data, f, indent=4)

@bot.hybrid_command(name='get_token')
async def get_token(ctx):
    if ctx.channel.id != GET_TOKEN_CHANNEL: return await ctx.send("⛔ Wrong channel!", delete_after=5)
    url = f"https://discord.com/oauth2/authorize?{urlencode({'client_id': CLIENT_ID, 'response_type': 'code', 'redirect_uri': REDIRECT_URL, 'scope': 'identify guilds.join'})}"
    await ctx.send(embed=discord.Embed(title="🔐 Authenticate", description=f"[CLICK HERE]({url})", color=0x5865F2))

@bot.hybrid_command(name='auth')
async def auth(ctx, code: str):
    msg = await ctx.send("🔄 Processing...")
    resp = requests.post('https://discord.com/api/v10/oauth2/token', data={'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URL})
    if resp.status_code != 200: return await msg.edit(content="❌ Invalid code.")
    
    data = resp.json()
    uid = str(ctx.author.id)
    lines = []
    if os.path.exists('auths.txt'):
        with open('auths.txt', 'r') as f: lines = [l for l in f.readlines() if not l.strip().startswith(uid)]
    lines.append(f"{uid},{data['access_token']},{data['refresh_token']}\n")
    
    with open('auths.txt', 'w') as f: f.writelines(lines)
    await msg.edit(embed=discord.Embed(title="✅ Authenticated!", color=0x57F287))

@bot.hybrid_command(name='djoin')
async def djoin(ctx, server_id: str):
    if ctx.channel.id != DJOIN_CHANNEL: return await ctx.send("⛔ Wrong channel!", delete_after=5)
    target = bot.get_guild(int(server_id))
    if not target: return await ctx.send("❌ Bot not in server.")
    
    mg = bot.get_guild(MAIN_SERVER)
    limits = load_limits()
    users = []
    if os.path.exists('auths.txt'):
        with open('auths.txt', 'r') as f:
            for line in f:
                p = line.strip().split(',')
                if len(p) >= 3: users.append({'id': p[0], 'acc': p[1], 'ref': p[2]})
    
    status_msg = await ctx.send(f"🚀 Joining {len(users)} users...")
    ok, fail = 0, 0
    
    for u in users:
        member = mg.get_member(int(u['id']))
        if not member: continue
        
        allowed = next((lim for rid, lim in ROLE_JOIN_LIMITS.items() if member.get_role(rid)), 0)
        if allowed == 0 or limits.get(u['id'], 0) >= allowed: continue
        
        r = requests.put(f"https://discord.com/api/v10/guilds/{server_id}/members/{u['id']}", headers={"Authorization": f"Bot {BOT_TOKEN}"}, json={"access_token": u['acc']})
        if r.status_code in (201, 204):
            ok += 1; limits[u['id']] = limits.get(u['id'], 0) + 1
        else: fail += 1
        await asyncio.sleep(1.5) # SAFE DELAY FOR RENDER FREE TIER
        
    save_limits(limits)
    await status_msg.edit(content=f"✅ Done! Joined: {ok} | Failed: {fail}")

# ================= MODERATION & TICKETS =================
@bot.hybrid_command(name='kick')
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=""):
    await member.kick(reason=reason)
    await ctx.send(embed=discord.Embed(title="👢 Kicked", description=f"{member.mention} | {reason}", color=0xED4245))

@bot.hybrid_command(name='ban')
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=""):
    await member.ban(reason=reason)
    await ctx.send(embed=discord.Embed(title="🔨 Banned", description=f"{member.mention} | {reason}", color=0xED4245))

@bot.hybrid_command(name='purge')
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 Purged {amount} messages.", delete_after=5)

@bot.hybrid_command(name='ticket_panel')
@commands.has_permissions(manage_channels=True)
async def ticket_panel(ctx):
    embed = discord.Embed(title="GrowXGrow™ Support", description="Welcome to the support center.\n\nPlease select a category from the dropdown below to open a ticket. Our team will respond as soon as possible.", color=0xCD7F32)
    await ctx.send(embed=embed, view=TicketView())

@bot.hybrid_command(name='close')
@commands.has_permissions(manage_channels=True)
async def close(ctx):
    if "ticket-" in ctx.channel.name: await ctx.channel.delete()

@bot.event
async def on_ready():
    print(f'✅ GrowXGrow™ Ready: {bot.user}')
    await bot.tree.sync()
    background_tasks.start()
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="GrowXGrow™"))

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
