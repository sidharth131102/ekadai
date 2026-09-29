from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.errors import DomainError
from app.routers import auth, cart, catalog, checkout, events, orders, reviews, users, wishlist
from events import producer as events_producer


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Only swap in the real Kafka transport when explicitly configured — the default
    # ("logging") keeps a fresh clone / the test suite free of any Kafka dependency.
    if settings.event_transport == "kafka":
        from events.transports.kafka_avro_transport import KafkaAvroTransport

        transport = KafkaAvroTransport(settings.kafka_bootstrap_servers, settings.schema_registry_url)
        events_producer.set_transport(transport)
        yield
        transport.flush()
    else:
        yield


app = FastAPI(title="Ekadai API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(catalog.router)
app.include_router(cart.router)
app.include_router(wishlist.router)
app.include_router(checkout.router)
app.include_router(orders.router)
app.include_router(events.router)
app.include_router(reviews.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
