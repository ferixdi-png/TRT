#!/bin/bash
# Скрипт для удаления webhook и возврата к polling

set -euo pipefail

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-${BOT_TOKEN:-}}"

if [[ -z "${BOT_TOKEN}" ]]; then
    echo "❌ Ошибка: TELEGRAM_BOT_TOKEN (или BOT_TOKEN) не установлен"
    echo "   Пример: TELEGRAM_BOT_TOKEN=... ./scripts/remove_webhook.sh"
    exit 1
fi

echo "🔧 Удаление webhook и возврат к polling..."
echo ""

# Удаление webhook
RESPONSE=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/deleteWebhook")

echo "$RESPONSE" | python3 -m json.tool

# Проверка результата
if echo "$RESPONSE" | grep -q '"ok":true'; then
    echo ""
    echo "✅ Webhook успешно удалён!"
    echo "✅ Бот вернётся к polling режиму"
else
    echo ""
    echo "❌ Ошибка при удалении webhook!"
    exit 1
fi

echo ""
echo "📋 Проверка (webhook должен быть пустым):"
curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool
