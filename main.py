# ФУНКЦИЯ импорт библиотек
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View, Button, Modal, TextInput
import json
import os
import re
import functools
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
BLACKLIST_CONFIG_FILE = 'blacklist_config.json'
VC_CONFIG_FILE = 'vc_config.json'

# ---------- ПУТИ К JSON-ФАЙЛАМ ДАННЫХ ----------
TICKETS_FILE = 'tickets.json'
PUNISHMENTS_FILE = 'punishments.json'
BLACKLIST_FILE = 'blacklist.json'

# ---------- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ----------
roster_messages = {}  # {channel_id: message_id}
ROLE_HIERARCHY = []

# ---------- ID ПОЛЬЗОВАТЕЛЯ С ПОЛНЫМИ ПРАВАМИ ----------
OWNER_ID = 1012623951719051284

# ---------- ФУНКЦИИ ЗАГРУЗКИ/СОХРАНЕНИЯ JSON ----------
def load_json(filename, default=None):
    if default is None:
        default = {}
    if not os.path.exists(filename):
        return default
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False, default=str)

# ---------- ЗАГРУЗКА КОНФИГОВ ----------
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
    return load_json(CONFIG_FILE, {})

def save_roles(data):
    save_json(CONFIG_FILE, data)

def load_permissions():
    return load_json(PERMISSIONS_FILE, {})

def save_permissions(data):
    save_json(PERMISSIONS_FILE, data)

def load_ticket_config():
    default = {
        "admin_channel_id": None,
        "allowed_roles": ["Глава", "Зам главы", "Тех администратор"]
    }
    return load_json(TICKET_CONFIG_FILE, default)

def save_ticket_config(data):
    save_json(TICKET_CONFIG_FILE, data)

def load_punishment_config():
    default = {
        "channel_id": None,
        "allowed_roles": ["Глава", "Зам главы", "Тех администратор"]
    }
    return load_json(PUNISHMENT_CONFIG_FILE, default)

def save_punishment_config(data):
    save_json(PUNISHMENT_CONFIG_FILE, data)

def load_blacklist_config():
    default = {
        "channel_id": None,
        "default_conditions": ""
    }
    return load_json(BLACKLIST_CONFIG_FILE, default)

def save_blacklist_config(data):
    save_json(BLACKLIST_CONFIG_FILE, data)

def load_vc_config():
    default = {
        "trigger_channel_id": None,
        "management_channel_id": None,
        "category_id": None,
        "name_template": "Голосовой канал {user}"
    }
    return load_json(VC_CONFIG_FILE, default)

def save_vc_config(data):
    save_json(VC_CONFIG_FILE, data)

TICKET_CONFIG = load_ticket_config()
PUNISHMENT_CONFIG = load_punishment_config()
BLACKLIST_CONFIG = load_blacklist_config()
VC_CONFIG = load_vc_config()

# ---------- ЗАГРУЗКА ДАННЫХ ИЗ JSON ----------
def load_tickets():
    return load_json(TICKETS_FILE, [])

def save_tickets(data):
    save_json(TICKETS_FILE, data)

def load_punishments():
    return load_json(PUNISHMENTS_FILE, [])

def save_punishments(data):
    save_json(PUNISHMENTS_FILE, data)

def load_blacklist():
    return load_json(BLACKLIST_FILE, [])

def save_blacklist(data):
    save_json(BLACKLIST_FILE, data)

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (с проверкой OWNER_ID) ----------
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
    if interaction.user.id == OWNER_ID:
        return True
    config = load_roles()
    level, _ = get_user_role_level(interaction.user, config)
    if level is not None and level <= 2:
        return True
    return False

def check_command_permission(interaction: discord.Interaction, command_name: str) -> bool:
    if interaction.user.id == OWNER_ID:
        return True
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
    if user.id == OWNER_ID:
        return True
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
    if user.id == OWNER_ID:
        return True
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

# ---------- ФУНКЦИЯ ОБНОВЛЕНИЯ ТАБЛИЦЫ РОЛЕЙ ----------
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

# ---------- ФУНКЦИИ ДЛЯ ТИКЕТОВ (JSON) ----------
async def get_ticket_by_channel(channel_id):
    tickets = load_tickets()
    for ticket in tickets:
        if ticket.get('channel_id') == channel_id:
            return ticket
    return None

