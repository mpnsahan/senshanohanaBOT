import asyncio
import os
import disnake
from disnake.ext import commands
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()
#мой айди
ADMIN_DISCORD_ID = 935421550260269076
DUEL_ROLE_NAME = "Дуэлянт"
DUEL_CATEGORY_ID = 1542518489518968873
# Укажи ID каналов, где боту РАЗРЕШЕНО работать
ALLOWED_CHANNEL_IDS = [1542572756720418907]


intents = disnake.Intents.default()
intents.message_content = True
intents.members = True  # Нужен для работы с ролями и пользователями

intents = disnake.Intents.default()
intents.message_content = True  # Нужен для чтения текста сообщений
#нужно поменять на айди серва
bot = commands.Bot(command_prefix="snh/", intents=intents, test_guilds=[1537474145921663056],status=disnake.Status.dnd,activity=disnake.Activity(type=disnake.ActivityType.watching, name="большой брат следит за вами"))

# Глобальная проверка для всех команд
@bot.check
async def check_channel(ctx):
    # Если команда вызвана в ЛС или в разрешенном канале — пропускаем
    if ctx.guild is None or ctx.channel.id in ALLOWED_CHANNEL_IDS:
        return True
    
    # Также разрешаем команду !close внутри самих дуэльных каналов!
    if "дуэль-" in ctx.channel.name:
        return True

    # Иначе блокируем вызов
    await ctx.send(f"❌ Бот работает только в специальном канале: <#{ALLOWED_CHANNEL_IDS[0]}>", delete_after=5)
    return False


@bot.event
async def on_ready():
    print(f"{bot.user} арбайтен")

@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

# --- ФУНКЦИЯ 1: ЗАЯВКА В ПОЛК (WTCLAN) ---

class WTClanModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Твой ник в War Thunder",
                placeholder="Например: КейкоПидор228",
                custom_id="wt_nick",
                style=disnake.TextInputStyle.short,
                max_length=32,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Доп. информация / Обратная связь",
                placeholder="Ну начиркай если хочешь",
                custom_id="feedback",
                style=disnake.TextInputStyle.paragraph,
                max_length=500,
                required=False,
            ),
        ]
        super().__init__(
            title="Заявка в полк War Thunder",
            custom_id="wtclan_modal",
            components=components,
        )

    # Что происходит после того, как пользователь нажал "Отправить"
    async def callback(self, inter: disnake.ModalInteraction):
        # Достаем то, что ввел юзер в карточке
        wt_nick = inter.text_values["wt_nick"]
        feedback = inter.text_values["feedback"] or "Не указано"
        
        now = disnake.utils.utcnow().strftime("%d.%m.%Y %H:%M MSK")

        # 1. Формируем сообщение ТЕБЕ В ЛС (в твоем строгом формате)
        msg_to_admin = (
            f"**Пользователь:** {inter.author} ({inter.author.mention})\n"
            f"**Ник в WT:** {wt_nick}\n"
            f"**Текст / Обратная связь:** {feedback}\n"
            f"**Время:** {now}"
        )

        # 2. Формируем красивый ответ для НОВИЧКА с инструкцией
        user_embed = disnake.Embed(
            title="🪖 Заявка отправлена!",
            description=(
                f"Привет, **{inter.author.display_name}**!\n"
                "Твоя анкета отправлена Кейко.\n\n"
                "⚠️ **ВАЖНОЕ НАПОМИНАНИЕ:**\n"
                "Чтобы мы могли тебя принять, обязательно кинь заявку **внутри самой игры**:\n"
                "1. Зайди в War Thunder.\n"
                "2. Открой раздел **Сообщество -> Полки**.\n"
                "3. Найди наш полк в поиске и нажми **«Подать заявку»**."
            ),
            color=disnake.Color.gold()
        )

        # Отвечаем юзеру (ephemeral=True значит, что это увидит только он)
        await inter.response.send_message(embed=user_embed, ephemeral=True)

        # Отправляем сообщение тебе в ЛС
        try:
            admin = await inter.bot.fetch_user(ADMIN_DISCORD_ID)
            await admin.send(msg_to_admin)
        except Exception as e:
            print(f"Ошибка отправки ЛС админу: {e}")

