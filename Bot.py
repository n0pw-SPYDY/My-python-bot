import discord
import requests
import json
import os
import asyncio
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import time
from urllib.parse import urlencode

print("🚀 STARTING BOT...")

# Load config safely from Environment Variables (Render)
BOT_TOKEN = os.getenv("BOT_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
MAIN_SERVER = 1437381878310109185  # Your main server ID

if not BOT_TOKEN or not CLIENT_ID or not CLIENT_SECRET:
    print("❌ ERROR: Missing BOT_TOKEN, CLIENT_ID, or CLIENT_SECRET in Environment Variables!")
    exit(1)

print(f"✅ Config loaded from Environment")
print(f"🆔 Client ID: {CLIENT_ID}")
print(f"🏠 Main Server: {MAIN_SERVER}")

# --- ROLE LIMIT CONFIGURATION ---
# Format: { ROLE_ID: MAX_JOINS_PER_COMMAND }
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

# Helper functions to track joins
def load_limits():
    if os.path.exists('limits.json'):
        with open('limits.json', 'r') as f:
            return json.load(f)
    return {}

def save_limits(limits_data):
    with open('limits.json', 'w') as f:
        json.dump(limits_data, f, indent=4)

# Create bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Added for better member handling

bot = commands.Bot(command_prefix=['!', '?'], intents=intents)
bot.remove_command("help")

# Store server join times
server_join_times = {}

@bot.event
async def on_ready():
    print(f' Bot is ready: {bot.user}')
    
    # SYNC SLASH COMMANDS (Crucial for hybrid commands to work)
    await bot.tree.sync()
    print(f'📋 Synced commands: {[command.name for command in bot.commands]}')
    
    # Initialize server join times
    for guild in bot.guilds:
        if guild.id != MAIN_SERVER:
            server_join_times[guild.id] = datetime.now()
            print(f"📝 Tracking server: {guild.name} ({guild.id})")
    
    # Start the cleanup task
    check_server_ages.start()

@tasks.loop(hours=24)  # Run once per day
async def check_server_ages():
    """Check servers and leave if they're older than 14 days (except main server)"""
    print("🔍 Checking server ages...")
    
    for guild in bot.guilds:
        if guild.id == MAIN_SERVER:
            continue  # Never leave main server
        
        guild_id = guild.id
        guild_name = guild.name
        guild_age = None
        
        # Calculate age
        if guild_id in server_join_times:
            join_time = server_join_times[guild_id]
            guild_age = datetime.now() - join_time
        else:
            # If we don't have a join time, assume we joined now
            server_join_times[guild_id] = datetime.now()
            guild_age = timedelta(0)
        
        if guild_age >= timedelta(days=14):
            try:
                print(f"🚪 Leaving server {guild_name} ({guild_id}) - Age: {guild_age.days} days")
                await guild.leave()
                
                # Send notification to main server
                main_guild = bot.get_guild(MAIN_SERVER)
                if main_guild:
                    for channel in main_guild.text_channels:
                        if channel.permissions_for(main_guild.me).send_messages:
                            embed = discord.Embed(
                                title="🚪 Bot Left Server",
                                description=f"**Server:** {guild_name}\n**ID:** {guild_id}\n**Reason:** Server age ({guild_age.days} days) exceeded 14 days",
                                color=0xED4245,
                                timestamp=datetime.now()
                            )
                            await channel.send(embed=embed)
                            break
                
                if guild_id in server_join_times:
                    del server_join_times[guild_id]
                    
            except Exception as e:
                print(f"❌ Error leaving server {guild_name}: {e}")
        else:
            print(f"✅ Server {guild_name} is {guild_age.days} days old - OK")

@bot.event
async def on_guild_join(guild):
    """Track when bot joins a new server"""
    if guild.id != MAIN_SERVER:
        server_join_times[guild.id] = datetime.now()
        print(f" Bot joined new server: {guild.name} ({guild.id})")
        
        main_guild = bot.get_guild(MAIN_SERVER)
        if main_guild:
            for channel in main_guild.text_channels:
                if channel.permissions_for(main_guild.me).send_messages:
                    embed = discord.Embed(
                        title="🏠 Bot Joined Server",
                        description=f"**Server:** {guild.name}\n**ID:** {guild.id}\n**Members:** {guild.member_count}\n**Will leave after:** 14 days",
                        color=0x57F287,
                        timestamp=datetime.now()
                    )
                    await channel.send(embed=embed)
                    break

@bot.event
async def on_guild_remove(guild):
    """Remove server from tracking when bot leaves"""
    if guild.id in server_join_times:
        del server_join_times[guild.id]
        print(f"🗑️ Removed tracking for server: {guild.name} ({guild.id})")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Command not found. Use `!help` to see available commands.")
    else:
        print(f"❌ Command error: {error}")

def refresh_access_token(refresh_token):
    """Refresh an expired access token"""
    try:
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }
        
        response = requests.post('https://discord.com/api/v10/oauth2/token', data=data)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Token refresh failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ Token refresh error: {e}")
        return None

