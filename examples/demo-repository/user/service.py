"""
User Service - intentionally has duplicate logic with OrderService.
Issues: Duplicate Code
"""


class UserService:
    def __init__(self):
        self.users = {}
        self.next_id = 1

    def create_user(self, name, email, role="customer"):
        # validate
        if not name:
            raise ValueError("Name is required")
        if not isinstance(name, str):
            raise ValueError("Name must be a string")
        if not email:
            raise ValueError("Email is required")
        if not isinstance(email, str):
            raise ValueError("Email must be a string")
        if "@" not in email:
            raise ValueError("Invalid email format")
        if role not in ("customer", "admin", "seller"):
            raise ValueError("Invalid role")

        # check duplicate
        for user in self.users.values():
            if user["email"] == email:
                raise ValueError("Email already registered")

        user_id = self.next_id
        self.next_id += 1
        user = {
            "id": user_id,
            "name": name,
            "email": email,
            "role": role,
            "active": True,
        }
        self.users[user_id] = user
        return user

    def get_user(self, user_id):
        return self.users.get(user_id)

    def deactivate_user(self, user_id):
        user = self.users[user_id]  # BUG: KeyError if not found
        user["active"] = False
        return user

    def list_users(self, role=None):
        results = []
        for user in self.users.values():
            if role and user["role"] != role:
                continue
            results.append(user)
        return results
