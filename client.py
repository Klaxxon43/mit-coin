import random
from aiogram import Bot, F, types, Router, Dispatcher
import asyncio
from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ChatMemberStatus, ChatType
from cachetools import TTLCache
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db import DB
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, InputMediaPhoto, ChatMemberUpdated, \
    ContentType, LabeledPrice, PreCheckoutQuery
from kb import menu_kb, back_menu_kb, profile_kb, pr_menu_kb, pr_menu_canc, work_menu_kb, back_work_menu_kb, \
    back_profile_kb, select_deposit_menu_kb, back_dep_kb, cancel_all_kb
import uuid
from config import CRYPTOBOT_TOKEN
import datetime
import pytz
from aiocryptopay import AioCryptoPay, Networks
import requests
import uuid
from config import ADMINS_ID


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = Router()

task_cache = {}
task_cache_chat = {}



MOSCOW_TZ = pytz.timezone("Europe/Moscow")



class create_tasks(StatesGroup):
    chanel_task_create = State()
    chanel_task_create2 = State()

    chat_task_create = State()
    chat_task_create2 = State()

    post_task_create = State()
    post_task_create2 = State()

class buystars(StatesGroup):
    buystars = State()

class checks(StatesGroup):
    check_op1 = State()
    check_op = State()
    add_activation = State()
    check_password = State()
    single_check_create = State()
    multi_check_quantity = State()
    multi_check_amount = State()
    check_discription = State()
    check_lock_user = State()
    check_password1 = State()
    ref_fund_quantity = State()
    refill_ref_fund_quantity = State()
    set_ref_fund = State()
    refill_ref_fund = State()
    reffer_id = State()

class convertation(StatesGroup):
    mittorub = State()

class output(StatesGroup):
    rub1 = State()
    usdt1 = State()
    usdt = State()
    rub = State()

async def send_message_safe(bot: Bot, chat_id: int, text: str, reply_markup=None):
    try:
        await bot.get_chat(chat_id)  # Проверяем, существует ли чат
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {e}")

@client.message(F.text.startswith('/start'))
async def start_handler(message: types.Message, state: FSMContext, bot: Bot):
    user = await DB.select_user(message.from_user.id)
    await state.clear()

    args = message.text.split()
    referrer_id = None
    check_uid = None
    ref_user_id = None  # ID пользователя, который активирует чек по реферальной ссылке

    if len(args) > 1:
        param = args[1]
        if param.startswith("check_"):
            check_uid = param[len("check_"):]
        elif param.startswith("ref_"):
            # Обработка реферальной ссылки для чеков
            ref_parts = param.split("_")
            if len(ref_parts) == 3:
                check_uid = ref_parts[1]
                ref_user_id = int(ref_parts[2])  # ID реферера (пользователя, чья ссылка использовалась)
                await state.update_data(reffer_id=ref_user_id)  # Обновляем данные для чека
        else:
            # Обработка обычной реферальной ссылки
            referrer_id = int(param)

    # Обработка личных сообщений
    if message.chat.type == 'private':
        if not user:
            # Пользователь новый
            await DB.add_user(message.from_user.id, message.from_user.username)
            await DB.increment_all_users() 
            
            # Если это чековая ссылка, но не реферальная, делаем пользователя рефералом создателя чека
            if check_uid and not ref_user_id:
                check = await DB.get_check_by_uid(check_uid)
                if check:
                    creator_id = check[2]  # ID создателя чека
                    await DB.update_user(message.from_user.id, referrer_id=creator_id)
                    await DB.add_balance(creator_id, 1000)  # Награда за привлечение
                    await DB.record_referral_earnings(referrer_id=creator_id, referred_user_id=message.from_user.id, amount=1000)
                    await send_message_safe(bot, creator_id,
                                           f"👤 Пользователь c ID {message.from_user.id} перешел по вашему чеку и стал вашим рефералом.\n\n💸 Вам начислено 1000 MitCoin за привлечение нового пользователя.",
                                           reply_markup=back_menu_kb())
            
            # Если это обычная реферальная ссылка
            elif referrer_id:
                await DB.update_user(message.from_user.id, referrer_id=referrer_id)
                await DB.add_balance(referrer_id, 1000)
                await DB.record_referral_earnings(referrer_id=referrer_id, referred_user_id=message.from_user.id, amount=1000)
                await send_message_safe(bot, referrer_id,
                                       f"👤 Пользователь c ID {message.from_user.id} перешел по вашей реферальной ссылке.\n\n💸 Вам начислено 1000 MitCoin за привлечение нового пользователя.",
                                       reply_markup=back_menu_kb())
            
            # Если это реферальная ссылка для чеков
            elif ref_user_id:
                await DB.update_user(message.from_user.id, referrer_id=ref_user_id)
                await DB.add_balance(ref_user_id, 1000)
                await DB.record_referral_earnings(referrer_id=ref_user_id, referred_user_id=message.from_user.id, amount=1000)
                await send_message_safe(bot, ref_user_id,
                                       f"👤 Пользователь c ID {message.from_user.id} перешел по вашей реферальной ссылке.\n\n💸 Вам начислено 1000 MitCoin за привлечение нового пользователя.",
                                       reply_markup=back_menu_kb())

        # Если пользователь уже зарегистрирован, но перешел по реферальной ссылке для чеков
        elif ref_user_id:
            check = await DB.get_check_by_uid(check_uid)
            if check:
                # Проверяем, есть ли еще активации в реферальном фонде
                if check[12] > 0 and check[12]:  # ref_fund
                    # Проверка подписки на канал
                    if check[10]:
                        try:
                            user_channel_status = await bot.get_chat_member(chat_id=check[10], user_id=message.from_user.id)
                            if user_channel_status.status not in ['member', 'administrator', 'creator']:
                                await message.answer(f"💸 <b>Для активации этого чека необходимо подписаться на канал:</b> {check[10]}\n\n<i>После подписки повторите попытку</i>", reply_markup=back_menu_kb())
                                return
                        except Exception as e:
                            logger.error(f'Ошибка при проверке подписки на канал - {e}')
                            await message.answer(f'😢 <b>В данный момент невозможно проверить подписку, повторите попытку позже</b>\n', reply_markup=back_menu_kb())
                            return

                    # Проверка пароля
                    if check[9]:
                        await message.answer("🔑 <b>Для получения чека необходимо ввести пароль:</b>", reply_markup=back_menu_kb())
                        await state.set_state(checks.check_password1)
                        await state.update_data(check_uid=check_uid)
                        return

                    # Активация чека
                    await DB.add_balance(message.from_user.id, check[4])
                    await DB.process_check_activation(check_uid)
                    await DB.add_activated_check(message.from_user.id, check_uid)

                    # Уменьшаем количество активаций в реферальном фонде
                    await DB.check_fund_minus(check[0])

                    # Начисляем реферальный бонус
                    referral_bonus = check[11]  # Получаем процент реферала из столбца ref_bonus
                    referral_amount = (check[4] * referral_bonus) // 100
                    await DB.add_balance(ref_user_id, referral_amount)

                    # Сообщение активатору чека
                    bot_username = (await bot.get_me()).username
                    referral_link = f"https://t.me/{bot_username}?start=ref_{check_uid}_{message.from_user.id}"
                    await message.answer(
                        f"🥳 <b>Вы успешно активировали реферальный чек на {check[4]} MitCoin!</b>\n\n"
                        f"🔗 <b>Ваша реферальная ссылка:</b>\n{referral_link}\n\n"
                        f"💸 <b>Распространяйте эту ссылку и получайте {referral_bonus}% от суммы чека за каждого привлеченного пользователя!</b>",
                        reply_markup=back_menu_kb()
                    )

                    # Сообщение рефереру
                    await send_message_safe(
                        bot,
                        ref_user_id,
                        f"💸 <b>Пользователь c ID {message.from_user.id} активировал ваш реферальный чек!</b>\n\n"
                        f"💰 <b>Вам начислено {referral_amount} MitCoin за активацию чека.</b>",
                        reply_markup=back_menu_kb()
                    )

                    # Если реферальный фонд закончился, уведомляем создателя чека
                    if check[12] - 1 == 0:
                        await send_message_safe(
                            bot,
                            check[2],
                            f"⚠️ <b>Реферальный фонд для чека {check_uid} закончился.</b>\n\n"
                            f"💵 Вы можете пополнить реферальный фонд, чтобы продолжить привлекать пользователей.",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                                InlineKeyboardButton(text="Пополнить реферальный фонд", callback_data=f'refill_ref_fund_{check[0]}')
                            ]])
                        )
                else:
                    await message.answer("❌ Реферальный фонд для этого чека закончился.", reply_markup=back_menu_kb())

        elif check_uid:
            # Активация чека
            check = await DB.get_check_by_uid(check_uid)
            if check and not await DB.is_check_activated(message.from_user.id, check_uid) and check[2] != message.from_user.id:
                usname = message.from_user.username
                name = message.from_user.full_name
                if usname is None:
                    usname = name
                else:
                    usname = f'@{usname}'

                # Отправляем информацию о чеке
                check_info = f"💎 <b>Информация о чеке:</b>\n\n" \
                             f"💸 Сумма: {check[4]} MitCoin\n" \
                             f"📝 Описание: {check[7] if check[7] else 'Отсутствует'}\n\n"
                if check[10]:
                    check_info += f"🔗 Подписка на канал: {check[10]}\n"
                if check[9]:
                    check_info += f"🔑 Пароль: Требуется\n"
                await message.answer(check_info, reply_markup=back_menu_kb())

                if check[3] == 1:  # Сингл-чек
                    if check[7]:
                        if (check[7])[0] == '@':
                            if check[7] != f'@{usname}':
                                await message.answer("❌ <b>Этот чек предназначен для другого пользователя</b>", reply_markup=back_menu_kb())
                                return
                        elif check[7] != message.from_user.id:
                            await message.answer("❌ <b>Этот чек предназначен для другого пользователя</b>",
                                                 reply_markup=back_menu_kb())
                            return

                    # Проверка подписки на канал
                    if check[10]:
                        try:
                            user_channel_status = await bot.get_chat_member(chat_id=check[10], user_id=message.from_user.id)
                            if user_channel_status.status not in ['member', 'administrator', 'creator']:
                                await message.answer(f"💸 <b>Для активации этого чека необходимо подписаться на канал:</b> {check[10]}\n\n<i>После подписки повторите попытку</i>", reply_markup=back_menu_kb())
                                return
                        except Exception as e:
                            logger.error(f'Ошибка при проверке подписки на канал - {e}')
                            await message.answer(f'😢 <b>В данный момент невозможно проверить подписку, повторите попытку позже</b>\n', reply_markup=back_menu_kb())
                            return

                    # Проверка пароля
                    if check[9]:
                        await message.answer("🔑 <b>Для получения чека необходимо ввести пароль:</b>", reply_markup=back_menu_kb())
                        await state.set_state(checks.check_password1)
                        await state.update_data(check_uid=check_uid)
                        return

                    # Активация чека
                    await DB.add_balance(message.from_user.id, check[4])
                    await DB.process_check_activation(check_uid)
                    await DB.add_activated_check(message.from_user.id, check_uid)
                    await message.answer(f"🥳 <b>Вы успешно активировали чек на {check[4]} MitCoin</b>", reply_markup=back_menu_kb())

                    # Уведомление создателю чека
                    await send_message_safe(bot, check[2], text=f'💸 <b>Ваш одноразовый чек на {check[4]} MitCoin был активирован пользователем {usname}</b>', reply_markup=back_menu_kb())
                    return

                elif check[3] == 2:  # Мульти-чек
                    if check[5] > 0:
                        # Проверка подписки на канал
                        if check[10]:
                            try:
                                user_channel_status = await bot.get_chat_member(chat_id=check[10], user_id=message.from_user.id)
                                if user_channel_status.status not in ['member', 'administrator', 'creator']:
                                    await message.answer(f"💸 <b>Для активации этого чека необходимо подписаться на канал:</b> {check[10]}\n\n<i>После подписки повторите попытку</i>", reply_markup=back_menu_kb())
                                    return
                            except Exception as e:
                                logger.error(f'Ошибка при проверке подписки на канал - {e}')
                                await message.answer(f'😢 <b>В данный момент невозможно проверить подписку, повторите попытку позже</b>\n', reply_markup=back_menu_kb())
                                return

                        # Проверка пароля
                        if check[9]:
                            await message.answer("🔑 <b>Для получения чека необходимо ввести пароль:</b>", reply_markup=back_menu_kb())
                            await state.set_state(checks.check_password1)
                            await state.update_data(check_uid=check_uid)
                            return

                        # Активация чека
                        await DB.add_balance(message.from_user.id, check[4])
                        await DB.process_check_activation(check_uid)
                        await DB.add_activated_check(message.from_user.id, check_uid)

                        # Если чек активирован по реферальной ссылке, начисляем награду рефереру
                        if ref_user_id and check[11]:
                            referral_bonus = check[11]
                            referral_amount = (check[4] * int(referral_bonus)) // 100
                            await DB.add_balance(ref_user_id, referral_amount)
                            await send_message_safe(bot, ref_user_id, f"💸 Вы получили {referral_amount} MitCoin за реферальную активацию чека.")

                        # Уведомление создателю чека
                        await send_message_safe(bot, check[2], f"💸 Ваш чек на {check[4]} MitCoin был активирован пользователем {usname}.")

                        # Создаем реферальную ссылку для текущего пользователя
                        if check[11] and not ref_user_id:
                            referral_bonus = check[11]
                            referral_amount = (check[4] * int(referral_bonus)) // 100
                            await DB.add_balance(ref_user_id, referral_amount)
                            await send_message_safe(bot, ref_user_id, f"💸 Вы получили {referral_amount} MitCoin за реферальную активацию чека.")
                            bot_username = (await bot.get_me()).username
                            referral_link = f"https://t.me/{bot_username}?start=ref_{check_uid}_{message.from_user.id}"
                            await message.answer(
                                f"🔗 <b>Ваша реферальная ссылка:</b>\n{referral_link}\n\n"
                                f"💸 <b>Распространяйте эту ссылку и получайте {str(referral_bonus)}% от суммы чека за каждого привлеченного пользователя!</b>",
                                reply_markup=back_menu_kb()
                            ) 

                        await message.answer(f"🥳 <b>Вы успешно активировали чек на {check[4]} MitCoin</b>", reply_markup=back_menu_kb())
                        return

                    else:
                        await message.answer("❌ Этот чек уже исчерпан.", reply_markup=back_menu_kb())
                        return
            else:
                await message.answer("❌ <b>Данный чек не может быть активирован по следующим возможным причинам:</b>\n\n<i>1) Этот чек был создан Вами\n2) Вы уже активировали данный чек\n3) Чек не существует, либо произошла ошибка</i>", reply_markup=back_menu_kb())
                return

        # Основное меню
        
        await message.answer(
            "💎 <b>PR MIT</b> - <em>мощный и уникальный инструмент для рекламы ваших проектов</em>\n\n<b>Главное меню</b>",
            reply_markup=menu_kb())

    # Обработка сообщений в группах и супер-группах
    elif message.chat.type in ['group', 'supergroup'] and not check_uid:
        await message.answer("Для получения информации используйте бота в личных сообщениях.")


@client.message(checks.check_password1)
async def handle_check_password(message: types.Message, state: FSMContext, bot: Bot):
    user_data = await state.get_data()
    check_uid = user_data.get("check_uid")
    data = await state.get_data()
    ref_user_id = data.get("reffer_id")
    name = message.from_user.full_name
    usname = message.from_user.username
    if usname is None:
        usname = name
    else:
        usname = f'@{usname}'

    if not check_uid:
        await message.answer("❌ <i>Возникла ошибка. Повторите попытку позже...</i>", reply_markup=back_menu_kb())
        await state.clear()
        return

    check = await DB.get_check_by_uid(check_uid)
    if not check:
        await message.answer("❌ Чек не найден или уже был активирован.", reply_markup=back_menu_kb())
        await state.clear()
        return

    if message.text == check[9]:  # Проверка пароля
        await DB.add_balance(message.from_user.id, check[4])
        await DB.process_check_activation(check_uid)
        await DB.add_activated_check(user_id=message.from_user.id, uid=check_uid)

        # Если чек активирован по реферальной ссылке, начисляем награду рефереру
        if ref_user_id and check[11]:
            referral_bonus = check[11]  # Получаем процент реферала из столбца ref_bonus
            referral_amount = (check[4] * referral_bonus) // 100
            await DB.add_balance(ref_user_id, referral_amount)
            await send_message_safe(bot, ref_user_id, f"💸 Вы получили {referral_amount} MitCoin за реферальную активацию чека.")

            # Уведомление создателю чека
            await send_message_safe(bot, check[2], f"💸 Ваш чек на {check[4]} MitCoin был активирован пользователем {usname}.")

            # Создаем реферальную ссылку для текущего пользователя
            bot_username = (await bot.get_me()).username
            referral_link = f"https://t.me/{bot_username}?start=ref_{check_uid}_{message.from_user.id}"
            await message.answer(
                f"🔗 <b>Ваша реферальная ссылка:</b>\n{referral_link}\n\n"
                f"💸 <b>Распространяйте эту ссылку и получайте {referral_bonus}% от суммы чека за каждого привлеченного пользователя!</b>",
                reply_markup=back_menu_kb()
            )

        await message.answer(f"🥳 <b>Вы успешно активировали чек на {check[4]} MitCoin</b>", reply_markup=back_menu_kb())
        await state.clear()
    else:
        await message.answer("❌ <b>Неверный пароль</b>", reply_markup=back_menu_kb())
        return









@client.callback_query(F.data == 'profile')
async def profile_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    print(user)
    balance = user['balance']
    rub_balance = user['rub_balance']
    if balance is None:
        balance = 0
    await callback.answer()
    await callback.message.edit_text(f'''
👀 <b>Профиль:</b>

🪪 <b>ID</b> - <code>{user_id}</code>

💰 Баланс ($MICO) - {balance} MitCoin
💳 Баланс (рубли) - {rub_balance} ₽
    ''', reply_markup=profile_kb())


@client.callback_query(F.data == 'back_menu')
async def back_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "<b>💎 PR MIT</b> - <em>мощный и уникальный инструмент для рекламы ваших проектов</em>\n\n<b>Главное меню</b>",
        reply_markup=menu_kb())


@client.callback_query(F.data == 'rasslka_menu')
async def back_menu_handler(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "Рассылка в боте - 1000 рублей, обращаться - @Coin_var",
        reply_markup=back_menu_kb())


@client.callback_query(F.data == 'op_piar_menu')
async def back_menu_handler(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "Реклама в ОП - 500 рублей за 1 день, обращаться - @Coin_var",
        reply_markup=back_menu_kb())


