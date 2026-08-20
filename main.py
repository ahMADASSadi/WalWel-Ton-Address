import asyncio
import base64
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from tonsdk.contract.wallet import Wallets, WalletVersionEnum
from tonsdk.crypto import mnemonic_new

from _requests import do_request

V4R2_WALLET_ID = 0x29A9A317


class TonTestnetWallet:
    def __init__(
        self,
        mnemonic: list[str] | str | None = None,
    ):
        if mnemonic is None:
            self.mnemonic = mnemonic_new()
            self.mnemonic_str = " ".join(self.mnemonic)
        else:
            self.mnemonic = mnemonic if isinstance(mnemonic, list) else mnemonic.split()
            self.mnemonic_str = " ".join(self.mnemonic)

        (
            self.mnemonic,
            self.public_key,
            self.private_key,
            self.wallet,
        ) = Wallets.from_mnemonics(
            self.mnemonic,
            WalletVersionEnum.v4r2,
            0,
        )

        self.address = self.wallet.address.to_string(
            is_user_friendly=True,
            is_url_safe=True,
            is_bounceable=False,
            is_test_only=True,
        )

        self.raw_address = self.wallet.address.to_string(
            is_user_friendly=False,
        )

    async def get_balance(self) -> str:
        data = await do_request(
            "GET",
            "getAddressBalance",
            {
                "address": self.address,
            },
        )

        balance_nano = int(data["result"])

        return f"{balance_nano / 1_000_000_000:.9f} TON"

    async def get_tsx(self, limit: int = 10) -> list[Any]:
        data = await do_request(
            "GET",
            "getTransactions",
            {
                "address": self.address,
                "limit": limit,
            },
        )

        return data["result"]

    async def get_seqno(self) -> int:
        data = await do_request(
            "POST",
            "runGetMethod",
            body={
                "address": self.raw_address,
                "method": "seqno",
                "stack": [],
            },
        )

        result = data["result"]

        # if result["exit_code"] != 0:
        #     raise RuntimeError(
        #         f"seqno getter failed: exit_code={result['exit_code']}"
        #     )

        stack = result["stack"]

        if not stack:
            raise RuntimeError("seqno getter returned an empty stack")

        # [["num", "0x14c97"]]
        value = stack[0][1]

        return int(value, 16)

    async def send_ton(
        self,
        dest_address: str,
        amount_ton: float,
    ) -> str:

        seqno = await self.get_seqno()
        print(f"seqno: {seqno}")

        amount_nano = int(amount_ton * 1_000_000_000)
        transfer = self.wallet.create_transfer_message(
            to_addr=dest_address,
            amount=amount_nano,
            seqno=seqno,
            send_mode=3,
        )

        boc_bytes = transfer["message"].to_boc(False)
        boc_base64 = base64.b64encode(boc_bytes).decode()
        data = await do_request(
            "POST",
            "sendBoc",
            body={
                "boc": boc_base64,
            },
        )

        print("broadcast result:", data)

        message_hash = transfer["message"].hash().hex()

        print("transaction broadcasted!")
        print(f"message hash: {message_hash}")

        return message_hash


def save_wallet_to_file(
    filepath: str,
    wallet: TonTestnetWallet,
):
    directory = os.path.dirname(filepath)

    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(filepath, "w") as file:
        file.write(wallet.mnemonic_str + "\n")
        file.write(wallet.address + "\n")
        file.write(wallet.raw_address + "\n")


def format_transactions(transactions: list[dict[str, Any]]) -> None:
    if not transactions:
        print("No transactions found.")
        return

    print("-" * 10)
    print("transaction history")
    print("-" * 10)

    for index, tx in enumerate(transactions, start=1):
        tx_id = tx.get("transaction_id", {})
        in_msg = tx.get("in_msg") or {}
        out_msgs = tx.get("out_msgs") or []

        account = tx.get("account", "")
        lt = tx_id.get("lt", "N/A")
        tx_hash = tx_id.get("hash", "N/A")

        utime = tx.get("utime")
        if utime:
            timestamp = datetime.fromtimestamp(
                utime,
                tz=UTC,
            ).strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            timestamp = "N/A"

        value_nano = int(in_msg.get("value", 0) or 0)
        value_ton = value_nano / 1_000_000_000

        fee_nano = int(tx.get("fee", 0) or 0)
        fee_ton = fee_nano / 1_000_000_000

        source = in_msg.get("source") or "External"
        destination = in_msg.get("destination") or account

        print(f"\n[{index}] Incoming Transaction")
        print("-" * 10)
        print(f"Time:          {timestamp}")
        print(f"LT:            {lt}")
        print(f"Hash:          {tx_hash}")
        print(f"\nFrom:          {source}")
        print(f"To:            {destination}")
        print(f"\nAmount:        {value_ton:.9f} TON")
        print(f"Fee:           {fee_ton:.9f} TON")

        if out_msgs:
            print(f"\nOutgoing:      {len(out_msgs)} message(s)")

            for msg_index, msg in enumerate(out_msgs, start=1):
                msg_value = int(msg.get("value", 0) or 0)
                msg_ton = msg_value / 1_000_000_000

                print(
                    f"  {msg_index}. "
                    f"{msg.get('source', 'N/A')} → "
                    f"{msg.get('destination', 'N/A')} "
                    f"({msg_ton:.9f} TON)"
                )
        else:
            print("\nOutgoing:      None")

    print("-" * 10)


