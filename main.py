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
def home(): return "Dattebayo! Role Picker System Online! 🛡️"
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
# 🛡️ VERIFICATION LOGIC
# ==========================================

class StartVerificationView(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Verify Identity", style=discord.ButtonStyle.success, emoji="🛡️", custom_id="start_verify_btn")
    async def verify_button(self, interaction: discord.Interaction, button: Button):
        config = await load_config(interaction.client)
        if not config or not config.get("questions"):
            return await interaction.response.send_message("❌ Verification not configured.", ephemeral=True)
        await run_question_step(interaction, config, 0, [])

async def run_question_step(interaction, config, index, answers):
    questions = config["questions"]
    if index >= len(questions):
        await finish_verification(interaction, config, answers)
        return

    q = questions[index]
    if q["type"] == "text":
        modal = QuestionModal(config, index, answers, q["prompt"])
        try: await interaction.response.send_modal(modal)
        except: await interaction.response.send_message("📝 **Next:**", view=ContinueView(config, index, answers, q["prompt"]), ephemeral=True)
    elif q["type"] == "select":
        view = QuestionSelectView(config, index, answers, q["prompt"], q["options"])
        try: await interaction.response.send_message(f"🔻 **Q{index+1}:** {q['prompt']}", view=view, ephemeral=True)
        except: await interaction.followup.send(f"🔻 **Q{index+1}:** {q['prompt']}", view=view, ephemeral=True)
    elif q["type"] == "radio":
        view = QuestionRadioView(config, index, answers, q["prompt"], q["options"])
        try: await interaction.response.send_message(f"🔘 **Q{index+1}:** {q['prompt']}", view=view, ephemeral=True)
        except: await interaction.followup.send(f"🔘 **Q{index+1}:** {q['prompt']}", view=view, ephemeral=True)

# UI Components
class QuestionModal(Modal):
    def __init__(self, config, index, answers, prompt):
        super().__init__(title=f"Question {index+1}")
        self.c, self.i, self.a = config, index, answers
        self.inp = TextInput(label=prompt[:45], required=True)
        self.add_item(self.inp)
    async def on_submit(self, interaction):
        self.a.append({"q": self.inp.label, "a": self.inp.value})
        await run_question_step(interaction, self.c, self.i + 1, self.a)

class ContinueView(View):
    def __init__(self, c, i, a, p):
        super().__init__(timeout=180)
        self.c, self.i, self.a, self.p = c, i, a, p
    @discord.ui.button(label="Answer", style=discord.ButtonStyle.primary)
    async def go(self, interaction, button):
        await interaction.response.send_modal(QuestionModal(self.c, self.i, self.a, self.p))

class QuestionSelectView(View):
    def __init__(self, c, i, a, p, o):
        super().__init__(timeout=180)
        self.c, self.i, self.a = c, i, a
        self.add_item(Select(options=[discord.SelectOption(label=x) for x in o[:25]]))
        self.children[0].callback = self.cb
    async def cb(self, interaction):
        self.a.append({"q": "Choice", "a": interaction.data['values'][0]})
        await interaction.response.edit_message(view=None)
        await run_question_step(interaction, self.c, self.i+1, self.a)

class QuestionRadioView(View):
    def __init__(self, c, i, a, p, o):
        super().__init__(timeout=180)
        self.c, self.i, self.a = c, i, a
        for opt in o[:5]:
            btn = Button(label=opt, style=discord.ButtonStyle.secondary)
            btn.callback = self.make_cb(opt)
            self.add_item(btn)
    def make_cb(self, val):
        async def cb(interaction):
            self.a.append({"q": "Selection", "a": val})
            await interaction.response.edit_message(view=None)
            await run_question_step(interaction, self.c, self.i+1, self.a)
        return cb

async def finish_verification(interaction, config, answers):
    # 🔄 REMOVE UNVERIFIED ROLE 🔄
    unverified_id = config.get("unverified_role_id")
    guild = interaction.guild
    member = interaction.user
    msg_log = []

    if unverified_id:
        unverified_role = guild.get_role(unverified_id)
        if unverified_role:
            try:
                await member.remove_roles(unverified_role)
                msg_log.append("🔓 Un-verified role removed.")
            except Exception as e:
                msg_log.append(f"⚠️ Failed to remove role: {e}")
        else:
            msg_log.append("⚠️ Configured role not found.")
    else:
        msg_log.append("⚠️ No role configured to remove.")

    final_msg = "\n".join(msg_log)
    await interaction.followup.send(f"🎉 **Verification Complete!**\n{final_msg}", ephemeral=True)

    # Log to Channel
    try:
        log_channel = interaction.client.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(title=f"🛡️ Verified: {interaction.user.name}", color=0x00ff00)
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            for item in answers:
                embed.add_field(name=item['q'], value=item['a'], inline=False)
            await log_channel.send(embed=embed)
    except: pass

# ==========================================
# 🛠️ SETUP WIZARD
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
        t = "**Questions:**\n" + "\n".join([f"{i+1}. {q['prompt']}" for i,q in enumerate(self.q)])
        await interaction.response.edit_message(content=t, view=self)

class SetupTextModal(Modal):
    def __init__(self, parent): super().__init__(title="Add Text Q"); self.p = parent; self.inp = TextInput(label="Prompt"); self.add_item(self.inp)
    async def on_submit(self, interaction): self.p.q.append({"type":"text","prompt":self.inp.value}); await self.p.update(interaction)

class SetupOptionsModal(Modal):
    def __init__(self, parent, t): super().__init__(title=f"Add {t} Q"); self.p = parent; self.t = t; self.prompt = TextInput(label="Prompt"); self.opts = TextInput(label="Options (comma separated)"); self.add_item(self.prompt); self.add_item(self.opts)
    async def on_submit(self, interaction): self.p.q.append({"type":self.t,"prompt":self.prompt.value,"options":[x.strip() for x in self.opts.value.split(',')]}); await self.p.update(interaction)

# ==========================================
# 🚀 MAIN COMMANDS
# ==========================================

@client.tree.command(name="setup_verification", description="Setup the Unverified role and questions")
@app_commands.describe(unverified_role="Select the role to remove after verification")
async def setup_verification(interaction: discord.Interaction, unverified_role: discord.Role):
    """
    Admin command to setup the system.
    Using 'discord.Role' type allows the user to SELECT the role from a list.
    No typing mistakes possible! 🛡️
    """
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("🚫 Admin only!", ephemeral=True)
    
    # Save the Role ID safely
    config = {
        "unverified_role_id": unverified_role.id,
        "questions": []
    }
    await interaction.response.send_message(f"🛠️ **Setup Wizard:**\nSelected Role: {unverified_role.mention}\nAdd your questions below:", view=SetupWizardView(config), ephemeral=True)

@client.tree.command(name="verify", description="Start verification")
async def verify_command(interaction: discord.Interaction):
    await interaction.response.send_message("🛡️ **Verify:**", view=StartVerificationView(), ephemeral=True)

@client.event
async def on_message(message):
    if message.author.bot: return

    # SYSTEM MESSAGE WATCHER (Join Event)
    if message.channel.id == WELCOME_CHANNEL_ID:
        is_join = message.type == discord.MessageType.new_member
        is_sim = (message.content == "!simulatejoin" and message.author.guild_permissions.administrator)

        if is_join or is_sim:
            target = message.author
            
            # 1. ASSIGN UNVERIFIED ROLE IMMEDIATELY
            try:
                config = await load_config(message.client)
                if config and config.get("unverified_role_id"):
                    role = message.guild.get_role(config["unverified_role_id"])
                    if role:
                        await target.add_roles(role)
                        print(f"🔒 Unverified role assigned to {target.name}")
            except Exception as e:
                print(f"❌ Failed to assign unverified role: {e}")

            # 2. GENERATE IMAGE
            raw_text = "Welcome {user} to {server}! Please verify to gain access."
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
                except: await message.channel.send(content=welcome_text, view=view)
            else:
                await message.channel.send(content=welcome_text, view=view)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}!")
    client.add_view(StartVerificationView())

keep_alive()
client.run(os.environ['DISCORD_TOKEN'])