def get_valid_token(user_id, access_token, refresh_token):
    """Get a valid access token, refreshing if needed"""
    headers = {'Authorization': f'Bearer {access_token}'}
    test_response = requests.get('https://discord.com/api/v10/users/@me', headers=headers)
    
    if test_response.status_code == 200:
        return access_token  # Token is still valid
    
    print(f"🔄 Token expired for user {user_id}, refreshing...")
    new_tokens = refresh_access_token(refresh_token)
    
    if new_tokens:
        update_token_in_file(user_id, new_tokens['access_token'], new_tokens['refresh_token'])
        return new_tokens['access_token']
    else:
        print(f"❌ Failed to refresh token for user {user_id}")
        return None

def update_token_in_file(user_id, new_access_token, new_refresh_token):
    """Update tokens in auths.txt file"""
    try:
        if not os.path.exists('auths.txt'):
            return False
        
        with open('auths.txt', 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        updated = False
        new_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            parts = line.split(',')
            if len(parts) >= 3 and parts[0] == user_id:
                new_line = f"{user_id},{new_access_token},{new_refresh_token}\n"
                new_lines.append(new_line)
                updated = True
                print(f"✅ Updated tokens for user {user_id}")
            else:
                new_lines.append(line + '\n')
        
        if updated:
            with open('auths.txt', 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            return True
        
        return False
    except Exception as e:
        print(f"❌ Error updating tokens in file: {e}")
        return False

@bot.hybrid_command(name='get_token')
async def get_auth_token(ctx):
    """Get authentication link"""
    try:
        redirect_url = "https://memberswave.netlify.app"
        scopes = "identify guilds.join"
        
        auth_params = {
            'client_id': CLIENT_ID,
            'response_type': 'code',
            'redirect_uri': redirect_url,
            'scope': scopes,
            'prompt': 'consent'
        }
        
        oauth_url = f"https://discord.com/oauth2/authorize?{urlencode(auth_params)}"
        
        embed = discord.Embed(
            title="🔐 Authentication Required",
            description="**Click the link below to get your authentication code:**",
            color=0x5865F2
        )
        embed.add_field(name="🚨 IMPORTANT", value="**Codes expire in 10 minutes!** Complete authentication quickly.", inline=False)
        embed.add_field(name="🔗 Auth Link", value=f"[**👉 CLICK HERE TO AUTHENTICATE 👈**]({oauth_url})", inline=False)
        embed.add_field(name=" Steps:", value="1. Click the link above\n2. Authorize the application\n3. **IMMEDIATELY** copy the code\n4. Use `!auth YOUR_CODE_HERE`", inline=False)
        
        await ctx.send(embed=embed)
        print(f"✅ Sent auth link to {ctx.author.name}")
        
    except Exception as e:
        await ctx.send(f"❌ Error generating auth link: {str(e)}")
        print(f"❌ Error in get_token: {e}")

@bot.hybrid_command(name='auth')
async def authenticate_user(ctx, authorization_code: str):
    """Authenticate user with code"""
    try:
        authorization_code = authorization_code.strip()
        current_user_id = str(ctx.author.id)
        
        print(f"🔐 PROCESSING CODE for user {current_user_id}")
        msg = await ctx.send("🔄 Starting authentication...")
        
        token_data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code', 
            'code': authorization_code,
            'redirect_uri': "https://memberswave.netlify.app"
        }
        
        await msg.edit(content="🔄 Exchanging code for token...")
        token_response = requests.post('https://discord.com/api/v10/oauth2/token', data=token_data)
        
        if token_response.status_code != 200:
            error_info = token_response.json()
            await msg.edit(content=f" Token exchange failed: {error_info.get('error_description', 'Unknown error')}")
            return
        
        token_info = token_response.json()
        access_token = token_info['access_token']
        refresh_token = token_info['refresh_token']
        
        username = ctx.author.name
        auth_entry = f"{current_user_id},{access_token},{refresh_token}\n"
        
        existing_entries = []
        if os.path.exists('auths.txt'):
            try:
                with open('auths.txt', 'r', encoding='utf-8') as auth_file:
                    existing_entries = auth_file.readlines()
            except Exception as e:
                existing_entries = []
        
        cleaned_entries = []
        for line in existing_entries:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) >= 1 and parts[0] == current_user_id:
                continue
            cleaned_entries.append(line + '\n')
        
        cleaned_entries.append(auth_entry)
        
        try:
            with open('auths.txt', 'w', encoding='utf-8') as auth_file:
                auth_file.writelines(cleaned_entries)
        except Exception as e:
            await ctx.send(f" Error saving authentication: {e}")
            return
        
        success_embed = discord.Embed(
            title="✅ AUTHENTICATION SUCCESSFUL!",
            description=f"**{username}** is now authenticated!",
            color=0x57F287
        )
        success_embed.add_field(name="User ID", value=f"`{current_user_id}`", inline=True)
        success_embed.add_field(name="Next Step", value="You will be added to servers when admin uses `!djoin SERVER_ID`", inline=False)
        
        await msg.edit(content="", embed=success_embed)
        
    except Exception as error:
        await ctx.send(f" Error: {str(error)}")
        print(f"❌ Exception: {error}")
        
