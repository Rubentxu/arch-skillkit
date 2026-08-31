// --- POSITIVE: actix endpoints (explicit attribute macros) ---
use actix_web::{get, post, web, HttpResponse};

#[get("/orders/{id}")]
async fn get_order(path: web::Path<u64>) -> HttpResponse {
    HttpResponse::Ok().finish()
}

#[post("/orders")]
async fn create_order(item: web::Json<Order>) -> HttpResponse {
    HttpResponse::Created().finish()
}

// --- POSITIVE: outgoing HTTP client (explicit reqwest markers) ---

pub fn build_http_client() -> reqwest::Client {
    reqwest::Client::new()
}
