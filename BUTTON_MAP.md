# Button Map

## Main menu
| Button text | Callback data | Handler pattern |
| --- | --- | --- |
| БЕСПЛАТНЫЕ МОДЕЛИ | `free_tools` | `data == "free_tools"` |
| Из текста в фото | `gen_type:text-to-image` | `data.startswith("gen_type:")` |
| Из фото в фото | `gen_type:image-to-image` | `data.startswith("gen_type:")` |
| Из текста в видео | `gen_type:text-to-video` | `data.startswith("gen_type:")` |
| Из фото в видео | `gen_type:image-to-video` | `data.startswith("gen_type:")` |
| Фото редактор | `gen_type:image-edit` | `data.startswith("gen_type:")` |
| Баланс | `check_balance` | `data == "check_balance"` |
| Партнерка | `referral_info` | `data == "referral_info"` |

## Catalog + model cards
| Button text | Callback data | Handler pattern |
| --- | --- | --- |
| Все модели | `show_all_models_list` | `data == "show_all_models_list"` |
| Категория | `category:<category>` | `data.startswith("category:")` |
| Выбор модели | `model:<model_id>` / `modelk:<hash>` | `data.startswith("model:")` / `data.startswith("modelk:")` |
| Старт генерации | `select_model:<model_id>` | `data.startswith("select_model:")` |
| Пример | `example:<model_id>` | `data.startswith("example:")` |
| Инфо | `info:<model_id>` | `data.startswith("info:")` |

## Wizard & confirmation
| Button text | Callback data | Handler pattern |
| --- | --- | --- |
| Подтвердить | `confirm_generate` | `data == "confirm_generate"` |
| Назад | `back_to_previous_step` | `data == "back_to_previous_step"` |
| Показать параметры | `show_parameters` | `data == "show_parameters"` |
| Редактировать параметр | `edit_param:<param>` | `data.startswith("edit_param:")` |
| Установить параметр | `set_param:<param>` | `data.startswith("set_param:")` |
| Назад к моделям | `show_models` | `data == "show_models"` |
| Главное меню | `back_to_menu` | `data == "back_to_menu"` |

## Help & language
| Button text | Callback data | Handler pattern |
| --- | --- | --- |
| Help | `help_menu` | `data == "help_menu"` |
| Support | `support_contact` | `data == "support_contact"` |
| Колесо удачи | `claim_gift` | `data == "claim_gift"` |
| Скопировать бота | `copy_bot` | `data == "copy_bot"` |
| Language RU | `set_language:ru` | `data.startswith("set_language:")` |
| Language EN | `set_language:en` | `data.startswith("set_language:")` |

## Payments & admin
| Button text | Callback data | Handler pattern |
| --- | --- | --- |
| Пополнить баланс | `topup_balance` | `data == "topup_balance"` |
| Быстрое пополнение | `topup_amount:<amount>` | `data.startswith("topup_amount:")` |
| Ввести сумму | `topup_custom` | `data == "topup_custom"` |
| Админ-панель | `admin_stats` | `data == "admin_stats"` |
| История генераций | `admin_view_generations` | `data == "admin_view_generations"` |
| Настройки | `admin_settings` | `data == "admin_settings"` |
| Возврат в меню | `admin_back_to_admin` | `data == "admin_back_to_admin"` |
