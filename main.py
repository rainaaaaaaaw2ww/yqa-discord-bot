from flask import Flask, render_template, request, redirect, url_for
import asyncio
import threading
import discord
from discord.ext import commands
from discord.ui import View, Button
from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = os.getenv("TOKEN")
WEB_PASSWORD = os.getenv("WEB_PASSWORD")

intents = discord.Intents.default()
intents.members = True
intents.guilds = True

bot = commands.Bot(intents=intents)
app = Flask(__name__)

MESSAGES = {
    "already_has": "\u4f60\u5df2\u7d93\u6709 {role}",
    "added": "\u5df2\u7d66\u4e88 {role}",
    "no_role": "\u76ee\u524d\u6c92\u6709\u53ef\u9078\u7684\u8eab\u5206\u7d44",
    "role_not_found": "\u627e\u4e0d\u5230\u8eab\u5206\u7d44",
    "guild_not_found": "\u627e\u4e0d\u5230\u9019\u500b\u4f3a\u670d\u5668\uff0c\u8acb\u78ba\u8a8d Bot \u5df2\u52a0\u5165\u4f3a\u670d\u5668\u3002",
    "channel_not_found": "\u627e\u4e0d\u5230\u9019\u500b\u983b\u9053",
    "wrong_password": "\u5bc6\u78bc\u932f\u8aa4",
    "select_role": "\u8acb\u9078\u64c7\u8eab\u5206\u7d44",
    "too_many_roles": "\u4e00\u500b\u4e0b\u62c9\u9078\u55ae\u6700\u591a\u53ea\u80fd\u653e 25 \u500b\u8eab\u5206\u7d44",
}


def get_selectable_roles(guild):
    return [
        role for role in guild.roles
        if not role.is_default()
        and not role.managed
        and guild.me
        and role < guild.me.top_role
    ]


async def give_role(member, selected_role):
    if selected_role in member.roles:
        return MESSAGES["already_has"].format(role=selected_role.name)

    await member.add_roles(selected_role)
    return MESSAGES["added"].format(role=selected_role.name)


class RoleButton(Button):
    def __init__(self, role):
        super().__init__(
            label=role.name[:80],
            style=discord.ButtonStyle.secondary,
            custom_id=f"role_button_{role.id}",
        )
        self.role_id = role.id

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)

        if not role:
            await interaction.response.send_message(MESSAGES["role_not_found"], ephemeral=True)
            return

        msg = await give_role(interaction.user, role)
        await interaction.response.send_message(msg, ephemeral=True)


def create_role_view(guild, role_ids):
    roles = [
        role for role_id in role_ids
        if (role := guild.get_role(role_id)) is not None
    ]
    view = View(timeout=None)

    if not roles:
        view.add_item(
            Button(
                label=MESSAGES["no_role"],
                style=discord.ButtonStyle.secondary,
                disabled=True,
            )
        )
        return view

    for role in roles[:25]:
        view.add_item(RoleButton(role))

    return view


def register_persistent_role_buttons():
    registered = 0

    for guild in bot.guilds:
        roles = get_selectable_roles(guild)

        for start in range(0, len(roles), 25):
            view = View(timeout=None)

            for role in roles[start:start + 25]:
                view.add_item(RoleButton(role))
                registered += 1

            if view.children:
                bot.add_view(view)

    print(f"Registered {registered} persistent role buttons")


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", guilds=bot.guilds, channels=[])


@app.route("/guild/<int:guild_id>", methods=["GET"])
def guild_page(guild_id):
    guild = bot.get_guild(guild_id)

    if not guild:
        return MESSAGES["guild_not_found"]

    channels = [
        channel for channel in guild.text_channels
        if channel.permissions_for(guild.me).send_messages
    ]
    roles = get_selectable_roles(guild)

    return render_template(
        "index.html",
        guilds=bot.guilds,
        selected_guild=guild,
        channels=channels,
        roles=roles,
    )


async def send_role_menu(guild_id, channel_id, role_ids, title, description, color):
    guild = bot.get_guild(guild_id)

    if not guild:
        raise ValueError(MESSAGES["guild_not_found"])

    channel = guild.get_channel(channel_id)

    if not channel:
        raise ValueError(MESSAGES["channel_not_found"])

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
    )

    view = create_role_view(guild, role_ids)
    await channel.send(embed=embed, view=view)


@app.route("/send", methods=["POST"])
def send_menu():
    password = request.form.get("password")

    if password != WEB_PASSWORD:
        return MESSAGES["wrong_password"]

    guild_id = int(request.form.get("guild_id"))
    channel_id = int(request.form.get("channel_id"))
    role_ids = [int(role_id) for role_id in request.form.getlist("role_ids")]
    title = request.form.get("title")
    description = request.form.get("description")
    color = int(request.form.get("color", "#5865f2").replace("#", ""), 16)

    if len(role_ids) > 25:
        return MESSAGES["too_many_roles"], 400

    future = asyncio.run_coroutine_threadsafe(
        send_role_menu(guild_id, channel_id, role_ids, title, description, color),
        bot.loop,
    )

    try:
        future.result(timeout=10)
    except Exception as exc:
        return str(exc), 500

    return redirect(url_for("guild_page", guild_id=guild_id))


def run_web():
    app.run(host="0.0.0.0", port=5000)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    for guild in bot.guilds:
        print(f"Guild: {guild.name} / ID: {guild.id}")

    if not getattr(bot, "persistent_buttons_registered", False):
        bot.persistent_buttons_registered = True
        register_persistent_role_buttons()

    if not getattr(bot, "web_started", False):
        bot.web_started = True
        threading.Thread(target=run_web, daemon=True).start()


if not TOKEN:
    raise RuntimeError("TOKEN is missing in .env")

bot.run(TOKEN)
