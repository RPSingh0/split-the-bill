import os

os.environ["FASTAPI_API_KEY"] = "test-api-key"
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost:5432/test"
os.environ["JWT_SECRET"] = "test-jwt-secret-that-is-long-enough-for-hs256"
