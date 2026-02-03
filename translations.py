"""
Translation module for KIE Telegram Bot
Provides translations for Russian and English
"""

TRANSLATIONS = {
    'ru': {
        'welcome_new': (
            '🔥 <b>FERIXDI AI</b> — AI-студия в Telegram\n'
            'Коротко и по делу: попробуй бесплатные, а платные подключишь, если зайдёт.\n\n'
            '✅ <b>Что умею:</b>\n'
            '• 🆓 Сначала тестируй бесплатные инструменты\n'
            '• 🎨 Фото / видео / аудио / текст / апскейл / фон — десятки нейросетей\n'
            '• 🎛️ Гибкие параметры: формат, стиль, соотношение сторон, качество и др.\n'
            '• ⚡️ Быстрый результат без лишних шагов\n'
            '• 💳 Понравится — подключишь расширенные модели\n\n'
            'Как пользоваться:\n'
            '1) Выбери инструмент\n'
            '2) Введи текст или загрузи файл\n'
            '3) Подтверди — получи результат'
        ),
        'welcome_returning': (
            '🔥 <b>FERIXDI AI</b> — AI-студия в Telegram\n'
            'Коротко и по делу: попробуй бесплатные, а платные подключишь, если зайдёт.\n\n'
            '✅ <b>Что умею:</b>\n'
            '• 🆓 Сначала тестируй бесплатные инструменты\n'
            '• 🎨 Фото / видео / аудио / текст / апскейл / фон — десятки нейросетей\n'
            '• 🎛️ Гибкие параметры: формат, стиль, соотношение сторон, качество и др.\n'
            '• ⚡️ Быстрый результат без лишних шагов\n'
            '• 💳 Понравится — подключишь расширенные модели\n\n'
            'Как пользоваться:\n'
            '1) Выбери инструмент\n'
            '2) Введи текст или загрузи файл\n'
            '3) Подтверди — получи результат'
        ),
        'select_language': (
            '🌍 <b>Выберите язык / Choose language</b>\n\n'
            'Select your preferred language:'
        ),
        'language_set': '✅ Язык установлен! / Language set!',
        'generate_free': '🎁 Генерировать бесплатно',
        'balance': '💰 Баланс',
        'models': '🤖 Модели',
        'help': '❓ Помощь',
        'support': '💬 Поддержка',
        'referral': '🎁 Рефералы',
        'my_generations': '📋 Мои генерации',
        'admin_panel': '👑 Админ-панель',
        # Buttons
        'btn_generate_free': '🎁 ГЕНЕРИРОВАТЬ БЕСПЛАТНО ({remaining}/{total})',
        'btn_generate_free_no_left': '🎁 ГЕНЕРИРОВАТЬ БЕСПЛАТНО (0/{total})',
        'btn_invite_friend': '🎁 Пригласи друга → +{bonus} в free tools обоим!',
        'btn_free_tools': '🆓 БЕСПЛАТНЫЕ ИНСТРУМЕНТЫ',
        'btn_all_models': '🤖 Все модели ({count})',
        'btn_claim_gift': '🎰 Получить подарок',
        'btn_balance': '💰 Баланс',
        'btn_my_generations': '📚 Мои генерации',
        'btn_top_up': '💳 Пополнить',
        'btn_invite_friend_short': '🎁 Пригласить друга',
        'btn_how_it_works': '❓ Как это работает?',
        'btn_help': '🆘 Помощь',
        'btn_support': '💬 Поддержка',
        'btn_language': '🌐 Язык',
        'btn_copy_bot': '📋 Скопировать бота',
        'msg_copy_bot_title': '📋 <b>СКОПИРОВАТЬ ЭТОГО БОТА</b> 📋',
        'msg_copy_bot_description': (
            'Этот бот можно скопировать с помощью кода и настроек.\n\n'
            '👨‍💻 <b>Администратор</b> может поделиться:\n'
            '• Исходным кодом бота\n'
            '• Настройками и конфигурацией\n'
            '• Инструкциями по развертыванию\n\n'
            '💡 <b>Свяжитесь с администратором</b> для получения доступа к коду и настройкам.'
        ),
        'btn_admin_panel': '👑 АДМИН ПАНЕЛЬ',
        'btn_back': '◀️ Назад',
        'btn_back_to_menu': '◀️ Главное меню',
        'btn_cancel': '❌ Отмена',
        'btn_all_models_short': '📋 Все модели',
        'btn_check_balance': '💰 Проверить баланс',
        'btn_confirm_generate': '✅ Генерировать',
        'msg_operation_cancelled': (
            '✅ <b>Операция отменена</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            '💡 <b>Что произошло:</b>\n'
            'Вы отменили текущую операцию и вернулись в главное меню.\n\n'
            '💡 <b>Что можно сделать:</b>\n'
            '• Выберите новое действие из меню\n'
            '• Начните новую генерацию\n'
            '• Проверьте баланс или историю\n\n'
            '🔄 <b>Совет:</b> Вы всегда можете вернуться в главное меню командой /start'
        ),
        # Messages
        'msg_referral_bonus': '\n🎁 <b>Отлично!</b> Ты пригласил <b>{count}</b> друзей\n   → Получено <b>+{bonus} бесплатных генераций</b>! 🎉\n\n',
        'msg_full_functionality': (
            '🚀 <b>Быстрый старт:</b>\n'
            '1) Выберите раздел в меню\n'
            '2) Опишите задачу или загрузите файл\n'
            '3) Получите результат\n\n'
            '🎁 <b>Партнерка:</b> +{ref_bonus} генераций в free tools вам и другу\n'
            '🔗 <code>{ref_link}</code>'
        ),
        'error_invalid_language': 'Неверный язык / Invalid language',
        'error_already_claimed': 'Вы уже получили подарок! / You already claimed the gift!',
        'btn_back_to_menu': '◀️ Главное меню',
        'btn_back_to_models': '◀️ Назад к моделям',
        'btn_home': '🏠 Главное меню',
        'btn_skip': '⏭️ Пропустить',
        'btn_top_up_balance': '💳 Пополнить баланс',
        'error_try_start': '❌ Ошибка. Попробуйте /start',
        'btn_start_generation': '🎨 Начать генерацию',
        'msg_referral_title': '🎁 <b>РЕФЕРАЛЬНАЯ СИСТЕМА</b> 🎁',
        'msg_referral_how_it_works': (
            '💡 <b>КАК ЭТО РАБОТАЕТ:</b>\n\n'
            '1) Пригласи друга по своей ссылке\n'
            '2) Друг нажимает /start по ссылке и доходит до главного меню (это активация)\n'
            '3) Вам обоим начисляется <b>+{bonus} бесплатных генераций</b> в free tools'
        ),
        'msg_referral_stats': (
            '📊 <b>ВАША СТАТИСТИКА:</b>\n\n'
            '• Приглашено: <b>{invited}</b>\n'
            '• Активировано: <b>{activated}</b>\n'
            '• Начислено бонусов: <b>{bonus_total}</b> генераций\n'
            '• Доступно в free tools: <b>{remaining}</b> генераций'
        ),
        'msg_referral_important': (
            'Начисление приходит автоматически и только один раз на пользователя.'
        ),
        'msg_referral_link_title': '🔗 <b>ВАША РЕФЕРАЛЬНАЯ ССЫЛКА:</b>',
        'msg_referral_send': (
            '💬 <b>Отправьте эту ссылку другу!</b>\n\n'
            '💡 <b>После его активации:</b>\n'
            '• Вы получите +{bonus} бесплатных генераций в free tools\n'
            '• Ваш друг получит +{bonus} бесплатных генераций в free tools\n'
            '• Бонус начисляется один раз на пользователя 🎉'
        ),
        'gen_type_text_to_image': '✨ Текст в фото',
        'gen_type_image_to_image': '🎨 Фото в фото',
        'gen_type_image_editing': '🖼️ Редактирование фото',
        'gen_type_text_to_video': '🎬 Текст в видео',
        'gen_type_image_to_video': '📸 Фото в видео',
        'gen_type_video_editing': '✂️ Редактирование видео',
        'gen_type_speech_to_video': '🎙️ Речь в видео',
        'gen_type_lip_sync': '👄 Синхронизация губ',
        'gen_type_speech_to_text': '🎙️ Речь в текст',
        'gen_type_text_to_speech': '🗣️ Текст в речь',
        'gen_type_text_to_music': '🎵 Текст в музыку',
        'gen_type_audio_to_audio': '🎧 Обработка аудио',
        'gen_type_desc_text_to_image': 'Создавайте изображения из текста',
        'gen_type_desc_image_to_image': 'Трансформация и стилизация изображений',
        'gen_type_desc_image_editing': 'Редактирование и улучшение изображений',
        'gen_type_desc_text_to_video': 'Создавайте видео из текстового описания',
        'gen_type_desc_image_to_video': 'Превращайте изображения в динамичные видео',
        'gen_type_desc_video_editing': 'Редактирование и обработка видео',
        'gen_type_desc_speech_to_video': 'Создание видео из речи и аудио',
        'gen_type_desc_lip_sync': 'Синхронизация губ с аудио',
        'gen_type_desc_speech_to_text': 'Преобразование речи в текст с высокой точностью',
        'gen_type_desc_text_to_speech': 'Преобразование текста в естественную речь',
        'gen_type_desc_text_to_music': 'Генерация музыки из текстового описания',
        'gen_type_desc_audio_to_audio': 'Обработка и улучшение аудио',
        'msg_gen_type_title': '🎨 <b>{name}</b>',
        'msg_gen_type_description': '📝 <b>Описание:</b>\n{description}',
        'msg_gen_type_free': '🎁 <b>БЕСПЛАТНО:</b> {remaining} генераций free tools доступно!',
        'msg_gen_type_models_available': '🤖 <b>Доступные нейросети ({count}):</b>',
        'msg_gen_type_select_model': '💡 <b>Выберите модель ниже</b>',
        'msg_gen_type_no_models': '❌ Модели для этого типа генерации не найдены.',
        'msg_payment_success': '✅ <b>ОПЛАТА УСПЕШНА!</b> ✅',
        'msg_payment_added': '💰 <b>Зачислено:</b> {amount:.2f} ₽',
        'msg_payment_method': '⭐ <b>Способ:</b> Telegram Stars ({stars} ⭐)',
        'msg_payment_balance': '💳 <b>Ваш баланс:</b> {balance} ₽',
        'msg_payment_use_funds': (
            '🎉 <b>Отлично! Баланс пополнен!</b>\n\n'
            '💡 <b>Что дальше:</b>\n'
            '• Начните генерацию контента прямо сейчас\n'
            '• Используйте любую модель из каталога\n'
            '• Наслаждайтесь премиум возможностями!'
        ),
        'error_session_empty': (
            '💡 <b>Сессия сброшена</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Ваша текущая сессия была сброшена.\n\n'
            '🔄 <b>Что делать:</b>\n'
            '• Вернитесь в главное меню\n'
            '• Выберите модель заново\n'
            '• Начните новую генерацию\n\n'
            '💡 Все ваши предыдущие генерации сохранены в разделе "📚 Мои генерации"'
        ),
        'error_no_data': (
            '⚠️ <b>Данные не получены</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Не удалось получить необходимые данные.\n\n'
            '🔄 <b>Что делать:</b>\n'
            '• Попробуйте ещё раз через несколько секунд\n'
            '• Вернитесь в главное меню и начните заново\n'
            '• Если проблема сохраняется, обратитесь в поддержку'
        ),
        'error_invalid_format': (
            '⚠️ <b>Неверный формат данных</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Введенные данные не соответствуют требуемому формату.\n\n'
            '📝 <b>Что проверить:</b>\n'
            '• Правильность всех введенных параметров\n'
            '• Формат URL (должен начинаться с http:// или https://)\n'
            '• Корректность числовых значений\n\n'
            '💡 Следуйте подсказкам бота на каждом шаге'
        ),
        'error_unknown': (
            '⚠️ <b>Временная проблема</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Возникла временная проблема при обработке запроса.\n\n'
            '🔄 <b>Что делать:</b>\n'
            '• Подождите 10-15 секунд и попробуйте ещё раз\n'
            '• Вернитесь в главное меню и начните заново\n'
            '• Если проблема сохраняется, попробуйте другую модель\n\n'
            '💬 Если проблема повторяется, обратитесь в поддержку'
        ),
        'error_insufficient_balance': (
            '💳 <b>Недостаточно средств</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'На вашем балансе недостаточно средств для этой операции.\n\n'
            '💡 <b>Варианты:</b>\n'
            '• Пополните баланс через кнопку "💳 Пополнить"\n'
            '• Используйте бесплатные генерации (кнопка "🎁 Генерировать бесплатно")\n'
            '• Пригласите друга и получите бонусные генерации'
        ),
        'error_operation_failed': (
            '⚠️ <b>Операция не завершена</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Операция не была завершена успешно.\n\n'
            '🔄 <b>Что делать:</b>\n'
            '• Подождите 10-15 секунд и попробуйте ещё раз\n'
            '• Вернитесь в главное меню и начните заново\n'
            '• Проверьте ваше интернет-соединение'
        ),
        'error_timeout': (
            '⏱️ <b>Превышено время ожидания</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Генерация заняла больше времени, чем обычно.\n\n'
            '💡 <b>Возможные причины:</b>\n'
            '• Сложный запрос требует больше времени обработки\n'
            '• Временная загрузка системы\n'
            '• Проблемы с подключением\n\n'
            '🔄 <b>Что делать:</b>\n'
            '• Подождите ещё немного - генерация может продолжаться\n'
            '• Проверьте "📚 Мои генерации" - результат может уже быть готов\n'
            '• Или попробуйте ещё раз с более простым запросом'
        ),
        'error_network': (
            '🌐 <b>Проблема с подключением</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Обнаружена проблема с интернет-соединением.\n\n'
            '🔄 <b>Что делать:</b>\n'
            '• Проверьте ваше интернет-соединение\n'
            '• Убедитесь, что Wi-Fi или мобильный интернет активен\n'
            '• Подождите несколько секунд и попробуйте ещё раз\n\n'
            '💡 После восстановления подключения повторите операцию'
        ),
        'error_display_generation': (
            '⚠️ <b>Не удалось отобразить результат</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Генерация завершена, но возникла проблема с отображением результата.\n\n'
            '💡 <b>Результат сохранен!</b>\n\n'
            '🔄 <b>Как посмотреть:</b>\n'
            '• Перейдите в раздел "📚 Мои генерации"\n'
            '• Найдите последнюю генерацию в списке\n'
            '• Результат будет доступен там\n\n'
            '💬 Если результат не появился, обратитесь в поддержку'
        ),
        'msg_spinning_wheel': '🎰 Крутим колесо фортуны...',
        'msg_admin_only': 'Эта функция доступна только администратору.',
        'msg_user_mode_enabled': 'Режим пользователя включен',
        'msg_returning_to_admin': 'Возврат в админ-панель',
        'msg_insufficient_funds': '💳 <b>Недостаточно средств</b>\n\n💰 <b>Ваш баланс:</b> {balance} ₽\n💵 <b>Требуется:</b> {required} ₽\n\n💡 <b>Пополните баланс</b> для продолжения генерации.\n\nИли используйте бесплатные генерации, если они доступны ✨',
        'msg_available_generations': '✅ <b>Доступно генераций:</b> {count}\n💳 <b>Ваш баланс:</b> {balance} ₽',
        'msg_unlimited_available': '✅ <b>Доступно:</b> Безлимит',
        'btn_check_balance': '💰 Проверить баланс',
        'btn_back_to_categories': '◀️ Назад к категориям',
        'btn_previous': '◀️ Предыдущая',
        'btn_next': 'Следующая ▶️',
        'btn_back_to_admin': '◀️ Назад в админ-панель',
        'btn_back_to_list': '◀️ Назад к списку',
        'btn_back_to_history': '◀️ Назад к истории',
        'btn_confirm_generate_text': '✅ Генерировать',
        'btn_copy_link': '📋 Скопировать ссылку',
        'btn_all_models_text': '📋 Все модели',
        'btn_z_image_free': '🆓 FAST TOOLS',
        'btn_next_step': '▶️ Далее',
        'btn_complete': '▶️ Завершить',
        'btn_custom_amount': '💰 Своя сумма',
        'btn_return_to_admin': '🔙 Вернуться в админ-панель',
        'btn_view_result': '👁️ Показать результат',
    },
    'en': {
        'welcome_new': (
            'Hi! 👋\n'
            '🔥 <b>{bot_name}</b>\n'
            'Performance creatives: photo, remix, video — fast output.\n\n'
            '🎁 Free generations: {free}/{free_limit}\n'
            '💳 Balance: {stars_balance} Stars\n\n'
            '📌 3 steps: pick a mode → prompt/file → result ✅\n'
            '👇 Choose a mode below.'
        ),
        'welcome_returning': (
            'Hi! 👋\n'
            '🔥 <b>{bot_name}</b>\n'
            'Performance creatives: photo, remix, video — fast output.\n\n'
            '🎁 Free generations: {free}/{free_limit}\n'
            '💳 Balance: {stars_balance} Stars\n\n'
            '📌 3 steps: pick a mode → prompt/file → result ✅\n'
            '👇 Choose a mode below.'
        ),
        'select_language': (
            '🌍 <b>Choose language / Выберите язык</b>\n\n'
            'Select your preferred language:'
        ),
        'language_set': '✅ Language set! / Язык установлен!',
        'generate_free': '🎁 Generate free',
        'balance': '💰 Balance',
        'models': '🤖 Models',
        'help': '❓ Help',
        'support': '💬 Support',
        'referral': '🎁 Referrals',
        'my_generations': '📋 My generations',
        'admin_panel': '👑 Admin panel',
        # Buttons
        'btn_generate_free': '🎁 GENERATE FREE ({remaining}/{total} left)',
        'btn_generate_free_no_left': '🎁 GENERATE FREE (0/{total} left)',
        'btn_invite_friend': '🎁 Invite friend → +{bonus} in free tools for both!',
        'btn_free_tools': '🆓 FREE TOOLS',
        'btn_all_models': '🤖 All Models ({count})',
        'btn_claim_gift': '🎰 Claim Gift',
        'btn_balance': '💰 Balance',
        'btn_my_generations': '📚 My Generations',
        'btn_top_up': '💳 Top Up',
        'btn_invite_friend_short': '🎁 Invite Friend',
        'btn_how_it_works': '❓ How it works?',
        'btn_help': '🆘 Help',
        'btn_support': '💬 Support',
        'btn_language': '🌐 Language / Язык',
        'btn_copy_bot': '📋 Copy This Bot',
        'msg_copy_bot_title': '📋 <b>COPY THIS BOT</b> 📋',
        'msg_copy_bot_description': (
            'This bot can be copied using code and settings.\n\n'
            '👨‍💻 <b>Administrator</b> can share:\n'
            '• Bot source code\n'
            '• Settings and configuration\n'
            '• Deployment instructions\n\n'
            '💡 <b>Contact the administrator</b> to get access to code and settings.'
        ),
        'btn_admin_panel': '👑 ADMIN PANEL',
        'btn_back': '◀️ Back',
        'btn_back_to_menu': '◀️ Main Menu',
        'btn_cancel': '❌ Cancel',
        'btn_all_models_short': '📋 All Models',
        'btn_check_balance': '💰 Check Balance',
        'btn_confirm_generate': '✅ Generate',
        'msg_operation_cancelled': (
            '✅ <b>Operation cancelled</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            '💡 <b>What happened:</b>\n'
            'You cancelled the current operation. All entered data is saved, but generation was not started.\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            '💡 <b>What you can do:</b>\n'
            '• Select a new action from the menu\n'
            '• Start a new generation\n'
            '• Check balance or history\n'
            '• Continue with any other model\n\n'
            '🔄 <b>Tip:</b> You can always return to the main menu with /start'
        ),
        # Messages
        'msg_referral_bonus': '\n🎁 <b>Great!</b> You invited <b>{count}</b> friends\n   → Received <b>+{bonus} free generations</b>! 🎉\n\n',
        'msg_full_functionality': (
            '🚀 <b>Quick start:</b>\n'
            '1) Pick a section from the menu\n'
            '2) Describe the task or upload a file\n'
            '3) Receive the result\n\n'
            '🎁 <b>Referral:</b> +{ref_bonus} free tools generations for both\n'
            '🔗 <code>{ref_link}</code>'
        ),
        'error_invalid_language': 'Invalid language / Неверный язык',
        'error_already_claimed': 'You already claimed the gift! / Вы уже получили подарок!',
        'btn_back_to_menu': '◀️ Main Menu',
        'btn_back_to_models': '◀️ Back to Models',
        'btn_home': '🏠 Main Menu',
        'btn_skip': '⏭️ Skip',
        'btn_top_up_balance': '💳 Top Up Balance',
        'error_try_start': '❌ Error. Try /start',
        'btn_start_generation': '🎨 Start Generation',
        'msg_referral_title': '🎁 <b>REFERRAL SYSTEM</b> 🎁',
        'msg_referral_how_it_works': (
            '💡 <b>HOW IT WORKS:</b>\n\n'
            '1) Invite a friend using your link\n'
            '2) They tap /start from the link and reach the main menu (activation)\n'
            '3) You both receive <b>+{bonus} free generations</b> in free tools'
        ),
        'msg_referral_stats': (
            '📊 <b>YOUR STATISTICS:</b>\n\n'
            '• Invited: <b>{invited}</b>\n'
            '• Activated: <b>{activated}</b>\n'
            '• Bonuses credited: <b>{bonus_total}</b> generations\n'
            '• Available in free tools: <b>{remaining}</b> generations'
        ),
        'msg_referral_important': (
            'Bonus is credited automatically and only once per user.'
        ),
        'msg_referral_link_title': '🔗 <b>YOUR REFERRAL LINK:</b>',
        'msg_referral_send': (
            '💬 <b>Send this link to a friend!</b>\n\n'
            '💡 <b>After activation:</b>\n'
            '• You receive +{bonus} free tools generations\n'
            '• Your friend receives +{bonus} free tools generations\n'
            '• Bonus is credited once per user 🎉'
        ),
        'gen_type_text_to_image': '✨ Text to Image',
        'gen_type_image_to_image': '🎨 Image to Image',
        'gen_type_image_editing': '🖼️ Image Editing',
        'gen_type_text_to_video': '🎬 Text to Video',
        'gen_type_image_to_video': '📸 Image to Video',
        'gen_type_video_editing': '✂️ Video Editing',
        'gen_type_speech_to_video': '🎙️ Speech to Video',
        'gen_type_lip_sync': '👄 Lip Sync',
        'gen_type_speech_to_text': '🎙️ Speech to Text',
        'gen_type_text_to_speech': '🗣️ Text to Speech',
        'gen_type_text_to_music': '🎵 Text to Music',
        'gen_type_audio_to_audio': '🎧 Audio Processing',
        'gen_type_desc_text_to_image': 'Create images from text',
        'gen_type_desc_image_to_image': 'Transform and style images',
        'gen_type_desc_image_editing': 'Edit and enhance images',
        'gen_type_desc_text_to_video': 'Create videos from text descriptions',
        'gen_type_desc_image_to_video': 'Turn images into dynamic videos',
        'gen_type_desc_video_editing': 'Edit and process videos',
        'gen_type_desc_speech_to_video': 'Create videos from speech and audio',
        'gen_type_desc_lip_sync': 'Lip synchronization with audio',
        'gen_type_desc_speech_to_text': 'Convert speech to text with high accuracy',
        'gen_type_desc_text_to_speech': 'Convert text to natural speech',
        'gen_type_desc_text_to_music': 'Generate music from text descriptions',
        'gen_type_desc_audio_to_audio': 'Process and enhance audio',
        'msg_gen_type_title': '🎨 <b>{name}</b>',
        'msg_gen_type_description': '📝 <b>Description:</b>\n{description}',
        'msg_gen_type_free': '🎁 <b>FREE:</b> {remaining} free tools generations available!',
        'msg_gen_type_models_available': '🤖 <b>Available AI models ({count}):</b>',
        'msg_gen_type_select_model': '💡 <b>Select a model below</b>',
        'msg_gen_type_no_models': '❌ No models found for this generation type.',
        'msg_payment_success': '✅ <b>PAYMENT SUCCESSFUL!</b> ✅',
        'msg_payment_added': '💰 <b>Added:</b> {stars} ⭐',
        'msg_payment_method': '⭐ <b>Method:</b> Telegram Stars ({stars} ⭐)',
        'msg_payment_balance': '💳 <b>Your balance:</b> {balance} ⭐',
        'msg_payment_use_funds': (
            '🎉 <b>Great! Balance topped up!</b>\n\n'
            '💡 <b>What\'s next:</b>\n'
            '• Start content generation right now\n'
            '• Use any model from the catalog\n'
            '• Enjoy premium features!'
        ),
        'error_session_empty': (
            '💡 <b>Session Reset</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Your current session was reset.\n\n'
            '🔄 <b>What to do:</b>\n'
            '• Return to main menu\n'
            '• Select a model again\n'
            '• Start a new generation\n\n'
            '💡 All your previous generations are saved in "📚 My Generations" section'
        ),
        'error_no_data': (
            '⚠️ <b>Data Not Received</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Failed to receive required data.\n\n'
            '🔄 <b>What to do:</b>\n'
            '• Try again in a few seconds\n'
            '• Return to main menu and start over\n'
            '• If problem persists, contact support'
        ),
        'error_invalid_format': (
            '⚠️ <b>Invalid Data Format</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Entered data doesn\'t match required format.\n\n'
            '📝 <b>What to check:</b>\n'
            '• Correctness of all entered parameters\n'
            '• URL format (should start with http:// or https://)\n'
            '• Correctness of numeric values\n\n'
            '💡 Follow bot hints at each step'
        ),
        'error_unknown': (
            '⚠️ <b>Temporary Issue</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Temporary issue occurred while processing request.\n\n'
            '🔄 <b>What to do:</b>\n'
            '• Wait 10-15 seconds and try again\n'
            '• Return to main menu and start over\n'
            '• If problem persists, try a different model\n\n'
            '💬 If problem repeats, contact support'
        ),
        'error_insufficient_balance': (
            '💳 <b>Insufficient Balance</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Your balance is insufficient for this operation.\n\n'
            '💡 <b>Options:</b>\n'
            '• Top up balance via "💳 Top Up" button\n'
            '• Use free generations ("🎁 Generate Free" button)\n'
            '• Invite a friend and get bonus generations'
        ),
        'error_operation_failed': (
            '⚠️ <b>Operation Not Completed</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Operation was not completed successfully.\n\n'
            '🔄 <b>What to do:</b>\n'
            '• Wait 10-15 seconds and try again\n'
            '• Return to main menu and start over\n'
            '• Check your internet connection'
        ),
        'error_timeout': (
            '⏱️ <b>Timeout Exceeded</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Generation took longer than usual.\n\n'
            '💡 <b>Possible reasons:</b>\n'
            '• Complex request requires more processing time\n'
            '• Temporary system load\n'
            '• Connection issues\n\n'
            '🔄 <b>What to do:</b>\n'
            '• Wait a bit more - generation may still be running\n'
            '• Check "📚 My Generations" - result may already be ready\n'
            '• Or try again with a simpler request'
        ),
        'error_network': (
            '🌐 <b>Connection Issue</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Internet connection problem detected.\n\n'
            '🔄 <b>What to do:</b>\n'
            '• Check your internet connection\n'
            '• Make sure Wi-Fi or mobile data is active\n'
            '• Wait a few seconds and try again\n\n'
            '💡 After connection is restored, repeat the operation'
        ),
        'error_display_generation': (
            '⚠️ <b>Failed to Display Result</b>\n\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            'Generation completed, but there was an issue displaying the result.\n\n'
            '💡 <b>Result is saved!</b>\n\n'
            '🔄 <b>How to view:</b>\n'
            '• Go to "📚 My Generations" section\n'
            '• Find the latest generation in the list\n'
            '• Result will be available there\n\n'
            '💬 If result doesn\'t appear, contact support'
        ),
        'msg_spinning_wheel': '🎰 Spinning the wheel of fortune...',
        'msg_admin_only': 'This function is available only to administrator.',
        'msg_user_mode_enabled': 'User mode enabled',
        'msg_returning_to_admin': 'Returning to admin panel',
        'msg_insufficient_funds': '💳 <b>Insufficient funds</b>\n\n💰 <b>Your balance:</b> {balance} ⭐\n💵 <b>Required:</b> {required} ⭐\n\n💡 <b>Top up your balance</b> to continue generation.\n\nOr use free generations if available ✨',
        'msg_available_generations': '✅ <b>Available generations:</b> {count}\n💳 <b>Your balance:</b> {balance} ⭐',
        'msg_unlimited_available': '✅ <b>Available:</b> Unlimited',
        'btn_check_balance': '💰 Check Balance',
        'btn_back_to_categories': '◀️ Back to Categories',
        'btn_previous': '◀️ Previous',
        'btn_next': 'Next ▶️',
        'btn_back_to_admin': '◀️ Back to Admin Panel',
        'btn_back_to_list': '◀️ Back to List',
        'btn_back_to_history': '◀️ Back to History',
        'btn_confirm_generate_text': '✅ Generate',
        'btn_copy_link': '📋 Copy Link',
        'btn_all_models_text': '📋 All Models',
        'btn_z_image_free': '🆓 Free models',
        'btn_next_step': '▶️ Next',
        'btn_complete': '▶️ Complete',
        'btn_custom_amount': '💰 Custom Amount',
        'btn_return_to_admin': '🔙 Return to Admin',
        'btn_view_result': '👁️ View Result',
    }
}


def t(key: str, lang: str = 'ru', **kwargs) -> str:
    """Get translated text."""
    translations = TRANSLATIONS.get(lang, TRANSLATIONS['ru'])
    text = translations.get(key, TRANSLATIONS['ru'].get(key, key))
    try:
        return text.format(**kwargs)
    except KeyError:
        return text
