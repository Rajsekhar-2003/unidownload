import requests
import time

def test_health():
    response = requests.get("http://localhost:8000/health")
    print(f"Health check: {response.json()}")

def test_video_info():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    response = requests.get(f"http://localhost:8000/api/info?url={url}")
    print(f"Video info: {response.json()}")

if __name__ == "__main__":
    time.sleep(2)  # Wait for server to start
    test_health()
    test_video_info()