@client.callback_query(F.data == 'cancel_all')
async def cancel_all(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await profile_handler(callback)


@client.callback_query(F.data == 'pr_menu_cancel')
async def cancel_pr(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await pr_menu_handler(callback)


@client.callback_query(F.data == 'menu_stats')
async def stats_menu_handler(callback: types.CallbackQuery):
    user_count = len(await DB.select_all())
    all_tasks = len(await DB.get_tasks())
    calculate_total_cost = await DB.calculate_total_cost()
    statics = await DB.get_statics() 
    print(statics)
    id, chanels, groups, all, see, u = statics[0] 
    id2, chanels2, groups2, all2, see2, users = statics[1] 
    balance = await DB.all_balance()
    gifts = await DB.count_bonus_time_rows()
    text = f"""
    <b>🌐 Статистика 🌐 </b>

👥 Всего пользователей: {user_count}

💼 Всего заданий: {all_tasks}
💸 Возможно заработать: {calculate_total_cost}

🗓<b>Ежедненая статистика</b>: 
💼Выполнено заданий всех типов: {all2}
📣 Подписались на каналы: {chanels2}
👥 Подписались на группы: {groups2}
👁️ Общее количество просмотров: {see2}
👤Новых пользователей сегодня: {users}

🗓<b>Статистика за всё время работы:</b>
💼Выполнено заданий всех типов: {all}
📣 Подписались на каналы: {chanels}
👥 Подписались на группы: {groups}
👁️ Общее количество просмотров: {see}
💸Баланс всех пользователей: {balance} MC
🎁Собрано подарков: {gifts}

"""
    build = InlineKeyboardBuilder()
    build.add(InlineKeyboardButton(text='🏆Рейтинг', callback_data='rating'))
    build.add(InlineKeyboardButton(text="Назад 🔙", callback_data='back_stats'))
    build.adjust(1)
    await callback.message.edit_text(text, reply_markup=build.as_markup())
    await callback.answer()


@client.callback_query(F.data == 'pr_menu')
async def pr_menu_handler(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "📋 <b>В данном разделе вы можете создать свои задания</b>\nЧто нужно рекламировать?", reply_markup=pr_menu_kb())


@client.callback_query(F.data == 'support')
async def refki_handler(callback: types.CallbackQuery):
    await callback.answer()
    roadmap = "https://telegra.ph/Dorozhnaya-karta-proekta-Mit-Coin--Mit-Coin-Project-Roadmap-11-25"
    token = "https://telegra.ph/Tokenomika-monety-MitCoin-MICO-11-25"
    channel = "https://t.me/mitcoinnews"
    add_button01 = InlineKeyboardButton(text="📋 О нас", url='https://telegra.ph/O-proekte-Mit-Coin-11-26')
    add_button0 = InlineKeyboardButton(text="💎 Канал бота", url=channel)
    add_button = InlineKeyboardButton(text="🚙 Дорожная карта", url=roadmap)
    add_button2 = InlineKeyboardButton(text="💱 Токеномика", url=token)
    add_button3 = InlineKeyboardButton(text="🛠️ Служба поддержки", callback_data='support_menu')
    add_button1 = InlineKeyboardButton(text="🔙 Назад", callback_data='back_menu')
    # Создаем клавиатуру и добавляем в нее кнопку
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button01], [add_button], [add_button2], [add_button0], [add_button3], [add_button1]])
    await callback.message.edit_text('''
Тут вы найдите всю нужную информацию касательно нашего проекта
    ''', reply_markup=keyboard)

@client.callback_query(F.data == 'support_menu')
async def refki_handler(callback: types.CallbackQuery):
    support_link = "https://t.me/mitcoinmen"
    add_button3 = InlineKeyboardButton(text="🛠️ Служба поддержки", url=support_link)
    add_button1 = InlineKeyboardButton(text="🔙 Назад", callback_data='back_menu')
    # Создаем клавиатуру и добавляем в нее кнопку
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button3], [add_button1]])
    await callback.message.edit_text('''
🛠️ Если у вас возникли технические трудности или вы нашли баг, пишите @mitcoinmen. Или <a href='https://t.me/mitcoin_chat'>в наш ЧАТ</a>. За находку багов вознаграждение.

Связь с владельцем - @Coin_var
        ''', reply_markup=keyboard)

@client.callback_query(F.data == 'op_help_menu')
async def refki_handler(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("""
👤 ОП (Обязательная Подписка) - функция для чатов, пользователи не смогут писать в чат, пока не подпишутся на необходимые каналы  

<b>Для настройки обязательной подписки (ОП)</b>:

1) Бот должен быть админом в данном чате и в рекламируемых (необходимых к подписке) каналах/чатах 📛
2) Напишите команду /setup @канал 
(⌛ для настройки ОП с таймером используйте /setup @канал **h, где ** количество часов)
<i>пример - /setup @mitcoinnews 12h</i>
3) для удаления всех ОП используйте /unsetup 
или /unsetup @канал для удаления конкретного канала 
4) список всех активных ОП в чате - /status
        """,reply_markup=back_menu_kb())

@client.callback_query(F.data == 'bonus_menu')
async def bonus_menu(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    user_id = callback.from_user.id
    ops = await DB.get_bonus_ops()


    unsubscribed_channels = []
    if ops:
        for op in ops:
            channel_id = op[1]
            link = op[2]
            if not await is_user_subscribed(user_id, channel_id, bot):
                unsubscribed_channels.append(link)

        # Если есть каналы, на которые нужно подписаться
    if unsubscribed_channels:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться", url=channel) for channel in unsubscribed_channels],
            [InlineKeyboardButton(text="✅ Проверить", callback_data='bonus_proverka')],
            [InlineKeyboardButton(text="🔙 Назад", callback_data='back_menu')]
        ])

        # Формируем список каналов для текстового сообщения
        channels_list = "\n".join(
            [f"{channel}" for channel in unsubscribed_channels])

        await callback.message.edit_text(f"🎁 <b>Подпишитесь на следующие каналы для получения бонуса</b>\n<i>(после подписки перезайдите в этот раздел для получения бонуса):</i>\n\n{channels_list}", reply_markup=keyboard, disable_web_page_preview=True)
        return

    last_bonus_date = await DB.get_last_bonus_date(user_id)
    today = datetime.datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")
    if last_bonus_date == today:
        await callback.message.edit_text("❌ <b>Бонус можно получить только один раз в день.</b>\n\nПопробуйте завтра <i>(возможность получения бонуса обновляется в 00:00 по МСК)</i>", reply_markup=back_menu_kb())
        return

    await DB.update_last_bonus_date(user_id)
    await DB.add_balance(user_id, 5000)
    await callback.answer('+5000 $MICO')
    await callback.message.edit_text(f"🎁 <b>Вы получили ежедневный бонус в размере 5000 $MICO</b>\n\nВозвращайтесь завтра 😉", reply_markup=back_menu_kb())



@client.callback_query(F.data == 'bonus_proverka')
async def bonus_menu(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    user_id = callback.from_user.id
    ops = await DB.get_bonus_ops()


    unsubscribed_channels = []
    if ops:
        for op in ops:
            channel_id = op[1]
            link = op[2]
            if not await is_user_subscribed(user_id, channel_id, bot):
                unsubscribed_channels.append(link)

        # Если есть каналы, на которые нужно подписаться
    if unsubscribed_channels:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться", url=channel) for channel in unsubscribed_channels],
            [InlineKeyboardButton(text="✅ Проверить", callback_data='bonus_proverka')],
            [InlineKeyboardButton(text="🔙 Назад", callback_data='back_menu')]
        ])

        # Формируем список каналов для текстового сообщения
        channels_list = "\n".join(
            [f"{channel}" for channel in unsubscribed_channels])

        await callback.message.edit_text(f"🎁 <b>Подпишитесь на следующие каналы для получения бонуса</b>\n<i>(после подписки перезайдите в этот раздел для получения бонуса):</i>\n\n{channels_list}", reply_markup=keyboard, disable_web_page_preview=True)
        return

    last_bonus_date = await DB.get_last_bonus_date(user_id)
    today = datetime.datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")
    if last_bonus_date == today:
        await callback.message.edit_text("❌ <b>Бонус можно получить только один раз в день.</b>\n\nПопробуйте завтра <i>(возможность получения бонуса обновляется в 00:00 по МСК)</i>", reply_markup=back_menu_kb())
        return

    await DB.update_last_bonus_date(user_id)
    await DB.add_balance(user_id, 5000)
    await callback.answer('+5000 $MICO')
    await callback.message.edit_text(f"🎁 <b>Вы получили ежедневный бонус в размере 5000 $MICO</b>\n\nВозвращайтесь завтра 😉", reply_markup=back_menu_kb())




@client.callback_query(F.data == 'output_menu')
async def outputmenu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    add_button2 = InlineKeyboardButton(text="🔙 Назад", callback_data='profile')
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button2]])
    await callback.message.edit_text(f'''
<b>😢 На данный момент вывод недоступен, следите за новостями в @mitcoinnews</b>
    ''', reply_markup=keyboard)



@client.callback_query(F.data == 'output_menuF')
async def outputmenu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    rub_balance = user['rub_balance']

    add_button1 = InlineKeyboardButton(text=f"💲 USDT", callback_data=f'usdt_output_menu')
    add_button3 = InlineKeyboardButton(text=f"Рубли (только для РФ)", callback_data=f'rub_output_menu')
    add_button2 = InlineKeyboardButton(text="🔙 Назад", callback_data='profile')
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button1], [add_button3], [add_button2]])
    await callback.message.edit_text(f'''
⚡ В данном разделе Вы можете произвести вывод ваших средств с баланса в рублях <i>(рубли можно получить при помощи конвертации)</i>

<span class="tg-spoiler"><b>Лимиты:</b>
Вывод в USDT - от 2.5$ 
Вывод в рублях - от 250₽</span>

⚠ Вывод производится в течении 3 рабочих дней

<b>Выберите способ вывода:</b>
    ''', reply_markup=keyboard)


@client.callback_query(F.data == 'usdt_output_menuF')
async def outputusdtmenu(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    rub_balance = user['rub_balance']

    data_cbr = requests.get('https://www.cbr-xml-daily.ru/daily_json.js').json()
    usd_data = data_cbr['Valute']['USD']
    usd = usd_data['Value']
    usd = int(usd)
    user_usdt = rub_balance/usd

    print(user_usdt)
    if user_usdt < 2.5:
        await callback.message.edit_text(f"😢 <b>Недостаточно средств на балансе</b>\n\nНа вашем балансе {round(user_usdt, 3)}$, минимальная сумма <b>должна быть более 2.5$</b>", reply_markup=back_profile_kb())
        return


    add_button2 = InlineKeyboardButton(text="🔙 Назад", callback_data='back_menu')
    # Создаем клавиатуру и добавляем в нее кнопку
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button2]])
    await callback.message.edit_text(f'💳 Укажите сумму <b>от 2.5 до {round(user_usdt, 3)} USDT</b>, которую вы хотите вывести', reply_markup=keyboard)
    await state.set_state(output.usdt)
    await state.update_data(usd=usd, user_usdt=user_usdt)



@client.message(output.usdt)
async def outputusdtmenu1(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        text = float(message.text)
    except ValueError:
        await message.answer("<b>Введите целое число</b>",reply_markup=back_menu_kb())
        return

    statedata = await state.get_data()
    usd = statedata['usd']
    user_usdt = statedata['user_usdt']

    if text < 2.5 or text > user_usdt:
        await message.answer(f'❗ Укажите сумму <b>от 2.5 до {user_usdt} USDT</b>', reply_markup=back_menu_kb())
        return
    await state.clear()
    await state.set_state(output.usdt1)
    await state.update_data(usd=usd, user_usdt=user_usdt, amount=text)

    await message.answer(f'👛 Теперь укажите Ваш кошелёк <b>USDT (BEP20)</b>, на который будет произведен вывод\n\n‼ <b>Внимание! При некорректном адресе кошелька/неверной сети - сумма вывода возвращена НЕ будет</b>', reply_markup=back_menu_kb())





@client.message(output.usdt1)
async def outputusdtmenu11(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    statedata = await state.get_data()
    usd = statedata['usd']
    amount = statedata['amount']

    try:
        wallet = str(message.text)

        if len(wallet) < 5 or len(wallet) > 50:
            await message.answer("‼ <b>Введите корректный адрес кошелька</b>", reply_markup=back_menu_kb())
            return

    except:
        await message.answer("‼ <b>Введите корректный адрес кошелька</b>",reply_markup=back_menu_kb())
        return


    usd = int(usd)
    sum = amount * usd
    sum = int(sum)

    await message.answer(f'🥳 <b>Заявка на вывод на {amount} USDT создана!</b>\nС вашего баланса списано {sum}₽', reply_markup=back_menu_kb())

    await DB.add_rub_balance(user_id=user_id, amount=-sum)
    await DB.add_output(user_id=user_id, amount=amount, wallet=wallet, type=1)
    await state.clear()










@client.callback_query(F.data == 'rub_output_menu')
async def outputrubmenu(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    rub_balance = user['rub_balance']


    if rub_balance < 250:
        await callback.message.edit_text(f"😢 <b>Недостаточно средств на балансе</b>\n\nНа вашем балансе {rub_balance}₽, минимальная сумма <b>должна быть 250₽ или более</b>", reply_markup=back_profile_kb())
        return


    add_button = InlineKeyboardButton(text="🔙 Назад", callback_data='back_menu')
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button]])
    await callback.message.edit_text(f'💳 Укажите сумму <b>от 250₽ до {rub_balance}₽</b>, которую вы хотите вывести (целое число)', reply_markup=keyboard)
    await state.set_state(output.rub)


@client.message(output.rub)
async def outputrubmenu1(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await DB.select_user(user_id)
    rub_balance = user['rub_balance']
    try:
        text = int(message.text)
    except ValueError:
        await message.answer("<b>Введите число</b>", reply_markup=back_menu_kb())
        return

    if text < 250 or text > rub_balance:
        await message.answer(f'❗ Укажите сумму <b>от 250₽ до {rub_balance}₽</b>', reply_markup=back_menu_kb())
        return

    await state.clear()
    await state.set_state(output.rub1)
    await state.update_data(amount=text)

    await message.answer(f'👛 Теперь укажите номер <b>банковской карты/телефона</b> (для перевода по СБП), а так же <b>имя и фамилию получателя</b>\n\n‼ <b>Внимание! При некорректном номере карты/телефона - сумма вывода возвращена НЕ будет</b>', reply_markup=back_menu_kb())


@client.message(output.rub1)
async def outputrubmenu11(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    statedata = await state.get_data()
    amount = statedata['amount']
    try:
        wallet = str(message.text)
        if len(wallet) > 100 or len(wallet) < 5:
            await message.answer("‼ <b>Введите корректный номер карты/телефона</b>", reply_markup=back_menu_kb())
            return

    except:
        await message.answer("‼ <b>Введите корректный номер карты/телефона</b>", reply_markup=back_menu_kb())
        return

    await message.answer(f'🥳 <b>Заявка на вывод на {amount}₽ создана!</b>\nС вашего баланса списано {amount} рублей', reply_markup=back_menu_kb())

    await DB.add_rub_balance(user_id=user_id, amount=-amount)
    await DB.add_output(user_id=user_id, amount=amount, wallet=wallet, type=2)
    await state.clear()











@client.callback_query(F.data == 'corvertation')
async def corvertation_handler(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    last_conversion_date = await DB.get_last_conversion_date(user_id)
    today = datetime.datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")
    if last_conversion_date == today:
        await callback.message.edit_text("❌ <b>Конвертацию можно проводить только один раз в день.</b>\n\nПопробуйте завтра <i>(возможность конвертации обновляется в 00:00 по МСК)</i>", reply_markup=back_profile_kb())
        return
    add_button1 = InlineKeyboardButton(text="Продолжить!", callback_data='mittorub')
    add_button2 = InlineKeyboardButton(text="🔙 Назад", callback_data='profile')
    # Создаем клавиатуру и добавляем в нее кнопку
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button1], [add_button2]])
    await callback.message.edit_text('''
🌀 <b>Вы можете конвертировать ваши $MICO в рубли!</b>

<i>Конвертацию можно проводить не более 1 раза в день и не более чем на 1% от баланса</i>
    ''', reply_markup=keyboard)

@client.callback_query(F.data == 'mittorub')
async def corvertation_rubtomit_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    mit_balance = user['balance']

    print(mit_balance)

    last_conversion_date = await DB.get_last_conversion_date(user_id)
    today = datetime.datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")
    if last_conversion_date == today:
        await callback.message.answer("❌ <b>Конвертацию можно проводить только один раз в день.</b>\n\nПопробуйте завтра <i>(возможность конвертации обновляется в 00:00 по МСК)</i>", reply_markup=back_profile_kb())
        return 

    if mit_balance is None or mit_balance == 0:
        await callback.message.edit_text('😢 <b>У вас недостаточно $MICO для осуществления конвертации</b>', reply_markup=back_profile_kb())

    maxprocent = mit_balance // 100

    if maxprocent < 1000:
        await callback.message.edit_text('😢 <b>У вас недостаточно $MICO для осуществления конвертации</b>', reply_markup=back_profile_kb())


    add_button1 = InlineKeyboardButton(text=f"Максимально ({maxprocent} $MICO)", callback_data=f'convert_{maxprocent}')
    add_button2 = InlineKeyboardButton(text="🔙 Назад", callback_data='back_menu')
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button1], [add_button2]])

    await callback.message.edit_text(f'''
❓ <b>Сколько $MICO (MitCoin) вы хотите конвертировать в рубли?</b>

<i>Максимальная сумма: 1% от MitCoin баланса</i> - {maxprocent}
    ''', reply_markup=keyboard)

    await state.set_state(convertation.mittorub)
    await state.update_data(maxprocent=maxprocent)


@client.message(convertation.mittorub)
async def corvertation_rubtomit_input(message: types.Message, state: FSMContext):
    maxprocent = await state.get_data()
    maxprocent = maxprocent['maxprocent']
    print(f'макс процент {maxprocent}')

    try:
        convert_amount = int(message.text)
        await state.clear()
    except ValueError:
        await message.reply("❌ Введено некорректное значение, пожалуйста, введите число.", reply_markup=back_menu_kb())
        return

    user_id = message.from_user.id
    user = await DB.select_user(user_id)
    mit_balance = user['balance']
    rub_balance = user['rub_balance']


    last_conversion_date = await DB.get_last_conversion_date(user_id)
    today = datetime.datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")

    if last_conversion_date == today:
        await message.answer("❌ <b>Конвертацию можно проводить только один раз в день.</b>\n\nПопробуйте завтра <i>(возможность конвертации обновляется в 00:00 по МСК)</i>", reply_markup=back_menu_kb())
        return

    if convert_amount > maxprocent:
        await message.answer('❌ Вы не можете конвертировать больше 1% от своего $MICO баланса', reply_markup=back_menu_kb())
        return

    if convert_amount < 1000:
        await message.answer('❌ Невозможно конвертировать сумму меньше 1000 $MICO', reply_markup=back_menu_kb())
        return


    add_rub_balance = convert_amount//1000  # 1000 $MICO = 1 рубль
    await DB.add_rub_balance(user_id, add_rub_balance)
    await DB.add_balance(user_id, -convert_amount)
    await DB.update_last_conversion_date(user_id)

    user = await DB.select_user(user_id)
    mit_balance = user['balance']
    rub_balance = user['rub_balance']

    await message.answer(f"✅ <b>Вы успешно конвертировали {convert_amount} $MICO в {add_rub_balance}₽</b>\n\n"
                                     f"💰 <b>Текущий баланс:</b>\nMitCoin - {mit_balance} $MICO;\nРубли - {rub_balance}₽", reply_markup=back_menu_kb())