# 2. Слэш-команда, которая ВЫЗЫВАЕТ эту форму
class DuelModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Ник или ID оппонента в Discord",
                placeholder="Например: User#1234, user или ID",
                custom_id="opponent_input",
                style=disnake.TextInputStyle.short,
                max_length=100,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Заявление / Условия дуэли",
                placeholder="Например: ТРБ, БР 5.7, до трёх побед, или просто пошли нахуй",
                custom_id="duel_reason",
                style=disnake.TextInputStyle.paragraph,
                max_length=500,
                required=True,
            ),
        ]
        super().__init__(
            title="Объявление Дуэли",
            custom_id="duel_modal",
            components=components,
        )

    async def callback(self, inter: disnake.ModalInteraction):
        # Откладываем ответ, чтобы бот успел выполнить сетевые запросы поиска
        await inter.response.defer(ephemeral=True)

        guild = inter.guild
        challenger = inter.author
        opponent_raw = inter.text_values["opponent_input"].strip()
        reason = inter.text_values["duel_reason"]

        opponent = None

        # 1. Если введен ID (цифры)
        if opponent_raw.isdigit():
            try:
                opponent = await guild.fetch_member(int(opponent_raw))
            except disnake.NotFound:
                opponent = None

        # 2. Поиск по имени / отображаемому нику без Privileged Intents
        if not opponent:
            clean_name = opponent_raw.lstrip("@").lower()

            # Ищем совпадения запросом к API Discord
            try:
                found_members = await guild.query_members(query=clean_name, limit=5)
                for member in found_members:
                    if (
                        member.name.lower() == clean_name or 
                        member.display_name.lower() == clean_name or 
                        str(member).lower() == clean_name
                    ):
                        opponent = member
                        break
                # Если точного совпадения нет, но кто-то найден — берем первого
                if not opponent and found_members:
                    opponent = found_members[0]
            except Exception:
                opponent = None

        if not opponent:
            return await inter.edit_original_message(
                content=f"❌ Пользователь `{opponent_raw}` не найден на этом сервере. Укажи точный ник или ID."
            )

        if opponent.id == challenger.id:
            return await inter.edit_original_message(content="❌ Нельзя вызвать на дуэль самого себя!")

        if opponent.bot:
            return await inter.edit_original_message(content="❌ Нельзя вызывать на дуэль ботов!")

        # Проверка роли
        duel_role = disnake.utils.get(guild.roles, name=DUEL_ROLE_NAME)
        
        if not duel_role:
            return await inter.edit_original_message(
                content=f"❌ На сервере отсутствует роль `{DUEL_ROLE_NAME}`. Обратись к администратору."
            )

        if duel_role not in challenger.roles:
            return await inter.edit_original_message(
                content=f"❌ У тебя нет роли `{DUEL_ROLE_NAME}`, необходимой для участия в дуэлях!"
            )

        if duel_role not in opponent.roles:
            return await inter.edit_original_message(
                content=f"❌ У оппонента {opponent.mention} нет роли `{DUEL_ROLE_NAME}`!"
            )

        # Права доступа для канала
        overwrites = {
            guild.default_role: disnake.PermissionOverwrite(read_messages=False),
            challenger: disnake.PermissionOverwrite(read_messages=True, send_messages=True),
            opponent: disnake.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: disnake.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        # Ищем категорию по ID
        category = guild.get_channel(DUEL_CATEGORY_ID)

        # Создаем канал внутри категории
        channel_name = f"⚔️-дуэль-{challenger.name}-vs-{opponent.name}"
        channel = await guild.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            category=category,  # <-- Передаем категорию
            reason="Создание арены для дуэли"
        )
        welcome_embed = disnake.Embed(
            title="⚔️ ДУЭЛЬ ОБЪЯВЛЕНА!",
            description=(
                f"**Вызвавший:** {challenger.mention}\n"
                f"**Соперник:** {opponent.mention}\n\n"
                f"📜 **Заявление / Условия:**\n> {reason}\n\n"
                "📌 **Инструкция:**\n"
                "Договоритесь об условиях, создайте сессию в игре и решите спор!\n"
                "Когда дуэль будет окончена, введите **`snh/close`** прямо в этот чат для удаления канала."
            ),
            color=disnake.Color.red()
        )

        await channel.send(content=f"{challenger.mention} {opponent.mention}", embed=welcome_embed)
        await inter.edit_original_message(content=f"✅ Дуэль объявлена! Приватная арена создана: {channel.mention}")


@bot.slash_command(
    name="duel",
    description="Вызвать участника сервера на дуэль"
)
async def duel(inter: disnake.ApplicationCommandInteraction):
    await inter.response.send_modal(modal=DuelModal())


@bot.command(name="close")
async def close_duel(ctx):
    if "дуэль-" in ctx.channel.name:
        await ctx.send("🧹 Дуэль завершена. Канал будет удален через 5 секунд...")
        await asyncio.sleep(5)
        await ctx.channel.delete(reason="Дуэль завершена, закрытие канала")
    else:
        await ctx.send("❌ Эта команда работает только внутри дуэльных каналов!")

# Слэш-команда /hello
@bot.slash_command(description="Поздороваться с ботом")
async def hello(inter: disnake.ApplicationCommandInteraction):
    await inter.response.send_message(f"Салам, {inter.author.mention}!")

bot.run(os.getenv("BOT_TOKEN"))