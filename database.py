import asyncpg
from pydantic_settings import BaseSettings, SettingsConfigDict

# 1. Configuração lendo do .env
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    database_url: str

settings = Settings()  # type: ignore

# 2. Classe gerenciadora do Pool
class Database:
    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        # Cria o pool de conexões
        self.pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=2,
            max_size=10
        )
        print("✅ Conectado ao PostgreSQL!")

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            print("🔌 Desconectado do PostgreSQL.")

db = Database()

# 3. Dependency do FastAPI (injeta a conexão nas rotas)
async def get_db():
    if not db.pool:
        raise RuntimeError("Banco de dados não inicializado.")
    async with db.pool.acquire() as connection:
        yield connection