"""
Static list of KIE AI models available in the bot
These models are shown in the menu instead of fetching from API
"""

# Available KIE AI models with their details
KIE_MODELS = [
    {
        "id": "z-image",
        "name": "Z-Image",
        "description": "Эффективная модель генерации изображений от Tongyi-MAI. Фотореалистичный вывод, быстрая производительность Turbo и точный двуязычный рендеринг текста.",
        "category": "Фото",
        "emoji": "🖼️",
        "pricing": "0.8 кредитов за изображение",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание изображения, которое вы хотите сгенерировать (макс. 1000 символов)",
                "required": True,
                "max_length": 1000
            },
            "quality": {
                "type": "string",
                "description": "Качество изображения (Basic = 2K, High = 4K)",
                "required": True,
                "default": "basic",
                "enum": ["basic", "high"]
            }
        }
    },
    {
        "id": "sora-2-pro-image-to-video",
        "name": "🔥 Sora 2 Pro Image-to-Video",
        "description": "⭐ ТОП МОДЕЛЬ! OpenAI Sora 2 Pro - премиальная генерация видео из изображений. Реалистичное движение, Standard/High качество.",
        "category": "Видео",
        "emoji": "🎬",
        "is_featured": True,
        "pricing": "150-630 кредитов (Standard/High, 10-15 сек)",
        "input_params": {
            "image_urls": {
                "type": "array",
                "description": "URL изображения для использования как первый кадр (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB, должно быть публично доступным)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого движения видео (макс. 10000 символов)",
                "required": True,
                "max_length": 10000
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон видео",
                "required": False,
                "default": "landscape",
                "enum": ["portrait", "landscape"]
            },
            "n_frames": {
                "type": "string",
                "description": "Количество кадров (длительность видео)",
                "required": False,
                "default": "10",
                "enum": ["10", "15"]
            },
            "size": {
                "type": "string",
                "description": "Качество видео (Standard = 150/270 кредитов, High = 330/630 кредитов)",
                "required": False,
                "default": "standard",
                "enum": ["standard", "high"]
            },
            "remove_watermark": {
                "type": "boolean",
                "description": "Удалить водяной знак с сгенерированного видео",
                "required": False,
                "default": True
            }
        }
    },
    {
        "id": "sora-watermark-remover",
        "name": "🔥 Sora Watermark Remover",
        "description": "⭐ ТОП МОДЕЛЬ! Удаление водяных знаков с видео Sora 2. AI-детекция и отслеживание движения.",
        "category": "Видео",
        "emoji": "🎬",
        "is_featured": True,
        "pricing": "10 кредитов за использование",
        "input_params": {
            "video_url": {
                "type": "string",
                "description": "URL видео Sora 2 от OpenAI (должен быть публично доступным, начинается с sora.chatgpt.com)",
                "required": True,
                "max_length": 500
            }
        }
    },
    {
        "id": "sora-2-text-to-video",
        "name": "🔥 Sora 2 Text-to-Video",
        "description": "⭐ ТОП МОДЕЛЬ! OpenAI Sora 2 - лучшая модель генерации видео из текста. Реалистичное движение, физическая согласованность, улучшенный контроль над стилем.",
        "category": "Видео",
        "emoji": "🎥",
        "is_featured": True,
        "pricing": "30-40 кредитов за видео (10-15 сек)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого движения видео (макс. 10000 символов)",
                "required": True,
                "max_length": 10000
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон видео",
                "required": True,
                "default": "landscape",
                "enum": ["portrait", "landscape"]
            },
            "n_frames": {
                "type": "string",
                "description": "Количество кадров (длительность видео)",
                "required": False,
                "default": "10",
                "enum": ["10", "15"]
            },
            "remove_watermark": {
                "type": "boolean",
                "description": "Удалить водяной знак с сгенерированного видео",
                "required": False,
                "default": True
            }
        }
    },
    {
        "id": "sora-2-image-to-video",
        "name": "🔥 Sora 2 Image-to-Video",
        "description": "⭐ ТОП МОДЕЛЬ! OpenAI Sora 2 - генерация видео из изображений. Реалистичное движение, 10-15 сек видео.",
        "category": "Видео",
        "emoji": "🎥",
        "is_featured": True,
        "pricing": "35-40 кредитов за видео (10-15 сек)",
        "input_params": {
            "image_urls": {
                "type": "array",
                "description": "URL изображения для первого кадра (JPEG/PNG/WebP, макс. 10MB)",
                "required": True,
                "item_type": "string"
            },
            "prompt": {
                "type": "string",
                "description": "Описание желаемого движения (до 10000 символов)",
                "required": True,
                "max_length": 10000
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон",
                "required": False,
                "default": "landscape",
                "enum": ["portrait", "landscape"]
            },
            "n_frames": {
                "type": "string",
                "description": "Длительность видео",
                "required": False,
                "default": "10",
                "enum": ["10", "15"]
            }
        }
    },
    {
        "id": "sora-2-pro-text-to-video",
        "name": "🔥 Sora 2 Pro Text-to-Video",
        "description": "⭐ ТОП МОДЕЛЬ! OpenAI Sora 2 Pro - премиальная генерация видео из текста. Standard/High качество, 10-15 сек.",
        "category": "Видео",
        "emoji": "🎥",
        "is_featured": True,
        "pricing": "150-630 кредитов (Standard/High, 10-15 сек)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Описание желаемого видео (до 10000 символов)",
                "required": True,
                "max_length": 10000
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон",
                "required": False,
                "default": "landscape",
                "enum": ["portrait", "landscape"]
            },
            "n_frames": {
                "type": "string",
                "description": "Длительность видео",
                "required": False,
                "default": "10",
                "enum": ["10", "15"]
            },
            "size": {
                "type": "string",
                "description": "Качество видео",
                "required": False,
                "default": "standard",
                "enum": ["standard", "high"]
            }
        }
    },
    {
        "id": "kling-2.6/image-to-video",
        "name": "Kling 2.6 Image-to-Video",
        "description": "Kling AI модель для генерации видео из изображений с синхронизированным аудио, речью, фоновыми звуками и звуковыми эффектами. Создает реалистичные видео с возможностью добавления звука.",
        "category": "Видео",
        "emoji": "🎬",
        "pricing": "55-220 кредитов в зависимости от длительности и наличия звука",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого движения и действий в видео (макс. 1000 символов)",
                "required": True,
                "max_length": 1000
            },
            "image_input": {
                "type": "array",
                "description": "Изображение для генерации видео (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string"
            },
            "sound": {
                "type": "boolean",
                "description": "Добавить звук в видео (речь, фоновые звуки, звуковые эффекты)",
                "required": True,
                "default": False
            },
            "duration": {
                "type": "string",
                "description": "Длительность видео в секундах",
                "required": True,
                "default": "5",
                "enum": ["5", "10"]
            }
        }
    },
    {
        "id": "kling-2.6/text-to-video",
        "name": "Kling 2.6 Text-to-Video",
        "description": "Kling AI модель для генерации видео из текста с синхронизированным аудио, речью, фоновыми звуками и звуковыми эффектами. Создает реалистичные видео только из текстового описания без необходимости изображения.",
        "category": "Видео",
        "emoji": "🎥",
        "pricing": "55-220 кредитов в зависимости от длительности и наличия звука",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого видео с визуальными и диалоговыми элементами (макс. 1000 символов). Пример: \"Visual: [описание сцены]. Dialog: [персонаж, голос] говорит: [текст]\"",
                "required": True,
                "max_length": 1000
            },
            "sound": {
                "type": "boolean",
                "description": "Добавить звук в видео (речь, фоновые звуки, звуковые эффекты)",
                "required": True,
                "default": False
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон видео",
                "required": True,
                "default": "1:1",
                "enum": ["1:1", "16:9", "9:16"]
            },
            "duration": {
                "type": "string",
                "description": "Длительность видео в секундах",
                "required": True,
                "default": "5",
                "enum": ["5", "10"]
            }
        }
    },
    {
        "id": "kling-2.6/motion-control",
        "name": "Kling 2.6 Motion Control",
        "description": "Перенос движений с референсного видео на изображение персонажа. Создает анимацию с точным копированием движений.",
        "category": "Видео",
        "emoji": "🎭",
        "pricing": "6-9 кредитов за секунду в зависимости от разрешения",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Описание желаемого результата (макс. 2500 символов)",
                "required": False,
                "max_length": 2500
            },
            "input_urls": {
                "type": "array",
                "description": "URL изображения персонажа (JPEG/PNG, макс. 10MB, мин. 300px)",
                "required": True,
                "item_type": "string"
            },
            "video_urls": {
                "type": "array",
                "description": "URL референсного видео с движениями (MP4/MOV, макс. 100MB, 3-30 сек)",
                "required": True,
                "item_type": "string"
            },
            "character_orientation": {
                "type": "string",
                "description": "Ориентация персонажа: image (как на фото, макс 10с) или video (как в видео, макс 30с)",
                "required": True,
                "default": "video",
                "enum": ["image", "video"]
            },
            "mode": {
                "type": "string",
                "description": "Разрешение выходного видео",
                "required": True,
                "default": "720p",
                "enum": ["720p", "1080p"]
            }
        }
    },
    {
        "id": "flux-2/pro-image-to-image",
        "name": "Flux 2 Pro Image-to-Image",
        "description": "Black Forest Labs модель Flux 2 Pro для генерации изображений из референсов. Фотореалистичная детализация, сильная согласованность с несколькими референсами и точный рендеринг текста. Поддержка до 8 референсных изображений без дополнительной платы.",
        "category": "Фото",
        "emoji": "🎨",
        "pricing": "5 кредитов (1K) или 7 кредитов (2K)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого изображения (от 3 до 5000 символов)",
                "required": True,
                "min_length": 3,
                "max_length": 5000
            },
            "image_input": {
                "type": "array",
                "description": "Референсные изображения для генерации (1-8 изображений, форматы: JPEG, PNG, WebP, макс. 10MB каждое)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 8
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон для сгенерированного изображения. Выберите 'auto' для соответствия первому входному изображению",
                "required": True,
                "default": "1:1",
                "enum": ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "auto"]
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение выходного изображения (1K = 5 кредитов, 2K = 7 кредитов)",
                "required": True,
                "default": "1K",
                "enum": ["1K", "2K"]
            }
        }
    },
    {
        "id": "flux-2/pro-text-to-image",
        "name": "Flux 2 Pro Text-to-Image",
        "description": "Black Forest Labs модель Flux 2 Pro для генерации изображений из текста. Фотореалистичная детализация, сильная согласованность и точный рендеринг текста с гибким контролем. Создает высококачественные изображения только из текстового описания.",
        "category": "Фото",
        "emoji": "✨",
        "pricing": "5 кредитов (1K) или 7 кредитов (2K)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого изображения (от 3 до 5000 символов)",
                "required": True,
                "min_length": 3,
                "max_length": 5000
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон для сгенерированного изображения",
                "required": True,
                "default": "1:1",
                "enum": ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "auto"]
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение выходного изображения (1K = 5 кредитов, 2K = 7 кредитов)",
                "required": True,
                "default": "1K",
                "enum": ["1K", "2K"]
            }
        }
    },
    {
        "id": "flux-2/flex-image-to-image",
        "name": "Flux 2 Flex Image-to-Image",
        "description": "Black Forest Labs модель Flux 2 Flex для генерации изображений из референсов. Фотореалистичная детализация, сильная согласованность с несколькими референсами и точный рендеринг текста. Поддержка до 8 референсных изображений без дополнительной платы. Более высокая цена, но с расширенными возможностями.",
        "category": "Фото",
        "emoji": "🎭",
        "pricing": "14 кредитов (1K) или 24 кредита (2K)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого изображения (от 3 до 5000 символов)",
                "required": True,
                "min_length": 3,
                "max_length": 5000
            },
            "image_input": {
                "type": "array",
                "description": "Референсные изображения для генерации (1-8 изображений, форматы: JPEG, PNG, WebP, макс. 10MB каждое)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 8
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон для сгенерированного изображения. Выберите 'auto' для соответствия первому входному изображению",
                "required": True,
                "default": "1:1",
                "enum": ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "auto"]
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение выходного изображения (1K = 14 кредитов, 2K = 24 кредита)",
                "required": True,
                "default": "1K",
                "enum": ["1K", "2K"]
            }
        }
    },
    {
        "id": "flux-2/flex-text-to-image",
        "name": "Flux 2 Flex Text-to-Image",
        "description": "Black Forest Labs модель Flux 2 Flex для генерации изображений из текста. Фотореалистичная детализация, сильная согласованность и точный рендеринг текста с гибким контролем. Создает высококачественные изображения только из текстового описания с расширенными возможностями.",
        "category": "Фото",
        "emoji": "🌟",
        "pricing": "14 кредитов (1K) или 24 кредита (2K)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого изображения (от 3 до 5000 символов)",
                "required": True,
                "min_length": 3,
                "max_length": 5000
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон для сгенерированного изображения",
                "required": True,
                "default": "1:1",
                "enum": ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "auto"]
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение выходного изображения (1K = 14 кредитов, 2K = 24 кредита)",
                "required": True,
                "default": "1K",
                "enum": ["1K", "2K"]
            }
        }
    },
    {
        "id": "topaz/image-upscale",
        "name": "Topaz Image Upscale",
        "description": "Topaz Labs модель для увеличения разрешения изображений с высоким качеством. Восстанавливает детали, улучшает текстуры и повышает четкость низкокачественных изображений. Поддержка увеличения до 8K.",
        "category": "Фото",
        "emoji": "🔍",
        "pricing": "10 кредитов (≤2K), 20 кредитов (4K), 40 кредитов (8K)",
        "input_params": {
            "image_input": {
                "type": "array",
                "description": "Изображение для увеличения разрешения (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "upscale_factor": {
                "type": "string",
                "description": "Коэффициент увеличения разрешения (1x = ≤2K: 10 кредитов, 2x/4x = 4K: 20 кредитов, 8x = 8K: 40 кредитов)",
                "required": True,
                "default": "2",
                "enum": ["1", "2", "4", "8"]
            }
        }
    },
    {
        "id": "kling/v2-5-turbo-text-to-video-pro",
        "name": "Kling 2.5 Turbo Text-to-Video Pro",
        "description": "Последняя модель генерации видео от Kuaishou Kling. Улучшенное следование промпту, более плавное движение, согласованные художественные стили и реалистичная симуляция физики. Создает высококачественные видео из текста.",
        "category": "Видео",
        "emoji": "⚡",
        "pricing": "42 кредита (5с) или 84 кредита (10с)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого видео (макс. 2500 символов)",
                "required": True,
                "max_length": 2500
            },
            "duration": {
                "type": "string",
                "description": "Длительность видео в секундах (5с = 42 кредита, 10с = 84 кредита)",
                "required": False,
                "default": "5",
                "enum": ["5", "10"]
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон видео",
                "required": False,
                "default": "16:9",
                "enum": ["16:9", "9:16", "1:1"]
            },
            "negative_prompt": {
                "type": "string",
                "description": "Что избегать в видео (макс. 2500 символов, опционально)",
                "required": False,
                "max_length": 2500
            },
            "cfg_scale": {
                "type": "number",
                "description": "CFG scale - насколько близко следовать промпту (0-1, шаг 0.1)",
                "required": False,
                "default": 0.5,
                "min": 0,
                "max": 1,
                "step": 0.1
            }
        }
    },
    {
        "id": "kling/v2-5-turbo-image-to-video-pro",
        "name": "Kling 2.5 Turbo Image-to-Video Pro",
        "description": "Последняя модель генерации видео из изображений от Kuaishou Kling. Улучшенное следование промпту, более плавное движение, согласованные художественные стили и реалистичная симуляция физики. Создает высококачественные видео из изображений.",
        "category": "Видео",
        "emoji": "🎞️",
        "pricing": "42 кредита (5с) или 84 кредита (10с)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого движения в видео (макс. 2500 символов)",
                "required": True,
                "max_length": 2500
            },
            "image_input": {
                "type": "array",
                "description": "Изображение для генерации видео (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "duration": {
                "type": "string",
                "description": "Длительность видео в секундах (5с = 42 кредита, 10с = 84 кредита)",
                "required": False,
                "default": "5",
                "enum": ["5", "10"]
            },
            "negative_prompt": {
                "type": "string",
                "description": "Что избегать в видео (макс. 2496 символов, опционально)",
                "required": False,
                "max_length": 2496
            },
            "cfg_scale": {
                "type": "number",
                "description": "CFG scale - насколько близко следовать промпту (0-1, шаг 0.1)",
                "required": False,
                "default": 0.5,
                "min": 0,
                "max": 1,
                "step": 0.1
            }
        }
    },
    {
        "id": "wan/2-5-image-to-video",
        "name": "WAN 2.5 Image-to-Video",
        "description": "Alibaba WAN 2.5 API для кинематографической генерации видео из изображений. Нативно синхронизирует визуал с диалогом, фоновыми звуками и музыкой. Поддержка разрешений 720p и 1080p.",
        "category": "Видео",
        "emoji": "🎬",
        "pricing": "12 кредитов/сек (720p) или 20 кредитов/сек (1080p)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого движения в видео (макс. 800 символов)",
                "required": True,
                "max_length": 800
            },
            "image_input": {
                "type": "array",
                "description": "Изображение для использования как первый кадр (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "duration": {
                "type": "string",
                "description": "Длительность видео в секундах",
                "required": False,
                "default": "5",
                "enum": ["5", "10"]
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение видео (720p = 12 кредитов/сек, 1080p = 20 кредитов/сек)",
                "required": False,
                "default": "720p",
                "enum": ["720p", "1080p"]
            },
            "negative_prompt": {
                "type": "string",
                "description": "Негативный промпт - что избегать в видео (макс. 500 символов, опционально)",
                "required": False,
                "max_length": 500
            },
            "enable_prompt_expansion": {
                "type": "boolean",
                "description": "Включить переписывание промпта с помощью LLM",
                "required": False,
                "default": True
            }
        }
    },
    {
        "id": "wan/2-5-text-to-video",
        "name": "WAN 2.5 Text-to-Video",
        "description": "Alibaba WAN 2.5 API для кинематографической генерации видео из текста. Нативно синхронизирует визуал с диалогом, фоновыми звуками и музыкой. Поддержка разрешений 720p и 1080p.",
        "category": "Видео",
        "emoji": "🎥",
        "pricing": "12 кредитов/сек (720p) или 20 кредитов/сек (1080p)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого видео (макс. 800 символов, поддерживает китайский и английский)",
                "required": True,
                "max_length": 800
            },
            "duration": {
                "type": "string",
                "description": "Длительность видео в секундах",
                "required": False,
                "default": "5",
                "enum": ["5", "10"]
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон видео",
                "required": False,
                "default": "16:9",
                "enum": ["16:9", "9:16", "1:1"]
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение видео (720p = 12 кредитов/сек, 1080p = 20 кредитов/сек)",
                "required": False,
                "default": "720p",
                "enum": ["720p", "1080p"]
            },
            "negative_prompt": {
                "type": "string",
                "description": "Негативный промпт - что избегать в видео (макс. 500 символов, опционально)",
                "required": False,
                "max_length": 500
            },
            "enable_prompt_expansion": {
                "type": "boolean",
                "description": "Включить переписывание промпта с помощью LLM (улучшает результаты для коротких промптов, но увеличивает время обработки)",
                "required": False,
                "default": True
            }
        }
    },
    {
        "id": "wan/2-6-text-to-video",
        "name": "WAN 2.6 Text-to-Video",
        "description": "Alibaba WAN 2.6 - новейшая модель генерации видео из текста. Поддержка 720p и 1080p, длительность до 15 секунд, режим multi-shots для переходов между кадрами.",
        "category": "Видео",
        "emoji": "🎥",
        "pricing": "54-243 ₽ в зависимости от длительности и разрешения",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого видео (макс. 5000 символов, поддерживает китайский и английский)",
                "required": True,
                "max_length": 5000
            },
            "duration": {
                "type": "string",
                "description": "Длительность видео в секундах",
                "required": False,
                "default": "5",
                "enum": ["5", "10", "15"]
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение видео",
                "required": False,
                "default": "1080p",
                "enum": ["720p", "1080p"]
            },
            "multi_shots": {
                "type": "boolean",
                "description": "Режим мультикадров - создаёт видео с переходами между несколькими кадрами вместо одного непрерывного",
                "required": False,
                "default": False
            }
        }
    },
    {
        "id": "wan/2-2-animate-move",
        "name": "WAN 2.2 Animate Move",
        "description": "Alibaba Tongyi Lab модель для генерации реалистичных видео персонажей с движением, выражениями и освещением. Поддерживает режим анимации для оживления статических изображений и режим замены для бесшовной замены персонажей в существующих клипах.",
        "category": "Видео",
        "emoji": "🎭",
        "pricing": "6 кредитов/сек (480p), 9.5 кредитов/сек (580p), 12.5 кредитов/сек (720p)",
        "input_params": {
            "video_input": {
                "type": "array",
                "description": "Входное видео для замены персонажа (1 видео, форматы: MP4, QuickTime, Matroska, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "image_input": {
                "type": "array",
                "description": "Изображение персонажа для замены (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB). Если изображение не соответствует соотношению сторон, оно будет изменено и обрезано по центру.",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение сгенерированного видео (480p = 6 кредитов/сек, 580p = 9.5 кредитов/сек, 720p = 12.5 кредитов/сек)",
                "required": False,
                "default": "480p",
                "enum": ["480p", "580p", "720p"]
            }
        }
    },
    {
        "id": "wan/2-2-animate-replace",
        "name": "WAN 2.2 Animate Replace",
        "description": "Alibaba Tongyi Lab модель для бесшовной замены персонажей в существующих видео. Генерирует реалистичные видео с движением, выражениями и освещением. Режим замены для подстановки персонажей в существующие клипы.",
        "category": "Видео",
        "emoji": "🔄",
        "pricing": "6 кредитов/сек (480p), 9.5 кредитов/сек (580p), 12.5 кредитов/сек (720p)",
        "input_params": {
            "video_input": {
                "type": "array",
                "description": "Входное видео для замены персонажа (1 видео, форматы: MP4, QuickTime, Matroska, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "image_input": {
                "type": "array",
                "description": "Изображение персонажа для замены (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB). Если изображение не соответствует соотношению сторон, оно будет изменено и обрезано по центру.",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение сгенерированного видео (480p = 6 кредитов/сек, 580p = 9.5 кредитов/сек, 720p = 12.5 кредитов/сек)",
                "required": False,
                "default": "480p",
                "enum": ["480p", "580p", "720p"]
            }
        }
    },
    {
        "id": "hailuo/02-text-to-video-pro",
        "name": "Hailuo 02 Text-to-Video Pro",
        "description": "Продвинутая модель генерации видео от Minimax Hailuo 02. Превращает текст в короткие кинематографические клипы. Поддержка высококачественного вывода до 1080P с реалистичным движением, симуляцией физики и точным контролем камеры. Генерирует 6-секундное 1080p видео.",
        "category": "Видео",
        "emoji": "🎞️",
        "pricing": "9.5 кредитов/сек (1080p, 6 секунд = 57 кредитов)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого видео (макс. 1500 символов)",
                "required": True,
                "max_length": 1500
            },
            "prompt_optimizer": {
                "type": "boolean",
                "description": "Использовать оптимизатор промпта модели",
                "required": False,
                "default": True
            }
        }
    },
    {
        "id": "hailuo/02-image-to-video-pro",
        "name": "Hailuo 02 Image-to-Video Pro",
        "description": "Продвинутая модель генерации видео от Minimax Hailuo 02. Превращает изображения в короткие кинематографические клипы. Поддержка высококачественного вывода до 1080P с реалистичным движением, симуляцией физики и точным контролем камеры. Генерирует 6-секундное 1080p видео из изображения.",
        "category": "Видео",
        "emoji": "🎬",
        "pricing": "9.5 кредитов/сек (1080p, 6 секунд = 57 кредитов)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемой анимации видео (макс. 1500 символов)",
                "required": True,
                "max_length": 1500
            },
            "image_input": {
                "type": "array",
                "description": "Входное изображение для анимации (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "end_image_url": {
                "type": "string",
                "description": "URL изображения для использования как последний кадр видео (опционально)",
                "required": False
            },
            "prompt_optimizer": {
                "type": "boolean",
                "description": "Использовать оптимизатор промпта модели",
                "required": False,
                "default": True
            }
        }
    },
    {
        "id": "hailuo/02-image-to-video-standard",
        "name": "Hailuo 02 Image-to-Video Standard",
        "description": "Стандартная модель генерации видео от Minimax Hailuo 02. Превращает изображения в короткие кинематографические клипы. Поддержка разрешений 512P и 768P с реалистичным движением и симуляцией физики.",
        "category": "Видео",
        "emoji": "🎥",
        "pricing": "2 кредита/сек (512P) или 5 кредитов/сек (768P)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого видео (макс. 1500 символов)",
                "required": True,
                "max_length": 1500
            },
            "image_input": {
                "type": "array",
                "description": "Изображение для использования как первый кадр видео (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "end_image_url": {
                "type": "string",
                "description": "URL изображения для использования как последний кадр видео (опционально)",
                "required": False
            },
            "duration": {
                "type": "string",
                "description": "Длительность видео в секундах (10 секунд не поддерживается для 1080p, но здесь нет 1080p)",
                "required": False,
                "default": "6",
                "enum": ["6", "10"]
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение видео (512P = 2 кредита/сек, 768P = 5 кредитов/сек)",
                "required": False,
                "default": "768P",
                "enum": ["512P", "768P"]
            },
            "prompt_optimizer": {
                "type": "boolean",
                "description": "Использовать оптимизатор промпта модели",
                "required": False,
                "default": True
            }
        }
    },
    {
        "id": "hailuo/02-text-to-video-standard",
        "name": "Hailuo 02 Text-to-Video Standard",
        "description": "Стандартная модель генерации видео от Minimax Hailuo 02. Превращает текст в короткие кинематографические клипы. Поддержка разрешения 768P с реалистичным движением и симуляцией физики.",
        "category": "Видео",
        "emoji": "🎞️",
        "pricing": "5 кредитов/сек (768P)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого видео (макс. 1500 символов)",
                "required": True,
                "max_length": 1500
            },
            "duration": {
                "type": "string",
                "description": "Длительность видео в секундах (10 секунд не поддерживается для 1080p, но здесь нет 1080p)",
                "required": False,
                "default": "6",
                "enum": ["6", "10"]
            },
            "prompt_optimizer": {
                "type": "boolean",
                "description": "Использовать оптимизатор промпта модели",
                "required": False,
                "default": True
            }
        }
    },
    {
        "id": "topaz/video-upscale",
        "name": "Topaz Video Upscale",
        "description": "Профессиональное улучшение видео с помощью AI. Восстанавливает детали, уменьшает шум и обеспечивает высококачественное увеличение разрешения до 1080p или 4K.",
        "category": "Видео",
        "emoji": "📹",
        "pricing": "12 кредитов/сек",
        "input_params": {
            "video_input": {
                "type": "array",
                "description": "Видео для увеличения разрешения (1 видео, форматы: MP4, QuickTime, Matroska, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "upscale_factor": {
                "type": "string",
                "description": "Коэффициент увеличения разрешения (1x, 2x, 4x)",
                "required": False,
                "default": "2",
                "enum": ["1", "2", "4"]
            }
        }
    },
    {
        "id": "kling/v1-avatar-standard",
        "name": "Kling AI Avatar Standard",
        "description": "Генерация реалистичных говорящих аватаров из фотографий и аудио. Контроль эмоций, выражений и темпа через промпт. Точная синхронизация губ и постоянная идентичность. Идеально для образования, маркетинга, соцсетей и виртуальных инфлюенсеров. Разрешение 720P.",
        "category": "Видео",
        "emoji": "👤",
        "pricing": "8 кредитов/сек (720P), до 15 секунд",
        "input_params": {
            "image_input": {
                "type": "array",
                "description": "Изображение для использования как аватар (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "audio_input": {
                "type": "array",
                "description": "Аудиофайл (1 файл, форматы: MPEG, WAV, AAC, MP4, OGG, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "prompt": {
                "type": "string",
                "description": "Промпт для генерации видео (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            }
        }
    },
    {
        "id": "kling/ai-avatar-v1-pro",
        "name": "Kling AI Avatar Pro",
        "description": "Генерация реалистичных говорящих аватаров из фотографий и аудио. Контроль эмоций, выражений и темпа через промпт. Точная синхронизация губ и постоянная идентичность. Идеально для образования, маркетинга, соцсетей и виртуальных инфлюенсеров. Разрешение 1080P.",
        "category": "Видео",
        "emoji": "👥",
        "pricing": "16 кредитов/сек (1080P), до 15 секунд",
        "input_params": {
            "image_input": {
                "type": "array",
                "description": "Изображение для использования как аватар (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "audio_input": {
                "type": "array",
                "description": "Аудиофайл (1 файл, форматы: MPEG, WAV, AAC, MP4, OGG, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "prompt": {
                "type": "string",
                "description": "Промпт для генерации видео (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            }
        }
    },
    {
        "id": "bytedance/seedream-v4-text-to-image",
        "name": "Seedream V4 Text-to-Image",
        "description": "Новое поколение модели от ByteDance, объединяющая генерацию изображений из текста, редактирование с пакетной согласованностью, высокой скоростью и профессиональным качеством вывода. Цена не зависит от разрешения, определяется только количеством возвращаемых изображений.",
        "category": "Изображения",
        "emoji": "🎨",
        "pricing": "5 кредитов за изображение",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание для генерации изображения (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "image_size": {
                "type": "string",
                "description": "Размер генерируемого изображения (соотношение сторон)",
                "required": False,
                "default": "square_hd",
                "enum": ["square", "square_hd", "portrait_4_3", "portrait_3_2", "portrait_16_9", "landscape_4_3", "landscape_3_2", "landscape_16_9", "landscape_21_9"]
            },
            "image_resolution": {
                "type": "string",
                "description": "Разрешение изображения (1K, 2K, 4K). Финальное разрешение определяется комбинацией image_size и image_resolution",
                "required": False,
                "default": "1K",
                "enum": ["1K", "2K", "4K"]
            },
            "max_images": {
                "type": "number",
                "description": "Максимальное количество изображений (1-6). Должно совпадать с количеством, указанным в промпте",
                "required": False,
                "default": 1,
                "min": 1,
                "max": 6,
                "step": 1
            }
        }
    },
    {
        "id": "bytedance/seedream-v4-edit",
        "name": "Seedream V4 Edit",
        "description": "Новое поколение модели от ByteDance для редактирования изображений. Объединяет редактирование изображений с пакетной согласованностью, высокой скоростью и профессиональным качеством вывода. Цена не зависит от разрешения, определяется только количеством возвращаемых изображений.",
        "category": "Изображения",
        "emoji": "✏️",
        "pricing": "5 кредитов за изображение",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание для редактирования изображения (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "image_input": {
                "type": "array",
                "description": "Список изображений для редактирования (до 10 изображений, форматы: JPEG, PNG, WebP, макс. 10MB каждое)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 10
            },
            "image_size": {
                "type": "string",
                "description": "Размер генерируемого изображения (соотношение сторон)",
                "required": False,
                "default": "square_hd",
                "enum": ["square", "square_hd", "portrait_4_3", "portrait_3_2", "portrait_16_9", "landscape_4_3", "landscape_3_2", "landscape_16_9", "landscape_21_9"]
            },
            "image_resolution": {
                "type": "string",
                "description": "Разрешение изображения (1K, 2K, 4K). Финальное разрешение определяется комбинацией image_size и image_resolution",
                "required": False,
                "default": "1K",
                "enum": ["1K", "2K", "4K"]
            },
            "max_images": {
                "type": "number",
                "description": "Максимальное количество изображений (1-6). Должно совпадать с количеством, указанным в промпте",
                "required": False,
                "default": 1,
                "min": 1,
                "max": 6,
                "step": 1
            }
        }
    },
    {
        "id": "recraft/remove-background",
        "name": "Recraft Remove Background",
        "description": "Точное удаление фона от Recraft AI. Отделяет объекты от любого фона и выдает чистые прозрачные результаты. Оптимизировано для бесшовной интеграции в веб-сайты, платформы электронной коммерции и творческие рабочие процессы.",
        "category": "Изображения",
        "emoji": "✂️",
        "pricing": "1 кредит за изображение",
        "input_params": {
            "image_input": {
                "type": "array",
                "description": "Изображение для удаления фона (1 изображение, форматы: PNG, JPG, WEBP, макс. 5MB, макс. 16MP, макс. размер 4096px, мин. размер 256px)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            }
        }
    },
    {
        "id": "recraft/crisp-upscale",
        "name": "Recraft Crisp Upscale",
        "description": "Превращает размытые фотографии в кристально четкие шедевры. Использует продвинутый AI для профессиональных результатов. Бесплатный апскейлер изображений с возможностями профессионального уровня.",
        "category": "Изображения",
        "emoji": "🔍",
        "pricing": "0.5 кредита за апскейл",
        "input_params": {
            "image_input": {
                "type": "array",
                "description": "Изображение для увеличения разрешения (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            }
        }
    },
    {
        "id": "ideogram/v3-reframe",
        "name": "Ideogram V3 Reframe",
        "description": "Специализированная модель image-to-image на базе Ideogram 3.0. Интеллектуально расширяет и адаптирует изображения для различных соотношений сторон и разрешений. Использует продвинутый AI outpainting, сохраняя визуальную согласованность и позволяя творческое изменение кадра для цифрового, печатного и видео контента.",
        "category": "Изображения",
        "emoji": "🖼️",
        "pricing": "3.5 кредита (Turbo), 7 кредитов (Balanced) или 10 кредитов (Quality) за изображение",
        "input_params": {
            "image_input": {
                "type": "array",
                "description": "Изображение для изменения кадра (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "image_size": {
                "type": "string",
                "description": "Разрешение для рефреймированного изображения",
                "required": True,
                "default": "square_hd",
                "enum": ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]
            },
            "rendering_speed": {
                "type": "string",
                "description": "Скорость рендеринга (TURBO = 3.5 кредита, BALANCED = 7 кредитов, QUALITY = 10 кредитов)",
                "required": False,
                "default": "BALANCED",
                "enum": ["TURBO", "BALANCED", "QUALITY"]
            },
            "style": {
                "type": "string",
                "description": "Тип стиля для генерации. Нельзя использовать вместе с style_codes",
                "required": False,
                "default": "AUTO",
                "enum": ["AUTO", "GENERAL", "REALISTIC", "DESIGN"]
            },
            "num_images": {
                "type": "string",
                "description": "Количество изображений (1-4)",
                "required": False,
                "default": "1",
                "enum": ["1", "2", "3", "4"]
            }
        }
    },
    {
        "id": "wan/2-2-a14b-speech-to-video-turbo",
        "name": "WAN 2.2 A14B Speech-to-Video Turbo",
        "description": "Революционная AI модель от Alibaba, превращающая статические изображения и аудио клипы в динамичные, выразительные видео. Идеально для создателей контента, маркетологов и педагогов. Бесшовная интеграция и непревзойденное качество генерации видео.",
        "category": "Видео",
        "emoji": "🎤",
        "pricing": "12 кредитов/сек (480P), 18 кредитов/сек (580P), 24 кредита/сек (720P)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовый промпт для генерации видео (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "image_input": {
                "type": "array",
                "description": "Входное изображение (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB). Если изображение не соответствует соотношению сторон, оно будет изменено и обрезано по центру.",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "audio_input": {
                "type": "array",
                "description": "Аудиофайл (1 файл, форматы: MP3, WAV, OGG, M4A, FLAC, AAC, WMA, MPEG, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "num_frames": {
                "type": "number",
                "description": "Количество кадров для генерации (40-120, должно быть кратно 4)",
                "required": False,
                "default": 80,
                "min": 40,
                "max": 120,
                "step": 4
            },
            "frames_per_second": {
                "type": "number",
                "description": "Кадров в секунду генерируемого видео (4-60)",
                "required": False,
                "default": 16,
                "min": 4,
                "max": 60,
                "step": 1
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение видео (480P = 12 кредитов/сек, 580P = 18 кредитов/сек, 720P = 24 кредита/сек)",
                "required": False,
                "default": "480p",
                "enum": ["480p", "580p", "720p"]
            },
            "negative_prompt": {
                "type": "string",
                "description": "Негативный промпт для генерации видео (макс. 500 символов, опционально)",
                "required": False,
                "max_length": 500
            },
            "num_inference_steps": {
                "type": "number",
                "description": "Количество шагов вывода для семплирования. Большие значения дают лучшее качество, но занимают больше времени (2-40)",
                "required": False,
                "default": 27,
                "min": 2,
                "max": 40,
                "step": 1
            },
            "guidance_scale": {
                "type": "number",
                "description": "Classifier-free guidance scale. Большие значения лучше следуют промпту, но могут снизить качество (1-10, шаг 0.1)",
                "required": False,
                "default": 3.5,
                "min": 1,
                "max": 10,
                "step": 0.1
            },
            "shift": {
                "type": "number",
                "description": "Значение сдвига для видео (1.0-10.0, шаг 0.1)",
                "required": False,
                "default": 5,
                "min": 1,
                "max": 10,
                "step": 0.1
            },
            "enable_safety_checker": {
                "type": "boolean",
                "description": "Если установлено true, входные данные будут проверены на безопасность перед обработкой",
                "required": False,
                "default": True
            }
        }
    },
    {
        "id": "bytedance/seedream",
        "name": "Seedream 3.0",
        "description": "Последний text-to-image API от ByteDance, созданный для нативного разрешения 2K, более быстрой генерации и точного двуязычного рендеринга текста. По сравнению с Seedream 2.0, Seedream v3 API обеспечивает более высокую точность, кинематографическую эстетику и типографику уровня дизайнера.",
        "category": "Изображения",
        "emoji": "🎨",
        "pricing": "3.5 кредита за изображение",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание для генерации изображения (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "image_size": {
                "type": "string",
                "description": "Размер генерируемого изображения (соотношение сторон)",
                "required": False,
                "default": "square_hd",
                "enum": ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]
            },
            "guidance_scale": {
                "type": "number",
                "description": "Контролирует, насколько близко выходное изображение соответствует входному промпту. Большие значения означают более сильную корреляцию с промптом (1-10, шаг 0.1)",
                "required": False,
                "default": 2.5,
                "min": 1,
                "max": 10,
                "step": 0.1
            },
            "enable_safety_checker": {
                "type": "boolean",
                "description": "Если установлено true, будет включен проверщик безопасности",
                "required": False,
                "default": True
            }
        }
    },
    {
        "id": "qwen/text-to-image",
        "name": "Qwen Text-to-Image",
        "description": "Qwen Image API позволяет создателям, разработчикам и бизнесу легко генерировать и редактировать фотореалистичные изображения. Независимо от того, создаете ли вы сложные дизайны или улучшаете существующие визуалы, этот мощный Qwen API бесшовно интегрируется в ваш рабочий процесс, обеспечивая многоязычный рендеринг текста и продвинутые возможности редактирования, сопоставимые с топовыми моделями.",
        "category": "Изображения",
        "emoji": "🎭",
        "pricing": "4 кредита за мегапиксель",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Промпт для генерации изображения (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "image_size": {
                "type": "string",
                "description": "Размер генерируемого изображения (соотношение сторон)",
                "required": False,
                "default": "square_hd",
                "enum": ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]
            },
            "num_inference_steps": {
                "type": "number",
                "description": "Количество шагов вывода для выполнения (2-250)",
                "required": False,
                "default": 30,
                "min": 2,
                "max": 250,
                "step": 1
            },
            "guidance_scale": {
                "type": "number",
                "description": "CFG scale - насколько близко модель должна следовать промпту (0-20, шаг 0.1)",
                "required": False,
                "default": 2.5,
                "min": 0,
                "max": 20,
                "step": 0.1
            },
            "enable_safety_checker": {
                "type": "boolean",
                "description": "Проверщик безопасности всегда включен в Playground. Может быть отключен только установкой false через API",
                "required": False,
                "default": True
            },
            "output_format": {
                "type": "string",
                "description": "Формат генерируемого изображения",
                "required": False,
                "default": "png",
                "enum": ["png", "jpeg"]
            },
            "negative_prompt": {
                "type": "string",
                "description": "Негативный промпт для генерации (макс. 500 символов, опционально)",
                "required": False,
                "max_length": 500
            },
            "acceleration": {
                "type": "string",
                "description": "Уровень ускорения для генерации изображения. 'none' - без ускорения, 'regular' - баланс скорости и качества, 'high' - рекомендуется для изображений без текста",
                "required": False,
                "default": "none",
                "enum": ["none", "regular", "high"]
            }
        }
    },
    {
        "id": "qwen/image-to-image",
        "name": "Qwen Image-to-Image",
        "description": "Qwen Image API позволяет создателям, разработчикам и бизнесу легко генерировать и редактировать фотореалистичные изображения. Независимо от того, создаете ли вы сложные дизайны или улучшаете существующие визуалы, этот мощный Qwen API бесшовно интегрируется в ваш рабочий процесс, обеспечивая многоязычный рендеринг текста и продвинутые возможности редактирования, сопоставимые с топовыми моделями.",
        "category": "Изображения",
        "emoji": "🖼️",
        "pricing": "4 кредита за изображение",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Промпт для генерации изображения (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "image_input": {
                "type": "array",
                "description": "Референсное изображение для управления генерацией (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "strength": {
                "type": "number",
                "description": "Сила денойзинга. 1.0 = полная переделка; 0.0 = сохранение оригинала (0-1, шаг 0.01)",
                "required": False,
                "default": 0.8,
                "min": 0,
                "max": 1,
                "step": 0.01
            },
            "output_format": {
                "type": "string",
                "description": "Формат генерируемого изображения",
                "required": False,
                "default": "png",
                "enum": ["png", "jpeg"]
            },
            "acceleration": {
                "type": "string",
                "description": "Уровень ускорения для генерации изображения. 'none' - без ускорения, 'regular' - баланс скорости и качества, 'high' - рекомендуется для изображений без текста",
                "required": False,
                "default": "none",
                "enum": ["none", "regular", "high"]
            },
            "negative_prompt": {
                "type": "string",
                "description": "Негативный промпт для генерации (макс. 500 символов, опционально)",
                "required": False,
                "max_length": 500
            },
            "num_inference_steps": {
                "type": "number",
                "description": "Количество шагов вывода для выполнения (2-250)",
                "required": False,
                "default": 30,
                "min": 2,
                "max": 250,
                "step": 1
            },
            "guidance_scale": {
                "type": "number",
                "description": "CFG scale - насколько близко модель должна следовать промпту (0-20, шаг 0.1)",
                "required": False,
                "default": 2.5,
                "min": 0,
                "max": 20,
                "step": 0.1
            },
            "enable_safety_checker": {
                "type": "boolean",
                "description": "Проверщик безопасности всегда включен в Playground. Может быть отключен только установкой false через API",
                "required": False,
                "default": True
            }
        }
    },
    {
        "id": "qwen/image-edit",
        "name": "Qwen Image Edit",
        "description": "Qwen-Image-Edit - модель редактирования изображений с открытым исходным кодом на базе Qwen-Image. Поддерживает семантическое и визуальное редактирование с точными, визуально согласованными результатами. Также обрабатывает двуязычное (китайский и английский) редактирование текста, сохраняя шрифт, размер и стиль, что делает его универсальным инструментом для продвинутой манипуляции визуальным контентом.",
        "category": "Изображения",
        "emoji": "✏️",
        "pricing": "≈ $0.03 за мегапиксель (зависит от соотношения сторон)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Промпт для генерации изображения (макс. 2000 символов)",
                "required": True,
                "max_length": 2000
            },
            "image_input": {
                "type": "array",
                "description": "Изображение для редактирования (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "acceleration": {
                "type": "string",
                "description": "Уровень ускорения для генерации изображения. 'none' - без ускорения, 'regular' - баланс скорости и качества. Значение по умолчанию: 'none'",
                "required": False,
                "default": "none",
                "enum": ["none", "regular", "high"]
            },
            "image_size": {
                "type": "string",
                "description": "Размер генерируемого изображения. Значение по умолчанию: landscape_4_3",
                "required": False,
                "default": "landscape_4_3",
                "enum": ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]
            },
            "num_inference_steps": {
                "type": "number",
                "description": "Количество шагов вывода для выполнения. Значение по умолчанию: 30 (2-49)",
                "required": False,
                "default": 30,
                "min": 2,
                "max": 49,
                "step": 1
            },
            "guidance_scale": {
                "type": "number",
                "description": "CFG scale - насколько близко модель должна следовать промпту. Значение по умолчанию: 4 (0-20, шаг 0.1)",
                "required": False,
                "default": 4,
                "min": 0,
                "max": 20,
                "step": 0.1
            },
            "num_images": {
                "type": "string",
                "description": "Количество изображений (1-4)",
                "required": False,
                "default": "1",
                "enum": ["1", "2", "3", "4"]
            },
            "enable_safety_checker": {
                "type": "boolean",
                "description": "Если установлено true, будет включен проверщик безопасности. Значение по умолчанию: true",
                "required": False,
                "default": True
            },
            "output_format": {
                "type": "string",
                "description": "Формат генерируемого изображения. Значение по умолчанию: 'png'",
                "required": False,
                "default": "png",
                "enum": ["jpeg", "png"]
            },
            "negative_prompt": {
                "type": "string",
                "description": "Негативный промпт для генерации. Значение по умолчанию: ' ' (макс. 500 символов, опционально)",
                "required": False,
                "default": " ",
                "max_length": 500
            }
        }
    },
    {
        "id": "ideogram/character-edit",
        "name": "Ideogram Character Edit",
        "description": "Ideogram Character - последняя функция от Ideogram AI, обеспечивающая сохранение основных характеристик персонажей, таких как черты лица, пропорции и прически, в разных сценах, художественных стилях и контекстах. Независимо от того, создаете ли вы персонажей из одного референсного изображения или дорабатываете существующих, Ideogram Character API от Kie.ai предлагает гибкость и точность через операции Base, Edit и Remix.",
        "category": "Изображения",
        "emoji": "👤",
        "pricing": "12 кредитов (Turbo), 18 кредитов (Balanced), 24 кредита (Quality)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Промпт для заполнения замаскированной части изображения (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "image_input": {
                "type": "array",
                "description": "Изображение для генерации (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB). Должно соответствовать размерам маски.",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "mask_input": {
                "type": "array",
                "description": "Маска для инпейнтинга изображения (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB). Должна соответствовать размерам входного изображения.",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "reference_image_input": {
                "type": "array",
                "description": "Набор изображений для использования в качестве референсов персонажа. В настоящее время поддерживается только 1 изображение (макс. общий размер 10MB). Изображения должны быть в формате JPEG, PNG или WebP.",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "rendering_speed": {
                "type": "string",
                "description": "Скорость рендеринга (TURBO = 12 кредитов, BALANCED = 18 кредитов, QUALITY = 24 кредита). Значение по умолчанию: 'BALANCED'",
                "required": False,
                "default": "BALANCED",
                "enum": ["TURBO", "BALANCED", "QUALITY"]
            },
            "style": {
                "type": "string",
                "description": "Тип стиля для генерации. Нельзя использовать вместе с style_codes. Значение по умолчанию: 'AUTO'",
                "required": False,
                "default": "AUTO",
                "enum": ["AUTO", "REALISTIC", "FICTION"]
            },
            "expand_prompt": {
                "type": "boolean",
                "description": "Определяет, должен ли использоваться MagicPrompt при генерации запроса. Значение по умолчанию: true",
                "required": False,
                "default": True
            },
            "num_images": {
                "type": "string",
                "description": "Количество изображений (1-4)",
                "required": False,
                "default": "1",
                "enum": ["1", "2", "3", "4"]
            }
        }
    },
    {
        "id": "ideogram/character-remix",
        "name": "Ideogram Character Remix",
        "description": "Ideogram Character - последняя функция от Ideogram AI, обеспечивающая сохранение основных характеристик персонажей, таких как черты лица, пропорции и прически, в разных сценах, художественных стилях и контекстах. Операция Remix позволяет создавать новые вариации персонажа с сохранением его ключевых характеристик.",
        "category": "Изображения",
        "emoji": "🎭",
        "pricing": "12 кредитов (Turbo), 18 кредитов (Balanced), 24 кредита (Quality)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Промпт для ремикса изображения (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "image_input": {
                "type": "array",
                "description": "Изображение для ремикса (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "reference_image_input": {
                "type": "array",
                "description": "Набор изображений для использования в качестве референсов персонажа. В настоящее время поддерживается только 1 изображение (макс. общий размер 10MB). Изображения должны быть в формате JPEG, PNG или WebP.",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "rendering_speed": {
                "type": "string",
                "description": "Скорость рендеринга (TURBO = 12 кредитов, BALANCED = 18 кредитов, QUALITY = 24 кредита). Значение по умолчанию: 'BALANCED'",
                "required": False,
                "default": "BALANCED",
                "enum": ["TURBO", "BALANCED", "QUALITY"]
            },
            "style": {
                "type": "string",
                "description": "Тип стиля для генерации. Нельзя использовать вместе с style_codes. Значение по умолчанию: 'AUTO'",
                "required": False,
                "default": "AUTO",
                "enum": ["AUTO", "REALISTIC", "FICTION"]
            },
            "expand_prompt": {
                "type": "boolean",
                "description": "Определяет, должен ли использоваться MagicPrompt при генерации запроса. Значение по умолчанию: true",
                "required": False,
                "default": True
            },
            "image_size": {
                "type": "string",
                "description": "Размер генерируемого изображения",
                "required": False,
                "default": "square_hd",
                "enum": ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]
            },
            "num_images": {
                "type": "string",
                "description": "Количество изображений (1-4)",
                "required": False,
                "default": "1",
                "enum": ["1", "2", "3", "4"]
            },
            "strength": {
                "type": "number",
                "description": "Сила входного изображения в ремиксе. Значение по умолчанию: 0.8 (0.1-1, шаг 0.1)",
                "required": False,
                "default": 0.8,
                "min": 0.1,
                "max": 1,
                "step": 0.1
            },
            "negative_prompt": {
                "type": "string",
                "description": "Описание того, что исключить из изображения. Значение по умолчанию: '' (макс. 500 символов, опционально)",
                "required": False,
                "default": "",
                "max_length": 500
            }
        }
    },
    {
        "id": "ideogram/character",
        "name": "Ideogram Character",
        "description": "Ideogram Character - последняя функция от Ideogram AI, обеспечивающая сохранение основных характеристик персонажей, таких как черты лица, пропорции и прически, в разных сценах, художественных стилях и контекстах. Операция Base позволяет создавать персонажей из одного референсного изображения.",
        "category": "Изображения",
        "emoji": "👥",
        "pricing": "12 кредитов (Turbo), 18 кредитов (Balanced), 24 кредита (Quality)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Промпт для генерации персонажа (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "reference_image_input": {
                "type": "array",
                "description": "Набор изображений для использования в качестве референсов персонажа. В настоящее время поддерживается только 1 изображение (макс. общий размер 10MB). Изображения должны быть в формате JPEG, PNG или WebP.",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "rendering_speed": {
                "type": "string",
                "description": "Скорость рендеринга (TURBO = 12 кредитов, BALANCED = 18 кредитов, QUALITY = 24 кредита). Значение по умолчанию: 'BALANCED'",
                "required": False,
                "default": "BALANCED",
                "enum": ["TURBO", "BALANCED", "QUALITY"]
            },
            "style": {
                "type": "string",
                "description": "Тип стиля для генерации. Нельзя использовать вместе с style_codes. Значение по умолчанию: 'AUTO'",
                "required": False,
                "default": "AUTO",
                "enum": ["AUTO", "REALISTIC", "FICTION"]
            },
            "expand_prompt": {
                "type": "boolean",
                "description": "Определяет, должен ли использоваться MagicPrompt при генерации запроса. Значение по умолчанию: true",
                "required": False,
                "default": True
            },
            "num_images": {
                "type": "string",
                "description": "Количество изображений (1-4)",
                "required": False,
                "default": "1",
                "enum": ["1", "2", "3", "4"]
            },
            "image_size": {
                "type": "string",
                "description": "Разрешение генерируемого изображения. Значение по умолчанию: square_hd",
                "required": False,
                "default": "square_hd",
                "enum": ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]
            },
            "negative_prompt": {
                "type": "string",
                "description": "Описание того, что исключить из изображения. Значение по умолчанию: '' (макс. 5000 символов, опционально)",
                "required": False,
                "default": "",
                "max_length": 5000
            }
        }
    },
    {
        "id": "bytedance/v1-pro-fast-image-to-video",
        "name": "ByteDance V1 Pro Fast Image-to-Video",
        "description": "Модель генерации видео от ByteDance, которая наследует качество Seedance 1.0 Pro, обеспечивая в 3 раза более быстрый рендеринг. Создает согласованные 1080p клипы со стабильным движением и эффективной производительностью. От семян идей до танцующих визуалов.",
        "category": "Видео",
        "emoji": "⚡",
        "pricing": "16 кредитов (720P, 5с) / 36 кредитов (720P, 10с) / 36 кредитов (1080P, 5с) / 72 кредита (1080P, 10с)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание для генерации видео (макс. 10000 символов)",
                "required": True,
                "max_length": 10000
            },
            "image_input": {
                "type": "array",
                "description": "Изображение для генерации видео (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение видео (720P = 16 кредитов за 5с / 36 за 10с, 1080P = 36 кредитов за 5с / 72 за 10с)",
                "required": False,
                "default": "720p",
                "enum": ["720p", "1080p"]
            },
            "duration": {
                "type": "string",
                "description": "Длительность видео в секундах (5с или 10с)",
                "required": False,
                "default": "5",
                "enum": ["5", "10"]
            }
        }
    },
    {
        "id": "kling/v2-1-master-image-to-video",
        "name": "Kling V2.1 Master Image-to-Video",
        "description": "Модель Kling 2.1 обеспечивает передовую генерацию видео с гиперреалистичным движением, продвинутой физикой и высоким разрешением до 1080p. Улучшенное семантическое понимание и быстрый рендеринг делают её идеальной для динамичного, профессионального создания видео.",
        "category": "Видео",
        "emoji": "🎬",
        "pricing": "160 кредитов (5с) или 320 кредитов (10с)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание видео для генерации (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "image_input": {
                "type": "array",
                "description": "URL изображения для использования в видео (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "duration": {
                "type": "string",
                "description": "Длительность сгенерированного видео в секундах (5с = 160 кредитов, 10с = 320 кредитов)",
                "required": False,
                "default": "5",
                "enum": ["5", "10"]
            },
            "negative_prompt": {
                "type": "string",
                "description": "Негативный промпт для исключения определенных элементов из видео (макс. 500 символов, опционально)",
                "required": False,
                "max_length": 500
            },
            "cfg_scale": {
                "type": "number",
                "description": "CFG (Classifier Free Guidance) scale - насколько близко модель должна следовать промпту (0-1, шаг 0.1)",
                "required": False,
                "default": 0.5,
                "min": 0,
                "max": 1,
                "step": 0.1
            }
        }
    },
    {
        "id": "kling/v2-1-standard",
        "name": "Kling V2.1 Standard",
        "description": "Модель Kling 2.1 обеспечивает передовую генерацию видео с гиперреалистичным движением, продвинутой физикой и высоким разрешением до 1080p. Улучшенное семантическое понимание и быстрый рендеринг делают её идеальной для динамичного, профессионального создания видео. Стандартная версия с более доступной ценой.",
        "category": "Видео",
        "emoji": "🎥",
        "pricing": "25 кредитов (5с) или 50 кредитов (10с)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание желаемого видео (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "image_input": {
                "type": "array",
                "description": "URL изображения для использования в видео (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "duration": {
                "type": "string",
                "description": "Длительность видео в секундах (5с = 25 кредитов, 10с = 50 кредитов)",
                "required": False,
                "default": "5",
                "enum": ["5", "10"]
            },
            "negative_prompt": {
                "type": "string",
                "description": "Описание элементов, которых следует избегать в сгенерированном видео (макс. 500 символов, опционально)",
                "required": False,
                "max_length": 500
            },
            "cfg_scale": {
                "type": "number",
                "description": "CFG (Classifier Free Guidance) scale - насколько близко модель должна следовать промпту (0-1, шаг 0.1)",
                "required": False,
                "default": 0.5,
                "min": 0,
                "max": 1,
                "step": 0.1
            }
        }
    },
    {
        "id": "kling/v2-1-pro",
        "name": "Kling V2.1 Pro",
        "description": "Модель Kling 2.1 обеспечивает передовую генерацию видео с гиперреалистичным движением, продвинутой физикой и высоким разрешением до 1080p. Улучшенное семантическое понимание и быстрый рендеринг делают её идеальной для динамичного, профессионального создания видео. Pro версия с улучшенным качеством.",
        "category": "Видео",
        "emoji": "🎞️",
        "pricing": "50 кредитов (5с) или 100 кредитов (10с)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание видео для генерации (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "image_input": {
                "type": "array",
                "description": "URL изображения для использования в видео (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "duration": {
                "type": "string",
                "description": "Длительность видео в секундах (5с = 50 кредитов, 10с = 100 кредитов)",
                "required": False,
                "default": "5",
                "enum": ["5", "10"]
            },
            "negative_prompt": {
                "type": "string",
                "description": "Термины, которых следует избегать в сгенерированном видео (макс. 500 символов, опционально)",
                "required": False,
                "max_length": 500
            },
            "cfg_scale": {
                "type": "number",
                "description": "CFG (Classifier Free Guidance) scale - насколько близко модель должна следовать промпту (0-1, шаг 0.1)",
                "required": False,
                "default": 0.5,
                "min": 0,
                "max": 1,
                "step": 0.1
            },
            "tail_image_url": {
                "type": "string",
                "description": "URL изображения для использования в конце видео (опционально, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": False
            }
        }
    },
    {
        "id": "kling/v2-1-master-text-to-video",
        "name": "Kling V2.1 Master Text-to-Video",
        "description": "Модель Kling 2.1 обеспечивает передовую генерацию видео с гиперреалистичным движением, продвинутой физикой и высоким разрешением до 1080p. Улучшенное семантическое понимание и быстрый рендеринг делают её идеальной для динамичного, профессионального создания видео. Master версия для генерации из текста.",
        "category": "Видео",
        "emoji": "🎬",
        "pricing": "160 кредитов (5с) или 320 кредитов (10с)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание видео, которое вы хотите сгенерировать (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "duration": {
                "type": "string",
                "description": "Длительность сгенерированного видео в секундах (5с = 160 кредитов, 10с = 320 кредитов)",
                "required": False,
                "default": "5",
                "enum": ["5", "10"]
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон кадра сгенерированного видео",
                "required": False,
                "default": "16:9",
                "enum": ["16:9", "9:16", "1:1"]
            },
            "negative_prompt": {
                "type": "string",
                "description": "Элементы, которых следует избегать в сгенерированном видео (макс. 500 символов, опционально)",
                "required": False,
                "max_length": 500
            },
            "cfg_scale": {
                "type": "number",
                "description": "CFG (Classifier Free Guidance) scale - насколько близко модель должна следовать промпту (0-1, шаг 0.1)",
                "required": False,
                "default": 0.5,
                "min": 0,
                "max": 1,
                "step": 0.1
            }
        }
    },
    {
        "id": "ideogram/v3-text-to-image",
        "name": "Ideogram V3 Text-to-Image",
        "description": "Последнее поколение модели генерации изображений от Ideogram. Предлагает text-to-image, редактирование изображений, изменение кадра и ремикс с улучшенной согласованностью и творческим контролем. Отличное качество генерации текста в изображениях.",
        "category": "Изображения",
        "emoji": "✨",
        "pricing": "3.5 кредита (Turbo), 7 кредитов (Balanced) или 10 кредитов (Quality) за изображение",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Описание изображения для генерации (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "rendering_speed": {
                "type": "string",
                "description": "Скорость рендеринга (TURBO = 3.5 кредита, BALANCED = 7 кредитов, QUALITY = 10 кредитов)",
                "required": False,
                "default": "BALANCED",
                "enum": ["TURBO", "BALANCED", "QUALITY"]
            },
            "style": {
                "type": "string",
                "description": "Тип стиля для генерации. Нельзя использовать вместе с style_codes",
                "required": False,
                "default": "AUTO",
                "enum": ["AUTO", "GENERAL", "REALISTIC", "DESIGN"]
            },
            "expand_prompt": {
                "type": "boolean",
                "description": "Определяет, должен ли использоваться MagicPrompt при генерации запроса",
                "required": False,
                "default": True
            },
            "image_size": {
                "type": "string",
                "description": "Разрешение сгенерированного изображения",
                "required": False,
                "default": "square_hd",
                "enum": ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]
            },
            "num_images": {
                "type": "string",
                "description": "Количество изображений (1-4)",
                "required": False,
                "default": "1",
                "enum": ["1", "2", "3", "4"]
            },
            "seed": {
                "type": "integer",
                "description": "Seed для генератора случайных чисел (опционально)",
                "required": False
            },
            "negative_prompt": {
                "type": "string",
                "description": "Описание того, что исключить из изображения. Описания в промпте имеют приоритет над описаниями в негативном промпте (макс. 5000 символов, опционально)",
                "required": False,
                "max_length": 5000
            }
        }
    },
    {
        "id": "ideogram/v3-edit",
        "name": "Ideogram V3 Edit",
        "description": "Последнее поколение модели редактирования изображений от Ideogram. Предлагает редактирование изображений с использованием маски (inpainting) с улучшенной согласованностью и творческим контролем. Идеально для точного редактирования определенных областей изображения.",
        "category": "Изображения",
        "emoji": "✏️",
        "pricing": "3.5 кредита (Turbo), 7 кредитов (Balanced) или 10 кредитов (Quality) за изображение",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Промпт для заполнения замаскированной части изображения (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "image_input": {
                "type": "array",
                "description": "Изображение для редактирования (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB). Должно соответствовать размерам маски.",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "mask_input": {
                "type": "array",
                "description": "Маска для инпейнтинга изображения (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB). Должна соответствовать размерам входного изображения.",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "rendering_speed": {
                "type": "string",
                "description": "Скорость рендеринга (TURBO = 3.5 кредита, BALANCED = 7 кредитов, QUALITY = 10 кредитов)",
                "required": False,
                "default": "BALANCED",
                "enum": ["TURBO", "BALANCED", "QUALITY"]
            },
            "expand_prompt": {
                "type": "boolean",
                "description": "Определяет, должен ли использоваться MagicPrompt при генерации запроса",
                "required": False,
                "default": True
            },
            "num_images": {
                "type": "string",
                "description": "Количество изображений (1-4)",
                "required": False,
                "default": "1",
                "enum": ["1", "2", "3", "4"]
            },
            "seed": {
                "type": "integer",
                "description": "Seed для генератора случайных чисел (опционально)",
                "required": False
            }
        }
    },
    {
        "id": "ideogram/v3-remix",
        "name": "Ideogram V3 Remix",
        "description": "Последнее поколение модели ремикса изображений от Ideogram. Предлагает ремикс изображений с улучшенной согласованностью и творческим контролем. Позволяет трансформировать существующие изображения с сохранением стиля и структуры.",
        "category": "Изображения",
        "emoji": "🎭",
        "pricing": "3.5 кредита (Turbo), 7 кредитов (Balanced) или 10 кредитов (Quality) за изображение",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Промпт для ремикса изображения (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "image_input": {
                "type": "array",
                "description": "Изображение для ремикса (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB)",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "rendering_speed": {
                "type": "string",
                "description": "Скорость рендеринга (TURBO = 3.5 кредита, BALANCED = 7 кредитов, QUALITY = 10 кредитов)",
                "required": False,
                "default": "BALANCED",
                "enum": ["TURBO", "BALANCED", "QUALITY"]
            },
            "style": {
                "type": "string",
                "description": "Тип стиля для генерации. Нельзя использовать вместе с style_codes",
                "required": False,
                "default": "AUTO",
                "enum": ["AUTO", "GENERAL", "REALISTIC", "DESIGN"]
            },
            "expand_prompt": {
                "type": "boolean",
                "description": "Определяет, должен ли использоваться MagicPrompt при генерации запроса",
                "required": False,
                "default": True
            },
            "image_size": {
                "type": "string",
                "description": "Разрешение сгенерированного изображения",
                "required": False,
                "default": "square_hd",
                "enum": ["square", "square_hd", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]
            },
            "num_images": {
                "type": "string",
                "description": "Количество изображений (1-4)",
                "required": False,
                "default": "1",
                "enum": ["1", "2", "3", "4"]
            },
            "seed": {
                "type": "integer",
                "description": "Seed для генератора случайных чисел (опционально)",
                "required": False
            },
            "strength": {
                "type": "number",
                "description": "Сила входного изображения в ремиксе (0.01-1, шаг 0.01)",
                "required": False,
                "default": 0.8,
                "min": 0.01,
                "max": 1,
                "step": 0.01
            },
            "negative_prompt": {
                "type": "string",
                "description": "Описание того, что исключить из изображения. Описания в промпте имеют приоритет над описаниями в негативном промпте (макс. 5000 символов, опционально)",
                "required": False,
                "max_length": 5000
            }
        }
    },
    {
        "id": "wan/2-2-a14b-text-to-video-turbo",
        "name": "WAN 2.2 A14B Text-to-Video Turbo",
        "description": "Последнее поколение модели WAN 2.2 A14B Turbo с архитектурой Mixture-of-Experts (MoE). Поддерживает text-to-video, image-to-video и speech-to-video. Создает плавные 720p@24fps клипы с кинематографическим качеством, стабильным движением и согласованным визуальным стилем для различных творческих и коммерческих применений.",
        "category": "Видео",
        "emoji": "⚡",
        "pricing": "16 кредитов/сек (720p), 12 кредитов/сек (580p), 8 кредитов/сек (480p)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовый промпт для генерации видео (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение сгенерированного видео (480p = 8 кредитов/сек, 580p = 12 кредитов/сек, 720p = 16 кредитов/сек)",
                "required": False,
                "default": "720p",
                "enum": ["480p", "580p", "720p"]
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон сгенерированного видео",
                "required": False,
                "default": "16:9",
                "enum": ["16:9", "9:16", "1:1"]
            },
            "enable_prompt_expansion": {
                "type": "boolean",
                "description": "Включить расширение промпта. Использует большую языковую модель для расширения промпта с дополнительными деталями, сохраняя исходный смысл",
                "required": False,
                "default": False
            },
            "seed": {
                "type": "number",
                "description": "Случайный seed для воспроизводимости. Если None, выбирается случайный seed (0-2147483647)",
                "required": False,
                "min": 0,
                "max": 2147483647,
                "step": 1
            },
            "acceleration": {
                "type": "string",
                "description": "Уровень ускорения для использования. Чем больше ускорение, тем быстрее генерация, но с более низким качеством. Рекомендуемое значение: 'none'",
                "required": False,
                "default": "none",
                "enum": ["none", "regular"]
            }
        }
    },
    {
        "id": "wan/2-2-a14b-image-to-video-turbo",
        "name": "WAN 2.2 A14B Image-to-Video Turbo",
        "description": "Последнее поколение модели WAN 2.2 A14B Turbo с архитектурой Mixture-of-Experts (MoE). Поддерживает text-to-video, image-to-video и speech-to-video. Создает плавные 720p@24fps клипы с кинематографическим качеством, стабильным движением и согласованным визуальным стилем для различных творческих и коммерческих применений. Генерация видео из изображений.",
        "category": "Видео",
        "emoji": "🎬",
        "pricing": "16 кредитов/сек (720p), 12 кредитов/сек (580p), 8 кредитов/сек (480p)",
        "input_params": {
            "image_input": {
                "type": "array",
                "description": "URL входного изображения (1 изображение, форматы: JPEG, PNG, WebP, макс. 10MB). Если изображение не соответствует выбранному соотношению сторон, оно будет изменено и обрезано по центру.",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 1
            },
            "prompt": {
                "type": "string",
                "description": "Текстовый промпт для генерации видео (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение сгенерированного видео (480p = 8 кредитов/сек, 580p = 12 кредитов/сек, 720p = 16 кредитов/сек)",
                "required": False,
                "default": "720p",
                "enum": ["480p", "580p", "720p"]
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон сгенерированного видео. Если 'auto', соотношение сторон будет определено автоматически на основе входного изображения",
                "required": False,
                "default": "auto",
                "enum": ["auto", "16:9", "9:16", "1:1"]
            },
            "enable_prompt_expansion": {
                "type": "boolean",
                "description": "Включить расширение промпта. Использует большую языковую модель для расширения промпта с дополнительными деталями, сохраняя исходный смысл",
                "required": False,
                "default": False
            },
            "seed": {
                "type": "number",
                "description": "Случайный seed для воспроизводимости. Если None, выбирается случайный seed (0-2147483647)",
                "required": False,
                "min": 0,
                "max": 2147483647,
                "step": 1
            },
            "acceleration": {
                "type": "string",
                "description": "Уровень ускорения для использования. Чем больше ускорение, тем быстрее генерация, но с более низким качеством. Рекомендуемое значение: 'none'",
                "required": False,
                "default": "none",
                "enum": ["none", "regular"]
            }
        }
    },
    {
        "id": "google/imagen4-ultra",
        "name": "Google Imagen 4 Ultra",
        "description": "Google Imagen 4, разработанная Google DeepMind и представленная на Google I/O 2025, - это передовая модель генерации изображений из текста, которая преобразует промпты в фотореалистичные, высококачественные визуалы с исключительной детализацией и творческой универсальностью. Улучшенный вариант Google Imagen 4 Ultra обеспечивает еще большую точность, скорость и разрешение, что делает обе модели идеальными для коммерческих, маркетинговых, дизайнерских и творческих применений.",
        "category": "Изображения",
        "emoji": "🌟",
        "pricing": "12 кредитов за изображение",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание того, что вы хотите увидеть (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "negative_prompt": {
                "type": "string",
                "description": "Описание того, чего следует избегать в сгенерированных изображениях (макс. 5000 символов, опционально)",
                "required": False,
                "max_length": 5000
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон сгенерированного изображения",
                "required": False,
                "default": "1:1",
                "enum": ["1:1", "16:9", "9:16", "3:4", "4:3"]
            },
            "seed": {
                "type": "string",
                "description": "Случайный seed для воспроизводимой генерации (макс. 500 символов, опционально)",
                "required": False,
                "max_length": 500
            }
        }
    },
    {
        "id": "google/imagen4-fast",
        "name": "Google Imagen 4 Fast",
        "description": "Google Imagen 4, разработанная Google DeepMind и представленная на Google I/O 2025, - это передовая модель генерации изображений из текста, которая преобразует промпты в фотореалистичные, высококачественные визуалы с исключительной детализацией и творческой универсальностью. Быстрая версия Imagen 4 Fast обеспечивает более быстрое время генерации при сохранении высокого качества, идеально подходит для быстрого прототипирования и массовой генерации.",
        "category": "Изображения",
        "emoji": "⚡",
        "pricing": "4 кредита за изображение",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание того, что вы хотите увидеть (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "negative_prompt": {
                "type": "string",
                "description": "Описание того, чего следует избегать в сгенерированных изображениях (макс. 5000 символов, опционально)",
                "required": False,
                "max_length": 5000
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон сгенерированного изображения",
                "required": False,
                "default": "1:1",
                "enum": ["1:1", "16:9", "9:16", "3:4", "4:3"]
            },
            "num_images": {
                "type": "string",
                "description": "Количество изображений (1-4)",
                "required": False,
                "default": "1",
                "enum": ["1", "2", "3", "4"]
            },
            "seed": {
                "type": "integer",
                "description": "Случайный seed для воспроизводимой генерации (опционально)",
                "required": False
            }
        }
    },
    {
        "id": "google/imagen4",
        "name": "Google Imagen 4",
        "description": "Google Imagen 4, разработанная Google DeepMind и представленная на Google I/O 2025, - это передовая модель генерации изображений из текста, которая преобразует промпты в фотореалистичные, высококачественные визуалы с исключительной детализацией и творческой универсальностью. Стандартная версия Imagen 4 обеспечивает оптимальный баланс между качеством и скоростью, идеально подходит для коммерческих, маркетинговых, дизайнерских и творческих применений.",
        "category": "Изображения",
        "emoji": "🎨",
        "pricing": "8 кредитов за изображение",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание того, что вы хотите увидеть (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "negative_prompt": {
                "type": "string",
                "description": "Описание того, чего следует избегать в сгенерированных изображениях (макс. 5000 символов, опционально)",
                "required": False,
                "max_length": 5000
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон сгенерированного изображения",
                "required": False,
                "default": "1:1",
                "enum": ["1:1", "16:9", "9:16", "3:4", "4:3"]
            },
            "num_images": {
                "type": "string",
                "description": "Количество изображений (1-4)",
                "required": False,
                "default": "1",
                "enum": ["1", "2", "3", "4"]
            },
            "seed": {
                "type": "string",
                "description": "Случайный seed для воспроизводимой генерации (макс. 500 символов, опционально)",
                "required": False,
                "max_length": 500
            }
        }
    },
    {
        "id": "nano-banana-pro",
        "name": "🔥 Nano Banana Pro",
        "description": "⭐ ТОП МОДЕЛЬ! Премиальная версия Nano Banana с поддержкой 4K, до 8 референс-изображений. Hyper-realistic генерация с физически корректными визуалами.",
        "category": "Фото",
        "emoji": "🍌",
        "pricing": "18-24 кредита за изображение (1K/2K: $0.09, 4K: $0.12)",
        "is_featured": True,
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание изображения (до 20000 символов)",
                "required": True,
                "max_length": 20000
            },
            "image_input": {
                "type": "array",
                "description": "URL референс-изображений (до 8 шт, JPEG/PNG/WebP, макс 30MB)",
                "required": False,
                "item_type": "string"
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон",
                "required": False,
                "default": "1:1",
                "enum": ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9", "auto"]
            },
            "resolution": {
                "type": "string",
                "description": "Разрешение выходного изображения",
                "required": False,
                "default": "1K",
                "enum": ["1K", "2K", "4K"]
            },
            "output_format": {
                "type": "string",
                "description": "Формат выходного изображения",
                "required": False,
                "default": "png",
                "enum": ["png", "jpg"]
            }
        }
    },
    {
        "id": "google/nano-banana",
        "name": "🔥 Google Nano Banana",
        "description": "⭐ ТОП МОДЕЛЬ! Gemini 3 Image Preview — продвинутая AI модель для генерации изображений. Гиперреалистичные визуалы с поддержкой естественного языка.",
        "category": "Фото",
        "emoji": "🍌",
        "is_featured": True,
        "pricing": "4 кредита за изображение (~$0.02)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание изображения, которое вы хотите сгенерировать (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "output_format": {
                "type": "string",
                "description": "Формат выходного изображения",
                "required": False,
                "default": "png",
                "enum": ["png", "jpeg"]
            },
            "image_size": {
                "type": "string",
                "description": "Соотношение сторон изображения",
                "required": False,
                "default": "1:1",
                "enum": ["1:1", "9:16", "16:9", "3:4", "4:3", "3:2", "2:3", "5:4", "4:5", "21:9", "auto"]
            }
        }
    },
    {
        "id": "google/nano-banana-edit",
        "name": "🔥 Google Nano Banana Edit",
        "description": "⭐ ТОП МОДЕЛЬ! Gemini 3 для редактирования изображений. Гиперреалистичные трансформации с поддержкой естественного языка.",
        "category": "Фото",
        "emoji": "✏️",
        "is_featured": True,
        "pricing": "4 кредита за изображение (~$0.02)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание изменений, которые вы хотите внести в изображение (макс. 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "image_urls": {
                "type": "array",
                "description": "Список URL изображений для редактирования (до 10 изображений). URL файла после загрузки, не содержимое файла. Поддерживаемые типы: image/jpeg, image/png, image/webp. Макс. размер: 10.0MB",
                "required": True,
                "item_type": "string",
                "min_items": 1,
                "max_items": 10
            },
            "output_format": {
                "type": "string",
                "description": "Формат выходного изображения",
                "required": False,
                "default": "png",
                "enum": ["png", "jpeg"]
            },
            "image_size": {
                "type": "string",
                "description": "Соотношение сторон изображения",
                "required": False,
                "default": "1:1",
                "enum": ["1:1", "9:16", "16:9", "3:4", "4:3", "3:2", "2:3", "5:4", "4:5", "21:9", "auto"]
            }
        }
    },
    {
        "id": "elevenlabs/speech-to-text",
        "name": "ElevenLabs Speech-to-Text",
        "description": "ElevenLabs API для преобразования речи в текст. Основан на модели Scribe v1, предоставляет передовую транскрипцию с точностью, лидирующей в отрасли, поддержкой множества языков и такими функциями, как разделение говорящих и тегирование аудио-событий.",
        "category": "Речь в текст",
        "emoji": "🎤",
        "pricing": "3.5 кредитов за минуту",
        "input_params": {
            "audio_url": {
                "type": "string",
                "description": "URL аудиофайла для транскрибации. После загрузки файла, не содержимое файла. Поддерживаемые типы: audio/mpeg, audio/wav, audio/x-wav, audio/aac, audio/mp4, audio/ogg. Макс. размер: 200.0MB",
                "required": True
            },
            "language_code": {
                "type": "string",
                "description": "Код языка аудио (макс. 500 символов, опционально). По умолчанию: ru (русский)",
                "required": False,
                "default": "ru",
                "max_length": 500
            },
            "tag_audio_events": {
                "type": "boolean",
                "description": "Тегировать аудио-события (смех, аплодисменты и т.д.)",
                "required": False,
                "default": False
            },
            "diarize": {
                "type": "boolean",
                "description": "Разделять говорящих (аннотировать, кто говорит)",
                "required": False,
                "default": False
            }
        }
    },
    # Новые модели с сайта KIE.ai (скоро появятся в API)
    {
        "id": "grok/imagine",
        "name": "🔥 Grok Imagine Video",
        "description": "⭐ ТОП МОДЕЛЬ! Grok Imagine — генерация видео из изображений и текста. 6 или 10 секунд, режимы fun/normal/spicy. Отличное следование промпту.",
        "category": "Видео",
        "emoji": "🎬",
        "is_featured": True,
        "pricing": "20-30 кредитов (6s: $0.10, 10s: $0.15)",
        "input_params": {
            "image_urls": {
                "type": "array",
                "description": "URL изображения для image-to-video (1 изображение)",
                "required": False,
                "item_type": "string"
            },
            "prompt": {
                "type": "string",
                "description": "Описание желаемого движения (до 5000 символов)",
                "required": False,
                "max_length": 5000
            },
            "mode": {
                "type": "string",
                "description": "Режим генерации: fun, normal, spicy",
                "required": False,
                "default": "normal",
                "enum": ["fun", "normal", "spicy"]
            },
            "duration": {
                "type": "string",
                "description": "Длительность видео: 6 или 10 секунд",
                "required": False,
                "default": "6",
                "enum": ["6", "10"]
            }
        }
    },
    {
        "id": "openai/4o-image",
        "name": "🔥 OpenAI 4o Image",
        "description": "⭐ ТОП МОДЕЛЬ! GPT-4o Image — генерация и редактирование изображений. Text-to-image, image editing, variants. Понимает визуальный контекст.",
        "category": "Изображения",
        "emoji": "🎨",
        "is_featured": True,
        "pricing": "6 кредитов за изображение ($0.03)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Описание желаемого изображения",
                "required": True,
                "max_length": 4000
            },
            "filesUrl": {
                "type": "array",
                "description": "URL изображений для редактирования (опционально)",
                "required": False,
                "item_type": "string"
            },
            "size": {
                "type": "string",
                "description": "Соотношение сторон изображения",
                "required": False,
                "default": "1:1",
                "enum": ["1:1", "3:2", "2:3", "16:9", "9:16"]
            },
            "nVariants": {
                "type": "integer",
                "description": "Количество вариантов (1-4)",
                "required": False,
                "default": 1
            }
        }
    },
    {
        "id": "flux/kontext",
        "name": "🔥 Flux Kontext",
        "description": "⭐ ТОП МОДЕЛЬ! Flux Kontext — редактирование изображений с пониманием контекста. Pro или Max качество. Идеально для e-commerce и маркетинга.",
        "category": "Изображения",
        "emoji": "🎭",
        "is_featured": True,
        "pricing": "5-10 кредитов (Pro: $0.025, Max: $0.05)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Описание желаемых изменений",
                "required": True,
                "max_length": 4000
            },
            "image_url": {
                "type": "string",
                "description": "URL изображения для редактирования",
                "required": False
            },
            "quality": {
                "type": "string",
                "description": "Качество: Pro (5 кредитов) или Max (10 кредитов)",
                "required": False,
                "default": "Pro",
                "enum": ["Pro", "Max"]
            }
        }
    },
    {
        "id": "google/veo-3",
        "name": "Google Veo 3",
        "description": "Google Veo 3 - следующее поколение AI модели генерации видео от Google DeepMind. Поддерживает text-to-video и image-to-video с кинематографическим качеством.",
        "category": "Видео",
        "emoji": "🎬",
        "pricing": "Скоро появится",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание видео (скоро появится)",
                "required": True
            }
        },
        "coming_soon": True
    },
    {
        "id": "google/veo-3.1",
        "name": "🔥 Google Veo 3.1",
        "description": "⭐ ТОП МОДЕЛЬ! Google Veo 3.1 — новейшая модель генерации видео. Text-to-video, image-to-video, reference-to-video. Native 9:16, Fast/Quality режимы, 4K output.",
        "category": "Видео",
        "emoji": "🎥",
        "is_featured": True,
        "pricing": "60-250 кредитов (Fast: $0.30, Quality: $1.25)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Описание желаемого видео (до 10000 символов)",
                "required": True,
                "max_length": 10000
            },
            "imageUrls": {
                "type": "array",
                "description": "URL изображений (1-2 шт) для image-to-video режима",
                "required": False,
                "item_type": "string"
            },
            "model": {
                "type": "string",
                "description": "Режим генерации: veo3_fast (быстрый) или veo3 (качество)",
                "required": True,
                "default": "veo3_fast",
                "enum": ["veo3_fast", "veo3"]
            },
            "generationType": {
                "type": "string",
                "description": "Тип генерации",
                "required": False,
                "default": "TEXT_2_VIDEO",
                "enum": ["TEXT_2_VIDEO", "FIRST_AND_LAST_FRAMES_2_VIDEO", "REFERENCE_2_VIDEO"]
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Соотношение сторон (16:9 landscape, 9:16 portrait)",
                "required": False,
                "default": "16:9",
                "enum": ["16:9", "9:16", "Auto"]
            }
        }
    },
    {
        "id": "sora-2-pro-storyboard",
        "name": "Sora 2 Pro Storyboard",
        "description": "OpenAI Sora 2 Pro Storyboard - продвинутая AI модель для структурированной генерации видео, поддерживающая многосценовые последовательности и визуальную согласованность до 25 секунд.",
        "category": "Видео",
        "emoji": "📽️",
        "pricing": "Скоро появится",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание видео (скоро появится)",
                "required": True
            }
        },
        "coming_soon": True
    },
    {
        "id": "kling/v2-5-turbo",
        "name": "Kling 2.5 Turbo",
        "description": "Kling 2.5 Turbo - последняя AI модель генерации видео от Kuaishou Kling для text-to-video и image-to-video. Улучшенное следование промптам, плавное движение и реалистичная физика.",
        "category": "Видео",
        "emoji": "⚡",
        "pricing": "Скоро появится",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание видео (скоро появится)",
                "required": True
            }
        },
        "coming_soon": True
    },
    {
        "id": "hailuo/2.3",
        "name": "Hailuo 2.3",
        "description": "Hailuo 2.3 - высококачественная AI модель генерации видео от MiniMax для создания реалистичного движения, выразительных персонажей и кинематографических визуалов.",
        "category": "Видео",
        "emoji": "🎞️",
        "pricing": "Скоро появится",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание видео (скоро появится)",
                "required": True
            }
        },
        "coming_soon": True
    },
    {
        "id": "infinitalk/from-audio",
        "name": "Infinitalk API-AI lip-sync",
        "description": "InfiniteTalk API - продвинутый AI генератор синхронизации губ от MeiGen-AI. Преобразует изображения или текст с аудио в естественные говорящие аватары с точной синхронизацией губ.",
        "category": "Видео",
        "emoji": "👄",
        "pricing": "Скоро появится",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание (скоро появится)",
                "required": True
            }
        },
        "coming_soon": True
    },
    {
        "id": "elevenlabs/audio-isolation",
        "name": "Elevenlabs Audio Isolation",
        "description": "ElevenLabs Audio Isolation API использует AI для удаления фонового шума, музыки и помех, сохраняя четкую естественную речь. Идеально для подкастов, интервью и профессиональных записей.",
        "category": "Аудио",
        "emoji": "🎧",
        "pricing": "Скоро появится",
        "input_params": {
            "audio_url": {
                "type": "string",
                "description": "URL аудиофайла (скоро появится)",
                "required": True
            }
        },
        "coming_soon": True
    },
    {
        "id": "elevenlabs/sound-effect",
        "name": "Elevenlabs Sound Effect",
        "description": "Elevenlabs Sound Effect V2 API - обновленная версия модели звуковых эффектов, поддерживающая клипы 20+ секунд, бесшовное зацикливание и 48 кГц аудио.",
        "category": "Аудио",
        "emoji": "🔊",
        "pricing": "Скоро появится",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание звукового эффекта (скоро появится)",
                "required": True
            }
        },
        "coming_soon": True
    },
    {
        "id": "elevenlabs/text-to-speech",
        "name": "Elevenlabs Text to Speech",
        "description": "ElevenLabs Text to Speech API - человеческий голос для вашего контента. Доступен через Kie.ai для подкастов, приложений и многого другого.",
        "category": "Аудио",
        "emoji": "🗣️",
        "pricing": "Скоро появится",
        "input_params": {
            "text": {
                "type": "string",
                "description": "Текст для преобразования в речь (скоро появится)",
                "required": True
            }
        },
        "coming_soon": True
    },
    {
        "id": "google/nanobanana-gemini-2.5-flash",
        "name": "Google NanoBanana-Gemini 2.5 Flash",
        "description": "Gemini 3 Image Preview (Nano Banana) - продвинутая AI модель, превосходящая в генерации и редактировании изображений на основе естественного языка. Создает гиперреалистичные, физически осознанные визуалы.",
        "category": "Изображения",
        "emoji": "🍌",
        "pricing": "Скоро появится",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание изображения (скоро появится)",
                "required": True
            }
        },
        "coming_soon": True
    },
    {
        "id": "runway/gen-4",
        "name": "Runway Video Generation",
        "description": "Runway API на базе архитектуры Gen-4 от Runway AI. Преобразует идеи в потрясающие видео с помощью Runway Gen 4 Turbo API и Runway Aleph API.",
        "category": "Видео",
        "emoji": "🎬",
        "pricing": "Скоро появится",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание видео (скоро появится)",
                "required": True
            }
        },
        "coming_soon": True
    },
    {
        "id": "elevenlabs/text-to-dialogue-v3",
        "name": "ElevenLabs Text to Dialogue V3",
        "description": "Генерация диалогов и речи из текста. Поддержка 70+ языков, настройка стабильности голоса. Идеально для озвучки, подкастов и аудиокниг.",
        "category": "Аудио",
        "emoji": "🗣️",
        "pricing": "14 кредитов за 1000 символов",
        "input_params": {
            "text": {
                "type": "string",
                "description": "Текст для преобразования в речь (до 10000 символов)",
                "required": True,
                "max_length": 10000
            },
            "stability": {
                "type": "number",
                "description": "Стабильность голоса (0-1, шаг 0.5)",
                "required": False,
                "default": 0.5
            },
            "language_code": {
                "type": "string",
                "description": "Код языка (auto, en, ru, zh и др.)",
                "required": False,
                "default": "auto",
                "enum": ["auto", "en", "ru", "zh", "es", "fr", "de", "it", "pt", "ja", "ko", "ar", "hi", "tr", "pl", "nl", "sv", "da", "no", "fi", "cs", "uk"]
            }
        }
    },
    {
        "id": "suno/v5",
        "name": "🔥 Suno V5 Music",
        "description": "⭐ ТОП МОДЕЛЬ! Suno V5 — генерация музыки из текста. Создание треков, расширение, добавление вокала/инструментов, отделение голоса, конвертация в WAV.",
        "category": "Аудио",
        "emoji": "🎵",
        "is_featured": True,
        "pricing": "0.31-38.53 ₽ (Lyrics: $0.002, Generate: $0.06, Multi-Stem: $0.25)",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Описание желаемой музыки (до 5000 символов)",
                "required": True,
                "max_length": 5000
            },
            "style": {
                "type": "string",
                "description": "Музыкальный стиль (до 1000 символов)",
                "required": False,
                "max_length": 1000
            },
            "title": {
                "type": "string",
                "description": "Название трека (до 200 символов)",
                "required": False,
                "max_length": 200
            },
            "instrumental": {
                "type": "boolean",
                "description": "Только инструментал (без вокала)",
                "required": False,
                "default": False
            },
            "model": {
                "type": "string",
                "description": "Версия модели",
                "required": False,
                "default": "V5",
                "enum": ["V3_5", "V4", "V4_5", "V4_5PLUS", "V5"]
            }
        }
    },
    {
        "id": "midjourney/api",
        "name": "Midjourney API",
        "description": "AI API от Kie.ai для генерации изображений и видео. Поддерживает text-to-image, image-to-image, image-to-video и upscaling с высоким качеством.",
        "category": "Изображения",
        "emoji": "🎨",
        "pricing": "Скоро появится",
        "input_params": {
            "prompt": {
                "type": "string",
                "description": "Текстовое описание (скоро появится)",
                "required": True
            }
        },
        "coming_soon": True
    }
]


