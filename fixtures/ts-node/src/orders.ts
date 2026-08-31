// Fixture: modular Node/TS sources with known outline symbols.

export interface OrderRepository {
  findById(id: string): Promise<Order | null>;
}

export interface Order {
  id: string;
  total: number;
}

export class OrdersController {
  constructor(private readonly repository: OrderRepository) {}
}

export class OrderService {
  constructor(private readonly repository: OrderRepository) {}
}

export function createApp(): OrdersController {
  return new OrdersController(new OrderService(null));
}
