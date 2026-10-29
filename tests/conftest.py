import os
import tempfile
import pytest

# Ensure all tests use an isolated temporary database
_test_db = os.path.join(tempfile.gettempdir(), "test_auto_mail.db")
os.environ["AUTO_MAIL_DB_PATH"] = _test_db

from backend.database import init_db

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    init_db()
    yield
    if os.path.exists(_test_db):
        try:
            os.remove(_test_db)
        except Exception:
            pass

