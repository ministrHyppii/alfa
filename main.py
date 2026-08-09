# ФУНКЦИЯ импорт библиотек
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View, Button
import json
import os
import re
import functools
import aiosqlite
from datetime import datetime, timedelta
import asyncio
from dotenv import load_dotenv

# ---------- ЗАГРУЗКА ТОКЕНА ----------
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    raise ValueError("Не найден BOT_TOKEN в .env")

# ---------- КОНФИГУРАЦИОННЫЕ ФАЙЛЫ ----------
CONFIG_FILE = 'roles_config.json'
HIERARCHY_FILE = 'hierarchy.json'
PERMISSIONS_FILE = 'permissions.json'
TICKET_CONFIG_FILE = 'ticket_config.json'
PUNISHMENT_CONFIG_FILE = 'punishment_config.json'
DB_PATH = "tickets.db"

# ---------- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ----------
roster_messages = {}  # {channel_id: message_id}
ROLE_HIERARCHY = []

# ---------- ФУНКЦИИ ЗАГРУЗКИ/СОХРАНЕНИЯ ----------
# ФУНКЦИЯ def load_hierarchy
def load_hierarchy():
    global ROLE_HIERARCHY
    if not os.path.exists(HIERARCHY_FILE):
        default = [
            "Глава", "Зам главы", "Тех администратор",
            "Модератор", "Модератор дискорда",
            "Работа с таблицей", "Бустер", "Младший модератор"
        ]
        save_hierarchy(default)
        return default
    with open(HIERARCHY_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_hierarchy(hierarchy):
    with open(HIERARCHY_FILE, 'w', encoding='utf-8') as f:
        json.dump(hierarchy, f, indent=4, ensure_ascii=False)

ROLE_HIERARCHY = load_hierarchy()

def load_roles():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_roles(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_permissions():
    if not os.path.exists(PERMISSIONS_FILE):
        return {}
    with open(PERMISSIONS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_permissions(data):
    with open(PERMISSIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_ticket_config():
    if not os.path.exists(TICKET_CONFIG_FILE):
        default = {
            "admin_channel_id": None,
            "allowed_roles": ["Глава", "Зам главы", "Тех администратор"]
        }
        save_ticket_config(default)
        return default
    with open(TICKET_CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_ticket_config(data):
    with open(TICKET_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

TICKET_CONFIG = load_ticket_config()

# ---------- КОНФИГУРАЦИЯ НАКАЗАНИЙ ----------
def load_punishment_config():
    if not os.path.exists(PUNISHMENT_CONFIG_FILE):
        default = {
            "channel_id": None,
            "allowed_roles": ["Глава", "Зам главы", "Тех администратор"]
        }
        save_punishment_config(default)
        return default
    with open(PUNISHMENT_CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_punishment_config(data):
    with open(PUNISHMENT_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

PUNISHMENT_CONFIG = load_punishment_config()

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
def get_user_role_level(user: discord.Member, config: dict):
    user_role_ids = [role.id for role in user.roles]
    for level, role_name in enumerate(ROLE_HIERARCHY):
        if role_name in config:
            role_id = config[role_name]
            if role_id in user_role_ids:
                return level, role_name
    return None, None

def has_role(user: discord.Member, role_name: str, config: dict) -> bool:
    if role_name not in config:
        return False
    role_id = config[role_name]
    return any(role.id == role_id for role in user.roles)

def check_management_permissions(interaction: discord.Interaction) -> bool:
    config = load_roles()
    level, _ = get_user_role_level(interaction.user, config)
    if level is None or level > 2:
        return False
    return True

def check_command_permission(interaction: discord.Interaction, command_name: str) -> bool:
    perms = load_permissions()
    if command_name not in perms:
        return True
    required_role = perms[command_name]
    config = load_roles()
    level, _ = get_user_role_level(interaction.user, config)
    if level is None:
        return False
    if required_role not in ROLE_HIERARCHY:
        return False
    required_level = ROLE_HIERARCHY.index(required_role)
    return level <= required_level

def check_ticket_permission(user: discord.Member) -> bool:
    config = load_roles()
    allowed = TICKET_CONFIG.get("allowed_roles", [])
    if not allowed:
        return False
    level, _ = get_user_role_level(user, config)
    if level is None:
        return False
    min_level = None
    for r in allowed:
        if r in ROLE_HIERARCHY:
            idx = ROLE_HIERARCHY.index(r)
            if min_level is None or idx < min_level:
                min_level = idx
    if min_level is None:
        return False
    return level <= min_level

def check_punishment_permission(user: discord.Member) -> bool:
    config = load_roles()
    allowed = PUNISHMENT_CONFIG.get("allowed_roles", [])
    if not allowed:
        return False
    level, _ = get_user_role_level(user, config)
    if level is None:
        return False
    min_level = None
    for r in allowed:
        if r in ROLE_HIERARCHY:
            idx = ROLE_HIERARCHY.index(r)
            if min_level is None or idx < min_level:
                min_level = idx
    if min_level is None:
        return False
    return level <= min_level

# ---------- ДЕКОРАТОР ДЛЯ ПРОВЕРКИ ПРАВ ----------
def require_permission(command_name: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if not check_command_permission(interaction, command_name):
                await interaction.response.send_message(
                    '❌ У вас недостаточно прав для использования этой команды.',
                    ephemeral=True
                )
                return
            return await func(interaction, *args, **kwargs)
        return wrapper
    return decorator

# ---------- ФУНКЦИЯ ОБНОВЛЕНИЯ ТАБЛИЦЫ ----------
async def update_roster(channel: discord.TextChannel):
    if channel.id not in roster_messages:
        return
    try:
        msg = await channel.fetch_message(roster_messages[channel.id])
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        del roster_messages[channel.id]
        return

    config = load_roles()
    users = []
    for member in channel.guild.members:
        level, role_name = get_user_role_level(member, config)
        if role_name:
            users.append((member, level, role_name))
    users.sort(key=lambda x: x[1] if x[1] is not None else 999)

    embed = discord.Embed(title="📋 Таблица ролей участников", color=discord.Color.blue())
    if not users:
        embed.description = "Нет участников с ролями из иерархии."
    else:
        lines = []
        for member, level, role_name in users[:30]:
            lines.append(f"{member.mention} — **{role_name}**")
        embed.description = "\n".join(lines)
        if len(users) > 30:
            embed.set_footer(text=f"Показано 30 из {len(users)} участников")
        else:
            embed.set_footer(text=f"Всего: {len(users)} участников")
    await msg.edit(embed=embed)

# ---------- БАЗА ДАННЫХ ----------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Создаём таблицу tickets, если её нет
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER UNIQUE,
                message_id INTEGER,
                user_id INTEGER,
                target_user_id TEXT,
                description TEXT,
                location TEXT,
                ps TEXT,
                status TEXT DEFAULT 'waiting',
                admin_id INTEGER,
                reason TEXT,
                punishment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Добавляем колонку closed_at, если её нет
        cursor = await db.execute("PRAGMA table_info(tickets)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        if 'closed_at' not in column_names:
            await db.execute('ALTER TABLE tickets ADD COLUMN closed_at TIMESTAMP')
            print("✅ Добавлена колонка closed_at в таблицу tickets")

        # Создаём таблицу punishments
        await db.execute('''
            CREATE TABLE IF NOT EXISTS punishments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                admin_id INTEGER,
                type TEXT,
                reason TEXT,
                conditions TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                removed_at TIMESTAMP,
                removed_by INTEGER,
                removed_reason TEXT,
                converted_to INTEGER
            )
        ''')
        await db.commit()

async def get_ticket_by_channel(channel_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM tickets WHERE channel_id = ?", (channel_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(zip(
                    ["id", "channel_id", "message_id", "user_id", "target_user_id",
                     "description", "location", "ps", "status", "admin_id", "reason", "punishment", "created_at", "closed_at"],
                    row
                ))
    return None

async def update_ticket_status(channel_id, status, admin_id=None, reason=None, punishment=None):
    async with aiosqlite.connect(DB_PATH) as db:
        query = "UPDATE tickets SET status = ?"
        params = [status]
        if admin_id is not None:
            query += ", admin_id = ?"
            params.append(admin_id)
        if reason is not None:
            query += ", reason = ?"
            params.append(reason)
        if punishment is not None:
            query += ", punishment = ?"
            params.append(punishment)
        if status in ("approved", "rejected"):
            query += ", closed_at = CURRENT_TIMESTAMP"
        query += " WHERE channel_id = ?"
        params.append(channel_id)
        await db.execute(query, params)
        await db.commit()

async def update_status_message(bot, channel_id, ticket):
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    try:
        msg = await channel.fetch_message(ticket["message_id"])
    except:
        return

    status_emoji = {
        "waiting": "⏳", "reviewing": "⚠️", "approved": "✅", "rejected": "❌"
    }
    status_text = {
        "waiting": "Ожидает принятия", "reviewing": "В рассмотрении",
        "approved": "Одобрено (наказание выдано)", "rejected": "Отказано"
    }
    embed = discord.Embed(
        title=f"📩 Тикет #{ticket['id']}",
        color=0x00ff00 if ticket["status"] == "approved" else 0xff0000 if ticket["status"] == "rejected" else 0xffaa00,
        timestamp=datetime.now()
    )
    embed.add_field(name="Подал", value=f"<@{ticket['user_id']}>", inline=True)
    embed.add_field(name="Нарушитель", value=ticket['target_user_id'], inline=True)
    embed.add_field(name="Статус",
                    value=f"{status_emoji.get(ticket['status'], '')} {status_text.get(ticket['status'], '')}",
                    inline=False)
    embed.add_field(name="Суть", value=ticket['description'], inline=False)
    if ticket['location']:
        embed.add_field(name="Место", value=ticket['location'], inline=True)
    if ticket['ps']:
        embed.add_field(name="PS", value=ticket['ps'], inline=True)
    if ticket['reason']:
        embed.add_field(name="Причина закрытия", value=ticket['reason'], inline=False)
    if ticket['punishment']:
        embed.add_field(name="Наказание", value=ticket['punishment'], inline=False)
    if ticket['closed_at']:
        try:
            closed_dt = datetime.strptime(ticket['closed_at'], "%Y-%m-%d %H:%M:%S")
            delete_time = closed_dt + timedelta(hours=24)
            embed.set_footer(text=f"Канал будет удалён {delete_time.strftime('%d.%m.%Y в %H:%M')}")
        except:
            pass
    await msg.edit(embed=embed)

# ---------- ФУНКЦИИ ДЛЯ НАКАЗАНИЙ ----------
async def add_punishment(user_id, admin_id, type, reason, conditions=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO punishments (user_id, admin_id, type, reason, conditions) VALUES (?, ?, ?, ?, ?)",
            (user_id, admin_id, type, reason, conditions)
        )
        await db.commit()
        return cursor.lastrowid

async def get_active_punishments(user_id, type=None):
    async with aiosqlite.connect(DB_PATH) as db:
        if type:
            cursor = await db.execute(
                "SELECT * FROM punishments WHERE user_id = ? AND type = ? AND status = 'active'",
                (user_id, type)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM punishments WHERE user_id = ? AND status = 'active'",
                (user_id,)
            )
        rows = await cursor.fetchall()
        columns = ["id", "user_id", "admin_id", "type", "reason", "conditions", "status", "created_at", "removed_at", "removed_by", "removed_reason", "converted_to"]
        return [dict(zip(columns, row)) for row in rows]

async def remove_punishment(punishment_id, removed_by, reason):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE punishments SET status = 'removed', removed_at = CURRENT_TIMESTAMP, removed_by = ?, removed_reason = ? WHERE id = ?",
            (removed_by, reason, punishment_id)
        )
        await db.commit()

async def get_user_punishments_summary(user_id):
    warnings = await get_active_punishments(user_id, 'warning')
    reprimands = await get_active_punishments(user_id, 'reprimand')
    return len(warnings), len(reprimands)

async def check_and_convert_warnings(user_id, bot):
    warnings = await get_active_punishments(user_id, 'warning')
    if len(warnings) >= 3:
        to_convert = warnings[:3]
        reason = "3 предупреждения (автоматическая конвертация)"
        reprimand_id = await add_punishment(user_id, 0, 'reprimand', reason, None)
        async with aiosqlite.connect(DB_PATH) as db:
            for w in to_convert:
                await db.execute(
                    "UPDATE punishments SET status = 'converted', converted_to = ? WHERE id = ?",
                    (reprimand_id, w['id'])
                )
            await db.commit()
        await send_punishment_notification(bot, user_id, 'reprimand', reason, admin_name="Система", conditions=None, converted_from_warnings=True)
        return True
    return False

async def check_and_reset_reprimands(user_id, bot):
    reprimands = await get_active_punishments(user_id, 'reprimand')
    if len(reprimands) >= 3:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE punishments SET status = 'expired' WHERE user_id = ? AND status = 'active'",
                (user_id,)
            )
            await db.commit()
        channel_id = PUNISHMENT_CONFIG.get('channel_id')
        if channel_id:
            channel = bot.get_channel(channel_id)
            if channel:
                embed = discord.Embed(
                    title="⚠️ Достигнут лимит выговоров",
                    description=f"У пользователя <@{user_id}> накопилось 3 выговора. Все его активные наказания сброшены.",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                await channel.send(embed=embed)
        return True
    return False

async def send_punishment_notification(bot, user_id, type, reason, admin_name, conditions=None, converted_from_warnings=False):
    channel_id = PUNISHMENT_CONFIG.get('channel_id')
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if not channel:
        return

    if type == 'warning':
        title = "⚠️ Предупреждение"
        color = discord.Color.orange()
    else:
        title = "📢 Выговор"
        color = discord.Color.red()

    embed = discord.Embed(title=title, color=color, timestamp=datetime.now())
    embed.add_field(name="Пользователь", value=f"<@{user_id}>", inline=True)
    embed.add_field(name="Выдал", value=admin_name, inline=True)
    embed.add_field(name="Причина", value=reason, inline=False)
    if conditions:
        embed.add_field(name="Условия снятия", value=conditions, inline=False)
    if converted_from_warnings:
        embed.add_field(name="Примечание", value="Конвертировано из 3 предупреждений", inline=False)
    await channel.send(embed=embed)

# ---------- ФОНОВАЯ ЗАДАЧА ДЛЯ УДАЛЕНИЯ КАНАЛОВ ----------
async def delete_expired_tickets(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT channel_id FROM tickets WHERE status IN ('approved', 'rejected') AND datetime(closed_at) <= datetime('now', '-1 day')"
                )
                rows = await cursor.fetchall()
                for row in rows:
                    channel_id = row[0]
                    channel = bot.get_channel(channel_id)
                    if channel:
                        try:
                            await channel.delete(reason="Автоматическое удаление через 24 часа после закрытия")
                            print(f"Канал {channel.name} удалён.")
                        except Exception as e:
                            print(f"Ошибка удаления канала {channel_id}: {e}")
                    await db.execute("DELETE FROM tickets WHERE channel_id = ?", (channel_id,))
                await db.commit()
        except Exception as e:
            print(f"Ошибка в delete_expired_tickets: {e}")
        await asyncio.sleep(60)

# ---------- ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ ПОЛЬЗОВАТЕЛЯ ИЗ REPLY ----------
async def get_target_from_reply(interaction: discord.Interaction):
    if interaction.message and interaction.message.reference:
        try:
            referenced = await interaction.channel.fetch_message(interaction.message.reference.message_id)
            if referenced.mentions:
                return referenced.mentions[0]
        except:
            pass
    return None

# ---------- КЛАССЫ ДЛЯ ТИКЕТОВ ----------
class RejectModal(discord.ui.Modal, title="❌ Отказ в жалобе"):
    reason = discord.ui.TextInput(label="Причина отказа", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, channel_id):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await update_ticket_status(self.channel_id, "rejected", reason=self.reason.value)
        ticket = await get_ticket_by_channel(self.channel_id)
        if ticket:
            await update_status_message(interaction.client, self.channel_id, ticket)
        try:
            await interaction.message.edit(view=None)
        except:
            pass
        await interaction.followup.send("✅ Тикет закрыт с отказом. Канал будет удалён через 24 часа.", ephemeral=True)

class ApproveModal(discord.ui.Modal, title="✅ Одобрение жалобы"):
    reason = discord.ui.TextInput(label="Причина закрытия", style=discord.TextStyle.paragraph, required=True)
    punishment = discord.ui.TextInput(label="Наказание", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, channel_id):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await update_ticket_status(self.channel_id, "approved", reason=self.reason.value, punishment=self.punishment.value)
        ticket = await get_ticket_by_channel(self.channel_id)
        if ticket:
            await update_status_message(interaction.client, self.channel_id, ticket)
        try:
            await interaction.message.edit(view=None)
        except:
            pass
        await interaction.followup.send("✅ Тикет одобрен и закрыт. Канал будет удалён через 24 часа.", ephemeral=True)

class TicketActionView(discord.ui.View):
    def __init__(self, ticket_id, channel_id, user_id):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.channel_id = channel_id
        self.user_id = user_id

    @discord.ui.button(label="⚠️ В рассмотрение", style=discord.ButtonStyle.primary, custom_id="ticket_review")
    async def review_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not check_ticket_permission(interaction.user):
            return await interaction.response.send_message("❌ У вас нет прав на обработку тикетов.", ephemeral=True)

        await update_ticket_status(self.channel_id, "reviewing", admin_id=interaction.user.id)

        channel = interaction.guild.get_channel(self.channel_id)
        if channel:
            try:
                await channel.set_permissions(interaction.user, view_channel=True, send_messages=True, read_messages=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Ошибка добавления прав: {e}", ephemeral=True)
                return
            try:
                await channel.send(f"{interaction.user.mention} взял тикет в рассмотрение.")
            except:
                pass

        ticket = await get_ticket_by_channel(self.channel_id)
        if ticket:
            await update_status_message(interaction.client, self.channel_id, ticket)

        try:
            await interaction.message.edit(view=None)
        except:
            pass

        await interaction.response.send_message("✅ Тикет взят в рассмотрение. Вы добавлены в канал.", ephemeral=True)

    @discord.ui.button(label="❌ Отказать", style=discord.ButtonStyle.danger, custom_id="ticket_reject")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not check_ticket_permission(interaction.user):
            return await interaction.response.send_message("❌ У вас нет прав на обработку тикетов.", ephemeral=True)
        modal = RejectModal(self.channel_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="✅ Одобрить", style=discord.ButtonStyle.success, custom_id="ticket_approve")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not check_ticket_permission(interaction.user):
            return await interaction.response.send_message("❌ У вас нет прав на обработку тикетов.", ephemeral=True)
        modal = ApproveModal(self.channel_id)
        await interaction.response.send_modal(modal)

class ReportModal(discord.ui.Modal, title="📝 Подача жалобы"):
    your_name = discord.ui.TextInput(label="1. Ваш ник", placeholder="Введите ваш игровой ник", required=True)
    target_name = discord.ui.TextInput(label="2. Ник нарушителя", placeholder="Кто нарушил?", required=True)
    description = discord.ui.TextInput(label="3. Суть жалобы", style=discord.TextStyle.paragraph, required=True)
    location = discord.ui.TextInput(label="4. Где произошло (необяз.)", required=False)
    ps = discord.ui.TextInput(label="5. PS (необяз.)", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("❌ Эта команда доступна только на сервере.", ephemeral=True)

        guild = interaction.guild
        category_name = "📩 Тикеты"
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            try:
                category = await guild.create_category(category_name)
            except:
                category = None

        channel_name = f"тикет-{interaction.user.display_name[:15]}-{interaction.user.id % 1000}"
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
            }
            for role_name in TICKET_CONFIG.get("allowed_roles", []):
                role = discord.utils.get(guild.roles, name=role_name)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)

            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Тикет от {interaction.user}"
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Не удалось создать канал: {e}", ephemeral=True)
            return

        embed = discord.Embed(title="📩 Новый тикет", color=0xffaa00, timestamp=datetime.now())
        embed.add_field(name="Подал", value=f"{interaction.user.mention} ({interaction.user.display_name})", inline=True)
        embed.add_field(name="Нарушитель", value=self.target_name.value, inline=True)
        embed.add_field(name="Статус", value="⏳ Ожидает принятия", inline=False)
        embed.add_field(name="Суть", value=self.description.value, inline=False)
        if self.location.value:
            embed.add_field(name="Место", value=self.location.value, inline=True)
        if self.ps.value:
            embed.add_field(name="PS", value=self.ps.value, inline=True)

        msg = await channel.send(embed=embed)

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO tickets (channel_id, message_id, user_id, target_user_id, description, location, ps) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (channel.id, msg.id, interaction.user.id, self.target_name.value, self.description.value,
                 self.location.value or "", self.ps.value or "")
            )
            await db.commit()
            ticket_id = cursor.lastrowid

        admin_channel_id = TICKET_CONFIG.get("admin_channel_id")
        if admin_channel_id:
            admin_channel = interaction.guild.get_channel(admin_channel_id)
            if admin_channel:
                view = TicketActionView(ticket_id, channel.id, interaction.user.id)
                admin_embed = discord.Embed(
                    title=f"🆕 Новый тикет #{ticket_id}",
                    color=0x00aaff,
                    timestamp=datetime.now()
                )
                admin_embed.add_field(name="Игрок", value=f"<@{interaction.user.id}>", inline=True)
                admin_embed.add_field(name="Нарушитель", value=self.target_name.value, inline=True)
                admin_embed.add_field(name="Суть", value=self.description.value[:100] + "...", inline=False)
                admin_embed.set_footer(text="Нажмите кнопку для действий")
                await admin_channel.send(embed=admin_embed, view=view)
            else:
                await interaction.followup.send("⚠️ Канал уведомлений не найден, но тикет создан.", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Канал уведомлений не настроен. Используйте `/ticket_setchannel`.", ephemeral=True)

        await interaction.followup.send(f"✅ Тикет создан! Перейдите в канал: {channel.mention}", ephemeral=True)

# ---------- КЛАСС ДЛЯ ВЫБОРА РОЛИ ----------
class RoleSelectView(View):
    def __init__(self, config, guild):
        super().__init__()
        self.config = config
        self.guild = guild
        self.select = Select(
            placeholder="Выберите роль для сохранения",
            min_values=1,
            max_values=1,
            options=[]
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        role_id = int(self.select.values[0])
        role = self.guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message('❌ Роль не найдена.', ephemeral=True)
            return
        if role.name not in ROLE_HIERARCHY:
            await interaction.response.send_message(
                f'❌ Роль "{role.name}" не входит в иерархию. Доступны: {", ".join(ROLE_HIERARCHY)}',
                ephemeral=True
            )
            return
        self.config[role.name] = role.id
        save_roles(self.config)
        embed = discord.Embed(
            title='✅ Роль сохранена',
            description=f'**{role.name}** → {role.mention} (ID: `{role.id}`)',
            color=discord.Color.green()
        )
        await interaction.response.edit_message(content="", embed=embed, view=None)
        await update_roster(interaction.channel)

# ---------- МОДАЛЬНЫЕ ОКНА ДЛЯ НАКАЗАНИЙ (с динамической статистикой) ----------
class WarningModal(discord.ui.Modal, title="⚠️ Выдача предупреждения"):
    def __init__(self, user=None):
        super().__init__()
        self.user = user
        self.user_input = discord.ui.TextInput(
            label="Пользователь (или ответьте на сообщение)",
            placeholder="Например: @user или имя",
            required=False
        )
        self.reason = discord.ui.TextInput(
            label="Причина",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.conditions = discord.ui.TextInput(
            label="Условия снятия (необяз.)",
            required=False
        )
        self.add_item(self.user_input)
        self.add_item(self.reason)
        self.add_item(self.conditions)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        target = None
        if self.user_input.value:
            raw = self.user_input.value.strip()
            if raw.startswith('<@') and raw.endswith('>'):
                user_id = int(raw.strip('<@!>'))
                target = interaction.guild.get_member(user_id)
            elif raw.isdigit():
                target = interaction.guild.get_member(int(raw))
            else:
                for member in interaction.guild.members:
                    if member.name.lower() == raw.lower() or member.display_name.lower() == raw.lower():
                        target = member
                        break
                if not target:
                    for member in interaction.guild.members:
                        if member.name.lower().startswith(raw.lower()) or member.display_name.lower().startswith(raw.lower()):
                            target = member
                            break

        if not target:
            target = await get_target_from_reply(interaction)

        if not target:
            await interaction.followup.send(
                "❌ Не удалось определить пользователя. Укажите его в поле или ответьте на сообщение бота с упоминанием.",
                ephemeral=True
            )
            return

        if not check_punishment_permission(interaction.user):
            await interaction.followup.send("❌ У вас нет прав на выдачу наказаний.", ephemeral=True)
            return

        await add_punishment(target.id, interaction.user.id, 'warning', self.reason.value, self.conditions.value or None)
        await send_punishment_notification(
            interaction.client,
            target.id,
            'warning',
            self.reason.value,
            interaction.user.display_name,
            self.conditions.value or None
        )
        converted = await check_and_convert_warnings(target.id, interaction.client)
        if converted:
            await check_and_reset_reprimands(target.id, interaction.client)

        await interaction.followup.send(f"✅ Предупреждение выдано пользователю {target.mention}.", ephemeral=True)

class ReprimandModal(discord.ui.Modal, title="📢 Выдача выговора"):
    def __init__(self, user=None):
        super().__init__()
        self.user = user
        self.user_input = discord.ui.TextInput(
            label="Пользователь (или ответьте на сообщение)",
            placeholder="Например: @user или имя",
            required=False
        )
        self.reason = discord.ui.TextInput(
            label="Причина",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.conditions = discord.ui.TextInput(
            label="Условия снятия (необяз.)",
            required=False
        )
        self.add_item(self.user_input)
        self.add_item(self.reason)
        self.add_item(self.conditions)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        target = None
        if self.user_input.value:
            raw = self.user_input.value.strip()
            if raw.startswith('<@') and raw.endswith('>'):
                user_id = int(raw.strip('<@!>'))
                target = interaction.guild.get_member(user_id)
            elif raw.isdigit():
                target = interaction.guild.get_member(int(raw))
            else:
                for member in interaction.guild.members:
                    if member.name.lower() == raw.lower() or member.display_name.lower() == raw.lower():
                        target = member
                        break
                if not target:
                    for member in interaction.guild.members:
                        if member.name.lower().startswith(raw.lower()) or member.display_name.lower().startswith(raw.lower()):
                            target = member
                            break

        if not target:
            target = await get_target_from_reply(interaction)

        if not target:
            await interaction.followup.send(
                "❌ Не удалось определить пользователя. Укажите его в поле или ответьте на сообщение бота с упоминанием.",
                ephemeral=True
            )
            return

        if not check_punishment_permission(interaction.user):
            await interaction.followup.send("❌ У вас нет прав на выдачу наказаний.", ephemeral=True)
            return

        await add_punishment(target.id, interaction.user.id, 'reprimand', self.reason.value, self.conditions.value or None)
        await send_punishment_notification(
            interaction.client,
            target.id,
            'reprimand',
            self.reason.value,
            interaction.user.display_name,
            self.conditions.value or None
        )
        await check_and_reset_reprimands(target.id, interaction.client)

        await interaction.followup.send(f"✅ Выговор выдан пользователю {target.mention}.", ephemeral=True)

class RemovePunishmentModal(discord.ui.Modal, title="Снятие наказания"):
    user_input = discord.ui.TextInput(
        label="Пользователь (или ответьте на сообщение)",
        placeholder="Например: @user или имя",
        required=False
    )
    punishment_type = discord.ui.TextInput(
        label="Тип (warning/reprimand)",
        placeholder="warning или reprimand",
        required=True
    )
    reason = discord.ui.TextInput(label="Причина снятия", style=discord.TextStyle.paragraph, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        target = None
        if self.user_input.value:
            raw = self.user_input.value.strip()
            if raw.startswith('<@') and raw.endswith('>'):
                user_id = int(raw.strip('<@!>'))
                target = interaction.guild.get_member(user_id)
            elif raw.isdigit():
                target = interaction.guild.get_member(int(raw))
            else:
                for member in interaction.guild.members:
                    if member.name.lower() == raw.lower() or member.display_name.lower() == raw.lower():
                        target = member
                        break
                if not target:
                    for member in interaction.guild.members:
                        if member.name.lower().startswith(raw.lower()) or member.display_name.lower().startswith(raw.lower()):
                            target = member
                            break

        if not target:
            target = await get_target_from_reply(interaction)

        if not target:
            await interaction.followup.send(
                "❌ Не удалось определить пользователя. Укажите его в поле или ответьте на сообщение бота с упоминанием.",
                ephemeral=True
            )
            return

        if not check_punishment_permission(interaction.user):
            await interaction.followup.send("❌ У вас нет прав на снятие наказаний.", ephemeral=True)
            return

        ptype = self.punishment_type.value.lower()
        if ptype not in ['warning', 'reprimand']:
            await interaction.followup.send("❌ Неверный тип. Укажите 'warning' или 'reprimand'.", ephemeral=True)
            return

        punishments = await get_active_punishments(target.id, ptype)
        if not punishments:
            await interaction.followup.send(f"❌ У пользователя {target.mention} нет активных наказаний типа {ptype}.", ephemeral=True)
            return

        for p in punishments:
            await remove_punishment(p['id'], interaction.user.id, self.reason.value)

        await interaction.followup.send(f"✅ Все активные {ptype} сняты с пользователя {target.mention}.", ephemeral=True)

# ---------- БОТ ----------
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    await init_db()
    await init_blacklist_db()
    bot.loop.create_task(delete_expired_tickets(bot))
    print(f'Бот {bot.user} готов!')

# ======================== КОМАНДЫ ========================

# ---------- УПРАВЛЕНИЕ РОЛЯМИ ----------
@bot.tree.command(name='setpermission', description='Установить минимальную роль для команды')
@app_commands.describe(command_name='Название команды', role_name='Роль из иерархии (оставьте пустым для доступа всем)')
@app_commands.default_permissions(administrator=True)
async def setpermission(interaction: discord.Interaction, command_name: str, role_name: str = None):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    cmd = bot.tree.get_command(command_name)
    if cmd is None:
        await interaction.response.send_message(f'❌ Команда `{command_name}` не найдена.', ephemeral=True)
        return
    perms = load_permissions()
    if role_name is None:
        if command_name in perms:
            del perms[command_name]
            save_permissions(perms)
            await interaction.response.send_message(f'✅ Доступ к команде `{command_name}` открыт для всех.', ephemeral=True)
        else:
            await interaction.response.send_message(f'ℹ️ Для команды `{command_name}` и так нет ограничений.', ephemeral=True)
        return
    if role_name not in ROLE_HIERARCHY:
        await interaction.response.send_message(f'❌ Роль `{role_name}` не найдена в иерархии.', ephemeral=True)
        return
    perms[command_name] = role_name
    save_permissions(perms)
    embed = discord.Embed(title='✅ Разрешение установлено', description=f'Для команды `{command_name}` требуется роль **{role_name}**', color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='showpermissions', description='Показать все настройки доступа к командам')
async def showpermissions(interaction: discord.Interaction):
    perms = load_permissions()
    if not perms:
        await interaction.response.send_message('📭 Нет настроенных разрешений.', ephemeral=True)
        return
    lines = [f'`{cmd}` → **{role}**' for cmd, role in perms.items()]
    embed = discord.Embed(title='📋 Разрешения команд', description='\n'.join(lines), color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='setrole', description='Настроить роль из иерархии (выберите из списка или введите вручную)')
@app_commands.describe(role_name='Название роли', role_id='ID роли (число)')
@app_commands.default_permissions(administrator=True)
async def setrole(interaction: discord.Interaction, role_name: str = None, role_id: str = None):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    if role_name is None and role_id is None:
        config = load_roles()
        view = RoleSelectView(config, interaction.guild)
        options = []
        for role in interaction.guild.roles:
            if not role.is_default() and role.name in ROLE_HIERARCHY:
                options.append(discord.SelectOption(label=role.name, value=str(role.id), description=f'ID: {role.id}'))
                if len(options) >= 25:
                    break
        if not options:
            await interaction.response.send_message('❌ На сервере нет ролей, соответствующих иерархии.', ephemeral=True)
            return
        view.select.options = options
        await interaction.response.send_message("Выберите роль для сохранения:", view=view, ephemeral=True)
        return
    if role_name is None or role_id is None:
        await interaction.response.send_message('❌ Укажите оба параметра или вызовите команду без параметров.', ephemeral=True)
        return
    if role_name not in ROLE_HIERARCHY:
        await interaction.response.send_message(f'❌ Роль "{role_name}" не найдена в иерархии.', ephemeral=True)
        return
    try:
        role_id_int = int(role_id)
        role = interaction.guild.get_role(role_id_int)
        if role is None:
            await interaction.response.send_message(f'❌ Роль с ID `{role_id}` не найдена.', ephemeral=True)
            return
    except ValueError:
        await interaction.response.send_message('❌ ID должен быть числом.', ephemeral=True)
        return
    config = load_roles()
    config[role_name] = role_id_int
    save_roles(config)
    embed = discord.Embed(title='✅ Роль сохранена', description=f'**{role_name}** → {role.mention} (ID: `{role_id_int}`)', color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await update_roster(interaction.channel)

@bot.tree.command(name='addrole', description='Добавить новую роль в иерархию')
@app_commands.describe(new_role='Название новой роли', position='Выше или ниже', target_role='Существующая роль')
@app_commands.choices(position=[
    app_commands.Choice(name='Выше', value='above'),
    app_commands.Choice(name='Ниже', value='below')
])
@app_commands.default_permissions(administrator=True)
async def addrole(interaction: discord.Interaction, new_role: str, position: app_commands.Choice[str], target_role: str):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    global ROLE_HIERARCHY
    if target_role not in ROLE_HIERARCHY:
        await interaction.response.send_message(f'❌ Роль "{target_role}" не найдена.', ephemeral=True)
        return
    if new_role in ROLE_HIERARCHY:
        await interaction.response.send_message(f'❌ Роль "{new_role}" уже существует.', ephemeral=True)
        return
    index = ROLE_HIERARCHY.index(target_role)
    if position.value == 'above':
        ROLE_HIERARCHY.insert(index, new_role)
    else:
        ROLE_HIERARCHY.insert(index + 1, new_role)
    save_hierarchy(ROLE_HIERARCHY)
    embed = discord.Embed(title='✅ Роль добавлена', description=f'**{new_role}** добавлена **{position.name}** роли **{target_role}**.', color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='removerole', description='Удалить запись о роли (из конфига ID)')
@app_commands.describe(role_name='Название роли')
@app_commands.default_permissions(administrator=True)
async def removerole(interaction: discord.Interaction, role_name: str):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    config = load_roles()
    if role_name not in config:
        await interaction.response.send_message(f'❌ Роль "{role_name}" не найдена в конфиге.', ephemeral=True)
        return
    del config[role_name]
    save_roles(config)
    await interaction.response.send_message(f'✅ ID для роли "{role_name}" удалён.', ephemeral=True)
    await update_roster(interaction.channel)

@bot.tree.command(name='promote_role', description='Поднять роль на одну позицию вверх в иерархии')
@app_commands.describe(role_name='Название роли')
@app_commands.default_permissions(administrator=True)
async def promote_role(interaction: discord.Interaction, role_name: str):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    global ROLE_HIERARCHY
    if role_name not in ROLE_HIERARCHY:
        await interaction.response.send_message(f'❌ Роль "{role_name}" не найдена.', ephemeral=True)
        return
    index = ROLE_HIERARCHY.index(role_name)
    if index == 0:
        await interaction.response.send_message(f'❌ Роль "{role_name}" уже на вершине.', ephemeral=True)
        return
    ROLE_HIERARCHY[index], ROLE_HIERARCHY[index - 1] = ROLE_HIERARCHY[index - 1], ROLE_HIERARCHY[index]
    save_hierarchy(ROLE_HIERARCHY)
    embed = discord.Embed(title='✅ Роль повышена', description=f'Роль **{role_name}** поднята вверх.', color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='demote_role', description='Опустить роль на одну позицию вниз в иерархии')
@app_commands.describe(role_name='Название роли')
@app_commands.default_permissions(administrator=True)
async def demote_role(interaction: discord.Interaction, role_name: str):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    global ROLE_HIERARCHY
    if role_name not in ROLE_HIERARCHY:
        await interaction.response.send_message(f'❌ Роль "{role_name}" не найдена.', ephemeral=True)
        return
    index = ROLE_HIERARCHY.index(role_name)
    if index == len(ROLE_HIERARCHY) - 1:
        await interaction.response.send_message(f'❌ Роль "{role_name}" уже внизу.', ephemeral=True)
        return
    ROLE_HIERARCHY[index], ROLE_HIERARCHY[index + 1] = ROLE_HIERARCHY[index + 1], ROLE_HIERARCHY[index]
    save_hierarchy(ROLE_HIERARCHY)
    embed = discord.Embed(title='✅ Роль понижена', description=f'Роль **{role_name}** опущена вниз.', color=discord.Color.orange())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='showroles', description='Показать все сохранённые роли с уровнями')
async def showroles(interaction: discord.Interaction):
    config = load_roles()
    if not config:
        await interaction.response.send_message('📭 Список ролей пуст.', ephemeral=True)
        return
    lines = []
    for level, name in enumerate(ROLE_HIERARCHY):
        if name in config:
            role_id = config[name]
            role = interaction.guild.get_role(role_id)
            mention = role.mention if role else f'❌ ID {role_id} не найден'
            lines.append(f'**{level+1}.** {name} → {mention}')
        else:
            lines.append(f'**{level+1}.** {name} → ❌ не задана')
    embed = discord.Embed(title='📋 Иерархия ролей', description='\n'.join(lines), color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='myrole', description='Показать вашу текущую роль в иерархии')
async def myrole(interaction: discord.Interaction):
    config = load_roles()
    level, role_name = get_user_role_level(interaction.user, config)
    if role_name is None:
        await interaction.response.send_message('❌ У вас нет ни одной роли из иерархии.', ephemeral=True)
    else:
        role_id = config[role_name]
        role = interaction.guild.get_role(role_id)
        mention = role.mention if role else f'ID {role_id}'
        await interaction.response.send_message(f'Ваша роль: **{role_name}** ({mention})\nУровень: {level+1} из {len(ROLE_HIERARCHY)}', ephemeral=True)

# ---------- ПОВЫШЕНИЕ/ПОНИЖЕНИЕ УЧАСТНИКОВ ----------
@bot.tree.command(name='promote', description='Повысить участника до следующей по иерархии роли')
@app_commands.describe(user='Участник, которого нужно повысить')
async def promote(interaction: discord.Interaction, user: discord.Member):
    config = load_roles()
    actor_level, actor_role = get_user_role_level(interaction.user, config)
    if actor_role is None:
        await interaction.response.send_message('❌ У вас нет роли из иерархии.', ephemeral=True)
        return
    target_level, target_role = get_user_role_level(user, config)
    if target_role is None:
        await interaction.response.send_message(f'❌ У {user.mention} нет роли из иерархии.', ephemeral=True)
        return
    if not (actor_level < target_level):
        await interaction.response.send_message(f'❌ Ваша роль ({actor_role}) не выше роли {user.mention}.', ephemeral=True)
        return
    if target_level == 0:
        await interaction.response.send_message(f'❌ {user.mention} уже имеет высшую роль.', ephemeral=True)
        return
    new_role_name = ROLE_HIERARCHY[target_level - 1]
    if new_role_name not in config:
        await interaction.response.send_message(f'❌ Роль "{new_role_name}" не привязана к ID.', ephemeral=True)
        return
    new_role = interaction.guild.get_role(config[new_role_name])
    if new_role is None:
        await interaction.response.send_message(f'❌ Роль с ID {config[new_role_name]} не найдена.', ephemeral=True)
        return
    if ROLE_HIERARCHY.index(new_role_name) <= actor_level:
        await interaction.response.send_message(f'❌ Вы не можете дать роль выше или равную вашей.', ephemeral=True)
        return
    old_role = interaction.guild.get_role(config[target_role])
    if old_role:
        await user.remove_roles(old_role)
    await user.add_roles(new_role)
    embed = discord.Embed(title='✅ Повышение выполнено', description=f'{user.mention} повышен с **{target_role}** до **{new_role_name}**.', color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await update_roster(interaction.channel)

@bot.tree.command(name='demote', description='Понизить участника до предыдущей по иерархии роли')
@app_commands.describe(user='Участник, которого нужно понизить')
async def demote(interaction: discord.Interaction, user: discord.Member):
    config = load_roles()
    actor_level, actor_role = get_user_role_level(interaction.user, config)
    if actor_role is None:
        await interaction.response.send_message('❌ У вас нет роли из иерархии.', ephemeral=True)
        return
    target_level, target_role = get_user_role_level(user, config)
    if target_role is None:
        await interaction.response.send_message(f'❌ У {user.mention} нет роли из иерархии.', ephemeral=True)
        return
    if not (actor_level < target_level):
        await interaction.response.send_message(f'❌ Ваша роль ({actor_role}) не выше роли {user.mention}.', ephemeral=True)
        return
    if target_level == len(ROLE_HIERARCHY) - 1:
        await interaction.response.send_message(f'❌ {user.mention} уже имеет самую низкую роль.', ephemeral=True)
        return
    new_role_name = ROLE_HIERARCHY[target_level + 1]
    if new_role_name not in config:
        await interaction.response.send_message(f'❌ Роль "{new_role_name}" не привязана к ID.', ephemeral=True)
        return
    new_role = interaction.guild.get_role(config[new_role_name])
    if new_role is None:
        await interaction.response.send_message(f'❌ Роль с ID {config[new_role_name]} не найдена.', ephemeral=True)
        return
    if ROLE_HIERARCHY.index(new_role_name) <= actor_level:
        await interaction.response.send_message(f'❌ Вы не можете дать роль выше или равную вашей.', ephemeral=True)
        return
    old_role = interaction.guild.get_role(config[target_role])
    if old_role:
        await user.remove_roles(old_role)
    await user.add_roles(new_role)
    embed = discord.Embed(title='✅ Понижение выполнено', description=f'{user.mention} понижен с **{target_role}** до **{new_role_name}**.', color=discord.Color.orange())
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await update_roster(interaction.channel)

# ---------- ТАБЛИЦА РОЛЕЙ ----------
@bot.tree.command(name='roster', description='Показать таблицу ролей участников (автообновление)')
async def roster(interaction: discord.Interaction):
    config = load_roles()
    users = []
    for member in interaction.guild.members:
        level, role_name = get_user_role_level(member, config)
        if role_name:
            users.append((member, level, role_name))
    users.sort(key=lambda x: x[1] if x[1] is not None else 999)

    embed = discord.Embed(title="📋 Таблица ролей участников", color=discord.Color.blue())
    if not users:
        embed.description = "Нет участников с ролями из иерархии."
    else:
        lines = []
        for member, level, role_name in users[:30]:
            lines.append(f"{member.mention} — **{role_name}**")
        embed.description = "\n".join(lines)
        if len(users) > 30:
            embed.set_footer(text=f"Показано 30 из {len(users)} участников")
        else:
            embed.set_footer(text=f"Всего: {len(users)} участников")

    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    roster_messages[interaction.channel.id] = msg.id

@bot.tree.command(name='update_roster', description='Принудительно обновить таблицу ролей в этом канале')
async def update_roster_command(interaction: discord.Interaction):
    channel = interaction.channel
    if channel.id in roster_messages:
        await update_roster(channel)
        await interaction.response.send_message("✅ Таблица ролей обновлена.", ephemeral=True)
    else:
        config = load_roles()
        users = []
        for member in interaction.guild.members:
            level, role_name = get_user_role_level(member, config)
            if role_name:
                users.append((member, level, role_name))
        users.sort(key=lambda x: x[1] if x[1] is not None else 999)

        embed = discord.Embed(title="📋 Таблица ролей участников", color=discord.Color.blue())
        if not users:
            embed.description = "Нет участников с ролями из иерархии."
        else:
            lines = []
            for member, level, role_name in users[:30]:
                lines.append(f"{member.mention} — **{role_name}**")
            embed.description = "\n".join(lines)
            if len(users) > 30:
                embed.set_footer(text=f"Показано 30 из {len(users)} участников")
            else:
                embed.set_footer(text=f"Всего: {len(users)} участников")

        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        roster_messages[interaction.channel.id] = msg.id
        await interaction.followup.send("📊 Таблица создана и сохранена для автообновления.", ephemeral=True)

@bot.tree.command(name='обновить_таблицу', description='Принудительно обновить таблицу ролей в этом канале')
async def update_roster_command_ru(interaction: discord.Interaction):
    channel = interaction.channel
    if channel.id in roster_messages:
        await update_roster(channel)
        await interaction.response.send_message("✅ Таблица ролей обновлена.", ephemeral=True)
    else:
        config = load_roles()
        users = []
        for member in interaction.guild.members:
            level, role_name = get_user_role_level(member, config)
            if role_name:
                users.append((member, level, role_name))
        users.sort(key=lambda x: x[1] if x[1] is not None else 999)

        embed = discord.Embed(title="📋 Таблица ролей участников", color=discord.Color.blue())
        if not users:
            embed.description = "Нет участников с ролями из иерархии."
        else:
            lines = []
            for member, level, role_name in users[:30]:
                lines.append(f"{member.mention} — **{role_name}**")
            embed.description = "\n".join(lines)
            if len(users) > 30:
                embed.set_footer(text=f"Показано 30 из {len(users)} участников")
            else:
                embed.set_footer(text=f"Всего: {len(users)} участников")

        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        roster_messages[interaction.channel.id] = msg.id
        await interaction.followup.send("📊 Таблица создана и сохранена для автообновления.", ephemeral=True)

# ---------- КОМАНДЫ ТИКЕТОВ ----------
@bot.tree.command(name='жалоба', description='Подать жалобу на игрока')
async def report(interaction: discord.Interaction):
    await interaction.response.send_modal(ReportModal())

@bot.tree.command(name='ticket_setchannel', description='Установить канал для уведомлений о новых тикетах')
@app_commands.describe(channel='Канал, куда будут приходить уведомления')
@app_commands.default_permissions(administrator=True)
async def ticket_setchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    TICKET_CONFIG["admin_channel_id"] = channel.id
    save_ticket_config(TICKET_CONFIG)
    await interaction.response.send_message(f'✅ Канал для уведомлений установлен: {channel.mention}', ephemeral=True)

@bot.tree.command(name='ticket_setroles', description='Установить роли, которые могут обрабатывать тикеты')
@app_commands.describe(roles='Список ролей через запятую (например: "Глава, Зам главы")')
@app_commands.default_permissions(administrator=True)
async def ticket_setroles(interaction: discord.Interaction, roles: str):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    role_list = [r.strip() for r in roles.split(',') if r.strip()]
    invalid = [r for r in role_list if r not in ROLE_HIERARCHY]
    if invalid:
        await interaction.response.send_message(f'❌ Роли не найдены: {", ".join(invalid)}', ephemeral=True)
        return
    TICKET_CONFIG["allowed_roles"] = role_list
    save_ticket_config(TICKET_CONFIG)
    await interaction.response.send_message(f'✅ Роли для тикетов: {", ".join(role_list)}', ephemeral=True)

@bot.tree.command(name='ticket_listroles', description='Показать список ролей, обрабатывающих тикеты')
async def ticket_listroles(interaction: discord.Interaction):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    roles = TICKET_CONFIG.get("allowed_roles", [])
    if not roles:
        await interaction.response.send_message('📭 Список ролей пуст.', ephemeral=True)
        return
    lines = [f"{i+1}. **{r}**" for i, r in enumerate(roles)]
    embed = discord.Embed(title="📋 Роли, обрабатывающие тикеты", description="\n".join(lines), color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='ticket_removerole', description='Удалить роль из списка разрешённых для тикетов')
@app_commands.describe(role='Название роли')
async def ticket_removerole(interaction: discord.Interaction, role: str):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    roles = TICKET_CONFIG.get("allowed_roles", [])
    if role not in roles:
        await interaction.response.send_message(f'❌ Роль **{role}** не найдена.', ephemeral=True)
        return
    roles.remove(role)
    TICKET_CONFIG["allowed_roles"] = roles
    save_ticket_config(TICKET_CONFIG)
    await interaction.response.send_message(f'✅ Роль **{role}** удалена.', ephemeral=True)

@bot.tree.command(name='ticket_clearroles', description='Очистить список ролей для тикетов')
async def ticket_clearroles(interaction: discord.Interaction):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    TICKET_CONFIG["allowed_roles"] = []
    save_ticket_config(TICKET_CONFIG)
    await interaction.response.send_message('✅ Список ролей для тикетов очищен.', ephemeral=True)

@bot.tree.command(name='ticket_removechannel', description='Убрать канал для уведомлений')
async def ticket_removechannel(interaction: discord.Interaction):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    if TICKET_CONFIG.get("admin_channel_id") is None:
        await interaction.response.send_message('ℹ️ Канал и так не задан.', ephemeral=True)
        return
    TICKET_CONFIG["admin_channel_id"] = None
    save_ticket_config(TICKET_CONFIG)
    await interaction.response.send_message('✅ Канал для уведомлений сброшен.', ephemeral=True)

@bot.tree.command(name='добавить', description='Добавить пользователя в текущий канал тикета')
@app_commands.describe(user='Пользователь для добавления')
async def adduser(interaction: discord.Interaction, user: discord.Member):
    if not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message("❌ Эта команда работает только в канале тикета.", ephemeral=True)
    ticket = await get_ticket_by_channel(interaction.channel.id)
    if not ticket:
        return await interaction.response.send_message("❌ Это не тикет-канал.", ephemeral=True)
    if ticket["status"] != "reviewing":
        return await interaction.response.send_message("❌ Тикет не в статусе 'в рассмотрении'.", ephemeral=True)
    if not check_ticket_permission(interaction.user):
        return await interaction.response.send_message("❌ У вас нет прав на обработку тикетов.", ephemeral=True)
    try:
        await interaction.channel.set_permissions(user, view_channel=True, send_messages=True, read_messages=True)
        await interaction.response.send_message(f"✅ {user.mention} добавлен в канал.", ephemeral=False)
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

@bot.tree.command(name='отказ', description='Закрыть текущий тикет с отказом')
async def closereject(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message("❌ Эта команда работает только в канале тикета.", ephemeral=True)
    ticket = await get_ticket_by_channel(interaction.channel.id)
    if not ticket:
        return await interaction.response.send_message("❌ Это не тикет-канал.", ephemeral=True)
    if ticket["status"] != "reviewing":
        return await interaction.response.send_message("❌ Тикет не в статусе 'в рассмотрении'.", ephemeral=True)
    if not check_ticket_permission(interaction.user):
        return await interaction.response.send_message("❌ У вас нет прав на обработку тикетов.", ephemeral=True)
    modal = RejectModal(interaction.channel.id)
    await interaction.response.send_modal(modal)

@bot.tree.command(name='одобрить', description='Закрыть текущий тикет с одобрением и наказанием')
async def closeapprove(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel):
        return await interaction.response.send_message("❌ Эта команда работает только в канале тикета.", ephemeral=True)
    ticket = await get_ticket_by_channel(interaction.channel.id)
    if not ticket:
        return await interaction.response.send_message("❌ Это не тикет-канал.", ephemeral=True)
    if ticket["status"] != "reviewing":
        return await interaction.response.send_message("❌ Тикет не в статусе 'в рассмотрении'.", ephemeral=True)
    if not check_ticket_permission(interaction.user):
        return await interaction.response.send_message("❌ У вас нет прав на обработку тикетов.", ephemeral=True)
    modal = ApproveModal(interaction.channel.id)
    await interaction.response.send_modal(modal)

# ---------- КОМАНДЫ НАКАЗАНИЙ (с подстановкой статистики) ----------
@bot.tree.command(name='предупреждение', description='Выдать предупреждение пользователю')
async def warning(interaction: discord.Interaction):
    target = await get_target_from_reply(interaction)
    modal = WarningModal(user=target)
    if target:
        warnings = await get_active_punishments(target.id, 'warning')
        reprimands = await get_active_punishments(target.id, 'reprimand')
        modal.user_input.default = target.mention
        modal.user_input.placeholder = f"Наказания: предупреждений - {len(warnings)}, выговоров - {len(reprimands)}"
    await interaction.response.send_modal(modal)

@bot.tree.command(name='выговор', description='Выдать выговор пользователю')
async def reprimand(interaction: discord.Interaction):
    target = await get_target_from_reply(interaction)
    modal = ReprimandModal(user=target)
    if target:
        warnings = await get_active_punishments(target.id, 'warning')
        reprimands = await get_active_punishments(target.id, 'reprimand')
        modal.user_input.default = target.mention
        modal.user_input.placeholder = f"Наказания: предупреждений - {len(warnings)}, выговоров - {len(reprimands)}"
    await interaction.response.send_modal(modal)

@bot.tree.command(name='снять', description='Снять активные наказания (предупреждения или выговоры)')
async def remove_punishment(interaction: discord.Interaction):
    target = await get_target_from_reply(interaction)
    modal = RemovePunishmentModal()
    if target:
        modal.user_input.default = target.mention
        warnings = await get_active_punishments(target.id, 'warning')
        reprimands = await get_active_punishments(target.id, 'reprimand')
        modal.user_input.placeholder = f"Наказания: предупреждений - {len(warnings)}, выговоров - {len(reprimands)}"
    await interaction.response.send_modal(modal)

@bot.tree.command(name='setkanalwarning', description='Установить канал для уведомлений о наказаниях')
@app_commands.describe(channel='Канал для уведомлений')
@app_commands.default_permissions(administrator=True)
async def set_punishment_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    PUNISHMENT_CONFIG["channel_id"] = channel.id
    save_punishment_config(PUNISHMENT_CONFIG)
    await interaction.response.send_message(f'✅ Канал для уведомлений о наказаниях: {channel.mention}', ephemeral=True)

@bot.tree.command(name='setrangwarning', description='Установить роли, которые могут выдавать наказания')
@app_commands.describe(roles='Список ролей через запятую (например: "Глава, Зам главы")')
@app_commands.default_permissions(administrator=True)
async def set_punishment_roles(interaction: discord.Interaction, roles: str):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    role_list = [r.strip() for r in roles.split(',') if r.strip()]
    invalid = [r for r in role_list if r not in ROLE_HIERARCHY]
    if invalid:
        await interaction.response.send_message(f'❌ Роли не найдены: {", ".join(invalid)}', ephemeral=True)
        return
    PUNISHMENT_CONFIG["allowed_roles"] = role_list
    save_punishment_config(PUNISHMENT_CONFIG)
    await interaction.response.send_message(f'✅ Роли для выдачи наказаний: {", ".join(role_list)}', ephemeral=True)

@bot.tree.command(name='showpunishmentsettings', description='Показать текущие настройки наказаний')
async def show_punishment_settings(interaction: discord.Interaction):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    channel_id = PUNISHMENT_CONFIG.get('channel_id')
    roles = PUNISHMENT_CONFIG.get('allowed_roles', [])
    embed = discord.Embed(title="⚙️ Настройки наказаний", color=discord.Color.blue())
    embed.add_field(name="Канал уведомлений", value=f"<#{channel_id}>" if channel_id else "Не задан", inline=False)
    embed.add_field(name="Роли, выдающие наказания", value=", ".join(roles) if roles else "Не заданы", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------- ПРИМЕР КОМАНДЫ С РАЗРЕШЕНИЕМ ----------
@bot.tree.command(name='kick', description='Выгнать участника')
@require_permission('kick')
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = "Не указана"):
    await user.kick(reason=reason)
    await interaction.response.send_message(f'Пользователь {user.mention} выгнан. Причина: {reason}')
# ===================================================================
#   СИСТЕМА ЧС (ЧЁРНЫЙ СПИСОК) – ОТДЕЛЬНЫЙ БЛОК
# ===================================================================

# ---------- ДОПОЛНИТЕЛЬНЫЕ ИМПОРТЫ (если ещё не добавлены) ----------
# Убедитесь, что у вас есть: import asyncio, from datetime import datetime, timedelta
# Они уже должны быть, но на всякий случай проверьте.

# ---------- КОНФИГУРАЦИОННЫЙ ФАЙЛ ДЛЯ ЧС ----------
BLACKLIST_CONFIG_FILE = 'blacklist_config.json'

def load_blacklist_config():
    if not os.path.exists(BLACKLIST_CONFIG_FILE):
        default = {
            "channel_id": None,
            "default_conditions": ""  # условия по умолчанию
        }
        save_blacklist_config(default)
        return default
    with open(BLACKLIST_CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_blacklist_config(data):
    with open(BLACKLIST_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

BLACKLIST_CONFIG = load_blacklist_config()

# ---------- ДОБАВЛЕНИЕ ТАБЛИЦЫ ЧС В БАЗУ ДАННЫХ ----------
# Эту функцию нужно вызвать в init_db (дописать в существующую функцию)
# Мы добавим отдельную функцию для миграции, которую вызовем в on_ready.

async def init_blacklist_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                target_name TEXT,
                reason TEXT,
                conditions TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                removed_at TIMESTAMP,
                removed_by INTEGER,
                removed_reason TEXT
            )
        ''')
        # Проверяем наличие колонок (если таблица уже была без нужных полей)
        cursor = await db.execute("PRAGMA table_info(blacklist)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        if 'target_name' not in column_names:
            await db.execute('ALTER TABLE blacklist ADD COLUMN target_name TEXT')
        if 'conditions' not in column_names:
            await db.execute('ALTER TABLE blacklist ADD COLUMN conditions TEXT')
        await db.commit()

# ---------- ФУНКЦИИ ДЛЯ РАБОТЫ С ЧС ----------
async def add_blacklist(user_id, target_name, reason, conditions):
    """Добавляет запись в ЧС."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO blacklist (user_id, target_name, reason, conditions) VALUES (?, ?, ?, ?)",
            (user_id, target_name, reason, conditions)
        )
        await db.commit()
        return cursor.lastrowid

async def get_active_blacklist(user_id=None, target_name=None):
    """Возвращает активные записи ЧС по ID пользователя или имени."""
    async with aiosqlite.connect(DB_PATH) as db:
        if user_id:
            cursor = await db.execute(
                "SELECT * FROM blacklist WHERE user_id = ? AND status = 'active'",
                (user_id,)
            )
        elif target_name:
            cursor = await db.execute(
                "SELECT * FROM blacklist WHERE target_name LIKE ? AND status = 'active'",
                (f'%{target_name}%',)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM blacklist WHERE status = 'active' ORDER BY created_at DESC"
            )
        rows = await cursor.fetchall()
        columns = ["id", "user_id", "target_name", "reason", "conditions", "status", "created_at", "removed_at", "removed_by", "removed_reason"]
        return [dict(zip(columns, row)) for row in rows]

async def remove_blacklist(entry_id, removed_by, removed_reason):
    """Снимает запись ЧС (устанавливает статус removed)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE blacklist SET status = 'removed', removed_at = CURRENT_TIMESTAMP, removed_by = ?, removed_reason = ? WHERE id = ?",
            (removed_by, removed_reason, entry_id)
        )
        await db.commit()

async def get_blacklist_by_id(entry_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM blacklist WHERE id = ?", (entry_id,))
        row = await cursor.fetchone()
        if row:
            columns = ["id", "user_id", "target_name", "reason", "conditions", "status", "created_at", "removed_at", "removed_by", "removed_reason"]
            return dict(zip(columns, row))
    return None

# ---------- ФУНКЦИЯ ОТПРАВКИ УВЕДОМЛЕНИЙ В КАНАЛ ----------
async def send_blacklist_notification(bot, entry, is_add=True, removed_reason=None):
    """Отправляет уведомление в канал ЧС."""
    channel_id = BLACKLIST_CONFIG.get('channel_id')
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if not channel:
        return

    if is_add:
        embed = discord.Embed(
            title="🚫 Выдача ЧС",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Пользователь", value=entry['target_name'] if entry['user_id'] == 0 else f"<@{entry['user_id']}>", inline=True)
        embed.add_field(name="Причина", value=entry['reason'], inline=False)
        if entry['conditions']:
            embed.add_field(name="Условия снятия", value=entry['conditions'], inline=False)
        embed.set_footer(text=f"ID записи: {entry['id']}")
    else:
        embed = discord.Embed(
            title="✅ Снятие ЧС",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Пользователь", value=entry['target_name'] if entry['user_id'] == 0 else f"<@{entry['user_id']}>", inline=True)
        embed.add_field(name="Причина снятия", value=removed_reason, inline=False)
        embed.set_footer(text=f"ID записи: {entry['id']}")

    await channel.send(embed=embed)

# ---------- МОДАЛЬНЫЕ ОКНА ДЛЯ ЧС ----------
class BlacklistModal(discord.ui.Modal, title="🚫 Выдача ЧС"):
    def __init__(self, user=None):
        super().__init__()
        self.user = user
        self.user_input = discord.ui.TextInput(
            label="Пользователь (или ответьте на сообщение)",
            placeholder="Например: @user или имя",
            required=False
        )
        self.reason = discord.ui.TextInput(
            label="Причина",
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.conditions = discord.ui.TextInput(
            label="Условия снятия (необяз.)",
            required=False
        )
        self.add_item(self.user_input)
        self.add_item(self.reason)
        self.add_item(self.conditions)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Определяем пользователя
        target = None
        target_name = ""
        if self.user_input.value:
            raw = self.user_input.value.strip()
            if raw.startswith('<@') and raw.endswith('>'):
                user_id = int(raw.strip('<@!>'))
                target = interaction.guild.get_member(user_id)
            elif raw.isdigit():
                target = interaction.guild.get_member(int(raw))
            else:
                # Ищем по имени
                for member in interaction.guild.members:
                    if member.name.lower() == raw.lower() or member.display_name.lower() == raw.lower():
                        target = member
                        break
                if not target:
                    target_name = raw

        if not target and not target_name:
            target = await get_target_from_reply(interaction)  # эта функция уже должна быть определена

        if not target and not target_name:
            await interaction.followup.send(
                "❌ Не удалось определить пользователя. Укажите его в поле или ответьте на сообщение бота с упоминанием.",
                ephemeral=True
            )
            return

        # Проверка прав (используем check_management_permissions или свою)
        if not check_management_permissions(interaction):
            await interaction.followup.send("❌ У вас нет прав на выдачу ЧС.", ephemeral=True)
            return

        # Условия: если поле пустое, берём из конфига
        conditions = self.conditions.value
        if not conditions:
            conditions = BLACKLIST_CONFIG.get('default_conditions', '')

        # Добавляем запись
        if target:
            user_id = target.id
            name = target.display_name
        else:
            user_id = 0
            name = target_name

        entry_id = await add_blacklist(user_id, name, self.reason.value, conditions)

        # Отправляем уведомление в канал
        entry = await get_blacklist_by_id(entry_id)
        if entry:
            await send_blacklist_notification(interaction.client, entry, is_add=True)

        await interaction.followup.send(f"✅ ЧС выдана {name}.", ephemeral=True)

class RemoveBlacklistModal(discord.ui.Modal, title="Снятие ЧС"):
    user_input = discord.ui.TextInput(
        label="Пользователь (или ответьте на сообщение)",
        placeholder="Например: @user или имя",
        required=False
    )
    reason = discord.ui.TextInput(label="Причина снятия", style=discord.TextStyle.paragraph, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Поиск пользователя аналогично
        target = None
        target_name = ""
        if self.user_input.value:
            raw = self.user_input.value.strip()
            if raw.startswith('<@') and raw.endswith('>'):
                user_id = int(raw.strip('<@!>'))
                target = interaction.guild.get_member(user_id)
            elif raw.isdigit():
                target = interaction.guild.get_member(int(raw))
            else:
                for member in interaction.guild.members:
                    if member.name.lower() == raw.lower() or member.display_name.lower() == raw.lower():
                        target = member
                        break
                if not target:
                    target_name = raw

        if not target and not target_name:
            target = await get_target_from_reply(interaction)

        if not target and not target_name:
            await interaction.followup.send(
                "❌ Не удалось определить пользователя.",
                ephemeral=True
            )
            return

        if not check_management_permissions(interaction):
            await interaction.followup.send("❌ У вас нет прав на снятие ЧС.", ephemeral=True)
            return

        # Ищем активные записи для этого пользователя
        if target:
            entries = await get_active_blacklist(user_id=target.id)
            display = target.display_name
        else:
            entries = await get_active_blacklist(target_name=target_name)
            display = target_name

        if not entries:
            await interaction.followup.send(f"❌ У {display} нет активных ЧС.", ephemeral=True)
            return

        # Снимаем все записи
        for entry in entries:
            await remove_blacklist(entry['id'], interaction.user.id, self.reason.value)
            # Отправляем уведомление о снятии
            await send_blacklist_notification(interaction.client, entry, is_add=False, removed_reason=self.reason.value)

        await interaction.followup.send(f"✅ ЧС снята с {display}.", ephemeral=True)

# ---------- КОМАНДЫ ЧС ----------
@bot.tree.command(name='чс', description='Выдать ЧС пользователю')
async def blacklist_add(interaction: discord.Interaction):
    target = await get_target_from_reply(interaction)
    modal = BlacklistModal(user=target)
    if target:
        modal.user_input.default = target.mention
    await interaction.response.send_modal(modal)

@bot.tree.command(name='редактор_условий', description='Задать или удалить условия по умолчанию для ЧС')
@app_commands.describe(action='Действие: set - задать, remove - удалить', conditions='Текст условий (только для set)')
@app_commands.default_permissions(administrator=True)
async def edit_default_conditions(interaction: discord.Interaction, action: str, conditions: str = None):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    action = action.lower()
    if action == 'set':
        if not conditions:
            await interaction.response.send_message('❌ Укажите текст условий для установки.', ephemeral=True)
            return
        BLACKLIST_CONFIG['default_conditions'] = conditions
        save_blacklist_config(BLACKLIST_CONFIG)
        await interaction.response.send_message(f'✅ Условия по умолчанию установлены:\n{conditions}', ephemeral=True)
    elif action == 'remove':
        BLACKLIST_CONFIG['default_conditions'] = ''
        save_blacklist_config(BLACKLIST_CONFIG)
        await interaction.response.send_message('✅ Условия по умолчанию удалены.', ephemeral=True)
    else:
        await interaction.response.send_message('❌ Неверное действие. Используйте "set" или "remove".', ephemeral=True)

@bot.tree.command(name='поиск_чс', description='Поиск ЧС по нику или ID')
@app_commands.describe(query='Ник или ID пользователя')
async def search_blacklist(interaction: discord.Interaction, query: str):
    # Пытаемся найти по ID
    if query.isdigit():
        entries = await get_active_blacklist(user_id=int(query))
    else:
        entries = await get_active_blacklist(target_name=query)

    if not entries:
        await interaction.response.send_message(f'❌ Не найдено активных ЧС для "{query}".', ephemeral=True)
        return

    embed = discord.Embed(title=f"🔍 Результаты поиска для '{query}'", color=discord.Color.blue())
    for entry in entries[:5]:  # показываем первые 5
        name = entry['target_name'] if entry['user_id'] == 0 else f"<@{entry['user_id']}>"
        embed.add_field(
            name=f"ID {entry['id']} – {name}",
            value=f"**Причина:** {entry['reason']}\n**Условия:** {entry['conditions'] or 'Нет'}\n**Дата:** {entry['created_at']}",
            inline=False
        )
    if len(entries) > 5:
        embed.set_footer(text=f"Показано 5 из {len(entries)} записей")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='список_чс', description='Показать список всех активных ЧС')
async def list_blacklist(interaction: discord.Interaction):
    entries = await get_active_blacklist()
    if not entries:
        await interaction.response.send_message('📭 Список ЧС пуст.', ephemeral=True)
        return

    embed = discord.Embed(title="📋 Список активных ЧС", color=discord.Color.red())
    for entry in entries[:20]:
        name = entry['target_name'] if entry['user_id'] == 0 else f"<@{entry['user_id']}>"
        embed.add_field(
            name=f"ID {entry['id']} – {name}",
            value=f"**Причина:** {entry['reason']}\n**Условия:** {entry['conditions'] or 'Нет'}",
            inline=False
        )
    if len(entries) > 20:
        embed.set_footer(text=f"Показано 20 из {len(entries)} записей")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='снять_чс', description='Снять ЧС с пользователя')
async def remove_blacklist_cmd(interaction: discord.Interaction):
    target = await get_target_from_reply(interaction)
    modal = RemoveBlacklistModal()
    if target:
        modal.user_input.default = target.mention
    await interaction.response.send_modal(modal)

@bot.tree.command(name='canellchs', description='Установить канал для уведомлений о ЧС')
@app_commands.describe(channel='Канал для уведомлений')
@app_commands.default_permissions(administrator=True)
async def set_blacklist_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return
    BLACKLIST_CONFIG['channel_id'] = channel.id
    save_blacklist_config(BLACKLIST_CONFIG)
    await interaction.response.send_message(f'✅ Канал для уведомлений о ЧС: {channel.mention}', ephemeral=True)

# ---------- ОБРАБОТЧИК СООБЩЕНИЙ ДЛЯ ОТВЕТОВ С ПИНГОМ ----------
@bot.event
async def on_message(message):
    # Игнорируем сообщения от бота (чтобы не зациклиться)
    if message.author == bot.user:
        return

    # Проверяем, является ли сообщение ответом на сообщение бота
    if message.reference:
        try:
            referenced = await message.channel.fetch_message(message.reference.message_id)
        except:
            return
        if referenced.author == bot.user:
            # Проверяем, есть ли упоминания в ответе
            if message.mentions:
                # Это уведомление о ЧС? Проверяем, содержит ли embed канала ЧС
                # Мы просто проверим, что это сообщение от бота в канале ЧС
                channel_id = BLACKLIST_CONFIG.get('channel_id')
                if referenced.channel.id == channel_id:
                    # Отправляем ЛС упомянутому пользователю
                    target = message.mentions[0]
                    # Находим запись ЧС по ID из футера (мы сохраняем ID в футере)
                    # Попробуем извлечь ID из embed.footer
                    if referenced.embeds:
                        embed = referenced.embeds[0]
                        if embed.footer and embed.footer.text:
                            # предположим, что футер содержит "ID записи: 123"
                            import re
                            match = re.search(r'ID записи:\s*(\d+)', embed.footer.text)
                            if match:
                                entry_id = int(match.group(1))
                                entry = await get_blacklist_by_id(entry_id)
                                if entry:
                                    # Отправляем ЛС
                                    dm_embed = discord.Embed(
                                        title="📨 Уведомление о ЧС",
                                        color=discord.Color.red() if entry['status'] == 'active' else discord.Color.green(),
                                        timestamp=datetime.now()
                                    )
                                    if entry['status'] == 'active':
                                        dm_embed.description = f"Вам была выдана ЧС.\n**Причина:** {entry['reason']}\n**Условия снятия:** {entry['conditions'] or 'Нет'}"
                                    else:
                                        dm_embed.description = f"С вас снята ЧС.\n**Причина снятия:** {entry['removed_reason']}"
                                    await target.send(embed=dm_embed)
                                    # Дадим знать в канале, что ЛС отправлено
                                    await message.channel.send(f"✅ Уведомление отправлено {target.mention} в ЛС.", delete_after=10)
        return

    # Обработка других команд (если они есть)
    await bot.process_commands(message)

# ===================================================================
#   КОМАНДА /написать – ОТПРАВКА СООБЩЕНИЯ В КАНАЛ
# ===================================================================

# ---------- АВТОДОПОЛНЕНИЕ ДЛЯ КАНАЛОВ ----------
async def channel_autocomplete(interaction: discord.Interaction, current: str):
    """
    Возвращает список текстовых каналов сервера, соответствующих вводу.
    """
    if not interaction.guild:
        return []
    # Получаем все текстовые каналы, к которым у бота есть доступ
    channels = [ch for ch in interaction.guild.text_channels if ch.permissions_for(interaction.guild.me).send_messages]
    # Фильтруем по введённому тексту (без учёта регистра)
    if current:
        channels = [ch for ch in channels if current.lower() in ch.name.lower()]
    # Возвращаем не более 25 вариантов (ограничение Discord)
    return [
        app_commands.Choice(name=f"#{ch.name}", value=str(ch.id))
        for ch in channels[:25]
    ]

# ---------- КОМАНДА /написать ----------
@bot.tree.command(name='написать', description='Отправить текст в указанный канал')
@app_commands.describe(
    текст='Текст сообщения',
    канал='Канал для отправки (выберите из списка)'
)
@app_commands.autocomplete(канал=channel_autocomplete)
@require_permission('написать')  # используем существующую систему разрешений
async def send_to_channel(interaction: discord.Interaction, текст: str, канал: str):
    """
    Отправляет текст в выбранный канал.
    Параметр канал – строковый ID канала, полученный из автодополнения.
    """
    # Проверяем, что канал существует и является текстовым
    try:
        channel_id = int(канал)
        target_channel = interaction.guild.get_channel(channel_id)
    except (ValueError, TypeError):
        await interaction.response.send_message('❌ Неверный идентификатор канала.', ephemeral=True)
        return

    if not target_channel or not isinstance(target_channel, discord.TextChannel):
        await interaction.response.send_message('❌ Указанный канал не найден или не является текстовым.', ephemeral=True)
        return

    # Проверяем, может ли бот отправлять сообщения в этот канал
    if not target_channel.permissions_for(interaction.guild.me).send_messages:
        await interaction.response.send_message('❌ У бота нет прав на отправку сообщений в этот канал.', ephemeral=True)
        return

    # Отправляем сообщение
    try:
        await target_channel.send(текст)
        await interaction.response.send_message(f'✅ Сообщение отправлено в канал {target_channel.mention}.', ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f'❌ Ошибка при отправке: {e}', ephemeral=True)
bot.run(TOKEN)