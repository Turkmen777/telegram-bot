import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# ========== НАСТРОЙКИ ==========
# ЗАМЕНИТЕ ЭТИ ДАННЫЕ НА СВОИ!
BOT_TOKEN = "8607427844:AAFloUJdBWJConJPBpPABuUQOXdjo1qRS44"  # ПОЛУЧИТЕ В @BotFather
GROUP_CHAT_ID = -1003759188641  # ID вашей группы (оставьте как есть)
ADMIN_IDS = [8444800411]  # Ваш Telegram ID (оставьте как есть)
MIN_AMOUNT = 50  # Минимальная сумма

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# В памяти
deposits = []
next_id = 1000

# Состояния
WAITING_ID, WAITING_AMOUNT = range(2)

# ========== КЛИЕНТСКАЯ ЧАСТЬ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("💰 Пополнить счет")]]
    await update.message.reply_text(
        "Привет! Нажмите кнопку:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_deposit_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите ваш ID:")
    return WAITING_ID

async def handle_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['client_id'] = update.message.text
    await update.message.reply_text("Введите сумму (мин. 50 TMT):")
    return WAITING_AMOUNT

async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.replace(',', '.'))
        
        if amount < MIN_AMOUNT:
            await update.message.reply_text(f"❌ Минимум {MIN_AMOUNT} TMT")
            return WAITING_AMOUNT
        
        global next_id, deposits
        
        # Создаем заявку
        deposit = {
            'id': next_id,
            'user_id': update.effective_user.id,
            'user_name': update.effective_user.first_name,
            'client_id': context.user_data['client_id'],
            'amount': amount,
            'time': datetime.now().strftime("%H:%M %d.%m.%Y"),
            'status': 'waiting'
        }
        
        deposits.append(deposit)
        
        # Клиенту
        await update.message.reply_text(
            f"✅ Заявка #{next_id} принята!\nОжидайте реквизиты..."
        )
        
        # ========== ОТПРАВКА В ГРУППУ ==========
        try:
            group_text = f"""
🆕 <b>НОВАЯ ЗАЯВКА #{next_id}</b>

👤 Клиент: {update.effective_user.first_name}
📞 ID: {context.user_data['client_id']}
💰 Сумма: {amount} TMT
⏰ Время: {deposit['time']}

<b>Отправьте номер телефона для клиента:</b>
(8 цифр, например: 65656565)
            """
            
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=group_text,
                parse_mode='HTML'
            )
            
            logger.info(f"✅ Заявка #{next_id} отправлена в группу {GROUP_CHAT_ID}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки в группу: {e}")
            await update.message.reply_text(f"Ошибка: {e}")
        
        next_id += 1
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Введите число!")
        return WAITING_AMOUNT

