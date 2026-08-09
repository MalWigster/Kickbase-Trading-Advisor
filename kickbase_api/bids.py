import requests

from kickbase_api.config import BASE_URL


def place_bid(token, league_id, player_id, amount):
    """Submit a bid for a player in the specified league.

    """

    url = f"{BASE_URL}/leagues/{league_id}/market/{player_id}/offers"
    payload = {
        "price": amount,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()
