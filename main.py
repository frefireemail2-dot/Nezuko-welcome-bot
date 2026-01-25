import discord
from discord import app_commands
from discord.ui import Modal, TextInput, View, Button, Select
import os
import random
import json
import asyncio
from flask import Flask
from threading import Thread
from PIL import Image, ImageDraw, ImageFont
import io
import requests

# --- CONFIGURATION ---
DATA_CHANNEL_ID = 1464978865351950432       # DB Server
TEMPLATE_CHANNEL_ID = 1464979503645200652   # DB Server
WELCOME_CHANNEL_ID = 1452952401064759348    # Main Server
LOG_CHANNEL_ID = 1452989288047317022        # Main Server (Logs)

# --- TEXT CONFIG ---
TEXT_X = 1395
TEXT_Y = 806
FONT_SIZE = 120
FONT_PATH = "njnaruto.ttf"

# --- FLASK SERVER ---
app = Flask('')
@app.route('/')
def home(): return "Dattebayo! System Stable! 🍃"
def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
def keep_alive():
    t = Thread(target=run)
    t.start()

# --- DISCORD SETUP ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True 

class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
    async def setup_hook(self):
        await self.tree.sync()

client = MyClient()

# ==========================================
# 💾 DATABASE FUNCTIONS
# ==========================================

async def save_config(bot_client, data):
    try:
        channel = await bot_client.fetch_channel(DATA_CHANNEL_ID)
        target_msg = None
        async for msg in channel.history(limit=20):
            if msg.content.startswith("CONFIG_VERIFY:"):
                target_msg = msg
                break
        json_str = "CONFIG_VERIFY:" + json.dumps(data)
        if target_msg: await target_msg.edit(content=json_str)
        else: await channel.send(json_str)
        return True
    except Exception as e:
        print(f"❌ Error saving config: {e}")
        return False

async def load_config(bot_client):
    try:
        channel = await bot_client.fetch_channel(DATA_CHANNEL_ID)
        async for msg in channel.history(limit=20):
            if msg.content.startswith("CONFIG_VERIFY:"):
                return json.loads(msg.content.replace("CONFIG_VERIFY:", ""))
        return None
    except: return None

# ==========================================
# 🖼️ IMAGE GENERATION
# ==========================================
async def get_random_template(bot_client):
    try:
        channel = await bot_client.fetch_channel(TEMPLATE_CHANNEL_ID)
        images = [m.attachments[0].url for m in [msg async for msg in channel.history(limit=10)] if m.attachments]
        return random.choice(images[:3]) if images else None
    except: return None

def create_naruto_text(base_image, text):
    draw = ImageDraw.Draw(base_image)
    try: font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except: font = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    curr_size = FONT_SIZE
    while text_width > 900 and curr_size > 50:
        curr_size -= 5
        try: font = ImageFont.truetype(FONT_PATH, curr_size)
        except: pass
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
    
    x, y = TEXT_X - (text_width / 2), TEXT_Y - (text_height / 2)
    draw.text((x, y), text, font=font, fill="white", stroke_width=8)
    
    mask = Image.new('L', base_image.size, 0)
    ImageDraw.Draw(mask).text((x, y), text, font=font, fill=255)
    color = Image.new('RGB', base_image.size, "black")
    c_draw = ImageDraw.Draw(color)
    c_draw.rectangle([(0, 0), (base_image.width, TEXT_Y)], fill="#00A2E8")
    c_draw.rectangle([(0, TEXT_Y), (base_image.width, base_image.height)], fill="#FFD700")
    base_image.paste(color, (0,0), mask)
    return base_image

# ==========================================
# 🛡️ STABLE VERIFICATION LOGIC
# ==========================================

class StartVerificationView(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Verify Identity", style=discord.ButtonStyle.success, emoji="🛡️", custom_id="start_verify_btn")
    async def verify_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True) # Ack immediately to prevent timeout
        config = await load_config(interaction.client)
        if not config or not config.get("questions"):
            return await interaction.followup.send("❌ Verification not configured.", ephemeral=True)
        
        # Start Step 0
        await run_question_step(interaction, config, 0, [], is_followup=True)

