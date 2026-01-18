# Structured Log Contract

## Формат
Единый формат structured logs (JSON или key=value). Обязательные поля:

* `correlation_id`
* `user_id`
* `chat_id`
* `update_id`
* `action`
* `action_path`
* `model_id`
* `gen_type`
* `stage`
* `waiting_for`
* `param`
* `outcome`
* `duration_ms`
* `error_code`
* `fix_hint`

## Рекомендуемый пример (key=value)
```
correlation_id=... user_id=... chat_id=... update_id=... \
action=CALLBACK action_path=menu>gen_type>select_model \
model_id=... gen_type=... stage=router waiting_for=text param=prompt \
outcome=success duration_ms=12 error_code= fix_hint=
```

## Политика логирования
* **CALLBACK** логируется 1 раз на каждый callback.
* **PRICE_RUB** логируется только:
  * при выборе модели,
  * при подтверждении генерации.
* Любая ошибка: `outcome=error`, `error_code` и `fix_hint` обязательны.

## Диагностика
* `fix_hint` должен содержать короткое действие по исправлению (например: `check_kie_api_key` или `send_photo`).
* Для неизвестных callback → `outcome=fallback` и `unknown_callback=true`.
