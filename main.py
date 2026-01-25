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
# These are the channel IDs you provided
DATA_CHANNEL_ID = 1464978865351950432      # Saves the welcome text
TEMPLATE_CHANNEL_ID = 1464979503645200652  # Saves the images
WELCOME_CHANNEL_ID = 1452952401064759348   # Where the bot says hello

# --- TEXT CONFIG (Coordinates & Font) ---
# Calculated based on your image data
TEXT_X = 1395
TEXT_Y = 806
FONT_SIZE = 120
FONT_PATH = "njnaruto.ttf" # ⚠️ Make sure this file is uploaded to Render!

# --- FLASK SERVER (For Render Keep-Alive) ---
app = Flask('')

@app.route('/')
def home():
    return "Dattebayo! The Bot is guarding the village! 🍃"

def run():
    # 🛠️ PORT FIX: This tells Render to use the port IT wants, or 8080 if local.
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- DISCORD BOT SETUP ---
intents = discord.Intents.default()
intents.members = True # CRITICAL: Allows bot to see when new ninja join
intents.message_content = True

class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

client = MyClient()

# --- HELPER FUNCTIONS ---

async def get_welcome_message(guild):
    """Fetches the custom welcome message from the storage channel."""
    try:
        channel = guild.get_channel(DATA_CHANNEL_ID)
        if not channel:
            return "Welcome to the server, {user}!"
        
        # Get the last message in history
        messages = [message async for message in channel.history(limit=1)]
        if messages:
            return messages[0].content
        return "Welcome to the server, {user}!"
    except Exception as e:
        print(f"Error fetching message: {e}")
        return "Welcome {user} to {server}!"

async def get_random_template(guild):
    """Fetches a random image URL from the template channel."""
    try:
        channel = guild.get_channel(TEMPLATE_CHANNEL_ID)
        if not channel:
            return None
        
        # Check last 10 messages for images
        images = []
        async for message in channel.history(limit=10):
            if message.attachments:
                images.append(message.attachments[0].url)
        
        # Pick from first 3 found
        if not images:
            return None
        
        candidates = images[:3]
        return random.choice(candidates)
    except Exception as e:
        print(f"Error fetching template: {e}")
        return None

def create_naruto_text(base_image, text):
    """
    Draws text with:
    1. White Outline (Stroke)
    2. Split Gradient (Top Blue, Bottom Yellow)
    """
    draw = ImageDraw.Draw(base_image)
    
    # Load Font
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except IOError:
        print(f"⚠️ Could not find {FONT_PATH}! Using default font.")
        font = ImageFont.load_default()

    # 1. Calculate Text Size
    # bbox returns (left, top, right, bottom)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Adjust font size if text is too wide for the box (max ~900px)
    current_font_size = FONT_SIZE
    while text_width > 900 and current_font_size > 50:
        current_font_size -= 5
        try:
            font = ImageFont.truetype(FONT_PATH, current_font_size)
        except:
            pass # Keep previous font if resize fails
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

    # Calculate Center Position
    x = TEXT_X - (text_width / 2)
    y = TEXT_Y - (text_height / 2)

    # 2. Draw the Outline (Stroke)
    # We draw it in white multiple times to create thickness
    stroke_width = 8
    draw.text((x, y), text, font=font, fill="white", stroke_width=stroke_width)

    # 3. Create the Gradient Text Layer
    # Create a separate image (mask) for the text shape
    # We make it the same size as the base image to keep coordinates simple
    mask_img = Image.new('L', base_image.size, 0)
    mask_draw = ImageDraw.Draw(mask_img)
    mask_draw.text((x, y), text, font=font, fill=255)

    # Create the color layer (Blue top, Yellow bottom)
    color_img = Image.new('RGB', base_image.size, "black")
    color_draw = ImageDraw.Draw(color_img)
    
    # Calculate split point (middle of the text height)
    split_y = TEXT_Y 
    
    # Fill Top Blue (#00A2E8) - Naruto Headband Blue
    color_draw.rectangle([(0, 0), (base_image.width, split_y)], fill="#00A2E8")
    
    # Fill Bottom Yellow (#FFD700) - Naruto Hair Yellow
    color_draw.rectangle([(0, split_y), (base_image.width, base_image.height)], fill="#FFD700")

    # 4. Composite: Paste the Color Layer onto the Base using the Text Mask
    base_image.paste(color_img, (0,0), mask_img)
    
    return base_image

# --- BOT EVENTS ---

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')

# Slash Command: /setwelcome
@client.tree.command(name="setwelcome", description="Set the custom welcome message")
@app_commands.describe(message="Use {user} for mention and {server} for server name")
async def set_welcome(interaction: discord.Interaction, message: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 You need Administrator permissions!", ephemeral=True)
        return

    try:
        channel = interaction.guild.get_channel(DATA_CHANNEL_ID)
        if channel:
            await channel.send(message)
            await interaction.response.send_message(f"✅ Welcome message updated!\n**Preview:** {message}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Data Channel not found.", ephemeral=True)
    except Exception as e:
        print(e)
        await interaction.response.send_message("❌ Failed to save message.", ephemeral=True)

# Event: Member Join
@client.event
async def on_member_join(member):
    print(f"User {member.name} joined! Preparing welcome...")
    try:
        welcome_channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if not welcome_channel:
            print("Welcome channel not found!")
            return

        # 1. Get Text
        welcome_text = await get_welcome_message(member.guild)
        welcome_text = welcome_text.replace("{user}", member.mention).replace("{server}", member.guild.name)

        # 2. Get Background
        bg_url = await get_random_template(member.guild)
        
        if bg_url:
            print(f"Downloading template: {bg_url}")
            # Download the image
            response = requests.get(bg_url)
            image_bytes = io.BytesIO(response.content)
            
            with Image.open(image_bytes).convert("RGBA") as img:
                # 3. Apply Naruto Text Logic
                final_img = create_naruto_text(img, member.name)
                
                # Save to buffer
                with io.BytesIO() as image_binary:
                    final_img.save(image_binary, 'PNG')
                    image_binary.seek(0)
                    
                    # 4. Send
                    file = discord.File(fp=image_binary, filename='welcome.png')
                    await welcome_channel.send(content=welcome_text, file=file)
                    print("Welcome image sent!")
        else:
            # Fallback if no image found in your Template Channel
            print("No template found, sending text only.")
            await welcome_channel.send(content=welcome_text)

    except Exception as e:
        print(f"Error in welcome event: {e}")

# --- RUN ---
keep_alive() # Start web server for Render
client.run(os.environ['DISCORD_TOKEN'])
