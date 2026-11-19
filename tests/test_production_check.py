import unittest
from cryptography.fernet import Fernet
from scripts.production_check import validate_environment


class ProductionPreflightPolicyTests(unittest.TestCase):
    def valid_environment(self):
        return {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "s" * 48,
            "DATABASE_URL": "postgresql://user:pass@db.example.test/app",
            "FILE_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "INTEGRATION_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "PUBLIC_BASE_URL": "https://app.example.test",
            "RATELIMIT_STORAGE_URI": "redis://redis.example.test:6379/0",
            "REDIS_URL": "redis://redis.example.test:6379/0",
            "OPENAI_API_KEY": "sk-test-not-a-real-key",
            "S3_BUCKET": "private-ai-workforce-test",
            "AWS_REGION": "us-east-1",
            "STORAGE_BACKEND": "s3",
            "COOKIE_SECURE": "true",
            "SECURITY_HEADERS_ENABLED": "true",
        }

    def test_valid_production_environment_passes_policy(self):
        self.assertEqual(validate_environment(self.valid_environment()), [])

    def test_rejects_sqlite_and_non_tls_public_url(self):
        env = self.valid_environment()
        env["DATABASE_URL"] = "sqlite:///app.db"
        env["PUBLIC_BASE_URL"] = "http://app.example.test"
        errors = validate_environment(env)
        self.assertTrue(any("PostgreSQL" in error for error in errors))
        self.assertTrue(any("HTTPS" in error for error in errors))

    def test_rejects_shared_encryption_keys_and_missing_redis(self):
        env = self.valid_environment()
        env["INTEGRATION_ENCRYPTION_KEY"] = env["FILE_ENCRYPTION_KEY"]
        env.pop("REDIS_URL")
        errors = validate_environment(env)
        self.assertTrue(any("must be different" in error for error in errors))
        self.assertTrue(any("REDIS_URL" in error for error in errors))

    def test_rejects_invalid_fernet_key(self):
        env = self.valid_environment()
        env["FILE_ENCRYPTION_KEY"] = "not-a-fernet-key"
        self.assertTrue(any("valid Fernet" in error for error in validate_environment(env)))


if __name__ == "__main__":
    unittest.main()
