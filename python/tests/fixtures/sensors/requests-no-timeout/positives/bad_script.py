"""Fixture: requests.get without timeout — SHOULD MATCH (positive fixture)."""
import requests

url = "https://httpbin.org/get"
result = requests.get(url)
print(result.text)
