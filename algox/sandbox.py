from typing import List
from algosdk.kmd import KMDClient

from algox.account import Account

KMD_ADDRESS = "http://localhost:4002"
KMD_TOKEN = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

KMD_WALLET_NAME = "unencrypted-default-wallet"
KMD_WALLET_PASSWORD = ""


def get_genesis_accounts() -> List[Account]:
    kmd = KMDClient(KMD_TOKEN, KMD_ADDRESS)

    wallets = kmd.list_wallets()
    walletID = None
    for wallet in wallets:
        if wallet["name"] == "unencrypted-default-wallet":
            walletID = wallet["id"]
            break

    if walletID is None:
        raise Exception("Wallet not found: {}".format(
            "unencrypted-default-wallet"))

    walletHandle = kmd.init_wallet_handle(walletID, "")

    try:
        addresses = kmd.list_keys(walletHandle)
        privateKeys = [
            kmd.export_key(walletHandle, "", addr)
            for addr in addresses
        ]
        kmdAccounts = [Account(sk) for sk in privateKeys]
    finally:
        kmd.release_wallet_handle(walletHandle)

    return kmdAccounts
