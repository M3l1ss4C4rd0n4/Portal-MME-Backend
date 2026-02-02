import sys
import os
import importlib
import traceback
import unittest
from pathlib import Path

# Add server root to path
server_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(server_root))

from infrastructure.database.manager import db_manager
from core.app_factory import create_app

class TestDashboardModules(unittest.TestCase):
    def test_database_connection(self):
        """Verify DB manager works"""
        print("\n[DB] Testing database connection...")
        try:
            # Simple query
            df = db_manager.query_df("SELECT sqlite_version()")
            
            self.assertFalse(df.empty, "Database query returned empty result")
            print(f"✅ DB Connection OK. SQLite Version: {df.iloc[0,0]}")
        except Exception as e:
            self.fail(f"❌ DB Connection Failed: {e}")

    def test_app_creation(self):
        """Verify app can be created (which imports all pages)"""
        print("\n[App] Testing app creation and page registration...")
        try:
            # create_app() will trigger Dash to import all pages in interface/pages
            app = create_app()
            self.assertIsNotNone(app)
            print("✅ App created successfully. All pages imported.")
        except Exception as e:
            print("❌ App creation FAILED")
            traceback.print_exc()
            self.fail(f"App creation failed: {e}")

if __name__ == '__main__':
    unittest.main()
