package demo

// Fixture: Spring-ish Kotlin sources with known outline symbols.

data class Order(val id: String, val total: Int)

interface OrderRepository {
    fun findById(id: String): Order?
}

class OrdersController(private val repository: OrderRepository)

class OrderService(private val repository: OrderRepository)

fun bootstrap(): OrdersController = OrdersController(OrderService(object : OrderRepository {
    override fun findById(id: String): Order? = null
}))
