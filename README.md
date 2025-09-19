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

## Быстрый старт (позже будет дополнено)
1. Установите Docker и Docker Desktop.
2. Запустите:
   - docker compose up --build

Дальше добавим Dockerfile для фронта/бэка и инструкцию по переменным окружения.