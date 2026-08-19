from typing import Any

from httpx import AsyncClient, HTTPError


async def do_request(
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
    base_url: str = "https://testnet.toncenter.com/api/v2/",
) -> dict[str, Any]:
    async with AsyncClient(timeout=timeout) as client:
        try:
            response = await client.request(
                method,
                base_url + url,
                json=body,
                params=params,
            )
            response.raise_for_status()
            return response.json()

        except HTTPError:
            print(f"HTTP error occurred while making request to {url}.")
            raise

        except Exception as e:
            print(f"Error occurred while making request: {e}")
            raise
