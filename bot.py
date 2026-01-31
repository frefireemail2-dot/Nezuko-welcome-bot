import discord
from discord.ext import commands
import aiohttp
import io
import json
import random
import os
import asyncio
from PIL import Image, ImageDraw, ImageFont
from keep_alive import keep_alive  # Import the web server

# --- CONFIGURATION (The Village Secrets) ---
TOKEN = os.getenv("DISCORD_TOKEN")  # Get this from Render Environment Variables

# Channel IDs
WELCOME_CHANNEL_ID = 1452952401064759348
IMAGE_SOURCE_CHANNEL_ID = 1464979503645200652
CONFIG_CHANNEL_ID = 1464978865351950432

# Admin IDs (The Kage)
ADMIN_IDS = [1410261255058493440]

# Image Settings (From your coordinates)
TEXT_CENTER_X = 1395
TEXT_CENTER_Y = 800
MAX_TEXT_WIDTH = 1052
FONT_PATH = "njnaruto.ttf"  # You MUST upload this file to Render/GitHub
DEFAULT_FONT_SIZE = 120

# Colors
COLOR_TOP = (0, 87, 183, 255)   # Naruto Blue
COLOR_BOTTOM = (255, 195, 0, 255) # Naruto Yellow

# Intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- MEMORY SYSTEM (The Scroll) ---
bot_config = {
    "welcome_message": "Welcome {name} to the village! Enjoy your stay."
}
cached_image_urls = []

async def save_config_to_discord():
    """Writes the current settings to a JSON file and uploads it to the Config Channel."""
    channel = bot.get_channel(CONFIG_CHANNEL_ID)
    if not channel:
        print("Error: Config channel not found!")
        return

    # Convert config to JSON string
    json_data = json.dumps(bot_config, indent=4)
    file_obj = io.BytesIO(json_data.encode("utf-8"))
    
    await channel.send(
        content=f"Create Date: {discord.utils.utcnow()}",
        file=discord.File(file_obj, filename="config.json")
    )
    print("Configuration scroll saved successfully.")

async def load_config_from_discord():
    """Downloads the last JSON file from the Config Channel to restore memory."""
    global bot_config
    channel = bot.get_channel(CONFIG_CHANNEL_ID)
    if not channel:
        return

    # Get the last message in the channel
    try:
        async for message in channel.history(limit=1):
            if message.attachments:
                attachment = message.attachments[0]
                if attachment.filename.endswith(".json"):
                    content = await attachment.read()
                    bot_config = json.loads(content)
                    print("Configuration scroll loaded!")
                    return
    except Exception as e:
        print(f"No previous config found or error loading: {e}")
        # If fail, we just use the default variable set above

async def refresh_image_cache():
    """Fetches all background images from the Source Channel."""
    global cached_image_urls
    channel = bot.get_channel(IMAGE_SOURCE_CHANNEL_ID)
    if not channel:
        print("Image source channel not found!")
        return

    new_cache = []
    # Scan last 100 messages for images
    async for message in channel.history(limit=100):
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                new_cache.append(attachment.url)
    
    cached_image_urls = new_cache
    print(f"Cached {len(cached_image_urls)} background images.")

# --- IMAGE PROCESSING (The Art) ---
def create_split_color_text(text, font):
    """Creates a text image that is half blue (top) and half yellow (bottom)."""
    # 1. Get size of the text
    left, top, right, bottom = font.getbbox(text)
    width = right - left
    height = bottom - top
    
    # Add a little padding
    img_w, img_h = width + 10, height + 10

    # 2. Create the mask (The text shape)
    mask = Image.new("L", (img_w, img_h), 0)
    draw = ImageDraw.Draw(mask)
    # Draw centered
    draw.text((img_w/2, img_h/2), text, font=font, fill=255, anchor="mm")

    # 3. Create the color block
    color_img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw_color = ImageDraw.Draw(color_img)
    
    # Top Half (Blue)
    draw_color.rectangle([(0, 0), (img_w, img_h / 2)], fill=COLOR_TOP)
    # Bottom Half (Yellow)
    draw_color.rectangle([(0, img_h / 2), (img_w, img_h)], fill=COLOR_BOTTOM)

    # 4. Apply the mask to the color block
    # Create a final transparent image
    final_text = Image.new("RGBA", (img_w, img_h), (0,0,0,0))
    final_text.paste(color_img, (0,0), mask=mask)
    
    return final_text

