# Интеграция меню моделей из каталога

## 📋 Созданные файлы

1. **`app/helpers/models_menu.py`** - Построение меню моделей из каталога
2. **`app/helpers/models_menu_handlers.py`** - Обработчики callback'ов

## 🔄 Интеграция в bot_kie.py

### 1. Обновить обработчик `show_all_models_list`

Найти в `bot_kie.py` (около строки 4674):

```python
if data == "show_all_models_list":
    # ... существующий код ...
```

Заменить на:

```python
if data == "show_all_models_list":
    try:
        await query.answer()
    except:
        pass
    
    logger.info(f"User {user_id} clicked 'show_all_models_list' button")
    
    # Используем новый каталог
    from app.helpers.models_menu_handlers import handle_show_all_models_list
    user_lang = get_user_language(user_id)
    await handle_show_all_models_list(query, user_id, user_lang)
    return SELECTING_MODEL
```

### 2. Обновить обработчик `model:*`

Найти в `bot_kie.py` (около строки 7808 и 8019):

```python
if data.startswith("model:"):
    # ... существующий код ...
```

Заменить на:

```python
if data.startswith("model:") or data.startswith("modelk:"):
    try:
        await query.answer()
    except:
        pass
    
    user_lang = get_user_language(user_id)
    
    # Используем новый каталог
    from app.helpers.models_menu_handlers import handle_model_callback
    success = await handle_model_callback(query, user_id, user_lang, data)
    
    if success:
        return SELECTING_MODEL
    else:
        return ConversationHandler.END
```

### 3. Добавить импорт в начало bot_kie.py

```python
from app.helpers.models_menu import build_models_menu_by_type
from app.kie_catalog import load_catalog, get_model
```

## ✅ Проверка

После интеграции:

1. ✅ Все модели из каталога отображаются
2. ✅ Цены показываются в рублях (×2)
3. ✅ Callback'и работают без падений
4. ✅ Карточки моделей показывают правильную информацию
5. ✅ Валидация наличия модели работает

## 🧪 Тестирование

```python
# Тест меню
from app.helpers.models_menu import build_models_menu_by_type
keyboard = build_models_menu_by_type('ru')
print(f"Keyboard has {len(keyboard.inline_keyboard)} rows")

# Тест карточки
from app.kie_catalog import get_model
from app.helpers.models_menu import build_model_card_text
model = get_model("flux-2/pro-text-to-image")
if model:
    text, kb = build_model_card_text(model, 0, 'ru')
    print(text)
```

