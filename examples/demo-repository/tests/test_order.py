"""
Tests for Order Service.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from order.service import OrderService


def test_create_order_success():
    service = OrderService()
    order = service.create_order(
        user_id=1,
        items=[{"name": "Widget", "price": 10.0, "quantity": 2}],
        payment_method="credit_card",
        shipping_address={"street": "123 Main St", "city": "Springfield", "zip_code": "62701"},
        billing_address={"street": "123 Main St", "city": "Springfield", "zip_code": "62701"},
    )
    assert order["id"] == 1
    assert order["total"] == 20.0
    assert order["status"] == "pending"


def test_create_order_with_coupon():
    service = OrderService()
    order = service.create_order(
        user_id=1,
        items=[{"name": "Widget", "price": 100.0, "quantity": 1}],
        payment_method="paypal",
        shipping_address={"street": "123 Main St", "city": "Springfield", "zip_code": "62701"},
        billing_address={"street": "123 Main St", "city": "Springfield", "zip_code": "62701"},
        coupon_code="SAVE10",
    )
    assert order["total"] == 90.0
    assert order["discount"] == 10.0


def test_get_order():
    service = OrderService()
    service.create_order(
        user_id=1,
        items=[{"name": "Widget", "price": 10.0, "quantity": 1}],
        payment_method="credit_card",
        shipping_address={"street": "123 Main St", "city": "Springfield", "zip_code": "62701"},
        billing_address={"street": "123 Main St", "city": "Springfield", "zip_code": "62701"},
    )
    order = service.get_order(1)
    assert order is not None
    assert order["id"] == 1


def test_cancel_order():
    service = OrderService()
    service.create_order(
        user_id=1,
        items=[{"name": "Widget", "price": 10.0, "quantity": 1}],
        payment_method="credit_card",
        shipping_address={"street": "123 Main St", "city": "Springfield", "zip_code": "62701"},
        billing_address={"street": "123 Main St", "city": "Springfield", "zip_code": "62701"},
    )
    result = service.cancel_order(1)
    assert result["status"] == "cancelled"


def test_calculate_total():
    service = OrderService()
    items = [
        {"name": "A", "price": 10.0, "quantity": 2},
        {"name": "B", "price": 5.0, "quantity": 3},
    ]
    assert service.calculate_total(items) == 35.0


if __name__ == "__main__":
    test_create_order_success()
    test_create_order_with_coupon()
    test_get_order()
    test_cancel_order()
    test_calculate_total()
    print("All tests passed!")
