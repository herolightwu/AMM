import os
from pyteal import *

tmpl_asset_a = Tmpl.Int("TMPL_ASSET_A")
tmpl_asset_b = Tmpl.Int("TMPL_ASSET_B")

fee = Int(5)
total_supply = Int(int(1e10))
scale = Int(1000)


class PoolContract:
    class Vars:
        gov_key = Bytes("gov")
        pool_key = Bytes("p")
        asset_a_key = Bytes("a")
        asset_b_key = Bytes("b")
        assets_set_key = Bytes("set")

    @staticmethod
    @Subroutine(TealType.none)
    def axfer(rx: TealType.bytes, aid: TealType.uint64, amt: TealType.uint64):
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: aid,
                    TxnField.asset_amount: amt,
                    TxnField.asset_receiver: rx,
                }
            ),
            InnerTxnBuilder.Submit(),
        )

    @staticmethod
    @Subroutine(TealType.none)
    def opt_in(aid: TealType.uint64):
        return PoolContract.axfer(Global.current_application_address(), aid, Int(0))

    @staticmethod
    @Subroutine(TealType.none)
    def create_pool_token(a: TealType.uint64, b: TealType.uint64):
        una = AssetParam.unitName(a)
        unb = AssetParam.unitName(b)

        return Seq(
            una,
            unb,
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetConfig,
                    TxnField.config_asset_name: Concat(
                        Bytes("DPT-"), una.value(), Bytes("-"), unb.value()
                    ),
                    TxnField.config_asset_unit_name: Bytes("dpt"),
                    TxnField.config_asset_total: total_supply,
                    TxnField.config_asset_decimals: Int(3),
                    TxnField.config_asset_manager: Global.current_application_address(),
                    TxnField.config_asset_reserve: Global.current_application_address(),
                }
            ),
            InnerTxnBuilder.Submit(),
            App.globalPut(
                PoolContract.Vars.pool_key,
                InnerTxn.created_asset_id()
            ),
        )

    @staticmethod
    @Subroutine(TealType.uint64)
    def mint_tokens(issued, asup, bsup, aamt, bamt):
        return If((aamt / asup) < (bamt / bsup), aamt / asup, bamt / bsup) * issued

    @staticmethod
    @Subroutine(TealType.uint64)
    def burn_tokens(issued, sup, amt):
        return sup * (amt / issued)

    @staticmethod
    @Subroutine(TealType.uint64)
    def swap_tokens(inamt, insup, outsup):
        factor = scale - fee
        return (inamt * factor * outsup) / ((insup * scale) + (inamt * factor))

    def on_create(self):
        return Seq(
            App.globalPut(self.Vars.gov_key, Txn.sender()),
            App.globalPut(self.Vars.asset_a_key, Int(0)),
            App.globalPut(self.Vars.asset_b_key, Int(0)),
            App.globalPut(self.Vars.assets_set_key, Int(0)),
            Approve()
        )

    def on_mint(self):
        asset_a = App.globalGet(self.Vars.asset_a_key)
        asset_b = App.globalGet(self.Vars.asset_b_key)
        assets_set = App.globalGet(self.Vars.assets_set_key)

        mine = Global.current_application_address()
        pool_token = App.globalGet(self.Vars.pool_key)

        pool_bal = AssetHolding.balance(mine, pool_token)
        a_bal = AssetHolding.balance(mine, asset_a)
        b_bal = AssetHolding.balance(mine, asset_b)

        return Seq(
            Assert(assets_set == Int(1)),  # check if assets set
            # Init MaybeValues
            pool_bal,
            a_bal,
            b_bal,
            # Check that the transaction is constructed correctly
            Assert(
                And(
                    Global.group_size() == Int(3),  # App call, Asset A, Asset B
                    And(
                        Txn.assets[0] == asset_a,
                        Txn.assets[1] == asset_b
                    ),
                    Gtxn[0].type_enum() == TxnType.ApplicationCall,
                    Gtxn[0].assets[0] == Gtxn[1].xfer_asset(),
                    Gtxn[0].assets[1] == Gtxn[2].xfer_asset(),
                    Gtxn[1].type_enum() == TxnType.AssetTransfer,
                    Gtxn[1].asset_receiver() == mine,
                    Gtxn[1].xfer_asset() == asset_a,
                    Gtxn[1].asset_amount() > Int(0),
                    Gtxn[1].sender() == Gtxn[0].sender(),
                    Gtxn[2].type_enum() == TxnType.AssetTransfer,
                    Gtxn[2].asset_receiver() == mine,
                    Gtxn[2].xfer_asset() == asset_b,
                    Gtxn[2].asset_amount() > Int(0),
                    Gtxn[2].sender() == Gtxn[0].sender(),
                )
            ),
            # Check that we have these things
            Assert(And(pool_bal.hasValue(), a_bal.hasValue(), b_bal.hasValue())),
            # mint tokens
            self.axfer(
                Gtxn[0].sender(),
                pool_token,
                self.mint_tokens(
                    total_supply - pool_bal.value(),
                    a_bal.value(),
                    b_bal.value(),
                    Gtxn[1].asset_amount(),
                    Gtxn[2].asset_amount(),
                ),
            ),
            Approve(),
        )

    def on_burn(self):
        asset_a = App.globalGet(self.Vars.asset_a_key)
        asset_b = App.globalGet(self.Vars.asset_b_key)
        assets_set = App.globalGet(self.Vars.assets_set_key)

        mine = Global.current_application_address()
        pool_token = App.globalGet(self.Vars.pool_key)

        pool_bal = AssetHolding.balance(mine, pool_token)
        a_bal = AssetHolding.balance(mine, asset_a)
        b_bal = AssetHolding.balance(mine, asset_b)

        return Seq(
            Assert(assets_set == Int(1)),  # check if assets set
            pool_bal,
            a_bal,
            b_bal,
            Assert(
                And(
                    Global.group_size() == Int(2),
                    And(
                        Txn.assets[0] == asset_a,
                        Txn.assets[1] == asset_b
                    ),
                    Gtxn[0].type_enum() == TxnType.ApplicationCall,
                    Gtxn[1].type_enum() == TxnType.AssetTransfer,
                    Gtxn[1].asset_receiver() == mine,
                    Gtxn[1].xfer_asset() == pool_token,
                )
            ),
            Assert(And(pool_bal.hasValue(), a_bal.hasValue(), b_bal.hasValue())),
            # Send back a
            self.axfer(
                Gtxn[1].sender(),
                asset_a,
                self.burn_tokens(
                    total_supply - pool_bal.value(),
                    a_bal.value(),
                    Gtxn[1].asset_amount(),
                ),
            ),
            # Send back b
            self.axfer(
                Gtxn[1].sender(),
                asset_b,
                self.burn_tokens(
                    total_supply - pool_bal.value(),
                    b_bal.value(),
                    Gtxn[1].asset_amount(),
                ),
            ),
            Approve(),
        )

    def on_swap(self):
        asset_a = App.globalGet(self.Vars.asset_a_key)
        asset_b = App.globalGet(self.Vars.asset_b_key)
        assets_set = App.globalGet(self.Vars.assets_set_key)

        mine = Global.current_application_address()

        in_id = Gtxn[1].xfer_asset()
        out_id = If(
            Gtxn[1].xfer_asset() == asset_a,
            asset_b,
            asset_a
        )

        in_sup = AssetHolding.balance(mine, in_id)
        out_sup = AssetHolding.balance(mine, out_id)

        return Seq(
            Assert(assets_set == Int(1)),  # check if assets set
            in_sup,
            out_sup,
            Assert(
                And(
                    Global.group_size() == Int(2),
                    And(
                        Txn.assets[0] == asset_a,
                        Txn.assets[1] == asset_b
                    ),
                    Gtxn[0].type_enum() == TxnType.ApplicationCall,
                    Gtxn[1].type_enum() == TxnType.AssetTransfer,
                    Or(in_id == asset_a, in_id == asset_b),
                    Gtxn[1].asset_amount() > Int(0),
                )
            ),
            Assert(And(in_sup.hasValue(), out_sup.hasValue())),
            self.axfer(
                Gtxn[1].sender(),
                out_id,
                self.swap_tokens(
                    Gtxn[1].asset_amount(),
                    in_sup.value(),
                    out_sup.value()
                ),
            ),
            Approve(),
        )

    def on_bootstrap(self):
        asset_a = App.globalGet(self.Vars.asset_a_key)
        asset_b = App.globalGet(self.Vars.asset_b_key)
        assets_set = App.globalGet(self.Vars.assets_set_key)
        gov = App.globalGet(self.Vars.gov_key)

        return Seq(
            Assert(assets_set == Int(1)),  # check if assets set
            Assert(
                And(
                    Global.group_size() == Int(1),
                    Gtxn[0].type_enum() == TxnType.ApplicationCall,
                    And(
                        Txn.assets[0] == asset_a,
                        Txn.assets[1] == asset_b
                    ),
                )
            ),
            Assert(gov == Txn.sender()),
            self.create_pool_token(asset_a, asset_b),
            self.opt_in(asset_a),
            self.opt_in(asset_b),
            Approve(),
        )

    def on_fund(self):
        assets_set = App.globalGet(self.Vars.assets_set_key)
        asset_a = App.globalGet(self.Vars.asset_a_key)
        asset_b = App.globalGet(self.Vars.asset_b_key)
        pool_token = App.globalGet(self.Vars.pool_key)

        return Seq(
            Assert(assets_set == Int(1)),
            Assert(
                And(
                    Global.group_size() == Int(3),
                    Gtxn[0].type_enum() == TxnType.ApplicationCall,
                    And(
                        Txn.assets[0] == asset_a,
                        Txn.assets[1] == asset_b,
                        Txn.assets[2] == pool_token
                    ),
                    Gtxn[1].type_enum() == TxnType.AssetTransfer,
                    Gtxn[1].xfer_asset() == asset_a,
                    Gtxn[1].asset_amount() > Int(0),
                    Gtxn[1].sender() == Gtxn[0].sender(),
                    Gtxn[2].type_enum() == TxnType.AssetTransfer,
                    Gtxn[2].xfer_asset() == asset_b,
                    Gtxn[2].asset_amount() > Int(0),
                    Gtxn[2].sender() == Gtxn[0].sender(),
                )
            ),
            self.axfer(
                Gtxn[0].sender(),
                pool_token,
                Sqrt(Gtxn[1].asset_amount() * Gtxn[2].asset_amount()) - scale,
            ),
            Approve()
        )

    def on_update_governor(self):
        gov = App.globalGet(self.Vars.gov_key)
        new_governor = Txn.accounts[1]
        return Seq(
            Assert(gov == Txn.sender()),
            App.globalPut(self.Vars.gov_key, new_governor),
            Approve()
        )

    def on_set_assets(self):
        gov = App.globalGet(self.Vars.gov_key)
        assets_set = App.globalGet(self.Vars.assets_set_key)
        asset_a = Txn.assets[0]
        asset_b = Txn.assets[1]
        return Seq(
            Assert(
                And(
                    gov == Txn.sender(),
                    asset_a < asset_b,
                    assets_set == Int(0)
                )
            ),
            App.globalPut(self.Vars.asset_a_key, asset_a),
            App.globalPut(self.Vars.asset_b_key, asset_b),
            App.globalPut(self.Vars.assets_set_key, Int(1)),
            Approve()
        )

    def on_call(self):
        on_call_method = Txn.application_args[0]
        return Cond(
            # Users
            [on_call_method == Bytes("mint"), self.on_mint()],
            [on_call_method == Bytes("burn"), self.on_burn()],
            [on_call_method == Bytes("swap"), self.on_swap()],
            # Admin
            [on_call_method == Bytes("boot"), self.on_bootstrap()],
            [on_call_method == Bytes("fund"), self.on_fund()],
            [on_call_method == Bytes("update"), self.on_update_governor()],
            [on_call_method == Bytes("set"), self.on_set_assets()],
        )

    def approval_program(self):
        gov = App.globalGet(self.Vars.gov_key)
        return Cond(
            [Txn.application_id() == Int(0), self.on_create()],
            [
                Or(
                    Txn.on_completion() == OnComplete.DeleteApplication,
                    Txn.on_completion() == OnComplete.UpdateApplication,
                ),
                Return(gov == Txn.sender())
            ],
            [Txn.on_completion() == OnComplete.CloseOut, Approve()],
            [Txn.on_completion() == OnComplete.OptIn, Reject()],
            [Txn.on_completion() == OnComplete.NoOp, self.on_call()],
        )

    def clear_program(self):
        return Approve()


if __name__ == "__main__":
    path = os.path.dirname(os.path.abspath(__file__))

    contract = PoolContract()

    with open(os.path.join(path, "pool_approval.teal"), "w") as f:
        compiled = compileTeal(
            contract.approval_program(), 
            mode=Mode.Application, 
            version=6, 
            assembleConstants=True
        )
        f.write(compiled)

    with open(os.path.join(path, "pool_clear.teal"), "w") as f:
        compiled = compileTeal(
            contract.clear_program(), 
            mode=Mode.Application, 
            version=6, 
            assembleConstants=True
        )
        f.write(compiled)