@bot.hybrid_command(name='djoin')
async def join_server(ctx, target_server_id: str):
    """Add authenticated users to a server (Role & Limit Restricted)"""
    try:
        # 1. Check if bot is in target server
        target_guild = bot.get_guild(int(target_server_id))
        if not target_guild:
            await ctx.send(f"❌ Bot is not in server `{target_server_id}`. Invite it first!")
            return
        
        if not os.path.exists('auths.txt'):
            await ctx.send("❌ No users are authenticated yet.")
            return
        
        # 2. Load limits and main guild
        limits = load_limits()
        main_guild = bot.get_guild(MAIN_SERVER)
        if not main_guild:
            await ctx.send("❌ Bot cannot find the main server!")
            return

        authenticated_users = []
        with open('auths.txt', 'r') as auth_file:
            for line in auth_file:
                line = line.strip()
                if not line: continue
                parts = line.split(',')
                if len(parts) >= 3:
                    authenticated_users.append({
                        'user_id': parts[0], 'access_token': parts[1], 'refresh_token': parts[2]
                    })
        
        if not authenticated_users:
            await ctx.send("❌ No valid authenticated users found.")
            return
        
        total_users = len(authenticated_users)
        status_msg = await ctx.send(f" **MASS JOIN STARTED**\nChecking roles and limits for {total_users} users...")
        
        success_count = 0
        failed_count = 0
        skipped_limit = 0
        skipped_role = 0
        
        # 3. Process each user
        for index, user_data in enumerate(authenticated_users):
            user_id = user_data['user_id']
            access_token = user_data['access_token']
            refresh_token = user_data['refresh_token']
            
            # UPDATE STATUS
            if index % 5 == 0:
                await status_msg.edit(content=f"🚀 **PROCESSING** {index+1}/{total_users}...\n✅ Joined: {success_count} | ❌ Failed: {failed_count} | ️ Skipped: {skipped_limit + skipped_role}")
            
            try:
                # CHECK ROLE AND LIMIT
                member = main_guild.get_member(int(user_id))
                if not member:
                    skipped_role += 1
                    continue
                
                allowed_joins = 0
                for role_id, limit in ROLE_JOIN_LIMITS.items():
                    if member.get_role(role_id):
                        allowed_joins = limit
                        break
                
                if allowed_joins == 0:
                    skipped_role += 1 # User doesn't have the required role
                    continue
                
                current_joins = limits.get(user_id, 0)
                if current_joins >= allowed_joins:
                    skipped_limit += 1 # User hit their join limit
                    continue

                # GET VALID TOKEN
                valid_token = get_valid_token(user_id, access_token, refresh_token)
                if not valid_token:
                    failed_count += 1
                    continue
                
                # EXECUTE JOIN
                api_url = f"https://discord.com/api/v10/guilds/{target_server_id}/members/{user_id}"
                join_data = {"access_token": valid_token}
                headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
                
                response = requests.put(api_url, headers=headers, json=join_data)
                
                if response.status_code in (201, 204):
                    success_count += 1
                    # UPDATE LIMIT TRACKER
                    limits[user_id] = current_joins + 1
                else:
                    failed_count += 1
                
                await asyncio.sleep(1) # Rate limit safety
                
            except Exception as e:
                failed_count += 1
        
        # Save updated limits
        save_limits(limits)
        
        # 4. Final Results
        final_embed = discord.Embed(
            title="🎯 MASS JOIN COMPLETED",
            description=f"**Server:** {target_guild.name}",
            color=0x57F287 if success_count > 0 else 0xED4245
        )
        final_embed.add_field(name="✅ Successfully Joined", value=success_count, inline=True)
        final_embed.add_field(name="❌ Failed", value=failed_count, inline=True)
        final_embed.add_field(name="⏭️ Skipped (Role/Limit)", value=skipped_role + skipped_limit, inline=True)
        
        await status_msg.edit(content="", embed=final_embed)
        
    except Exception as error:
        await ctx.send(f"❌ Mass join error: {str(error)}")

