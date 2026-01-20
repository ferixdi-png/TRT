#!/bin/bash
# Скрипт для настройки webhook для Telegram бота

set -euo pipefail

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-${BOT_TOKEN:-}}"
WEBHOOK_URL="${WEBHOOK_URL:-${1:-}}"

if [[ -z "${BOT_TOKEN}" ]]; then
    echo "❌ Ошибка: TELEGRAM_BOT_TOKEN (или BOT_TOKEN) не установлен"
    echo "   Пример: TELEGRAM_BOT_TOKEN=... WEBHOOK_URL=https://example.com/webhook ./scripts/setup_webhook.sh"
    exit 1
fi

if [[ -z "${WEBHOOK_URL}" ]]; then
    echo "❌ Ошибка: WEBHOOK_URL не установлен"
    echo "   Пример: WEBHOOK_URL=https://example.com/webhook ./scripts/setup_webhook.sh"
    exit 1
fi

echo "🔧 Настройка webhook для Telegram бота..."
echo ""

# Проверка текущего webhook
echo "📋 Проверка текущего webhook:"
curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool
echo ""

# Установка webhook
echo "🔧 Установка webhook..."
RESPONSE=$(curl -s -F "url=${WEBHOOK_URL}" "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook")

echo "$RESPONSE" | python3 -m json.tool

# Проверка результата
if echo "$RESPONSE" | grep -q '"ok":true'; then
    echo ""
    echo "✅ Webhook успешно установлен!"
    echo "📍 URL: ${WEBHOOK_URL}"
else
    echo ""
    echo "❌ Ошибка при установке webhook!"
    exit 1
fi

echo ""
echo "📋 Финальная проверка:"
curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" | python3 -m json.tool
