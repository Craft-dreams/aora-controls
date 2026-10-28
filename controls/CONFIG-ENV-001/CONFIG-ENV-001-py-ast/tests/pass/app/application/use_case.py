from app.domain.service import PaymentService


class CheckoutUseCase:
    def __init__(self, payment_service: PaymentService):
        self.payment_service = payment_service