@client.callback_query(lambda c: c.data.startswith("convert_"))
async def corvertation_rubtomit_input1(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    convert_amount = int(callback.data.split('_')[1])  # Начальная страница
    user = await DB.select_user(user_id)
    mit_balance = user['balance']
    rub_balance = user['rub_balance']
    maxprocent = mit_balance // 100

    last_conversion_date = await DB.get_last_conversion_date(user_id)
    today = datetime.datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")

    if last_conversion_date == today:
        await callback.message.answer("❌ <b>Конвертацию можно проводить только один раз в день.</b>\n\nПопробуйте завтра <i>(возможность конвертации обновляется в 00:00 по МСК)</i>", reply_markup=back_menu_kb())
        return

    if convert_amount > maxprocent:
        await callback.message.edit_text('❌ Вы не можете конвертировать больше 1% от своего $MICO баланса', reply_markup=back_menu_kb())
        return

    if convert_amount < 1000:
        await callback.message.edit_text('❌ Невозможно конвертировать сумму меньше 1000 $MICO', reply_markup=back_menu_kb())
        return


    add_rub_balance = convert_amount//1000  # 1000 $MICO = 1 рубль
    await DB.add_rub_balance(user_id, add_rub_balance)
    await DB.add_balance(user_id, -convert_amount)
    await DB.update_last_conversion_date(user_id)

    user = await DB.select_user(user_id)
    mit_balance = user['balance']
    rub_balance = user['rub_balance']

    await callback.message.edit_text(f"✅ <b>Вы успешно конвертировали {convert_amount} $MICO в {add_rub_balance}₽</b>\n\n"
                                     f"💰 <b>Текущий баланс:</b>\nMitCoin - {mit_balance} $MICO;\nРубли - {rub_balance}₽", reply_markup=back_menu_kb())










CRYPTOBOT_TESTNET = False  # Указываем, что это тестовая среда

cryptopay = AioCryptoPay(token=CRYPTOBOT_TOKEN, network=Networks.MAIN_NET)


@client.callback_query(F.data == 'select_deposit_menu')
async def select_deposit_handler(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("<b>Выберите удобный Вам способ депозита:</b>\n\n🔥 Акция, при депозите за рубли +25% к пополнению!", reply_markup=select_deposit_menu_kb())

@client.callback_query(F.data == 'deposit_menu')
async def deposit_handler(callback: types.CallbackQuery):
    # Создание кнопок для депозитов
    buttons = [
        ("100к MITcoin | 1💲", 100000, 1),
        ("250к MITcoin | 2.5💲", 250000, 2.5),
        ("500к MITcoin | 5💲", 500000, 5),
        ("1кк MITcoin | 10💲", 1000000, 10),
        ("2.5кк MITcoin | 25💲", 2500000, 25),
        ("5кк MITcoin | 50💲", 5000000, 50),
        ("🔙 Назад", None, None)  # Кнопка "Назад"
    ]

    # Создание списка кнопок для InlineKeyboardMarkup
    inline_buttons = []
    for text, amount, price in buttons:
        if amount is not None and price is not None and isinstance(amount, int):
            inline_buttons.append([InlineKeyboardButton(text=text, callback_data=f'deposit_{amount}_{price}')])
        else:
            inline_buttons.append([InlineKeyboardButton(text=text, callback_data='select_deposit_menu')])  # Кнопка "Назад"

    builder = InlineKeyboardMarkup(inline_keyboard=inline_buttons)  # Передача inline_keyboard

    await callback.message.edit_text(
        "💵 <b>Пополните баланс с помощью CryptoBot</b>\n\nВыберите сумму для пополнения:",
        reply_markup=builder)


@client.callback_query(F.data.startswith('deposit_'))
async def handle_deposit(callback: types.CallbackQuery, bot: Bot):
    data = callback.data.split('_')
    amount = int(data[1])  # Сумма MITcoin
    price = float(data[2])  # Цена в USDT

    try:
        invoice = await cryptopay.create_invoice(
            amount=price,
            asset='USDT',  # Указываем, что это счет для USDT
            description=f'Пополнение на {amount} MITcoin'
        )

        # Выводим все доступные атрибуты объекта invoice для отладки
        logger.error(f"Объект инвойса: {invoice}")

        # Получаем URL для оплаты
        payment_url = invoice.bot_invoice_url

        if not payment_url:
            logger.error("URL для оплаты не найден.")
            await callback.message.edit_text("🤔 Ошибка при создании счета. Попробуйте еще раз...",
                                             reply_markup=back_profile_kb())
            return

        # Создаем разметку для клавиатуры
        builder = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔗 Оплатить", url=payment_url)
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="deposit_menu")
            ]
        ])

        await callback.message.edit_text(
            f"🧾 <b>Ваш счет на {amount} MITcoin:</b> \n\nСумма к оплате: {price} USDT. \n\n‼️ <b>После оплаты счета НЕ ВЫХОДИТЕ из данного меню до получения уведомления, иначе Ваш баланс пополнен НЕ БУДЕТ</b>\n\n⏳ <em>Счет действителен 5 минут</em>",
            reply_markup=builder
        )

        user_id = callback.from_user.id
        invoice_id = invoice.invoice_id
        for _ in range(30):  # 30 * 10 секунд = 300 секунд (5 минут)
            invoice = await cryptopay.get_invoices(invoice_ids=invoice_id)  # Получаем текущий статус инвойса
            logger.info(f"Статус инвойса {invoice_id}: {invoice.status}")

            if invoice.status == 'paid':
                # Если счет оплачен, начисляем MITCoin пользователю
                await DB.add_balance_dep(user_id, amount)
                await DB.add_deposit(user_id, amount=price)
                await callback.message.edit_text(f"🥳 Поздравляем! Вам начислено {amount} MITcoin",
                                                 reply_markup=back_menu_kb())
                return

            await asyncio.sleep(10)  # Ждем 10 секунд перед следующей проверкой

    except Exception as e:
        logger.error(f"Ошибка при создании счета: {e}")
        await callback.message.edit_text("Ошибка при создании счета. Попробуйте еще раз.")




@client.callback_query(F.data == 'dep_stars_menu')
async def dep_stars_handler(callback: types.CallbackQuery):
    # Создание кнопок для пополнений через Telegram Stars
    buttons = [
        ("100к MITcoin | 49 ⭐", 100000, 49),
        ("250к MITcoin | 124 ⭐", 250000, 124),
        ("500к MITcoin | 249 ⭐", 500000, 249),
        ("1кк MITcoin | 499 ⭐", 1000000, 499),
        ("2.5кк MITcoin | 1249 ⭐", 2500000, 1249),
        ("5кк MITcoin | 2499 ⭐", 5000000, 2499),
        ("🔙 Назад", None, None)  # Кнопка "Назад"
    ]

    # Создание списка кнопок для InlineKeyboardMarkup
    inline_buttons = []
    for text, amount, price in buttons:
        if amount is not None and price is not None and isinstance(amount, int):
            inline_buttons.append([InlineKeyboardButton(text=text, callback_data=f'stars_{amount}_{price}')])
        else:
            inline_buttons.append([InlineKeyboardButton(text=text, callback_data='select_deposit_menu')])  # Кнопка "Назад"

    builder = InlineKeyboardMarkup(inline_keyboard=inline_buttons)

    await callback.message.edit_text(
        "⭐ <b>Пополните баланс через Telegram Stars:</b>\n\nВыберите сумму:",
        reply_markup=builder
    )


