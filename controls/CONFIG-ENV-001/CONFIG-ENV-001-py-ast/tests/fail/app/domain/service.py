import os


class PaymentService:
    def __init__(self) -> None:
        self.endpoint = os.getenv("PAYMENT_GATEWAY_URL")
