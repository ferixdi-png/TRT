# Git Remote Policy

## 🔴 КРИТИЧЕСКИ ВАЖНО

**ВСЕГДА пушить в репозиторий `ferixdi-png/TRT`!**

### Правильный remote:

```bash
origin  https://github.com/ferixdi-png/TRT.git
```

### Проверка перед push:

```bash
git remote -v
```

Должно быть:
```
origin  https://github.com/ferixdi-png/TRT.git (fetch)
origin  https://github.com/ferixdi-png/TRT.git (push)
```

### Если remote неправильный:

```bash
git remote set-url origin https://github.com/ferixdi-png/TRT.git
```

### Команда для push:

```bash
git push origin main
```

**НЕ использовать репозиторий `ferixdi-png/5656` - это другой проект!**

---

**Дата создания:** 2025-01-07  
**Статус:** ✅ Активно