# Обработка кнопок пополнения через Telegram Stars
# Функция обработки кнопок для оплаты Stars
@client.callback_query(F.data.startswith('stars_'))
async def process_stars_payment(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    data = callback.data.split('_')  # Разделяем данные

    try:
        amount = int(data[1])  # Сумма MITcoin
        stars = int(data[2])   # Стоимость в Stars
    except (IndexError, ValueError):
        await callback.message.edit_text("❌ Ошибка обработки данных для платежа. Попробуйте снова.")
        await callback.answer()
        return

    # Создаем цены для оплаты
    prices = [LabeledPrice(label=f"{stars} Stars", amount=stars)]  # Цена в копейках

    try:
        # Отправляем счет
        await bot.send_invoice(
            chat_id=user_id,
            title=f"⭐ {amount} Mit Coin",
            description=f"Купить {amount} Mit Coin (MICO) за {stars} Stars",
            payload=f"user_{user_id}_stars_{amount}",
            provider_token="",
            currency="XTR",
            prices=prices,
            start_parameter="stars_payment"
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка при создании счета: {e}")
        print(e)
        await callback.answer()

# Функция для обработки платежей
@client.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    # Подтверждаем платеж
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

# Функция завершения оплаты
@client.message(F.successful_payment)
async def successful_payment_handler(message: types.Message, bot: Bot):
    payload = message.successful_payment.invoice_payload
    try:
        # Разделяем payload
        parts = payload.split('_')  # ['user', '<user_id>', 'stars', '<amount>']
        user_id = int(parts[1])  # Преобразуем user_id
        amount = int(parts[3])  # Преобразуем amount
    except (ValueError, IndexError) as e:
        await message.answer("☹  Произошла ошибка при обработке оплаты, обратитесь в тех. поддержку с чеком, который доступен выше")
        print(f"Error parsing payload: {payload} - {e}") 
        return

    if amount == 100000:
        stars = 49
    elif amount == 250000:
        stars = 124
    elif amount == 500000:
        stars = 249
    elif amount == 1000000:
        stars = 499
    elif amount == 2500000:
        stars = 1249
    elif amount == 5000000:
        stars = 2499
    else:
        stars = amount / 3000

    dep_stats = stars * 0.013
    # Зачисляем MITcoin на баланс пользователя
    await DB.add_balance_dep(user_id, amount)
    await DB.add_deposit(user_id, amount=dep_stats)

    # Полезная нагрузка (invoice_payload)

    await message.answer(
        f"✅ Пополнение успешно завершено!\n\n💳 Сумма: <b>{amount} MITcoin</b>\n"
        f"💸 Стоимость: <b>{stars} Stars</b>\n\nСпасибо за то, что Вы с нами! 😊",
        reply_markup=back_profile_kb())






@client.callback_query(F.data == 'buy_stars')
async def buystars_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("<b>Вы можете обменять свои Telegram Stars на Mit Coin по курсу:</b>\n\n1⭐ = 3000 Mit Coin\n\n<b>Введите количество звезд, которое вы хотите продать</b>", reply_markup=back_menu_kb())
    await state.set_state(buystars.buystars)


@client.message(buystars.buystars)
async def buystars_hand(message: types.Message, state: FSMContext, bot: Bot):
    stars_amount = message.text
    try:
        stars_amount = int(stars_amount)
    except ValueError:
        await message.answer("Ошибка, повторите попытку", reply_markup=back_menu_kb())
        return

    user_id = message.from_user.id
    stars = stars_amount
    amount = stars * 2000

    await state.clear()
    # Создаем цены для оплаты

    prices = [LabeledPrice(label=f"{stars} Stars", amount=stars)]  # Цена в копейках
    try:
        # Отправляем счет
        await bot.send_invoice(
            chat_id=user_id,
            title=f"Продажа ⭐",
            description=f"Продать {stars} ⭐ за {amount} MitCoin",
            payload=f"user_{user_id}_stars_{amount}",
            provider_token="",
            currency="XTR",
            prices=prices,
            start_parameter="stars_payment"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при создании счета: {e}", reply_markup=back_menu_kb())
        print(e)





@client.callback_query(F.data == 'rub_donate')
async def rub_donate_h(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("🔥 Акция, при депозите за рубли +25% к пополнению!\n\n💰 Для депозита в рублях обращаться - @Coin_var", reply_markup=back_dep_kb())


@client.callback_query(F.data == 'refka_menu')
async def refki_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    bot_username = (await bot.get_me()).username
    ref_link = f'https://t.me/{bot_username}?start={user_id}'
    user = await DB.select_user(user_id)

    if user and user.get('referrer_id'):
        referrer_id = user['referrer_id']
    else:
        referrer_id = 'нету'

    referred_users = await DB.get_referred_users(user_id)
    earned_from_referrals = await DB.get_earned_from_referrals(user_id)
    if earned_from_referrals is not None:
        earned_from_referrals = round(earned_from_referrals, 3)
    else:
        earned_from_referrals = 0

    text = (f'''
<b>Ваша реферальная ссылка:</b> \n<code>{ref_link}</code>\n
ID того, кто пригласил: <code>{referrer_id}</code>\n

<em>1000 MITcoin за приглашенного пользователя</em>
<em>15% за пополнения и выполнение заданий рефералом</em>

Кол-во приглашенных пользователей: {len(referred_users)} 
Заработано с рефералов: {earned_from_referrals} MIT 💎
    ''')

    await callback.message.edit_text(text, reply_markup=back_profile_kb())
    await callback.answer()


@client.callback_query(F.data == 'work_menu')
async def works_handler(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    user_id = callback.from_user.id
    total_count = await DB.calculate_total_cost()
    chanel_stats = len(await DB.select_chanel_tasks())
    chat_stats = len(await DB.select_chat_tasks())
    post_stats = len(await DB.select_post_tasks())

    await callback.message.edit_text(f'''
💰 Вы можете заработать - <b>{total_count} MITcoin</b>

<b>Заданий на:</b>
📣 Каналы - {chanel_stats}
👥 Чаты - {chat_stats}
👀 Посты - {post_stats}


🚨 <em>Запрещено покидать канал/чат ранее чем через 7 дней. За нарушение вы можете получить блокировку заработка или штраф!</em>

<b>Выберите способ заработка</b> 👇    
    ''', reply_markup=work_menu_kb())


# Создаем кэш для задач (хранится 1 минут)
task_cache = TTLCache(maxsize=100000, ttl=600)
task_cache_chat = TTLCache(maxsize=100000, ttl=480)


async def update_task_cache_for_all_users(bot, DB):
    tasks = [cache_all_tasks(bot, DB)]
    await asyncio.gather(*tasks)
    print("Кэш (каналы) обновлен")


async def update_task_cache_for_all_users_chat(bot, DB):
    tasks = [get_cached_tasks_chat(bot, DB)]
    await asyncio.gather(*tasks)
    print("Кэш (чаты) обновлен")


semaphore = asyncio.Semaphore(2)  # Ограничение одновременных задач


async def cache_all_tasks(bot, DB):
    """Кэшируем задания на каналы только при доступности ссылки и добавляем название канала."""
    all_tasks = await DB.select_chanel_tasks()
    tasks_with_links = [] 
    print(f'все задания в бд - {len(all_tasks)}')

    async with semaphore:
        for task in all_tasks:
            retry_count = 0
            while retry_count < 5:  # Максимальное количество попыток
                try:
                    chat = await bot.get_chat(task[2])
                    invite_link = chat.invite_link
                    if invite_link and task[3] > 0:
                        chat_title = chat.title
                        # Добавляем задание с названием канала, но без самой ссылки
                        tasks_with_links.append((*task, chat_title))
                    else:
                        print(f"Нет доступа к каналу - {task[2]}")
                    break  # Успешно получили данные, выходим из цикла
                except Exception as e:
                    error_message = str(e)
                    if "Flood control exceeded" in error_message:
                        # Попробуем извлечь время ожидания из сообщения об ошибке
                        wait_time = 60  # Устанавливаем значение по умолчанию
                        if "retry after" in error_message:
                            try:
                                wait_time = int(error_message.split("retry after ")[-1].split(" ")[0]) + 5  # +5 секунд
                            except (IndexError, ValueError):
                                print("Не удалось извлечь время ожидания, используем значение по умолчанию.")
                        print(f"Достигнут лимит запросов. Ожидание {wait_time} секунд...")
                        await asyncio.sleep(wait_time)  # Ждем перед повторной попыткой
                        retry_count += 1
                    else:
                        print(f'Ошибка при создании кэша: {e}') 
                        break  # Если ошибка не связана с лимитом, выходим из цикла

    # Сохраняем все задачи с доступными ссылками и названиями каналов в кэш
    task_cache['all_tasks'] = tasks_with_links
    print(f"Кэш (каналы) обновляется... длина - {len(task_cache)}, список заданий - {tasks_with_links}")


async def get_cached_tasks_chat(bot, DB):
    """Кэшируем задания на каналы только при доступности ссылки."""
    all_tasks = await DB.select_chat_tasks()
    tasks_with_links_chat = []

    # Параллельно проверяем наличие ссылок
    async with semaphore:
        for task in all_tasks:
            invite_link = await check_admin_and_get_invite_link_chat(bot, task[2])
            if invite_link and task[3] > 0:
                # Получаем информацию о чате и добавляем название канала
                try:
                    chat = await bot.get_chat(task[2])
                    chat_title = chat.title
                except:
                    chat_title = "Неизвестный чат"
                # Добавляем задание с названием канала, но без самой ссылки
                tasks_with_links_chat.append((*task, chat_title))

    # Сохраняем все задачи с доступными ссылками в кэш
    task_cache_chat['all_tasks'] = tasks_with_links_chat



async def scheduled_cache_update(bot, DB):
    """Функция для запуска обновления кэша задач раз в 5 минут."""
    while True:
        await update_task_cache_for_all_users(bot, DB)
        await asyncio.sleep(600)  # Задержка в 300 секунд (5 минут)


async def scheduled_cache_update_chat(bot, DB):
    """Функция для запуска обновления кэша задач раз в 5 минут."""
    while True:
        await update_task_cache_for_all_users_chat(bot, DB)
        await asyncio.sleep(480)  # Задержка в 300 секунд (7 минут)


# Запуск фоновой задачи в основном цикле
async def start_background_tasks(bot, DB):
    # Запускаем задачу обновления кэша раз в 5 минут
    asyncio.create_task(scheduled_cache_update(bot, DB))
    asyncio.create_task(scheduled_cache_update_chat(bot, DB))
    asyncio.create_task(check_subscriptions_periodically(bot))



@client.callback_query(F.data == 'work_chanel')
async def taskss_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id

    try:
        # Получаем все задачи с ссылками из кэша и фильтруем
        all_tasks = task_cache.get('all_tasks', [])
        print(f'все задания кэш - {len(all_tasks)}')
        tasks = [
            task for task in all_tasks if not await DB.is_task_completed(user_id, task[0])
        ]
        print(f'задания для пользователя {user_id} - {len(tasks)}')
        
        if tasks:
            # Сортируем задачи по количеству подписчиков
            random.shuffle(tasks)
            print(f'сортированные задания {user_id} - {len(tasks)}')
            
            # Генерация клавиатуры
            keyboard = await generate_tasks_keyboard_chanel(tasks, bot)

            await callback.message.edit_text(
                "📢 <b>Задания на каналы:</b>\n\n🎢 Каналы в списке располагаются по количеству необходимых подписчиков\n\n⚡<i>Запрещено отписываться от канала раньше чем через 7 дней, в случае нарушения возможен штраф!</i>",
                reply_markup=keyboard
            )
        else:
            await callback.message.edit_text(
                "На данный момент доступных заданий нет, возвращайся позже 😉",
                reply_markup=back_work_menu_kb()
            )
    except Exception as e:
        print(f"Ошибка в taskss_handler: {e}")
        markup = InlineKeyboardBuilder()
        markup.row(types.InlineKeyboardButton(text='🔄 Обновить', callback_data='work_chanel'))
        await callback.message.edit_text(
            "Произошла ошибка при загрузке заданий. Попробуйте обновить страницу.",
            reply_markup=markup.as_markup()
        )


# Функция для генерации клавиатуры с заданиями
async def generate_tasks_keyboard_chanel(tasks, bot):
    builder = InlineKeyboardBuilder()

    # Выводим задания (по 5 на страницу)
    for task in tasks[:5]:  # Ограничиваем количество заданий на одной странице
        chat_id = task[2]
        chat_title = task[5]

        from aiogram.types import Chat
        chat: Chat = await bot.get_chat(chat_id)
        button_text = f"{chat.title} | +1500"
        builder.row(types.InlineKeyboardButton(text=button_text, callback_data=f"chaneltask_{task[0]}"))

    # Кнопка "Назад"
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="work_menu"))

    # Кнопка "Обновить"
    builder.row(types.InlineKeyboardButton(text="🔄 Обновить", callback_data="work_chanel"))

    return builder.as_markup()


async def check_admin_and_get_invite_link_chanel(bot, target_id):
    try:
        ChatFullInfo = await bot.get_chat(target_id)
        invite_link = ChatFullInfo.invite_link
        return invite_link
    except Exception as e:
        print(e)
        return False


@client.callback_query(lambda c: c.data.startswith("chaneltask_"))
async def task_detail_handler(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    task_id = int(callback.data.split('_')[1])
    task = await DB.get_task_by_id(task_id)

    amount = task[3]

    invite_link = ""

    invite_link = await check_admin_and_get_invite_link_chanel(bot, task[2])
    chat_id = task[2]
    chat = await bot.get_chat(chat_id)
    task_info = f"""
📢 {chat.title} | <i>{amount}</i>
<i>Подпишитесь на канал и нажмите кнопку -</i> <b>Проверить</b> 🔄️

{invite_link}    
    """
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(text="🔙", callback_data="work_chanel"))
    builder.add(types.InlineKeyboardButton(text="Проверить 🔄️", callback_data=f"chanelcheck_{task_id}"))
    builder.add(types.InlineKeyboardButton(text="Репорт ⚠️", callback_data=f"chanelreport_{task_id}"))
    await callback.message.edit_text(task_info, reply_markup=builder.as_markup())


@client.callback_query(F.data.startswith('chanelcheck_'))
async def check_subscription_chanel(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    task_id = int(callback.data.split('_')[1])
    task = await DB.get_task_by_id(task_id)
    if task is None:
        await callback.message.edit_text("❗ Задание не существует или уже выполнено", reply_markup=back_menu_kb())
        await asyncio.sleep(1)

    user_id = callback.from_user.id
    target_id = task[2]
    invite_link = await check_admin_and_get_invite_link_chanel(bot, task[2])
    # Проверяем, подписан ли пользователь на канал
    try:
        bot_member = await bot.get_chat_member(target_id, callback.message.chat.id)
        if bot_member.status != "member":
            builder = InlineKeyboardBuilder()
            builder.add(types.InlineKeyboardButton(text="🔙 Назад", callback_data="work_chanel"))
            builder.add(types.InlineKeyboardButton(text="Проверить 🔄️", callback_data=f"chanelcheck_{task_id}"))
            await callback.message.edit_text(
                f"🚩 Пожалуйста, <b>подпишитесь на канал</b> по ссылке {invite_link} и повторите попытку",
                reply_markup=builder.as_markup())
            return
    except:
        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(text="🔙 Назад", callback_data="work_chanel"))
        builder.add(types.InlineKeyboardButton(text="Проверить 🔄️", callback_data=f"chanelcheck_{task_id}"))
        await callback.message.edit_text(
            f"🚩 Пожалуйста, <b>подпишитесь на канал</b> по ссылке {invite_link} и повторите попытку",
            reply_markup=builder.as_markup())
        return

    if not await DB.is_task_completed(user_id, task[0]):

        # Шаг 4. Обновляем задание (вычитаем amount на 1)
        await DB.update_task_amount(task_id)
        await DB.add_completed_task(user_id, task_id, target_id, 1500, task[1], status=1)
        await DB.add_balance(amount=1500, user_id=user_id)
        # Проверяем, нужно ли удалить задание
        updated_task = await DB.get_task_by_id(task_id)

        if updated_task[3] == 0:
            delete_task = await DB.get_task_by_id(task_id)
            creator_id = delete_task[1]
            await DB.delete_task(task_id)
            await bot.send_message(creator_id, f"🎉 Одно из ваших заданий было успешно выполнено",
                                   reply_markup=back_menu_kb())
            
        await DB.increment_all_subs_chanel() 
        await DB.increment_all_taasks() 
        await callback.message.edit_text("✅")
        await callback.answer("+1500")
        await asyncio.sleep(2)
    else:
        await callback.message.edit_text("‼ Задание уже выполнено", reply_markup=back_menu_kb())
        await callback.answer("Задание уже выполнено")
        await asyncio.sleep(3)

    # Получаем все задачи с ссылками из кэша и фильтруем
    all_tasks = task_cache.get('all_tasks', [])
    tasks = [
        task for task in all_tasks if not await DB.is_task_completed(user_id, task[0])
    ]

    if tasks:
        random.shuffle(tasks)
        chanelpage = 1
        tasks_on_page, total_pages = await generate_tasks_keyboard_chanel(tasks, chanelpage)
        keyboard = await generate_tasks_keyboard_chanel(tasks_on_page, chanelpage, total_pages, bot)
        await callback.message.edit_text(
            "📢 <b>Задания на каналы:</b>\n\n🎢 Каналы в списке располагаются по количеству необходимых подписчиков\n\n⚡<i>Запрещено отписываться от канала раньше чем через 7 дней, в случае нарушения возможен штраф!</i>",
            reply_markup=keyboard)
    else:
        await callback.message.edit_text("На данный момент доступных заданий нет, возвращайся позже 😉",
                                         reply_markup=back_work_menu_kb())
        
    if not await DB.is_task_completed(user_id, task[0]):
        await DB.update_task_amount(task_id)
        await DB.add_completed_task(user_id, task_id, target_id, 1500, task[1], status=1)


class ChanelReport(StatesGroup):
    desc = State()

@client.callback_query(F.data.startswith('chanelreport_'))
async def request_chanel_report_description(callback: types.CallbackQuery, bot: Bot, state: FSMContext):
    await callback.answer()
    task_id = int(callback.data.split('_')[1])
    task = await DB.get_task_by_id(task_id)
    target_id = task[2]

    # Сохраняем task_id в состояние пользователя
    await state.update_data(task_id=task_id, target_id=target_id)

    # Запрашиваем описание проблемы
    await callback.message.edit_text("⚠️ Пожалуйста, опишите проблему с этим каналом. Например, канал не соответствует правилам или содержит недопустимый контент.")
    await state.set_state(ChanelReport.desc)

@client.message(ChanelReport.desc)
async def save_chanel_report_description(message: types.Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    description = message.text

    # Получаем task_id и target_id из состояния
    data = await state.get_data()
    task_id = data.get("task_id")
    target_id = data.get("target_id")

    if task_id and target_id:
        # Добавляем репорт в базу данных
        await DB.add_report(task_id=task_id, chat_id=target_id, user_id=user_id, description=description)

        # Отправляем подтверждение
        chat = await bot.get_chat(target_id)
        await message.answer(f'⚠️ Жалоба на канал <b>{chat.title}</b> отправлена!')
        await asyncio.sleep(1)

        # Возвращаем пользователя к списку заданий
        all_tasks = task_cache.get('all_tasks', [])
        tasks = [task for task in all_tasks if not await DB.is_task_completed(user_id, task[0])]

        if tasks:
            random.shuffle(tasks)
            chanelpage = 1
            tasks_on_page, total_pages = await generate_tasks_keyboard_chanel(tasks, chanelpage)
            keyboard = await generate_tasks_keyboard_chanel(tasks_on_page, chanelpage, total_pages, bot)
            await message.answer(
                "📢 <b>Задания на каналы:</b>\n\n🎢 Каналы в списке располагаются по количеству необходимых подписчиков\n\n⚡<i>Запрещено отписываться от канала раньше чем через 7 дней, в случае нарушения возможен штраф!</i>",
                reply_markup=keyboard)
        else:
            await message.answer("На данный момент доступных заданий нет, возвращайся позже 😉",
                                 reply_markup=back_work_menu_kb())
    else:
        await message.answer("Ошибка: не удалось получить данные о задании.")

    # Сбрасываем состояние
    await state.clear()


@client.callback_query(F.data == 'work_chat')
async def tasksschat_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id

    try:
        # Получаем все задачи с ссылками из кэша и фильтруем
        all_tasks = task_cache_chat.get('all_tasks', [])
        tasks = [
            task for task in all_tasks if not await DB.is_task_completed(user_id, task[0])
        ]

        if tasks:
            random.shuffle(tasks)
            keyboard = await generate_tasks_keyboard_chat(tasks, bot)

            await callback.message.edit_text(
                "👤 <b>Задания на чаты:</b>\n\n🎢 Чаты в списке располагаются по количеству необходимых участников\n\n⚡<i>Запрещено покидать чат раньше чем через 7 дней, в случае нарушения возможен штраф!</i>",
                reply_markup=keyboard
            )
        else:
            await callback.message.edit_text(
                "На данный момент доступных заданий нет, возвращайся позже 😉",
                reply_markup=back_work_menu_kb()
            )
    except Exception as e:
        print(f"Ошибка в tasksschat_handler: {e}")
        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(text="🔄 Обновить", callback_data="work_chat"))
        await callback.message.edit_text(
                "Произошла ошибка при загрузке заданий. Попробуйте обновить страницу.",
            reply_markup=builder.as_markup()            )



# Функция для генерации клавиатуры с заданиями
async def generate_tasks_keyboard_chat(tasks, bot):
    builder = InlineKeyboardBuilder()

    # Выводим задания (по 5 на страницу)
    for task in tasks[:5]:  # Ограничиваем количество заданий на одной странице
        chat_id = task[2]
        chat_title = task[5]

        button_text = f"{chat_title} | +1500"
        builder.row(types.InlineKeyboardButton(text=button_text, callback_data=f"chattask_{task[0]}"))

    # Кнопка "Назад"
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="work_menu"))

    # Кнопка "Обновить"
    builder.row(types.InlineKeyboardButton(text="🔄 Обновить", callback_data="work_chat"))

    return builder.as_markup()


async def check_admin_and_get_invite_link_chat(bot, target_id):
    try:
        ChatFullInfo = await bot.get_chat(target_id)
        invite_link = ChatFullInfo.invite_link
        return invite_link
    except Exception as e:
        print(e)
        return False


@client.callback_query(lambda c: c.data.startswith("chattask_"))
async def task_detail_handler(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    task_id = int(callback.data.split('_')[1])
    task = await DB.get_task_by_id(task_id)

    amount = task[3]

    invite_link = await check_admin_and_get_invite_link_chat(bot, task[2])
    chat_id = task[2]
    chat = await bot.get_chat(chat_id)
    task_info = f"""
👤 {chat.title} | <i>{amount}</i>
<i>Вступите в чат и нажмите кнопку -</i> <b>Проверить</b> 🔄️

{invite_link}    
    """
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(text="🔙", callback_data="work_chat"))
    builder.add(types.InlineKeyboardButton(text="Проверить 🔄️", callback_data=f"chatcheck_{task_id}"))
    builder.add(types.InlineKeyboardButton(text="Репорт ⚠️", callback_data=f"chatreport_{task_id}"))
    await callback.message.edit_text(task_info, reply_markup=builder.as_markup())


@client.callback_query(F.data.startswith('chatcheck_'))
async def check_subscription_chat(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    task_id = int(callback.data.split('_')[1])
    task = await DB.get_task_by_id(task_id)
    if task is None:
        await callback.message.edit_text("❗ Задание не найдено или уже выполнено", reply_markup=back_menu_kb())
        await asyncio.sleep(1)
        return

    user_id = callback.from_user.id
    target_id = task[2]
    invite_link = await check_admin_and_get_invite_link_chat(bot, task[2])

    # Проверяем, подписан ли пользователь на чат
    try:
        bot_member = await bot.get_chat_member(target_id, callback.message.chat.id)
        if bot_member.status != "member":
            builder = InlineKeyboardBuilder()
            builder.add(types.InlineKeyboardButton(text="🔙 Назад", callback_data="work_chat"))
            builder.add(types.InlineKeyboardButton(text="Проверить 🔄️", callback_data=f"chatcheck_{task_id}"))
            await callback.message.edit_text(
                f"🚩 Пожалуйста, <b>вступите в чат</b> по ссылке {invite_link} и повторите попытку",
                reply_markup=builder.as_markup())
            return
    except Exception as e:
        print(f"Ошибка при проверке подписки: {e}")
        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(text="🔙", callback_data="work_chat"))
        builder.add(types.InlineKeyboardButton(text="Проверить 🔄️", callback_data=f"chatcheck_{task_id}"))

        await callback.message.edit_text(
            f"🚩 Пожалуйста, <b>вступите в чат</b> по ссылке {invite_link} и повторите попытку",
            reply_markup=builder.as_markup())
        return

    if not await DB.is_task_completed(user_id, task[0]):
        # Обновляем задание (вычитаем amount на 1)
        await DB.update_task_amount(task_id)
        await DB.add_completed_task(user_id, task_id, target_id, 1500, task[1], status=1)
        await DB.add_balance(amount=1500, user_id=user_id)

        # Проверяем, нужно ли удалить задание
        updated_task = await DB.get_task_by_id(task_id)
        if updated_task[3] == 0:
            delete_task = await DB.get_task_by_id(task_id)
            creator_id = delete_task[1]
            await DB.delete_task(task_id)
            await bot.send_message(creator_id, f"🎉 Одно из ваших заданий было успешно выполнено",
                                   reply_markup=back_menu_kb())

        await DB.increment_all_subs_group()
        await DB.increment_all_taasks()
        await callback.message.edit_text("✅")
        await callback.answer("+1500")
        await asyncio.sleep(2)
    else:
        await callback.message.edit_text("‼ Вы уже выполнили это задание", reply_markup=back_menu_kb())
        await asyncio.sleep(3)

    # Обновляем список заданий после выполнения
    all_tasks = task_cache_chat.get('all_tasks', [])
    tasks = [
        task for task in all_tasks if not await DB.is_task_completed(user_id, task[0])
    ]

    if tasks:
        random.shuffle(tasks)
        keyboard = await generate_tasks_keyboard_chat(tasks, bot)
        await callback.message.edit_text(
            "👤 <b>Задания на чаты:</b>\n\n🎢 Чаты в списке располагаются по количеству необходимых участников\n\n⚡<i>Запрещено покидать чат раньше чем через 7 дней, в случае нарушения возможен штраф!</i>",
            reply_markup=keyboard
        )
    else:
        await callback.message.edit_text(
            "На данный момент доступных заданий нет, возвращайся позже 😉",
            reply_markup=back_work_menu_kb()
        )


class ChatReport(StatesGroup):
    desc = State()

@client.callback_query(F.data.startswith('chatreport_'))
async def request_chat_report_description(callback: types.CallbackQuery, bot: Bot, state: FSMContext):
    await callback.answer()
    task_id = int(callback.data.split('_')[1])
    task = await DB.get_task_by_id(task_id)
    target_id = task[2]

    # Сохраняем task_id в состояние пользователя
    await state.update_data(task_id=task_id, target_id=target_id)

    # Запрашиваем описание проблемы
    await callback.message.edit_text("⚠️ Пожалуйста, опишите проблему с этим чатом. Например, чат не соответствует правилам или содержит недопустимый контент.")
    await state.set_state(ChatReport.desc)

@client.message(ChatReport.desc)
async def save_chat_report_description(message: types.Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    description = message.text

    # Получаем task_id и target_id из состояния
    data = await state.get_data()
    task_id = data.get("task_id")
    target_id = data.get("target_id")

    if task_id and target_id:
        # Добавляем репорт в базу данных
        await DB.add_report(task_id=task_id, chat_id=target_id, user_id=user_id, description=description)

        # Отправляем подтверждение
        chat = await bot.get_chat(target_id)
        await message.answer(f'⚠️ Жалоба на чат <b>{chat.title}</b> отправлена!')
        await asyncio.sleep(1)

        # Возвращаем пользователя к списку заданий
        all_tasks = task_cache_chat.get('all_tasks', [])
        tasks = [task for task in all_tasks if not await DB.is_task_completed(user_id, task[0])]

        if tasks:
            random.shuffle(tasks)
            chatpage = 1
            keyboard = await generate_tasks_keyboard_chat(tasks, bot)
            await message.answer(
                "👤 <b>Задания на чаты:</b>\n\n🎢 Чаты в списке располагаются по количеству необходимых участников\n\n⚡<i>Запрещено покидать чат раньше чем через 7 дней, в случае нарушения возможен штраф!</i>",
                reply_markup=keyboard)
        else:
            await message.answer("На данный момент доступных заданий нет, возвращайся позже 😉",
                                 reply_markup=back_work_menu_kb())
    else:
        await message.answer("Ошибка: не удалось получить данные о задании.")

    # Сбрасываем состояние
    await state.clear()

@client.callback_query(F.data == 'work_post')
async def works_post_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id

    try:
        # Получаем все задания на посты
        all_tasks = await DB.select_post_tasks()
        print(f"Все задания: {all_tasks}")  # Отладочное сообщение

        if not all_tasks:
            builder = InlineKeyboardBuilder()
            builder.add(types.InlineKeyboardButton(text="🔄 Обновить", callback_data="work_post"))
            await callback.message.edit_text(
                "На данный момент заданий на посты нет, возвращайся позже 😉",
                reply_markup=builder.as_markup()
            )
            return

        # Фильтруем задания, которые пользователь ещё не выполнил
        available_tasks = [task for task in all_tasks if not await DB.is_task_completed(user_id, task[0])]
        print(f"Доступные задания: {available_tasks}")  # Отладочное сообщение

        if not available_tasks:
            await callback.message.edit_text(
                "На данный момент заданий на посты нет, возвращайся позже 😉",
                reply_markup=back_menu_kb()
            )
            return

        # Отображаем первое доступное задание
        task = available_tasks[0]
        task_id, target_id, amount = task[0], task[2], task[3]
        print(f"Задание: task_id={task_id}, target_id={target_id}, amount={amount}")  # Отладочное сообщение

        # Проверяем формат target_id
        try:
            chat_id, message_id = map(int, target_id.split(":"))
            print(f"Chat ID: {chat_id}, Message ID: {message_id}")  # Отладочное сообщение
        except ValueError as e:
            print(f"Ошибка в формате target_id: {e}")
            await callback.message.answer("Ошибка: некорректный формат задания.")
            return

        # Формируем клавиатуру
        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(text="🔙 Назад", callback_data="work_menu"))
        builder.add(types.InlineKeyboardButton(text="🔄 Обновить", callback_data="work_post"))
        builder.add(types.InlineKeyboardButton(text="Репорт ⚠️", callback_data=f"postreport_{task_id}"))

        # Пересылаем пост пользователю
        await bot.forward_message(chat_id=user_id, from_chat_id=chat_id, message_id=message_id)
        await callback.message.answer_sticker(
            'CAACAgIAAxkBAAENFeZnLS0EwvRiToR0f5njwCdjbSmWWwACTgEAAhZCawpt1RThO2pwgjYE'
        )
        await asyncio.sleep(3)

        # Отправляем сообщение с кнопками
        await callback.message.answer(
            f"👀 <b>Просмотрели пост? +250 MITcoin</b>\n\nНажмите кнопку для просмотра следующего поста",
            reply_markup=builder.as_markup()
        )

        # Обновляем количество выполнений задания
        await DB.update_task_amount(task_id)
        updated_task = await DB.get_task_by_id(task_id)

        # Добавляем задание в список выполненных
        await DB.add_completed_task(user_id, task_id, target_id, 250, task[1], status=0)
        await DB.add_balance(amount=250, user_id=user_id)

        # Если задание выполнено полностью, удаляем его
        if updated_task[3] == 0:
            delete_task = await DB.get_task_by_id(task_id)
            creator_id = delete_task[1]
            await DB.delete_task(task_id)
            await DB.increment_all_see()
            await DB.increment_all_taasks()
            await bot.send_message(
                creator_id,
                f"🎉 Одно из ваших заданий на пост было успешно выполнено!",
                reply_markup=back_menu_kb()
            )

    except Exception as e:
        print(f"Ошибка в works_post_handler: {e}")
        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(text="🔄 Обновить", callback_data="work_post"))
        await callback.message.edit_text(
            "Произошла ошибка при загрузке заданий. Попробуйте обновить страницу.",
            reply_markup=builder.as_markup()
        )
        

class PostReport(StatesGroup):
    desc = State()

@client.callback_query(F.data.startswith('postreport_'))
async def request_post_report_description(callback: types.CallbackQuery, bot: Bot, state: FSMContext):
    task_id = int(callback.data.split('_')[1])
    await callback.answer()

    # Сохраняем task_id в состояние пользователя
    await state.update_data(task_id=task_id)

    # Запрашиваем описание проблемы
    await callback.message.edit_text(
        "⚠️ Пожалуйста, опишите проблему с этим постом. Например, пост не соответствует правилам или содержит недопустимый контент."
    )
    await state.set_state(PostReport.desc)

