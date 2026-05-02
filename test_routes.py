import requests

# List of URLs to test
urls = [
    "http://127.0.0.1:5000/",
    "http://127.0.0.1:5000/login",
    "http://127.0.0.1:5000/register",
    "http://127.0.0.1:5000/dashboard",
    "http://127.0.0.1:5000/admin",
    "http://127.0.0.1:5000/track",
    "http://127.0.0.1:5000/schedule",
    "http://127.0.0.1:5000/my-packages"
]

# Check each URL
for url in urls:
    response = requests.get(url)
    if response.status_code == 200:
        print(f"✔️ {url} is working!")
    else:
        print(f"❌ {url} failed with status code {response.status_code}")