from fastapi import FastAPI, HTTPException
import requests

app = FastAPI()

@app.get("/generate-matrix")
def generate_matrix():
    PYRUS_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6ImF0K2p3dCJ9.eyJuYmYiOjE3NDgxMDc5MjMsImV4cCI6MTc0ODE5NDMyMywiaXNzIjoiaHR0cDovL3B5cnVzLWlkZW50aXR5LXNlcnZlci5weXJ1cy1wcm9kLnN2Yy5jbHVzdGVyLmxvY2FsIiwiYXVkIjoicHVibGljYXBpIiwiY2xpZW50X2lkIjoiMTFGRjI4OTctRDNFMS00QjAwLUJCRjYtNDFCMzhDM0EwMDcyIiwic3ViIjoiMTE0MDQ2NiIsImF1dGhfdGltZSI6MTc0ODEwNzkyMywiaWRwIjoibG9jYWwiLCJzZWNyZXQiOiI5MmY0Yzc5NjQ4MmJkMWRlNjU5ZTNhM2I5NGRlYTliYmM3M2I3ZTljZjg2MGMzZWU4MjUwNjdmMmRiOTI3ZDE1IiwidGltZXN0YW1wIjoiMTc0ODE5NDMyMyIsInNjb3BlIjpbInB1YmxpY2FwaSJdLCJhbXIiOlsicHdkIl19.JdJxy-dhtoY4jZsK49EBQql34Y6mv0CmY8v871O30FOQKT1M7CEPA-FBbRn9adyJzZCrC2xjgJWGhSFyBFIuZJpYxER-nyCzJYwqKdj8AN9PyolIk9y-dG9K-t4fGOovy7wFiwsnDPbkzYEy9ZVb_I-Yz51fzVSS6jHEM_u5hM9lwp9wMJ1feDo62Mn_t-xQK9_c-ww9fCoc8f3MhW99vcrhvYVhsd3mEaIMPklqhZJ2EKDKfkqmKUUoPYgNHXKoW1LW_Uo-0IpLBfHf6W89cvGjbhHtae_QcggNe1dCr-RllmLLoPo4ou_QmYbFCdHRh3O8dNh5cmGagdAv9xfZ5g"
    url = "https://api.pyrus.com/v4/forms/2309262/register"
    headers = {"Authorization": f"Bearer {PYRUS_TOKEN}"}

    resp = requests.get(url, headers=headers)

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Ошибка от Pyrus API")

    try:
        data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Невалидный JSON от Pyrus: {str(e)}")

    return {
        "status": "ok",
        "tasks_count": len(data.get("tasks", [])),
        "example": data.get("tasks", [])[0] if data.get("tasks") else {}
    }