def get_model_by_id(model_id: str) -> dict:
    """Get model by ID"""
    for model in KIE_MODELS:
        if model["id"] == model_id:
            return model
    return None


def get_models_by_category(category: str = None) -> list:
    """Get models filtered by category"""
    if category:
        return [m for m in KIE_MODELS if m["category"] == category]
    return KIE_MODELS


def get_categories() -> list:
    """Get list of available categories"""
    categories = list(set([m["category"] for m in KIE_MODELS]))
    return sorted(categories)


# Generation types mapping
def _get_free_tools_model_ids() -> set:
    try:
        from pricing.engine import load_config

        config = load_config()
        free_tools = config.get("free_tools", {}) if isinstance(config, dict) else {}
        model_ids = free_tools.get("model_ids", [])
        if isinstance(model_ids, list):
            return set(model_ids)
    except Exception:
        return set()
    return set()
GENERATION_TYPES = {
    # Video Generation
    "text-to-video": {
        "name": "🎬 Текст в видео",
        "description": "Создавайте видео из текстового описания",
        "models": ["sora-2-text-to-video", "kling-2.6/text-to-video", "kling/v2-5-turbo-text-to-video-pro", "wan/2-6-text-to-video", "wan/2-5-text-to-video", "hailuo/02-text-to-video-pro", "hailuo/02-text-to-video-standard", "kling/v2-1-master-text-to-video", "grok/imagine", "google/veo-3.1", "kling/v2-5-turbo", "hailuo/2.3", "runway/gen-4"]
    },
    "image-to-video": {
        "name": "📸 Фото в видео",
        "description": "Превращайте изображения в динамичные видео",
        "models": ["sora-2-pro-image-to-video", "kling-2.6/image-to-video", "kling-2.6/motion-control", "kling/v2-5-turbo-image-to-video-pro", "wan/2-5-image-to-video", "hailuo/02-image-to-video-pro", "hailuo/02-image-to-video-standard", "bytedance/v1-pro-fast-image-to-video", "kling/v2-1-master-image-to-video", "kling/v2-1-standard", "kling/v2-1-pro", "grok/imagine", "google/veo-3.1", "kling/v2-5-turbo", "hailuo/2.3", "runway/gen-4"]
    },
    "video-editing": {
        "name": "✂️ Редактирование видео",
        "description": "Редактирование и обработка видео",
        "models": ["sora-watermark-remover", "topaz/video-upscale"]
    },
    "speech-to-video": {
        "name": "🎙️ Речь в видео",
        "description": "Создание видео из речи и аудио",
        "models": ["wan/2-2-a14b-speech-to-video-turbo", "infinitalk/from-audio"]
    },
    "lip-sync": {
        "name": "👄 Синхронизация губ",
        "description": "Синхронизация губ с аудио",
        "models": ["kling/v1-avatar-standard", "kling/ai-avatar-v1-pro", "wan/2-2-animate-move", "wan/2-2-animate-replace", "infinitalk/from-audio"]
    },
    # Image Generation
    "text-to-image": {
        "name": "✨ Текст в фото",
        "description": "Создавайте изображения из текста",
        "models": ["z-image", "google/nano-banana", "seedream/4.5-text-to-image", "flux-2/pro-text-to-image", "flux-2/flex-text-to-image", "bytedance/seedream-v4-text-to-image", "bytedance/seedream", "qwen/text-to-image", "ideogram/v3-text-to-image", "google/imagen4-ultra", "google/imagen4-fast", "google/imagen4", "grok/imagine", "openai/4o-image", "flux/kontext", "google/nanobanana-gemini-2.5-flash"]
    },
    "image-to-image": {
        "name": "🎨 Фото в фото",
        "description": "Трансформация и стилизация изображений",
        "models": ["seedream/4.5-edit", "flux-2/pro-image-to-image", "flux-2/flex-image-to-image", "nano-banana-pro", "bytedance/seedream-v4-edit", "qwen/image-to-image", "ideogram/v3-remix", "openai/4o-image", "flux/kontext", "google/nanobanana-gemini-2.5-flash", "google/nano-banana-edit"]
    },
    "image-editing": {
        "name": "🖼️ Редактирование фото",
        "description": "Редактирование и улучшение изображений",
        "models": ["topaz/image-upscale", "recraft/crisp-upscale", "recraft/remove-background", "ideogram/v3-reframe", "qwen/image-edit", "ideogram/character-edit", "ideogram/character-remix", "ideogram/character", "ideogram/v3-edit"]
    },
    "text-to-speech": {
        "name": "🗣️ Текст в речь",
        "description": "Генерация речи и диалогов из текста",
        "models": ["elevenlabs/text-to-dialogue-v3"]
    }
}


