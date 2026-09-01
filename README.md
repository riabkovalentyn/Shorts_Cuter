# Shorts Cuter

MVP приложения для нарезки стримов на клипы (Shorts/Reels) с последующей загрузкой на YouTube.

## Стек
- Frontend: React + TypeScript + Tailwind (Vite)
- Backend: Python 3.11+ (FastAPI)
- DB: MongoDB (Beanie ODM)
- Очереди: ARQ (Redis) или in-process background task
- Загрузка видео: yt-dlp (Python-пакет, отдельный бинарник не нужен)
- Видеообработка: ffmpeg / ffprobe
- Подбор моментов: Claude (`claude-opus-5`) + faster-whisper
- Авторизация YouTube: OAuth2 (refreshToken)
- Инфраструктура: Docker + docker-compose

## Структура
- `frontend/` — клиентское приложение
- `backend_py/` — серверное приложение (FastAPI)
- `docker-compose.yml` — локальный запуск (mongo + backend + frontend)

## Требования

- Python 3.11+
- Node.js 20+ (только для фронтенда)
- FFmpeg (`ffmpeg` и `ffprobe` в PATH)
- MongoDB (локально или через Docker)

Установка FFmpeg на Windows:

```powershell
winget install Gyan.FFmpeg
# или: choco install ffmpeg
```

Проверка: `ffmpeg -version; ffprobe -version`. Если команда не найдена — перезапустите терминал, чтобы PATH обновился.

> yt-dlp ставить отдельно **не нужно** — он приходит как зависимость Python.

## Локальная разработка

1) Виртуальное окружение и зависимости бэкенда:

```powershell
cd backend_py
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..
```

2) Зависимости фронтенда и корневые скрипты:

```powershell
npm install
npm --prefix frontend install
```

3) Поднимите Mongo:

```powershell
docker compose up -d mongo
```

4) Скопируйте `backend_py/.env.sample` в `backend_py/.env` и заполните значения.

5) Старт разработки (фронтенд + бэкенд одновременно):

```powershell
npm run dev
```

- Бэкенд: http://localhost:4000
- Swagger UI: http://localhost:4000/docs
- Фронтенд: http://localhost:5173

Только бэкенд:

```powershell
cd backend_py
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 4000
```

Тесты бэкенда:

```powershell
npm run test:backend
```

## Переменные окружения

Файл `backend_py/.env` (образец — `backend_py/.env.sample`):

```
PORT=4000
MONGO_URI=mongodb://localhost:27017/shorts_cuter
STORAGE_DIR=./storage

GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
YT_REDIRECT_URI=http://localhost:4000/api/auth/youtube/callback

# Необязательно: включает воркер ARQ вместо фоновой задачи в процессе API
# REDIS_URL=redis://localhost:6379
```

Без `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` кнопка подключения YouTube вернёт ошибку — это ожидаемо. После заполнения нажмите Connect в Settings, пройдите OAuth, `refreshToken` сохранится в Mongo.

`MONGO_URI` обязан содержать имя базы (`.../shorts_cuter`), иначе бэкенд не стартует.

## AI-подбор моментов

Клипы выбирает Claude по расшифровке стрима, а не эвристика по сценам и тишине.

Пайплайн:

1. `faster-whisper` расшифровывает VOD с таймкодами (CTranslate2, без torch).
2. Claude (`claude-opus-5`) читает расшифровку целиком — 4 часа стрима это ~60–80k токенов, при окне в 1M влезает за один запрос — и возвращает моменты в формате Twitch-клипа.
3. Он же пишет заголовок и описание для каждого клипа, поэтому шаблонный текст не применяется.

Формат клипа повторяет Twitch:

- длительность **5–60 секунд**, разная для каждого клипа;
- **развязка в конце** — Twitch по кнопке Clip забирает предыдущие секунды, а не последующие (его же API определяет `vod_offset` как *конец* клипа);
- клипы не пересекаются и самодостаточны.

Если слишком длинный фрагмент нужно обрезать, отрезается **начало** — чтобы развязка сохранилась.

Включение — задайте ключ в `backend_py/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-opus-5
# AI_EFFORT=high
# WHISPER_MODEL=base        # tiny|base|small|medium|large-v3
# WHISPER_LANGUAGE=en       # автоопределение, если не задано
# CLIP_MIN_SEC=5
# CLIP_MAX_SEC=60
```

Без ключа (или если `faster-whisper` не установлен, или Claude отказался отвечать) пайплайн **не падает**, а откатывается на старый детектор по сценам и тишине. В логах будет строка `AI selection unavailable (...); using heuristic`.

Стоимость: около **$0.45** за 4-часовой VOD (~70k входных токенов по $5/1M плюс ответ по $25/1M). Расшифровка идёт локально и по деньгам бесплатна, но требует CPU/GPU-времени.

> На AI-пути параметр `clipLengthSec` из формы игнорируется: длину каждого клипа выбирает модель в пределах 5–60 с.

## Очередь (необязательно)

По умолчанию пайплайн выполняется фоновой задачей внутри процесса API. Если задать `REDIS_URL`, задачи уходят в ARQ, и нужно поднять воркер:

```powershell
npm run worker
# или: cd backend_py; python -m arq app.worker.WorkerSettings
```

В `docker-compose.yml` для этого есть закомментированные сервисы `redis` и `worker`.

## Docker Compose (полный стек)

```powershell
docker compose up --build
```

Перед этим создайте `.env` в корне по образцу `.env.template`.

## API

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/projects` | создать задачу нарезки |
| GET | `/api/jobs/{id}` | статус задачи |
| GET | `/api/clips?jobId=` | список клипов |
| POST | `/api/clips/{id}/upload` | залить клип на YouTube |
| GET | `/api/auth/youtube/url` | старт OAuth |
| GET | `/api/auth/youtube/callback` | приём OAuth-кода |
| GET | `/api/auth/youtube/status` | состояние подключения |
| GET | `/health` | health-check |

Интерактивная документация: `/docs`.

## Деплой

Вариант A: Render.com (бэкенд + статический фронтенд)

- В репозитории есть `render.yaml`.
- В Render создайте Blueprint Deploy из вашего форка.
- Backend (Docker, контекст `backend_py`):
	- Переменные: `MONGO_URI` (MongoDB Atlas), `GOOGLE_CLIENT_ID`/`SECRET`, `YT_REDIRECT_URI`, опционально `REDIS_URL`.
	- Диск: имя `storage`, 1 GB+, точка монтирования `/app/storage`.
- Frontend (Static Site):
	- После первого деплоя бэкенда возьмите его URL и выставьте `VITE_API_URL`, затем пересоберите статику.

Опционально CI: создайте в Render Deploy Hook и сохраните URL в GitHub Secrets как `RENDER_BACKEND_HOOK_URL`. Workflow `.github/workflows/deploy-backend-render.yml` триггерит деплой на пуш в `main`.

Вариант B: GitHub Pages (только фронтенд)

- Бэкенд разместите на Render, возьмите публичный URL.
- Сохраните его в GitHub Secrets как `PUBLIC_API_URL`.
- Workflow `.github/workflows/deploy-frontend-pages.yml` соберёт `frontend` и опубликует в Pages.

## Известные ограничения

- Нет аутентификации: API открыт, CORS `*`, YouTube-токен один на всё приложение.
- Без `ANTHROPIC_API_KEY` работает только эвристика (склейки сцен + тишина): она находит визуально активные моменты, но не реакции стримера.
- Клипы не переводятся в вертикальный формат 9:16 — режется исходный кадр.
- На free-плане Render нет постоянного диска, а 512 МБ RAM мало для libx264.
