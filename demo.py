import os
import dotenv

from algosdk import *
from algosdk.future.transaction import *

from algox.account import Account
from algox.operations import *
from algox.sandbox import get_genesis_accounts
from algox.utils import get_algod_client, get_app_global_state


def demo(asset_a=None, asset_b=None):
    #Load environment variables
    dotenv.load_dotenv('.env')
    
    algod_url = os.environ.get("ALGOD_URL")
    algod_api_key = os.environ.get("ALGOD_API_KEY")
    
    client = get_algod_client(algod_url, algod_api_key)
    
    #Generates the creator address
    sender = Account.from_mnemonic(os.environ.get("CREATOR_MN"))
        
    #Create pool template
    template_pool_app_id = create_pool_app(client, sender)
    print(f"template pool id: {template_pool_app_id}")
    #Create master App
    master_app_id = create_master_app(client, sender, template_pool_app_id)
    print(f"master app id: {master_app_id}")
    
    asset_a = create_asset(client, sender, "A")
    print("Created asset a with id: {}".format(asset_a))

    asset_b = create_asset(client, sender, "B")
    print("Created asset b with id: {}".format(asset_b))

    #Get master app id
    app_addr = logic.get_application_address(master_app_id)
    print("Application Address: {}".format(app_addr))
    
    assert asset_a < asset_b
    #Create pool for asset A and asset B in master app
    create_pool(client, sender, master_app_id, template_pool_app_id, asset_a, asset_b)

    #Generates the pool name and get the pool id
    master_app_state = get_app_global_state(client, master_app_id)
    pool_name = asset_a.to_bytes(8, 'big') + b"_" + asset_b.to_bytes(8, 'big')
    new_pool_id = master_app_state.get(pool_name)
    print(f"pool app id for asset {asset_a} and asset {asset_b}: {new_pool_id}")
    
    #Get pool app address
    pool_app_addr = logic.get_application_address(new_pool_id)
    print("Pool App Address: {}".format(pool_app_addr))
    
    #Show pool state
    new_pool_state = get_app_global_state(client, master_app_id)
    print(f"State of pool for asset {asset_a} and asset {asset_b}")
    print(new_pool_state)

    # Get sender address
    sender_addr = sender.get_address()
    sender_pk = sender.get_private_key()
    print("Sender address: {}".format(sender_addr))
    
    #Set govener
    sp = client.suggested_params()
    txn_group = assign_group_id(
        [
            get_app_call(
                sender_addr, sp, master_app_id, app_args=["set_govener"], assets=[asset_a, asset_b], accounts=[sender_addr], apps=[new_pool_id]
            ),
        ]
    )
    send(client, "set_govener", [txn.sign(sender_pk) for txn in txn_group])
    
    # If this is a new contract, we should fund it with algos
    fund_if_needed(client, sender_addr, sender_pk, pool_app_addr)
    
    # Bootstrap Pool
    sp = client.suggested_params()
    txn_group = assign_group_id(
        [
            get_app_call(
                sender_addr, sp, new_pool_id, app_args=["boot"], assets=[asset_a, asset_b]
            ),
        ]
    )
    result = send(client, "boot", [txn.sign(sender_pk) for txn in txn_group])
    pool_token = result["inner-txns"][0]["asset-index"]

    print("Created Pool Token: {}".format(pool_token))
    # Opt addr into newly created Pool Token
    sp = client.suggested_params()
    txn_group = assign_group_id(
       [
           get_asset_xfer(sender_addr, sp, pool_token, pool_app_addr, 0),
       ]
    )
    send(client, "optin", [txn.sign(sender_pk) for txn in txn_group])
    print_balances(client, pool_app_addr, pool_app_addr, pool_token, asset_a, asset_b)

    # Optin pool token to sender
    sp = client.suggested_params()
    txn_group = assign_group_id(
       [
           get_asset_xfer(sender_addr, sp, pool_token, sender_addr, 0),
       ]
    )
    send(client, "optin", [txn.sign(sender_pk) for txn in txn_group])
    
    # Fund Pool with initial liquidity
    sp = client.suggested_params()
    txn_group = assign_group_id(
        [
            get_app_call(
                sender_addr,
                sp,
                new_pool_id,
                app_args=["fund"],
                assets=[asset_a, asset_b, pool_token],
            ),
            AssetTransferTxn(sender_addr, sp, pool_app_addr, 1000, asset_a),
            AssetTransferTxn(sender_addr, sp, pool_app_addr, 3000, asset_b),
        ]
    )
    send(client, "fund", [txn.sign(sender_pk) for txn in txn_group])
    print_balances(client, pool_app_addr, sender_addr, pool_token, asset_a, asset_b)

    # Mint liquidity tokens
    sp = client.suggested_params()
    txn_group = assign_group_id(
        [
            get_app_call(
                sender_addr,
                sp,
                new_pool_id,
                app_args=["mint"],
                assets=[asset_a, asset_b, pool_token],
            ),
            get_asset_xfer(sender_addr, sp, asset_a, pool_app_addr, 100000),
            get_asset_xfer(sender_addr, sp, asset_b, pool_app_addr, 10000),
        ]
    )

    send(client, "mint", [txn.sign(sender_pk) for txn in txn_group])
    print_balances(client, pool_app_addr, sender_addr, pool_token, asset_a, asset_b)

    # Get Account from sandbox for Swap
    account = get_genesis_accounts()[0]
    addr = account.get_address()
    sk = account.get_private_key()
    
    print("Using {}".format(addr))
    
    # Swap A for B by user
    sp = client.suggested_params()
    txn_group = assign_group_id(
        [
            get_app_call(addr, sp, new_pool_id, ["swap"], [asset_a, asset_b]),
            get_asset_xfer(addr, sp, asset_a, pool_app_addr, 5),
        ]
    )
    send(client, "swap_a_b", [txn.sign(sk) for txn in txn_group])
    print_balances(client, pool_app_addr, addr, pool_token, asset_a, asset_b)

    # Swap B for A by user
    sp = client.suggested_params()
    txn_group = assign_group_id(
        [
            get_app_call(addr, sp, new_pool_id, ["swap"], [asset_a, asset_b]),
            get_asset_xfer(addr, sp, asset_b, pool_app_addr, 5),
        ]
    )
    send(client, "swap_b_a", [txn.sign(sk) for txn in txn_group])
    print_balances(client, pool_app_addr, addr, pool_token, asset_a, asset_b)

    # Burn liq tokens
    sp = client.suggested_params()
    txn_group = assign_group_id(
        [
            get_app_call(sender_addr, sp, new_pool_id, ["burn"], [asset_a, asset_b, pool_token]),
            get_asset_xfer(sender_addr, sp, pool_token, pool_app_addr, 1000),
        ]
    )
    send(client, "burn", [txn.sign(sender_pk) for txn in txn_group])
    print_balances(client, pool_app_addr, sender_addr, pool_token, asset_a, asset_b)


if __name__ == "__main__":
    demo()