def load_mnemonic_from_file(filepath: str) -> str:
    with open(filepath, "r") as file:
        return file.readline().strip()


def print_wallet_info(
    name: str,
    wallet: TonTestnetWallet,
):
    print(f"\n{name}")
    print(f"{'_' * 10}")

    print(f"Address:       {wallet.address}")
    print(f"Raw address:   {wallet.raw_address}")
    print("Wallet:        V4R2")
    print(f"Wallet ID:     0x{V4R2_WALLET_ID:08X}")
    print(f"Public key:    {wallet.public_key.hex()}")
    print(f"Private key:   {wallet.private_key.hex()}")
    print(f"{'_' * 10}")


async def main():
    source_file = "wallets/test.txt"
    target_file = "wallets/test1.txt"

    if os.path.exists(source_file):
        print("found existing source wallet. Restoring from file...")

        source_mnemonic = load_mnemonic_from_file(source_file)

        source_wallet = TonTestnetWallet(mnemonic=source_mnemonic)

    else:
        print("generating new source wallet...")

        source_wallet = TonTestnetWallet()

        save_wallet_to_file(
            source_file,
            source_wallet,
        )

        print(f"saved source wallet to {source_file}")

    if os.path.exists(target_file):
        print("found existing target wallet. Restoring from file...")

        target_mnemonic = load_mnemonic_from_file(target_file)

        target_wallet = TonTestnetWallet(mnemonic=target_mnemonic)

    else:
        print("generating new target wallet...")

        target_wallet = TonTestnetWallet()

        save_wallet_to_file(
            target_file,
            target_wallet,
        )

        print(f"saved target wallet to {target_file}")

    print_wallet_info(
        "source",
        source_wallet,
    )

    print_wallet_info(
        "target",
        target_wallet,
    )

    source_balance = await source_wallet.get_balance()

    target_balance = await target_wallet.get_balance()

    print(f"\nsource balance: {source_balance}")

    print(f"target balance: {target_balance}")

    try:
        await asyncio.sleep(1)
        source_transactions = await source_wallet.get_tsx(limit=5)
        await asyncio.sleep(1)
        target_transactions = await target_wallet.get_tsx(limit=5)
        await asyncio.sleep(1)

        print("\nSOURCE TRANSACTIONS:")
        print(format_transactions(source_transactions))

        print("\nTARGET TRANSACTIONS:")
        print(format_transactions(target_transactions))

    except httpx.HTTPError as e:
        print(f"\nfetch failed: {e}")

    # source_balance_val = float(source_balance.split()[0])

    # if source_balance_val > 0.2:
    #     print("\nsource has enough balance.")

    #     print("Sending 0.1 TON to target...")

    #     # Uncomment when ready.

    #     tx_hash = await source_wallet.send_ton(
    #         dest_address=target_wallet.address,
    #         amount_ton=0.1,
    #     )

    #     print(f"TX: {tx_hash}")

    #     print("waiting for transaction to process...")

    #     await asyncio.sleep(5)

    #     final_source_balance = await source_wallet.get_balance()

    #     final_target_balance = await target_wallet.get_balance()

    #     print(f"\nfinal source balance: {final_source_balance}")

    #     print(f"final target balance: {final_target_balance}")

    # else:
    #     print(f"\ninsufficient source balance ({source_balance}).")

    #     print("Fund the wallet using the TON testnet faucet:")

    #     print(source_wallet.address)


if __name__ == "__main__":
    os.makedirs("wallets", exist_ok=True)

    asyncio.run(main())
