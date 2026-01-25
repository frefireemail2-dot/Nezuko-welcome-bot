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
# ⚠️ MAKE SURE THE BOT IS PRESENT IN BOTH SERVERS (Main & Storage)!
DATA_CHANNEL_ID = 1464978865351950432      # DB Server: Saves the welcome text
TEMPLATE_CHANNEL_ID = 1464979503645200652  # DB Server: Saves the images
WELCOME_CHANNEL_ID = 1452952401064759348   # Main Server: Where the bot says hello

# --- TEXT CONFIG (Coordinates & Font) ---
TEXT_X = 1395
TEXT_Y = 806
FONT_SIZE = 120
FONT_PATH = "njnaruto.ttf"

# --- FLASK SERVER (Render Keep-Alive) ---
app = Flask('')

@app.route('/')
def home():
    return "Dattebayo! Bot is connected to the Global Ninja Network! 🌐"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- DISCORD BOT SETUP ---
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
    """
    Fetches the custom welcome message from the storage channel.
    Uses fetch_channel to find it globally (in the DB server).
    """
    try:
        # 🛠️ FIX: Use bot_client.fetch_channel to find it in the Storage Server
        channel = await bot_client.fetch_channel(DATA_CHANNEL_ID)
        
        # Get the last message in history
        messages = [message async for message in channel.history(limit=1)]
        if messages:
            return messages[0].content
        return "Welcome to the server, {user}!"
    except Exception as e:
        print(f"Error fetching welcome message: {e}")
        return "Welcome {user} to {server}!"

async def get_random_template(bot_client):
    """
    Fetches a random image URL from the template channel in the DB Server.
    """
    try:
        # 🛠️ FIX: Use bot_client.fetch_channel to find it in the Storage Server
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
    """Draws the text with Naruto styling (Stroke + Split Gradient)."""
    draw = ImageDraw.Draw(base_image)
    
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except IOError:
        print(f"⚠️ Could not find {FONT_PATH}! Using default font.")
        font = ImageFont.load_default()

    # 1. Calculate Text Size
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Resize logic
    current_font_size = FONT_SIZE
    while text_width > 900 and current_font_size > 50:
        current_font_size -= 5
        try:
            font = ImageFont.truetype(FONT_PATH, current_font_size)
        except:
            pass
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

    # Center Position
    x = TEXT_X - (text_width / 2)
    y = TEXT_Y - (text_height / 2)

    # 2. Outline (Stroke)
    stroke_width = 8
    draw.text((x, y), text, font=font, fill="white", stroke_width=stroke_width)

    # 3. Gradient Text Layer
    mask_img = Image.new('L', base_image.size, 0)
    mask_draw = ImageDraw.Draw(mask_img)
    mask_draw.text((x, y), text, font=font, fill=255)

    color_img = Image.new('RGB', base_image.size, "black")
    color_draw = ImageDraw.Draw(color_img)
    
    split_y = TEXT_Y 
    color_draw.rectangle([(0, 0), (base_image.width, split_y)], fill="#00A2E8") # Blue
    color_draw.rectangle([(0, split_y), (base_image.width, base_image.height)], fill="#FFD700") # Yellow

    base_image.paste(color_img, (0,0), mask_img)
    return base_image

# --- BOT EVENTS ---

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('Dattebayo! Ready to serve across servers! 🦊')

# Slash Command: /setwelcome
@client.tree.command(name="setwelcome", description="Set the custom welcome message")
@app_commands.describe(message="Use {user} for mention and {server} for server name")
async def set_welcome(interaction: discord.Interaction, message: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 You need Administrator permissions!", ephemeral=True)
        return

    # Defer the response because fetching across servers might take 1-2 seconds
    await interaction.response.defer(ephemeral=True)

    try:
        # 🛠️ FIX: Search GLOBALLY for the Data Channel using interaction.client
        channel = await interaction.client.fetch_channel(DATA_CHANNEL_ID)
        
        await channel.send(message)
        await interaction.followup.send(f"✅ Welcome message saved to Database Channel!\n**Preview:** {message}")
            
    except discord.NotFound:
        await interaction.followup.send(f"❌ Could not find channel {DATA_CHANNEL_ID}. Is the bot in the Storage Server?")
    except discord.Forbidden:
        await interaction.followup.send("❌ I see the channel, but I don't have permission to write there!")
    except Exception as e:
        print(e)
        await interaction.followup.send(f"❌ Something went wrong: {e}")

# Event: Member Join
@client.event
async def on_member_join(member):
    print(f"User {member.name} joined {member.guild.name}! Preparing welcome...")
    try:
        # Check if this is the Main Server (where we want to welcome people)
        if member.guild.id != 1452952401064759348 and str(member.guild.id) != "1452952401064759348":
             # Optional: If you only want it to welcome in ONE specific server, keep this check.
             # If you want it to welcome in ANY server using the ID config, remove this block.
             pass

        welcome_channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if not welcome_channel:
            print("Welcome channel not found in this guild.")
            return

        # 1. Get Text (passing member.client to find the DB channel)
        raw_text = await get_welcome_message(member.client)
        welcome_text = raw_text.replace("{user}", member.mention).replace("{server}", member.guild.name)

        # 2. Get Background (passing member.client)
        bg_url = await get_random_template(member.client)
        
        if bg_url:
            print(f"Downloading template: {bg_url}")
            response = requests.get(bg_url)
            image_bytes = io.BytesIO(response.content)
            
            with Image.open(image_bytes).convert("RGBA") as img:
                # 3. Apply Naruto Text Logic
                final_img = create_naruto_text(img, member.name)
                
                with io.BytesIO() as image_binary:
                    final_img.save(image_binary, 'PNG')
                    image_binary.seek(0)
                    
                    file = discord.File(fp=image_binary, filename='welcome.png')
                    await welcome_channel.send(content=welcome_text, file=file)
                    print("Welcome sent!")
        else:
            print("No template found, sending text only.")
            await welcome_channel.send(content=welcome_text)

    except Exception as e:
        print(f"Error in welcome event: {e}")

# --- RUN ---
keep_alive()
client.run(os.environ['DISCORD_TOKEN'])
