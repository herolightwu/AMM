import base64
from typing import Tuple
from algosdk.future import transaction
from algosdk.v2client.algod import AlgodClient
from algosdk.logic import get_application_address
from pyteal import compileTeal, Mode, Int
from .account import Account
from .contracts.master import MasterContract
from .contracts.pool import PoolContract
from .utils import fully_compile_contract, wait_for_transaction


def fund_if_needed(client: AlgodClient, funder: str, pk: str, app: str):
    fund = False
    try:
        ai = client.account_info(app)
        fund = ai["amount"] < 1e7
    except:
        fund = True

    if fund:
        # Fund App address
        sp = client.suggested_params()
        txn_group = [transaction.PaymentTxn(funder, sp, app, 10000000)]
        return send(client, "seed", [txn.sign(pk) for txn in txn_group])


def write_dryrun(name: str, client: AlgodClient, txns: transaction.List[transaction.SignedTransaction]):
    with open("dryruns/" + name + ".msgp", "wb") as f:
        drr = transaction.create_dryrun(client, txns)
        f.write(base64.b64decode(transaction.encoding.msgpack_encode(drr)))


def print_balances(client:AlgodClient, app: str, addr: str, pool: int, a: int, b: int):
    appbal = client.account_info(app)
    print("App: ")
    for asset in appbal["assets"]:
        if asset["asset-id"] == pool:
            print("\tPool Balance {}".format(asset["amount"]))
        if asset["asset-id"] == a:
            print("\tAssetA Balance {}".format(asset["amount"]))
        if asset["asset-id"] == b:
            print("\tAssetB Balance {}".format(asset["amount"]))

    addrbal = client.account_info(addr)
    print("Participant: ")
    for asset in addrbal["assets"]:
        if asset["asset-id"] == pool:
            print("\tPool Balance {}".format(asset["amount"]))
        if asset["asset-id"] == a:
            print("\tAssetA Balance {}".format(asset["amount"]))
        if asset["asset-id"] == b:
            print("\tAssetB Balance {}".format(asset["amount"]))


def get_asset_xfer(addr, sp, asset_id, app_addr, amt):
    return transaction.AssetTransferTxn(addr, sp, app_addr, amt, asset_id)


def send(client, name, signed_group):
    print("Sending Transaction for {}".format(name))
    # write_dryrun(name, client, signed_group)
    txid = client.send_transactions(signed_group)
    return transaction.wait_for_confirmation(client, txid, 4)


def get_app_call(addr, sp, app_id, app_args=[], assets=[], accounts=[], apps=[]):
    return transaction.ApplicationCallTxn(
        addr,
        sp,
        app_id,
        transaction.OnComplete.NoOpOC,
        app_args=app_args,
        foreign_assets=assets,
        accounts=accounts,
        foreign_apps=apps,
    )
    

def get_master_contracts(client: AlgodClient) -> Tuple[bytes, bytes]:
    contract = MasterContract()
    approval_program = fully_compile_contract(
        client, compileTeal(
            contract.approval_program(),
            mode=Mode.Application,
            version=6
        )
    )
    clear_state_program = fully_compile_contract(
        client, compileTeal(
            contract.clear_program(),
            mode=Mode.Application,
            version=6
        )
    )

    return approval_program, clear_state_program


def get_pool_contracts(client: AlgodClient, asset_a: int, asset_b: int) -> Tuple[bytes, bytes]:
    contract = PoolContract()
    approval_program = fully_compile_contract(
        client,
        compileTeal(
            contract.approval_program(),
            mode=Mode.Application,
            version=6
        )
    )
    clear_state_program = fully_compile_contract(
        client,
        compileTeal(contract.clear_program(), mode=Mode.Application, version=6)
    )

    return approval_program, clear_state_program


def create_master_app(client: AlgodClient, sender: Account, template_pool_id: int) -> int:
    approval_program, clear_program = get_master_contracts(client)

    global_schema = transaction.StateSchema(32, 32)
    local_schema = transaction.StateSchema(0, 0)

    txn = transaction.ApplicationCreateTxn(
        sender=sender.get_address(),
        sp=client.suggested_params(),
        on_complete=transaction.OnComplete.NoOpOC,
        approval_program=approval_program,
        clear_program=clear_program,
        global_schema=global_schema,
        local_schema=local_schema,
        foreign_apps=[template_pool_id]
    )
    signed_txn = txn.sign(sender.get_private_key())
    tx_id = client.send_transaction(signed_txn)

    response = wait_for_transaction(client, tx_id)
    assert response.application_index is not None and response.application_index > 0
    return response.application_index


def create_pool_app(client: AlgodClient, sender: Account) -> int:
    approval_program, clear_program = get_pool_contracts(client, 0, 0)

    global_schema = transaction.StateSchema(32, 32)
    local_schema = transaction.StateSchema(0, 0)

    txn = transaction.ApplicationCreateTxn(
        sender=sender.get_address(),
        sp=client.suggested_params(),
        on_complete=transaction.OnComplete.NoOpOC,
        approval_program=approval_program,
        clear_program=clear_program,
        global_schema=global_schema,
        local_schema=local_schema
    )
    signed_txn = txn.sign(sender.get_private_key())
    tx_id = client.send_transaction(signed_txn)

    response = wait_for_transaction(client, tx_id)
    assert response.application_index is not None and response.application_index > 0
    return response.application_index


def create_pool(client: AlgodClient, sender: Account, master_app_id: int, template_pool_id: int, asset_a: int, asset_b: int) -> int:
    assert asset_a < asset_b
    txn = transaction.PaymentTxn(
        sender=sender.get_address(),
        sp=client.suggested_params(),
        receiver=get_application_address(master_app_id),
        amt=2_715_000
    )
    signed_txn = txn.sign(sender.get_private_key())
    tx_id = client.send_transaction(signed_txn)
    
    wait_for_transaction(client, tx_id)
    
    txn2 = transaction.ApplicationCallTxn(
        sender=sender.get_address(),
        sp=client.suggested_params(),
        index=master_app_id,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[
            b"new_pool",
        ],
        foreign_assets=[
            asset_a,
            asset_b
        ],
        foreign_apps=[template_pool_id]
    )

    signed_txn2 = txn2.sign(sender.get_private_key())
    tx_id = client.send_transaction(signed_txn2)

    wait_for_transaction(client, tx_id)


def create_asset(client: AlgodClient, sender: Account, unitname: str):
    txn = transaction.AssetCreateTxn(
        sender=sender.get_address(),
        sp=client.suggested_params(),
        total=1_000_000,
        decimals=0,
        default_frozen=False,
        asset_name="asset",
        unit_name=unitname
    )
    signed_txn = txn.sign(sender.get_private_key())

    tx_id = client.send_transaction(signed_txn)

    response = wait_for_transaction(client, tx_id)

    assert response.asset_index is not None and response.asset_index > 0
    return response.asset_index
