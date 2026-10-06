"""
Order Controller - HTTP layer.
Issues: Poor Responsibility (mixes validation, business logic, and response formatting)
"""


class OrderController:
    def __init__(self, order_service):
        self.service = order_service

    def handle_create(self, request_data):
        # Duplicate validation that should be in service layer
        if "user_id" not in request_data:
            return {"status": 400, "body": {"error": "user_id is required"}}
        if "items" not in request_data:
            return {"status": 400, "body": {"error": "items is required"}}
        if "payment_method" not in request_data:
            return {"status": 400, "body": {"error": "payment_method is required"}}

        user_id = request_data["user_id"]
        items = request_data["items"]
        payment_method = request_data["payment_method"]
        shipping_address = request_data.get("shipping_address", {})
        billing_address = request_data.get("billing_address", {})
        coupon_code = request_data.get("coupon_code")

        try:
            order = self.service.create_order(
                user_id=user_id,
                items=items,
                payment_method=payment_method,
                shipping_address=shipping_address,
                billing_address=billing_address,
                coupon_code=coupon_code,
            )
            return {"status": 201, "body": {"order": order, "message": "Order created successfully"}}
        except ValueError as e:
            return {"status": 400, "body": {"error": str(e)}}
        except Exception as e:
            return {"status": 500, "body": {"error": "Internal server error"}}

    def handle_get(self, order_id):
        order = self.service.get_order(order_id)
        if not order:
            return {"status": 404, "body": {"error": "Order not found"}}
        return {"status": 200, "body": {"order": order}}

    def handle_cancel(self, order_id):
        try:
            result = self.service.cancel_order(order_id)
            if "error" in result:
                return {"status": 400, "body": result}
            return {"status": 200, "body": {"order": result, "message": "Order cancelled"}}
        except KeyError:
            return {"status": 404, "body": {"error": "Order not found"}}

    def handle_list(self, user_id=None, status=None):
        orders = self.service.list_orders(user_id=user_id, status=status)
        return {"status": 200, "body": {"orders": orders, "count": len(orders)}}
