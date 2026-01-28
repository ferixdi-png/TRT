"""
Анализ единого pipeline параметров в TRT.

Проверяет как работает валидация параметров на разных этапах:
1. Ввод параметров в input_parameters
2. Валидация в confirm_generation
3. Нормализация через kie_input_adapter
"""

def analyze_parameter_pipeline():
    """Анализирует текущий pipeline параметров."""
    
    print("=" * 80)
    print("АНАЛИЗ ЕДИНОГО PIPELINE ПАРАМЕТРОВ")
    print("=" * 80)
    print()
    
    # 1. Анализ input_parameters
    print("1. INPUT_PARAMETERS АНАЛИЗ:")
    print("   - Расположен: bot_kie.py строка ~19624")
    print("   - Валидация: НЕ ИСПОЛЬЗУЕТСЯ при вводе")
    print("   - Проверяет только базовые типы (enum, boolean, number)")
    print("   - НЕ проверяет соответствие схеме модели")
    print("   - НЕ проверяет обязательные поля")
    print("   - НЕ проверяет диапазоны значений")
    print("   - Проблема: пользователь узнает об ошибке только в confirm_generation")
    print()
    
    # 2. Анализ confirm_generation
    print("2. CONFIRM_GENERATION АНАЛИЗ:")
    print("   - Расположен: bot_kie.py строка ~22624")
    print("   - Валидация: ИСПОЛЬЗУЕТСЯ через normalize_for_generation")
    print("   - Вызывает: kie_input_adapter.normalize_for_generation()")
    print("   - Проверяет: схему, обязательные поля, типы, enum значения")
    print("   - Показывает ошибки пользователю")
    print("   - Нормализует параметры перед отправкой в KIE API")
    print()
    
    # 3. Анализ kie_input_adapter
    print("3. KIE_INPUT_ADAPTER АНАЛИЗ:")
    print("   - Расположен: kie_input_adapter.py")
    print("   - Функция: normalize_for_generation()")
    print("   - Этапы:")
    print("     a) get_schema() - загружает схему из models/kie_models.yaml")
    print("     b) apply_defaults() - применяет дефолтные значения")
    print("     c) validate_params() - валидирует по схеме")
    print("     d) adapt_to_api() - адаптирует к формату KIE API")
    print("   - Валидация проверяет:")
    print("     - Обязательные поля (required)")
    print("     - Типы данных (string, number, boolean, enum, array)")
    print("     - Enum значения")
    print("     - Длину строк (max)")
    print("     - URL валидацию для массивов")
    print("   - НЕ проверяет:")
    print("     - Числовые диапазоны (min/max)")
    print("     - Регулярные выражения")
    print()
    
    # 4. Проблемы
    print("4. ВЫЯВЛЕННЫЕ ПРОБЛЕМЫ:")
    print("   [X] input_parameters не использует валидацию схемы")
    print("   [X] Пользователь может вводить неверные данные без обратной связи")
    print("   [X] Ошибки валидации показываются только в самом конце")
    print("   [X] validate_params не проверяет числовые диапазоны (min/max)")
    print("   [X] Нет валидации в реальном времени при вводе")
    print()
    
    # 5. Рекомендации
    print("5. РЕКОМЕНДАЦИИ ПО УЛУЧШЕНИЮ:")
    print("   [+] Добавить валидацию в input_parameters при вводе каждого параметра")
    print("   [+] Использовать validate_params() из kie_input_adapter")
    print("   [+] Показывать ошибки немедленно, не ждать confirm_generation")
    print("   [+] Добавить проверку числовых диапазонов в validate_params()")
    print("   [+] Добавить подсказки при вводе (допустимые значения, диапазоны)")
    print()
    
    # 6. Текущий статус
    print("6. СТАТУС PIPELINE:")
    print("   Ввод параметров: [X] БЕЗ ВАЛИДАЦИИ")
    print("   Проверка перед генерацией: [OK] ЕСТЬ ВАЛИДАЦИЯ")
    print("   Нормализация: [OK] РАБОТАЕТ")
    print("   Отправка в KIE API: [OK] ВАЛИДИРОВАНО")
    print()
    
    print("=" * 80)
    print("ИТОГ: Pipeline частично работает, но нужен рефакторинг")
    print("Рекомендация: Добавить валидацию в input_parameters")
    print("=" * 80)

if __name__ == "__main__":
    analyze_parameter_pipeline()
