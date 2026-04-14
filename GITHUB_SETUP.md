# GitHub Setup

Этот вариант рассчитан на отдельный новый репозиторий GitHub для `TehNio`.

## Что загружать в новый репозиторий

В новый репозиторий нужно заливать содержимое папки `auto_news_bot`, а не весь `Playground`.

В корне нового репозитория должны лежать:

- `main.py`
- `news_bot/`
- `.github/workflows/tehnio-auto-posts.yml`
- `scripts/build_ci_config.py`
- `config.tehnio.example.json`
- `state/`

## Что делает GitHub Actions

Workflow `TehNio Auto Posts`:

- запускается каждые 30 минут;
- умеет запускаться вручную через `Run workflow`;
- собирает `config.ci.json` из `config.tehnio.example.json` и GitHub secrets/variables;
- публикует новости в Telegram;
- сохраняет `state/news.db` обратно в репозиторий, чтобы не было дублей.

## GitHub Secrets

В `Settings -> Secrets and variables -> Actions -> Secrets` добавьте:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHANNEL_ID`
- `OPENAI_API_KEY` — опционально, только если хотите LLM-сводку и комментарии

Пример `TELEGRAM_CHANNEL_ID`:

- `@TehNio`

## GitHub Variables

В `Settings -> Secrets and variables -> Actions -> Variables` можно добавить:

- `AUTO_NEWS_PUBLICATION_TITLE`: `TehNio`
- `AUTO_NEWS_SUBSCRIBE_CTA_TEXT`: `⚔️ Вступить в легион TehNio!`
- `AUTO_NEWS_LINK_TEXT`: `Подробности ниже 👇`
- `OPENAI_MODEL`: `gpt-4o-mini`
- `AUTO_NEWS_MAX_POSTS_PER_CYCLE`: `1` или `2`
- `AUTO_NEWS_MIN_PUBLISH_GAP_MINUTES`: `20`

Если variable не задана, берется значение из `config.tehnio.example.json`.

## Обязательная настройка репозитория

В `Settings -> Actions -> General` включите для `GITHUB_TOKEN`:

- `Read and write permissions`

Иначе workflow не сможет коммитить `state/news.db`.

## Первый запуск

1. Создайте новый пустой репозиторий на GitHub.
2. Загрузите туда содержимое папки `auto_news_bot`.
3. Добавьте secrets и variables.
4. Откройте вкладку `Actions`.
5. Выберите `TehNio Auto Posts`.
6. Нажмите `Run workflow`.
7. Для первой проверки лучше включить `dry_run=true`.

## После проверки

Когда dry-run выглядит нормально:

- запустите workflow вручную уже без `dry_run`;
- дальше публикации пойдут автоматически по расписанию.

## Важные замечания

- Инсайдерские X-источники в `config.tehnio.example.json` оставлены выключенными как `RSS bridge`-заглушки. Их нужно заменить на реальные RSS/Atom мосты.
- Без `OPENAI_API_KEY` бот все равно работает: summary и комментарий будут собираться встроенной логикой.
- База `state/news.db` будет меняться после публикаций и коммититься самим workflow.