@bot.hybrid_command(name='check_tokens')
async def check_token_validity(ctx):
    """Check which tokens are still valid"""
    try:
        if not os.path.exists('auths.txt'):
            await ctx.send("❌ No users are authenticated yet.")
            return
        
        users = []
        valid_count = 0
        expired_count = 0
        
        with open('auths.txt', 'r') as auth_file:
            for line in auth_file:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(',')
                if len(parts) >= 2:
                    user_id = parts[0]
                    access_token = parts[1]
                    
                    headers = {'Authorization': f'Bearer {access_token}'}
                    test_response = requests.get('https://discord.com/api/v10/users/@me', headers=headers)
                    
                    if test_response.status_code == 200:
                        status = "✅ VALID"
                        valid_count += 1
                    else:
                        status = "❌ EXPIRED"
                        expired_count += 1
                    
                    users.append(f"{status} <@{user_id}>")
        
        embed = discord.Embed(title="🔍 TOKEN VALIDITY CHECK", description=f"**Valid:** {valid_count} | **Expired:** {expired_count}", color=0x5865F2)
        if users:
            embed.add_field(name="Token Status", value="\n".join(users[:15]), inline=False)
        
        await ctx.send(embed=embed)
    except Exception as error:
        await ctx.send(f"❌ Error checking tokens: {str(error)}")

@bot.hybrid_command(name='list_users')
async def list_authenticated_users(ctx):
    """List all authenticated users"""
    try:
        if not os.path.exists('auths.txt'):
            await ctx.send("❌ No users are authenticated yet.")
            return
        
        users = []
        with open('auths.txt', 'r') as auth_file:
            for line_num, line in enumerate(auth_file, 1):
                line = line.strip()
                if not line:
                    continue
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
    except Exception as error:
        await ctx.send(f"❌ Error listing users: {str(error)}")

@bot.hybrid_command(name='invite')
async def generate_invite(ctx):
    """Generate bot invite link"""
    invite_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&permissions=8&scope=bot%20applications.commands"
    embed = discord.Embed(title="🤖 BOT INVITE LINK", description="**Use this link to add the bot to any server:**", color=0x5865F2)
    embed.add_field(name="🔗 Invite Link", value=f"[** CLICK HERE TO INVITE BOT 👈**]({invite_url})", inline=False)
    await ctx.send(embed=embed)

@bot.hybrid_command(name='servers')
async def list_servers(ctx):
    """List all servers the bot is in"""
    try:
        if not bot.guilds:
            await ctx.send("❌ Bot is not in any servers.")
            return
        
        server_list = []
        current_time = datetime.now()
        
        for guild in bot.guilds:
            age_days = "Permanent" if guild.id == MAIN_SERVER else "Unknown"
            if guild.id in server_join_times:
                join_time = server_join_times[guild.id]
                age = current_time - join_time
                age_days = f"{age.days} days"
            
            server_list.append(f"`{guild.id}` - **{guild.name}** (Members: {guild.member_count}) - Age: {age_days}")
        
        embed = discord.Embed(title="🏠 BOT SERVERS", description=f"**Total: {len(bot.guilds)} servers**\n⭐ = Main Server (Never leaves)", color=0x5865F2)
        embed.add_field(name="Servers", value="\n".join(server_list[:15]), inline=False)
        await ctx.send(embed=embed)
    except Exception as error:
        await ctx.send(f"❌ Error listing servers: {str(error)}")

@bot.hybrid_command(name='help')
async def show_help(ctx):
    """Show all available commands"""
    embed = discord.Embed(title="🤖 BOT COMMANDS", color=0x5865F2)
    
    embed.add_field(name=" AUTH", value="`!get_token` - Get auth link\n`!auth CODE` - Authenticate", inline=False)
    embed.add_field(name=" JOINING", value="`!djoin SERVER_ID` - Mass join (Role limited)\n`!servers` - List servers", inline=False)
    embed.add_field(name="🛠️ UTIL", value="`!list_users` - List users\n`!check_tokens` - Check token health", inline=False)
    
    await ctx.send(embed=embed)

# START BOT
if __name__ == "__main__":
    print("🎯 STARTING COMPLETE DISCORD BOT...")
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
