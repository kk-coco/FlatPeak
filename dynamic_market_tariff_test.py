from time import sleep
import requests
from datetime import datetime, timedelta
import base64


def get_bearer_token(account_id, api_key):
    """Step 1: Authenticate and obtain bearer token."""
    url = "https://api.flatpeak.com/login"
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
        # print("request data", data)
        response_json = response.json()
        # print('response_json',response_json)
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
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    print(response.text)
    return response.json()['location_id']


def get_tariff_rates(location_id, bearer_token):
    """Step 5: Fetch tariff rates for the location."""
    url = f"https://api.flatpeak.com/tariffs/rates/{location_id}"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    start_time = (datetime.utcnow()).isoformat() + "Z"
    end_time = (datetime.utcnow() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
    params = {
        "start_time": start_time,
        "end_time": end_time,
        "include_tariff": True,
        "include_carbon": False,
        "direction": "IMPORT"
    }
    response = requests.get(url, headers=headers, params=params)
    print(response.text)
    response.raise_for_status()
    return response.json()


def main():
    # Retrieve credentials from environment variables
    account_id = "acc_672a0c0c9986827a8308670b"#os.environ.get("FLATPEAK_ACCOUNT_ID")
    api_key = "sk_live_c83e648de7733aae9ee4c636f5064514"#os.environ.get("FLATPEAK_API_KEY")

    # Step 1: Get bearer token
    print('------------start get_bearer_token------------')
    bearer_token = get_bearer_token(account_id, api_key)
    # Step 2: Create connect token
    print('------------start create_connect_token------------')
    connect_token = create_connect_token(bearer_token)
    #
    # # Step 3: Simulate Connect session
    print('------------start simulate_connect_session------------')
    simulate_connect_session(connect_token)

    # Step 4: Exchange for location ID
    print('------------start exchange_connect_token------------')
    location_id = exchange_connect_token(connect_token,bearer_token)
    # Step 5: Get tariff rates
    print('------------start waiting 30s tariff process------------')
    sleep(30)
    print('------------start get_tariff_rates------------')
    rates = get_tariff_rates(location_id, bearer_token)
    # Assertions
    request_end_time = rates['request']['end_time']
    expected_end_time = rates['data'][-1]['valid_to']
    # 1. assert End time matches request
    assert request_end_time == expected_end_time,  f"End time mismatch. Expected {expected_end_time}, Got {request_end_time}"
    # 2. assert Start time is the current time
    current_time = (datetime.utcnow()).replace(microsecond=0).isoformat() + "Z"
    assert current_time == rates['request']['start_time'], f"Start time not equal to current time, Expected ~{current_time}, Got {rates['request']['start_time']}"
    # 3. assert currency_code
    assert rates['currency_code'] == 'GBP', f"wrong currency code. Expected GBP, Got {rates['currency_code']}"
    #  Hourly rates validation
    if len(rates['data']) <= 0:
        return "Data array is empty."
    for entry in rates['data']:
        valid_from = datetime.fromisoformat(entry["valid_from"].replace("Z", "+00:00"))
        valid_to = datetime.fromisoformat(entry["valid_to"].replace("Z", "+00:00"))
        confidence = entry["tariff"]["confidence"]
        # 4. check hourly rate
        assert (valid_to.hour == (valid_from + timedelta(hours=1)).hour) or (valid_to.hour == 0), f"Hourly rate validation failed: valid_to ({valid_to}) should be later than valid_from ({valid_from})."
        # 5. check confidence is 1
        assert confidence == 1, f"Confidence check failed: Expected 1, but got {confidence}."
    print("End time matches request,Start time is the current time,Currency code is GBP,Data array has valid hourly rates and confidence is 1.")
if __name__ == "__main__":
    main()