async def generate_welcome_card(user_name):
    """Downloads a background, writes the name, returns bytes."""
    if not cached_image_urls:
        await refresh_image_cache()
    
    if not cached_image_urls:
        return None # No images available

    bg_url = random.choice(cached_image_urls)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(bg_url) as resp:
            if resp.status != 200:
                return None
            data = await resp.read()

    # Open the background
    bg_image = Image.open(io.BytesIO(data)).convert("RGBA")

    # Load Font
    try:
        font_size = DEFAULT_FONT_SIZE
        font = ImageFont.truetype(FONT_PATH, font_size)
    except IOError:
        font = ImageFont.load_default() # Fallback if you forget to upload the font file
        print("WARNING: njnaruto.ttf not found. Using default font.")

    # Dynamic Font Scaling
    # If name is too long, shrink the font until it fits MAX_WIDTH
    text_width = font.getlength(user_name)
    while text_width > MAX_TEXT_WIDTH and font_size > 30:
        font_size -= 5
        font = ImageFont.truetype(FONT_PATH, font_size)
        text_width = font.getlength(user_name)

    # Generate the special split-color text
    text_image = create_split_color_text(user_name, font)

    # Paste it onto the background (Centered)
    # Calculate top-left position for the paste based on center coordinates
    w, h = text_image.size
    paste_x = int(TEXT_CENTER_X - (w / 2))
    paste_y = int(TEXT_CENTER_Y - (h / 2))

    # Paste with transparency (mask=text_image helps blending)
    bg_image.paste(text_image, (paste_x, paste_y), mask=text_image)

    # Save to buffer
    output_buffer = io.BytesIO()
    bg_image.save(output_buffer, format="PNG")
    output_buffer.seek(0)
    
    return output_buffer

# --- EVENTS & COMMANDS ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} - Dattebayo!")
    # Start the Keep-Alive Web Server
    keep_alive()
    # Restore Memory
    await load_config_from_discord()
    # Cache Images
    await refresh_image_cache()

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if not channel:
        return

    # Format the message
    # {name} = @Mention, {user_name} = Just the text name
    msg_text = bot_config["welcome_message"].format(
        name=member.mention, 
        user_name=member.name
    )

    # Generate Image
    img_buffer = await generate_welcome_card(member.name)
    
    if img_buffer:
        file = discord.File(img_buffer, filename="welcome.png")
        await channel.send(content=msg_text, file=file)
    else:
        # Fallback if image generation fails
        await channel.send(content=msg_text)

# Admin Command: Set Welcome Message
@bot.command()
async def set_welcome(ctx, *, message: str):
    if ctx.author.id not in ADMIN_IDS:
        await ctx.send("You are not the Hokage! (Admin only)")
        return

    bot_config["welcome_message"] = message
    await save_config_to_discord()
    await ctx.send(f"Welcome message updated! Example: {message.format(name=ctx.author.mention, user_name=ctx.author.name)}")

# Admin Command: Force Refresh Images
@bot.command()
async def refresh_images(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
    await refresh_image_cache()
    await ctx.send(f"Refreshed! Found {len(cached_image_urls)} images.")

# Admin Command: Test the Welcome Card
@bot.command()
async def test_welcome(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return
        
    await ctx.send("Generating test card... ⏳")
    img_buffer = await generate_welcome_card(ctx.author.name)
    
    msg_text = bot_config["welcome_message"].format(
        name=ctx.author.mention,
        user_name=ctx.author.name
    )
    
    if img_buffer:
        await ctx.send(content=msg_text, file=discord.File(img_buffer, filename="test.png"))
    else:
        await ctx.send("Failed to generate image. Check source channel.")

bot.run(TOKEN)
