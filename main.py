import discord
from discord import app_commands
import os
import random
from flask import Flask
from threading import Thread
from PIL import Image, ImageDraw, ImageFont
import io
import requests

# --- CONFIGURATION ---
DATA_CHANNEL_ID = 1464978865351950432      # DB Server: Data
TEMPLATE_CHANNEL_ID = 1464979503645200652  # DB Server: Images
WELCOME_SERVER_ID = 1452948411014713386    # Main Server: ID
WELCOME_CHANNEL_ID = 1452952401064759348   # Main Server: Channel

TEXT_X = 1395
TEXT_Y = 806
FONT_SIZE = 120
FONT_PATH = "njnaruto.ttf"

# --- FLASK SERVER ---
app = Flask('')

@app.route('/')
def home():
    return "Dattebayo! Bot is Online! 🍃"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- DISCORD SETUP ---
# ⚠️ CRITICAL: Only works if enabled in Developer Portal
intents = discord.Intents.default()
intents.members = True 
intents.message_content = True

class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

client = MyClient()

# --- HELPER FUNCTIONS ---

async def get_welcome_message(bot_client):
    try:
        channel = await bot_client.fetch_channel(DATA_CHANNEL_ID)
        messages = [message async for message in channel.history(limit=1)]
        if messages:
            return messages[0].content
        return "Welcome to the server, {user}!"
    except Exception as e:
        print(f"Error fetching DB Message: {e}")
        return "Welcome {user} to {server}!"

async def get_random_template(bot_client):
    try:
        channel = await bot_client.fetch_channel(TEMPLATE_CHANNEL_ID)
        images = []
        async for message in channel.history(limit=10):
            if message.attachments:
                images.append(message.attachments[0].url)
        
        if not images:
            return None
        candidates = images[:3]
        return random.choice(candidates)
    except Exception as e:
        print(f"Error fetching DB Template: {e}")
        return None

def create_naruto_text(base_image, text):
    draw = ImageDraw.Draw(base_image)
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except IOError:
        print("Font file not found, using default.")
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    current_font_size = FONT_SIZE
    while text_width > 900 and current_font_size > 50:
        current_font_size -= 5
        try:
            font = ImageFont.truetype(FONT_PATH, current_font_size)
        except: pass
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

    x = TEXT_X - (text_width / 2)
    y = TEXT_Y - (text_height / 2)

    draw.text((x, y), text, font=font, fill="white", stroke_width=8)

    mask_img = Image.new('L', base_image.size, 0)
    mask_draw = ImageDraw.Draw(mask_img)
    mask_draw.text((x, y), text, font=font, fill=255)

    color_img = Image.new('RGB', base_image.size, "black")
    color_draw = ImageDraw.Draw(color_img)
    split_y = TEXT_Y 
    color_draw.rectangle([(0, 0), (base_image.width, split_y)], fill="#00A2E8")
    color_draw.rectangle([(0, split_y), (base_image.width, base_image.height)], fill="#FFD700")

    base_image.paste(color_img, (0,0), mask_img)
    return base_image

# --- COMMANDS & EVENTS ---

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print(f'Watching Server ID: {WELCOME_SERVER_ID}')

@client.tree.command(name="setwelcome", description="Set custom welcome message")
async def set_welcome(interaction: discord.Interaction, message: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 Admin only!", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        channel = await interaction.client.fetch_channel(DATA_CHANNEL_ID)
        await channel.send(message)
        await interaction.followup.send(f"✅ Saved! Preview: {message}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}")

# 🧪 NEW DEBUG COMMAND
@client.tree.command(name="testwelcome", description="Force a welcome message to test if the bot works")
async def test_welcome(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 Admin only!", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        # Simulate the logic
        member = interaction.user
        welcome_channel = interaction.guild.get_channel(WELCOME_CHANNEL_ID)
        
        if not welcome_channel:
            await interaction.followup.send(f"❌ I cannot find the Welcome Channel (ID: {WELCOME_CHANNEL_ID}). Check permissions!")
            return

        raw_text = await get_welcome_message(interaction.client)
        welcome_text = raw_text.replace("{user}", member.mention).replace("{server}", member.guild.name)

        bg_url = await get_random_template(interaction.client)
        
        if bg_url:
            response = requests.get(bg_url)
            image_bytes = io.BytesIO(response.content)
            
            with Image.open(image_bytes).convert("RGBA") as img:
                final_img = create_naruto_text(img, member.name)
                
                with io.BytesIO() as image_binary:
                    final_img.save(image_binary, 'PNG')
                    image_binary.seek(0)
                    file = discord.File(fp=image_binary, filename='welcome.png')
                    await welcome_channel.send(content=welcome_text, file=file)
                    await interaction.followup.send("✅ Test Sent! Check the welcome channel.")
        else:
            await interaction.followup.send("❌ No template image found in DB channel.")
            
    except Exception as e:
        await interaction.followup.send(f"❌ Error during test: {e}")

@client.event
async def on_member_join(member):
    # Debug print to Render Logs
    print(f"EVENT TRIGGERED: {member.name} joined {member.guild.id}")
    
    if member.guild.id != WELCOME_SERVER_ID:
        return

    try:
        welcome_channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if not welcome_channel:
            print("Welcome channel missing.")
            return

        raw_text = await get_welcome_message(member.client)
        welcome_text = raw_text.replace("{user}", member.mention).replace("{server}", member.guild.name)
        bg_url = await get_random_template(member.client)
        
        if bg_url:
            response = requests.get(bg_url)
            image_bytes = io.BytesIO(response.content)
            
            with Image.open(image_bytes).convert("RGBA") as img:
                final_img = create_naruto_text(img, member.name)
                
                with io.BytesIO() as image_binary:
                    final_img.save(image_binary, 'PNG')
                    image_binary.seek(0)
                    file = discord.File(fp=image_binary, filename='welcome.png')
                    await welcome_channel.send(content=welcome_text, file=file)
    except Exception as e:
        print(f"Error in on_member_join: {e}")

keep_alive()
client.run(os.environ['DISCORD_TOKEN'])
