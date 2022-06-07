import os
import dotenv
from algox.account import Account
from algox.operations import create_asset, create_master_app, create_pool, create_pool_app

from algox.utils import get_algod_client, get_app_global_state


if __name__ == '__main__':
    dotenv.load_dotenv('.env')
    
    algod_url = os.environ.get("ALGOD_URL")
    algod_api_key = os.environ.get("ALGOD_API_KEY")
    
    client = get_algod_client(algod_url, algod_api_key)
    
    sender = Account.from_mnemonic(os.environ.get("CREATOR_MN"))
    
    template_pool_app_id = create_pool_app(client, sender)
    print(f"template pool id: {template_pool_app_id}")
    
    master_app_id = create_master_app(client, sender, template_pool_app_id)
    print(f"master app id: {master_app_id}")
    
    asset_a = create_asset(client, sender, "A")
    print("Created asset a with id: {}".format(asset_a))

    asset_b = create_asset(client, sender, "B")
    print("Created asset b with id: {}".format(asset_b))
    
    create_pool(client, sender, master_app_id, template_pool_app_id, asset_a, asset_b)
    
    master_app_state = get_app_global_state(client, master_app_id)
    pool_name = asset_a.to_bytes(8, 'big') + b"_" + asset_b.to_bytes(8, 'big')
    new_pool_id = master_app_state.get(pool_name)
    print(f"pool app id for asset {asset_a} and asset {asset_b}: {new_pool_id}")
    
    new_pool_state = get_app_global_state(client, new_pool_id)
    print(f"State of pool for asset {asset_a} and asset {asset_b}")
    print(new_pool_state)
