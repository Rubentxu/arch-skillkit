"""Fixture: requests.get WITH timeout — SHOULD NOT MATCH (negative fixture)."""
import requests


def fetch_user_safe(user_id: int) -> dict:
    response = requests.get(
        f"https://api.example.com/users/{user_id}",
        timeout=5,
    )
    return response.json()
