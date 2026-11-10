import unittest
import ast
from pathlib import Path
from runpy import run_path
# Load the pure policy without core.__init__, which initializes the legacy UI/DB stack.
require_patient_registration = run_path(str(Path(__file__).parents[1] / "core/registration_policy.py"))["require_patient_registration"]

# Exercise the actual service guard before any DB access, without importing the
# legacy Streamlit/SQLAlchemy package or touching its hardcoded patient database.
source = Path(__file__).parents[1] / "services/user_service.py"
functions = [node for node in ast.parse(source.read_text()).body
             if isinstance(node, ast.FunctionDef) and node.name in {"create_user", "ensure_default_users"}]
def forbidden_database_access():
    raise AssertionError("Public staff signup must fail before database access")
namespace = {"require_patient_registration": require_patient_registration,
             "get_db_context": forbidden_database_access}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)

class PublicRegistrationTests(unittest.TestCase):
    def test_service_denies_staff_before_database_access(self):
        for role in ("doctor", "physician", "technician", "admin", " PHYSICIAN "):
            with self.subTest(role=role), self.assertRaises(ValueError):
                namespace["create_user"](role, "synthetic", "synthetic-password")

    def test_default_user_hook_never_accesses_database(self):
        self.assertIsNone(namespace["ensure_default_users"]())

    def test_patient_allowed(self):
        require_patient_registration("patient")

    def test_privileged_and_invalid_roles_denied(self):
        for role in ("doctor", "physician", "technician", "admin", "", "Patient", None):
            with self.subTest(role=role), self.assertRaises(ValueError):
                require_patient_registration(role)

if __name__ == "__main__":
    unittest.main()
