// Fixture: hexagonal-ish Rust module with known outline symbols.
// Used as ground truth by tests/workspace… tests/scan.bats.

pub struct Order {
    pub id: u64,
    pub status: OrderStatus,
}

pub enum OrderStatus {
    Pending,
    Shipped,
}

pub trait OrderRepository {
    fn find(&self, id: u64) -> Option<Order>;
    fn save(&mut self, order: Order);
}

pub struct SqliteOrderRepository {
    connection: String,
}

impl OrderRepository for SqliteOrderRepository {
    fn find(&self, id: u64) -> Option<Order> {
        None
    }

    fn save(&mut self, order: Order) {}
}

pub fn open_repository(path: &str) -> SqliteOrderRepository {
    SqliteOrderRepository {
        connection: path.to_string(),
    }
}
