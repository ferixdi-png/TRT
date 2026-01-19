"""Error taxonomy for traceability."""

ERROR_CATALOG = {
    "UI_UNKNOWN_CALLBACK": "Проверьте список callback и router регистрации.",
    "SESSION_CORRUPT": "Проверьте восстановление сессии и storage.",
    "PARAM_MISSING": "Проверьте обязательные параметры модели.",
    "PARAM_INVALID_ENUM": "Проверьте enum/validations для параметров.",
    "PRICING_NOT_FOUND": "Проверьте каталог цен и settings.",
    "KIE_AUTH": "Проверьте KIE_API_KEY и права доступа.",
    "KIE_RATE_LIMIT": "Проверьте лимиты KIE и повторные запросы.",
    "KIE_TIMEOUT": "Проверьте timeout/backoff и статус KIE.",
    "KIE_FAIL_STATE": "Проверьте ответ KIE recordInfo/failed.",
    "KIE_RESULT_EMPTY": "Проверьте наличие resultJson/resultUrls/resultText в ответе KIE.",
    "KIE_RESULT_EMPTY_TEXT": "Проверьте текстовые поля resultText/resultObject в ответе KIE.",
    "TG_SEND_FAIL": "Проверьте параметры отправки в Telegram.",
    "STORAGE_READ_FAIL": "Проверьте доступ к storage/permissions.",
    "STORAGE_WRITE_FAIL": "Проверьте доступ к storage/permissions.",
    "INTERNAL_EXCEPTION": "Проверьте stacktrace и логи.",
}
