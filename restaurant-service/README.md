# Restaurant Service

## Uruchomienie przez Docker

Skonfiguruj zmienne srodowiskowe w pliku `.env`:

```env
POSTGRES_DB=restaurant_db
POSTGRES_USER=restaurant_user
POSTGRES_PASSWORD=restaurant_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
```

```bash
docker compose up --build
```

Docker Compose uruchamia PostgreSQL, czeka az baza bedzie gotowa, wykonuje migracje i startuje serwer Django.

Swagger dostepny pod adresem `http://localhost:8000/api/docs`.

## Endpointy

- `GET /api/restaurants/`
- `POST /api/restaurants/apply/`
- `GET/PUT /api/restaurants/{id}/`
- `GET /api/restaurants/{id}/menu/`
- `GET /api/restaurants/{id}/orders/`
- `PATCH /api/restaurants/{id}/orders/{order_id}/accept/`
- `PATCH /api/restaurants/{id}/orders/{order_id}/reject/`
- `PATCH /api/restaurants/{id}/orders/{order_id}/preparing/`
- `PATCH /api/restaurants/{id}/orders/{order_id}/ready/`
- `GET/POST /api/restaurants/{id}/menus/`
- `PUT/DELETE /api/restaurants/{id}/menus/{menu_id}/`
- `POST /api/restaurants/{id}/menus/{menu_id}/items/`
- `PUT/DELETE /api/restaurants/{id}/menus/{menu_id}/items/{item_id}/`
- `GET /api/admin/restaurants/pending/`
- `GET /api/admin/restaurants/{id}/`
- `PATCH /api/admin/restaurants/{id}/verify/`
- `GET /api/internal/restaurants/{id}/is-open/`
- `GET /api/internal/restaurants/{id}/covers-address/`
- `GET /api/internal/restaurants/{id}/menu-items/`
- `GET /api/schema/`
- `GET /api/docs/`
