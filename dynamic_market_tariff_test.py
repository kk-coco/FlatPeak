import os
import requests
from datetime import datetime, timedelta
import base64


def get_bearer_token(account_id, api_key):
    """Step 1: Authenticate and obtain bearer token."""
    url = "https://api.flatpeak.com/login"
    username = "your_flatpeak_account_id"
    password = "your_flatpeak_api_key"
    # Combine username and password and Base64 encode them
    auth_value = f"{account_id}:{api_key}"
    encoded_auth_value = base64.b64encode(auth_value.encode('utf-8')).decode('utf-8')
    headers = {
        "Authorization": f"Basic {encoded_auth_value}"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()['bearer_token']


def create_connect_token(bearer_token):
    """Step 2: Create a connect token using the bearer token."""
    url = "https://api.flatpeak.com/connect/tariff/token"
    headers = {"Authorization": f"Bearer {bearer_token}",
               "Content-Type": "application/json"}
    params = {"callback_uri": "https://webhook.site/4623e56fc5c1",
              "connect_web_uri": "http://localhost:7070"
              }
    response = requests.post(url, headers=headers, json=params)
    response.raise_for_status()
    return response.json()['connect_token']


def simulate_connect_session(connect_token):
    """Step 3: Simulate the Connect session to create a location."""
    url = "https://connect.flatpeak.com"
    headers = {"Content-Type": "application/json"}
    data = {
        "connect_token": connect_token,
        "route": "session_restore"
    }

    while True:
        response = requests.post(url, headers=headers, json=data)
        # response.raise_for_status()
        print("request data", data)
        response_json = response.json()
        print('response_json',response_json)
        current_route = response_json.get("route")

        if current_route == "session_restore":
            break  # Session completed

        data = {
            "connect_token": connect_token,
            "route": current_route
        }

        if current_route == "postal_address_capture":
            data["data"] = {"postal_address": {
                "address_line1": "1-3",
                "address_line2": "Strand",
                "city": "London",
                "state": "Greater London",
                "post_code": "WC2N 5EH",
                "country_code": "GB"
            }
        }
        elif current_route == "provider_select":
            providers = response_json.get("data", {}).get("providers", [])
            ecotricity = next(p for p in providers if p["display_name"] == "Ecotricity")
            data["data"] = {"provider":{"id": ecotricity["id"]}}
        elif current_route == "tariff_structure_select":
            # tariffs = response_json.get("data", {}).get("options", [])
            # dynamic_tariff = next(t for t in tariffs)
            data["data"] = {"options": ["MARKET"]}
        elif current_route == "market_surcharge_capture":
            data["region"] = response_json["data"]["currency_code"]
            data["data"] = {"surcharge": {
                "fixed": 0.345,
                "percentage": 18.50
            }}
        elif current_route == "tariff_name_capture":
            data["data"] = {"tariff": {"name": "Super Cheap Energy 2008"}}
        elif current_route == "contract_term_capture":
            expiry_date = (datetime.utcnow() + timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
            data["data"] = {"contract_end_date": expiry_date}
        elif current_route == "summary_tou_confirm":
            data["action"] = "SAVE"
        elif current_route == "session_complete":
            return response_json
        else:
            raise ValueError(f"Unhandled route: {current_route}")




def exchange_connect_token(connect_token,bearer_token):
    """Step 4: Exchange connect token for location ID."""
    url = "https://api.flatpeak.com/connect/tariff/token"
    headers = {"Authorization": f"Bearer {bearer_token}",
               "Content-Type": "application/json"}
    params = {"connect_token": connect_token}
    response = requests.get(url, headers=headers,params=params)
    # response.raise_for_status()
    print(response.text)
    return response.json()['location_id']


def get_tariff_rates(location_id, bearer_token):
    """Step 5: Fetch tariff rates for the location."""
    url = "https://api.flatpeak.com/costs/instant"
    headers = {"Authorization": f"Bearer {bearer_token}",
               "Content-Type": "application/json"}
    start_time = (datetime.utcnow()).replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
    end_time = (datetime.utcnow() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
    params = {
        "location_id": location_id,
        "start_time": start_time,
        "end_time": end_time,
        "units": "W",
        "value": 20566,
        "resolution": "hourly",
        "session_reference_id": "SESSION1234567890",
        "record_reference_id": "MET1234567890",
        "direction": "IMPORT",
        "tariff_rate": "IMPORT",
        "measurand": "TRANSFERRED",
        "confidence": 1
    }
    response = requests.post(url, headers=headers, json=params)
    print(response.text)
    response.raise_for_status()
    return response.json()


def main():
    # Retrieve credentials from environment variables
    account_id = "acc_672a0c0c9986827a8308670b"#os.environ.get("FLATPEAK_ACCOUNT_ID")
    api_key = "sk_live_c83e648de7733aae9ee4c636f5064514"#os.environ.get("FLATPEAK_API_KEY")

    # Step 1: Get bearer token
    bearer_token = get_bearer_token(account_id, api_key)
    # Step 2: Create connect token
    connect_token = create_connect_token(bearer_token)
    #
    # # Step 3: Simulate Connect session
    simulate_connect_session(connect_token)

    # Step 4: Exchange for location ID
    location_id = exchange_connect_token(connect_token,bearer_token)
    # Step 5: Get tariff rates
    rates = get_tariff_rates(location_id, bearer_token)

    # Assertions
    now = datetime.utcnow()
    # expected_end_time = (now + timedelta(days=1)).replace(
    #     hour=0, minute=0, second=0, microsecond=0
    # ).isoformat() + "Z"
    request_end_time = rates['request']['end_time']
    expected_end_time = rates['data']['end_time']
    # assert rates['data']['end_time'] == expected_end_time
    assert request_end_time == expected_end_time,  "request end time should be equal to response end time"

    current_time = (datetime.utcnow()).replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
    assert current_time == rates['data']['start_time'], "Start time should be current time"
    #
    assert rates['currency_code'] == 'GBP', "Currency must be GBP"

    start = datetime.fromisoformat(rates['data']['start_time'].replace('Z', ''))
    end = datetime.fromisoformat(rates['data']['end_time'].replace('Z', ''))
    expected_hours = int((end - start).total_seconds() // 3600)
    assert len(rates['data']) == expected_hours, "Incorrect number of hourly rates"

    for entry in rates['request']:
        print(entry['confidence'])
        assert entry['confidence'] == 1, "All rates must have confidence 1"

if __name__ == "__main__":
    main()