@client.message(PostReport.desc)
async def save_post_report_description(message: types.Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    description = message.text

    # Получаем task_id из состояния
    data = await state.get_data()
    task_id = data.get("task_id")

    if task_id:
        task = await DB.get_task_by_id(task_id)
        if task:
            target_id = task[2]

            # Добавляем репорт в базу данных
            await DB.add_report(task_id=task_id, chat_id=target_id, user_id=user_id, description=description)

            # Отправляем подтверждение
            await message.answer("⚠️ Жалоба на пост отправлена!")
            await asyncio.sleep(1)

            # Возвращаем пользователя к списку заданий
            all_tasks = await DB.select_post_tasks()
            if all_tasks:
                available_tasks = [task for task in all_tasks if not await DB.is_task_completed(user_id, task[0])]
                if not available_tasks:
                    await message.answer("На данный момент доступных заданий нет, возвращайся позже 😉",
                                         reply_markup=back_work_menu_kb())
                    return

                for task in available_tasks:
                    task_id, target_id, amount = task[0], task[2], task[3]
                    chat_id, message_id = map(int, target_id.split(":"))
                    try:
                        builder = InlineKeyboardBuilder()
                        builder.add(types.InlineKeyboardButton(text="🔙", callback_data="work_menu"))
                        builder.add(types.InlineKeyboardButton(text="Дальше ⏭️", callback_data=f"work_post"))
                        builder.add(types.InlineKeyboardButton(text="Репорт ⚠️", callback_data=f"postreport_{task_id}"))
                        await bot.forward_message(chat_id=user_id, from_chat_id=chat_id, message_id=message_id)
                        await message.answer_sticker(
                            'CAACAgIAAxkBAAENFeZnLS0EwvRiToR0f5njwCdjbSmWWwACTgEAAhZCawpt1RThO2pwgjYE')
                        await asyncio.sleep(3)

                        await message.answer(
                            f"👀 <b>Просмотрели пост? +250 MITcoin</b>\n\nНажмите кнопку для просмотра следующего поста",
                            reply_markup=builder.as_markup())

                        await DB.update_task_amount(task_id)
                        updated_task = await DB.get_task_by_id(task_id)

                        await DB.add_completed_task(user_id, task_id, target_id, 250, task[1], status=0)
                        await DB.add_balance(amount=250, user_id=user_id)

                        if updated_task[3] == 0:
                            delete_task = await DB.get_task_by_id(task_id)
                            creator_id = delete_task[1]
                            await DB.delete_task(task_id)
                            await DB.increment_all_see()
                            await DB.increment_all_taasks()
                            await bot.send_message(creator_id, f"🎉 Одно из ваших заданий на пост было успешно выполнено!",
                                                   reply_markup=back_menu_kb())

                        return
                    except Exception as e:
                        print(f"Ошибка: {e}")
                        continue

                # Если все задания были пропущены
                await message.answer("На данный момент доступных заданий нет, возвращайся позже 😉",
                                     reply_markup=back_work_menu_kb())
            else:
                await message.answer("На данный момент заданий на посты нет, возвращайся позже 😉",
                                     reply_markup=back_work_menu_kb())
        else:
            await message.answer("Задание не найдено.")
    else:
        await message.answer("Ошибка: не удалось получить данные о задании.")

    # Сбрасываем состояние
    await state.clear()

# Назначим текстовые представления для типов заданий
TASK_TYPES = {
    1: '📢 Канал',
    2: '👥 Чат',
    3: '👀 Пост'
}


async def generate_tasks_keyboard(tasks, page, total_pages):
    builder = InlineKeyboardBuilder()

    # Выводим задания на текущей странице (по 5 на страницу)
    for task in tasks:
        task_type = TASK_TYPES.get(task[4], 'Неизвестно')
        amount = task[3]  
        button_text = f"{task_type} | {amount}"
        # Каждая кнопка в новой строке
        builder.row(types.InlineKeyboardButton(text=button_text, callback_data=f"task_{task[0]}"))

    # Кнопка "Назад"
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="profile"))

    # Кнопки пагинации
    pagination = []
    if page > 1:
        pagination.append(types.InlineKeyboardButton(text="⬅️", callback_data=f"page_{page - 1}"))
    pagination.append(types.InlineKeyboardButton(text=str(page), callback_data="current_page"))
    if page < total_pages:
        pagination.append(types.InlineKeyboardButton(text="➡️", callback_data=f"page_{page + 1}"))

    builder.row(*pagination)  # Кнопки пагинации в одну строку

    return builder.as_markup()

async def generate_tasks_keyboard2(tasks, page, total_pages, bot):
    builder = InlineKeyboardBuilder()

    # Выводим задания на текущей странице (по 5 на страницу)
    for task in tasks:
        # Распаковываем данные задачи
        task_id, user_id, chat_id, amount, task_type_id, _ = task  # Шестой элемент игнорируем

        # Получаем тип задачи
        task_type = TASK_TYPES.get(task_type_id, 'Неизвестно')

        # Получаем информацию о канале/чате для каждой задачи
        try:
            chat = await bot.get_chat(chat_id)  # Получаем информацию о канале/чате
            chat_name = chat.title  # Извлекаем название канала/чата
        except Exception as e:
            print(f"Ошибка при получении информации о канале: {e}")
            chat_name = "Неизвестный канал"  # Используем заглушку в случае ошибки

        # Формируем текст кнопки
        button_text = f"{task_type} | {chat_name} | {amount}"
        
        # Каждая кнопка в новой строке
        builder.row(types.InlineKeyboardButton(text=button_text, callback_data=f"task_{task_id}"))

    # Кнопка "Назад"
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="profile"))

    # Кнопки пагинации
    pagination = []
    if page > 1:
        pagination.append(types.InlineKeyboardButton(text="⬅️", callback_data=f"page_{page - 1}"))
    pagination.append(types.InlineKeyboardButton(text=str(page), callback_data="current_page"))
    if page < total_pages:
        pagination.append(types.InlineKeyboardButton(text="➡️", callback_data=f"page_{page + 1}"))

    builder.row(*pagination)  # Кнопки пагинации в одну строку

    return builder.as_markup()

# Метод для получения страницы с заданиями (пагинация)
def paginate_tasks(tasks, page=1, per_page=5):
    total_pages = (len(tasks) + per_page - 1) // per_page  # Вычисление общего количества страниц
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    tasks_on_page = tasks[start_idx:end_idx]
    return tasks_on_page, total_pages


@client.callback_query(F.data == 'my_works')
async def taskss_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    tasks = await DB.get_tasks_by_user(user_id)  # Получаем задачи пользователя
    print(tasks)  # Проверяем данные

    # Начинаем с первой страницы
    page = 1
    tasks_on_page, total_pages = paginate_tasks(tasks, page)

    # Генерируем инлайн кнопки
    keyboard = await generate_tasks_keyboard2(tasks_on_page, page, total_pages, bot)

    await callback.message.edit_text("💼 <b>Ваши задания:</b>", reply_markup=keyboard)


@client.callback_query(lambda c: c.data.startswith("page_"))
async def change_page_handler(callback: types.CallbackQuery, bot: Bot):
    # Получаем номер страницы из callback_data
    page = int(callback.data.split('_')[1])
    
    # Получаем ID пользователя
    user_id = callback.from_user.id
    
    # Получаем задачи пользователя
    tasks = await DB.get_tasks_by_user(user_id)
    
    # Получаем задания на нужной странице
    tasks_on_page, total_pages = paginate_tasks(tasks, page)

    # Генерируем инлайн кнопки
    keyboard = await generate_tasks_keyboard2(tasks_on_page, page, total_pages, bot)

    # Обновляем сообщение с новыми кнопками
    await callback.message.edit_text("💼 <b>Ваши задания:</b>", reply_markup=keyboard)


# Функция для проверки прав админа и генерации ссылки
async def check_admin_and_get_invite_link(bot, target_id):
    try:
        chat_administrators = await bot.get_chat_administrators(target_id)
        # Проверяем, является ли бот администратором
        for admin in chat_administrators:
            if admin.user.id == bot.id:
                # Если бот админ, генерируем ссылку-приглашение
                try:
                    ChatFullInfo = await bot.get_chat(target_id)
                    invite_link = ChatFullInfo.invite_link
                    return invite_link

                except Exception as e:
                    print(f'ошибка получения инвайта для {target_id}, ошибка - {e}')
                    return "😑 Предоставьте боту права администратора, иначе задание выполняться не будет"
        # Если бот не админ
        return "😑 Предоставьте боту права администратора, иначе задание выполняться не будет"
    except:
        return "😑 Предоставьте боту права администратора, иначе задание выполняться не будет"


@client.callback_query(lambda c: c.data.startswith("task_"))
async def task_detail_handler(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    task_id = int(callback.data.split('_')[1])
    task = await DB.get_task_by_id(task_id)

    # Определяем тип задачи
    task_type = TASK_TYPES.get(task[4], 'Неизвестно')
    amount = task[3]
    max_amount = task[5]
    if amount is None:
        amount = 1
    # Вычисляем стоимость задания
    price_per_unit = {1: 1500, 2: 1500, 3: 300}
    cost = amount * price_per_unit.get(task[4], 0)

    # Если это канал или чат, проверяем права администратора и создаем ссылку
    invite_link = ""
    if task[4] in [1, 2]:  # Канал или чат
        invite_link = await check_admin_and_get_invite_link(bot, task[2])
        chat_id = task[2]
        try:
            chat = await bot.get_chat(chat_id)
            chat_title = chat.title
        except:
            chat_title = "⚠️ Бот был удален с канала или не является администратором ⚠️"
        task_info = f"""
<b>{task_type}</b>: 
{chat_title}
🔋Активаций: {max_amount}
🧮 Активаций осталось: {amount}
💰 Стоимость: {cost} MITcoin 

{invite_link}    
            """
        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(text="🔙 Назад", callback_data="my_works"))
        builder.add(types.InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_{task_id}"))
        builder.add(types.InlineKeyboardButton(text="✏️Изменить количество выполнений", callback_data=f"edit_{task_id}"))
        builder.adjust(2, 1)
        await callback.message.edit_text(task_info, reply_markup=builder.as_markup())

    if task[4] in [3]:
        target_id = task[2]
        chat_id, message_id = map(int, target_id.split(":"))
        user_id = callback.from_user.id
        task_info = f"""
{task_type}

🧮 Количество: {amount}
💰 Стоимость: {cost} MITcoin 

{invite_link}    
            """
        await bot.forward_message(chat_id=user_id, from_chat_id=chat_id, message_id=message_id)
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="my_works"), types.InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_{task_id}"))
        # builder.add(types.InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_{task_id}"))
        builder.row(types.InlineKeyboardButton(text="✏️Изменить количество выполнений", callback_data=f"edit_{task_id}"))
        await callback.message.edit_text(task_info, reply_markup=builder.as_markup())


@client.callback_query(lambda c: c.data.startswith("delete_"))
async def delete_task_handler(callback: types.CallbackQuery):
    task_id = int(callback.data.split('_')[1])
    task = await DB.get_task_by_id(task_id)
    amount = task[3] 
    if amount is None:
        amount = 1
    price_per_unit = {1: 1500, 2: 1500, 3: 300}
    cost = amount * price_per_unit.get(task[4], 0)
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    balance = user['balance']
    new_balance = balance + cost

    # Удаляем задачу из базы данных
    await DB.delete_task(task_id)
    await DB.update_balance(user_id, balance=new_balance)
    await callback.message.edit_text("Задание удалено!")

    # После удаления возвращаем пользователя к его заданиям
    user_id = callback.from_user.id
    tasks = await DB.get_tasks_by_user(user_id)
    page = 1
    tasks_on_page, total_pages = paginate_tasks(tasks, page)
    keyboard = await generate_tasks_keyboard(tasks_on_page, page, total_pages)

    await callback.message.edit_text("💼 <b>Ваши задания:</b>", reply_markup=keyboard)

class EditTaskState(StatesGroup):
    waiting_for_amount = State()  # Состояние ожидания ввода нового количества

@client.callback_query(lambda c: c.data.startswith("edit_"))
async def edit_task_handler(callback: types.CallbackQuery, state: FSMContext):
    # Получаем ID задания из callback-запроса
    task_id = int(callback.data.split('_')[1])
    
    # Получаем задачу из базы данных
    task = await DB.get_task_by_id(task_id)
    if not task:
        await callback.message.edit_text("Задание не найдено!")
        return

    # Сохраняем ID задания в состоянии FSM
    await state.update_data(task_id=task_id)

    # Запрашиваем у пользователя новое количество выполнений
    await callback.message.edit_text("✏️ Введите новое количество выполнений для задания:")
    
    # Переводим бота в состояние ожидания ввода нового количества
    await state.set_state(EditTaskState.waiting_for_amount)

@client.message(EditTaskState.waiting_for_amount)
async def process_amount_input(message: types.Message, state: FSMContext):
    try:
        new_amount = int(message.text)
        if new_amount <= 0:
            await message.answer("❌ Количество выполнений должно быть больше 0.")
            return

        balance = await DB.get_user_balance(message.from_user.id)

        if new_amount > balance // 1500:
            await message.reply(f"""
❌ <b>У вас недостаточно средств для создания задания.</b>
Ваш баланс: {balance}
Требуется: {new_amount * 1500}
Не хватает: { (new_amount * 1500) - balance}""", reply_markup=types.ReplyKeyboardRemove()) # Удаляем клавиатуру
            return

        data = await state.get_data()
        task_id = data.get("task_id")
        await DB.update_task_amount2(task_id, new_amount)

        user_id = message.from_user.id
        tasks = await DB.get_tasks_by_user(user_id)
        page = 1
        tasks_on_page, total_pages = paginate_tasks(tasks, page)
        keyboard = await generate_tasks_keyboard(tasks_on_page, page, total_pages)

        # Вместо message.answer используем message.edit_text
        await message.reply("✅ Количество выполнений успешно обновлено!\n💼 <b>Ваши задания:</b>", reply_markup=keyboard)


    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число.")
        await state.clear()
    except Exception as e:
        await message.reply(f"Произошла ошибка: {e}") #Обработка других ошибок



@client.callback_query(F.data == 'chanel_pr_button')
async def pr_chanel_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    balance = user['balance']
    if balance is None:
        balance = 0
    maxcount = balance // 1500
    await callback.message.edit_text(f'''
📢 Реклама канала

💹 1500 MITcoin = 1 подписчик

Баланс - {balance}; Всего вы можете купить {maxcount} подписчиков

<b>Сколько нужно подписчиков</b>❓

<em>Что бы создать задание на вашем балансе должно быть не менее 1500 MitCoin</em>
    ''', reply_markup=pr_menu_canc())
    await state.set_state(create_tasks.chanel_task_create)


@client.message(create_tasks.chanel_task_create)
async def pr_chanel2(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await DB.select_user(user_id)
    balance = user['balance']
    if balance is None:
        balance = 0
    try:
        uscount = int(message.text.strip())
        if uscount >= 1:
            price = 1500 * uscount
            await state.update_data(uscount=uscount, price=price, balance=balance)
            if balance >= price:
                builder = InlineKeyboardBuilder()
                builder.add(types.InlineKeyboardButton(text="✅ Продолжить", callback_data="pr_chanel_confirm"))
                builder.add(types.InlineKeyboardButton(text="❌ Назад", callback_data="pr_menu_cancel"))
                await message.answer(
                    f'👥 <b>Количество - {uscount}</b>\n💰<b> Стоимость - {price} MITcoin</b>\n\n<em>Нажмите кнопку <b>Продолжить</b> или введите другое число...</em>',
                    reply_markup=builder.as_markup())
            else:
                builder = InlineKeyboardBuilder()
                builder.add(types.InlineKeyboardButton(text="Пополнить баланс", callback_data="cancel_all"))
                builder.add(types.InlineKeyboardButton(text="❌ Назад", callback_data="pr_menu_cancel"))
                await message.answer(
                    f'😢 <b>Недостаточно средств на балансе</b> Ваш баланс - {balance} MITcoin\n<em>Пополните баланс или измените желаемое количество подписок...</em>',
                    reply_markup=builder.as_markup())
        else:
            await message.answer('<b>❗Минимальная покупка от 1 подписчика!</b>\nВведи корректное число...',
                                 reply_markup=pr_menu_canc())
    except ValueError:
        await message.answer('<b>Ошибка ввода</b>\nПопробуй ввести целое число...', reply_markup=pr_menu_canc())


@client.callback_query(F.data == 'pr_chanel_confirm')
async def pr_chanel3(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uscount = data.get('uscount')
    price = data.get('price')
    balance = data.get('balance')
    await state.clear()
    bot_username = (await bot.get_me()).username
    invite_link = f"http://t.me/{bot_username}?startchannel&admin=invite_users+manage_chat"
    add_button = InlineKeyboardButton(text="➕ Добавить бота в канал", url=invite_link)
    add_button1 = InlineKeyboardButton(text="❌ Отмена", callback_data='pr_menu_cancel')
    # Создаем клавиатуру и добавляем в нее кнопку 
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button], [add_button1]])
    await callback.message.edit_text(f'''
👾 Теперь необходимо добавить бота в ваш канал и предоставить ему права администратора, для этого...

<em>Зайдите в профиль бота -> "Добавить в группу или канал" -> предоставьте боту права админа -> перешлите сюда ОДНО любое сообщение с канала</em>
<b>ИЛИ</b>
Воспользуйся кнопкой 👇
    ''', reply_markup=keyboard)
    await state.set_state(create_tasks.chanel_task_create2)
    await state.update_data(uscount=uscount, price=price, balance=balance)


# Создаем глобальную блокировку
task_creation_lock = asyncio.Lock()


@client.message(create_tasks.chanel_task_create2)
async def pr_chanel4(message: types.Message, state: FSMContext, bot: Bot):
    async with task_creation_lock:  # Устанавливаем блокировку
        data = await state.get_data()
        user_id = message.from_user.id
        amount = data.get('uscount')
        price = data.get('price')
        balance = data.get('balance')
        if amount is None:
            amount = 1
        if balance is None:
            user = await DB.select_user(user_id)
            balance = user['balance']
        if price is None:
            price = 1500

        new_balance = balance - price
        # Проверка, не было ли уже создано задание в текущей сессии
        if data.get('task_created'):
            await message.answer("Задание уже было создано. Пожалуйста, не пересылайте несколько сообщений.",
                                 reply_markup=pr_menu_canc())
            return

        # Проверка на пересланное сообщение из канала
        if not message.forward_from_chat:
            await message.answer("Пожалуйста, перешлите сообщение именно из канала.", reply_markup=pr_menu_canc())
            return

        channel_id = message.forward_from_chat.id
        bot_info = await bot.get_me()

        try:
            bot_member = await bot.get_chat_member(chat_id=channel_id, user_id=bot_info.id)
        except Exception:
            await message.answer("😢 Не удалось получить информацию о канале. Убедитесь, что бот добавлен в канал...",
                                 reply_markup=pr_menu_canc())
            return

        if bot_member.status != ChatMemberStatus.ADMINISTRATOR or not bot_member.can_invite_users:
            await message.answer("🫤 Пожалуйста, предоставьте боту права администратора.", reply_markup=pr_menu_canc())
            return

        # Все условия выполнены: сохраняем ID канала, создаем задание, обновляем баланс и устанавливаем флаг
        await state.update_data(channel_id=channel_id)
        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_menu"))
        await message.answer(
            "🥳 Задание создано! Оно будет размещено в разделе <b>Заработать</b>\n\nКогда задание будет выполнено - Вы получите уведомление 😉",
            reply_markup=builder.as_markup()
        )

        task_type = 1

        await DB.update_balance(user_id, balance=new_balance)
        await DB.add_task(user_id=user_id, target_id=channel_id, amount=amount, task_type=task_type)

        # Устанавливаем флаг, что задание уже создано, чтобы избежать повторов
        await state.update_data(task_created=True)
        await state.clear()


@client.callback_query(F.data == 'chat_pr_button')
async def pr_chat_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    balance = user['balance']
    if balance is None:
        balance = 0
    maxcount = balance // 1500
    await callback.message.edit_text(f'''
👥 Реклама чата

💵 1500 MIT coin = 1 участник

Баланс - <b>{balance}</b>; Всего вы можете купить <b>{maxcount}</b> участников

<b>Сколько нужно участников</b>❓

<em>Что бы создать задание на вашем балансе должно быть не менее 1500 MITcoin</em>
    ''', reply_markup=pr_menu_canc())
    await state.set_state(create_tasks.chat_task_create)


@client.message(create_tasks.chat_task_create)
async def pr_chat2(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await DB.select_user(user_id)
    balance = user['balance']
    if balance is None:
        balance = 0
    try:
        uscount = int(message.text.strip())
        if uscount >= 1:
            price = 1500 * uscount
            await state.update_data(uscount=uscount, price=price, balance=balance)
            if balance >= price:
                builder = InlineKeyboardBuilder()
                builder.add(types.InlineKeyboardButton(text="✅ Продолжить", callback_data="pr_chat_confirm"))
                builder.add(types.InlineKeyboardButton(text="❌ Назад", callback_data="pr_menu_cancel"))
                await message.answer(
                    f'👥 <b>Количество - {uscount}</b>\n💰<b> Стоимость - {price} MITcoin</b>\n\n<em>Нажмите кнопку <b>Продолжить</b> или введите другое число...</em>',
                    reply_markup=builder.as_markup())
            else:
                builder = InlineKeyboardBuilder()
                builder.add(types.InlineKeyboardButton(text="Пополнить баланс", callback_data="cancel_all"))
                builder.add(types.InlineKeyboardButton(text="❌ Назад", callback_data="pr_menu_cancel"))
                await message.answer(
                    f'😢 <b>Недостаточно средств на балансе</b> Ваш баланс - {balance} MITcoin\n<em>Пополните баланс или измените желаемое количество участников...</em>',
                    reply_markup=builder.as_markup())
        else:
            await message.answer('<b>❗Минимальная покупка от 1 участника!</b>\nВведи корректное число...',
                                 reply_markup=pr_menu_canc())
    except ValueError:
        await message.answer('<b>Ошибка ввода</b>\nПопробуй ввести целое число...', reply_markup=pr_menu_canc())


@client.callback_query(F.data == 'pr_chat_confirm')
async def pr_chat3(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uscount = data.get('uscount')
    price = data.get('price')
    balance = data.get('balance')
    await state.clear()
    bot_username = (await bot.get_me()).username
    invite_link = f"https://t.me/{bot_username}?startgroup&admin=invite_users+manage_chat"

    add_button = InlineKeyboardButton(text="➕ Добавить бота в чат", url=invite_link)
    add_button1 = InlineKeyboardButton(text="❌ Отмена", callback_data='pr_menu_cancel')
    # Создаем клавиатуру и добавляем в нее кнопку
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button], [add_button1]])
    await callback.message.edit_text(f'''
👾 Теперь необходимо добавить бота в ваш чат и предоставить ему права администратора, для этого...

<em>Добавьте бота в чат с помощью кнопки снизу -> предоставьте боту права админа -> перешлите в этот чат сообщение бота с кодом</em>
    ''', reply_markup=keyboard)
    await state.set_state(create_tasks.chat_task_create2)
    await state.update_data(uscount=uscount, price=price, balance=balance)


