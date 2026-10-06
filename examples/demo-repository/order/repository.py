"""
Order Repository - data access layer.
Issues: Duplicate Code pattern
"""


class OrderRepository:
    def __init__(self):
        self._storage = {}

    def save(self, order):
        order_id = order["id"]
        self._storage[order_id] = order
        return order

    def find_by_id(self, order_id):
        if order_id not in self._storage:
            return None
        return self._storage[order_id]

    def find_all(self):
        return list(self._storage.values())

    def find_by_user(self, user_id):
        results = []
        for order in self._storage.values():
            if order["user_id"] == user_id:
                results.append(order)
        return results

    def find_by_status(self, status):
        results = []
        for order in self._storage.values():
            if order["status"] == status:
                results.append(order)
        return results

    def delete(self, order_id):
        if order_id in self._storage:
            del self._storage[order_id]
            return True
        return False

    def count(self):
        return len(self._storage)
