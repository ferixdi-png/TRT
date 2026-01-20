# Wizard State Machine

## Схема состояния
Каждая сессия содержит:
* `ui_context`: текущий UI контекст (`MAIN_MENU`, `GEN_TYPE_MENU`, `MODEL_MENU`, `FREE_TOOLS_MENU`, `WIZARD`).
* `active_gen_type`: активный тип генерации (только для GEN_TYPE/MODEL меню и WIZARD).
* `active_model_id`: выбранная модель для мастера.
* `state`: текущее состояние мастера.
* `waiting_for`: ожидаемый тип ввода (`text`, `photo`, `audio`, `document`).
* `current_param`: ключ параметра, который сейчас запрашиваем.
* `required`: список обязательных параметров.
* `params`: собранные параметры.
* `has_image_input`: требуется ли изображение.
* `has_audio_input`: требуется ли аудио.

## Основные состояния

### `idle`
* **Описание:** пользователь в меню или вне процесса.
* **Переходы:**
  * `select_model` → `wizard_step`.

### `wizard_step`
* **Описание:** запрос конкретного параметра.
* **waiting_for:** `text | photo | audio | document`.
* **Переходы:**
  * Валидный ввод → следующий параметр или `confirm`.
  * Невалидный ввод → остаёмся в `wizard_step`.
  * `back` → предыдущий параметр.
  * `cancel` → `idle`.

### `confirm`
* **Описание:** подтверждение генерации.
* **Переходы:**
  * `confirm_generate` → `generating`.
  * `back` → `wizard_step`.
  * `cancel` → `idle`.

### `generating`
* **Описание:** процесс генерации.
* **Переходы:**
  * `success` → `result`.
  * `failure` → `idle` с ошибкой.

### `result`
* **Описание:** выдача результата.
* **Переходы:**
  * `generate_again` → `wizard_step`.
  * `back_to_menu` → `idle`.

## Правила переходов

### Back
* Удаляет `current_param` из `params`.
* Возвращает `waiting_for` и `current_param` к предыдущему.
* Пересобирает клавиатуру шага.

### Cancel
* Сбрасывает `state`, `waiting_for`, `current_param`, `params`.
* Возвращает в меню.

### /start и Главное меню
* Безусловный safe reset.
* `ui_context` → `MAIN_MENU`, `active_gen_type` очищается.
* Не сбрасывает баланс/реферальные данные.

## UI Context Rules

### MAIN_MENU
* Всегда очищает `active_gen_type`/`gen_type`.
* Не зависит от прошлого выбранного типа генерации.

### GEN_TYPE_MENU
* Показывает типы генерации.
* `active_gen_type` очищается (mixed menu).

### MODEL_MENU
* Пользователь выбрал тип генерации.
* `active_gen_type` фиксируется до выбора модели.

### FREE_TOOLS_MENU
* Меню смешанных моделей.
* `active_gen_type` очищается (mixed menu).

### WIZARD
* Всегда строится по `model_spec` + schema, а не по меню.
* `active_gen_type` устанавливается из выбранной модели.

## Input Validation
* Несоответствие `waiting_for` → сообщение пользователю + повтор запроса.
* Любой ввод логируется с `outcome=invalid_input` при ошибке.