@client.message(create_tasks.chat_task_create2)
async def pr_chat4(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data.get('uscount')
    price = data.get('price')
    balance = data.get('balance')
    user_id = message.from_user.id
    bot_info = await bot.get_me()
    code = message.text.strip()
    code_chat_id, code_user_id = map(int, code.split(":"))
    print(f'chat_id-{code_chat_id}; code_user_id - {code_user_id}, real user id - {user_id}')
    if user_id == code_user_id:
        try:
            bot_member = await bot.get_chat_member(chat_id=code_chat_id, user_id=bot_info.id)
        except Exception as e:
            await message.answer(f"☹ Не удалось получить информацию о чате. Убедитесь, что бот добавлен в группу.",
                                 reply_markup=pr_menu_canc())
            return

            # Проверяем, является ли бот администратором
        if bot_member.status != ChatMemberStatus.ADMINISTRATOR:
            await message.answer(
                "☹ Бот не является администратором в этой группе. Пожалуйста, предоставьте боту права администратора и перешлите сообщение заново",
                reply_markup=pr_menu_canc())
            return

        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_menu"))
        
        await message.answer(
            "🥳 Задание создано! Оно будет размещено в разделе <b>Заработать</b>\n\nКогда задание будет выполнено - Вы получите уведомление 😉",
            reply_markup=builder.as_markup())
        user_id = message.from_user.id
        task_type = 2  # Чат
        new_balance = balance - price
        await DB.update_balance(user_id, balance=new_balance)
        await DB.add_task(user_id=user_id, target_id=code_chat_id, amount=amount, task_type=task_type)
        await bot.send_message(code_chat_id, '🥳 Настройка бота успешно завершена!')

        await state.clear()

    else:
        await message.answer("🫤 Проверьте, добавлен ли бот в группу и повторите попытку...",
                             reply_markup=pr_menu_canc())


@client.my_chat_member()
async def on_bot_added(event: ChatMemberUpdated, bot: Bot):
    # Проверяем, что бот был добавлен
    if event.new_chat_member.user.id == (await bot.get_me()).id:
        # Проверяем, что бот был добавлен в группу или супергруппу
        if event.chat.type in ['group', 'supergroup']:
            # Бота добавили в группу
            if event.new_chat_member.status in ['member', 'administrator']:
                chat_id = event.chat.id
                chat_title = event.chat.title
                inv_user_id = event.from_user.id

                # Отправляем сообщение в чат
                await bot.send_message(chat_id, "👋")
                await bot.send_message(chat_id, f"{chat_id}:{inv_user_id}")
                await bot.send_message(chat_id,
                                       "👆 Для завершения настройки перешлите <b>сообщение с кодом</b> в личные сообщения бота")
        # Игнорируем событие, если бот добавлен в канал
        elif event.chat.type == 'channel':
            return


@client.callback_query(F.data == 'post_pr_button')
async def pr_post_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    balance = user['balance']
    if balance is None:
        balance = 0
    maxcount = balance // 300
    await callback.message.edit_text(f'''
👀 Реклама поста

💵 300 MITcoin = 1 просмотр

Баланс - <b>{balance}</b>; Всего вы можете купить <b>{maxcount}</b> просмотров

<b>Сколько нужно просмотров</b>❓

<em>Что бы создать задание на вашем балансе должно быть не менее 300 MITcoin</em>
    ''', reply_markup=pr_menu_canc())
    await state.set_state(create_tasks.post_task_create)


@client.message(create_tasks.post_task_create)
async def pr_post2(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await DB.select_user(user_id)
    balance = user['balance']
    if balance is None:
        balance = 0
    try:
        uscount = int(message.text.strip())
        if uscount >= 1:
            price = 300 * uscount
            await state.update_data(uscount=uscount, price=price, balance=balance)
            if balance >= price:
                builder = InlineKeyboardBuilder()
                builder.add(types.InlineKeyboardButton(text="✅ Продолжить", callback_data="pr_post_confirm"))
                builder.add(types.InlineKeyboardButton(text="❌ Назад", callback_data="pr_menu_cancel"))
                await message.answer(
                    f'👀 <b>Количество - {uscount}</b>\n💰<b> Стоимость - {price} MITcoin</b>\n\n<em>Нажмите кнопку <b>Продолжить</b> или введите другое число...</em>',
                    reply_markup=builder.as_markup())
            else:
                builder = InlineKeyboardBuilder()
                builder.add(types.InlineKeyboardButton(text="Пополнить баланс", callback_data="cancel_all"))
                builder.add(types.InlineKeyboardButton(text="❌ Назад", callback_data="pr_menu_cancel"))
                await message.answer(
                    f'😢 <b>Недостаточно средств на балансе</b> Ваш баланс - {balance} MITcoin\n<em>Пополните баланс или измените желаемое количество просмотров...</em>',
                    reply_markup=builder.as_markup())
        else:
            await message.answer('<b>❗Минимальная покупка от 1 просмотра!</b>\nВведи корректное число...',
                                 reply_markup=pr_menu_canc())
    except ValueError:
        await message.answer('<b>Ошибка ввода</b>\nПопробуй ввести целое число...', reply_markup=pr_menu_canc())


@client.callback_query(F.data == 'pr_post_confirm')
async def pr_post3(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uscount = data.get('uscount')
    price = data.get('price')
    balance = data.get('balance')
    await state.clear()
    await callback.message.edit_text(f'''
👾 Теперь перешли ОДИН пост (‼ если пост с несколькими картинками - перешлите ОДНУ картинку, просмотры на пост будут засчитаны), который нужно рекламировать. Я жду...
    ''', reply_markup=pr_menu_canc())
    await state.set_state(create_tasks.post_task_create2)
    await state.update_data(uscount=uscount, price=price, balance=balance)


@client.message(create_tasks.post_task_create2)
async def pr_post4(message: types.Message, state: FSMContext, bot: Bot):
    async with task_creation_lock:  # Устанавливаем блокировку
        user_id = message.from_user.id
        data = await state.get_data()
        amount = data.get('uscount')
        price = data.get('price')
        balance = data.get('balance')
        if amount is None:
            amount = 1
        if balance is None:
            user = await DB.select_user(user_id)
            balance = user['balance']
        if price is None:
            price = 600

        if message.forward_from_chat:
            message_id = message.forward_from_message_id
            chat_id = message.forward_from_chat.id
            target_id_code = f'{chat_id}:{message_id}'

            try:
                await bot.forward_message(chat_id=user_id, from_chat_id=chat_id, message_id=message_id)
                task_type = 3  # пост
                new_balance = balance - price
                await DB.update_balance(user_id, balance=new_balance)
                await DB.add_task(user_id=user_id, target_id=target_id_code, amount=amount, task_type=task_type)

                builder = InlineKeyboardBuilder()
                builder.add(types.InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_menu"))
                await message.answer(
                    "🥳 Задание создано! Оно будет размещено в разделе <b>Заработать</b>\n\nКогда задание будет выполнено - Вы получите уведомление 😉",
                    reply_markup=builder.as_markup())
                await state.clear()
            except:
                bot_username = (await bot.get_me()).username
                invite_link = f"http://t.me/{bot_username}?startchannel&admin=invite_users+manage_chat"
                add_button = InlineKeyboardButton(text="➕ Добавить бота в канал", url=invite_link)
                add_button1 = InlineKeyboardButton(text="❌ Отмена", callback_data='pr_menu_cancel')
                # Создаем клавиатуру и добавляем в нее кнопку
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button], [add_button1]])
                await message.answer(
                    '😶 Добавьте бота в канал с правами админа при помощи кнопки снизу и перешлите пост заново...',
                    reply_markup=keyboard)


async def generate_tasks_keyboard_chating(chating_tasks, vchatingpage, total_pages, bot):
    builder = InlineKeyboardBuilder()

    # Выводим задания на текущей странице (по 5 на страницу)
    for task in chating_tasks:
        chat_id = task[1]
        chat = await bot.get_chat(chat_id)
        price = task[2]
        chat_title = chat.title
        button_text = f"{chat_title} | {price}"
        # Каждая кнопка в новой строке
        builder.row(types.InlineKeyboardButton(text=button_text, callback_data=f"vchatingtask_{task[0]}"))

    # Кнопка "Назад"
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="work_menu"))
    # Кнопки пагинации
    pagination = []
    if vchatingpage > 1:
        pagination.append(types.InlineKeyboardButton(text="⬅️", callback_data=f"vchatingpage_{vchatingpage - 1}"))
    pagination.append(types.InlineKeyboardButton(text=str(vchatingpage), callback_data="current_page"))
    if vchatingpage < total_pages:
        pagination.append(types.InlineKeyboardButton(text="➡️", callback_data=f"vchatingpage_{vchatingpage + 1}"))

    builder.row(*pagination)  # Кнопки пагинации в одну строку

    return builder.as_markup()


# Метод для получения страницы с заданиями (пагинация)
async def paginate_tasks_chating(tasks, vchatingpage=1, per_page=5):
    total_pages = (len(tasks) + per_page - 1) // per_page  # Вычисление общего количества страниц
    start_idx = (vchatingpage - 1) * per_page
    end_idx = start_idx + per_page
    tasks_on_page = tasks[start_idx:end_idx]
    return tasks_on_page, total_pages


@client.callback_query(F.data == 'work_chating')
async def chating_tasks_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    tasks = await DB.get_chating_tasks()

    # Начинаем с первой страницы
    vchatingpage = 1
    tasks_on_page, total_pages = paginate_tasks(tasks, vchatingpage)

    # Генерируем инлайн кнопки
    keyboard = await generate_tasks_keyboard_chating(tasks_on_page, vchatingpage, total_pages, bot)

    await callback.message.edit_text(
        "🔥 <b>Зарабатывайте на сообщениях!</b>\nВыберите чат, вступите в него и получайте Mit Coin за каждое сообщение!",
        reply_markup=keyboard)


@client.callback_query(lambda c: c.data.startswith("vchatingpage_"))
async def vchange_page_handler(callback: types.CallbackQuery, bot: Bot):
    vchatingpage = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    tasks = await DB.get_chating_tasks()

    # Получаем задания на нужной странице
    tasks_on_page, total_pages = paginate_tasks(tasks, vchatingpage)

    # Генерируем инлайн кнопки
    keyboard = await generate_tasks_keyboard_chating(tasks_on_page, vchatingpage, total_pages, bot)

    await callback.message.edit_text(
        "🔥 <b>Зарабатывайте на сообщениях!</b>\nВыберите чат, вступите в него и получайте MITcoin за каждое сообщение!",
        reply_markup=keyboard)


# Функция для проверки прав админа и генерации ссылки
async def check_admin_and_get_invite_link_chating(bot, chat_id):
    try:
        chat_administrators = await bot.get_chat_administrators(chat_id)
        # Проверяем, является ли бот администратором
        for admin in chat_administrators:
            if admin.user.id == bot.id:
                # Если бот админ, генерируем ссылку-приглашение
                invite_link = await bot.export_chat_invite_link(chat_id)
                return invite_link
        # Если бот не админ
        return "😑 Ошибка, приходите позже..."
    except:
        return "😑 Ошибка, приходите позже..."


@client.callback_query(lambda c: c.data.startswith("vchatingtask_"))
async def task_detail_handler(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    task_id = int(callback.data.split('_')[1])
    task = await DB.get_chating_task_by_id(task_id)

    price = task[2]

    invite_link = await check_admin_and_get_invite_link(bot, task[1])
    chat_id = task[1]
    chat = await bot.get_chat(chat_id)
    task_info = f"""
<b>{chat.title}</b>

<em>Вступите в чат, пишите сообщения и зарабатывайте MITcoin</em>

💰 Плата за 1 сообщение - {price} MITcoin 

{invite_link}    
    """
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(text="🔙 Назад", callback_data="work_chating"))

    await callback.message.edit_text(task_info, reply_markup=builder.as_markup())


@client.message(Command('help'))
async def help_handler(message: types.Message, state: FSMContext):
    if message.chat.type in ['group', 'supergroup']:
        await message.answer('''
<b>Для настройки обязательной подписки (ОП)</b>:

1) Бот должен быть админом в данном чате и в рекламируемых каналах 📛
2) Напишите команду /setup @канал 
(для настройки ОП с таймером используйте /setup @канал **h, где ** количество часов)
<i>пример - /setup @mitcoinnews 12h</i>
3) для удаления всех ОП используйте /unsetup 
или /unsetup @канал для удаления конкретного канала 
4) список всех активных ОП в чате - /status

При включенной обязательной подписке пользователи не смогут писать в чат, пока не подпишутся на необходимые каналы 
        ''')


# Команда /setup для настройки ОП
@client.message(Command('setup'))
async def setup_op(message: types.Message, bot: Bot):
    # Проверяем, является ли пользователь администратором чата
    user_id = message.from_user.id
    chat_id = message.text.split()[1]

    if not await is_user_admin(user_id, chat_id, bot):
        await message.answer(f'Бот не является администратором в {chat_id}')
        return  # Игнорируем команды от неадминистраторов

    # Разбираем команду и проверяем указанный канал
    command_parts = message.text.split()
    if len(command_parts) < 2:
        await message.reply("🧾 Укажите канал/чат для настройки ОП. Пример: /setup @mitcoinnews")
        return

    channel_id = command_parts[1]
    try:
        # Проверяем, является ли бот администратором в канале
        bot_member = await bot.get_chat_member(channel_id, bot.id)
        if bot_member.status != 'administrator':
            await message.reply("Бот должен быть администратором в указанном канале ⚠️")
            return
    except TelegramBadRequest:
        await message.reply("Канал не найден или бот не является его администратором 📛")
        return

    # Проверка наличия таймера
    timer_hours = None
    if len(command_parts) > 2 and command_parts[2].endswith("h"):
        timer_hours = int(command_parts[2][:-1])
        expiration_time = datetime.datetime.now() + datetime.timedelta(hours=timer_hours)
    else:
        expiration_time = None

    # Сохраняем ОП в базе данных
    await DB.add_op(chat_id, channel_id, expiration_time)

    if timer_hours:
        await message.reply(f"ОП на {channel_id} добавлена на {timer_hours} часов.")
    else:
        await message.reply(f"ОП на {channel_id} добавлена.")

    # Если есть таймер, запускаем задачу удаления
    if expiration_time:
        await asyncio.create_task(remove_op_after_delay(chat_id, channel_id, expiration_time, bot))


# Команда /unsetup для удаления ОП
@client.message(Command('unsetup'))
async def unsetup_op(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await is_user_admin(user_id, chat_id, bot):
        return  # Игнорируем команды от неадминистраторов

    command_parts = message.text.split()
    if len(command_parts) == 1:
        await DB.remove_op(chat_id)
        await message.reply("Все ОП были удалены 🗑️")
    else:
        channel_id = command_parts[1]
        await DB.remove_op(chat_id, channel_id)
        await message.reply(f"ОП на {channel_id} удалена 🗑️")


# Команда /status для отображения всех ОП
@client.message(Command('status'))
async def status_op(message: types.Message):
    chat_id = message.chat.id

    # Получаем все активные ОП из базы данных
    ops = await DB.get_ops(chat_id)
    if not ops:
        await message.reply("📄 В чате нет активных ОП")
        return

    status_message = "🗒️ Активные ОП:\n\n"
    for op in ops:
        channel = op[0]
        expiration = op[1]

        if expiration:
            expiration = datetime.datetime.strptime(expiration, "%Y-%m-%d %H:%M:%S.%f")

            remaining_time = expiration - datetime.datetime.now()
            # Расчет оставшихся часов и минут
            total_seconds = remaining_time.total_seconds()
            hours_left = int(total_seconds // 3600)
            minutes_left = int((total_seconds % 3600) // 60)

            status_message += f"{channel} - {hours_left} час(ов) {minutes_left} минут(ы)\n"
        else:
            status_message += f"{channel}\n"

    await message.reply(status_message)


async def is_user_admin(user_id, chat_id, bot):
    member = await bot.get_chat_member(chat_id, user_id)
    # Проверка статуса на наличие прав администратора или владельца
    return member.status in ["administrator", "creator"]


async def is_user_subscribed(user_id: int, channel_id: int, bot: Bot) -> bool:
    # Проверка, подписан ли пользователь на канал.
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        return member.status != 'left'
    except TelegramBadRequest:
        return False


async def remove_op_after_delay(chat_id: int, channel_id: str, expiration_time: datetime.datetime, bot: Bot):
    # Функция для автоматического удаления ОП по истечении времени.
    delay = (expiration_time - datetime.datetime.now()).total_seconds()
    await asyncio.sleep(delay)
    await DB.remove_op(chat_id, channel_id)
    await bot.send_message(chat_id, f"ОП на {channel_id} была удалена в связи с окончанием таймера 🗑️")


@client.message(lambda message: message.chat.type in ['group', 'supergroup'])
async def handler_chat_message(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    chat_id = message.chat.id
    name = message.from_user.full_name
    commands_list = ['/help', '/status', '/setup', '/unsetup']
    # Проверяем, является ли чат группой или супер-группой
    if (message.chat.type in ['group', 'supergroup']) and (message.text not in commands_list):

        # Получаем список всех задач из базы данных
        chating_tasks = await DB.get_chating_tasks()

        # Проверяем, есть ли чат в списке задач
        for task in chating_tasks:
            task_chat_id = task[1]
            price = task[2]
            if chat_id == task_chat_id:
                # Проверяем, есть ли пользователь в базе данных
                user_in_db = await DB.select_user(user_id)
                if user_in_db:
                    # Начисляем пользователю сумму на баланс
                    await DB.add_balance(user_id, price)
                break

        member = await bot.get_chat_member(chat_id, user_id)
        if name is None:
            name = "👤"
        if member.status in ["member"]:
            # Получаем все ОП для чата
            ops = await DB.get_ops(chat_id)
            if not ops:
                return  # Если нет активных ОП, не проверяем

            # Проверяем, подписан ли пользователь на все каналы ОП
            unsubscribed_channels = []
            op_tasks = await DB.get_op_tasks()
            if op_tasks:
                pr_op_task = random.choice(op_tasks)
                pr_op = pr_op_task[1]
                text = pr_op_task[2]

                pr_text = f"<a href='https://t.me/{pr_op[1:]}'>{text}</a>"
            else:
                pr_text = "ㅤ"

            # Цикл для проверки подписки и отправки сообщения с кнопками
            for op in ops:
                channel_id = op[0]
                if not await is_user_subscribed(user_id, channel_id, bot):
                    unsubscribed_channels.append(channel_id)

            # Если есть каналы, на которые нужно подписаться
            if unsubscribed_channels:
                try:
                    await message.delete()
                except:
                    print(f"ошибка удаления сообщения в {chat_id}")

                # Создаем клавиатуру вручную, экранируя текст в URL-канале
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Подписаться", url=f"https://t.me/{channel[1:]}")]
                    for channel in unsubscribed_channels
                ])

                # Формируем список каналов для текстового сообщения
                channels_list = "\n".join(
                    [f"@{channel[1:]}" for channel in unsubscribed_channels])

                # Отправляем сообщение с кнопками
                msg = await message.answer(f"""
<a href='tg://user?id={user_id}'>{name}</a>, <b>для того чтобы отправлять сообщения в этот чат, подпишитесь на указанные каналы:</b>

{channels_list}
                """, reply_markup=keyboard, disable_web_page_preview=True)
                await asyncio.sleep(30)
                await msg.delete()








@client.callback_query(F.data == 'checks_menu')
async def checks_menu(callback: types.CallbackQuery, bot: Bot):
    add_button = InlineKeyboardButton(text="👤 Сингл-чек (одноразовый)", callback_data="single_check")
    add_button1 = InlineKeyboardButton(text="💰 Мои чеки", callback_data="my_checks")
    add_button2 = InlineKeyboardButton(text="👥 Мульти-чек (многоразовый)", callback_data=f"multi_check")
    add_button3 = InlineKeyboardButton(text="🔙", callback_data="back_menu")
    # Создаем клавиатуру и добавляем в нее кнопку
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button], [add_button1], [add_button2], [add_button3]])

    await callback.message.edit_text("💸 Чеки позволяют быстро и удобно передавать Mit Coin\n\n<b>Выберите необходимый тип чека:</b>", reply_markup=keyboard)



