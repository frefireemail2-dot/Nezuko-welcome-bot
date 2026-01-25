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
# 1. DB Server (Where data lives)
DATA_CHANNEL_ID = 1464978865351950432
TEMPLATE_CHANNEL_ID = 1464979503645200652

# 2. Main Server (Where people join)
WELCOME_SERVER_ID = 1452948411014713386    # <--- NEW: The ID of the server to watch
WELCOME_CHANNEL_ID = 1452952401064759348   # <--- The channel to send the image to

# --- TEXT CONFIG ---
TEXT_X = 1395
TEXT_Y = 806
FONT_SIZE = 120
FONT_PATH = "njnaruto.ttf"

# --- FLASK SERVER ---
app = Flask('')

@app.route('/')
def home():
    return "Dattebayo! Guarding Server 1452948411014713386! 🛡️"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- DISCORD BOT SETUP ---
intents = discord.Intents.default()
intents.members = True # ⚠️ CRITICAL: Must be enabled in Dev Portal!
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
        # Search globally for the DB channel
        channel = await bot_client.fetch_channel(DATA_CHANNEL_ID)
        messages = [message async for message in channel.history(limit=1)]
        if messages:
            return messages[0].content
        return "Welcome to the server, {user}!"
    except Exception as e:
        print(f"Error fetching welcome message: {e}")
        return "Welcome {user} to {server}!"

async def get_random_template(bot_client):
    try:
        # Search globally for the DB channel
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
        print(f"Error fetching template: {e}")
        return None

def create_naruto_text(base_image, text):
    draw = ImageDraw.Draw(base_image)
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except IOError:
        font = ImageFont.load_default()

    # Text Size & Position
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

    # Stroke
    draw.text((x, y), text, font=font, fill="white", stroke_width=8)

    # Gradient Mask
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

# --- BOT EVENTS ---

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('Dattebayo! Ready to welcome new ninja! 🦊')

@client.tree.command(name="setwelcome", description="Set the custom welcome message")
@app_commands.describe(message="Use {user} for mention and {server} for server name")
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

@client.event
async def on_member_join(member):
    # 🕵️ Check if the join happened in the correct server
    if member.guild.id != WELCOME_SERVER_ID:
        print(f"Ignored join in server: {member.guild.id} (Not our target village)")
        return

    print(f"New Shinobi detected: {member.name} in {member.guild.name}")

    try:
        welcome_channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if not welcome_channel:
            print("❌ Welcome channel not found inside this server!")
            return

        # 1. Get Data from DB
        raw_text = await get_welcome_message(member.client)
        welcome_text = raw_text.replace("{user}", member.mention).replace("{server}", member.guild.name)

        # 2. Get Image
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
                    print("✅ Welcome Scroll Sent!")
        else:
            await welcome_channel.send(content=welcome_text)

    except Exception as e:
        print(f"❌ Error in welcome event: {e}")

keep_alive()
client.run(os.environ['DISCORD_TOKEN'])