async def update_ticket_status(channel_id, status, admin_id=None, reason=None, punishment=None):
    tickets = load_tickets()
    for ticket in tickets:
        if ticket.get('channel_id') == channel_id:
            ticket['status'] = status
            if admin_id:
                ticket['admin_id'] = admin_id
            if reason:
                ticket['reason'] = reason
            if punishment:
                ticket['punishment'] = punishment
            if status in ("approved", "rejected"):
                ticket['closed_at'] = datetime.now().isoformat()
            break
    save_tickets(tickets)

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
        title=f"📩 Тикет #{ticket.get('id', '')}",
        color=0x00ff00 if ticket.get("status") == "approved" else 0xff0000 if ticket.get("status") == "rejected" else 0xffaa00,
        timestamp=datetime.now()
    )
    embed.add_field(name="Подал", value=f"<@{ticket.get('user_id')}>", inline=True)
    embed.add_field(name="Нарушитель", value=ticket.get('target_user_id'), inline=True)
    embed.add_field(name="Статус",
                    value=f"{status_emoji.get(ticket.get('status'), '')} {status_text.get(ticket.get('status'), '')}",
                    inline=False)
    embed.add_field(name="Суть", value=ticket.get('description'), inline=False)
    if ticket.get('location'):
        embed.add_field(name="Место", value=ticket.get('location'), inline=True)
    if ticket.get('ps'):
        embed.add_field(name="PS", value=ticket.get('ps'), inline=True)
    if ticket.get('reason'):
        embed.add_field(name="Причина закрытия", value=ticket.get('reason'), inline=False)
    if ticket.get('punishment'):
        embed.add_field(name="Наказание", value=ticket.get('punishment'), inline=False)
    if ticket.get('closed_at'):
        try:
            closed_dt = datetime.fromisoformat(ticket['closed_at'])
            delete_time = closed_dt + timedelta(hours=24)
            embed.set_footer(text=f"Канал будет удалён {delete_time.strftime('%d.%m.%Y в %H:%M')}")
        except:
            pass
    await msg.edit(embed=embed)

# ---------- ФУНКЦИИ ДЛЯ НАКАЗАНИЙ (JSON) ----------
async def add_punishment(user_id, admin_id, type, reason, conditions=None):
    punishments = load_punishments()
    new_id = max([p.get('id', 0) for p in punishments]) + 1 if punishments else 1
    entry = {
        "id": new_id,
        "user_id": user_id,
        "admin_id": admin_id,
        "type": type,
        "reason": reason,
        "conditions": conditions,
        "status": "active",
        "created_at": datetime.now().isoformat(),
        "removed_at": None,
        "removed_by": None,
        "removed_reason": None,
        "converted_to": None
    }
    punishments.append(entry)
    save_punishments(punishments)
    return new_id

async def get_active_punishments(user_id, type=None):
    punishments = load_punishments()
    result = []
    for p in punishments:
        if p.get('user_id') != user_id:
            continue
        if p.get('status') != 'active':
            continue
        if type and p.get('type') != type:
            continue
        result.append(p)
    return result

async def remove_punishment(punishment_id, removed_by, reason):
    punishments = load_punishments()
    for p in punishments:
        if p.get('id') == punishment_id:
            p['status'] = 'removed'
            p['removed_at'] = datetime.now().isoformat()
            p['removed_by'] = removed_by
            p['removed_reason'] = reason
            break
    save_punishments(punishments)

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
        punishments = load_punishments()
        for w in to_convert:
            for p in punishments:
                if p.get('id') == w['id']:
                    p['status'] = 'converted'
                    p['converted_to'] = reprimand_id
                    break
        save_punishments(punishments)
        await send_punishment_notification(bot, user_id, 'reprimand', reason, admin_name="Система", conditions=None, converted_from_warnings=True)
        return True
    return False

async def check_and_reset_reprimands(user_id, bot):
    reprimands = await get_active_punishments(user_id, 'reprimand')
    if len(reprimands) >= 3:
        punishments = load_punishments()
        for p in punishments:
            if p.get('user_id') == user_id and p.get('status') == 'active':
                p['status'] = 'expired'
        save_punishments(punishments)
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

# ---------- ФУНКЦИИ ДЛЯ ЧС (JSON) – с поддержкой steam_id ----------
async def add_blacklist(user_id, target_name, reason, conditions, steam_id=None):
    """
    Добавляет запись в ЧС. Если steam_id указан и есть активная запись с таким же steam_id,
    обновляет target_name и возвращает id существующей записи, иначе создаёт новую.
    """
    blacklist = load_blacklist()
    # Если указан steam_id, ищем активную запись с таким steam_id
    if steam_id:
        steam_id = steam_id.strip()
        for entry in blacklist:
            if entry.get('status') == 'active' and entry.get('steam_id') == steam_id:
                # Обновляем target_name
                entry['target_name'] = target_name
                # Также можно обновить reason и conditions? По желанию, но оставим как есть.
                save_blacklist(blacklist)
                return entry['id']  # возвращаем существующий id
    # Если не нашли или steam_id не указан, создаём новую запись
    new_id = max([b.get('id', 0) for b in blacklist]) + 1 if blacklist else 1
    entry = {
        "id": new_id,
        "user_id": user_id,
        "target_name": target_name,
        "reason": reason,
        "conditions": conditions,
        "steam_id": steam_id or "",  # сохраняем даже пустое
        "status": "active",
        "created_at": datetime.now().isoformat(),
        "removed_at": None,
        "removed_by": None,
        "removed_reason": None
    }
    blacklist.append(entry)
    save_blacklist(blacklist)
    return new_id