CHECKS_TYPES = {
    1: '👤 Сингл-Чек',
    2: '👥 Мульти-чек'
}


async def generate_tasks_keyboard_checks(checks, checkspage, total_pages):
    builder = InlineKeyboardBuilder()

    # Выводим задания на текущей странице (по 5 на страницу)
    for check in checks:
        print(check)
        check_type = CHECKS_TYPES.get(check[3], 'Неизвестно')
        amount = check[4]
        button_text = f"{check_type} | {amount} Mit Coin"
        # Каждая кнопка в новой строке
        builder.row(types.InlineKeyboardButton(text=button_text, callback_data=f"check_{check[0]}"))

    # Кнопка "Назад"
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="checks_menu"))

    # Кнопки пагинации
    pagination = []
    if checkspage > 1:
        pagination.append(types.InlineKeyboardButton(text="⬅️", callback_data=f"checkspage_{checkspage - 1}"))
    pagination.append(types.InlineKeyboardButton(text=str(checkspage), callback_data="checkscurrent_page"))
    if checkspage < total_pages:
        pagination.append(types.InlineKeyboardButton(text="➡️", callback_data=f"checkspage_{checkspage + 1}"))

    builder.row(*pagination)  # Кнопки пагинации в одну строку

    return builder.as_markup()


# Метод для получения страницы с заданиями (пагинация)
def checkspaginate_tasks(checks, checkspage=1, per_page=5):
    total_pages = (len(checks) + per_page - 1) // per_page  # Вычисление общего количества страниц
    start_idx = (checkspage - 1) * per_page
    end_idx = start_idx + per_page
    tasks_on_page = checks[start_idx:end_idx]
    return tasks_on_page, total_pages


@client.callback_query(F.data == 'my_checks')
async def my_checks(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    checks = await DB.get_check_by_user_id(user_id)
    print(checks)
    # Начинаем с первой страницы
    checkspage = 1
    tasks_on_page, total_pages = paginate_tasks(checks, checkspage)

    # Генерируем инлайн кнопки
    keyboard = await generate_tasks_keyboard_checks(tasks_on_page, checkspage, total_pages)

    await callback.message.edit_text("💸 <b>Ваши чеки:</b>", reply_markup=keyboard)


@client.callback_query(lambda c: c.data.startswith("checkspage_"))
async def change_page_handler(callback: types.CallbackQuery):
    checkspage = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    checks = await DB.get_check_by_user_id(user_id)

    # Получаем задания на нужной странице
    tasks_on_page, total_pages = paginate_tasks(checks, checkspage)

    # Генерируем инлайн кнопки
    keyboard = await generate_tasks_keyboard_checks(tasks_on_page, checkspage, total_pages)

    await callback.message.edit_text("💸 Ваши чеки:", reply_markup=keyboard)




@client.callback_query(lambda c: c.data.startswith("check_"))
async def check_detail_handler(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    check_id = int(callback.data.split('_')[1])
    check = await DB.get_check_by_id(check_id)
    bot_username = (await bot.get_me()).username
    # Определяем тип задачи
    check_type = CHECKS_TYPES.get(check[3], 'Неизвестно')
    amount = check[5]
    amount_max = check[6]
    sum = check[4]
    check_link = f'https://t.me/{bot_username}?start=check_{check[1]}'

    discription = check[7]
    pin_the_user = check[8]
    
    password = check[9]
    OP_check = check[10]

    if discription is None:
        discription = " "
    if pin_the_user is None:
        pin_the_user = "нет"
    if password is None:
        password = "нет"
    if OP_check is None:
        OP_check = "нет"

    if check[3] == 1:
        check_info = f'''
💸 <b>Одноразовый чек на сумму {sum} MIT Coin</b>

📝 <b>Описание:</b> {discription}
📌 <b>Привязка к пользователю:</b> {pin_the_user}

❗ Помните, что отправляя кому-либо ссылку на чек - Вы передаете свои монеты без гарантий получить что-либо в ответ

<span class="tg-spoiler">{check_link}</span>
        '''
    elif check[3] == 2:
        check_info = f"""
💸 <b>Многоразовый чек на сумму {sum*amount} MIT Coin</b>

<b>Общее количество активаций: {amount_max} </b>
<b>Количество оставшихся активаций: {amount} </b>
<b>Сумма одной активации: {sum} Mit Coin</b>
 
📝 <b>Описание:</b> {discription}
🔐 <b>Пароль:</b> {password}
📣 <b>Обязательная подписка (ОП):</b> {OP_check}


❗ Помните, что отправляя кому-либо ссылку на чек - Вы передаете свои монеты без гарантий получить что-либо в ответ

<span class="tg-spoiler">{check_link}</span>
        """

    if check[3] == 1:
        add_button = InlineKeyboardButton(text="✈ Отправить", switch_inline_query=f'\nЧЕК НА СУММУ {sum} MIT COIN\n{discription}\n\n{check_link}')
        add_button1 = InlineKeyboardButton(text="📝 Добавить описание", callback_data=f'adddiscription_{check_id}')
        add_button2 = InlineKeyboardButton(text="⛓ Привязать к пользователю", callback_data=f"pincheckuser_{check_id}")
        add_button3 = InlineKeyboardButton(text="🗑 Удалить", callback_data=f"checkdelete_{check_id}")
        add_button4 = InlineKeyboardButton(text="🔙 Назад", callback_data="my_checks")
        # Создаем клавиатуру и добавляем в нее кнопку
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button], [add_button1], [add_button2], [add_button3], [add_button4]])
    elif check[3] == 2:
        add_button = InlineKeyboardButton(text="✈ Отправить",
                                          switch_inline_query=f'💸 ЧЕК НА СУММУ {sum*amount} MIT COIN\n{discription}\n\n{check_link}')
        add_button1 = InlineKeyboardButton(text="📝 Добавить описание", callback_data=f'adddiscription_{check_id}')
        add_button2 = InlineKeyboardButton(text="📣 Добавить ОП", callback_data=f"addopcheck_{check_id}")
        add_button3 = InlineKeyboardButton(text="🔑 Задать пароль", callback_data=f"addpasswordcheck_{check_id}")
        add_button4 = InlineKeyboardButton(text="👑 Разместить в MIT Coin DROPS", callback_data=f"sendmitdrops_{check_id}")
        add_button5 = InlineKeyboardButton(text="💰 Пополнить баланс чека", callback_data=f"addbalancecheck_{check_id}")
        add_button6 = InlineKeyboardButton(text="🗑 Удалить", callback_data=f"checkdelete_{check_id}")
        add_button7 = InlineKeyboardButton(text="🔙 Назад", callback_data="my_checks")
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[add_button], [add_button1], [add_button2], [add_button3], [add_button4], [add_button5], [add_button6], [add_button7]])
    await callback.message.edit_text(check_info, reply_markup=keyboard)






@client.callback_query(lambda c: c.data.startswith("sendmitdrops_"))
async def sendmitdrops(callback: types.CallbackQuery, state: FSMContext):
    check_id = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    add_button = InlineKeyboardButton(text="📤 Разместить", callback_data=f"mitcoindrop_{check_id}")
    add_button1 = InlineKeyboardButton(text="🔙 Назад", callback_data=f"check_{check_id}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button], [add_button1]])
    await callback.message.edit_text('''
<b>Вы можете разместить свой чек в @mitcoin_drops</b> 

<b>Условия размещения:</b>
1) Чек без пароля
2) Общая сумма чека больше 50000 Mit Coin 
    ''', reply_markup=keyboard)

@client.callback_query(lambda c: c.data.startswith("mitcoindrop_"))
async def sendmitdrops1(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    check_id = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    check = await DB.get_check_by_id(check_id)
    type = check[3]
    sum = check[4]
    amount = check[5]
    bot_username = (await bot.get_me()).username
    general_sum = sum*amount
    check_link = f'https://t.me/{bot_username}?start=check_{check[1]}'
    if type == 2 and general_sum >= 50000 and check[8] is None:

        if check[6] is not None:
            description = check[6]
        else:
            description = ''
            
        text = f'''
💸 <b>Чек на сумму {general_sum} MitCoin</b>

{amount} активаций
{sum} MitCoin за одну активацию

{description}

{check_link}        
        '''
        try:
            add_button = InlineKeyboardButton(text="Получить", url=check_link)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button]])
            await bot.send_message(chat_id='-1002446297366', text=text, reply_markup=keyboard)
            await callback.message.edit_text('🥳 Чек успешно размещен в @mitcoin_drops',reply_markup=back_menu_kb())
        except:
            await callback.message.edit_text('Ошибка размещения чека в @mitcoin_drops, попробуйте позже или обратитеть в тех поддержку', reply_markup=back_menu_kb())
    else:
        await callback.message.edit_text(
            '❌ Ваш чек не подходит по условиям',
            reply_markup=back_menu_kb())

@client.callback_query(lambda c: c.data.startswith("addopcheck_"))
async def delete_check_handler(callback: types.CallbackQuery, state: FSMContext):
    check_id = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    add_button = InlineKeyboardButton(text="🔙 Назад", callback_data=f"check_{check_id}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button]])
    await callback.message.edit_text('📣 <b>Вы можете настроить обязательную подписку (ОП) для чека</b>\n\n<i>Пользователь не сможет активировать чек, пока не подпишется на канал</i>\n\n<b>Добавьте бота в администраторы канала и введите @username канала</b>', reply_markup=keyboard)
    await state.set_state(checks.check_op)
    await state.update_data(check_id=check_id)

@client.message(checks.check_op)
async def handle_custom_check_amount(message: types.Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    check_id = data.get('check_id')
    #check = await DB.get_check_by_id(check_id)
    #check_OP = check[9]

    #if check_OP is not None:
        #availeble_OP = check_OP.split('_')
        #print(availeble_OP)
        #if len(availeble_OP) >= 5:
            #await message.answer('❗ Вы достигли лимита в 5 каналов необходимых к ОП')

        
    try:
        text = str(message.text)

        if text == "None":
            await message.answer('❗ Введите @username канала, необходимого к ОП')
            return
        try:
            chat = await bot.get_chat(text)
            test = chat.invite_link
            if not test:
                await message.answer('❗ Этот бот не является администратором данного канала, повторите попытку')
                return
            print(chat)
            #OP = f'{text}_'
            await DB.update_check(check_id=check_id, OP_id=text)
            #add_button = InlineKeyboardButton(text="➕ Добавить", callback_data=f"addnextop_{check_id}")
            add_button1 = InlineKeyboardButton(text="✅ Готово", callback_data=f"check_{check_id}")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button1]])
            await message.answer(f'📣 Канал <b>{chat.title}</b> успешно добавлен к ОП', reply_markup=keyboard)
            await state.clear()
        except:
            await message.answer('☹ Не удалось найти канал по указанному @username, либо бот не является администратором данного канала, повторите попытку')
            return

    except ValueError:
        await message.answer('❗ Введите @username канала, необходимого к ОП')

#@client.callback_query(lambda c: c.data.startswith("addnextop_"))
#async def delete_check_handler(callback: types.CallbackQuery, state: FSMContext):
 #   check_id = int(callback.data.split('_')[1])
  #  user_id = callback.from_user.id

   # add_button = InlineKeyboardButton(text="🔙 Назад", callback_data=f"check_{check_id}")
    #keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button]])
    #await callback.message.edit_text('📣 <b>Добавьте бота в администраторы канала и введите @username канала</b>\n\n<i>Всего можно добавить не более 5 каналов</i>', reply_markup=keyboard)
    #await state.set_state(checks.check_op)
    #await state.update_data(check_id=check_id)