def get_generation_types() -> list:
    """Get list of available generation types"""
    return list(GENERATION_TYPES.keys())


def get_models_by_generation_type(gen_type: str) -> list:
    """Get models for a specific generation type"""
    if gen_type not in GENERATION_TYPES:
        return []
    
    model_ids = GENERATION_TYPES[gen_type]["models"]
    result = []
    free_ids = _get_free_tools_model_ids()
    
    for model in KIE_MODELS:
        model_id = model["id"]
        if model_id in model_ids and model_id not in free_ids:
            result.append(model)
    
    return result


def get_generation_type_info(gen_type: str) -> dict:
    """Get information about a generation type"""
    return GENERATION_TYPES.get(gen_type, {})


def normalize_model_for_api(model: dict) -> dict:
    """
    Нормализует модель для единообразного использования в API.
    Добавляет недостающие поля: title, generation_type, input_schema, help.
    """
    normalized = model.copy()
    
    # Добавляем title (используем name если есть, иначе id)
    if 'title' not in normalized:
        normalized['title'] = normalized.get('name', normalized.get('id', 'Unknown'))
    
    # Определяем generation_type на основе id и category
    if 'generation_type' not in normalized:
        model_id = normalized.get('id', '').lower()
        category = normalized.get('category', '').lower()
        
        # Определяем тип генерации
        if 'text-to-video' in model_id or ('video' in category and 'text' in model_id):
            gen_type = 'text_to_video'
        elif 'image-to-video' in model_id or ('video' in category and 'image' in model_id):
            gen_type = 'image_to_video'
        elif 'text-to-image' in model_id or ('фото' in category and 'text' in model_id):
            gen_type = 'text_to_image'
        elif 'image-to-image' in model_id or 'edit' in model_id:
            gen_type = 'image_to_image'
        elif 'remove' in model_id or 'background' in model_id:
            gen_type = 'remove_bg'
        elif 'upscale' in model_id:
            gen_type = 'upscale'
        elif 'speech-to-text' in model_id:
            gen_type = 'speech_to_text'
        elif 'text-to-speech' in model_id:
            gen_type = 'text_to_speech'
        elif 'text-to-music' in model_id or 'suno' in model_id:
            gen_type = 'text_to_music'
        else:
            # Fallback: определяем по GENERATION_TYPES
            gen_type = 'text_to_image'  # Default
            for gt, info in GENERATION_TYPES.items():
                if normalized.get('id') in info.get('models', []):
                    gen_type = gt.replace('-', '_')
                    break
        
        normalized['generation_type'] = gen_type
    
    # Добавляем input_schema (используем input_params если есть)
    if 'input_schema' not in normalized:
        if 'input_params' in normalized:
            # Конвертируем input_params в input_schema
            schema = {}
            for param_name, param_info in normalized['input_params'].items():
                schema[param_name] = param_info.get('type', 'string')
            normalized['input_schema'] = schema
        else:
            normalized['input_schema'] = {}
    
    # Добавляем help (используем description если есть)
    if 'help' not in normalized:
        help_text = normalized.get('description', '')
        if not help_text:
            # Генерируем базовую инструкцию
            gen_type = normalized.get('generation_type', '')
            if 'text_to_image' in gen_type:
                help_text = "Отправь текстовый промпт, выбери соотношение сторон и получи изображение."
            elif 'image_to_image' in gen_type:
                help_text = "Отправь изображение и текстовый промпт для трансформации."
            elif 'text_to_video' in gen_type:
                help_text = "Отправь текстовый промпт и получи видео."
            elif 'image_to_video' in gen_type:
                help_text = "Отправь изображение и получи видео."
            else:
                help_text = f"Используй модель {normalized.get('title', 'Unknown')} для генерации."
        normalized['help'] = help_text
    
    return normalized


def get_normalized_models() -> list:
    """Возвращает список моделей с нормализованной структурой."""
    return [normalize_model_for_api(model) for model in KIE_MODELS]
