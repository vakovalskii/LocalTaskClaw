# Xiaozhi MCP Integration | Интеграция Xiaozhi MCP

Интеграция LocalTaskClawXiaozhi с MCP-сервером через `mcp_pipe.py`.

## Обзор

Этот MCP-сервер предоставляет инструменты для управления LocalTaskClawXiaozhi через MCP-протокол:
- Управление kanban-досками (проектами)
- Создание и управление задачами
- Управление агентами
- Запуск проектов через "spawn"

## Установка

### 1. Установка зависимостей

```bash
cd /media/alexander/data/ML/MCP/LocalTaskClawXiaozhi/mcp
pip install -r requirements.txt
```

### 2. Запуск LocalTaskClawXiaozhi

Убедитесь, что LocalTaskClawXiaozhi запущен:

```bash
ltc start
```

Проверка доступности:

```bash
curl http://localhost:11387/health
```

### 3. Запуск MCP-сервера

```bash
cd mcp
export MCP_ENDPOINT="ws://your-mcp-endpoint/ws"
python mcp_pipe.py
```

Или запустить только один сервер:

```bash
python server_xiaozhi.py
```

## MCP Инструменты

### Kanban (Задачи)

| Инструмент | Описание |
|------------|----------|
| `xiaozhi_kanban_list(column)` | Список задач (опционально по колонке) |
| `xiaozhi_kanban_create(title, description, agent_id, column, board_id, repeat_minutes)` | Создать задачу |
| `xiaozhi_kanban_move(task_id, column)` | Переместить задачу в другую колонку |
| `xiaozhi_kanban_run(task_id)` | Запустить агента на задаче |
| `xiaozhi_kanban_verify(task_id, approved, comment)` | Проверить выполненную задачу |

### Агенты

| Инструмент | Описание |
|------------|----------|
| `xiaozhi_agents_list()` | Список всех агентов |
| `xiaozhi_agent_create(name, system_prompt, role, emoji, color)` | Создать агента |

### Проекты (Доски)

| Инструмент | Описание |
|------------|----------|
| `xiaozhi_boards_list()` | Список всех досок/проектов |
| `xiaozhi_board_create(name, emoji)` | Создать новую доску |
| `xiaozhi_project_spawn(description, board_id, stream)` | Создать проект с агентами и задачами |

### Другое

| Инструмент | Описание |
|------------|----------|
| `xiaozhi_chat(message, chat_id, stream)` | Отправить сообщение агенту |
| `xiaozhi_health()` | Проверка статуса сервера |

## Примеры использования

### Создание новой задачи в kanban

```python
# Через MCP-клиент
result = xiaozhi_kanban_create(
    title="Написать документацию",
    description="Создать README для проекта",
    agent_id=1,
    column="backlog",
    board_id=1
)
```

### Запуск проекта через spawn

```python
# Автоматическое создание команды агентов и задач
result = xiaozhi_project_spawn(
    description="Создать веб-скрапер для сбора новостей с технических сайтов"
)
```

### Проверка выполненной задачи

```python
# Утверждение задачи
result = xiaozhi_kanban_verify(
    task_id=5,
    approved=True,
    comment="Отличная работа, всё соответствует требованиям"
)
```

## Конфигурация в mcp_config.json

```json
{
  "mcpServers": {
    "xiaozhi-kanban": {
      "type": "stdio",
      "command": "python",
      "args": ["-u", "server_xiaozhi.py"],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "XIAOZHI_BASE_URL": "http://localhost:11387",
        "XIAOZHI_API_KEY": ""
      }
    }
  }
}
```

## Архитектура

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────────┐
│   MCP Client    │──────│  xiaozhi_mcp.py  │──────│  LocalTaskClawXiaozhi │
│   (AI Model)    │ stdio│  (MCP Server)    │ HTTP │  (port 11387)       │
└─────────────────┘      └──────────────────┘      └─────────────────────┘
                                                        │
                                                        ├── Kanban Board
                                                        ├── Agents
                                                        └── Tasks
```

## Структура файлов

```
mcp/
├── server_xiaozhi.py    # MCP сервер для Xiaozhi
├── mcp_pipe.py          # Коммуникационный шлюз
├── mcp_config.json      # Конфигурация MCP серверов
└── requirements.txt     # Зависимости
```

## API Endpoints (LocalTaskClawXiaozhi)

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/health` | GET | Проверка статуса |
| `/kanban` | GET | Список задач |
| `/kanban/tasks` | POST | Создать задачу |
| `/kanban/tasks/{id}/move` | POST | Переместить задачу |
| `/kanban/tasks/{id}/run` | POST | Запустить агента |
| `/kanban/tasks/{id}/verify` | POST | Проверить задачу |
| `/agents` | GET/POST | Список/создание агентов |
| `/kanban/boards` | GET/POST | Список/создание досок |
| `/spawn` | POST | Создать проект |

## Troubleshooting

### Ошибка подключения

```
Error: Connection refused to http://localhost:11387
```

**Решение:** Убедитесь, что LocalTaskClawXiaozhi запущен:
```bash
ltc status
```

### Ошибка аутентификации

```
Error: 401 Unauthorized
```

**Решение:** Установите правильный `XIAOZHI_API_KEY` в `.env` или `mcp_config.json`.

### Таймаут запроса

```
Error: Request timeout
```

**Решение:** Увеличьте таймаут в `server_xiaozhi.py` или проверьте, что сервер не перегружен.

## Лицензия

MIT