# ========== ОБРАБОТКА ГРУППЫ ==========
async def handle_group_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений в группе"""
    
    # Проверяем, что это наша группа
    if update.effective_chat.id != GROUP_CHAT_ID:
        return
    
    # Проверяем, что это админ
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    text = update.message.text.strip()
    
    # Проверяем, 8 ли это цифр
    if text.isdigit() and len(text) == 8:
        # Ищем последнюю заявку без номера
        last_deposit = None
        for deposit in deposits:
            if deposit['status'] == 'waiting' and 'phone' not in deposit:
                last_deposit = deposit
                break
        
        if not last_deposit:
            await update.message.reply_text("❌ Нет заявок, ожидающих номер")
            return
        
        # Форматируем номер
        phone = f"+993 {text[:2]} {text[2:5]} {text[5:]}"
        last_deposit['phone'] = phone
        
        # Отправляем клиенту
        try:
            await context.bot.send_message(
                chat_id=last_deposit['user_id'],
                text=f"💳 <b>РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ</b>\n\n"
                     f"📱 Номер: <code>{phone}</code>\n"
                     f"💰 Сумма: {last_deposit['amount']} TMT\n\n"
                     f"После оплаты отправьте скриншот!",
                parse_mode='HTML'
            )
            
            # В группе подтверждаем
            await update.message.reply_text(
                f"✅ <b>Реквизиты отправлены клиенту #{last_deposit['id']}</b>"
            )
            
            # Создаем кнопку для подтверждения оплаты
            keyboard = [[
                InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"confirm_{last_deposit['id']}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"⏳ Ожидаем скриншот от клиента #{last_deposit['id']}",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    # Команда для админа
    elif text == "/list":
        waiting = [d for d in deposits if d['status'] == 'waiting' and 'phone' not in d]
        
        if not waiting:
            await update.message.reply_text("⏳ Нет ожидающих заявок")
            return
        
        msg = "⏳ <b>Ожидают номер:</b>\n\n"
        for d in waiting:
            msg += f"🆔 #{d['id']} - {d['user_name']} - {d['amount']} TMT\n"
        
        await update.message.reply_text(msg, parse_mode='HTML')

# ========== СКРИНШОТЫ ==========
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото (скриншотов)"""
    
    user_id = update.effective_user.id
    
    # Ищем заявку пользователя
    user_deposit = None
    for deposit in deposits:
        if deposit['user_id'] == user_id and deposit.get('phone') and deposit['status'] == 'waiting':
            user_deposit = deposit
            break
    
    if not user_deposit:
        await update.message.reply_text("❌ Нет активной заявки")
        return
    
    await update.message.reply_text("✅ Скриншот получен! Ожидайте подтверждения")
    
    # Пересылаем в группу
    try:
        photo = update.message.photo[-1]
        
        # Отправляем фото
        await context.bot.send_photo(
            chat_id=GROUP_CHAT_ID,
            photo=photo.file_id,
            caption=f"📸 Скриншот оплаты #{user_deposit['id']}"
        )
        
        # Создаем кнопку для подтверждения
        keyboard = [[
            InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"confirm_{user_deposit['id']}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"✅ Скриншот получен от клиента #{user_deposit['id']}",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки скриншота: {e}")

# ========== ПОДТВЕРЖДЕНИЕ ОПЛАТЫ ==========
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("confirm_"):
        deposit_id = int(query.data.split("_")[1])
        
        # Проверяем админа
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Только администратор", show_alert=True)
            return
        
        # Ищем заявку
        deposit = None
        for d in deposits:
            if d['id'] == deposit_id:
                deposit = d
                break
        
        if not deposit:
            await query.answer("❌ Заявка не найдена", show_alert=True)
            return
        
        # Обновляем статус
        deposit['status'] = 'completed'
        deposit['confirmed_by'] = query.from_user.first_name
        
        # Обновляем сообщение в группе
        await query.edit_message_text(
            f"✅ <b>ПЛАТЕЖ ПОДТВЕРЖДЕН #{deposit_id}</b>"
        )
        
        # Сообщаем клиенту
        try:
            await context.bot.send_message(
                chat_id=deposit['user_id'],
                text=f"🎉 <b>Счет пополнен!</b>\n\n"
                     f"💰 Сумма: {deposit['amount']} TMT\n"
                     f"🆔 Заявка: #{deposit_id}",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"❌ Ошибка отправки клиенту: {e}")

# ========== ОТМЕНА ==========
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено")
    return ConversationHandler.END

# ========== ЗАПУСК ==========
def main():
    """Главная функция запуска"""
    print("=" * 50)
    print("🤖 ЗАПУСКАЕМ ТЕЛЕГРАМ БОТА")
    print("=" * 50)
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ConversationHandler для клиента
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^💰 Пополнить счет$"), handle_deposit_button)
        ],
        states={
            WAITING_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_id)
            ],
            WAITING_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Обработчик группы
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(chat_id=GROUP_CHAT_ID) & ~filters.COMMAND,
        handle_group_text
    ))
    
    print("✅ Бот готов к работе!")
    print("📱 Напишите /start в Telegram")
    print("=" * 50)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':

    main()
