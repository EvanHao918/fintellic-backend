import requests
import json

# 基础URL
base_url = "http://localhost:8000/api/v1"

# 登录信息
login_data = {
    "username": "test2@fintellic.com",
    "password": "Test123456"
}

# 登录获取token
print("Logging in...")
login_response = requests.post(
    f"{base_url}/auth/login",
    data=login_data
)

if login_response.status_code == 200:
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Login successful!\n")
    
    # 测试8-K filing
    print("Testing 8-K Filing (ID: 6)")
    response = requests.get(f"{base_url}/filings/6", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(f"Filing Type: {data.get('type')}")
        print(f"Item Type: {data.get('item_type')}")
        print(f"Event Timeline: {data.get('event_timeline')}")
        print(f"Items: {data.get('items')}")
        print(f"Fiscal Year: {data.get('fiscal_year')}")
        print(f"Fiscal Quarter: {data.get('fiscal_quarter')}")
        print(f"Period End Date: {data.get('period_end_date')}")
        
        # 打印所有字段以查看
        print("\nAll fields:")
        for key, value in data.items():
            if value is not None:
                print(f"  {key}: {value}")
    else:
        print(f"Error: {response.status_code} - {response.text}")
    
    print("\n" + "="*50 + "\n")
    
    # 测试10-Q filing
    print("Testing 10-Q Filing (ID: 25)")
    response = requests.get(f"{base_url}/filings/25", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(f"Filing Type: {data.get('type')}")
        print(f"Expectations Comparison: {data.get('expectations_comparison')}")
        print(f"Cost Structure: {data.get('cost_structure')}")
        print(f"Guidance Update: {data.get('guidance_update')}")
        print(f"Fiscal Year: {data.get('fiscal_year')}")
        print(f"Fiscal Quarter: {data.get('fiscal_quarter')}")
        
        # 打印所有字段以查看
        print("\nAll fields:")
        for key, value in data.items():
            if value is not None:
                print(f"  {key}: {value}")
    else:
        print(f"Error: {response.status_code} - {response.text}")
else:
    print(f"Login failed: {login_response.status_code} - {login_response.text}")