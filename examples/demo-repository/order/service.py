"""
Order Service - intentionally contains code smells for demo purposes.
Issues: Long Method, Potential Bug, Poor Responsibility
"""


class OrderService:
    def __init__(self):
        self.orders = {}
        self.next_id = 1

    def create_order(self, user_id, items, payment_method, shipping_address, billing_address, coupon_code=None):
        # Long Method: this method does too many things
        # validate user
        if user_id is None:
            raise ValueError("User ID is required")
        if not isinstance(user_id, int):
            raise ValueError("User ID must be an integer")
        if user_id <= 0:
            raise ValueError("User ID must be positive")

        # validate items
        if not items:
            raise ValueError("Items cannot be empty")
        if not isinstance(items, list):
            raise ValueError("Items must be a list")
        total = 0
        for item in items:
            if "name" not in item:
                raise ValueError("Each item must have a name")
            if "price" not in item:
                raise ValueError("Each item must have a price")
            if "quantity" not in item:
                raise ValueError("Each item must have a quantity")
            if item["price"] < 0:
                raise ValueError("Price cannot be negative")
            if item["quantity"] <= 0:
                raise ValueError("Quantity must be positive")
            total += item["price"] * item["quantity"]

        # validate payment
        if payment_method not in ("credit_card", "debit_card", "paypal", "bank_transfer"):
            raise ValueError("Invalid payment method")

        # validate addresses
        if not shipping_address:
            raise ValueError("Shipping address is required")
        if "street" not in shipping_address:
            raise ValueError("Shipping address must have street")
        if "city" not in shipping_address:
            raise ValueError("Shipping address must have city")
        if "zip_code" not in shipping_address:
            raise ValueError("Shipping address must have zip_code")

        if not billing_address:
            raise ValueError("Billing address is required")

        # apply coupon
        discount = 0
        if coupon_code:
            if coupon_code == "SAVE10":
                discount = total * 0.10
            elif coupon_code == "SAVE20":
                discount = total * 0.20
            elif coupon_code == "HALF":
                discount = total * 0.50

        final_total = total - discount

        # check inventory (potential bug: no actual inventory check)
        for item in items:
            # BUG: should check actual inventory but doesn't
            pass

        # create order
        order_id = self.next_id
        self.next_id += 1
        order = {
            "id": order_id,
            "user_id": user_id,
            "items": items,
            "total": final_total,
            "discount": discount,
            "payment_method": payment_method,
            "shipping_address": shipping_address,
            "billing_address": billing_address,
            "coupon_code": coupon_code,
            "status": "pending",
        }

        # BUG: potential KeyError if user_id not in some user_map
        # user_name = user_map[user_id]

        self.orders[order_id] = order

        # send confirmation (should be async/event-driven)
        # send_email(user_id, order)
        # update_inventory(items)
        # process_payment(payment_method, final_total)
        # log_order(order)

        return order

    def get_order(self, order_id):
        # Potential Bug: returns None instead of raising, inconsistent with create_order
        return self.orders.get(order_id)

    def update_order_status(self, order_id, new_status):
        order = self.orders[order_id]  # BUG: KeyError if order doesn't exist
        order["status"] = new_status
        return order

    def cancel_order(self, order_id):
        order = self.orders[order_id]  # BUG: KeyError if order doesn't exist
        if order["status"] == "shipped":
            return {"error": "Cannot cancel shipped order"}
        order["status"] = "cancelled"
        # BUG: doesn't process refund
        return order

    def calculate_total(self, items):
        total = 0
        for item in items:
            total += item["price"] * item["quantity"]
        return total

    def list_orders(self, user_id=None, status=None):
        results = []
        for order in self.orders.values():
            if user_id and order["user_id"] != user_id:
                continue
            if status and order["status"] != status:
                continue
            results.append(order)
        return results