async def get_active_blacklist(user_id=None, target_name=None):
    blacklist = load_blacklist()
    result = []
    for entry in blacklist:
        if entry.get('status') != 'active':
            continue
        if user_id and entry.get('user_id') != user_id:
            continue
        if target_name and target_name.lower() not in entry.get('target_name', '').lower():
            continue
        result.append(entry)
    return result

async def remove_blacklist(entry_id, removed_by, removed_reason):
    blacklist = load_blacklist()
    for entry in blacklist:
        if entry.get('id') == entry_id:
            entry['status'] = 'removed'
            entry['removed_at'] = datetime.now().isoformat()
            entry['removed_by'] = removed_by
            entry['removed_reason'] = removed_reason
            break
    save_blacklist(blacklist)

async def get_blacklist_by_id(entry_id):
    blacklist = load_blacklist()
    for entry in blacklist:
        if entry.get('id') == entry_id:
            return entry
    return None

async def send_blacklist_notification(bot, entry, is_add=True, removed_reason=None):
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
        if entry.get('conditions'):
            embed.add_field(name="Условия снятия", value=entry['conditions'], inline=False)
        if entry.get('steam_id'):
            embed.add_field(name="Steam ID", value=entry['steam_id'], inline=True)
        embed.set_footer(text=f"ID записи: {entry['id']}")
    else:
        embed = discord.Embed(
            title="✅ Снятие ЧС",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Пользователь", value=entry['target_name'] if entry['user_id'] == 0 else f"<@{entry['user_id']}>", inline=True)
        embed.add_field(name="Причина снятия", value=removed_reason, inline=False)
        if entry.get('steam_id'):
            embed.add_field(name="Steam ID", value=entry['steam_id'], inline=True)
        embed.set_footer(text=f"ID записи: {entry['id']}")
    await channel.send(embed=embed)

# ---------- ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ ПОЛЬЗОВАТЕЛЯ ИЗ REPLY (для ЧС и тикетов) ----------
async def get_target_from_reply(interaction: discord.Interaction):
    if interaction.message and interaction.message.reference:
        try:
            referenced = await interaction.channel.fetch_message(interaction.message.reference.message_id)
            if referenced.mentions:
                return referenced.mentions[0]
        except:
            pass
    return None

# ---------- ФОНОВАЯ ЗАДАЧА ДЛЯ УДАЛЕНИЯ КАНАЛОВ ТИКЕТОВ ----------
async def delete_expired_tickets(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            tickets = load_tickets()
            now = datetime.now()
            for ticket in tickets:
                if ticket.get('status') in ('approved', 'rejected') and ticket.get('closed_at'):
                    closed_at = datetime.fromisoformat(ticket['closed_at'])
                    if (now - closed_at) >= timedelta(hours=24):
                        channel = bot.get_channel(ticket['channel_id'])
                        if channel:
                            try:
                                await channel.delete(reason="Автоматическое удаление через 24 часа после закрытия")
                                print(f"Канал {channel.name} удалён.")
                            except Exception as e:
                                print(f"Ошибка удаления канала {ticket['channel_id']}: {e}")
                        tickets = [t for t in tickets if t.get('id') != ticket.get('id')]
                        save_tickets(tickets)
        except Exception as e:
            print(f"Ошибка в delete_expired_tickets: {e}")
        await asyncio.sleep(60)

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

        tickets = load_tickets()
        new_id = max([t.get('id', 0) for t in tickets]) + 1 if tickets else 1
        ticket_data = {
            "id": new_id,
            "channel_id": channel.id,
            "message_id": msg.id,
            "user_id": interaction.user.id,
            "target_user_id": self.target_name.value,
            "description": self.description.value,
            "location": self.location.value or "",
            "ps": self.ps.value or "",
            "status": "waiting",
            "admin_id": None,
            "reason": None,
            "punishment": None,
            "created_at": datetime.now().isoformat(),
            "closed_at": None
        }
        tickets.append(ticket_data)
        save_tickets(tickets)

        admin_channel_id = TICKET_CONFIG.get("admin_channel_id")
        if admin_channel_id:
            admin_channel = interaction.guild.get_channel(admin_channel_id)
            if admin_channel:
                view = TicketActionView(new_id, channel.id, interaction.user.id)
                admin_embed = discord.Embed(
                    title=f"🆕 Новый тикет #{new_id}",
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

# ---------- МОДАЛЬНЫЕ ОКНА ДЛЯ НАКАЗАНИЙ ----------
class WarningModal(discord.ui.Modal, title="⚠️ Выдача предупреждения"):
    def __init__(self):
        super().__init__()
        self.user_input = discord.ui.TextInput(
            label="Пользователь (имя, @упоминание или ID)",
            placeholder="Например: @user или имя",
            required=True
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
        target_name = ""
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
            await interaction.followup.send(
                "❌ Не удалось определить пользователя. Укажите корректное имя, @упоминание или ID.",
                ephemeral=True
            )
            return

        if not check_punishment_permission(interaction.user):
            await interaction.followup.send("❌ У вас нет прав на выдачу наказаний.", ephemeral=True)
            return

        if target:
            user_id = target.id
            display_name = target.display_name
            await add_punishment(user_id, interaction.user.id, 'warning', self.reason.value, self.conditions.value or None)
            await send_punishment_notification(
                interaction.client,
                user_id,
                'warning',
                self.reason.value,
                interaction.user.display_name,
                self.conditions.value or None
            )
            converted = await check_and_convert_warnings(user_id, interaction.client)
            if converted:
                await check_and_reset_reprimands(user_id, interaction.client)
            await interaction.followup.send(f"✅ Предупреждение выдано пользователю {target.mention}.", ephemeral=True)
        else:
            await add_punishment(0, interaction.user.id, 'warning', self.reason.value, self.conditions.value or None, target_name=target_name)
            await send_punishment_notification_with_name(interaction.client, 0, target_name, 'warning', self.reason.value, interaction.user.display_name, self.conditions.value or None)
            await interaction.followup.send(f"✅ Предупреждение выдано пользователю '{target_name}'.", ephemeral=True)

class ReprimandModal(discord.ui.Modal, title="📢 Выдача выговора"):
    def __init__(self):
        super().__init__()
        self.user_input = discord.ui.TextInput(
            label="Пользователь (имя, @упоминание или ID)",
            placeholder="Например: @user или имя",
            required=True
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
        target_name = ""
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
            await interaction.followup.send(
                "❌ Не удалось определить пользователя. Укажите корректное имя, @упоминание или ID.",
                ephemeral=True
            )
            return

        if not check_punishment_permission(interaction.user):
            await interaction.followup.send("❌ У вас нет прав на выдачу наказаний.", ephemeral=True)
            return

        if target:
            user_id = target.id
            display_name = target.display_name
            await add_punishment(user_id, interaction.user.id, 'reprimand', self.reason.value, self.conditions.value or None)
            await send_punishment_notification(
                interaction.client,
                user_id,
                'reprimand',
                self.reason.value,
                interaction.user.display_name,
                self.conditions.value or None
            )
            await check_and_reset_reprimands(user_id, interaction.client)
            await interaction.followup.send(f"✅ Выговор выдан пользователю {target.mention}.", ephemeral=True)
        else:
            await add_punishment(0, interaction.user.id, 'reprimand', self.reason.value, self.conditions.value or None, target_name=target_name)
            await send_punishment_notification_with_name(interaction.client, 0, target_name, 'reprimand', self.reason.value, interaction.user.display_name, self.conditions.value or None)
            await interaction.followup.send(f"✅ Выговор выдан пользователю '{target_name}'.", ephemeral=True)

class RemovePunishmentModal(discord.ui.Modal, title="Снятие наказания"):
    user_input = discord.ui.TextInput(
        label="Пользователь (имя, @упоминание или ID)",
        placeholder="Например: @user или имя",
        required=True
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
        target_name = ""
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
            await interaction.followup.send(
                "❌ Не удалось определить пользователя. Укажите корректное имя, @упоминание или ID.",
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

        if target:
            user_id = target.id
            punishments = await get_active_punishments(user_id, ptype)
            if not punishments:
                await interaction.followup.send(f"❌ У пользователя {target.mention} нет активных наказаний типа {ptype}.", ephemeral=True)
                return
            for p in punishments:
                await remove_punishment(p['id'], interaction.user.id, self.reason.value)
            embed = discord.Embed(
                title="✅ Снятие наказания",
                description=f"С {target.mention} сняты все {ptype}.\nПричина: {self.reason.value}",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            channel_id = PUNISHMENT_CONFIG.get('channel_id')
            if channel_id:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    await channel.send(embed=embed)
            await interaction.followup.send(f"✅ Все активные {ptype} сняты с {target.mention}.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Снятие наказаний с текстовых имён пока не поддерживается.", ephemeral=True)

# ---------- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ОТПРАВКИ УВЕДОМЛЕНИЙ С ИМЕНЕМ ----------
async def send_punishment_notification_with_name(bot, user_id, display_name, type, reason, admin_name, conditions=None):
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
    embed.add_field(name="Пользователь", value=display_name, inline=True)
    embed.add_field(name="Выдал", value=admin_name, inline=True)
    embed.add_field(name="Причина", value=reason, inline=False)
    if conditions:
        embed.add_field(name="Условия снятия", value=conditions, inline=False)
    await channel.send(embed=embed)

# ---------- БОТ ----------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
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

# ---------- КОМАНДЫ НАКАЗАНИЙ ----------
@bot.tree.command(name='предупреждение', description='Выдать предупреждение пользователю')
async def warning(interaction: discord.Interaction):
    modal = WarningModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(name='выговор', description='Выдать выговор пользователю')
async def reprimand(interaction: discord.Interaction):
    modal = ReprimandModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(name='снять', description='Снять активные наказания (предупреждения или выговоры)')
async def remove_punishment(interaction: discord.Interaction):
    modal = RemovePunishmentModal()
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

# ---------- ЧС (ЧЁРНЫЙ СПИСОК) – ОБНОВЛЁННАЯ ВЕРСИЯ ----------
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
        self.steam_input = discord.ui.TextInput(
            label="Steam ID (необязательно)",
            placeholder="Введите Steam ID (32-битный или обычный)",
            required=False
        )
        self.add_item(self.user_input)
        self.add_item(self.reason)
        self.add_item(self.conditions)
        self.add_item(self.steam_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

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
                "❌ Не удалось определить пользователя. Укажите его в поле или ответьте на сообщение бота с упоминанием.",
                ephemeral=True
            )
            return

        if not check_management_permissions(interaction):
            await interaction.followup.send("❌ У вас нет прав на выдачу ЧС.", ephemeral=True)
            return

        conditions = self.conditions.value
        if not conditions:
            conditions = BLACKLIST_CONFIG.get('default_conditions', '')

        steam_id = self.steam_input.value.strip() or None

        if target:
            user_id = target.id
            name = target.display_name
        else:
            user_id = 0
            name = target_name

        # Добавляем или обновляем запись
        entry_id = await add_blacklist(user_id, name, self.reason.value, conditions, steam_id)
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

        if target:
            entries = await get_active_blacklist(user_id=target.id)
            display = target.display_name
        else:
            entries = await get_active_blacklist(target_name=target_name)
            display = target_name

        if not entries:
            await interaction.followup.send(f"❌ У {display} нет активных ЧС.", ephemeral=True)
            return

        for entry in entries:
            await remove_blacklist(entry['id'], interaction.user.id, self.reason.value)
            await send_blacklist_notification(interaction.client, entry, is_add=False, removed_reason=self.reason.value)

        await interaction.followup.send(f"✅ ЧС снята с {display}.", ephemeral=True)

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
    if query.isdigit():
        entries = await get_active_blacklist(user_id=int(query))
    else:
        entries = await get_active_blacklist(target_name=query)

    if not entries:
        await interaction.response.send_message(f'❌ Не найдено активных ЧС для "{query}".', ephemeral=True)
        return

    embed = discord.Embed(title=f"🔍 Результаты поиска для '{query}'", color=discord.Color.blue())
    for entry in entries[:5]:
        name = entry['target_name'] if entry['user_id'] == 0 else f"<@{entry['user_id']}>"
        steam = entry.get('steam_id', '')
        embed.add_field(
            name=f"ID {entry['id']} – {name}",
            value=f"**Причина:** {entry['reason']}\n**Условия:** {entry['conditions'] or 'Нет'}\n**Steam ID:** {steam or 'Не указан'}\n**Дата:** {entry['created_at']}",
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
        steam = entry.get('steam_id', '')
        embed.add_field(
            name=f"ID {entry['id']} – {name}",
            value=f"**Причина:** {entry['reason']}\n**Условия:** {entry['conditions'] or 'Нет'}\n**Steam ID:** {steam or 'Не указан'}",
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

# ---------- ОБРАБОТЧИК СООБЩЕНИЙ (для ответов с пингом в ЧС) ----------
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.reference:
        try:
            referenced = await message.channel.fetch_message(message.reference.message_id)
        except:
            return
        if referenced.author == bot.user:
            if message.mentions:
                channel_id = BLACKLIST_CONFIG.get('channel_id')
                if referenced.channel.id == channel_id:
                    target = message.mentions[0]
                    if referenced.embeds:
                        embed = referenced.embeds[0]
                        if embed.footer and embed.footer.text:
                            import re
                            match = re.search(r'ID записи:\s*(\d+)', embed.footer.text)
                            if match:
                                entry_id = int(match.group(1))
                                entry = await get_blacklist_by_id(entry_id)
                                if entry:
                                    dm_embed = discord.Embed(
                                        title="📨 Уведомление о ЧС",
                                        color=discord.Color.red() if entry['status'] == 'active' else discord.Color.green(),
                                        timestamp=datetime.now()
                                    )
                                    if entry['status'] == 'active':
                                        dm_embed.description = f"Вам была выдана ЧС.\n**Причина:** {entry['reason']}\n**Условия снятия:** {entry['conditions'] or 'Нет'}\n**Steam ID:** {entry.get('steam_id', 'Не указан')}"
                                    else:
                                        dm_embed.description = f"С вас снята ЧС.\n**Причина снятия:** {entry['removed_reason']}"
                                    await target.send(embed=dm_embed)
                                    await message.channel.send(f"✅ Уведомление отправлено {target.mention} в ЛС.", delete_after=10)
        return

    await bot.process_commands(message)

# ---------- КОМАНДА /написать ----------
async def channel_autocomplete(interaction: discord.Interaction, current: str):
    if not interaction.guild:
        return []
    channels = [ch for ch in interaction.guild.text_channels if ch.permissions_for(interaction.guild.me).send_messages]
    if current:
        channels = [ch for ch in channels if current.lower() in ch.name.lower()]
    return [
        app_commands.Choice(name=f"#{ch.name}", value=str(ch.id))
        for ch in channels[:25]
    ]

@bot.tree.command(name='написать', description='Отправить текст в указанный канал')
@app_commands.describe(текст='Текст сообщения', канал='Канал для отправки (выберите из списка)')
@app_commands.autocomplete(канал=channel_autocomplete)
@require_permission('написать')
async def send_to_channel(interaction: discord.Interaction, текст: str, канал: str):
    try:
        channel_id = int(канал)
        target_channel = interaction.guild.get_channel(channel_id)
    except (ValueError, TypeError):
        await interaction.response.send_message('❌ Неверный идентификатор канала.', ephemeral=True)
        return

    if not target_channel or not isinstance(target_channel, discord.TextChannel):
        await interaction.response.send_message('❌ Указанный канал не найден или не является текстовым.', ephemeral=True)
        return

    if not target_channel.permissions_for(interaction.guild.me).send_messages:
        await interaction.response.send_message('❌ У бота нет прав на отправку сообщений в этот канал.', ephemeral=True)
        return

    try:
        await target_channel.send(текст)
        await interaction.response.send_message(f'✅ Сообщение отправлено в канал {target_channel.mention}.', ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f'❌ Ошибка при отправке: {e}', ephemeral=True)

# ---------- КОМАНДА /kick ----------
@bot.tree.command(name='kick', description='Выгнать участника')
@require_permission('kick')
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = "Не указана"):
    await user.kick(reason=reason)
    await interaction.response.send_message(f'Пользователь {user.mention} выгнан. Причина: {reason}')

# ===================================================================
#   СИСТЕМА ВРЕМЕННЫХ ГОЛОСОВЫХ КАНАЛОВ (VOICE MASTER)
# ===================================================================
# ---------- ХРАНИЛИЩЕ СООБЩЕНИЙ УПРАВЛЕНИЯ ----------
active_vc_messages = {}

async def get_vc_management_message(guild, voice_channel_id):
    if voice_channel_id not in active_vc_messages:
        return None
    msg_id = active_vc_messages[voice_channel_id]
    channel_id = VC_CONFIG.get('management_channel_id')
    if not channel_id:
        return None
    channel = guild.get_channel(channel_id)
    if not channel:
        return None
    try:
        return await channel.fetch_message(msg_id)
    except:
        return None

class VoiceControlView(View):
    def __init__(self, voice_channel_id, creator_id, guild):
        super().__init__(timeout=None)
        self.voice_channel_id = voice_channel_id
        self.creator_id = creator_id
        self.guild = guild

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.creator_id:
            return True
        if interaction.user.guild_permissions.manage_channels:
            return True
        await interaction.response.send_message("❌ Только создатель канала или администратор может управлять им.", ephemeral=True)
        return False

    @discord.ui.button(label="Открыть", style=discord.ButtonStyle.success, emoji="🔓")
    async def open_button(self, interaction: discord.Interaction, button: Button):
        channel = self.guild.get_channel(self.voice_channel_id)
        if not channel:
            await interaction.response.edit_message(content="❌ Канал уже удалён.", view=None)
            return
        await channel.set_permissions(self.guild.default_role, connect=True)
        await interaction.response.send_message("✅ Канал открыт для всех.", ephemeral=True)

    @discord.ui.button(label="Закрыть", style=discord.ButtonStyle.danger, emoji="🔒")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        channel = self.guild.get_channel(self.voice_channel_id)
        if not channel:
            await interaction.response.edit_message(content="❌ Канал уже удалён.", view=None)
            return
        await channel.set_permissions(self.guild.default_role, connect=False)
        await interaction.response.send_message("✅ Канал закрыт (только разрешённые пользователи).", ephemeral=True)

    @discord.ui.button(label="Показать", style=discord.ButtonStyle.secondary, emoji="👁️")
    async def show_button(self, interaction: discord.Interaction, button: Button):
        channel = self.guild.get_channel(self.voice_channel_id)
        if not channel:
            await interaction.response.edit_message(content="❌ Канал уже удалён.", view=None)
            return
        await channel.set_permissions(self.guild.default_role, view_channel=True)
        await interaction.response.send_message("✅ Канал теперь виден всем.", ephemeral=True)

    @discord.ui.button(label="Спрятать", style=discord.ButtonStyle.secondary, emoji="🙈")
    async def hide_button(self, interaction: discord.Interaction, button: Button):
        channel = self.guild.get_channel(self.voice_channel_id)
        if not channel:
            await interaction.response.edit_message(content="❌ Канал уже удалён.", view=None)
            return
        await channel.set_permissions(self.guild.default_role, view_channel=False)
        await interaction.response.send_message("✅ Канал скрыт от всех, кроме разрешённых.", ephemeral=True)

    @discord.ui.button(label="Разрешить", style=discord.ButtonStyle.primary, emoji="➕")
    async def allow_button(self, interaction: discord.Interaction, button: Button):
        channel = self.guild.get_channel(self.voice_channel_id)
        if not channel:
            await interaction.response.edit_message(content="❌ Канал уже удалён.", view=None)
            return
        modal = UserPermissionModal(channel, allow=True)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Запретить", style=discord.ButtonStyle.danger, emoji="➖")
    async def deny_button(self, interaction: discord.Interaction, button: Button):
        channel = self.guild.get_channel(self.voice_channel_id)
        if not channel:
            await interaction.response.edit_message(content="❌ Канал уже удалён.", view=None)
            return
        modal = UserPermissionModal(channel, allow=False)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Разрешения", style=discord.ButtonStyle.secondary, emoji="📋")
    async def permissions_button(self, interaction: discord.Interaction, button: Button):
        channel = self.guild.get_channel(self.voice_channel_id)
        if not channel:
            await interaction.response.edit_message(content="❌ Канал уже удалён.", view=None)
            return
        perms = channel.overwrites
        users_with_perms = []
        for target, overwrite in perms.items():
            if isinstance(target, discord.Member):
                if overwrite.connect is not None or overwrite.view_channel is not None:
                    users_with_perms.append(f"{target.mention}: connect={overwrite.connect}, view={overwrite.view_channel}")
        if not users_with_perms:
            await interaction.response.send_message("📭 Нет особых разрешений для пользователей.", ephemeral=True)
        else:
            embed = discord.Embed(title="📋 Разрешения пользователей", description="\n".join(users_with_perms[:10]), color=discord.Color.blue())
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Удалить канал", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, interaction: discord.Interaction, button: Button):
        channel = self.guild.get_channel(self.voice_channel_id)
        if not channel:
            await interaction.response.edit_message(content="❌ Канал уже удалён.", view=None)
            return
        await channel.delete(reason=f"Удаление по запросу {interaction.user}")
        msg = await get_vc_management_message(self.guild, self.voice_channel_id)
        if msg:
            await msg.delete()
        active_vc_messages.pop(self.voice_channel_id, None)
        await interaction.response.send_message("✅ Канал удалён.", ephemeral=True)

class UserPermissionModal(Modal, title="Выберите пользователя"):
    def __init__(self, channel, allow):
        super().__init__()
        self.channel = channel
        self.allow = allow
        self.user_input = TextInput(
            label="Упоминание или ID пользователя",
            placeholder="Например: @user или 123456789",
            required=True
        )
        self.add_item(self.user_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.user_input.value.strip()
        user = None
        if raw.startswith('<@') and raw.endswith('>'):
            user_id = int(raw.strip('<@!>'))
            user = interaction.guild.get_member(user_id)
        elif raw.isdigit():
            user = interaction.guild.get_member(int(raw))
        else:
            for member in interaction.guild.members:
                if member.name.lower() == raw.lower() or member.display_name.lower() == raw.lower():
                    user = member
                    break
        if not user:
            await interaction.response.send_message("❌ Пользователь не найден.", ephemeral=True)
            return
        if self.allow:
            await self.channel.set_permissions(user, connect=True, view_channel=True)
            await interaction.response.send_message(f"✅ {user.mention} добавлен в список разрешённых.", ephemeral=True)
        else:
            await self.channel.set_permissions(user, connect=False, view_channel=False)
            await interaction.response.send_message(f"✅ {user.mention} добавлен в список запрещённых.", ephemeral=True)

@bot.event
async def on_voice_state_update(member, before, after):
    trigger_id = VC_CONFIG.get('trigger_channel_id')
    if not trigger_id:
        return
    if after.channel and after.channel.id == trigger_id:
        for vc_id in active_vc_messages.keys():
            ch = member.guild.get_channel(vc_id)
            if ch and ch.id != trigger_id and ch in member.voice.channels:
                await member.move_to(None)
                try:
                    await member.send("❌ У вас уже есть активный голосовой канал.")
                except:
                    pass
                return

        guild = member.guild
        category_id = VC_CONFIG.get('category_id')
        category = guild.get_channel(category_id) if category_id else None
        name_template = VC_CONFIG.get('name_template', 'Голосовой канал {user}')
        channel_name = name_template.format(user=member.display_name)

        try:
            new_channel = await guild.create_voice_channel(
                name=channel_name,
                category=category,
                reason=f"Временный канал для {member.display_name}"
            )
        except Exception as e:
            try:
                await member.send(f"❌ Не удалось создать канал: {e}")
            except:
                pass
            return

        await member.move_to(new_channel)

        management_channel_id = VC_CONFIG.get('management_channel_id')
        if management_channel_id:
            management_channel = guild.get_channel(management_channel_id)
            if management_channel:
                view = VoiceControlView(new_channel.id, member.id, guild)
                embed = discord.Embed(
                    title=f"🎙️ Управление каналом {channel_name}",
                    description=f"Создатель: {member.mention}",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                msg = await management_channel.send(embed=embed, view=view)
                try:
                    await msg.pin()
                except:
                    pass
                active_vc_messages[new_channel.id] = msg.id
        bot.loop.create_task(check_and_delete_empty_vc_channel(new_channel))

async def check_and_delete_empty_vc_channel(channel):
    await asyncio.sleep(30)
    channel = channel.guild.get_channel(channel.id)
    if not channel:
        return
    if len(channel.members) == 0:
        msg = await get_vc_management_message(channel.guild, channel.id)
        if msg:
            await msg.delete()
        active_vc_messages.pop(channel.id, None)
        try:
            await channel.delete(reason="Канал пуст (автоудаление)")
        except:
            pass

@bot.tree.command(name='vc_setup', description='Настройка системы временных голосовых каналов')
@app_commands.describe(
    trigger='ID голосового канала-триггера',
    management='ID текстового канала для управления (опционально)',
    category='ID категории для новых каналов (опционально)',
    name_template='Шаблон имени (используйте {user} для имени создателя)'
)
@app_commands.default_permissions(administrator=True)
async def vc_setup(interaction: discord.Interaction, trigger: str, management: str = None,
                   category: str = None, name_template: str = "Голосовой канал {user}"):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав для настройки голосовых каналов.', ephemeral=True)
        return

    try:
        trigger_ch = interaction.guild.get_channel(int(trigger))
        if not trigger_ch or not isinstance(trigger_ch, discord.VoiceChannel):
            raise ValueError
    except:
        await interaction.response.send_message('❌ Неверный ID канала-триггера (нужен ID голосового канала).', ephemeral=True)
        return

    management_ch = None
    if management:
        try:
            management_ch = interaction.guild.get_channel(int(management))
            if not management_ch or not isinstance(management_ch, discord.TextChannel):
                raise ValueError
        except:
            await interaction.response.send_message('❌ Неверный ID канала управления (нужен ID текстового канала).', ephemeral=True)
            return

    category_ch = None
    if category:
        try:
            category_ch = interaction.guild.get_channel(int(category))
            if not category_ch or not isinstance(category_ch, discord.CategoryChannel):
                raise ValueError
        except:
            await interaction.response.send_message('❌ Неверный ID категории.', ephemeral=True)
            return

    VC_CONFIG['trigger_channel_id'] = trigger_ch.id
    VC_CONFIG['management_channel_id'] = management_ch.id if management_ch else None
    VC_CONFIG['category_id'] = category_ch.id if category_ch else None
    VC_CONFIG['name_template'] = name_template
    save_vc_config(VC_CONFIG)

    embed = discord.Embed(title='✅ Настройки сохранены', color=discord.Color.green())
    embed.add_field(name="Канал-триггер", value=trigger_ch.mention, inline=False)
    embed.add_field(name="Канал управления", value=management_ch.mention if management_ch else "Не задан (управление в ЛС)", inline=False)
    embed.add_field(name="Категория", value=category_ch.mention if category_ch else "Не задана", inline=False)
    embed.add_field(name="Шаблон имени", value=name_template, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='vc_config', description='Показать текущие настройки временных голосовых каналов')
async def vc_config(interaction: discord.Interaction):
    if not check_management_permissions(interaction):
        await interaction.response.send_message('❌ У вас недостаточно прав.', ephemeral=True)
        return

    trigger_id = VC_CONFIG.get('trigger_channel_id')
    management_id = VC_CONFIG.get('management_channel_id')
    category_id = VC_CONFIG.get('category_id')
    name_template = VC_CONFIG.get('name_template', "Голосовой канал {user}")

    trigger = interaction.guild.get_channel(trigger_id) if trigger_id else None
    management = interaction.guild.get_channel(management_id) if management_id else None
    category = interaction.guild.get_channel(category_id) if category_id else None

    embed = discord.Embed(title='⚙️ Текущие настройки', color=discord.Color.blue())
    embed.add_field(name="Канал-триггер", value=trigger.mention if trigger else "Не задан", inline=False)
    embed.add_field(name="Канал управления", value=management.mention if management else "Не задан (управление в ЛС)", inline=False)
    embed.add_field(name="Категория", value=category.mention if category else "Не задана", inline=False)
    embed.add_field(name="Шаблон имени", value=name_template, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------- ЗАПУСК ----------
bot.run(TOKEN)