@client.callback_query(lambda c: c.data.startswith("addbalancecheck_"))
async def activation_check_handler(callback: types.CallbackQuery, state: FSMContext):
    check_id = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    balance = user["balance"]
    check = await DB.get_check_by_id(check_id)
    sum = check[4]
    available_act = balance // sum
    add_button = InlineKeyboardButton(text="🔙 Назад", callback_data=f"check_{check_id}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button]])
    await callback.message.edit_text(f'➕ Вы можете добавить количество активаций к вашему чеку, не создавая новый\n\n<b>Введите количество активаций, которое вы хотите добавить ({available_act} максимально):</b>', reply_markup=keyboard)
    await state.set_state(checks.add_activation)
    await state.update_data(check_id=check_id)

@client.message(checks.add_activation)
async def handle_custom_check_activation(message: types.Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    user = await DB.select_user(user_id)
    check_id = data.get('check_id')
    balance = user["balance"]
    check = await DB.get_check_by_id(check_id)
    sum = check[4]
    available_act = balance // sum
    try:
        text = int(message.text)
        if text > available_act:
            await message.answer(f'❗ Максимально вы можете добавить {available_act} активаций')
            return
        if text == "None":
            await message.answer('❗ Введите целое число')
            return
        new_amount = check[5] + text
        await DB.update_check(check_id=check_id, amount=new_amount)
        new_price = sum*text
        await DB.add_balance(user_id, amount=-new_price)
        add_button = InlineKeyboardButton(text="🔙 Назад", callback_data=f"check_{check_id}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button]])
        await message.answer(f'🥳 <b>К чеку добавлено {text} активаций</b>', reply_markup=keyboard)
        await state.clear()
    except ValueError:
        await message.answer('❗ Введите желаемое количество активаций в виде целого числа')


















@client.callback_query(lambda c: c.data.startswith("addpasswordcheck_"))
async def delete_check_handler(callback: types.CallbackQuery, state: FSMContext):
    check_id = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    add_button = InlineKeyboardButton(text="🔙 Назад", callback_data=f"check_{check_id}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button]])
    await callback.message.edit_text('📝 <b>Отправьте пароль для чека:</b>', reply_markup=keyboard)
    await state.set_state(checks.check_password)
    await state.update_data(check_id=check_id)

@client.message(checks.check_password)
async def handle_custom_check_amount(message: types.Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    check_id = data.get('check_id')
    try:
        text = str(message.text)
        if len(text) > 20:
            await message.answer('❗ Пароль не должен превышать 20 символов...')
            return
        if text == "None":
            await message.answer('❗ Пароль может быть исключительно в текстовом формате! Повторите попытку')
            return
        await DB.update_check(check_id=check_id, password=text)
        add_button = InlineKeyboardButton(text="🔙 К чеку", callback_data=f"check_{check_id}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button]])
        await message.answer(f'<i>{text}</i>\n\nПароль установлен к чеку', reply_markup=keyboard)
        await state.clear()
    except ValueError:
        await message.answer('❗ Напишите пароль в текстовом формате...')








@client.callback_query(lambda c: c.data.startswith("adddiscription_"))
async def delete_check_handler(callback: types.CallbackQuery, state: FSMContext):
    check_id = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    await callback.message.edit_text('📝 <b>Отправьте необходимое описание для чека:</b>')
    await state.set_state(checks.check_discription)
    await state.update_data(check_id=check_id)

@client.message(checks.check_discription)
async def handle_custom_check_amount(message: types.Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    check_id = data.get('check_id')
    try:
        text = str(message.text)
        if len(text) > 50:
            await message.answer('❗ Описание не должно превышать 50 символов...')
            return
        if text == "None":
            await message.answer('❗ В описании не может быть стикеров, картинок и другого медиа-контента, допустим только текст...')
            return
        await DB.update_check(check_id=check_id, description=text)
        add_button = InlineKeyboardButton(text="🔙 К чеку", callback_data=f"check_{check_id}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button]])
        await message.answer(f'<i>{text}</i>\n\nОписание установлено к чеку', reply_markup=keyboard)
        await state.clear()
    except ValueError:
        await message.answer('❗ Напишите текстовое описание к чеку...')







@client.callback_query(lambda c: c.data.startswith("pincheckuser_"))
async def delete_check_handler(callback: types.CallbackQuery, state: FSMContext):
    check_id = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    await callback.message.edit_text('📝 <b>Отправьте @username либо ID пользователя, к которому нужно привязать чек</b>')
    await state.set_state(checks.check_lock_user)
    await state.update_data(check_id=check_id)

@client.message(checks.check_lock_user)
async def handle_custom_check_amount(message: types.Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    check_id = data.get('check_id')
    try:
        user = str(message.text)

        if user == "None" or len(user) > 20:
            await message.answer('❗ Укажите верный юзернейм либо ID пользователя')
            return
        await DB.update_check(check_id=check_id, locked_for_user=user)
        add_button = InlineKeyboardButton(text="🔙 К чеку", callback_data=f"check_{check_id}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button]])
        await message.answer(f'🔐 <b>Теперь этот чек доступен только для</b> {user}', reply_markup=keyboard)
        await state.clear()
    except ValueError:
        await message.answer('❗ Попробуйте заново...')











@client.callback_query(lambda c: c.data.startswith("checkdelete_"))
async def delete_check_handler(callback: types.CallbackQuery):
    check_id = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    user = await DB.select_user(user_id)
    balance = user['balance']
    check = await DB.get_check_by_id(check_id)
    amount = check[5]
    sum = check[4]

    cost = sum*amount

    new_balance = balance + cost

    # Удаляем задачу из базы данных
    await DB.delete_check(check_id=check_id, user_id=user_id)
    await DB.update_balance(user_id, balance=new_balance)
    await callback.message.edit_text("🗑")
    await asyncio.sleep(1)
    # После удаления возвращаем пользователя к его заданиям
    user_id = callback.from_user.id
    checks = await DB.get_check_by_user_id(user_id)
    checkspage = 1
    tasks_on_page, total_pages = paginate_tasks(checks, checkspage)
    keyboard = await generate_tasks_keyboard_checks(tasks_on_page, checkspage, total_pages)

    await callback.message.edit_text("💸 <b>Ваши чеки:</b>", reply_markup=keyboard)






@client.callback_query(F.data == 'single_check')
async def create_single_check(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    user_balance = await DB.get_user_balance(user_id)


    if user_balance < 1010:
        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(text="Пополнить баланс", callback_data='deposit_menu'))
        builder.add(types.InlineKeyboardButton(text="🔙 Назад", callback_data='back_menu'))
        await callback.message.edit_text(
            "❌ У вас недостаточно средств для создания чека.\nПополните баланс для продолжения.",
            reply_markup=builder.as_markup())
        return

    max_check = user_balance - (user_balance // 100)


    add_button = InlineKeyboardButton(text=f"📈 Максимально ({max_check} MitCoin)", callback_data=f'checkamount_{max_check}')
    add_button1 = InlineKeyboardButton(text=f"📉 Минимально (1000 MitCoin)", callback_data=f'checkamount_1000')
    add_button2 = InlineKeyboardButton(text="📊 Другая сумма", callback_data='customcheck_amount')
    add_button3 = InlineKeyboardButton(text="🔙 Назад", callback_data='checks_menu')
    # Создаем клавиатуру и добавляем в нее кнопку
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button], [add_button1], [add_button2], [add_button3]])
    await callback.message.edit_text(
        "💰 <b>Сколько MitCoin вы хотите отправить пользователю?</b>",
        reply_markup=keyboard
    )

@client.callback_query(F.data == 'customcheck_amount')
async def custom_check_amount(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "💵 <b>Введите сумму MitCoin, которую получит пользователь за активацию чека (целое число)</b>"
    )
    await state.set_state(checks.single_check_create)


@client.message(checks.single_check_create)
async def handle_custom_check_amount(message: types.Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    user_balance = await DB.get_user_balance(user_id)


    bot_username = (await bot.get_me()).username
    try:
        sum = int(message.text)
        if sum + (sum // 100) > user_balance:
            builder = InlineKeyboardBuilder()
            builder.add(types.InlineKeyboardButton(text="Пополнить баланс", callback_data='deposit_menu'))
            builder.add(types.InlineKeyboardButton(text="🔙 Назад", callback_data='back_menu'))
            await message.answer(
                "❌ У вас недостаточно средств для создания чека на эту сумму, введите другое число",
                reply_markup=builder.as_markup()
            )
            return

        # Списание с баланса

        await state.clear()
        # Генерация уникального чека
        uid = str(uuid.uuid4())
        await DB.update_balance(user_id, balance=user_balance - (sum + sum//100))
        await DB.create_check(uid=uid, user_id=user_id, type=1, sum=sum, amount=1)
        check = await DB.get_check_by_uid(uid)
        check_id = check[0]
        check_link = f"https://t.me/{bot_username}?start=check_{uid}"
        add_button1 = InlineKeyboardButton(text="✈ Отправить", switch_inline_query=check_link)
        add_button2 = InlineKeyboardButton(text="⚙ Настройка", callback_data=f'check_{check_id}')
        add_button3 = InlineKeyboardButton(text="🔙 Назад", callback_data='checks_menu')
        # Создаем клавиатуру и добавляем в нее кнопку
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button1], [add_button2], [add_button3]])
        await message.answer(f'''
💸 <b>Одноразовый чек на сумму {sum} MitCoin</b>

❗ Помните, что отправляя кому-либо эту ссылку Вы передаете свои монеты без гарантий получить что-то в ответ
<i>Вы можете настроить чек с помощью кнопки ниже</i>

<span class="tg-spoiler">{check_link}</span>
        ''', reply_markup=keyboard)

    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректную сумму.")


@client.callback_query(F.data.startswith('checkamount_'))
async def handle_check_amount(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    sum = int(callback.data.split('_')[1])
    bot_username = (await bot.get_me()).username
    # Проверка баланса
    user_balance = await DB.get_user_balance(user_id)


    if sum + (sum//100) > user_balance:
        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(text="Пополнить баланс", callback_data='deposit_menu'))
        builder.add(types.InlineKeyboardButton(text="🔙 Назад", callback_data='back_menu'))
        await callback.message.edit_text(
            "❌ У вас недостаточно средств для создания чека на эту сумму.",
            reply_markup=builder.as_markup()
        )
        return

    # Списание с баланса


    # Генерация уникального чека
    uid = str(uuid.uuid4())
    await DB.update_balance(user_id, balance=user_balance - (sum + (sum // 100)))
    await DB.create_check(uid=uid, user_id=user_id, type=1, sum=sum, amount=1, ref_bonus=0, ref_fund=0) 

    check = await DB.get_check_by_uid(uid)
    check_id = check[0]
    check_link = f"https://t.me/{bot_username}?start=check_{uid}"
    add_button1 = InlineKeyboardButton(text="✈ Отправить", switch_inline_query=check_link)
    add_button2 = InlineKeyboardButton(text="⚙ Настройка", callback_data=f'check_{check_id}')
    add_button3 = InlineKeyboardButton(text="🔙 Назад", callback_data='checks_menu')
    # Создаем клавиатуру и добавляем в нее кнопку
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button1], [add_button2], [add_button3]])
    await callback.message.edit_text(f'''
💸 <b>Одноразовый чек на сумму {sum} MitCoin</b>

<i>Вы можете настроить чек с помощью кнопки ниже</i>
❗ Помните, что отправляя кому-либо эту ссылку Вы передаете свои монеты без каких-либо гарантий получить что-то в ответ

<span class="tg-spoiler">{check_link}</span>
    ''', reply_markup=keyboard)





@client.callback_query(F.data == 'multi_check')
async def create_multi_check(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_balance = await DB.get_user_balance(user_id)

    if user_balance < 1010:
        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(text="Пополнить баланс", callback_data='deposit_menu'))
        builder.add(types.InlineKeyboardButton(text="🔙 Назад", callback_data='back_menu'))
        await callback.message.edit_text(
            "❌ У вас недостаточно средств для создания мульти-чека.\nПополните баланс для продолжения.",
            reply_markup=builder.as_markup()
        )
        return

    await callback.message.edit_text(
        f"📋 <b>Введите необходимое количество активаций (целое число)</b>\n\nМаксимальное количество активаций при минимальной цене (1000 MitCoin) для вашего баланса - {int((user_balance/1000) - ((user_balance/1000)/100))}", reply_markup=cancel_all_kb()
    )
    await state.set_state(checks.multi_check_quantity)
    await state.update_data(balance=user_balance)

@client.message(checks.multi_check_quantity)
async def handle_multi_check_quantity(message: types.Message, state: FSMContext):
    data = await state.get_data()
    balance = data.get('balance')
    try:
        quantity = int(message.text)
        if quantity <= 0:
            await message.answer("❌ <b>Количество активаций не может быть меньше 0</b>, введите корректное число", reply_markup=cancel_all_kb())
            return
        if quantity > balance // 1000:
            await message.answer(f"❌ <b>У вас недостаточно MitCoin для создания {quantity} активаций чека.</b>\nПополните баланс для продолжения", reply_markup=cancel_all_kb())
            return

        await message.answer(f"💵 <b>Введите сумму MitCoin за одну активацию чека (целое число)</b>\n\n<i>Максимальная сумма для вашего баланса - {int(balance//quantity - ((balance//quantity)//100))} MitCoin</i>", reply_markup=cancel_all_kb())
        await state.set_state(checks.multi_check_amount)
        await state.update_data(quantity=quantity)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное количество активаций", reply_markup=cancel_all_kb())

@client.message(checks.multi_check_amount)
async def handle_multi_check_amount(message: types.Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    user_balance = await DB.get_user_balance(user_id)

    try:
        data = await state.get_data()
        quantity = data.get('quantity')

        amount_per_check = int(message.text)
        total_amount = quantity * amount_per_check

        if amount_per_check < 1000:
            await message.answer("❌ Сумма одного чека должна быть 1000 MitCoin или больше. Попробуйте ещё раз.", reply_markup=cancel_all_kb())
            return

        if total_amount > user_balance:
            builder = InlineKeyboardBuilder()
            builder.add(types.InlineKeyboardButton(text="Пополнить баланс", callback_data='deposit_menu'))
            builder.add(types.InlineKeyboardButton(text="🔙 Назад", callback_data='back_menu'))
            await message.answer(
                f"❌ <b>У вас недостаточно средств для создания чека на {quantity} активаций и суммы в {amount_per_check} MitCoin за одну активацию</b>\n\nВаш баланс - {user_balance}\nОбщая сумма чека - {total_amount} ",
                reply_markup=builder.as_markup()
            )
            return

        # Сохраняем данные о чеке в состоянии
        await state.update_data(amount_per_check=amount_per_check, total_amount=total_amount)

        # Спрашиваем, хочет ли пользователь включить реферальную систему
        builder = InlineKeyboardBuilder()
        builder.add(types.InlineKeyboardButton(text="Да", callback_data='enable_referral'))
        builder.add(types.InlineKeyboardButton(text="Нет", callback_data='disable_referral'))
        await message.answer("🔗 <b>Хотите включить реферальную систему для этого чека?</b>", reply_markup=builder.as_markup())

    except ValueError:
        await message.answer("❌ <b>Пожалуйста, введите корректную сумму за одну активацию чека</b>")

@client.callback_query(F.data == 'enable_referral')
async def enable_referral(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(text="25%", callback_data='referral_percent_25'))
    builder.add(types.InlineKeyboardButton(text="50%", callback_data='referral_percent_50'))
    builder.add(types.InlineKeyboardButton(text="75%", callback_data='referral_percent_75'))
    builder.add(types.InlineKeyboardButton(text="100%", callback_data='referral_percent_100'))
    await callback.message.edit_text("📊 <b>Выберите процент от суммы чека, который будут получать рефералы:</b>", reply_markup=builder.as_markup())

@client.callback_query(F.data.startswith('referral_percent_'))
async def set_referral_percent(callback: types.CallbackQuery, state: FSMContext):
    percent = int(callback.data.split('_')[-1])
    await state.update_data(referral_percent=percent)

    await callback.message.answer(
        "📊 <b>Введите количество доступных активаций по реферальным ссылкам:</b>",
        reply_markup=cancel_all_kb()
    )
    await state.set_state(checks.set_ref_fund)

@client.message(checks.set_ref_fund)
async def handle_set_ref_fund(message: types.Message, state: FSMContext, bot: Bot):
    try:
        ref_fund = int(message.text)
        if ref_fund < 0:
            await message.answer("❌ Количество активаций не может быть отрицательным. Попробуйте ещё раз.", reply_markup=cancel_all_kb())
            return

        # Получаем данные о чеке из состояния
        data = await state.get_data()
        quantity = data.get('quantity')
        amount_per_check = data.get('amount_per_check')
        total_amount = data.get('total_amount') 
        referral_percent = data.get('referral_percent')
        print(total_amount)
        total_amount = total_amount//quantity 
        print(total_amount)
        # Рассчитываем общую сумму списания
        total_deduction = total_amount * quantity + ( total_amount * (referral_percent / 100) * ref_fund ) 
        print(total_deduction) 
        print(f'{total_amount} * {quantity} + ( {total_amount} * ({referral_percent / 100}) * {ref_fund} ) = {total_deduction}')
        # Списание с баланса
        user_id = message.from_user.id
        user_balance = await DB.get_user_balance(user_id)
        if user_balance < total_deduction:
            await message.answer("❌ Недостаточно средств на балансе для создания чека с учётом реферального фонда.", reply_markup=cancel_all_kb())
            return

        await DB.update_balance(user_id, balance=user_balance - total_deduction)

        # Генерация уникального чека
        uid = str(uuid.uuid4()) 
        await DB.create_check(
            uid=uid,
            user_id=user_id,
            type=2,
            sum=amount_per_check,
            amount=quantity,
            ref_bonus=referral_percent,
            ref_fund=ref_fund
        )

        check = await DB.get_check_by_uid(uid)
        check_id = check[0]
        bot_username = (await bot.get_me()).username
        check_link = f"https://t.me/{bot_username}?start=check_{uid}"

        add_button1 = InlineKeyboardButton(text="✈ Отправить", switch_inline_query=check_link)
        add_button2 = InlineKeyboardButton(text="⚙ Настройка", callback_data=f'check_{check_id}')
        add_button3 = InlineKeyboardButton(text="🔙 Назад", callback_data='checks_menu')

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_button1], [add_button2], [add_button3]])
        await message.answer(
            f'''
💸 <b>Ваш мульти-чек создан:</b>

Количество активаций: {quantity}
Сумма за одну активацию: {amount_per_check} MitCoin
Реферальный фонд: {ref_fund} активаций

💰 Общая сумма чека: {total_amount} MitCoin
💼 Реферальный процент: {referral_percent}%

❗ Помните, что отправляя кому-либо эту ссылку Вы передаете свои монеты без гарантий получить что-то в ответ
<i>Вы можете настроить чек с помощью кнопки ниже</i>

<span class="tg-spoiler">{check_link}</span>
''',
            reply_markup=keyboard
        )

        await state.clear()
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число.", reply_markup=cancel_all_kb())

@client.callback_query(F.data == 'disable_referral')
async def disable_referral(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    # Получаем данные о чеке из состояния
    data = await state.get_data()
    quantity = data.get('quantity')
    amount_per_check = data.get('amount_per_check')
    total_amount = quantity * amount_per_check
    print(f'{quantity} * {amount_per_check}')

    # Создаем чек без реферального фонда
    uid = str(uuid.uuid4())
    await DB.create_check(
        uid=uid,
        user_id=callback.from_user.id,
        type=2,
        sum=amount_per_check,
        amount=quantity,
        ref_bonus=None,
        ref_fund=None
    )
    await DB.update_balance(callback.from_user.id, balance=await DB.get_user_balance(callback.from_user.id) - total_amount)

    bot_username = (await bot.get_me()).username
    check_link = f"https://t.me/{bot_username}?start=check_{uid}"

    await callback.message.answer(
            f'''
💸 <b>Ваш мульти-чек создан:</b>

Количество активаций: {quantity}
Сумма за одну активацию: {amount_per_check} MitCoin
Реферальный фонд: отсутствует

💰 Общая сумма чека: {total_amount} MitCoin
💼 Реферальный процент: отсутствует

❗ Помните, что отправляя кому-либо эту ссылку Вы передаете свои монеты без гарантий получить что-то в ответ
<i>Вы можете настроить чек с помощью кнопки ниже</i>

<span class="tg-spoiler">{check_link}</span>
''',        reply_markup=back_menu_kb()
    )
    await state.clear()

@client.callback_query(F.data.startswith('refill_ref_fund_'))
async def refill_ref_fund(callback: types.CallbackQuery, state: FSMContext):
    """
    Запрашивает у пользователя количество активаций для пополнения реферального фонда.
    """
    check_id = int(callback.data.split('_')[-1])  # Получаем ID чека из callback_data
    await state.update_data(check_id=check_id)  # Сохраняем ID чека в состоянии

    await callback.message.answer(
        "💵 <b>Введите количество активаций для пополнения реферального фонда:</b>",
        reply_markup=cancel_all_kb()
    )
    await state.set_state(checks.refill_ref_fund)

@client.message(checks.refill_ref_fund)
async def handle_refill_ref_fund(message: types.Message, state: FSMContext, bot: Bot):
    """
    Обрабатывает ввод пользователя и пополняет реферальный фонд.
    """
    try:
        ref_fund = int(message.text)  # Получаем количество активаций
        if ref_fund <= 0:
            await message.answer("❌ Количество активаций должно быть больше 0.", reply_markup=cancel_all_kb())
            return

        data = await state.get_data()
        check_id = data.get('check_id')  # Получаем ID чека из состояния

        # Получаем текущий реферальный фонд
        check = await DB.get_check_by_id(check_id)
        current_ref_fund = check[12]  # ref_fund находится в 12-й колонке

        # Обновляем реферальный фонд
        new_ref_fund = current_ref_fund + ref_fund
        await DB.update_check2(check_id, ref_fund=new_ref_fund)

        # Уведомляем пользователя об успешном пополнении
        await message.answer(
            f"✅ <b>Реферальный фонд успешно пополнен на {ref_fund} активаций.</b>\n\n"
            f"Теперь доступно {new_ref_fund} активаций.",
            reply_markup=back_menu_kb()
        )


        await state.clear()
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число.", reply_markup=cancel_all_kb())


# Добавляем в db.py новые методы

async def get_active_completed_tasks(self):
    """Получить активные задания для проверки"""
    async with self.con.cursor() as cur:
        await cur.execute('''
            SELECT * FROM completed_tasks 
            WHERE status = 1 AND rem_days > 0
        ''')
        return await cur.fetchall()

async def update_completed_task(self, task_id, status=None, rem_days=None):
    """Обновить данные выполненного задания"""
    updates = []
    params = []
    async with self.con.cursor() as cur:
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if rem_days is not None:
            updates.append("rem_days = ?")
            params.append(rem_days)
        
        if updates:
            params.append(task_id)
            await cur.execute(f'''
                UPDATE completed_tasks 
                SET {', '.join(updates)} 
                WHERE rowid = ?
            ''', params)
            await self.con.commit()

# Добавляем в client.py
async def check_subscriptions_periodically(bot: Bot):
    while True:
        await asyncio.sleep(7200)  # Каждые 2 часа
        print('провожу проверку')
        try:
            active_tasks = await DB.get_active_completed_tasks()
            print(active_tasks)
            for task in active_tasks:
                user_id, task_id, target_id, task_sum, owner_id, status, rem_days, *_ = task
                
                # Проверка подписки
                try:
                    member = await bot.get_chat_member(target_id, user_id)
                    print('member: '+ str(member))
                    is_subscribed = member.status in ['member', 'administrator', 'creator']
                except Exception:
                    is_subscribed = False

                if not is_subscribed:
                    # Отправка предупреждения
                    try:
                        chat = await bot.get_chat(target_id)
                        invite_link = chat.invite_link
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="Подписаться", url=invite_link)]
                        ])
                        
                        await bot.send_message(
                            user_id,
                            f"⚠️ Вы отписались от {chat.title}!\n"
                            "Пожалуйста, подпишитесь снова в течение 2 часов, "
                            f"иначе будет списано {task_sum} MITcoin!",
                            reply_markup=keyboard
                        )
                        
                        # Ждем 2 часа и проверяем снова
                        await asyncio.sleep(7200)
                        member = await bot.get_chat_member(target_id, user_id)
                        is_subscribed = member.status in ['member', 'administrator', 'creator']
                        
                        if not is_subscribed:
                            # Списание средств
                            await DB.add_balance(user_id, -task_sum)
                            await DB.add_balance(owner_id, task_sum)
                            await DB.update_completed_task(user_id, status=0) 
                            
                            await bot.send_message(
                                user_id,
                                f"❌ Вам списан штраф {task_sum} MITcoin "
                                f"за отписку от {chat.title}!"
                            )
                            await bot.send_message(
                                owner_id,
                                f"💸 Вам возвращено {task_sum} MITcoin "
                                f"от пользователя {user_id} за отписку"
                            )
                            
                    except Exception as e:
                        print(f"Ошибка обработки штрафа: {e}")

            # Ежедневное уменьшение rem_days
            if datetime.datetime.now().hour == 0 or datetime.datetime.now().hour == 1:  # В полночь
                await DB.con.execute('''
                    UPDATE completed_tasks 
                    SET rem_days = rem_days - 1 
                    WHERE status = 1 AND rem_days > 0
                ''')
                await DB.con.commit()
                
        except Exception as e:
            print(f"Ошибка в фоновой задаче: {e}")


# Обработчик команды /report
@client.message(Command('report'))
async def send_report(message: types.Message, bot: Bot):
    # Проверяем, что текст после команды /report не пустой
    if len(message.text.split()) > 1:
        report_text = ' '.join(message.text.split()[1:])  # Получаем текст после команды /report
        
        # Формируем сообщение для админов
        admin_message = (f"""
      🚨 <b>Новый репорт!</b> 🚨
👤 <b>Пользователь:</b> @{message.from_user.username}
🆔 <b>ID:</b> <code>{message.from_user.id}</code>\n
📝 <b>Текст репорта:</b>
<blockquote>{report_text}</blockquote>"""
        )
        from config import ADMINS_ID
        # Отправляем сообщение всем админам
        for admin_id in ADMINS_ID:
            try:
                await bot.send_message(admin_id, admin_message)
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение админу {admin_id}: {e}")
        
        # Отправляем подтверждение пользователю
        await message.reply("✅ Ваш репорт успешно отправлен админам!")
    else:
        await message.reply("⚠️ Пожалуйста, укажите текст репорта после команды /report.")



# Команда /top
@client.callback_query(F.data.startswith('rating'))
async def show_top(callback: types.CallbackQuery):
    top_users = await DB.get_top_users(ADMINS_ID)
    print(top_users)
    
    # Создаем клавиатуру с рейтингом
    keyboard = InlineKeyboardBuilder()

    for i in range(len(top_users)):
        user_id, username, balance = top_users[i]
        if i+1 == 1:
            emoji = "🥇"
        elif i+1 == 2:
            emoji = "🥈"
        elif i+1 == 3:
            emoji = "🥉"
        else:
            emoji = "🔹"
        keyboard.add(InlineKeyboardButton(text=f"{emoji}{i+1}. {username} - {balance} 💰", url='https://t.me/'+ username))
    keyboard.add(InlineKeyboardButton(text="Назад 🔙", callback_data='menu_stats'))
    keyboard.adjust(1) 

    
    # Отправляем сообщение с рейтингом
    await callback.message.edit_text("🏆 Топ-10 пользователей по балансу 🏆", reply_markup=keyboard.as_markup())