async def run_question_step(interaction, config, index, answers, is_followup=False):
    questions = config["questions"]
    
    # 1. FINISH CHECK
    if index >= len(questions):
        await finish_verification(interaction, config, answers)
        return

    q = questions[index]
    
    # 2. DETERMINE NEXT STEP TYPE
    # TEXT -> Needs a Modal. We MUST send a button first if we are coming from a Followup or Edit.
    if q["type"] == "text":
        view = ModalTriggerView(config, index, answers, q["prompt"])
        msg_content = f"📝 **Question {index+1}:** Click to answer."
        
        if is_followup:
            await interaction.followup.send(msg_content, view=view, ephemeral=True)
        else:
            # We try to edit, but if it was a text input before, we might need a new message
            try: await interaction.response.edit_message(content=msg_content, view=view)
            except: await interaction.response.send_message(msg_content, view=view, ephemeral=True)

    # DROPDOWN -> View
    elif q["type"] == "select":
        view = QuestionSelectView(config, index, answers, q["prompt"], q["options"])
        content = f"🔻 **Question {index+1}:** {q['prompt']}"
        
        if is_followup:
            await interaction.followup.send(content, view=view, ephemeral=True)
        else:
            try: await interaction.response.edit_message(content=content, view=view)
            except: await interaction.response.send_message(content, view=view, ephemeral=True)

    # BUTTONS -> View
    elif q["type"] == "radio":
        view = QuestionRadioView(config, index, answers, q["prompt"], q["options"])
        content = f"🔘 **Question {index+1}:** {q['prompt']}"
        
        if is_followup:
            await interaction.followup.send(content, view=view, ephemeral=True)
        else:
            try: await interaction.response.edit_message(content=content, view=view)
            except: await interaction.response.send_message(content, view=view, ephemeral=True)

# --- UI COMPONENTS ---

