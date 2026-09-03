"""Fixture: requests.get without timeout — SHOULD MATCH (positive fixture)."""
import requests


def fetch_user(user_id: int) -> dict:
    response = requests.get(f"https://api.example.com/users/{user_id}")
    return response.json()
