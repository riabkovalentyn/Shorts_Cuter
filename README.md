# Shorts Cuter

MVP приложения для нарезки стримов на клипы (Shorts/Reels) с последующей загрузкой на YouTube.

## Стек
- Frontend: React + TypeScript + Tailwind
- Backend: Node.js + TypeScript (Express)
- DB: MongoDB
- Очереди: BullMQ (Redis) или in-process
- Видеообработка: ffmpeg (fluent-ffmpeg)
- Авторизация YouTube: OAuth2 (refreshToken)
- Инфраструктура: Docker + docker-compose

## Структура
- `frontend/` — клиентское приложение
- `backend/` — серверное приложение
- `docker-compose.yml` — локальный запуск (mongo + backend + frontend)

## Единая точка запуска

Локальная разработка (оба сервиса поднимутся одновременно):

1) Установите зависимости в корне (мы добавили скрипты):

```powershell
cd D:\YouTube_Shorts_Cuter\Shorts_Cuter
npm install
```

2) Поднимите Mongo (в Docker) отдельно, чтобы бэкенд мог подключиться:

```powershell
docker compose up -d mongo
```

3) Старт разработки (фронтенд + бэкенд):

```powershell
npm run dev
```

- Бэкенд: http://localhost:4000
- Фронтенд: http://localhost:5173

Сборка проекта:

```powershell
npm run build
```

Прод-запуск локально (бэкенд + превью фронта):

```powershell
npm start
```

## Переменные окружения (YouTube OAuth)

Заполните файл `backend/.env` по образцу `backend/.env.sample`:

```
PORT=4000
MONGO_URI=mongodb://localhost:27017/shorts_cuter
STORAGE_DIR=./storage

GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
YT_REDIRECT_URI=http://localhost:4000/api/auth/youtube/callback
```

Без `GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET` кнопка подключения YouTube вернёт ошибку, это ожидаемо. После заполнения переменных нажмите Connect в Settings, пройдите OAuth, refreshToken сохранится в Mongo.

## Docker Compose (полный стек)

Для прод-сборки/демо можно запустить весь стек через Docker (Mongo + Backend + Frontend):

```powershell
docker compose up --build
```

Перед этим создайте файл `.env` в корне по образцу `.env.template` и заполните OAuth секреты. Backend автоматически получит их через `env_file`.

Пример `.env`:

```
MONGO_URI=mongodb://mongo:27017/shorts_cuter
PORT=4000
STORAGE_DIR=/app/storage
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
YT_REDIRECT_URI=http://localhost:4000/api/auth/youtube/callback
# REDIS_URL=redis://redis:6379
```

## Известные предупреждения/«PROBLEMS»

- Tailwind @tailwind/@apply в `frontend/src/index.css`: подавлены в VS Code (это валидные директивы для PostCSS). См. `.vscode/settings.json`.
- Вкладка Docker может показывать уязвимости базовых образов. Мы используем slim-образы (node:20-bookworm-slim, nginx:bookworm). Для прод окружений используйте внутренний сканер и политику обновлений.

## Трюки и устранение неполадок (Windows)

- Установите FFmpeg (для ffmpeg/ffprobe):
	- Chocolatey: choco install ffmpeg
	- Winget: winget install Gyan.FFmpeg
	- Вручную: скачайте сборку с https://www.gyan.dev/ffmpeg/builds/ и добавьте ffmpeg.exe/ffprobe.exe в PATH

- Установите yt-dlp (надёжная загрузка YouTube):
	- Chocolatey: choco install yt-dlp
	- Winget: winget install yt-dlp.yt-dlp
	- Вручную: https://github.com/yt-dlp/yt-dlp/releases и добавить в PATH

- Проверка:
	- В PowerShell: ffmpeg -version; ffprobe -version; yt-dlp --version
	- Если что-то не найдено — перезапустите терминал после установки, чтобы PATH обновился.