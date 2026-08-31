package demo.infra

import demo.Order
import demo.OrderRepository

// --- POSITIVE: spring endpoints (explicit mapping annotations) ---

@RestController
class PaymentController(private val paymentRepository: PaymentRepository) {

    @GetMapping("/payments/{id}")
    fun getPayment(@PathVariable id: String): Payment? = null

    @PostMapping("/payments")
    fun createPayment(@RequestBody payment: Payment): Payment = payment

    @DeleteMapping("/payments/{id}")
    fun cancelPayment(id: String) {
    }
}

// --- POSITIVE: messaging (explicit Kafka listener annotation) ---

class PaymentEvents {
    @KafkaListener(topics = ["payments"])
    fun onPayment(event: PaymentEvent) {
    }
}

// --- POSITIVE: persistence (explicit repository annotation) ---

@Repository
interface PaymentRepository : JpaRepository<Payment, String>
