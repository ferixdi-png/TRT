# TRT_REPORT.md

## ✅ Покрыто

### Команды
| Команда | Где находится | Что делает | Тест(ы) |
| --- | --- | --- | --- |
| `/start` | `bot_kie.py` | Показывает главное меню (welcome + клавиатура). | `tests/test_main_menu.py::test_start_command` |
| `/help` | `bot_kie.py` | Открывает справку/поддержку. | `tests/test_callbacks_smoke.py::test_all_known_callbacks_no_crash` |
| `/balance` | `bot_kie.py` | Показывает баланс/лимиты. | `tests/test_check_balance_button.py` |
| `/models` | `bot_kie.py` | Открывает меню моделей. | `tests/test_callbacks_smoke.py::test_all_known_callbacks_no_crash` |
| `/generate` | `bot_kie.py` | Запускает генерацию (legacy/alias). | `tests/test_e2e_flow.py` |
| `/search` | `bot_kie.py` | Поиск по знаниям/БЗ. | `tests/test_callbacks_smoke.py::test_all_known_callbacks_no_crash` |
| `/ask` | `bot_kie.py` | Вопрос к БЗ. | `tests/test_callbacks_smoke.py::test_all_known_callbacks_no_crash` |
| `/add` | `bot_kie.py` | Добавление знания. | `tests/test_callbacks_smoke.py::test_all_known_callbacks_no_crash` |
| `/reset` | `bot_kie.py` | Сброс сценария, возврат в меню. | `tests/test_navigation_resets_session.py` |
| `/cancel` | `bot_kie.py` | Отмена сценария, возврат в меню. | `tests/test_cancel_unknown.py` |
| `/selftest` | `bot_kie.py` | Self-test диагностика. | `tests/test_callbacks_smoke.py::test_all_known_callbacks_no_crash` |
| `/config_check` | `bot_kie.py` | Проверка конфигурации (admin). | `tests/test_callbacks_smoke.py::test_all_known_callbacks_no_crash` |
| `/admin` | `bot_kie.py` | Админ-меню. | `tests/test_callbacks_smoke.py::test_all_known_callbacks_no_crash` |
| `/payments` | `bot_kie.py` | Админ-платежи. | `tests/test_callbacks_smoke.py::test_all_known_callbacks_no_crash` |
| `/block_user` | `bot_kie.py` | Блок пользователя (admin). | `tests/test_callbacks_smoke.py::test_all_known_callbacks_no_crash` |
| `/unblock_user` | `bot_kie.py` | Разблок пользователя (admin). | `tests/test_callbacks_smoke.py::test_all_known_callbacks_no_crash` |
| `/user_balance` | `bot_kie.py` | Баланс пользователя (admin). | `tests/test_callbacks_smoke.py::test_all_known_callbacks_no_crash` |
| `/add_admin` | `bot_kie.py` | Назначение админа. | `tests/test_callbacks_smoke.py::test_all_known_callbacks_no_crash` |

### ReplyKeyboard
* **Отсутствует** (UI построен на InlineKeyboard).

### Inline-кнопки (callback_data)
> Полный список callback_data из активного UI (bot_kie.py + helpers.py + app/).  
> Для проверки покрытия используется `scripts/verify_button_coverage.py` и smoke-тесты.

**Главное меню / навигация**
* `show_models`, `other_models`, `show_all_models_list`, `back_to_menu`, `back_to_previous_step`, `reset_step`, `cancel`, `help_menu`, `support_contact`

**Каталог/модели**
* `gen_type:`, `category:`, `type_header:`
* `model:`, `modelk:`, `m:`
* `select_model:`, `sel:`, `select_mode:`, `mode:`
* `example:`, `info:`, `start:`
* `show_parameters`

**Параметры/ввод**
* `set_param:`, `edit_param:`, `confirm_param:`
* `add_image`, `skip_image`, `image_done`
* `add_audio`, `skip_audio`
* `back_to_confirmation`

**Генерации/история**
* `confirm_generate`, `retry_generate:`, `retry_delivery:`
* `generate_again`, `gen_view:`, `gen_repeat:`, `gen_history:`, `my_generations`

**Бесплатные/рефералы/бонусы**
* `free_tools`, `claim_gift`, `referral_info`

**Баланс/оплаты**
* `check_balance`, `topup_balance`, `topup_amount:`, `topup_custom`
* `pay_sbp:`, `pay_stars:`, `view_payment_screenshots`, `payment_screenshot_nav:`

**Админ**
* `admin_stats`, `admin_view_generations`, `admin_gen_nav:`, `admin_gen_view:`
* `admin_settings`, `admin_set_currency_rate`, `admin_search`, `admin_add`
* `admin_promocodes`, `admin_broadcast`, `admin_create_broadcast`, `admin_broadcast_stats`
* `admin_test_ocr`, `admin_user_mode`, `admin_back_to_admin`, `admin_user_info:`, `admin_topup_user:`
* `admin_payments_back`, `admin_config_check`

**Обучение/прочее**
* `tutorial_start`, `tutorial_step`, `tutorial_complete`
* `copy_bot`, `all_models`

### Экраны/ветки сценариев
* **Главное меню** → категории/типы генераций → список моделей → карточка модели → ввод параметров → подтверждение → генерация → доставка результата → возврат.
* **Бесплатные модели** → список бесплатных SKU → параметры → генерация → доставка результата.
* **Баланс/оплата** → пополнение → способ оплаты → подтверждение → возврат.
* **История генераций** → просмотр → повтор.
* **Рефералы/партнёрка** → реферальная ссылка → возврат.
* **Админ-панель** → статистика, выплаты, промокоды, рассылки, проверки → возврат.
* **Саппорт/обучение** → контакты/инструкции → возврат.

## ❌ Блокеры/непродуманные сценарии
* Не выявлены в активном UI.  
  Если должны быть активны кнопки/сценарии из legacy-модулей (`5656-main/`, `menu_with_modes.py`, `balance_notifications.py`) — потребуется уточнение. Потенциально затронутые callback_data: `main_menu`, `promo_codes`, `my_bonuses`, `quick:*`, `gen:`, `param_menu:`, `param_input:`, `back_to_params`, `back_to_mode`, `back_to_model:`, `back_to_categories`, `back_to_models`, `show_price_confirmation`.

## 🐞 Исправленные проблемы
* Убрана «мёртвая» кнопка **«Проверить статус»** в итоговой карточке генерации — ранее callback не имел обработчика.  
* Кнопка **«Другие модели»** теперь ведёт на карточку `sora-watermark-remover` и проходит полный сценарий выбора/ввода/генерации.  
* Добавлен обработчик короткого callback `m:` (устранён потенциальный тупик при обрезанном model_id).

## 🧪 Как запускать тесты
* `pytest tests/test_main_menu.py tests/test_other_models_button.py tests/test_callbacks_smoke.py`
* `python scripts/verify_button_coverage.py`

## 📌 Риски под нагрузкой
* Нагрузка на KIE API и доставку медиа: возможны таймауты, требуется контроль ретраев и timeouts.
* GitHub storage (GITHUB_JSON) под высокими нагрузками может стать узким местом: стоит мониторить latency/ретраи.
* Очереди генераций и длительные задачи: важно следить за дедупликацией и корректным сбросом состояний, чтобы избежать «залипания» FSM.
