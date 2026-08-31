package demo.infra

import demo.Order

// --- NEGATIVE: these must NOT match architecture rules ---
// (service/component/plain markers are not endpoints, listeners or stores)

@Service
class PaymentService(private val paymentRepository: PaymentRepository)

@Component
class PaymentMapper

class PaymentValidator {
    fun validate(payment: Order): Boolean = true
}