# Used to launch a Modal safely
class ModalTriggerView(View):
    def __init__(self, c, i, a, p):
        super().__init__(timeout=300)
        self.c, self.i, self.a, self.p = c, i, a, p
    
    @discord.ui.button(label="Answer Question", style=discord.ButtonStyle.primary, emoji="✍️")
    async def open_modal(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(QuestionModal(self.c, self.i, self.a, self.p))

class QuestionModal(Modal):
    def __init__(self, config, index, answers, prompt):
        super().__init__(title=f"Question {index+1}")
        self.c, self.i, self.a = config, index, answers
        self.inp = TextInput(label=prompt[:45], required=True)
        self.add_item(self.inp)
    async def on_submit(self, interaction: discord.Interaction):
        # Save answer
        self.a.append({"q": self.inp.label, "a": self.inp.value})
        # Go to next, treat as followup because Modal consumes the token
        await interaction.response.defer(ephemeral=True) 
        await run_question_step(interaction, self.c, self.i + 1, self.a, is_followup=True)

class QuestionSelectView(View):
    def __init__(self, c, i, a, p, o):
        super().__init__(timeout=300)
        self.c, self.i, self.a = c, i, a
        self.add_item(Select(options=[discord.SelectOption(label=x[:100]) for x in o[:25]]))
        self.children[0].callback = self.cb
    async def cb(self, interaction: discord.Interaction):
        self.a.append({"q": "Choice", "a": interaction.data['values'][0]})
        # We must defer update to allow transition
        await interaction.response.defer(ephemeral=True)
        # Disable old view
        await interaction.edit_original_response(content="✅ **Saved.** Loading next...", view=None)
        await run_question_step(interaction, self.c, self.i+1, self.a, is_followup=True)

class QuestionRadioView(View):
    def __init__(self, c, i, a, p, o):
        super().__init__(timeout=300)
        self.c, self.i, self.a = c, i, a
        for opt in o[:5]:
            btn = Button(label=opt[:80], style=discord.ButtonStyle.secondary)
            btn.callback = self.make_cb(opt)
            self.add_item(btn)
    def make_cb(self, val):
        async def cb(interaction: discord.Interaction):
            self.a.append({"q": "Selection", "a": val})
            await interaction.response.defer(ephemeral=True)
            await interaction.edit_original_response(content="✅ **Saved.** Loading next...", view=None)
            await run_question_step(interaction, self.c, self.i+1, self.a, is_followup=True)
        return cb

async def finish_verification(interaction, config, answers):
    unverified_id = config.get("unverified_role_id")
    guild = interaction.guild
    member = interaction.user
    msg_log = []

    # Role Removal Logic
    if unverified_id:
        unverified_role = guild.get_role(unverified_id)
        if unverified_role:
            try:
                await member.remove_roles(unverified_role)
                msg_log.append("🔓 Access Granted (Unverified role removed).")
            except Exception as e:
                msg_log.append(f"⚠️ Permission Error: Could not remove role. Check Bot Roles hierarchy!")
        else:
            msg_log.append("⚠️ Config Error: Unverified role ID not found in this server.")
    else:
        msg_log.append("ℹ️ No role removal configured.")

    final_msg = "\n".join(msg_log)
    await interaction.followup.send(f"🎉 **You are now Verified!**\n{final_msg}", ephemeral=True)

    # Logs
    try:
        log_channel = interaction.client.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(title=f"🛡️ Verified: {interaction.user.name}", color=0x00ff00)
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            for item in answers:
                embed.add_field(name=item['q'], value=str(item['a']), inline=False)
            await log_channel.send(embed=embed)
    except: pass

# ==========================================
# 🛠️ SETUP WIZARD (Admin)
# ==========================================
class SetupWizardView(View):
    def __init__(self, config):
        super().__init__(timeout=600)
        self.config = config
        self.q = config.get("questions", [])

    @discord.ui.button(label="+ Text Q", style=discord.ButtonStyle.primary, row=0)
    async def add_text(self, interaction, button): await interaction.response.send_modal(SetupTextModal(self))
    @discord.ui.button(label="+ Dropdown", style=discord.ButtonStyle.secondary, row=0)
    async def add_select(self, interaction, button): await interaction.response.send_modal(SetupOptionsModal(self, "select"))
    @discord.ui.button(label="+ Buttons", style=discord.ButtonStyle.secondary, row=0)
    async def add_radio(self, interaction, button): await interaction.response.send_modal(SetupOptionsModal(self, "radio"))
    
    @discord.ui.button(label="💾 Save Config", style=discord.ButtonStyle.success, row=1)
    async def save(self, interaction, button):
        self.config["questions"] = self.q
        await save_config(interaction.client, self.config)
        await interaction.response.edit_message(content=f"✅ **Saved!** {len(self.q)} questions.", view=None)

    async def update(self, interaction):
        t = "**Current Questions:**\n" + "\n".join([f"{i+1}. [{q['type'].upper()}] {q['prompt']}" for i,q in enumerate(self.q)])
        await interaction.response.edit_message(content=t, view=self)

class SetupTextModal(Modal):
    def __init__(self, parent): super().__init__(title="Add Text Q"); self.p = parent; self.inp = TextInput(label="Prompt"); self.add_item(self.inp)
    async def on_submit(self, interaction): self.p.q.append({"type":"text","prompt":self.inp.value}); await self.p.update(interaction)

class SetupOptionsModal(Modal):
    def __init__(self, parent, t): super().__init__(title=f"Add {t} Q"); self.p = parent; self.t = t; self.prompt = TextInput(label="Prompt"); self.opts = TextInput(label="Options (comma separated)"); self.add_item(self.prompt); self.add_item(self.opts)
    async def on_submit(self, interaction): self.p.q.append({"type":self.t,"prompt":self.prompt.value,"options":[x.strip() for x in self.opts.value.split(',')]}); await self.p.update(interaction)

# ==========================================
# 🚀 COMMANDS & EVENTS
# ==========================================

@client.tree.command(name="setup_verification", description="Setup verification questions")
@app_commands.describe(unverified_role="Select the Unverified Role")
async def setup_verification(interaction: discord.Interaction, unverified_role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("🚫 Admin only!", ephemeral=True)
    config = {"unverified_role_id": unverified_role.id, "questions": []}
    await interaction.response.send_message(f"🛠️ **Setup Wizard**\nRole to remove: {unverified_role.mention}", view=SetupWizardView(config), ephemeral=True)

@client.tree.command(name="verify", description="Start verification manually")
async def verify_command(interaction: discord.Interaction):
    await interaction.response.send_message("🛡️ **Verify Identity:**", view=StartVerificationView(), ephemeral=True)

@client.event
async def on_message(message):
    if message.author.bot: return

    # SYSTEM MESSAGE WATCHER
    if message.channel.id == WELCOME_CHANNEL_ID:
        is_join = message.type == discord.MessageType.new_member
        is_sim = (message.content == "!simulatejoin" and message.author.guild_permissions.administrator)

        if is_join or is_sim:
            print(f"👀 Event Detected! Sim: {is_sim}")
            target = message.author
            
            # 1. Try to Assign Role (Fail safe)
            try:
                config = await load_config(message.client)
                if config and config.get("unverified_role_id"):
                    role = message.guild.get_role(config["unverified_role_id"])
                    if role:
                        await target.add_roles(role)
                        print("🔒 Unverified Role Added")
            except Exception as e: print(f"⚠️ Role Error: {e}")

            # 2. Image & Button
            raw_text = "Welcome {user} to {server}! Verify to enter."
            welcome_text = raw_text.replace("{user}", target.mention).replace("{server}", message.guild.name)
            bg_url = await get_random_template(message.client)
            
            view = StartVerificationView()

            if bg_url:
                try:
                    res = requests.get(bg_url)
                    with Image.open(io.BytesIO(res.content)).convert("RGBA") as img:
                        final = create_naruto_text(img, target.name)
                        with io.BytesIO() as binary:
                            final.save(binary, 'PNG')
                            binary.seek(0)
                            f = discord.File(fp=binary, filename='welcome.png')
                            await message.channel.send(content=welcome_text, file=f, view=view)
                except Exception as e:
                    print(f"❌ Image Error: {e}")
                    await message.channel.send(content=welcome_text, view=view)
            else:
                await message.channel.send(content=welcome_text, view=view)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}!")
    client.add_view(StartVerificationView())

keep_alive()
client.run(os.environ['DISCORD_TOKEN'])
